from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.management import call_command
from django.core.management.base import CommandError
from accounts.models import User, EmailOTP


class OwnerLoginAuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner_password = "SecureOwnerPassword123!"
        self.owner = User.objects.create_user(
            username="owner_admin",
            email="owner_admin@hirenexa.internal",
            password=self.owner_password,
            is_active=True,
            is_staff=True,
            is_superuser=True,
            role="owner",
        )
        self.login_url = reverse("owner_login")

    @override_settings(OWNER_REQUIRE_OTP=False)
    def test_owner_password_login_works_without_otp(self):
        """1. Owner password login works without OTP when OWNER_REQUIRE_OTP=False."""
        response = self.client.post(self.login_url, {
            "username": "owner_admin",
            "password": self.owner_password,
        })
        # Should redirect to owner_dashboard
        self.assertRedirects(response, reverse("owner_dashboard"))
        # User is authenticated in session
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)
        # Should not issue an OTP record
        self.assertFalse(EmailOTP.objects.filter(user=self.owner).exists())
        # Can access owner dashboard
        dash_response = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(dash_response.status_code, 200)

    @override_settings(OWNER_REQUIRE_OTP=False)
    def test_owner_login_works_with_email_identifier(self):
        """Owner can log in using their email address as identifier."""
        response = self.client.post(self.login_url, {
            "username": "owner_admin@hirenexa.internal",
            "password": self.owner_password,
        })
        self.assertRedirects(response, reverse("owner_dashboard"))
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)

    @override_settings(OWNER_REQUIRE_OTP=False)
    def test_owner_login_works_with_case_insensitive_identifier(self):
        """Owner can log in with case-insensitive username or email."""
        response = self.client.post(self.login_url, {
            "username": "OWNER_ADMIN@HIRENEXA.INTERNAL",
            "password": self.owner_password,
        })
        self.assertRedirects(response, reverse("owner_dashboard"))
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)

    @override_settings(OWNER_REQUIRE_OTP=False)
    def test_wrong_password_fails(self):
        """2. Wrong password fails with error and does not authenticate."""
        response = self.client.post(self.login_url, {
            "username": "owner_admin",
            "password": "IncorrectPassword999!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        self.assertContains(response, "Invalid administrator credentials")

    @override_settings(OWNER_REQUIRE_OTP=False)
    def test_inactive_user_fails(self):
        """3. Inactive owner account fails with generic error and does not authenticate."""
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])

        response = self.client.post(self.login_url, {
            "username": "owner_admin",
            "password": self.owner_password,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        self.assertContains(response, "Invalid administrator credentials")

    @override_settings(OWNER_REQUIRE_OTP=False)
    def test_non_owner_denied(self):
        """4. Non-owner (candidate/recruiter) is denied access to owner login."""
        candidate_pwd = "CandidateSecret123!"
        candidate = User.objects.create_user(
            username="candidate_john",
            email="candidate_john@example.com",
            password=candidate_pwd,
            is_active=True,
            is_staff=False,
            is_superuser=False,
            role=User.Role.CANDIDATE,
        )

        response = self.client.post(self.login_url, {
            "username": "candidate_john",
            "password": candidate_pwd,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        self.assertContains(response, "Invalid administrator credentials")

    @override_settings(OWNER_REQUIRE_OTP=True)
    def test_otp_is_enforced_when_owner_require_otp_true(self):
        """5. OTP is enforced when OWNER_REQUIRE_OTP=True."""
        response = self.client.post(self.login_url, {
            "username": "owner_admin",
            "password": self.owner_password,
        })
        # Should NOT log in directly
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        # Should set preauth session id
        self.assertEqual(self.client.session.get("owner_preauth_id"), self.owner.id)
        # Should redirect to OTP verification page
        self.assertRedirects(response, reverse("owner_login_otp_verify"))
        # Should have generated an EmailOTP record
        self.assertTrue(EmailOTP.objects.filter(user=self.owner, purpose=EmailOTP.Purpose.LOGIN).exists())

    def test_public_signup_cannot_create_owner_or_superuser(self):
        """6. Public signup cannot create owner or superuser accounts (server-side check)."""
        response = self.client.post(reverse("signup"), {
            "full_name": "Malicious User",
            "username": "malicious_user",
            "email": "malicious@example.com",
            "phone_number": "9812345678",
            "country_code": "+91",
            "role": "OWNER",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
            "terms": "on",
        })
        created = User.objects.filter(username="malicious_user").first()
        if created:
            self.assertNotEqual(str(created.role).upper(), "OWNER")
            self.assertFalse(created.is_superuser)
            self.assertFalse(created.is_staff)


class ResetAndCreateOwnerCommandTests(TestCase):
    @override_settings(DEBUG=True, ENVIRONMENT="development")
    def test_command_refuses_without_i_understand_flag(self):
        """reset_and_create_owner raises CommandError without --i-understand flag."""
        with self.assertRaises(CommandError) as ctx:
            call_command("reset_and_create_owner")
        self.assertIn("--i-understand", str(ctx.exception))

    def test_command_refuses_in_production(self):
        """reset_and_create_owner raises CommandError in production environment."""
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError) as ctx:
                call_command("reset_and_create_owner", i_understand=True)
            self.assertIn("SECURITY VIOLATION", str(ctx.exception))

    def test_command_refuses_when_environment_is_production(self):
        """reset_and_create_owner raises CommandError when ENVIRONMENT=production."""
        with override_settings(ENVIRONMENT="production"):
            with self.assertRaises(CommandError) as ctx:
                call_command("reset_and_create_owner", i_understand=True)
            self.assertIn("SECURITY VIOLATION", str(ctx.exception))
