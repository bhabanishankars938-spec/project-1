from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # 0. Role Hub / Landing (Matches ChatGPT Specification)
    path("roles/", views.role_hub_view, name="role_hub"),

    # 1. Platform Owner / Super Admin
    path("owner/login/", views.owner_login_view, name="owner_login"),
    path("owner/login/verify-otp/", views.owner_login_otp_verify_view, name="owner_login_otp_verify"),
    path("owner/login/resend-otp/", views.owner_login_otp_resend_view, name="owner_login_otp_resend"),
    path("owner/setup/", views.first_time_owner_setup_view, name="first_time_owner_setup"),
    path("owner/setup/verify/", views.first_time_owner_setup_verify_view, name="first_time_owner_setup_verify"),
    path("owner/setup/resend-otp/", views.first_time_owner_setup_resend_view, name="first_time_owner_setup_resend"),

    # 2. HR / Tech Recruiter
    path("hr/login/", views.hr_login_view, name="hr_login"),
    path("hr/signup/", views.hr_signup_view, name="hr_signup"),
    path("hr/register/", views.hr_signup_view, name="hr_register"),

    # 3. Freelancer
    path("freelancer/login/", views.freelancer_login_view, name="freelancer_login"),
    path("freelancer/signup/", views.freelancer_signup_view, name="freelancer_signup"),
    path("freelancer/register/", views.freelancer_signup_view, name="freelancer_register"),

    # 4. Student / Candidate
    path("candidate/login/", views.candidate_login_view, name="candidate_login"),
    path("candidate/signup/", views.candidate_signup_view, name="candidate_signup"),
    path("student/login/", views.candidate_login_view, name="student_login"),
    path("student/register/", views.candidate_signup_view, name="student_register"),

    # Unified Multi-Identifier Login & Public Sign Up
    path("login/", views.unified_login_view, name="login"),
    path("login/verify-otp/", views.unified_login_otp_verify_view, name="unified_login_otp_verify"),
    path("login/resend-otp/", views.unified_login_otp_resend_view, name="unified_login_otp_resend"),
    path("signup/", views.signup_view, name="signup"),
    path("register/", views.signup_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("switch-portal/", views.switch_portal_view, name="switch_portal"),
    path("demo-login/<str:role>/", views.demo_login_view, name="demo_login"),

    # Enterprise Dual Email & Mobile OTP Verification
    path("verify/", views.dual_verification_view, name="dual_verification"),
    path("verify/resend/<str:channel>/", views.resend_otp_api_view, name="resend_otp_api"),

    # Pluggable Multi-Portal OTP System (Email OTP & Mobile OTP)
    path("otp/request/", views.request_otp_view, name="request_otp"),
    path("otp/verify/", views.verify_otp_view, name="verify_otp"),
    path("otp/resend/", views.resend_otp_view, name="resend_otp"),
    path("set-password/", views.set_password_view, name="set_password"),

    # Phone Number OTP System (Passwordless Login - Enhanced & Synced)
    path("login/otp/", views.phone_otp_login_request_view, name="phone_otp_login"),
    path("login/otp/verify/", views.phone_otp_verify_view, name="phone_otp_verify"),

    # Email & Phone Verification System (Badges)
    path("verify/email/send/", views.send_email_verification_view, name="send_email_verification"),
    path("verify/email/confirm/", views.verify_email_otp_view, name="verify_email_otp"),
    path("verify/phone/send/", views.send_phone_verification_view, name="send_phone_verification"),
    path("verify/phone/confirm/", views.verify_phone_verification_view, name="verify_phone_verification"),

    # Forgot Password & Reset via OTP (Email & Mobile Phone) and Secure Link
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("reset-password/", views.reset_password_view, name="reset_password_otp"),
    path("password-reset/", views.forgot_password_view, name="password_reset"),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/reset_password.html",
            success_url="/accounts/login/"
        ),
        name="password_reset_confirm",
    ),
]
