import json
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from accounts.models import User, UserSettings, NotificationPreference, LoginHistory, AuditLog, PlatformSetting
from recruitment.models import Job, Notification, Organization, OrganizationMember


class NavbarAndSettingsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

        # Create Owner User
        self.owner = User.objects.create_user(
            username="test_owner_user",
            email="owner@hirenexa.com",
            password="OwnerPassword123!",
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
        )

        # Create Candidate User
        self.candidate = User.objects.create_user(
            username="test_candidate_user",
            email="candidate@hirenexa.com",
            password="CandidatePassword123!",
            role=User.Role.CANDIDATE,
        )

        # Create Recruiter User
        self.recruiter = User.objects.create_user(
            username="test_recruiter_user",
            email="recruiter@hirenexa.com",
            password="RecruiterPassword123!",
            role=User.Role.RECRUITER,
        )

        # Create Notification for candidate
        Notification.objects.create(
            recipient=self.candidate,
            title="Interview Invitation",
            message="You have been invited for a technical round.",
            notification_type=Notification.Type.INTERVIEW,
            is_read=False,
        )

    def test_anonymous_context_processor(self):
        """Anonymous visitor context should have is_authenticated=False and 0 unread."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_authenticated"])
        self.assertEqual(response.context["unread_notifications_count"], 0)
        self.assertContains(response, "Sign In")
        self.assertContains(response, "Sign Up Free")

    def test_authenticated_candidate_context_and_navbar(self):
        """Authenticated candidate receives role badge, unread count, and settings links."""
        self.client.login(username="test_candidate_user", password="CandidatePassword123!")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_authenticated"])
        self.assertEqual(response.context["current_role"], "CANDIDATE")
        self.assertEqual(response.context["unread_notifications_count"], 1)
        # Check navbar components
        self.assertContains(response, "My Profile")
        self.assertContains(response, "Account Settings")
        self.assertContains(response, "Security (Password, 2FA, Sessions)")
        self.assertContains(response, "Logout")
        self.assertContains(response, "Alerts Center")
        self.assertContains(response, "HireNexa AI")
        self.assertNotContains(response, "Owner Control Center")

    def test_owner_context_and_available_portals(self):
        """Platform Owner has universal access across all portals."""
        self.client.login(username="test_owner_user", password="OwnerPassword123!")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_role"], "OWNER")
        available = response.context["available_portals"]
        roles = [p["role"] for p in available]
        self.assertIn("OWNER", roles)
        self.assertIn("COMPANY_ADMIN", roles)
        self.assertIn("RECRUITER", roles)
        self.assertIn("FREELANCER", roles)
        self.assertIn("CANDIDATE", roles)
        self.assertContains(response, "Owner Control Center")

    def test_secure_portal_switch(self):
        """Owner switches active portal via secure POST request."""
        self.client.login(username="test_owner_user", password="OwnerPassword123!")
        response = self.client.post(reverse("switch_portal"), {"portal_role": "RECRUITER"})
        self.assertEqual(response.status_code, 302)
        # Verify session active role updated
        session = self.client.session
        self.assertEqual(session.get("active_role"), "RECRUITER")

    def test_unauthorized_portal_switch_blocked(self):
        """Regular Candidate cannot switch to Owner portal."""
        self.client.login(username="test_candidate_user", password="CandidatePassword123!")
        response = self.client.post(reverse("switch_portal"), {"portal_role": "OWNER"})
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        self.assertNotEqual(session.get("active_role"), "OWNER")

    def test_logout_strictly_requires_post(self):
        """GET request to logout does not log user out; POST logs user out with CSRF."""
        self.client.login(username="test_candidate_user", password="CandidatePassword123!")
        # GET should be rejected and redirect back
        get_response = self.client.get(reverse("logout"))
        self.assertEqual(get_response.status_code, 302)
        # Check user is still authenticated
        home_res = self.client.get(reverse("home"))
        self.assertTrue(home_res.context["user"].is_authenticated)

        # POST should securely log user out
        post_response = self.client.post(reverse("logout"))
        self.assertEqual(post_response.status_code, 302)
        home_after = self.client.get(reverse("home"))
        self.assertFalse(home_after.context["user"].is_authenticated)

    def test_settings_profile_view_get_and_post(self):
        """Profile settings update saves headline and location to UserSettings."""
        self.client.login(username="test_candidate_user", password="CandidatePassword123!")
        response = self.client.get(reverse("settings_profile"))
        self.assertEqual(response.status_code, 200)

        post_data = {
            "first_name": "Arjun",
            "last_name": "Patel",
            "phone_number": "+919876543210",
            "headline": "Lead Python Engineer",
            "location": "Bhubaneswar, India",
            "bio": "Experienced backend architect.",
            "website_url": "https://arjun.dev",
            "github_url": "https://github.com/arjun",
            "linkedin_url": "https://linkedin.com/in/arjun",
            "twitter_url": "",
        }
        res = self.client.post(reverse("settings_profile"), post_data)
        self.assertEqual(res.status_code, 302)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.first_name, "Arjun")
        self.assertEqual(self.candidate.settings.headline, "Lead Python Engineer")
        self.assertEqual(self.candidate.settings.location, "Bhubaneswar, India")

    def test_settings_security_password_and_2fa(self):
        """Security settings allows password change and 2FA toggle."""
        self.client.login(username="test_candidate_user", password="CandidatePassword123!")
        
        # Toggle 2FA
        res = self.client.post(reverse("settings_security"), {
            "action": "toggle_2fa",
            "two_factor_enabled": "on",
            "two_factor_method": "EMAIL",
        })
        self.assertEqual(res.status_code, 302)
        self.candidate.settings.refresh_from_db()
        self.assertTrue(self.candidate.settings.two_factor_enabled)

        # Generate Backup codes
        res2 = self.client.post(reverse("settings_security"), {
            "action": "generate_backup_codes",
        })
        self.assertEqual(res2.status_code, 302)
        self.candidate.settings.refresh_from_db()
        self.assertEqual(len(self.candidate.settings.backup_codes), 8)

    def test_settings_privacy_gdpr_export(self):
        """GDPR data download returns JSON archive of user account."""
        self.client.login(username="test_candidate_user", password="CandidatePassword123!")
        res = self.client.post(reverse("settings_privacy"), {"action": "download_gdpr_data"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/json")
        data = json.loads(res.content)
        self.assertEqual(data["user_account"]["username"], "test_candidate_user")

    def test_platform_settings_permission_check(self):
        """Non-owner users are blocked from accessing Platform Governance Settings."""
        self.client.login(username="test_candidate_user", password="CandidatePassword123!")
        res = self.client.get(reverse("settings_platform"))
        self.assertEqual(res.status_code, 302)  # Redirected away

        # Owner has full access
        self.client.login(username="test_owner_user", password="OwnerPassword123!")
        res_owner = self.client.get(reverse("settings_platform"))
        self.assertEqual(res_owner.status_code, 200)
        self.assertContains(res_owner, "Platform Master Governance")
