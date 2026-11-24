from django.test import TestCase, Client, override_settings
from django.urls import reverse
from accounts.models import User
from accounts.services.rate_limiter import RateLimiter


@override_settings(UNIFIED_REQUIRE_OTP=False, OWNER_REQUIRE_OTP=False)
class AuthenticationScenariosTestSuite(TestCase):
    """
    Comprehensive verification suite for HireNexa V4 Workspace Authentication:
    1. Existing user with correct password.
    2. Existing user with incorrect password.
    3. Email login.
    4. Username login.
    5. Mobile login.
    6. Inactive account.
    7. Owner login.
    8. Candidate login.
    9. Recruiter login.
    10. Session persistence.
    """

    def setUp(self):
        self.client = Client()
        self.login_url = reverse("login")
        RateLimiter.reset_all()

        self.password = "SecureTestPass123!"

        # 1. Platform Owner (admin)
        self.owner = User.objects.create_user(
            username="admin",
            email="admin@hirenexa.internal",
            phone_number="+919800000000",
            password=self.password,
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
            is_active=True,
            is_email_verified=True,
            is_phone_verified=True,
        )

        # 2. Candidate User
        self.candidate = User.objects.create_user(
            username="priya_candidate",
            email="priya@example.com",
            phone_number="+919876543210",
            password=self.password,
            role=User.Role.CANDIDATE,
            is_active=True,
            is_email_verified=True,
            is_phone_verified=True,
        )

        # 3. Recruiter User
        self.recruiter = User.objects.create_user(
            username="rajesh_recruiter",
            email="rajesh@company.com",
            phone_number="+919876543211",
            password=self.password,
            role=User.Role.RECRUITER,
            is_active=True,
            is_email_verified=True,
            is_phone_verified=True,
        )

        # 4. Inactive User
        self.inactive_user = User.objects.create_user(
            username="inactive_john",
            email="inactive@example.com",
            phone_number="+919876543212",
            password=self.password,
            role=User.Role.CANDIDATE,
            is_active=False,
            is_email_verified=True,
            is_phone_verified=True,
        )

    def tearDown(self):
        RateLimiter.reset_all()

    def test_01_existing_user_correct_password(self):
        """1. Existing user with correct password authenticates and redirects."""
        response = self.client.post(self.login_url, {
            "username": "admin@hirenexa.internal",
            "password": self.password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)
        self.assertRedirects(response, reverse("owner_dashboard"))

    def test_02_existing_user_incorrect_password(self):
        """2. Existing user with incorrect password returns 200 with invalid credentials message."""
        response = self.client.post(self.login_url, {
            "username": "admin@hirenexa.internal",
            "password": "WrongPassword999!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        self.assertContains(response, "Invalid credentials")

    def test_03_email_login(self):
        """3. Login using registered email address."""
        response = self.client.post(self.login_url, {
            "username": "admin@hirenexa.internal",
            "password": self.password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)

    def test_04_username_login(self):
        """4. Login using standard username."""
        response = self.client.post(self.login_url, {
            "username": "admin",
            "password": self.password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)

    def test_05_mobile_login(self):
        """5. Login using mobile phone number in both E.164 and 10-digit formats."""
        # 5a. E.164 format (+919800000000)
        response_e164 = self.client.post(self.login_url, {
            "username": "+919800000000",
            "password": self.password,
        })
        self.assertEqual(response_e164.status_code, 302)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)
        self.client.logout()

        # 5b. Local 10-digit format (9800000000)
        response_local = self.client.post(self.login_url, {
            "username": "9800000000",
            "password": self.password,
        })
        self.assertEqual(response_local.status_code, 302)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.owner.id)

    def test_06_inactive_account(self):
        """6. Inactive account cannot authenticate and returns error message."""
        response = self.client.post(self.login_url, {
            "username": "inactive_john",
            "password": self.password,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        self.assertContains(response, "deactivated")

    def test_07_owner_login_redirect(self):
        """7. Platform Owner login redirects directly to Owner Dashboard (/owner/)."""
        response = self.client.post(self.login_url, {
            "username": "admin@hirenexa.internal",
            "password": self.password,
        })
        self.assertRedirects(response, reverse("owner_dashboard"))

    def test_08_candidate_login_redirect(self):
        """8. Candidate login redirects directly to Candidate Dashboard (/candidate/)."""
        response = self.client.post(self.login_url, {
            "username": "priya@example.com",
            "password": self.password,
        })
        self.assertRedirects(response, reverse("candidate_dashboard"))
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.candidate.id)

    def test_09_recruiter_login_redirect(self):
        """9. Recruiter login redirects directly to Recruiter/HR Dashboard (/hr/)."""
        response = self.client.post(self.login_url, {
            "username": "rajesh@company.com",
            "password": self.password,
        })
        self.assertRedirects(response, reverse("hr_dashboard"))
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.recruiter.id)

    def test_10_session_persistence(self):
        """10. Session persistence: remember_me sets 14-day expiry; unchecked expires on browser close."""
        # 10a. With remember_me checked
        self.client.post(self.login_url, {
            "username": "admin@hirenexa.internal",
            "password": self.password,
            "remember_me": "1",
        })
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)  # 14 days
        self.client.logout()

        # 10b. Without remember_me
        self.client.post(self.login_url, {
            "username": "admin@hirenexa.internal",
            "password": self.password,
        })
        self.assertTrue(self.client.session.get_expire_at_browser_close())
