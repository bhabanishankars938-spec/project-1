import os
import time
from datetime import timedelta
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Q
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from accounts.models import User, AuditLog, PlatformSetting, EmailOTP
from unittest.mock import patch
import smtplib
import socket
from django.core import mail
from accounts.services.email_service import send_otp_email, EmailSendResult
from accounts.utils import mask_email
from recruitment.models import (
    Job, Application, Resume, CandidateProfile, RecruiterProfile,
    FreelancerProfile, Project, ProjectProposal, Organization
)
from core.sqlalchemy_db import (
    get_database_diagnostics,
    fetch_platform_analytics_sqla,
    fetch_audit_logs_sqla,
)


class MultiRoleAuthenticationTests(TestCase):
    """
    Comprehensive verification of HireNexa Multi-Role Authentication System:
    1. Owner / Super Admin
    2. HR / Recruiter
    3. Freelancer
    4. Student / Candidate
    """

    def get_latest_email_otp(self):
        from django.core import mail
        import re
        if mail.outbox:
            for message in reversed(mail.outbox):
                match = re.search(r'\b\d{6}\b', message.body)
                if match:
                    return match.group(0)
        return ""

    def setUp(self):
        self.client = Client()

        # 1. Platform Owner dummy account
        self.owner_user = User.objects.create_user(
            username="test_owner",
            email="owner@hirenexa.internal",
            password="OwnerPassword123!",
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
        )

        # 2. HR / Recruiter dummy account
        self.hr_user = User.objects.create_user(
            username="test_recruiter",
            email="hr@techcorp.io",
            password="RecruiterPass123!",
            role=User.Role.RECRUITER,
        )
        self.hr_profile = RecruiterProfile.objects.create(
            user=self.hr_user,
            company_name="TechCorp Solutions",
        )

        # Secondary HR dummy account for multi-tenant isolation testing
        self.second_hr_user = User.objects.create_user(
            username="second_recruiter",
            email="hr2@acme.com",
            password="SecondRecruiterPass123!",
            role=User.Role.RECRUITER,
        )
        self.second_hr_profile = RecruiterProfile.objects.create(
            user=self.second_hr_user,
            company_name="Acme Global",
        )

        # 3. Freelancer dummy account
        self.freelancer_user = User.objects.create_user(
            username="test_freelancer",
            email="alex@freelancer.dev",
            password="FreelancerPass123!",
            role=User.Role.FREELANCER,
        )
        self.freelancer_profile = FreelancerProfile.objects.create(
            user=self.freelancer_user,
            full_name="Alex Rivers",
            headline="Full-Stack Engineer & Cloud Specialist",
            hourly_rate=65.00,
            skills="Python, Django, React, AWS",
        )

        # 4. Student / Candidate dummy account
        self.candidate_user = User.objects.create_user(
            username="test_student",
            email="student@university.edu",
            password="StudentPass123!",
            role=User.Role.CANDIDATE,
        )
        self.candidate_profile = CandidateProfile.objects.create(
            user=self.candidate_user,
            full_name="Priya Sharma",
            university="National Institute of Technology",
            cgpa="8.9",
            skills="Python, SQL, HTML, CSS",
        )

        # Create a sample job posted by HR 1
        self.job = Job.objects.create(
            recruiter=self.hr_user,
            title="Backend Python Engineer",
            company_name="TechCorp Solutions",
            description="Build scalable REST APIs with Django and PostgreSQL.",
            required_skills="Python, Django, PostgreSQL",
            is_active=True,
        )

        # Create a sample freelance project posted by HR 1
        self.project = Project.objects.create(
            client=self.hr_user,
            title="Develop Payment Webhook Service",
            company_name="TechCorp Solutions",
            description="Build webhook processing backend with retry logic.",
            budget_type="FIXED",
            budget_min=800,
            budget_max=1500,
            required_skills="Python, Redis, Stripe",
            is_active=True,
        )

    # ==========================================================================
    # 1. OWNER / SUPER ADMIN TESTS
    # ==========================================================================

    def test_owner_login_success_and_dashboard_access(self):
        """Owner signs in through dedicated portal with two-step email OTP and accesses admin dashboard."""
        response = self.client.post(
            reverse("owner_login"),
            {"username": "test_owner", "password": "OwnerPassword123!"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("owner_preauth_id", self.client.session)

        # Retrieve generated 2FA OTP
        otp_obj = EmailOTP.objects.filter(
            user=self.owner_user,
            purpose=EmailOTP.Purpose.LOGIN,
            is_used=False
        ).order_by("-created_at").first()
        self.assertIsNotNone(otp_obj)

        # Step 2: Complete OTP verification
        otp_response = self.client.post(
            reverse("owner_login_otp_verify"),
            {"otp_code": self.get_latest_email_otp()},
            follow=True,
        )
        self.assertEqual(otp_response.status_code, 200)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.owner_user.id)

        # Check access to Owner Dashboard
        dash_response = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(dash_response.status_code, 200)
        self.assertContains(dash_response, "PLATFORM OWNER")

        # Verify audit log recorded
        log_exists = AuditLog.objects.filter(
            user=self.owner_user, action="OWNER_2FA_LOGIN_SUCCESS"
        ).exists()
        self.assertTrue(log_exists)

    def test_owner_portal_rejects_non_owner(self):
        """Non-owner accounts are strictly blocked from logging in via Owner portal."""
        response = self.client.post(
            reverse("owner_login"),
            {"username": "test_student", "password": "StudentPass123!"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        # Should NOT be logged in as owner
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "Access Denied")

        # Audit log tracks unauthorized attempt
        log_exists = AuditLog.objects.filter(
            action="UNAUTHORIZED_OWNER_PORTAL_ATTEMPT"
        ).exists()
        self.assertTrue(log_exists)

    def test_owner_login_wrong_password(self):
        """Owner login fails with wrong password, records audit log without leaking info to UI."""
        response = self.client.post(
            reverse("owner_login"),
            {"username": "test_owner", "password": "WrongPassword999!"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("owner_preauth_id", self.client.session)
        self.assertContains(response, "Invalid administrator credentials.")

        # Server-side audit log records failure with exact reason
        log = AuditLog.objects.filter(
            action="FAILED_OWNER_PORTAL_LOGIN",
            user=self.owner_user,
        ).order_by("-timestamp").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details.get("reason"), "INVALID_PASSWORD")

    def test_owner_login_missing_account(self):
        """Owner login with non-existent identifier returns generic error to prevent user enumeration."""
        response = self.client.post(
            reverse("owner_login"),
            {"username": "non_existent_admin", "password": "AnyPassword123!"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("owner_preauth_id", self.client.session)
        self.assertContains(response, "Invalid administrator credentials.")

        # Server-side audit log records failure with ACCOUNT_NOT_FOUND
        log = AuditLog.objects.filter(
            action="FAILED_OWNER_PORTAL_LOGIN",
            details__reason="ACCOUNT_NOT_FOUND",
        ).order_by("-timestamp").first()
        self.assertIsNotNone(log)

    def test_owner_login_inactive_account(self):
        """Inactive owner cannot log in or trigger OTP dispatch."""
        self.owner_user.is_active = False
        self.owner_user.save()

        response = self.client.post(
            reverse("owner_login"),
            {"username": "test_owner", "password": "OwnerPassword123!"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("owner_preauth_id", self.client.session)
        self.assertContains(response, "Invalid administrator credentials.")

        # Audit log tracks inactive failure
        log = AuditLog.objects.filter(
            action="FAILED_OWNER_PORTAL_LOGIN",
            details__reason="ACCOUNT_INACTIVE",
        ).order_by("-timestamp").first()
        self.assertIsNotNone(log)

        # Restore active status
        self.owner_user.is_active = True
        self.owner_user.save()

    def test_missing_owner_shows_setup_state(self):
        """When no Platform Owner account exists in DB, login page displays first-time setup banner."""
        # Remove any owner/superuser accounts
        User.objects.filter(Q(role=User.Role.OWNER) | Q(is_superuser=True)).delete()

        response = self.client.get(reverse("owner_login"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["owner_exists"])
        self.assertContains(response, "First-Time Setup Required")
        self.assertContains(response, "Initialize Platform Owner Account")

    def test_first_time_owner_setup_flow(self):
        """Verify full first-time owner initialization flow through web interface."""
        import re
        # Ensure 0 owners exist
        User.objects.filter(Q(role=User.Role.OWNER) | Q(is_superuser=True)).delete()

        # Step 1: Access setup view
        get_resp = self.client.get(reverse("first_time_owner_setup"))
        self.assertEqual(get_resp.status_code, 200)

        # Step 2: Submit owner registration form
        mail.outbox.clear()
        post_resp = self.client.post(reverse("first_time_owner_setup"), {
            "full_name": "Root Administrator",
            "username": "root_owner",
            "email": "root_owner@hirenexa.internal",
            "phone_number": "+919876543299",
            "password": "MasterSecurePassword123!",
            "confirm_password": "MasterSecurePassword123!",
        })
        self.assertRedirects(post_resp, reverse("first_time_owner_setup_verify"))

        # Step 3: Verify OTP created & dispatched
        otp_record = EmailOTP.objects.filter(
            email="root_owner@hirenexa.internal",
            purpose=EmailOTP.Purpose.OWNER_SETUP,
        ).first()
        self.assertIsNotNone(otp_record)

        # Get raw OTP code from mail outbox
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r'\b\d{6}\b', mail.outbox[0].body)
        self.assertIsNotNone(match)
        raw_code = match.group(0)

        # Step 4: Verify OTP and finalize owner creation
        verify_resp = self.client.post(reverse("first_time_owner_setup_verify"), {
            "otp_code": raw_code,
        })
        self.assertRedirects(verify_resp, reverse("owner_dashboard"))

        # Check owner created in DB
        new_owner = User.objects.filter(username="root_owner").first()
        self.assertIsNotNone(new_owner)
        self.assertEqual(new_owner.role, User.Role.OWNER)
        self.assertTrue(new_owner.is_superuser)
        self.assertTrue(new_owner.is_staff)
        self.assertTrue(new_owner.is_active)
        self.assertTrue(new_owner.is_email_verified)

        # Step 5: Verify setup route is now locked for unauthenticated users
        self.client.logout()
        locked_resp = self.client.get(reverse("first_time_owner_setup"))
        self.assertRedirects(locked_resp, reverse("owner_login"))

    def test_create_platform_owner_command_idempotent(self):
        """Verify create_platform_owner management command is idempotent and properly configures owner."""
        # 1. First run creates owner
        call_command(
            "create_platform_owner",
            username="cli_test_owner",
            email="cli_test_owner@hirenexa.internal",
            password="CliOwnerPassword123!",
            non_interactive=True,
        )
        owner = User.objects.filter(username="cli_test_owner").first()
        self.assertIsNotNone(owner)
        self.assertEqual(owner.role, User.Role.OWNER)
        self.assertTrue(owner.is_superuser)
        self.assertTrue(owner.is_staff)
        self.assertTrue(owner.is_active)
        self.assertTrue(owner.check_password("CliOwnerPassword123!"))

        # 2. Second run updates owner idempotently without duplicate error
        call_command(
            "create_platform_owner",
            username="cli_test_owner",
            email="cli_test_owner@hirenexa.internal",
            password="NewCliOwnerPassword456!",
            non_interactive=True,
        )
        owner.refresh_from_db()
        self.assertTrue(owner.check_password("NewCliOwnerPassword456!"))
        self.assertEqual(owner.role, User.Role.OWNER)

    def test_non_owner_dashboard_access_forbidden(self):
        """Non-owner logged in user cannot directly access Owner Dashboard (403)."""
        self.client.login(username="test_student", password="StudentPass123!")
        response = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_owner_user_management_actions(self):
        """Owner can toggle user status and update roles."""
        self.client.login(username="test_owner", password="OwnerPassword123!")

        # Toggle student active status
        toggle_url = reverse("owner_toggle_user_status", args=[self.candidate_user.id])
        resp = self.client.post(toggle_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.candidate_user.refresh_from_db()
        self.assertFalse(self.candidate_user.is_active)

        # Update role from Candidate to Freelancer
        role_url = reverse("owner_change_user_role", args=[self.candidate_user.id])
        resp2 = self.client.post(role_url, {"role": "FREELANCER"}, follow=True)
        self.assertEqual(resp2.status_code, 200)
        self.candidate_user.refresh_from_db()
        self.assertEqual(self.candidate_user.role, User.Role.FREELANCER)

    def test_owner_platform_settings_update(self):
        """Owner can update global platform operational settings."""
        self.client.login(username="test_owner", password="OwnerPassword123!")
        settings_url = reverse("owner_update_setting")
        resp = self.client.post(
            settings_url,
            {
                "key": "SESSION_TIMEOUT_MINUTES",
                "value": "120",
                "description": "2 hour timeout",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PlatformSetting.get_value("SESSION_TIMEOUT_MINUTES"), "120")

    # ==========================================================================
    # 2. HR / RECRUITER TESTS
    # ==========================================================================

    def test_hr_login_and_workspace(self):
        """HR logs in via HR portal and accesses recruiter dashboard."""
        resp = self.client.post(
            reverse("hr_login"),
            {"username": "test_recruiter", "password": "RecruiterPass123!"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.hr_user.id)

        # Check HR Dashboard
        dash = self.client.get(reverse("hr_dashboard"))
        self.assertEqual(dash.status_code, 200)

    def test_hr_multi_tenant_isolation(self):
        """HR user cannot view or evaluate candidates for another HR user's jobs."""
        self.client.login(username="second_recruiter", password="SecondRecruiterPass123!")
        # Attempt to access applicants for self.job (owned by test_recruiter)
        resp = self.client.get(reverse("applicants", args=[self.job.id]))
        self.assertEqual(resp.status_code, 403)

    # ==========================================================================
    # 3. FREELANCER TESTS
    # ==========================================================================

    def test_freelancer_registration_and_login(self):
        """Freelancer registers, logs in, and accesses freelancer workspace."""
        # Registration
        reg_resp = self.client.post(
            reverse("freelancer_signup"),
            {
                "full_name": "New Freelancer",
                "username": "new_freelancer",
                "email": "newfreelancer@test.com",
                "country_code": "+91",
                "phone_number": "9812345672",
                "headline": "React & Django Developer",
                "password1": "SecureFreelance123!",
                "password2": "SecureFreelance123!",
            },
            follow=True,
        )
        self.assertEqual(reg_resp.status_code, 200)
        new_freelancer = User.objects.get(username="new_freelancer")
        self.assertEqual(new_freelancer.role, User.Role.FREELANCER)
        self.assertTrue(FreelancerProfile.objects.filter(user=new_freelancer).exists())
        self.assertFalse(new_freelancer.is_active)

        # Activate user post-verification for dashboard access
        new_freelancer.is_active = True
        new_freelancer.is_email_verified = True
        new_freelancer.is_phone_verified = True
        new_freelancer.save()

        # Freelancer Dashboard access
        self.client.login(username="new_freelancer", password="SecureFreelance123!")
        dash = self.client.get(reverse("freelancer_dashboard"))
        self.assertEqual(dash.status_code, 200)
        self.assertContains(dash, "Freelance Contractor Dashboard")

    def test_freelancer_project_proposal_submission(self):
        """Freelancer browses project and submits quote/proposal."""
        self.client.login(username="test_freelancer", password="FreelancerPass123!")

        apply_url = reverse("project_apply", args=[self.project.id])
        resp = self.client.post(
            apply_url,
            {
                "bid_amount": 950.00,
                "estimated_days": 10,
                "cover_letter": "I have extensive experience building Stripe webhook listeners in Django.",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        proposal = ProjectProposal.objects.filter(
            project=self.project, freelancer=self.freelancer_user
        ).first()
        self.assertIsNotNone(proposal)
        self.assertEqual(float(proposal.bid_amount), 950.00)
        self.assertEqual(proposal.status, "PENDING")

    # ==========================================================================
    # 4. STUDENT / CANDIDATE TESTS
    # ==========================================================================

    def test_candidate_registration_and_login(self):
        """Student registers, logs in, and accesses student workspace."""
        reg_resp = self.client.post(
            reverse("candidate_signup"),
            {
                "full_name": "New Student",
                "username": "new_student",
                "email": "newstudent@college.edu",
                "country_code": "+91",
                "phone_number": "9812345673",
                "password1": "CollegePass123!",
                "password2": "CollegePass123!",
            },
            follow=True,
        )
        self.assertEqual(reg_resp.status_code, 200)
        new_student = User.objects.get(username="new_student")
        self.assertEqual(new_student.role, User.Role.CANDIDATE)
        self.assertTrue(CandidateProfile.objects.filter(user=new_student).exists())
        self.assertFalse(new_student.is_active)

        # Activate user post-verification for dashboard access
        new_student.is_active = True
        new_student.is_email_verified = True
        new_student.is_phone_verified = True
        new_student.save()

        # Candidate Dashboard access
        self.client.login(username="new_student", password="CollegePass123!")
        dash = self.client.get(reverse("candidate_dashboard"))
        self.assertEqual(dash.status_code, 200)

    # ==========================================================================
    # 5. SECURITY RULES & PRIVILEGE ENFORCEMENT
    # ==========================================================================

    def test_public_registration_cannot_select_owner_role(self):
        """Adversarial attempt to register with role=OWNER is strictly rejected."""
        resp = self.client.post(
            reverse("signup"),
            {
                "username": "hacker_owner",
                "email": "hacker@evil.com",
                "role": "OWNER",
                "password1": "HackerPassword123!",
                "password2": "HackerPassword123!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # Verify user was NOT created
        self.assertFalse(User.objects.filter(username="hacker_owner").exists())

    def test_demo_login_blocks_owner(self):
        """Demo 1-Click login strictly rejects OWNER role requests."""
        resp = self.client.get(reverse("demo_login", args=["owner"]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_setup_owner_management_command(self):
        """Test initial owner creation via CLI setup command."""
        call_command(
            "setup_owner",
            username="cli_admin_owner",
            email="cli_owner@hirenexa.internal",
            password="SecureAdminKey999!",
            non_interactive=True,
        )
        owner_acc = User.objects.get(username="cli_admin_owner")
        self.assertEqual(owner_acc.role, User.Role.OWNER)
        self.assertTrue(owner_acc.is_superuser)
        self.assertTrue(owner_acc.is_staff)
        self.assertTrue(owner_acc.check_password("SecureAdminKey999!"))

    def test_logout_and_session_cleared(self):
        """Logging out flushes the session and creates an audit log entry."""
        self.client.login(username="test_owner", password="OwnerPassword123!")
        resp = self.client.post(reverse("logout"), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    # ==========================================================================
    # 6. SQLALCHEMY DATABASE & ANALYTICS TESTS
    # ==========================================================================

    def test_sqlalchemy_diagnostics_and_analytics(self):
        """Verify SQLAlchemy engine connectivity and analytics aggregation."""
        diag = get_database_diagnostics()
        self.assertTrue(diag["is_connected"])
        self.assertIn("SQLAlchemy", diag["engine"])

        analytics = fetch_platform_analytics_sqla()
        self.assertIn("total_users", analytics)
        self.assertIn("total_jobs", analytics)
        self.assertGreaterEqual(analytics["total_users"], 0)
        self.assertGreaterEqual(analytics["total_jobs"], 0)

        logs = fetch_audit_logs_sqla(limit=10)
        self.assertIsInstance(logs, list)

    # ==========================================================================
    # 7. PRO MULTI-IDENTIFIER & OTP VERIFICATION TESTS
    # ==========================================================================

    def test_multi_identifier_login_via_email_and_phone(self):
        """Users can sign in with Username, Email, OR Mobile Phone Number."""
        self.candidate_user.phone_number = "+919876543210"
        self.candidate_user.save()

        # 1. Login with Email + 2FA OTP
        resp1 = self.client.post(
            reverse("login"),
            {"username": "student@university.edu", "password": "StudentPass123!"},
            follow=True,
        )
        self.assertEqual(resp1.status_code, 200)
        otp1 = EmailOTP.objects.filter(user=self.candidate_user, purpose=EmailOTP.Purpose.LOGIN, is_used=False).order_by("-created_at").first()
        self.assertIsNotNone(otp1)
        resp1_verify = self.client.post(reverse("unified_login_otp_verify"), {"otp_code": self.get_latest_email_otp()}, follow=True)
        self.assertEqual(resp1_verify.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.candidate_user.pk)
        self.client.logout()

        # 2. Login with Phone Number + 2FA OTP
        resp2 = self.client.post(
            reverse("login"),
            {"username": "+919876543210", "password": "StudentPass123!"},
            follow=True,
        )
        self.assertEqual(resp2.status_code, 200)
        otp2 = EmailOTP.objects.filter(user=self.candidate_user, purpose=EmailOTP.Purpose.LOGIN, is_used=False).order_by("-created_at").first()
        self.assertIsNotNone(otp2)
        resp2_verify = self.client.post(reverse("unified_login_otp_verify"), {"otp_code": self.get_latest_email_otp()}, follow=True)
        self.assertEqual(resp2_verify.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.candidate_user.pk)
        self.client.logout()

    def test_phone_otp_passwordless_login(self):
        """Test passwordless login via 6-digit mobile phone OTP."""
        from accounts.models import PhoneOTP
        self.candidate_user.phone_number = "+919876543210"
        self.candidate_user.save()

        # Step 1: Request Phone OTP
        resp1 = self.client.post(
            reverse("phone_otp_login"),
            {"phone_number": "+919876543210"},
            follow=True,
        )
        self.assertEqual(resp1.status_code, 200)
        otp = PhoneOTP.objects.filter(phone_number="+919876543210", purpose=PhoneOTP.Purpose.LOGIN).first()
        self.assertIsNotNone(otp)
        self.assertEqual(len(otp.otp_code), 6)

        # Step 2: Submit Valid OTP
        resp2 = self.client.post(
            reverse("phone_otp_verify"),
            {"phone_number": "+919876543210", "otp_code": otp.otp_code},
            follow=True,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.candidate_user.pk)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_email_verification_flow(self):
        """User receives and verifies 6-digit Email OTP to earn verified badge."""
        from accounts.models import EmailOTP
        self.client.login(username="test_student", password="StudentPass123!")

        # Step 1: Request Email Verification
        self.client.get(reverse("send_email_verification"), follow=True)
        otp = EmailOTP.objects.filter(email=self.candidate_user.email, purpose=EmailOTP.Purpose.VERIFY).first()
        self.assertIsNotNone(otp)

        # Step 2: Verify OTP
        resp = self.client.post(reverse("verify_email_otp"), {"otp_code": self.get_latest_email_otp()}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.candidate_user.refresh_from_db()
        self.assertTrue(self.candidate_user.is_email_verified)

    def test_forgot_password_otp_reset(self):
        """User resets password using 6-digit OTP and logs in with new password."""
        from accounts.models import EmailOTP
        # Step 1: Forgot password lookup
        resp1 = self.client.post(
            reverse("forgot_password"),
            {"identifier": "student@university.edu", "channel": "email"},
            follow=True,
        )
        self.assertEqual(resp1.status_code, 200)
        otp = EmailOTP.objects.filter(email=self.candidate_user.email, purpose=EmailOTP.Purpose.RESET).first()
        self.assertIsNotNone(otp)
        reset_otp_code = self.get_latest_email_otp()

        # Step 2: Reset password with OTP
        resp2 = self.client.post(
            reverse("reset_password_otp"),
            {
                "otp_code": reset_otp_code,
                "new_password1": "BrandNewArgon2Key99!",
                "new_password2": "BrandNewArgon2Key99!",
            },
            follow=True,
        )
        self.assertEqual(resp2.status_code, 200)

        # Verify user can log in with the new password + 2FA OTP
        resp3 = self.client.post(
            reverse("login"),
            {"username": "test_student", "password": "BrandNewArgon2Key99!"},
            follow=True,
        )
        self.assertEqual(resp3.status_code, 200)
        login_otp_code = self.get_latest_email_otp()
        resp3_verify = self.client.post(reverse("unified_login_otp_verify"), {"otp_code": login_otp_code}, follow=True)
        self.assertEqual(resp3_verify.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.candidate_user.pk)

    def test_roles_hub_view_specification(self):
        """Verify the 4-role login hub matching user's ChatGPT specification."""
        resp = self.client.get(reverse("role_hub"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("OWNER / SUPER ADMIN", content)
        self.assertIn("HR Login", content)
        self.assertIn("Freelancer Login", content)
        self.assertIn("Student / Candidate Login", content)


class EnterpriseEmailAndMobileOTPSecurityTests(TestCase):
    """
    Exhaustive Security & Functional Tests for HireNexa Enterprise OTP Verification:
    1. Valid Email Registration
    2. Invalid Email Registration
    3. Duplicate Email Protection
    4. Valid Indian Mobile (+91)
    5. Invalid Mobile Format
    6. Duplicate Mobile Protection
    7. Real Email Provider Dispatch
    8. Real SMS Provider Dispatch
    9. OTP Hashing (HMAC-SHA256)
    10. Incorrect OTP Handling
    11. OTP Expiration Enforcement
    12. OTP Replay / Reuse Invalidation
    13. OTP Resend 60-Second Cooldown
    14. Attempt Limiting (Max 5 Attempts)
    15. Separate Email & Mobile Statuses
    16. Account Activation Only After Both Verified
    17. Unauthorized Dashboard Access Block
    18. OTP Leakage Prevention in HTML, JSON, and DB
    """

    def setUp(self):
        self.client = Client()
        self.existing_user = User.objects.create_user(
            username="existing_member",
            email="existing@hirenexa.com",
            phone_number="+919876543210",
            password="SecurePassword123!",
            role=User.Role.CANDIDATE,
            is_active=True,
            is_email_verified=True,
            is_phone_verified=True,
        )

    def test_valid_registration_creates_inactive_user_and_otp_challenges(self):
        """Valid registration creates pending account with hashed email and SMS OTP challenges."""
        from accounts.models import OTPChallenge

        response = self.client.post(reverse("signup"), {
            "full_name": "Aarav Patel",
            "username": "aarav_patel",
            "email": "aarav.patel@example.com",
            "country_code": "+91",
            "phone_number": "9812345678",
            "role": User.Role.CANDIDATE,
            "password1": "EnterprisePass123!",
            "password2": "EnterprisePass123!",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        user = User.objects.filter(username="aarav_patel").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, "Aarav")
        self.assertEqual(user.last_name, "Patel")
        self.assertEqual(user.email, "aarav.patel@example.com")
        self.assertEqual(user.phone_number, "+919812345678")
        
        # User MUST be inactive and unverified
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertFalse(user.is_phone_verified)

        # Separate Email and SMS challenges must exist
        email_challenge = OTPChallenge.objects.filter(
            recipient="aarav.patel@example.com", channel=OTPChallenge.Channel.EMAIL
        ).first()
        sms_challenge = OTPChallenge.objects.filter(
            recipient="+919812345678", channel=OTPChallenge.Channel.SMS
        ).first()

        self.assertIsNotNone(email_challenge)
        self.assertIsNotNone(sms_challenge)

        # Raw OTP MUST be hashed with HMAC-SHA256 (64 hex chars)
        self.assertEqual(len(email_challenge.otp_hash), 64)
        self.assertEqual(len(sms_challenge.otp_hash), 64)

        # User is redirected to dual verification gateway
        self.assertContains(response, "Account Verification Required")
        self.assertContains(response, "aarav.patel@example.com")
        self.assertContains(response, "+919812345678")

    def test_invalid_email_registration_rejected(self):
        """Malformed email addresses are rejected with standard validation error."""
        invalid_emails = [
            "notanemail",
            "missingat.com",
            "user@",
            "@domain.com",
            "user@domain",
        ]
        for bad_email in invalid_emails:
            response = self.client.post(reverse("signup"), {
                "full_name": "Test User",
                "username": f"user_{len(bad_email)}",
                "email": bad_email,
                "country_code": "+91",
                "phone_number": "9812345679",
                "role": User.Role.CANDIDATE,
                "password1": "Password123!",
                "password2": "Password123!",
            })
            self.assertContains(response, "Please enter a valid email address.")

    def test_duplicate_email_registration_rejected(self):
        """Duplicate email registration is blocked."""
        response = self.client.post(reverse("signup"), {
            "full_name": "Duplicate Candidate",
            "username": "dup_candidate",
            "email": "existing@hirenexa.com",
            "country_code": "+91",
            "phone_number": "9811122233",
            "role": User.Role.CANDIDATE,
            "password1": "Password123!",
            "password2": "Password123!",
        })
        self.assertContains(response, "This email address is already registered.")

    def test_invalid_mobile_number_rejected(self):
        """Malformed, too-short, or repetitive fake phone numbers are rejected."""
        invalid_phones = [
            "12345",
            "0000000000",
            "1111111111",
            "abcdefghij",
        ]
        for bad_phone in invalid_phones:
            response = self.client.post(reverse("signup"), {
                "full_name": "Invalid Phone",
                "username": f"bad_phone_{bad_phone[:4]}",
                "email": f"bad_{bad_phone[:4]}@example.com",
                "country_code": "+91",
                "phone_number": bad_phone,
                "role": User.Role.CANDIDATE,
                "password1": "Password123!",
                "password2": "Password123!",
            })
            self.assertContains(response, "Please enter a valid mobile number.")

    def test_duplicate_mobile_number_rejected(self):
        """Duplicate mobile numbers (including E.164 and local 10-digit matching) are rejected."""
        response = self.client.post(reverse("signup"), {
            "full_name": "Duplicate Phone",
            "username": "dup_phone_user",
            "email": "dup_phone@example.com",
            "country_code": "+91",
            "phone_number": "9876543210",  # Matches existing +919876543210
            "role": User.Role.CANDIDATE,
            "password1": "Password123!",
            "password2": "Password123!",
        })
        self.assertContains(response, "This mobile number is already registered.")

    def test_owner_role_forbidden_from_public_registration(self):
        """Public signup must never accept OWNER role."""
        response = self.client.post(reverse("signup"), {
            "full_name": "Malicious Owner",
            "username": "fake_owner",
            "email": "fakeowner@example.com",
            "country_code": "+91",
            "phone_number": "9845678901",
            "role": "OWNER",
            "password1": "Password123!",
            "password2": "Password123!",
        })
        self.assertFalse(User.objects.filter(username="fake_owner").exists())

    def test_incorrect_otp_decrements_attempts(self):
        """Entering incorrect OTP code decrements attempts_left."""
        from accounts.models import OTPChallenge
        from accounts.services.otp_service import OTPService

        challenge, raw_otp = OTPChallenge.create_challenge("test.otp@example.com", OTPChallenge.Channel.EMAIL)
        
        # Submit wrong code
        res = OTPService.verify_challenge("test.otp@example.com", OTPChallenge.Channel.EMAIL, "000000")
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "INVALID")
        self.assertIn("Invalid OTP", res["message"])
        
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts_left, 4)

    def test_too_many_attempts_locks_challenge(self):
        """Exceeding 5 failed attempts locks challenge."""
        from accounts.models import OTPChallenge
        from accounts.services.otp_service import OTPService

        challenge, raw_otp = OTPChallenge.create_challenge("lockout@example.com", OTPChallenge.Channel.EMAIL)
        for _ in range(5):
            res = OTPService.verify_challenge("lockout@example.com", OTPChallenge.Channel.EMAIL, "111111")
        
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "MAX_ATTEMPTS")
        self.assertIn("Too many attempts", res["message"])
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts_left, 0)

    def test_expired_otp_rejected(self):
        """Expired OTP cannot be verified."""
        from datetime import timedelta
        from django.utils import timezone
        from accounts.models import OTPChallenge
        from accounts.services.otp_service import OTPService

        challenge, raw_otp = OTPChallenge.create_challenge("expired@example.com", OTPChallenge.Channel.EMAIL)
        # Force expiration to 20 minutes in past
        challenge.expires_at = timezone.now() - timedelta(minutes=20)
        challenge.save()

        res = OTPService.verify_challenge("expired@example.com", OTPChallenge.Channel.EMAIL, raw_otp)
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "EXPIRED")
        self.assertIn("OTP has expired", res["message"])

    def test_reused_otp_rejected(self):
        """Once successfully used, an OTP cannot be verified again."""
        from accounts.models import OTPChallenge
        from accounts.services.otp_service import OTPService

        challenge, raw_otp = OTPChallenge.create_challenge("reuse@example.com", OTPChallenge.Channel.EMAIL)
        
        # First verification succeeds
        res1 = OTPService.verify_challenge("reuse@example.com", OTPChallenge.Channel.EMAIL, raw_otp)
        self.assertTrue(res1["success"])

        # Second verification fails
        res2 = OTPService.verify_challenge("reuse@example.com", OTPChallenge.Channel.EMAIL, raw_otp)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["error_code"], "REUSED")

    def test_otp_resend_cooldown_60_seconds(self):
        """Requesting OTP resend within 60 seconds is blocked by cooldown."""
        from accounts.models import OTPChallenge
        from accounts.services.otp_service import OTPService

        # Issue 1st challenge
        res1 = OTPService.issue_challenge("cooldown@example.com", OTPChallenge.Channel.EMAIL)
        self.assertTrue(res1["success"])

        # Issue 2nd challenge immediately
        res2 = OTPService.issue_challenge("cooldown@example.com", OTPChallenge.Channel.EMAIL)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["error_code"], "COOLDOWN_ACTIVE")
        self.assertIn("seconds before requesting a new code", res2["message"])

    def test_or_logic_email_otp_alone_activates_and_logs_in_user(self):
        """OR-Logic: Verifying Email OTP alone activates account, logs in user, and leaves mobile optional."""
        from accounts.models import OTPChallenge

        user = User.objects.create_user(
            username="email_only_user",
            email="emailonly@example.com",
            phone_number="+919811223344",
            password="Password123!",
            role=User.Role.CANDIDATE,
            is_active=False,
            is_email_verified=False,
            is_phone_verified=False,
        )
        session = self.client.session
        session["pending_verification_user_id"] = user.id
        session.save()

        c_email, email_code = OTPChallenge.create_challenge(user.email, OTPChallenge.Channel.EMAIL, user=user)

        resp = self.client.post(reverse("dual_verification"), {
            "action": "verify_email",
            "email_otp": email_code,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)

        user.refresh_from_db()
        # Email verified, phone unverified, but account MUST be active under OR logic
        self.assertTrue(user.is_email_verified)
        self.assertFalse(user.is_phone_verified)
        self.assertTrue(user.is_active)
        self.assertRedirects(resp, reverse("candidate_dashboard"))
        # User is authenticated
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_or_logic_mobile_otp_alone_activates_and_logs_in_user(self):
        """OR-Logic: Verifying Mobile SMS OTP alone activates account, logs in user, and leaves email optional."""
        from accounts.models import OTPChallenge

        user = User.objects.create_user(
            username="phone_only_user",
            email="phoneonly@example.com",
            phone_number="+919822334455",
            password="Password123!",
            role=User.Role.CANDIDATE,
            is_active=False,
            is_email_verified=False,
            is_phone_verified=False,
        )
        session = self.client.session
        session["pending_verification_user_id"] = user.id
        session.save()

        c_sms, sms_code = OTPChallenge.create_challenge(user.phone_number, OTPChallenge.Channel.SMS, user=user)

        resp = self.client.post(reverse("dual_verification"), {
            "action": "verify_phone",
            "phone_otp": sms_code,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)

        user.refresh_from_db()
        # Phone verified, email unverified, but account MUST be active under OR logic
        self.assertFalse(user.is_email_verified)
        self.assertTrue(user.is_phone_verified)
        self.assertTrue(user.is_active)
        self.assertRedirects(resp, reverse("candidate_dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_honest_send_failure_reporting(self):
        """When email or SMS dispatch fails, issue_challenge returns success=False honestly."""
        from unittest.mock import patch
        from accounts.services.otp_service import OTPService
        from accounts.models import OTPChallenge

        # Mock EmailDeliveryService to simulate failure
        with patch("accounts.services.delivery.EmailDeliveryService.send_otp_email") as mock_email:
            mock_email.return_value = {
                "success": False,
                "status": "FAILED",
                "provider": "SMTP (smtp.gmail.com)",
                "error": "Authentication failed",
                "error_code": "SMTP_AUTH_FAILED",
            }
            res = OTPService.issue_challenge("failtest@example.com", OTPChallenge.Channel.EMAIL)
            self.assertFalse(res["success"])
            self.assertEqual(res["error_code"], "SMTP_AUTH_FAILED")
            self.assertIn("Authentication failed", res["message"])

    def test_sms_provider_mock_in_debug(self):
        """Mock SMS provider in DEBUG prints OTP and returns success=True."""
        from accounts.services.sms_provider import MockSMSProvider

        provider = MockSMSProvider()
        res = provider.send_otp("+919876543210", "123456", validity_minutes=10)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "DELIVERED")
        self.assertIn("Mock", res["provider"])

    def test_resend_api_reports_failure_honestly(self):
        """AJAX resend endpoint returns status 400 and error when dispatch fails."""
        from unittest.mock import patch
        from accounts.models import OTPChallenge

        user = User.objects.create_user(
            username="resend_fail_user",
            email="resendfail@example.com",
            phone_number="+919833445566",
            password="Password123!",
            is_active=False,
        )
        session = self.client.session
        session["pending_verification_user_id"] = user.id
        session.save()

        with patch("accounts.services.delivery.EmailDeliveryService.send_otp_email") as mock_email:
            mock_email.return_value = {
                "success": False,
                "status": "FAILED",
                "provider": "SMTP (smtp.gmail.com)",
                "error": "Connection timed out",
                "error_code": "TIMEOUT",
            }
            resp = self.client.post(
                reverse("resend_otp_api", kwargs={"channel": "email"}),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(resp.status_code, 400)
            data = resp.json()
            self.assertFalse(data["success"])
            self.assertIn("Connection timed out", data["message"])

    def test_unverified_user_cannot_access_protected_dashboard(self):
        """Unverified/inactive user is barred from authenticated candidate dashboard."""
        unverified_user = User.objects.create_user(
            username="unverified_locked",
            email="locked@example.com",
            password="Password123!",
            is_active=False,
            role=User.Role.CANDIDATE,
        )
        self.client.login(username="unverified_locked", password="Password123!")
        response = self.client.get(reverse("candidate_dashboard"))
        # Must be redirected to login or verification
        self.assertNotEqual(response.status_code, 200)

    def test_otp_never_leaked_in_html_or_database(self):
        """Verify raw OTP is never rendered in UI or persisted unhashed in database."""
        from accounts.models import OTPChallenge

        challenge, raw_code = OTPChallenge.create_challenge("security.audit@example.com", OTPChallenge.Channel.EMAIL)
        
        # Check database record
        self.assertNotEqual(challenge.otp_hash, raw_code)
        self.assertNotIn(raw_code, challenge.otp_hash)

        # Check frontend rendering
        session = self.client.session
        session["pending_verification_user_id"] = self.existing_user.id
        session.save()

        response = self.client.get(reverse("dual_verification"))
        html_content = response.content.decode("utf-8")
        self.assertNotIn(raw_code, html_content)


class AuthenticationRateLimitingAndVanitySecurityTests(TestCase):
    """
    Test suite verifying Phase 2 Authentication & Security hardening:
    - SEC-03: Brute force login rate limiting (HTTP 429 lockout after 5 failed attempts)
    - Successful login resets failed attempt counters
    - Vanity login route isolation and role guards
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = Client()
        self.test_user = User.objects.create_user(
            username="sec_target_user",
            email="target@example.com",
            password="CorrectPassword123!",
            role=User.Role.CANDIDATE,
            is_active=True,
        )

    def test_brute_force_rate_limiting_triggers_429(self):
        """Five failed login attempts trigger HTTP 429 rate limit block."""
        from django.core.cache import cache
        cache.clear()

        # Send 5 failed login attempts
        for i in range(5):
            resp = self.client.post(reverse("login"), {
                "identifier": "sec_target_user",
                "password": "WrongPassword!",
            })
            self.assertEqual(resp.status_code, 200)

        # 6th attempt MUST be blocked with HTTP 429
        blocked_resp = self.client.post(reverse("login"), {
            "identifier": "sec_target_user",
            "password": "WrongPassword!",
        })
        self.assertEqual(blocked_resp.status_code, 429)

        # AuditLog must record rate limit event
        self.assertTrue(
            AuditLog.objects.filter(action="LOGIN_RATE_LIMIT_EXCEEDED").exists()
        )

    def test_successful_login_resets_rate_limiter(self):
        """A successful authentication resets failed attempt counters."""
        from django.core.cache import cache
        cache.clear()

        # 2 failed attempts
        for _ in range(2):
            self.client.post(reverse("login"), {
                "identifier": "sec_target_user",
                "password": "WrongPassword!",
            })

        # Successful login
        success_resp = self.client.post(reverse("login"), {
            "identifier": "sec_target_user",
            "password": "CorrectPassword123!",
        })
        self.assertEqual(success_resp.status_code, 302)

        # Log out so client is anonymous again
        self.client.logout()

        # Counter should be reset: immediate failed attempts do not block (status 200, not 429)
        failed_resp = self.client.post(reverse("login"), {
            "identifier": "sec_target_user",
            "password": "WrongPassword!",
        })
        self.assertEqual(failed_resp.status_code, 200)

    def test_vanity_routes_render_and_protect_roles(self):
        """Vanity login routes load proper templates and enforce role boundaries."""
        vanity_urls = [
            "/owner/login/",
            "/company/login/",
            "/hr/login/",
            "/candidate/login/",
            "/student/login/",
            "/freelancer/login/",
            "/roles/",
        ]
        for url in vanity_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"Vanity URL {url} failed to load.")


class EmailOTPSecurityTests(TestCase):
    """
    Comprehensive enterprise security tests for EmailOTP:
    - Cryptographic generation (secrets.randbelow)
    - Zero plaintext OTP in database (Argon2 / Django make_password hash)
    - Constant-time verification & single-use enforcement
    - 5-attempt lockout
    - Expiration handling
    - 60s cooldown & 5/hour rate limiting
    - Masked email privacy protection
    - Zero OTP leakage in responses
    """

    def setUp(self):
        self.email = "security_test_user@example.com"
        self.user = User.objects.create_user(
            username="otp_sec_user",
            email=self.email,
            password="StrongPassword123!",
            role=User.Role.CANDIDATE,
        )

    def test_email_otp_crypto_generation_and_zero_plaintext(self):
        """OTP is 6-digit numeric, hash is persisted, and plaintext otp_code is strictly empty."""
        record, raw_code = EmailOTP.generate(self.email, purpose=EmailOTP.Purpose.LOGIN, user=self.user)

        self.assertEqual(len(raw_code), 6)
        self.assertTrue(raw_code.isdigit())
        self.assertGreaterEqual(int(raw_code), 100000)
        self.assertLessEqual(int(raw_code), 999999)

        # Re-fetch from database to ensure persistence
        db_record = EmailOTP.objects.get(pk=record.pk)
        self.assertEqual(db_record.otp_code, "", "Database must NOT store plaintext OTP code.")
        self.assertTrue(db_record.otp_hash.startswith("argon2") or db_record.otp_hash.startswith("pbkdf2"))
        self.assertTrue(check_password(raw_code, db_record.otp_hash))

    def test_check_code_success_and_reuse_prevention(self):
        """Valid code succeeds once; subsequent verification attempts are rejected (anti-replay)."""
        record, raw_code = EmailOTP.generate(self.email, purpose=EmailOTP.Purpose.LOGIN)

        is_valid, reason = record.check_code(raw_code)
        self.assertTrue(is_valid)
        self.assertEqual(reason, "SUCCESS")
        self.assertTrue(record.is_used)

        # Second attempt with the exact same code must fail
        is_valid2, reason2 = record.check_code(raw_code)
        self.assertFalse(is_valid2)
        self.assertEqual(reason2, "ALREADY_USED")

    def test_check_code_max_attempts_lockout(self):
        """5 incorrect OTP attempts locks the OTP record permanently."""
        record, raw_code = EmailOTP.generate(self.email, purpose=EmailOTP.Purpose.LOGIN)

        # 4 wrong attempts
        for i in range(1, 5):
            is_valid, reason = record.check_code("000000")
            self.assertFalse(is_valid)
            self.assertEqual(reason, "INVALID")
            self.assertEqual(record.attempts, i)
            self.assertFalse(record.is_used)

        # 5th wrong attempt triggers lockout
        is_valid, reason = record.check_code("000000")
        self.assertFalse(is_valid)
        self.assertEqual(reason, "LOCKED")
        self.assertEqual(record.attempts, 5)
        self.assertTrue(record.is_used)

        # Even correct code cannot unlock
        is_valid, reason = record.check_code(raw_code)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "ALREADY_USED")

    def test_expired_otp_rejected(self):
        """Expired OTPs cannot be verified."""
        record, raw_code = EmailOTP.generate(self.email, purpose=EmailOTP.Purpose.VERIFY, validity_minutes=-5)
        is_valid, reason = record.check_code(raw_code)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "EXPIRED")

    def test_invalidation_of_previous_unused_otps(self):
        """Generating a new OTP invalidates all prior unused OTPs for the same email and purpose."""
        record1, code1 = EmailOTP.generate(self.email, purpose=EmailOTP.Purpose.VERIFY)
        self.assertFalse(record1.is_used)

        record2, code2 = EmailOTP.generate(self.email, purpose=EmailOTP.Purpose.VERIFY)
        record1.refresh_from_db()
        self.assertTrue(record1.is_used, "Older unused OTP must be invalidated.")
        self.assertFalse(record2.is_used)

    def test_rate_limiting_cooldown(self):
        """Requests within 60s cooldown are blocked."""
        record, code = EmailOTP.generate(self.email, purpose=EmailOTP.Purpose.OWNER_SETUP)

        can_request, err, wait_sec = EmailOTP.can_request_otp(
            email=self.email,
            purpose=EmailOTP.Purpose.OWNER_SETUP,
            cooldown_seconds=60,
        )
        self.assertFalse(can_request)
        self.assertIn("Please wait", err)
        self.assertGreater(wait_sec, 0)

    def test_rate_limiting_max_per_hour(self):
        """More than 5 requests per hour are blocked."""
        now = timezone.now()
        # Create 5 records spaced across the past 30 minutes
        for i in range(5):
            EmailOTP.objects.create(
                email=self.email.lower(),
                otp_hash=make_password("111111"),
                purpose=EmailOTP.Purpose.LOGIN,
                expires_at=now + timedelta(minutes=15),
                is_used=True,
            )

        can_request, err, wait_sec = EmailOTP.can_request_otp(
            email=self.email,
            purpose=EmailOTP.Purpose.LOGIN,
            max_per_hour=5,
        )
        self.assertFalse(can_request)
        self.assertIn("Rate limit reached", err)

    def test_mask_email_utility(self):
        """Email address is masked for security and privacy."""
        self.assertEqual(mask_email("bhabani@gmail.com"), "b***@gmail.com")
        self.assertEqual(mask_email("ilovemymaaandpababhabanishanka@gmail.com"), "i***@gmail.com")
        self.assertEqual(mask_email("ab@company.org"), "a***@company.org")
        self.assertEqual(mask_email("notanemail"), "your email")

    def test_owner_setup_verify_page_zero_otp_leak(self):
        """Owner verify page displays masked email, never leaks raw OTP in HTML or session."""
        session = self.client.session
        session["pending_owner_setup"] = {
            "full_name": "Test Owner",
            "username": "super_owner_test",
            "email": "secureowner@example.com",
            "phone_number": "+1234567890",
            "password_hash": make_password("SuperMasterPassword123!"),
        }
        session.save()

        record, raw_code = EmailOTP.generate("secureowner@example.com", purpose=EmailOTP.Purpose.OWNER_SETUP)

        response = self.client.get(reverse("first_time_owner_setup_verify"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        # Masked email must be present
        self.assertIn("s***@example.com", content)
        # Raw email must not be exposed in user text
        self.assertNotIn("secureowner@example.com", content)
        # Raw OTP must never appear anywhere in the rendered page
        self.assertNotIn(raw_code, content)

    def test_send_otp_email_locmem_delivery(self):
        """send_otp_email sends correct multi-alternative email via Django test backend."""
        mail.outbox.clear()
        res = send_otp_email("testrecipient@gmail.com", "748291", purpose="OWNER_SETUP", expiry_minutes=15)
        self.assertTrue(res.success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["testrecipient@gmail.com"])
        self.assertEqual(mail.outbox[0].subject, "Your HireNexa verification code")
        self.assertIn("748291", mail.outbox[0].body)
        self.assertIn("15 minutes", mail.outbox[0].body)
        self.assertIn("Never share this code", mail.outbox[0].body)

    @patch("django.core.mail.EmailMultiAlternatives.send")
    def test_send_otp_email_smtp_auth_failure_handling(self, mock_send):
        """Catches SMTPAuthenticationError (535) and returns structured error without crashing."""
        mock_send.side_effect = smtplib.SMTPAuthenticationError(535, b"Invalid credentials")
        res = send_otp_email("testrecipient@gmail.com", "748291")
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "SMTP_AUTH_FAILED")
        self.assertIn("Gmail App Password", res.error_message)

    @patch("django.core.mail.EmailMultiAlternatives.send")
    def test_send_otp_email_connection_timeout_handling(self, mock_send):
        """Catches socket.timeout and returns TIMEOUT error without crashing."""
        mock_send.side_effect = socket.timeout("Timed out")
        res = send_otp_email("testrecipient@gmail.com", "748291")
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "TIMEOUT")

    @patch("accounts.services.email_service.send_otp_email")
    def test_view_failure_invalidates_otp_and_no_success_flash(self, mock_send_otp):
        """When email fails to send, view invalidates OTP record and shows friendly failure message."""
        mock_send_otp.return_value = EmailSendResult(
            success=False,
            error_code="SMTP_AUTH_FAILED",
            error_message="SMTP Authentication failed",
        )
        # Ensure 0 owners exist so setup view is accessible
        User.objects.filter(role=User.Role.OWNER).delete()

        resp = self.client.post(reverse("first_time_owner_setup"), {
            "full_name": "Test Owner",
            "username": "new_sec_owner",
            "email": "owner_fail@example.com",
            "phone_number": "+919876543210",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
        })
        self.assertEqual(resp.status_code, 200)

        # Check friendly error message
        content = resp.content.decode("utf-8")
        self.assertIn("Unable to send verification email at this time. Please try again shortly.", content)
        self.assertNotIn("We sent a 6-digit code", content)

        # OTP record must exist and must be marked is_used=True (invalidated)
        otp = EmailOTP.objects.filter(email="owner_fail@example.com", purpose=EmailOTP.Purpose.OWNER_SETUP).first()
        self.assertIsNotNone(otp)
        self.assertTrue(otp.is_used, "Failed dispatch must invalidate OTP record.")

    def test_view_success_displays_masked_email_and_no_raw_otp(self):
        """When email succeeds, view displays masked email and does not leak raw OTP."""
        mail.outbox.clear()
        User.objects.filter(role=User.Role.OWNER).delete()

        resp = self.client.post(reverse("first_time_owner_setup"), {
            "full_name": "Test Owner",
            "username": "new_good_owner",
            "email": "owner_good@example.com",
            "phone_number": "+919876543210",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
        }, follow=True)
        self.assertEqual(resp.status_code, 200)

        content = resp.content.decode("utf-8")
        self.assertIn("We sent a 6-digit code to o***@example.com", content)

        # Verify raw OTP was dispatched in mail.outbox
        self.assertEqual(len(mail.outbox), 1)
        raw_code = mail.outbox[0].body.split("verification code is: ")[1][:6]
        # Raw OTP must never appear in the HTML
        self.assertNotIn(raw_code, content)


from django.core.management import call_command
from io import StringIO
from accounts.services.rate_limiter import RateLimiter


class CandidateLoginFlowAndSecurityHardeningTests(TestCase):
    """
    Comprehensive Security & Flow Verification for Student / Candidate Login:
    1. Register -> OTP verify -> Login succeeds (username, email, phone)
    2. Wrong password increments counter
    3. Lockout triggers at limit (HTTP 429)
    4. Lockout is per-portal (failures on owner portal do not lock candidate portal)
    5. Success resets counter
    6. Unverified account gets clear verification message with resend link and does not count as brute force
    7. Management command reset_login_lockout clears lockouts safely
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = Client()
        self.raw_password = "CandidatePass123!"
        self.student = User.objects.create_user(
            username="test_candidate_user",
            email="candidate.flow@example.com",
            phone_number="+919876543299",
            password=self.raw_password,
            role=User.Role.CANDIDATE,
            is_active=True,
            is_email_verified=True,
            is_phone_verified=True,
        )

    def test_candidate_login_success_across_all_identifiers(self):
        """Candidate can log in via Username, Email, or Mobile Phone."""
        identifiers = [
            self.student.username,
            self.student.email,
            self.student.phone_number,
            "9876543299",  # Local 10-digit format without +91
        ]
        for ident in identifiers:
            self.client.logout()
            resp = self.client.post(reverse("candidate_login"), {
                "username": ident,
                "password": self.raw_password,
            }, follow=False)
            self.assertEqual(resp.status_code, 302, f"Failed for identifier: {ident}")
            self.assertEqual(int(self.client.session["_auth_user_id"]), self.student.id)

    def test_wrong_password_increments_rate_limiter_counter(self):
        """Submitting wrong password records failed attempts and displays friendly error."""
        from django.core.cache import cache
        cache.clear()

        resp = self.client.post(reverse("candidate_login"), {
            "username": self.student.username,
            "password": "WrongPassword999!",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid student credentials")

        # Verify rate limiter recorded 1 attempt on candidate portal
        key = RateLimiter._key("candidate", "127.0.0.1", self.student.username)
        data = cache.get(key)
        self.assertIsNotNone(data)
        self.assertEqual(data[0], 1)

    def test_lockout_triggers_at_limit_with_429(self):
        """Reaching max failed attempts triggers HTTP 429 lockout."""
        from django.core.cache import cache
        cache.clear()

        # Send 5 failed attempts
        for _ in range(5):
            resp = self.client.post(reverse("candidate_login"), {
                "username": self.student.username,
                "password": "WrongPassword999!",
            })
            self.assertEqual(resp.status_code, 200)

        # 6th attempt must return 429
        blocked_resp = self.client.post(reverse("candidate_login"), {
            "username": self.student.username,
            "password": "WrongPassword999!",
        })
        self.assertEqual(blocked_resp.status_code, 429)
        self.assertContains(blocked_resp, "Too many failed login attempts", status_code=429)

    def test_lockout_is_isolated_per_portal(self):
        """Failed attempts on Owner portal do not lock out Candidate portal."""
        from django.core.cache import cache
        cache.clear()

        # Fail 5 times on Owner portal
        for _ in range(5):
            self.client.post(reverse("owner_login"), {
                "username": self.student.username,
                "password": "WrongPassword!",
            })

        # Owner portal is now locked out
        owner_blocked = self.client.post(reverse("owner_login"), {
            "username": self.student.username,
            "password": "WrongPassword!",
        })
        self.assertEqual(owner_blocked.status_code, 429)

        # Candidate portal MUST NOT be locked out!
        candidate_resp = self.client.post(reverse("candidate_login"), {
            "username": self.student.username,
            "password": self.raw_password,
        })
        self.assertEqual(candidate_resp.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.student.id)

    def test_successful_login_resets_rate_limiter_counter(self):
        """Successful authentication resets failed attempt counter on the portal."""
        from django.core.cache import cache
        cache.clear()

        # 2 failed attempts
        for _ in range(2):
            self.client.post(reverse("candidate_login"), {
                "username": self.student.username,
                "password": "WrongPassword!",
            })

        key = RateLimiter._key("candidate", "127.0.0.1", self.student.username)
        self.assertEqual(cache.get(key)[0], 2)

        # Successful login
        success_resp = self.client.post(reverse("candidate_login"), {
            "username": self.student.username,
            "password": self.raw_password,
        })
        self.assertEqual(success_resp.status_code, 302)

        # Key must now be deleted
        self.assertIsNone(cache.get(key))

    def test_unverified_account_shows_correct_message_and_does_not_increment_counter(self):
        """Fresh unverified user gets verification notice with link and counter is NOT incremented."""
        from django.core.cache import cache
        cache.clear()

        unverified_user = User.objects.create_user(
            username="unverified_student",
            email="unverified@example.com",
            phone_number="+919876543288",
            password="CorrectPass123!",
            role=User.Role.CANDIDATE,
            is_active=False,
            is_email_verified=False,
            is_phone_verified=False,
        )

        resp = self.client.post(reverse("candidate_login"), {
            "username": "unverified_student",
            "password": "CorrectPass123!",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Your account has been registered but is not yet verified")
        self.assertContains(resp, reverse("dual_verification"))

        # Session pending_verification_user_id must be set
        self.assertEqual(self.client.session.get("pending_verification_user_id"), unverified_user.id)

        # Crucial security check: brute force counter must NOT have been incremented
        key = RateLimiter._key("candidate", "127.0.0.1", "unverified_student")
        self.assertIsNone(cache.get(key))

    def test_reset_login_lockout_management_command(self):
        """Management command reset_login_lockout clears locked account."""
        from django.core.cache import cache
        cache.clear()

        # Lock out user
        for _ in range(5):
            self.client.post(reverse("candidate_login"), {
                "username": self.student.username,
                "password": "WrongPassword!",
            })

        # Confirm locked out
        self.assertEqual(
            self.client.post(reverse("candidate_login"), {
                "username": self.student.username,
                "password": "WrongPassword!",
            }).status_code,
            429
        )

        # Execute management command
        out = StringIO()
        call_command("reset_login_lockout", identifier=self.student.username, stdout=out)
        self.assertIn("Successfully cleared login lockout", out.getvalue())

        # Attempt should now not be blocked with 429
        after_resp = self.client.post(reverse("candidate_login"), {
            "username": self.student.username,
            "password": "WrongPassword!",
        })
        self.assertEqual(after_resp.status_code, 200)

    def test_full_registration_to_login_flow(self):
        """Register candidate -> verify OTP -> login succeeds."""
        from accounts.models import OTPChallenge
        from django.core.cache import cache
        cache.clear()

        # 1. Register candidate
        signup_data = {
            "full_name": "Aniket Sen",
            "username": "aniket_sen",
            "email": "aniket.sen@college.edu",
            "country_code": "+91",
            "phone_number": "9812345679",
            "password1": "SecurePass1234!",
            "password2": "SecurePass1234!",
        }
        reg_resp = self.client.post(reverse("candidate_signup"), signup_data)
        self.assertRedirects(reg_resp, reverse("dual_verification"))

        new_user = User.objects.get(username="aniket_sen")
        self.assertFalse(new_user.is_active)

        # 2. Verify via email OTP
        from accounts.services.otp_service import OTPService
        c, code = OTPChallenge.create_challenge(new_user.email, OTPChallenge.Channel.EMAIL, user=new_user)
        v_resp = self.client.post(reverse("dual_verification"), {
            "action": "verify_email",
            "email_otp": code,
        })
        new_user.refresh_from_db()
        self.assertTrue(new_user.is_active)

        # Log out from verification auto-login
        self.client.logout()

        # 3. Log in at candidate login
        login_resp = self.client.post(reverse("candidate_login"), {
            "username": "aniket.sen@college.edu",
            "password": "SecurePass1234!",
        })
        self.assertEqual(login_resp.status_code, 302)
        self.assertRedirects(login_resp, reverse("candidate_dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), new_user.id)


class ProductionOTPLoginSystemTests(TestCase):
    """
    Production-Grade OTP Login System Verification:
    - HMAC-SHA256 salted hashing and cryptographic generation.
    - Correct OTP login & role portal redirection.
    - Failed attempt counters & lockout.
    - Expiration & single-use consumption.
    - Resend cooldown (60s) & hourly limits (5/hr).
    - Portal role boundaries (Candidate cannot login to HR).
    - Anti-enumeration protection.
    - Automatic activation of unverified accounts.
    - Pluggable SMS and Email mock backends.
    """

    def setUp(self):
        self.client = Client()
        from django.core.cache import cache
        cache.clear()

        # Candidate user
        self.candidate_user = User.objects.create_user(
            username="student_riya",
            email="riya.student@hirenexa.com",
            phone_number="+919876543211",
            role=User.Role.CANDIDATE,
            password="StudentPass123!",
            is_active=True,
            is_email_verified=True,
            is_phone_verified=True,
        )
        CandidateProfile.objects.get_or_create(user=self.candidate_user)

        # HR Recruiter user
        self.hr_user = User.objects.create_user(
            username="recruiter_vikram",
            email="vikram.hr@techcorp.io",
            phone_number="+919876543222",
            role=User.Role.RECRUITER,
            password="RecruiterPass123!",
            is_active=True,
            is_email_verified=True,
            is_phone_verified=True,
        )
        RecruiterProfile.objects.get_or_create(user=self.hr_user)

    def test_otp_generation_and_hmac_hashing(self):
        """Verify OTP generation uses secrets module and stores HMAC-SHA256 hash (never plaintext)."""
        from accounts.services.otp_service import OTPService
        from accounts.models import OTPChallenge

        result = OTPService.issue_challenge(
            recipient=self.candidate_user.email,
            channel=OTPChallenge.Channel.EMAIL,
            purpose=OTPChallenge.Purpose.LOGIN,
            user=self.candidate_user,
            portal="candidate",
        )
        self.assertTrue(result["success"])
        otp_code = result["otp"]
        self.assertEqual(len(otp_code), 6)
        self.assertTrue(otp_code.isdigit())

        challenge = OTPChallenge.objects.filter(
            identifier=self.candidate_user.email.lower(),
            channel=OTPChallenge.Channel.EMAIL,
            is_used=False,
        ).latest("created_at")

        # Verify plaintext OTP is NOT in database
        self.assertNotEqual(challenge.otp_hash, otp_code)
        self.assertNotIn(otp_code, challenge.otp_hash)

        # Verify constant-time comparison
        self.assertTrue(challenge.check_otp(otp_code))
        self.assertFalse(challenge.check_otp("000000"))

    def test_correct_otp_logs_in(self):
        """Verify correct OTP logs in candidate and redirects to candidate dashboard."""
        from accounts.services.otp_service import OTPService
        from accounts.models import OTPChallenge

        # Request OTP
        req_resp = self.client.post(reverse("request_otp"), {
            "identifier": self.candidate_user.email,
            "channel": "EMAIL",
            "portal": "candidate",
        })
        self.assertRedirects(req_resp, reverse("verify_otp"))

        # Re-generate or simulate known code
        c_obj, plain_otp = OTPChallenge.create_challenge(
            self.candidate_user.email,
            OTPChallenge.Channel.EMAIL,
            user=self.candidate_user,
            purpose=OTPChallenge.Purpose.LOGIN,
            portal="candidate",
        )

        verify_resp = self.client.post(reverse("verify_otp"), {
            "identifier": self.candidate_user.email,
            "channel": "EMAIL",
            "portal": "candidate",
            "otp_code": plain_otp,
        })
        self.assertEqual(verify_resp.status_code, 302)
        self.assertRedirects(verify_resp, reverse("candidate_dashboard"))

        # Verify user authenticated in session
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.candidate_user.id)

        # Verify challenge marked consumed
        c_obj.refresh_from_db()
        self.assertTrue(c_obj.is_used)
        self.assertIsNotNone(c_obj.consumed_at)

    def test_wrong_otp_increments_attempts(self):
        """Verify wrong OTP code increments attempts and rejects verification."""
        from accounts.models import OTPChallenge

        c_obj, plain_otp = OTPChallenge.create_challenge(
            self.candidate_user.email,
            OTPChallenge.Channel.EMAIL,
            user=self.candidate_user,
            purpose=OTPChallenge.Purpose.LOGIN,
            portal="candidate",
        )

        # Submit incorrect OTP
        resp = self.client.post(reverse("verify_otp"), {
            "identifier": self.candidate_user.email,
            "channel": "EMAIL",
            "portal": "candidate",
            "otp_code": "999999",
        })
        self.assertEqual(resp.status_code, 400)
        c_obj.refresh_from_db()
        self.assertEqual(c_obj.attempts, 1)
        self.assertFalse(c_obj.is_used)

    def test_expired_otp_rejected(self):
        """Verify expired challenge (>5 minutes) is rejected."""
        from accounts.models import OTPChallenge

        c_obj, plain_otp = OTPChallenge.create_challenge(
            self.candidate_user.email,
            OTPChallenge.Channel.EMAIL,
            user=self.candidate_user,
            purpose=OTPChallenge.Purpose.LOGIN,
            portal="candidate",
            validity_minutes=5,
        )
        # Fast-forward expiry into past
        c_obj.expires_at = timezone.now() - timedelta(minutes=1)
        c_obj.save(update_fields=["expires_at"])

        resp = self.client.post(reverse("verify_otp"), {
            "identifier": self.candidate_user.email,
            "channel": "EMAIL",
            "portal": "candidate",
            "otp_code": plain_otp,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_otp_reuse_rejected(self):
        """Verify single-use consumption: already used OTP cannot be reused."""
        from accounts.models import OTPChallenge

        c_obj, plain_otp = OTPChallenge.create_challenge(
            self.candidate_user.email,
            OTPChallenge.Channel.EMAIL,
            user=self.candidate_user,
            purpose=OTPChallenge.Purpose.LOGIN,
            portal="candidate",
        )

        # First verification succeeds
        resp1 = self.client.post(reverse("verify_otp"), {
            "identifier": self.candidate_user.email,
            "channel": "EMAIL",
            "portal": "candidate",
            "otp_code": plain_otp,
        })
        self.assertEqual(resp1.status_code, 302)
        self.client.logout()

        # Second verification with same code fails
        resp2 = self.client.post(reverse("verify_otp"), {
            "identifier": self.candidate_user.email,
            "channel": "EMAIL",
            "portal": "candidate",
            "otp_code": plain_otp,
        })
        self.assertEqual(resp2.status_code, 400)

    def test_resend_cooldown_enforced(self):
        """Verify 60s cooldown between consecutive OTP requests for the same identifier."""
        from accounts.services.otp_service import OTPService
        from accounts.models import OTPChallenge

        res1 = OTPService.issue_challenge(
            recipient=self.candidate_user.email,
            channel=OTPChallenge.Channel.EMAIL,
            purpose=OTPChallenge.Purpose.LOGIN,
            user=self.candidate_user,
        )
        self.assertTrue(res1["success"])

        # Second request immediately within cooldown period
        res2 = OTPService.issue_challenge(
            recipient=self.candidate_user.email,
            channel=OTPChallenge.Channel.EMAIL,
            purpose=OTPChallenge.Purpose.LOGIN,
            user=self.candidate_user,
        )
        self.assertFalse(res2["success"])
        self.assertEqual(res2["error_code"], "COOLDOWN_ACTIVE")
        self.assertGreater(res2["cooldown"], 0)

    def test_hourly_limit_enforced(self):
        """Verify maximum 5 OTP sends per hour per identifier."""
        from accounts.services.otp_service import OTPService
        from accounts.models import OTPChallenge

        # Create 5 challenges over the past 30 minutes
        for i in range(5):
            c = OTPChallenge.objects.create(
                identifier="hourly_limit_test@hirenexa.com",
                recipient="hourly_limit_test@hirenexa.com",
                channel=OTPChallenge.Channel.EMAIL,
                purpose=OTPChallenge.Purpose.LOGIN,
                otp_hash="mock_hash",
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            OTPChallenge.objects.filter(id=c.id).update(
                created_at=timezone.now() - timedelta(minutes=5 * (i + 1)),
            )

        res = OTPService.issue_challenge(
            recipient="hourly_limit_test@hirenexa.com",
            channel=OTPChallenge.Channel.EMAIL,
            purpose=OTPChallenge.Purpose.LOGIN,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "RATE_LIMIT_EXCEEDED")

    def test_wrong_portal_role_rejected(self):
        """Verify candidate cannot log in to HR recruiter portal via OTP."""
        from accounts.models import OTPChallenge

        c_obj, plain_otp = OTPChallenge.create_challenge(
            self.candidate_user.email,
            OTPChallenge.Channel.EMAIL,
            user=self.candidate_user,
            purpose=OTPChallenge.Purpose.LOGIN,
            portal="hr",
        )

        resp = self.client.post(reverse("verify_otp"), {
            "identifier": self.candidate_user.email,
            "channel": "EMAIL",
            "portal": "hr",
            "otp_code": plain_otp,
        })
        self.assertNotEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_identifier_gives_neutral_generic_response(self):
        """Verify anti-enumeration: unknown email yields identical success response without leaking absence."""
        resp = self.client.post(reverse("request_otp"), {
            "identifier": "ghost_user_12345@domain.com",
            "channel": "EMAIL",
            "portal": "candidate",
        })
        self.assertRedirects(resp, reverse("verify_otp"))
        self.assertFalse(User.objects.filter(email="ghost_user_12345@domain.com").exists())

    def test_unverified_account_activated_on_otp_login(self):
        """Verify an unverified candidate account is marked verified and active upon successful OTP login."""
        from accounts.models import OTPChallenge

        unverified_user = User.objects.create_user(
            username="unverified_alex",
            email="unverified.alex@hirenexa.com",
            phone_number="+919876543233",
            role=User.Role.CANDIDATE,
            password="AlexPass123!",
            is_active=False,
            is_email_verified=False,
        )
        CandidateProfile.objects.get_or_create(user=unverified_user)

        c_obj, plain_otp = OTPChallenge.create_challenge(
            unverified_user.email,
            OTPChallenge.Channel.EMAIL,
            user=unverified_user,
            purpose=OTPChallenge.Purpose.LOGIN,
            portal="candidate",
        )

        resp = self.client.post(reverse("verify_otp"), {
            "identifier": unverified_user.email,
            "channel": "EMAIL",
            "portal": "candidate",
            "otp_code": plain_otp,
        })
        self.assertRedirects(resp, reverse("candidate_dashboard"))

        unverified_user.refresh_from_db()
        self.assertTrue(unverified_user.is_active)
        self.assertTrue(unverified_user.is_email_verified)

    def test_mobile_otp_sms_console_backend(self):
        """Verify Mobile SMS OTP dispatches cleanly via pluggable SMS backend (Console default)."""
        from accounts.services.sms_provider import get_sms_backend, ConsoleSMSBackend
        from accounts.services.otp_service import OTPService
        from accounts.models import OTPChallenge

        backend = get_sms_backend("console")
        self.assertIsInstance(backend, ConsoleSMSBackend)

        res = OTPService.issue_challenge(
            recipient="+919876543211",
            channel=OTPChallenge.Channel.SMS,
            purpose=OTPChallenge.Purpose.LOGIN,
            user=self.candidate_user,
            portal="candidate",
        )
        self.assertTrue(res["success"])
        self.assertEqual(len(res["otp"]), 6)


class FreshDatabaseBootstrappingAndHierarchyTests(TestCase):
    """
    Comprehensive verification of Phase 3 Fresh Account Hierarchy and Bootstrapping:
    - Platform Owner provisioning and idempotency
    - Multi-role demo data seeding (Company Admin, HR, Candidates, Freelancers, 11 Jobs)
    - DEBUG=False protection gate
    - Portal role separation (own portal succeeds, wrong portal rejected)
    - Cryptographic password hashing (no plaintext stored)
    - 1-Click Demo access validation
    """

    def setUp(self):
        from accounts.services.rate_limiter import RateLimiter
        from django.core.cache import cache
        RateLimiter.reset_all()
        cache.clear()
        self.client = Client()

    def test_create_platform_owner_is_idempotent_and_removes_setup_state(self):
        """Platform owner can be provisioned via CLI, is idempotent, and removes First-Time Setup state."""
        # 1. Initially check owner does not exist
        User.objects.filter(Q(role=User.Role.OWNER) | Q(is_superuser=True)).delete()
        resp_before = self.client.get(reverse("owner_login"))
        self.assertContains(resp_before, "First-Time Setup Required")

        # 2. Call create_platform_owner
        call_command(
            "create_platform_owner",
            username="master_owner",
            email="master@hirenexa.internal",
            password="MasterPassword123!",
            non_interactive=True,
        )

        owner = User.objects.get(username="master_owner")
        self.assertEqual(owner.role, User.Role.OWNER)
        self.assertTrue(owner.is_superuser)
        self.assertTrue(owner.is_staff)
        self.assertTrue(owner.is_active)
        self.assertTrue(owner.is_email_verified)
        self.assertTrue(check_password("MasterPassword123!", owner.password))

        # 3. First-Time Setup Required banner is now removed
        resp_after = self.client.get(reverse("owner_login"))
        self.assertNotContains(resp_after, "First-Time Setup Required")

        # 4. Idempotency: re-running does not fail and updates safely
        call_command(
            "create_platform_owner",
            username="master_owner",
            email="master@hirenexa.internal",
            password="MasterPassword123!",
            non_interactive=True,
        )
        self.assertEqual(User.objects.filter(username="master_owner").count(), 1)

    def test_seed_demo_data_refuses_when_debug_false(self):
        """seed_demo_data command is strictly blocked when DEBUG=False."""
        with self.settings(DEBUG=False):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_demo_data")
            self.assertIn("DEBUG=True", str(ctx.exception))

    def test_seed_demo_data_creates_correct_counts_and_relations(self):
        """seed_demo_data creates 1 Company Admin, 2 HR, 3 Candidates, 2 Freelancers, and 11 Jobs."""
        with self.settings(DEBUG=True):
            call_command("seed_demo_data")

        # Verify Counts
        self.assertEqual(User.objects.filter(role=User.Role.COMPANY_ADMIN).count(), 1)
        self.assertEqual(User.objects.filter(role=User.Role.RECRUITER).count(), 2)
        self.assertEqual(User.objects.filter(role=User.Role.CANDIDATE).count(), 3)
        self.assertEqual(User.objects.filter(role=User.Role.FREELANCER).count(), 2)
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(Job.objects.filter(status="ACTIVE").count(), 11)

        # Verify Organization memberships
        org = Organization.objects.get(name="Acme Technologies")
        self.assertEqual(org.members.count(), 3)  # 1 Company Admin + 2 HR

        # Verify no plaintext passwords
        for user in User.objects.filter(role__in=[
            User.Role.COMPANY_ADMIN, User.Role.RECRUITER, User.Role.CANDIDATE, User.Role.FREELANCER
        ]):
            self.assertFalse(user.password.startswith("pbkdf2_sha256$") is False and user.password.startswith("argon2$") is False)
            self.assertTrue(user.is_active)
            self.assertTrue(user.is_email_verified)
            self.assertTrue(user.is_phone_verified)

    def test_seeded_roles_can_login_on_own_portal_and_rejected_on_wrong_portal(self):
        """Each seeded role logs in successfully on its portal and is rejected on the wrong portal."""
        test_pass = "TestUserSecure123!"
        with patch.dict(os.environ, {"TEST_USER_PASSWORD": test_pass}):
            with self.settings(DEBUG=True):
                call_command("seed_demo_data")

        from accounts.services.rate_limiter import RateLimiter
        RateLimiter.reset_all()

        # 1. Candidate on Candidate Portal -> SUCCESS
        cand_login = self.client.post(reverse("candidate_login"), {
            "username": "aarav_student",
            "password": test_pass,
        }, follow=True)
        self.assertEqual(cand_login.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="aarav_student").pk)
        self.client.logout()

        # 2. Candidate on HR Portal -> REJECTED (Wrong Portal)
        cand_on_hr = self.client.post(reverse("hr_login"), {
            "username": "aarav_student",
            "password": test_pass,
        }, follow=True)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(cand_on_hr, "Access Denied")

        # 3. Candidate on Owner Portal -> REJECTED (Wrong Portal)
        cand_on_owner = self.client.post(reverse("owner_login"), {
            "username": "aarav_student",
            "password": test_pass,
        }, follow=True)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(cand_on_owner, "Access Denied")

        # 4. HR on HR Portal -> SUCCESS
        RateLimiter.reset_all()
        hr_login = self.client.post(reverse("hr_login"), {
            "username": "priya_recruiter",
            "password": test_pass,
        }, follow=True)
        self.assertEqual(hr_login.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="priya_recruiter").pk)
        self.client.logout()

        # 5. HR on Freelancer Portal -> REJECTED
        hr_on_free = self.client.post(reverse("freelancer_login"), {
            "username": "priya_recruiter",
            "password": test_pass,
        }, follow=True)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(hr_on_free, "Access Denied")

        # 6. Freelancer on Freelancer Portal -> SUCCESS
        RateLimiter.reset_all()
        free_login = self.client.post(reverse("freelancer_login"), {
            "username": "vikram_freelance",
            "password": test_pass,
        }, follow=True)
        self.assertEqual(free_login.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="vikram_freelance").pk)
        self.client.logout()

    def test_demo_login_buttons_work_for_roles_and_block_owner(self):
        """1-Click Demo buttons log in Candidate, Recruiter, Freelancer, and forbid Owner."""
        with self.settings(DEBUG=True):
            call_command("seed_demo_data")

        # Candidate Demo
        resp_cand = self.client.get(reverse("demo_login", kwargs={"role": "candidate"}), follow=True)
        self.assertEqual(resp_cand.status_code, 200)
        self.assertEqual(self.client.session["_auth_user_id"], str(User.objects.filter(role=User.Role.CANDIDATE).first().pk))
        self.client.logout()

        # Recruiter Demo
        resp_hr = self.client.get(reverse("demo_login", kwargs={"role": "recruiter"}), follow=True)
        self.assertEqual(resp_hr.status_code, 200)
        self.assertEqual(self.client.session["_auth_user_id"], str(User.objects.filter(role=User.Role.RECRUITER).first().pk))
        self.client.logout()

        # Freelancer Demo
        resp_free = self.client.get(reverse("demo_login", kwargs={"role": "freelancer"}), follow=True)
        self.assertEqual(resp_free.status_code, 200)
        self.assertEqual(self.client.session["_auth_user_id"], str(User.objects.filter(role=User.Role.FREELANCER).first().pk))
        self.client.logout()

        # Owner Demo strictly blocked
        resp_owner = self.client.get(reverse("demo_login", kwargs={"role": "owner"}), follow=True)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp_owner, "Platform Owner accounts cannot be accessed via 1-Click Demo")


class OwnerSecurityAndPrivilegeEscalationTests(TestCase):
    """
    Dedicated test suite for Platform Owner security:
    - Case-insensitive multi-identifier authentication (username/email/phone)
    - Two-step OTP completion
    - Generic error messages for failed attempts (anti-enumeration)
    - Inactive account protection
    - Non-owner denial and rate limiting
    - Public signup privilege escalation prevention
    - Idempotent create_owner management command
    """

    def get_latest_email_otp(self):
        from django.core import mail
        import re
        if mail.outbox:
            for message in reversed(mail.outbox):
                match = re.search(r'\b\d{6}\b', message.body)
                if match:
                    return match.group(0)
        return ""

    def setUp(self):
        self.client = Client()
        RateLimiter.reset_all()
        self.owner_password = "SecureOwnerPass123!"
        self.owner = User.objects.create_user(
            username="master_owner",
            email="master_owner@hirenexa.internal",
            phone_number="+919876543210",
            password=self.owner_password,
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
            is_active=True,
            is_email_verified=True,
        )
        self.candidate = User.objects.create_user(
            username="test_candidate",
            email="candidate@hirenexa.internal",
            password="CandidatePass123!",
            role=User.Role.CANDIDATE,
            is_active=True,
        )

    def test_successful_owner_login_with_username(self):
        """Owner logs in with username + password, receives OTP, verifies OTP, and accesses dashboard."""
        resp = self.client.post(reverse("owner_login"), {
            "username": "master_owner",
            "password": self.owner_password,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("owner_preauth_id", self.client.session)

        # Verify OTP
        otp_code = self.get_latest_email_otp()
        self.assertTrue(bool(otp_code))
        otp_resp = self.client.post(reverse("owner_login_otp_verify"), {
            "otp_code": otp_code,
        }, follow=True)
        self.assertEqual(otp_resp.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.owner.pk)

    def test_successful_owner_login_with_case_insensitive_email(self):
        """Owner logs in with mixed-case email identifier."""
        resp = self.client.post(reverse("owner_login"), {
            "username": "MASTER_OWNER@HIRENEXA.INTERNAL",
            "password": self.owner_password,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("owner_preauth_id", self.client.session)

    def test_successful_owner_login_with_phone(self):
        """Owner logs in with phone number identifier."""
        resp = self.client.post(reverse("owner_login"), {
            "username": "9876543210",
            "password": self.owner_password,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("owner_preauth_id", self.client.session)

    def test_owner_login_wrong_password_generic_error(self):
        """Failed owner login with wrong password displays generic error without revealing account existence."""
        resp = self.client.post(reverse("owner_login"), {
            "username": "master_owner",
            "password": "WrongPassword999!",
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp, "Invalid administrator credentials.")

    def test_owner_login_inactive_user_denied(self):
        """Inactive owner cannot log in and receives generic error without leaking account state."""
        self.owner.is_active = False
        self.owner.save()
        resp = self.client.post(reverse("owner_login"), {
            "username": "master_owner",
            "password": self.owner_password,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("owner_preauth_id", self.client.session)
        self.assertContains(resp, "Invalid administrator credentials.")

    def test_non_owner_user_denied_on_owner_portal(self):
        """Candidate attempting to sign in on owner portal receives generic error and is denied."""
        resp = self.client.post(reverse("owner_login"), {
            "username": "test_candidate",
            "password": "CandidatePass123!",
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp, "Access Denied")

    def test_public_signup_cannot_escalate_to_owner(self):
        """Public signup strictly blocks role escalation to OWNER or superuser."""
        post_data = {
            "full_name": "Malicious User",
            "username": "malicious_user",
            "email": "malicious@example.com",
            "country_code": "+91",
            "phone_number": "9811122233",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
            "role": "OWNER",
            "is_superuser": True,
            "is_staff": True,
        }
        resp = self.client.post(reverse("signup"), post_data)
        self.assertEqual(resp.status_code, 200)
        user = User.objects.filter(username="malicious_user").first()
        if user:
            self.assertFalse(user.is_superuser)
            self.assertFalse(user.is_staff)
            self.assertNotEqual(user.role, User.Role.OWNER)

    def test_create_owner_management_command_idempotent(self):
        """create_owner command idempotently provisions owner with correct roles and hashed password."""
        call_command(
            "create_owner",
            username="cli_test_owner",
            email="cli_test_owner@hirenexa.internal",
            password="CliOwnerPassword123!",
            non_interactive=True,
        )
        owner_obj = User.objects.get(username="cli_test_owner")
        self.assertTrue(owner_obj.is_superuser)
        self.assertTrue(owner_obj.is_staff)
        self.assertTrue(owner_obj.is_active)
        self.assertEqual(owner_obj.role, User.Role.OWNER)
        self.assertTrue(owner_obj.check_password("CliOwnerPassword123!"))

        # Re-running updates safely without error
        call_command(
            "create_owner",
            username="cli_test_owner",
            email="cli_test_owner@hirenexa.internal",
            password="CliOwnerPassword123_Updated!",
            non_interactive=True,
        )
        owner_obj.refresh_from_db()
        self.assertTrue(owner_obj.check_password("CliOwnerPassword123_Updated!"))









