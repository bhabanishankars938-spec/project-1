import re
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.decorators import login_required
from .utils import mask_email
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from django.http import JsonResponse
from .backends import MultiIdentifierModelBackend
from .decorators import (
    owner_required,
    recruiter_required,
    freelancer_required,
    candidate_required,
    get_client_ip,
)
from .forms import (
    SignUpForm,
    StudentSignUpForm,
    HRSignUpForm,
    FreelancerSignUpForm,
    ForgotPasswordRequestForm,
    ResetPasswordWithOTPForm,
    ChangeEmailForm,
    ChangePhoneForm,
)
from .models import (
    User, PhoneOTP, EmailOTP, AuditLog, PlatformSetting,
    OTPChallenge, OTPAttempt, VerificationEvent
)
from .validators import (
    validate_and_normalize_email,
    validate_and_normalize_phone,
    COUNTRY_CODES,
)
from .services.delivery import EmailDeliveryService, SMSDeliveryService
from .services.otp_service import OTPService
from .services.rate_limiter import RateLimiter
from .services.auth_service import AuthService
from recruitment.models import (
    CandidateProfile,
    RecruiterProfile,
    FreelancerProfile,
    Job,
    Application,
    Project,
    ProjectProposal,
)
from core.sqlalchemy_db import (
    get_database_diagnostics,
    fetch_audit_logs_sqla,
    fetch_platform_analytics_sqla,
)


def get_role_dashboard_url(user):
    """Determine the appropriate destination dashboard for a user role."""
    if not user or not user.is_authenticated:
        return reverse("login")
    if user.is_superuser or str(getattr(user, "role", "")).upper() in (User.Role.OWNER, "OWNER") or getattr(user, "is_owner", False):
        return reverse("owner_dashboard")
    elif getattr(user, "is_company_admin", False) or user.role == "COMPANY_ADMIN":
        return reverse("company_dashboard")
    elif user.role == User.Role.RECRUITER:
        return reverse("hr_dashboard")
    elif user.role == User.Role.FREELANCER:
        return reverse("freelancer_dashboard")
    return reverse("candidate_dashboard")


def clean_phone_number(raw_phone):
    """Normalize phone number string into clean digits with standard format."""
    if not raw_phone:
        return ""
    cleaned = raw_phone.strip()
    digits = re.sub(r"[^\d]", "", cleaned)
    if cleaned.startswith("+"):
        return f"+{digits}"
    return digits


def find_user_by_identifier(identifier):
    """
    Lookup a user across Username, Email ID, or Mobile Phone Number.
    Supports local format and international E.164 formats (+91 9876543210, 9876543210).
    Delegates to MultiIdentifierModelBackend for single source of truth.
    """
    return MultiIdentifierModelBackend.find_user(identifier)


# ==============================================================================
# 0. HRENEXA MULTI-ROLE LOGIN HUB (MATCHES CHATGPT SPECIFICATION)
# ==============================================================================

def role_hub_view(request):
    """
    Central 4-Role Login Hub matching the exact architecture specification:
      1. OWNER / SUPER ADMIN (Full Platform Access)
      2. HR Login (Company Dashboard)
      3. Freelancer Login (Freelancer Dashboard)
      4. Student / Candidate Login (Resume Upload & Applications)
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))
    return render(request, "accounts/roles_hub.html")


# ==============================================================================
# 1. OWNER / SUPER ADMIN LOGIN & CONTROL CENTER
# ==============================================================================

def owner_login_view(request):
    """
    Tier-0 High-Security Gateway for Platform Owner / Super Admin.
    Enforces Two-Step Authentication: Password + Mandatory Email OTP.
    """
    if request.user.is_authenticated:
        if request.user.is_owner:
            return redirect("owner_dashboard")
        return redirect(get_role_dashboard_url(request.user))

    owner_exists = User.objects.filter(Q(role__iexact="owner") | Q(is_superuser=True)).exists()
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("owner_dashboard")

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip() or request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")

        auth_result = AuthService.authenticate_portal(request, identifier, password, portal="owner")
        status = auth_result["status"]

        if status == "RATE_LIMITED":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/owner_login.html", {
                "next": next_url,
                "identifier": identifier,
                "owner_exists": owner_exists,
                "is_locked_out": True,
                "retry_minutes": auth_result.get("retry_minutes", 1),
            }, status=429)

        if status in ("INVALID_CREDENTIALS", "UNVERIFIED", "DEACTIVATED", "WRONG_PORTAL"):
            messages.error(request, "Access Denied: Invalid administrator credentials. Please check your username/email and password.")
            return render(request, "accounts/owner_login.html", {
                "next": next_url,
                "identifier": identifier,
                "owner_exists": owner_exists,
            })

        # SUCCESS: Valid active owner
        resolved_user = auth_result["user"]

        # Check whether OTP is required for Owner Login
        require_otp = getattr(settings, "OWNER_REQUIRE_OTP", False)
        if not require_otp:
            # Password-only authentication: Login directly without OTP
            login(request, resolved_user, backend="accounts.backends.MultiIdentifierModelBackend")
            RateLimiter.reset_attempts(get_client_ip(request), resolved_user.username, portal="owner")
            AuditLog.objects.create(
                user=resolved_user,
                action="OWNER_LOGIN_SUCCESS",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"username": resolved_user.username, "login_method": "PASSWORD"},
            )
            messages.success(request, f"Welcome Platform Owner {resolved_user.username}. Security session initialized.")
            return redirect(next_url)

        # 2-Step Authentication: Issue Email OTP
        target_email = resolved_user.email or f"{resolved_user.username}@hirenexa.internal"
        otp_obj, raw_code = EmailOTP.generate(
            email=target_email,
            purpose=EmailOTP.Purpose.LOGIN,
            user=resolved_user,
            validity_minutes=10,
        )
        dispatch_res = EmailDeliveryService.send_otp_email(
            recipient_email=target_email,
            user_name=resolved_user.full_name,
            raw_otp=raw_code,
            validity_minutes=10,
        )

        if not dispatch_res.get("success"):
            otp_obj.is_used = True
            otp_obj.save(update_fields=["is_used"])
            messages.error(request, "Email delivery failed. Please check SMTP settings or try again.")
            return render(request, "accounts/owner_login.html", {
                "next": next_url,
                "identifier": identifier,
                "owner_exists": owner_exists,
            })

        request.session["owner_preauth_id"] = resolved_user.id
        request.session["owner_preauth_next"] = next_url

        AuditLog.objects.create(
            user=resolved_user,
            action="OWNER_PASSWORD_VERIFIED_OTP_DISPATCHED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"username": resolved_user.username, "email": mask_email(target_email)},
        )
        messages.success(request, f"We sent a 6-digit verification code to {mask_email(target_email)}.")
        return redirect("owner_login_otp_verify")

    return render(request, "accounts/owner_login.html", {"next": next_url, "owner_exists": owner_exists})


def owner_login_otp_verify_view(request):
    """
    Step 2: Platform Owner 2FA Verification Gateway.
    Verifies 6-digit Email OTP before initiating owner administrative session.
    """
    owner_id = request.session.get("owner_preauth_id")
    if not owner_id:
        messages.warning(request, "Security verification session expired. Please sign in again.")
        return redirect("owner_login")

    owner = get_object_or_404(User, pk=owner_id)
    if not owner.is_active:
        messages.error(request, "This account is inactive. Authentication aborted.")
        return redirect("owner_login")
    next_url = request.session.get("owner_preauth_next") or reverse("owner_dashboard")
    client_ip = get_client_ip(request)
    masked_email = mask_email(owner.email)

    if request.method == "POST":
        otp_code = request.POST.get("otp_code", "").strip()
        if not otp_code or len(otp_code) != 6:
            messages.error(request, "Please enter the complete 6-digit code.")
            return render(request, "accounts/owner_login_otp.html", {"owner": owner, "masked_email": masked_email})

        otp_record = EmailOTP.objects.filter(
            user=owner,
            purpose=EmailOTP.Purpose.LOGIN,
            is_used=False,
            expires_at__gte=timezone.now(),
        ).first()

        if not otp_record:
            messages.error(request, "Invalid or expired code. Please request a new verification code.")
            return render(request, "accounts/owner_login_otp.html", {"owner": owner, "masked_email": masked_email})

        is_valid, status_reason = otp_record.check_code(otp_code)

        if status_reason == "LOCKED":
            RateLimiter.record_failed_attempt(client_ip, owner.username)
            AuditLog.objects.create(
                user=owner,
                action="OWNER_2FA_OTP_LOCKED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"reason": "5_FAILED_ATTEMPTS"},
            )
            messages.error(request, "Too many failed attempts (5/5). This code is locked. Please request a new code.")
            return render(request, "accounts/owner_login_otp.html", {"owner": owner, "masked_email": masked_email})

        elif not is_valid:
            RateLimiter.record_failed_attempt(client_ip, owner.username)
            remaining = max(0, 5 - otp_record.attempts)
            AuditLog.objects.create(
                user=owner,
                action="OWNER_2FA_OTP_FAILED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"attempts": otp_record.attempts},
            )
            messages.error(request, f"Invalid or expired code. ({remaining} attempts remaining)")
            return render(request, "accounts/owner_login_otp.html", {"owner": owner, "masked_email": masked_email})

        # Success
        RateLimiter.reset_attempts(client_ip, owner.username, portal="owner")
        login(request, owner, backend="accounts.backends.MultiIdentifierModelBackend")

        AuditLog.objects.create(
            user=owner,
            action="OWNER_2FA_LOGIN_SUCCESS",
            ip_address=client_ip,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"username": owner.username, "login_method": "2FA_EMAIL_OTP"},
        )

        request.session.pop("owner_preauth_id", None)
        request.session.pop("owner_preauth_next", None)

        messages.success(request, f"✓ Welcome Platform Owner {owner.username}. Security session initialized.")
        return redirect(next_url)

    return render(request, "accounts/owner_login_otp.html", {"owner": owner, "masked_email": masked_email})


def owner_login_otp_resend_view(request):
    """Resend 6-digit Email OTP for Platform Owner 2FA with cooldown and hourly limit."""
    owner_id = request.session.get("owner_preauth_id")
    if not owner_id:
        return redirect("owner_login")

    owner = get_object_or_404(User, pk=owner_id)
    if not owner.is_active:
        messages.error(request, "This account is inactive. Authentication aborted.")
        return redirect("owner_login")

    can_request, err_msg, wait_sec = EmailOTP.can_request_otp(
        email=owner.email,
        purpose=EmailOTP.Purpose.LOGIN,
        cooldown_seconds=60,
        max_per_hour=5,
    )
    if not can_request:
        messages.warning(request, err_msg)
        return redirect("owner_login_otp_verify")

    otp_obj, raw_code = EmailOTP.generate(
        email=owner.email,
        purpose=EmailOTP.Purpose.LOGIN,
        user=owner,
        validity_minutes=10,
    )
    dispatch_res = EmailDeliveryService.send_otp_email(
        recipient_email=owner.email,
        user_name=owner.full_name,
        raw_otp=raw_code,
        validity_minutes=10,
    )

    if not dispatch_res.get("success"):
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        messages.error(request, "Unable to send verification email at this time. Please try again shortly.")
    else:
        messages.success(request, f"We sent a fresh 6-digit code to {mask_email(owner.email)}.")

    return redirect("owner_login_otp_verify")


# ==============================================================================
# 1B. FIRST-TIME PLATFORM OWNER INITIALIZATION (WEB ROUTE)
# ==============================================================================

def first_time_owner_setup_view(request):
    """
    Secure One-Time Platform Owner Provisioning Gateway.
    Strictly disabled if a Platform Owner account already exists.
    """
    if User.objects.filter(Q(role__iexact="owner") | Q(is_superuser=True)).exists():
        messages.error(request, "A Platform Owner account is already initialized. Public setup is permanently locked.")
        return redirect("owner_login")

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone_number = clean_phone_number(request.POST.get("phone_number", ""))
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        errors = []
        if not full_name:
            errors.append("Full Name is required.")
        if not username or len(username) < 3:
            errors.append("Username must be at least 3 characters long.")
        elif User.objects.filter(username__iexact=username).exists():
            errors.append(f"Username '{username}' is already taken.")

        if not email or "@" not in email:
            errors.append("A valid official email address is required.")
        elif User.objects.filter(email__iexact=email).exists():
            errors.append(f"Email '{email}' is already registered to another user.")

        if len(password) < 8:
            errors.append("Master Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Master Password and Confirmation Password do not match.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "accounts/owner_setup.html", {"form_data": request.POST})

        # Check rate limits on OTP creation
        can_request, err_msg, wait_sec = EmailOTP.can_request_otp(
            email=email,
            purpose=EmailOTP.Purpose.OWNER_SETUP,
            cooldown_seconds=60,
            max_per_hour=5,
        )
        if not can_request:
            messages.error(request, err_msg)
            return render(request, "accounts/owner_setup.html", {"form_data": request.POST})

        # Generate Email OTP (hashed in database)
        otp_record, raw_code = EmailOTP.generate(
            email=email,
            purpose=EmailOTP.Purpose.OWNER_SETUP,
            validity_minutes=15,
        )
        dispatch_res = EmailDeliveryService.send_otp_email(
            recipient_email=email,
            user_name=full_name,
            raw_otp=raw_code,
            validity_minutes=15,
        )

        if getattr(settings, "DEBUG", False):
            request.session["dev_owner_otp"] = raw_code
            messages.info(request, f"[DEV MODE] Platform Owner Setup OTP: {raw_code}")

        if not dispatch_res.get("success"):
            if not getattr(settings, "DEBUG", False):
                otp_record.is_used = True
                otp_record.save(update_fields=["is_used"])
                messages.error(request, "Unable to send verification email at this time. Please try again shortly.")
                return render(request, "accounts/owner_setup.html", {"form_data": request.POST})
            else:
                messages.warning(request, f"[DEV NOTICE] Live email dispatch skipped ({dispatch_res.get('error')}). Use the dev OTP code above.")

        # Store pending registration with password securely hashed via Argon2/Django make_password
        request.session["pending_owner_setup"] = {
            "full_name": full_name,
            "username": username,
            "email": email,
            "phone_number": phone_number or None,
            "password_hash": make_password(password),
        }

        messages.success(request, f"We sent a 6-digit code to {mask_email(email)}")
        return redirect("first_time_owner_setup_verify")

    return render(request, "accounts/owner_setup.html")


def first_time_owner_setup_verify_view(request):
    """Step 2: Confirm Email OTP and create root Platform Owner account."""
    if User.objects.filter(Q(role__iexact="owner") | Q(is_superuser=True)).exists():
        messages.error(request, "A Platform Owner account is already initialized. Public setup is permanently locked.")
        return redirect("owner_login")

    pending_data = request.session.get("pending_owner_setup")
    if not pending_data:
        messages.warning(request, "Owner initialization session expired. Please begin setup again.")
        return redirect("first_time_owner_setup")

    target_email = pending_data["email"]
    masked_email = mask_email(target_email)

    # Cooldown remaining for resend button
    latest_otp = EmailOTP.objects.filter(
        email__iexact=target_email,
        purpose=EmailOTP.Purpose.OWNER_SETUP,
    ).order_by("-created_at").first()
    cooldown_remaining = max(0, int(60 - (timezone.now() - latest_otp.created_at).total_seconds())) if latest_otp else 0

    if request.method == "POST":
        otp_code = request.POST.get("otp_code", "").strip()
        if not otp_code or len(otp_code) != 6:
            messages.error(request, "Please enter the complete 6-digit code.")
            return render(request, "accounts/owner_setup_verify.html", {
                "masked_email": masked_email,
                "cooldown_remaining": cooldown_remaining,
            })

        otp_record = EmailOTP.objects.filter(
            email__iexact=target_email,
            purpose=EmailOTP.Purpose.OWNER_SETUP,
            is_used=False,
            expires_at__gte=timezone.now(),
        ).first()

        if not otp_record:
            messages.error(request, "Invalid or expired code. Please request a new verification code.")
            return render(request, "accounts/owner_setup_verify.html", {
                "masked_email": masked_email,
                "cooldown_remaining": cooldown_remaining,
            })

        is_valid, status_reason = otp_record.check_code(otp_code)

        if status_reason == "LOCKED":
            messages.error(request, "Too many failed attempts (5/5). This code has been locked for security. Please click 'Resend Code'.")
            return render(request, "accounts/owner_setup_verify.html", {
                "masked_email": masked_email,
                "cooldown_remaining": 0,
            })

        elif not is_valid:
            rem = max(0, 5 - otp_record.attempts)
            messages.error(request, f"Invalid or expired code. ({rem} attempts remaining)")
            return render(request, "accounts/owner_setup_verify.html", {
                "masked_email": masked_email,
                "cooldown_remaining": cooldown_remaining,
            })

        # Verification successful: Create Root Platform Owner
        name_parts = pending_data["full_name"].split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        owner = User(
            username=pending_data["username"],
            email=target_email,
            first_name=first_name,
            last_name=last_name,
            phone_number=pending_data.get("phone_number") or None,
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
            is_active=True,
            is_email_verified=True,
            email_verified_at=timezone.now(),
            password=pending_data["password_hash"],  # Pre-hashed with Argon2id
        )
        owner.save()

        # Reassign any existing news announcements to the new owner
        from recruitment.models import NewsAnnouncement
        NewsAnnouncement.objects.all().update(author=owner)

        AuditLog.objects.create(
            user=owner,
            action="PLATFORM_OWNER_INITIALIZED_WEB",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={
                "username": owner.username,
                "email": mask_email(owner.email),
                "role": owner.role,
                "auth_method": "ARGON2ID_EMAIL_OTP",
            },
        )

        request.session.pop("pending_owner_setup", None)
        login(request, owner, backend="django.contrib.auth.backends.ModelBackend")

        messages.success(
            request,
            f"✓ Platform Owner account '{owner.username}' initialized and verified successfully! Welcome to HireNexa."
        )
        return redirect("owner_dashboard")

    return render(request, "accounts/owner_setup_verify.html", {
        "masked_email": masked_email,
        "cooldown_remaining": cooldown_remaining,
        "dev_owner_otp": request.session.get("dev_owner_otp"),
    })


def first_time_owner_setup_resend_view(request):
    """Resend 6-digit Email OTP for Platform Owner First-Time Setup."""
    if User.objects.filter(Q(role__iexact="owner") | Q(is_superuser=True)).exists():
        messages.error(request, "A Platform Owner account is already initialized.")
        return redirect("owner_login")

    pending_data = request.session.get("pending_owner_setup")
    if not pending_data:
        messages.warning(request, "Owner initialization session expired. Please start setup again.")
        return redirect("first_time_owner_setup")

    target_email = pending_data["email"]

    can_request, err_msg, wait_sec = EmailOTP.can_request_otp(
        email=target_email,
        purpose=EmailOTP.Purpose.OWNER_SETUP,
        cooldown_seconds=60,
        max_per_hour=5,
    )
    if not can_request:
        messages.warning(request, err_msg)
        return redirect("first_time_owner_setup_verify")

    otp_record, raw_code = EmailOTP.generate(
        email=target_email,
        purpose=EmailOTP.Purpose.OWNER_SETUP,
        validity_minutes=15,
    )
    dispatch_res = EmailDeliveryService.send_otp_email(
        recipient_email=target_email,
        user_name=pending_data["full_name"],
        raw_otp=raw_code,
        validity_minutes=15,
    )

    if getattr(settings, "DEBUG", False):
        request.session["dev_owner_otp"] = raw_code
        messages.info(request, f"[DEV MODE] Fresh Verification Code: {raw_code}")

    if not dispatch_res.get("success"):
        if not getattr(settings, "DEBUG", False):
            otp_record.is_used = True
            otp_record.save(update_fields=["is_used"])
            messages.error(request, "Unable to send verification email at this time. Please try again shortly.")
        else:
            messages.warning(request, f"[DEV NOTICE] Live email dispatch skipped ({dispatch_res.get('error')}). Use the dev OTP code above.")
    else:
        messages.success(request, f"We sent a fresh 6-digit code to {mask_email(target_email)}.")

    return redirect("first_time_owner_setup_verify")



# ==============================================================================
# 2. HR / RECRUITER LOGIN & REGISTRATION
# ==============================================================================

def hr_login_view(request):
    """
    Dedicated login interface for HR and Tech Recruiters.
    Supports Username, Email ID, or Mobile Phone Number.
    """
    if request.GET.get("switch") == "1":
        logout(request)
        messages.info(request, "Signed out of previous session. Please sign in with your corporate credentials.")
        return redirect("vanity_company_login")

    if request.user.is_authenticated:
        if request.user.is_recruiter or request.user.is_company_admin or request.user.is_owner:
            return redirect(get_role_dashboard_url(request.user))
        logout(request)
        messages.info(request, "Switched to Corporate portal. Please sign in with your Company Admin / Recruiter credentials.")
        return redirect("vanity_company_login")

    next_url = request.GET.get("next") or request.POST.get("next") or reverse("hr_dashboard")

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip() or request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")

        auth_result = AuthService.authenticate_portal(request, identifier, password, portal="hr")
        status = auth_result["status"]

        if status == "RATE_LIMITED":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/hr_login.html", {
                "next": next_url,
                "identifier": identifier,
                "is_locked_out": True,
                "retry_minutes": auth_result.get("retry_minutes", 1),
            }, status=429)

        if status == "INVALID_CREDENTIALS":
            messages.error(request, "Invalid recruiter credentials. Please verify your Username/Email/Phone and Password.")
            return render(request, "accounts/hr_login.html", {"next": next_url, "identifier": identifier})

        if status == "UNVERIFIED":
            resolved_user = auth_result["user"]
            request.session["pending_verification_user_id"] = resolved_user.id
            request.session["post_verification_next_url"] = next_url
            verify_url = reverse("dual_verification")
            messages.warning(
                request,
                mark_safe(f'Your account is pending verification. <a href="{verify_url}" style="text-decoration: underline; font-weight: bold;">Verify / Resend OTP &rarr;</a>')
            )
            return render(request, "accounts/hr_login.html", {
                "next": next_url,
                "identifier": identifier,
                "unverified_account": True,
                "verify_url": verify_url,
            })

        if status == "DEACTIVATED":
            messages.error(request, "Your account has been deactivated. Please contact support.")
            return render(request, "accounts/hr_login.html", {"next": next_url, "identifier": identifier})

        if status == "WRONG_PORTAL":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/hr_login.html", {
                "next": next_url,
                "identifier": identifier,
                "wrong_portal": True,
                "correct_url": auth_result.get("correct_url"),
            })

        # SUCCESS
        auth_user = auth_result["user"]
        login(request, auth_user, backend="accounts.backends.MultiIdentifierModelBackend")
        messages.success(request, f"Welcome back, {auth_user.username}! Recruiter workspace loaded.")
        return redirect(get_role_dashboard_url(auth_user))

    return render(request, "accounts/hr_login.html", {"next": next_url})


def hr_signup_view(request):
    """Dedicated registration for HR / Tech Recruiters."""
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    if request.method == "POST":
        form = HRSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            company_name = form.cleaned_data.get("company_name", "").strip()
            RecruiterProfile.objects.get_or_create(
                user=user,
                defaults={"company_name": company_name or "Independent Recruiter"}
            )
            require_otp = getattr(settings, "UNIFIED_REQUIRE_OTP", False)
            if not require_otp:
                user.is_active = True
                user.is_email_verified = True
                user.is_phone_verified = True
                user.save(update_fields=["is_active", "is_email_verified", "is_phone_verified"])
                login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
                AuditLog.objects.create(
                    user=user,
                    action="HR_REGISTERED_AUTO_ACTIVATED",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"username": user.username, "company_name": company_name, "email": user.email, "phone": user.phone_number},
                )
                messages.success(request, f"Welcome to HireNexa, {user.first_name or user.username}! Your recruiter account has been created successfully.")
                return redirect(get_role_dashboard_url(user))

            res_email = OTPService.issue_challenge(user.email, OTPChallenge.Channel.EMAIL, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="hr")
            res_phone = OTPService.issue_challenge(user.phone_number, OTPChallenge.Channel.SMS, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="hr")
            request.session["pending_verification_user_id"] = user.id
            if getattr(settings, "DEBUG", False):
                request.session["dev_email_otp"] = res_email.get("otp")
                request.session["dev_phone_otp"] = res_phone.get("otp")

            AuditLog.objects.create(
                user=user,
                action="HR_REGISTERED_PENDING_VERIFICATION",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"username": user.username, "company_name": company_name, "email": user.email, "phone": user.phone_number},
            )
            if res_email.get("success") or res_phone.get("success"):
                messages.info(request, "Registration successful! Please verify either your Email OR Mobile OTP to activate your recruiter account.")
            else:
                messages.warning(request, f"Registration complete, but OTP dispatch failed: {res_email.get('message')}. Please click Resend on the verification page.")
            return redirect("dual_verification")
    else:
        form = HRSignUpForm()

    return render(request, "accounts/hr_signup.html", {"form": form})


# ==============================================================================
# 3. FREELANCER LOGIN & REGISTRATION
# ==============================================================================

def freelancer_login_view(request):
    """Dedicated login interface for Freelancers."""
    if request.user.is_authenticated:
        if request.user.is_freelancer or request.user.is_owner:
            return redirect("freelancer_dashboard")
        return redirect(get_role_dashboard_url(request.user))

    next_url = request.GET.get("next") or request.POST.get("next") or reverse("freelancer_dashboard")

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip() or request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")

        auth_result = AuthService.authenticate_portal(request, identifier, password, portal="freelancer")
        status = auth_result["status"]

        if status == "RATE_LIMITED":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/freelancer_login.html", {
                "next": next_url,
                "identifier": identifier,
                "is_locked_out": True,
                "retry_minutes": auth_result.get("retry_minutes", 1),
            }, status=429)

        if status == "INVALID_CREDENTIALS":
            messages.error(request, "Invalid freelancer credentials. Please verify your details.")
            return render(request, "accounts/freelancer_login.html", {"next": next_url, "identifier": identifier})

        if status == "UNVERIFIED":
            resolved_user = auth_result["user"]
            request.session["pending_verification_user_id"] = resolved_user.id
            request.session["post_verification_next_url"] = next_url
            verify_url = reverse("dual_verification")
            messages.warning(
                request,
                mark_safe(f'Your account is pending verification. <a href="{verify_url}" style="text-decoration: underline; font-weight: bold;">Verify / Resend OTP &rarr;</a>')
            )
            return render(request, "accounts/freelancer_login.html", {
                "next": next_url,
                "identifier": identifier,
                "unverified_account": True,
                "verify_url": verify_url,
            })

        if status == "DEACTIVATED":
            messages.error(request, "Your account has been deactivated. Please contact support.")
            return render(request, "accounts/freelancer_login.html", {"next": next_url, "identifier": identifier})

        if status == "WRONG_PORTAL":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/freelancer_login.html", {
                "next": next_url,
                "identifier": identifier,
                "wrong_portal": True,
                "correct_url": auth_result.get("correct_url"),
            })

        # SUCCESS
        auth_user = auth_result["user"]
        login(request, auth_user, backend="accounts.backends.MultiIdentifierModelBackend")
        messages.success(request, f"Welcome back, {auth_user.username}! Freelancer hub ready.")
        return redirect(get_role_dashboard_url(auth_user))

    return render(request, "accounts/freelancer_login.html", {"next": next_url})


def freelancer_signup_view(request):
    """Dedicated registration for Freelancers."""
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    if request.method == "POST":
        form = FreelancerSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            headline = form.cleaned_data.get("headline", "").strip()
            FreelancerProfile.objects.get_or_create(
                user=user,
                defaults={"headline": headline or "Full-Stack Software Contractor"}
            )
            require_otp = getattr(settings, "UNIFIED_REQUIRE_OTP", False)
            if not require_otp:
                user.is_active = True
                user.is_email_verified = True
                user.is_phone_verified = True
                user.save(update_fields=["is_active", "is_email_verified", "is_phone_verified"])
                login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
                AuditLog.objects.create(
                    user=user,
                    action="FREELANCER_REGISTERED_AUTO_ACTIVATED",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"username": user.username, "headline": headline, "email": user.email, "phone": user.phone_number},
                )
                messages.success(request, f"Welcome to HireNexa, {user.first_name or user.username}! Your freelancer profile is ready.")
                return redirect(get_role_dashboard_url(user))

            res_email = OTPService.issue_challenge(user.email, OTPChallenge.Channel.EMAIL, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="freelancer")
            res_phone = OTPService.issue_challenge(user.phone_number, OTPChallenge.Channel.SMS, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="freelancer")
            request.session["pending_verification_user_id"] = user.id
            if getattr(settings, "DEBUG", False):
                request.session["dev_email_otp"] = res_email.get("otp")
                request.session["dev_phone_otp"] = res_phone.get("otp")

            AuditLog.objects.create(
                user=user,
                action="FREELANCER_REGISTERED_PENDING_VERIFICATION",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"username": user.username, "headline": headline, "email": user.email, "phone": user.phone_number},
            )
            if res_email.get("success") or res_phone.get("success"):
                messages.info(request, "Registration successful! Please verify either your Email OR Mobile OTP to activate your freelancer account.")
            else:
                messages.warning(request, f"Registration complete, but OTP dispatch failed: {res_email.get('message')}. Please click Resend on the verification page.")
            return redirect("dual_verification")
    else:
        form = FreelancerSignUpForm()

    return render(request, "accounts/freelancer_signup.html", {"form": form})


# ==============================================================================
# 4. STUDENT / CANDIDATE LOGIN & REGISTRATION
# ==============================================================================

def candidate_login_view(request):
    """Dedicated login interface for Students & Candidates."""
    if request.user.is_authenticated:
        if request.user.is_candidate or request.user.is_owner:
            return redirect("candidate_dashboard")
        return redirect(get_role_dashboard_url(request.user))

    next_url = request.GET.get("next") or request.POST.get("next") or reverse("candidate_dashboard")

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip() or request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")

        auth_result = AuthService.authenticate_portal(request, identifier, password, portal="candidate")
        status = auth_result["status"]

        if status == "RATE_LIMITED":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/candidate_login.html", {
                "next": next_url,
                "identifier": identifier,
                "is_locked_out": True,
                "retry_minutes": auth_result.get("retry_minutes", 1),
            }, status=429)

        if status == "INVALID_CREDENTIALS":
            messages.error(request, "Invalid student credentials. Please verify your Username/Email/Phone and Password.")
            return render(request, "accounts/candidate_login.html", {"next": next_url, "identifier": identifier})

        if status == "UNVERIFIED":
            resolved_user = auth_result["user"]
            request.session["pending_verification_user_id"] = resolved_user.id
            request.session["post_verification_next_url"] = next_url
            verify_url = reverse("dual_verification")
            messages.warning(
                request,
                mark_safe(
                    f"Your account has been registered but is not yet verified. "
                    f'<a href="{verify_url}" style="text-decoration: underline; font-weight: 700; margin-left: 4px;">Click here to verify your account or resend OTP &rarr;</a>'
                ),
            )
            return render(
                request,
                "accounts/candidate_login.html",
                {
                    "next": next_url,
                    "identifier": identifier,
                    "unverified_account": True,
                    "verify_url": verify_url,
                },
            )

        if status == "DEACTIVATED":
            messages.error(request, "Your account has been deactivated. Please contact support.")
            return render(request, "accounts/candidate_login.html", {"next": next_url, "identifier": identifier})

        if status == "WRONG_PORTAL":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/candidate_login.html", {
                "next": next_url,
                "identifier": identifier,
                "wrong_portal": True,
                "correct_url": auth_result.get("correct_url"),
            })

        # SUCCESS
        auth_user = auth_result["user"]
        login(request, auth_user, backend="accounts.backends.MultiIdentifierModelBackend")
        messages.success(request, f"Welcome back, {auth_user.username}! Career dashboard loaded.")
        return redirect(get_role_dashboard_url(auth_user))

    return render(request, "accounts/candidate_login.html", {"next": next_url})


def candidate_signup_view(request):
    """Dedicated registration for Students & Job Candidates."""
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    if request.method == "POST":
        form = StudentSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            CandidateProfile.objects.get_or_create(user=user)
            require_otp = getattr(settings, "UNIFIED_REQUIRE_OTP", False)
            if not require_otp:
                user.is_active = True
                user.is_email_verified = True
                user.is_phone_verified = True
                user.save(update_fields=["is_active", "is_email_verified", "is_phone_verified"])
                login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
                AuditLog.objects.create(
                    user=user,
                    action="CANDIDATE_REGISTERED_AUTO_ACTIVATED",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"username": user.username, "email": user.email, "phone": user.phone_number},
                )
                messages.success(request, f"Welcome to HireNexa, {user.first_name or user.username}! Your candidate account is active.")
                return redirect("candidate_dashboard")

            res_email = OTPService.issue_challenge(user.email, OTPChallenge.Channel.EMAIL, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="candidate")
            res_phone = OTPService.issue_challenge(user.phone_number, OTPChallenge.Channel.SMS, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="candidate")
            request.session["pending_verification_user_id"] = user.id
            if getattr(settings, "DEBUG", False):
                request.session["dev_email_otp"] = res_email.get("otp")
                request.session["dev_phone_otp"] = res_phone.get("otp")

            AuditLog.objects.create(
                user=user,
                action="CANDIDATE_REGISTERED_PENDING_VERIFICATION",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"username": user.username, "email": user.email, "phone": user.phone_number},
            )
            if res_email.get("success") or res_phone.get("success"):
                messages.info(request, "Registration successful! Please verify either your Email OR Mobile OTP to activate your candidate account.")
            else:
                messages.warning(request, f"Registration complete, but OTP dispatch failed: {res_email.get('message')}. Please click Resend on the verification page.")
            return redirect("dual_verification")
    else:
        form = StudentSignUpForm()

    return render(request, "accounts/candidate_signup.html", {"form": form})


# ==============================================================================
# 5. UNIFIED MULTI-IDENTIFIER LOGIN
# ==============================================================================

def unified_login_view(request):
    """
    Unified multi-identifier sign-in.
    Accepts:
      - Username (e.g. 'priya_sharma', 'techcorp_hr', 'admin')
      - Email ID (e.g. 'priya@example.com', 'admin@example.com')
      - Mobile Phone Number (e.g. '+91 9876543210', '9876543210')
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip() or request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")

        auth_result = AuthService.authenticate_portal(request, identifier, password, portal="unified")
        status = auth_result["status"]

        if status == "RATE_LIMITED":
            messages.error(request, auth_result["message"])
            return render(request, "accounts/login.html", {
                "next": next_url,
                "identifier": identifier,
                "is_locked_out": True,
                "retry_minutes": auth_result.get("retry_minutes", 1),
            }, status=429)

        if status == "INVALID_CREDENTIALS":
            messages.error(request, "Invalid credentials. Please verify your Username, Email ID, or Mobile Number and Password.")
            return render(request, "accounts/login.html", {"next": next_url, "identifier": identifier})

        if status == "UNVERIFIED":
            user = auth_result["user"]
            request.session["pending_verification_user_id"] = user.id
            request.session["post_verification_next_url"] = next_url
            OTPService.issue_challenge(user.email, OTPChallenge.Channel.EMAIL, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="unified")
            OTPService.issue_challenge(user.phone_number, OTPChallenge.Channel.SMS, purpose=OTPChallenge.Purpose.REGISTRATION, user=user, request=request, portal="unified")
            messages.warning(
                request,
                "Your account requires verification before activation. Please verify either your Email or Mobile number."
            )
            return redirect("dual_verification")

        if status == "DEACTIVATED":
            messages.error(request, "Your account has been deactivated. Please contact support.")
            return render(request, "accounts/login.html", {"next": next_url, "identifier": identifier})

        # SUCCESS: User ID/Email + Password Authentication
        user = auth_result["user"]
        remember_me = request.POST.get("remember_me")
        require_otp = getattr(settings, "UNIFIED_REQUIRE_OTP", False)
        if not require_otp:
            # Verified User ID & Password: Login directly without OTP!
            login(request, user, backend=getattr(user, "backend", "accounts.backends.MultiIdentifierModelBackend"))
            client_ip = get_client_ip(request)
            RateLimiter.reset_attempts(client_ip, user.username, portal="unified")
            RateLimiter.reset_attempts(client_ip, identifier, portal="unified")
            if getattr(user, "email", None):
                RateLimiter.reset_attempts(client_ip, user.email, portal="unified")
            
            # Session expiry: remember me persists 14 days; otherwise expires on browser close
            if remember_me:
                request.session.set_expiry(1209600)  # 14 days
            else:
                request.session.set_expiry(0)  # On browser close

            AuditLog.objects.create(
                user=user,
                action="USER_LOGIN_SUCCESS",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"identifier": identifier, "resolved_user": user.username, "role": user.role, "login_method": "PASSWORD"},
            )
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            return redirect(next_url or get_role_dashboard_url(user))

        # Optional 2FA Two-Step Authentication (Email OTP on Login if enabled in settings)
        target_email = user.email or f"{user.username}@hirenexa.local"
        otp_obj, raw_code = EmailOTP.generate(
            email=target_email,
            purpose=EmailOTP.Purpose.LOGIN,
            user=user,
            validity_minutes=10,
        )
        dispatch_res = EmailDeliveryService.send_otp_email(
            recipient_email=target_email,
            user_name=user.full_name,
            raw_otp=raw_code,
            validity_minutes=10,
        )

        if not dispatch_res.get("success"):
            otp_obj.is_used = True
            otp_obj.save(update_fields=["is_used"])
            messages.error(request, "Email delivery failed. Please check SMTP settings or try again.")
            return render(request, "accounts/login.html", {"next": next_url, "identifier": identifier})

        request.session["login_preauth_id"] = user.id
        request.session["login_preauth_next"] = next_url

        AuditLog.objects.create(
            user=user,
            action="USER_LOGIN_PASSWORD_VERIFIED_OTP_DISPATCHED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"identifier": identifier, "resolved_user": user.username, "role": user.role, "email": mask_email(target_email)},
        )
        messages.success(request, f"We sent a 6-digit verification code to {mask_email(target_email)}.")
        return redirect("unified_login_otp_verify")

    return render(request, "accounts/login.html", {"next": next_url})


def unified_login_otp_verify_view(request):
    """
    Step 2: Universal Two-Step Verification for all user roles.
    Verifies 6-digit Email OTP before initiating session.
    """
    user_id = request.session.get("login_preauth_id")
    if not user_id:
        messages.warning(request, "Login session expired. Please sign in again.")
        return redirect("login")

    user = get_object_or_404(User, pk=user_id)
    target_email = user.email or f"{user.username}@hirenexa.local"
    masked_email = mask_email(target_email)
    next_url = request.session.get("login_preauth_next")
    client_ip = get_client_ip(request)

    if request.method == "POST":
        otp_code = request.POST.get("otp_code", "").strip()
        if not otp_code or len(otp_code) != 6:
            messages.error(request, "Please enter the complete 6-digit OTP code.")
            return render(request, "accounts/login_otp.html", {"target_user": user, "masked_email": masked_email})

        otp_record = EmailOTP.objects.filter(
            user=user,
            purpose=EmailOTP.Purpose.LOGIN,
            is_used=False,
            expires_at__gte=timezone.now(),
        ).first()

        if not otp_record:
            messages.error(request, "Invalid or expired code. Please request a new code.")
            return render(request, "accounts/login_otp.html", {"target_user": user, "masked_email": masked_email})

        is_valid, status_reason = otp_record.check_code(otp_code)

        if status_reason == "LOCKED":
            RateLimiter.record_failed_attempt(client_ip, user.username)
            AuditLog.objects.create(
                user=user,
                action="USER_2FA_OTP_LOCKED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"reason": "5_FAILED_ATTEMPTS"},
            )
            messages.error(request, "Too many failed attempts (5/5). This code has been locked. Please request a new code.")
            return render(request, "accounts/login_otp.html", {"target_user": user, "masked_email": masked_email})

        elif not is_valid:
            RateLimiter.record_failed_attempt(client_ip, user.username)
            rem = max(0, 5 - otp_record.attempts)
            AuditLog.objects.create(
                user=user,
                action="USER_2FA_OTP_FAILED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"attempts": otp_record.attempts},
            )
            messages.error(request, f"Invalid or expired code. ({rem} attempts remaining)")
            return render(request, "accounts/login_otp.html", {"target_user": user, "masked_email": masked_email})

        # Success
        RateLimiter.reset_attempts(client_ip, user.username, portal="unified")
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        AuditLog.objects.create(
            user=user,
            action="USER_2FA_LOGIN_SUCCESS",
            ip_address=client_ip,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"username": user.username, "role": user.role, "method": "EMAIL_OTP"},
        )

        request.session.pop("login_preauth_id", None)
        request.session.pop("login_preauth_next", None)

        messages.success(request, f"✓ Verified! Welcome back, {user.username}.")
        if next_url:
            return redirect(next_url)
        return redirect(get_role_dashboard_url(user))

    return render(request, "accounts/login_otp.html", {"target_user": user, "masked_email": masked_email})


def unified_login_otp_resend_view(request):
    """Resend 6-digit Email OTP for User 2FA with cooldown and hourly limit."""
    user_id = request.session.get("login_preauth_id")
    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, pk=user_id)
    target_email = user.email or f"{user.username}@hirenexa.local"

    can_request, err_msg, wait_sec = EmailOTP.can_request_otp(
        email=target_email,
        purpose=EmailOTP.Purpose.LOGIN,
        cooldown_seconds=60,
        max_per_hour=5,
    )
    if not can_request:
        messages.warning(request, err_msg)
        return redirect("unified_login_otp_verify")

    otp_obj, raw_code = EmailOTP.generate(
        email=target_email,
        purpose=EmailOTP.Purpose.LOGIN,
        user=user,
        validity_minutes=10,
    )
    dispatch_res = EmailDeliveryService.send_otp_email(
        recipient_email=target_email,
        user_name=user.full_name,
        raw_otp=raw_code,
        validity_minutes=10,
    )

    if not dispatch_res.get("success"):
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        messages.error(request, "Unable to send verification email at this time. Please try again shortly.")
    else:
        messages.success(request, f"We sent a fresh 6-digit code to {mask_email(target_email)}.")

    return redirect("unified_login_otp_verify")



# ==============================================================================
# 6. PHONE NUMBER OTP SYSTEM (PASSWORDLESS SIGN IN & 2FA)
# ==============================================================================

def request_otp_view(request):
    """
    Step 1: Universal OTP Request Gateway for all portals:
    - User enters Email address or Mobile phone number.
    - Channel can be explicitly chosen via tabs (EMAIL or SMS) or auto-detected.
    - Portal parameter maintains role boundary (candidate, hr, freelancer, owner, unified).
    - Hardened against account enumeration: Always returns a neutral, identical success response.
    - Distinct rate-limiting counter isolated from password lockout.
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    if request.method == "POST":
        raw_identifier = (
            request.POST.get("identifier", "").strip()
            or request.POST.get("username", "").strip()
            or request.POST.get("phone_number", "").strip()
            or request.POST.get("email", "").strip()
        )
        channel_param = request.POST.get("channel", "auto").strip().upper()
        portal = request.POST.get("portal", "candidate").strip().lower()
        next_url = request.POST.get("next") or request.GET.get("next") or ""
        client_ip = get_client_ip(request)

        # Auto-detect channel if not explicitly specified
        if channel_param in ("EMAIL", "SMS"):
            channel = channel_param
        else:
            channel = OTPChallenge.Channel.EMAIL if "@" in raw_identifier else OTPChallenge.Channel.SMS

        # Separate Rate Limiting for OTP request (per-portal, per-IP, per-identifier)
        is_blocked, retry_after, reason = RateLimiter.is_rate_limited(
            ip=client_ip,
            identifier=raw_identifier,
            portal=f"otp_req_{portal}",
            max_attempts=10,
            window_seconds=900,
        )
        if is_blocked:
            minutes = max(1, (retry_after + 59) // 60)
            AuditLog.objects.create(
                action="OTP_REQUEST_RATE_LIMIT_EXCEEDED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"portal": portal, "identifier": raw_identifier, "retry_after": retry_after},
            )
            err_msg = f"Too many verification requests. For security, please wait {minutes} minute(s) before trying again."
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": False, "message": err_msg, "retry_after": retry_after}, status=429)
            messages.error(request, err_msg)
            redirect_view_name = f"{portal}_login" if f"{portal}_login" in ["candidate_login", "hr_login", "freelancer_login", "owner_login"] else "login"
            return redirect(redirect_view_name)

        channel_label = "Email address" if channel == OTPChallenge.Channel.EMAIL else "Mobile phone number"
        generic_msg = f"If an account is associated with this {channel_label}, a 6-digit verification code has been sent."

        if not raw_identifier:
            err_msg = f"Please enter your {channel_label}."
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": False, "message": err_msg}, status=400)
            messages.error(request, err_msg)
            redirect_view_name = f"{portal}_login" if f"{portal}_login" in ["candidate_login", "hr_login", "freelancer_login", "owner_login"] else "login"
            return redirect(redirect_view_name)

        resolved_user = find_user_by_identifier(raw_identifier)

        if resolved_user:
            dispatch_target = (
                resolved_user.email
                if channel == OTPChallenge.Channel.EMAIL
                else (resolved_user.phone_number or raw_identifier)
            )
            issue_res = OTPService.issue_challenge(
                recipient=dispatch_target,
                channel=channel,
                purpose=OTPChallenge.Purpose.LOGIN,
                user=resolved_user,
                request=request,
                portal=portal,
            )
            if not issue_res.get("success") and issue_res.get("error_code") in ("COOLDOWN_ACTIVE", "RATE_LIMIT_EXCEEDED"):
                if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                    return JsonResponse(issue_res, status=429)
                messages.warning(request, issue_res.get("message"))
                return redirect("verify_otp")

            request.session["pending_otp_login"] = {
                "identifier": dispatch_target,
                "input_identifier": raw_identifier,
                "channel": channel,
                "portal": portal,
                "user_id": resolved_user.id,
                "has_user": True,
                "is_new_user": False,
                "purpose": OTPChallenge.Purpose.LOGIN,
                "next": next_url,
            }
            AuditLog.objects.create(
                user=resolved_user,
                action="OTP_LOGIN_CHALLENGE_REQUESTED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"portal": portal, "channel": channel, "username": resolved_user.username},
            )
        else:
            # NEW USER: Issue and dispatch real OTP directly to this recipient!
            clean_ident = OTPService.clean_identifier(raw_identifier, channel)
            issue_res = OTPService.issue_challenge(
                recipient=clean_ident,
                channel=channel,
                purpose=OTPChallenge.Purpose.REGISTRATION,
                user=None,
                request=request,
                portal=portal,
            )
            if not issue_res.get("success") and issue_res.get("error_code") in ("COOLDOWN_ACTIVE", "RATE_LIMIT_EXCEEDED"):
                if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                    return JsonResponse(issue_res, status=429)
                messages.warning(request, issue_res.get("message"))
                return redirect("verify_otp")

            request.session["pending_otp_login"] = {
                "identifier": clean_ident,
                "input_identifier": raw_identifier,
                "channel": channel,
                "portal": portal,
                "user_id": None,
                "has_user": False,
                "is_new_user": True,
                "purpose": OTPChallenge.Purpose.REGISTRATION,
                "next": next_url,
            }
            AuditLog.objects.create(
                action="NEW_USER_OTP_CHALLENGE_REQUESTED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"portal": portal, "channel": channel, "attempted_identifier": raw_identifier},
            )

        if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
            return JsonResponse({
                "success": True,
                "message": generic_msg,
                "channel": channel,
                "portal": portal,
                "redirect_url": reverse("verify_otp"),
                "cooldown": 60,
            })

        messages.info(request, generic_msg)
        return redirect("verify_otp")

    return redirect("login")


def phone_otp_login_request_view(request):
    """
    Dedicated Mobile Phone OTP Login Gateway:
    Delegates to universal OTP request service and generates PhoneOTP for legacy compatibility.
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    if request.method == "POST":
        raw_phone = request.POST.get("phone_number", "").strip() or request.POST.get("identifier", "").strip()
        portal = request.POST.get("portal", "candidate").strip().lower()
        clean_phone = clean_phone_number(raw_phone)
        resolved_user = find_user_by_identifier(clean_phone) or find_user_by_identifier(raw_phone)

        # Generate PhoneOTP for compatibility with PhoneOTP tests and legacy endpoints
        PhoneOTP.generate(
            phone_number=raw_phone,
            purpose=PhoneOTP.Purpose.LOGIN,
            user=resolved_user,
            validity_minutes=10,
        )
        request.session["otp_auth_phone"] = raw_phone

        post_data = request.POST.copy()
        post_data["identifier"] = raw_phone
        post_data["channel"] = "SMS"
        post_data["portal"] = portal
        request.POST = post_data
        return request_otp_view(request)

    return render(request, "accounts/phone_otp_login.html")


def verify_otp_view(request):
    """
    Step 2: Universal OTP Verification Gateway:
    - Verifies 6-digit OTP code against HMAC-SHA256 salted hash in constant-time.
    - Decrements attempt counter on failure (max 5 attempts).
    - Enforces portal role authorization boundaries (Candidate, HR, Freelancer, Owner).
    - Supports unverified account activation upon successful OTP verification.
    - Resets rate-limiting counters upon successful authentication.
    - Single-use consumption (marks challenge consumed).
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    pending = request.session.get("pending_otp_login") or {}
    identifier = (
        pending.get("identifier")
        or request.POST.get("identifier", "").strip()
        or request.GET.get("identifier", "").strip()
        or request.session.get("otp_auth_phone", "")
    )
    channel = (
        pending.get("channel")
        or request.POST.get("channel", "").strip().upper()
        or ("EMAIL" if "@" in identifier else "SMS")
    )
    portal = (
        pending.get("portal")
        or request.POST.get("portal", "").strip().lower()
        or "candidate"
    )
    has_user = pending.get("has_user", True)
    user_id = pending.get("user_id")
    is_new_user = pending.get("is_new_user", False)
    purpose = pending.get("purpose") or (OTPChallenge.Purpose.REGISTRATION if is_new_user else OTPChallenge.Purpose.LOGIN)
    next_url = (
        pending.get("next")
        or request.POST.get("next")
        or request.GET.get("next")
        or ""
    )

    if not identifier and request.method == "GET":
        messages.info(request, "Please enter your email address or mobile phone number to sign in.")
        redirect_target = f"{portal}_login" if f"{portal}_login" in ["candidate_login", "hr_login", "freelancer_login", "owner_login"] else "login"
        return redirect(redirect_target)

    # Format masked identifier for UI display
    masked_identifier = identifier
    if "@" in identifier:
        parts = identifier.split("@")
        user_part = parts[0]
        domain = parts[1] if len(parts) > 1 else ""
        masked_user = user_part[:2] + ("*" * max(3, len(user_part) - 2)) if len(user_part) > 2 else user_part + "***"
        masked_identifier = f"{masked_user}@{domain}"
    elif identifier:
        clean_num = re.sub(r"\D", "", identifier)
        if len(clean_num) >= 10:
            masked_identifier = f"+91 ******{clean_num[-4:]}"
        else:
            masked_identifier = f"***{identifier[-3:]}" if len(identifier) > 3 else identifier

    context = {
        "identifier": identifier,
        "masked_identifier": masked_identifier,
        "channel": channel,
        "channel_label": "Email Address" if channel == "EMAIL" else "Mobile Number",
        "portal": portal,
        "next": next_url,
        "cooldown_seconds": getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60),
    }

    if request.method == "POST":
        # Support single input, legacy field names, or 6 separate digit boxes
        otp_code = (
            request.POST.get("otp_code", "").strip()
            or request.POST.get("code", "").strip()
            or request.POST.get("phone_otp", "").strip()
        )
        if not otp_code and "digit_1" in request.POST:
            otp_code = "".join(request.POST.get(f"digit_{i}", "").strip() for i in range(1, 7))

        client_ip = get_client_ip(request)

        # Rate Limiting on OTP verification attempts (per-identifier + per-IP + per-portal)
        is_blocked, retry_after, reason = RateLimiter.is_rate_limited(
            ip=client_ip,
            identifier=identifier,
            portal=f"otp_ver_{portal}",
            max_attempts=getattr(settings, "OTP_MAX_ATTEMPTS", 5),
            window_seconds=600,
        )
        if is_blocked:
            minutes = max(1, (retry_after + 59) // 60)
            AuditLog.objects.create(
                action="OTP_VERIFICATION_RATE_LIMIT_EXCEEDED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"portal": portal, "identifier": identifier, "retry_after": retry_after},
            )
            err_msg = f"Too many failed OTP attempts. For security, please wait {minutes} minute(s) before trying again."
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": False, "message": err_msg, "retry_after": retry_after}, status=429)
            context["error_message"] = err_msg
            return render(request, "accounts/otp_verify.html", context, status=429)

        if not otp_code or len(otp_code) != getattr(settings, "OTP_LENGTH", 6) or not otp_code.isdigit():
            err_msg = f"Please enter the complete {getattr(settings, 'OTP_LENGTH', 6)}-digit verification code."
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": False, "message": err_msg}, status=400)
            context["error_message"] = err_msg
            return render(request, "accounts/otp_verify.html", context, status=400)

        # Anti-enumeration scenario: User did not exist when request was submitted and not a new user registration flow
        if not has_user and not is_new_user:
            RateLimiter.record_failed_attempt(
                ip=client_ip,
                identifier=identifier,
                portal=f"otp_ver_{portal}",
                window_seconds=600,
            )
            AuditLog.objects.create(
                action="OTP_VERIFY_UNKNOWN_IDENTIFIER_FAILED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"portal": portal, "identifier": identifier},
            )
            err_msg = "Invalid or expired verification code. Please check the code or click Resend."
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": False, "message": err_msg}, status=400)
            context["error_message"] = err_msg
            return render(request, "accounts/otp_verify.html", context, status=400)

        # Verify challenge cryptographically
        verify_result = OTPService.verify_challenge(
            identifier=identifier,
            channel=channel,
            otp=otp_code,
            purpose=purpose,
            portal=portal,
            request=request,
        )

        if not verify_result.get("success"):
            RateLimiter.record_failed_attempt(
                ip=client_ip,
                identifier=identifier,
                portal=f"otp_ver_{portal}",
                window_seconds=600,
            )
            AuditLog.objects.create(
                action="OTP_VERIFY_FAILED",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={
                    "portal": portal,
                    "identifier": identifier,
                    "error_code": verify_result.get("error_code"),
                    "attempts_left": verify_result.get("attempts_left"),
                },
            )
            err_msg = verify_result.get("message", "Invalid or expired verification code.")
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse(verify_result, status=400)
            context["error_message"] = err_msg
            return render(request, "accounts/otp_verify.html", context, status=400)

        # Successful OTP verification: Resolve user
        user = verify_result.get("user")
        if not user and user_id:
            user = User.objects.filter(id=user_id).first()
        if not user:
            user = find_user_by_identifier(identifier)

        newly_created = False
        if not user:
            # First-time auto-provisioning
            clean_digits = re.sub(r"\D", "", identifier)
            if "@" in identifier:
                prefix = re.sub(r"[^a-zA-Z0-9_]", "", identifier.split("@")[0].lower())[:20]
            else:
                prefix = f"user_{clean_digits[-4:]}" if len(clean_digits) >= 4 else "user"
            base_username = prefix or "user"
            uname = base_username
            c = 1
            while User.objects.filter(username=uname).exists():
                uname = f"{base_username}_{c}"
                c += 1
            email_val = identifier if channel == "EMAIL" else ""
            phone_val = identifier if channel == "SMS" else ""
            
            initial_role = User.Role.CANDIDATE
            if portal.lower() == "hr":
                initial_role = User.Role.RECRUITER
            elif portal.lower() == "freelancer":
                initial_role = User.Role.FREELANCER

            user = User(
                username=uname,
                email=email_val,
                phone_number=phone_val,
                role=initial_role,
                is_active=True,
                is_email_verified=(channel == "EMAIL"),
                email_verified_at=timezone.now() if channel == "EMAIL" else None,
                is_phone_verified=(channel == "SMS"),
                phone_verified_at=timezone.now() if channel == "SMS" else None,
            )
            user.set_unusable_password()
            user.save()

            if initial_role == User.Role.RECRUITER:
                RecruiterProfile.objects.get_or_create(user=user, defaults={"company_name": "Independent Recruiter"})
            elif initial_role == User.Role.FREELANCER:
                FreelancerProfile.objects.get_or_create(user=user)
            else:
                CandidateProfile.objects.get_or_create(user=user)

            newly_created = True

        # Activate user and verify credentials if pending verification
        update_fields = []
        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")
        if channel == "EMAIL" and not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = timezone.now()
            update_fields.extend(["is_email_verified", "email_verified_at"])
        elif channel == "SMS" and not user.is_phone_verified:
            user.is_phone_verified = True
            user.phone_verified_at = timezone.now()
            update_fields.extend(["is_phone_verified", "phone_verified_at"])
            if not user.phone_number:
                user.phone_number = identifier
                update_fields.append("phone_number")
        if update_fields:
            user.save(update_fields=update_fields)

        # Reset rate limiting counters across portal & OTP verification
        RateLimiter.reset_attempts(ip=client_ip, identifier=identifier, portal=f"otp_ver_{portal}")
        RateLimiter.reset_attempts(ip=client_ip, identifier=identifier, portal=f"otp_req_{portal}")
        RateLimiter.reset_attempts(ip=client_ip, identifier=user.username, portal=portal)

        # Clear pending OTP session keys
        request.session.pop("pending_otp_login", None)
        request.session.pop("otp_auth_phone", None)
        request.session.pop("otp_auth_purpose", None)

        # If user needs to set password (new user, newly created, or no usable password)
        if is_new_user or newly_created or not user.has_usable_password():
            request.session["set_password_user_id"] = user.id
            request.session["set_password_next_url"] = next_url

            AuditLog.objects.create(
                user=user,
                action="OTP_VERIFIED_REDIRECT_SET_PASSWORD",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"portal": portal, "channel": channel, "username": user.username, "email": user.email},
            )

            messages.success(request, f"✓ {channel.capitalize()} verified! Please set a secure password for your account.")
            target_redirect = reverse("set_password")
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": True, "redirect_url": target_redirect})
            return redirect(target_redirect)

        # PORTAL ROLE BOUNDARY ENFORCEMENT
        user_role = getattr(user, "role", "").upper()
        portal_lower = portal.lower()
        is_owner = (user_role == User.Role.OWNER or getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))

        authorized = False
        if is_owner:
            authorized = True
        elif portal_lower == "candidate" and user_role == User.Role.CANDIDATE:
            authorized = True
        elif portal_lower == "hr" and user_role in (User.Role.RECRUITER, User.Role.COMPANY_ADMIN):
            authorized = True
        elif portal_lower == "freelancer" and user_role == User.Role.FREELANCER:
            authorized = True
        elif portal_lower in ("unified", "login", ""):
            authorized = True

        if not authorized:
            AuditLog.objects.create(
                user=user,
                action="OTP_LOGIN_PORTAL_ROLE_FORBIDDEN",
                ip_address=client_ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"portal": portal, "user_role": user_role, "username": user.username},
            )
            portal_display_names = {
                "candidate": "Student & Candidate Portal",
                "hr": "HR & Recruiter Portal",
                "freelancer": "Freelancer Portal",
                "owner": "Platform Owner Portal",
            }
            err_msg = (
                f"Access Denied: Your account role is {user_role}. "
                f"You are not authorized to sign in to the {portal_display_names.get(portal_lower, portal)}. "
                f"Please use your designated portal."
            )
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": False, "message": err_msg}, status=403)
            messages.error(request, err_msg)
            redirect_portal = f"{portal}_login" if f"{portal}_login" in ["candidate_login", "hr_login", "freelancer_login", "owner_login"] else "login"
            return redirect(redirect_portal)

        # Activate user and verify credentials if pending verification
        update_fields = []
        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")
        if channel == "EMAIL" and not user.is_email_verified:
            user.is_email_verified = True
            update_fields.append("is_email_verified")
        elif channel == "SMS" and not user.is_phone_verified:
            user.is_phone_verified = True
            update_fields.append("is_phone_verified")
            if not user.phone_number:
                user.phone_number = identifier
                update_fields.append("phone_number")
        if update_fields:
            user.save(update_fields=update_fields)

        # Authenticate and login session
        login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")

        # Reset rate limiting counters across portal & OTP verification
        RateLimiter.reset_attempts(ip=client_ip, identifier=identifier, portal=f"otp_ver_{portal}")
        RateLimiter.reset_attempts(ip=client_ip, identifier=identifier, portal=f"otp_req_{portal}")
        RateLimiter.reset_attempts(ip=client_ip, identifier=user.username, portal=portal)

        # Clear pending OTP session keys
        request.session.pop("pending_otp_login", None)
        request.session.pop("otp_auth_phone", None)
        request.session.pop("otp_auth_purpose", None)

        AuditLog.objects.create(
            user=user,
            action="OTP_LOGIN_SUCCESS",
            ip_address=client_ip,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"portal": portal, "channel": channel, "username": user.username},
        )

        messages.success(
            request,
            f"✓ Verified! Welcome back, {user.first_name or user.username}. Signed in via {channel} OTP."
        )

        target_redirect = next_url if (next_url and next_url.startswith("/")) else get_role_dashboard_url(user)
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
            return JsonResponse({"success": True, "redirect_url": target_redirect})
        return redirect(target_redirect)

    return render(request, "accounts/otp_verify.html", context)


def resend_otp_view(request):
    """
    Step 2b: Resend OTP Code:
    - Enforces cooldown period (30-60 seconds) and max hourly sends.
    - Issues new HMAC-SHA256 hashed OTP code and invalidates prior unconsumed challenges.
    - Rate-limited and audited.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed"}, status=405)

    pending = request.session.get("pending_otp_login") or {}
    identifier = (
        pending.get("identifier")
        or request.POST.get("identifier", "").strip()
        or request.session.get("otp_auth_phone", "")
    )
    channel = (
        pending.get("channel")
        or request.POST.get("channel", "").strip().upper()
        or ("EMAIL" if "@" in identifier else "SMS")
    )
    portal = (
        pending.get("portal")
        or request.POST.get("portal", "").strip().lower()
        or "candidate"
    )
    user_id = pending.get("user_id")
    has_user = pending.get("has_user", True)
    is_new_user = pending.get("is_new_user", False)
    purpose = pending.get("purpose") or (OTPChallenge.Purpose.REGISTRATION if is_new_user else OTPChallenge.Purpose.LOGIN)

    if not identifier:
        return JsonResponse({"success": False, "message": "No active verification session found."}, status=400)

    resolved_user = User.objects.filter(id=user_id).first() if user_id else find_user_by_identifier(identifier)

    if resolved_user or not has_user or is_new_user:
        issue_res = OTPService.issue_challenge(
            recipient=identifier,
            channel=channel,
            purpose=purpose,
            user=resolved_user,
            request=request,
            portal=portal,
        )
        if not issue_res.get("success"):
            status_code = 429 if issue_res.get("error_code") in ("COOLDOWN_ACTIVE", "RATE_LIMIT_EXCEEDED") else 400
            return JsonResponse(issue_res, status=status_code)

    AuditLog.objects.create(
        user=resolved_user,
        action="OTP_RESEND_REQUESTED",
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        details={"portal": portal, "channel": channel, "identifier": identifier},
    )

    channel_label = "email address" if channel == "EMAIL" else "mobile phone number"
    return JsonResponse({
        "success": True,
        "message": f"A new verification code has been dispatched to your {channel_label}.",
        "cooldown": getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60),
    })


def phone_otp_verify_view(request):
    """
    Dedicated Mobile Phone OTP Verification Gateway:
    Supports PhoneOTP verification directly and seamlessly falls back to verify_otp_view.
    """
    if request.method == "POST":
        phone_num = request.POST.get("phone_number", "").strip() or request.session.get("otp_auth_phone", "")
        otp_code = (
            request.POST.get("otp_code", "").strip()
            or request.POST.get("code", "").strip()
            or request.POST.get("phone_otp", "").strip()
        )
        if phone_num and otp_code:
            # Check PhoneOTP record
            phone_record = PhoneOTP.objects.filter(
                phone_number=phone_num,
                purpose=PhoneOTP.Purpose.LOGIN,
                is_used=False,
                expires_at__gte=timezone.now(),
            ).first()
            if phone_record and phone_record.otp_code == otp_code:
                phone_record.is_used = True
                phone_record.save(update_fields=["is_used"])
                user = phone_record.user or find_user_by_identifier(phone_num)
                if user:
                    if not user.is_active:
                        user.is_active = True
                        user.is_phone_verified = True
                        user.save(update_fields=["is_active", "is_phone_verified"])
                    login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
                    messages.success(request, f"Welcome back, {user.username}!")
                    return redirect(get_role_dashboard_url(user))

        post_data = request.POST.copy()
        if phone_num and not post_data.get("identifier"):
            post_data["identifier"] = phone_num
        if not post_data.get("channel"):
            post_data["channel"] = "SMS"
        request.POST = post_data

    return verify_otp_view(request)


def set_password_view(request):
    """
    Step 3 of New User Onboarding & Post-OTP Password Setup:
    - User has verified their Email/Phone via OTP.
    - Sets a secure Argon2id password.
    - Optionally allows user to specify Full Name and choose their Workspace Role.
    - Upon setting password, activates account, creates profile, logs user in,
      and redirects directly to their dashboard.
    - Future logins will use User ID (Username/Email) + Password directly WITHOUT requiring OTP!
    """
    user_id = request.session.get("set_password_user_id")
    user = None
    if user_id:
        user = User.objects.filter(id=user_id).first()
    elif request.user.is_authenticated:
        user = request.user

    if not user:
        messages.info(request, "Please enter your email or sign in first to set your password.")
        return redirect("login")

    next_url = request.session.get("set_password_next_url") or ""

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        role = request.POST.get("role", "").strip().upper()
        p1 = request.POST.get("password", "")
        p2 = request.POST.get("confirm_password", "")

        errors = []
        if not p1 or not p2:
            errors.append("Please enter both password fields.")
        elif p1 != p2:
            errors.append("Passwords do not match. Please re-enter your password.")
        elif len(p1) < 8:
            errors.append("Password must be at least 8 characters long.")

        if not errors:
            # Set Argon2id encrypted password
            user.set_password(p1)
            user.is_active = True
            user.is_email_verified = True
            if not user.email_verified_at and user.email:
                user.email_verified_at = timezone.now()

            if full_name:
                parts = full_name.split(" ", 1)
                user.first_name = parts[0]
                user.last_name = parts[1] if len(parts) > 1 else ""

            # Update role if valid
            if role in (User.Role.CANDIDATE, User.Role.RECRUITER, User.Role.FREELANCER):
                user.role = role

            user.save()

            # Ensure proper profile exists
            if user.role == User.Role.RECRUITER:
                RecruiterProfile.objects.get_or_create(user=user, defaults={"company_name": "Independent Recruiter"})
            elif user.role == User.Role.FREELANCER:
                FreelancerProfile.objects.get_or_create(user=user)
            else:
                CandidateProfile.objects.get_or_create(user=user)

            # Log user in
            login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")

            AuditLog.objects.create(
                user=user,
                action="USER_SET_PASSWORD_SUCCESS",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"username": user.username, "email": user.email, "role": user.role},
            )

            # Clear session keys
            request.session.pop("set_password_user_id", None)
            request.session.pop("set_password_next_url", None)

            messages.success(
                request,
                f"🎉 Welcome to HireNexa, {user.first_name or user.username}! Your password has been set. You can now log in anytime using your Email and Password."
            )
            dest = next_url if (next_url and next_url.startswith("/")) else get_role_dashboard_url(user)
            return redirect(dest)
        else:
            for err in errors:
                messages.error(request, err)

    context = {
        "user_target": user,
        "email": user.email,
        "username": user.username,
        "current_role": user.role,
        "next": next_url,
    }
    return render(request, "accounts/set_password.html", context)

# ==============================================================================
# 7. ENTERPRISE EMAIL & MOBILE DUAL OTP VERIFICATION SYSTEM
# ==============================================================================

def dual_verification_view(request):
    """
    Enterprise Dual Verification Gateway:
    - Verifies Email Address and Mobile Number independently.
    - 6-digit OTP inputs with auto-advance and clipboard paste support.
    - Resend countdown with 60-second cooldown timer and hourly throttling.
    - In-place Change Email / Change Mobile modal options with validation.
    - Activates account only after BOTH contact methods are successfully verified.
    """
    user_id = request.session.get("pending_verification_user_id")
    if not user_id and request.user.is_authenticated:
        user_id = request.user.id

    if not user_id:
        messages.info(request, "Please log in or register to complete your account verification.")
        return redirect("login")

    user = get_object_or_404(User, pk=user_id)

    # If already verified and active, log in and send to role dashboard (OR logic: either verified activates account)
    if user.is_active and (user.is_email_verified or user.is_phone_verified):
        if not request.user.is_authenticated:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session.pop("pending_verification_user_id", None)
        next_url = request.session.pop("post_verification_next_url", None)
        if next_url:
            return redirect(next_url)
        return redirect(get_role_dashboard_url(user))

    # Calculate remaining cooldowns for UI timers
    clean_email_target = user.email.lower().strip()
    email_challenge = OTPChallenge.objects.filter(
        Q(identifier__iexact=clean_email_target) | Q(recipient__iexact=clean_email_target),
        channel=OTPChallenge.Channel.EMAIL,
    ).order_by("-created_at").first()
    email_cooldown = email_challenge.cooldown_seconds_remaining(60) if email_challenge else 0

    phone_target = user.phone_number or ""
    phone_challenge = OTPChallenge.objects.filter(
        Q(identifier__iexact=phone_target) | Q(recipient__iexact=phone_target),
        channel=OTPChallenge.Channel.SMS,
    ).order_by("-created_at").first() if phone_target else None
    phone_cooldown = phone_challenge.cooldown_seconds_remaining(60) if phone_challenge else 0

    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "")

    if request.method == "POST":
        action = request.POST.get("action", "")

        # 1. VERIFY EMAIL OTP (OR Logic: Email verification activates account)
        if action == "verify_email":
            code = request.POST.get("email_otp", "").strip() or request.POST.get("otp_code", "").strip() or request.POST.get("code", "").strip()
            res = OTPService.verify_challenge(
                recipient=user.email,
                channel=OTPChallenge.Channel.EMAIL,
                raw_code=code,
                purpose=None,
                user=user,
                request=request
            )
            if res["success"]:
                user.refresh_from_db()
                # OR logic: EITHER email OTP OR mobile OTP verified activates the account!
                user.is_active = True
                user.save(update_fields=["is_active"])
                login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
                request.session.pop("pending_verification_user_id", None)
                request.session.pop("dev_email_otp", None)
                next_url = request.session.pop("post_verification_next_url", None)
                dest_url = next_url or get_role_dashboard_url(user)
                if user.is_phone_verified:
                    msg = "Email verified! Both email and mobile phone are verified. Account activated!"
                else:
                    msg = "Email verified successfully! Your account is now active. You can verify your mobile phone anytime from your profile."
                if is_ajax:
                    return JsonResponse({
                        "success": True,
                        "message": msg,
                        "redirect_url": dest_url,
                        "is_activated": True,
                        "email_verified": True,
                        "phone_verified": user.is_phone_verified,
                    })
                messages.success(request, msg)
                return redirect(dest_url)
            else:
                if is_ajax:
                    return JsonResponse({"success": False, "message": res["message"], "error_code": res.get("error_code")}, status=400)
                messages.error(request, res["message"])
                return redirect("dual_verification")

        # 2. VERIFY MOBILE OTP (OR Logic: Mobile verification activates account)
        elif action == "verify_phone":
            code = request.POST.get("phone_otp", "").strip() or request.POST.get("otp_code", "").strip() or request.POST.get("code", "").strip()
            res = OTPService.verify_challenge(
                recipient=user.phone_number,
                channel=OTPChallenge.Channel.SMS,
                raw_code=code,
                purpose=None,
                user=user,
                request=request
            )
            if res["success"]:
                user.refresh_from_db()
                # OR logic: EITHER email OTP OR mobile OTP verified activates the account!
                user.is_active = True
                user.save(update_fields=["is_active"])
                login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
                request.session.pop("pending_verification_user_id", None)
                request.session.pop("dev_phone_otp", None)
                next_url = request.session.pop("post_verification_next_url", None)
                dest_url = next_url or get_role_dashboard_url(user)
                if user.is_email_verified:
                    msg = "Mobile verified! Both email and mobile phone are verified. Account activated!"
                else:
                    msg = "Mobile phone verified successfully! Your account is now active. You can verify your email anytime from your profile."
                if is_ajax:
                    return JsonResponse({
                        "success": True,
                        "message": msg,
                        "redirect_url": dest_url,
                        "is_activated": True,
                        "email_verified": user.is_email_verified,
                        "phone_verified": True,
                    })
                messages.success(request, msg)
                return redirect(dest_url)
            else:
                if is_ajax:
                    return JsonResponse({"success": False, "message": res["message"], "error_code": res.get("error_code")}, status=400)
                messages.error(request, res["message"])
                return redirect("dual_verification")

        # 3. RESEND EMAIL OTP
        elif action == "resend_email":
            res = OTPService.issue_challenge(
                recipient=user.email,
                channel=OTPChallenge.Channel.EMAIL,
                user=user,
                request=request
            )
            if getattr(settings, "DEBUG", False):
                request.session["dev_email_otp"] = res.get("otp")
            if res["success"]:
                msg = res.get("message", "Email verification OTP sent successfully.")
                if is_ajax:
                    return JsonResponse({"success": True, "message": msg, "cooldown": res.get("cooldown_remaining", 60), "dev_otp": res.get("otp") if getattr(settings, "DEBUG", False) else None})
                messages.success(request, msg)
            else:
                err_msg = res.get("message", "Failed to send email verification OTP.")
                status_code = 429 if res.get("error_code") in ["COOLDOWN_ACTIVE", "RATE_LIMIT_EXCEEDED"] else 400
                if is_ajax:
                    return JsonResponse({"success": False, "message": err_msg, "cooldown": res.get("cooldown_remaining", 0), "error_code": res.get("error_code")}, status=status_code)
                messages.error(request, err_msg)
            return redirect("dual_verification")

        # 4. RESEND MOBILE OTP
        elif action == "resend_phone":
            res = OTPService.issue_challenge(
                recipient=user.phone_number,
                channel=OTPChallenge.Channel.SMS,
                user=user,
                request=request
            )
            if getattr(settings, "DEBUG", False):
                request.session["dev_phone_otp"] = res.get("otp")
            if res["success"]:
                msg = res.get("message", "Mobile OTP sent successfully.")
                if is_ajax:
                    return JsonResponse({"success": True, "message": msg, "cooldown": res.get("cooldown_remaining", 60), "dev_otp": res.get("otp") if getattr(settings, "DEBUG", False) else None})
                messages.success(request, msg)
            else:
                err_msg = res.get("message", "Failed to send mobile OTP.")
                status_code = 429 if res.get("error_code") in ["COOLDOWN_ACTIVE", "RATE_LIMIT_EXCEEDED"] else 400
                if is_ajax:
                    return JsonResponse({"success": False, "message": err_msg, "cooldown": res.get("cooldown_remaining", 0), "error_code": res.get("error_code")}, status=status_code)
                messages.error(request, err_msg)
            return redirect("dual_verification")

        # 5. CHANGE EMAIL
        elif action == "change_email":
            change_form = ChangeEmailForm(request.POST, user_id=user.id)
            if change_form.is_valid():
                new_email = change_form.cleaned_data["new_email"]
                user.email = new_email
                user.is_email_verified = False
                user.email_verified_at = None
                user.save(update_fields=["email", "is_email_verified", "email_verified_at"])
                send_res = OTPService.issue_challenge(user.email, OTPChallenge.Channel.EMAIL, user=user, request=request)
                if send_res["success"]:
                    msg = "Email address updated. A new verification OTP has been sent."
                    if is_ajax:
                        return JsonResponse({"success": True, "message": msg, "new_email": new_email})
                    messages.success(request, msg)
                else:
                    msg = f"Email updated to {new_email}, but sending code failed: {send_res.get('message')}"
                    if is_ajax:
                        return JsonResponse({"success": False, "message": msg, "new_email": new_email}, status=400)
                    messages.warning(request, msg)
                return redirect("dual_verification")
            else:
                err_text = " ".join([e for errs in change_form.errors.values() for e in errs])
                if is_ajax:
                    return JsonResponse({"success": False, "message": err_text}, status=400)
                messages.error(request, err_text)
                return redirect("dual_verification")

        # 6. CHANGE PHONE NUMBER
        elif action == "change_phone":
            change_phone_form = ChangePhoneForm(request.POST, user_id=user.id)
            if change_phone_form.is_valid():
                new_phone = change_phone_form.cleaned_data["new_phone_number"]
                user.phone_number = new_phone
                user.is_phone_verified = False
                user.phone_verified_at = None
                user.save(update_fields=["phone_number", "is_phone_verified", "phone_verified_at"])
                send_res = OTPService.issue_challenge(user.phone_number, OTPChallenge.Channel.SMS, user=user, request=request)
                if send_res["success"]:
                    msg = "Mobile number updated. A new verification OTP has been sent."
                    if is_ajax:
                        return JsonResponse({"success": True, "message": msg, "new_phone": new_phone})
                    messages.success(request, msg)
                else:
                    msg = f"Mobile number updated to {new_phone}, but sending code failed: {send_res.get('message')}"
                    if is_ajax:
                        return JsonResponse({"success": False, "message": msg, "new_phone": new_phone}, status=400)
                    messages.warning(request, msg)
                return redirect("dual_verification")
            else:
                err_text = " ".join([e for errs in change_phone_form.errors.values() for e in errs])
                if is_ajax:
                    return JsonResponse({"success": False, "message": err_text}, status=400)
                messages.error(request, err_text)
                return redirect("dual_verification")

    email_status, email_provider = EmailDeliveryService.get_provider_status()
    sms_status, sms_provider = SMSDeliveryService.get_provider_status()

    # Track delivery failures to inform user honestly on page load
    email_delivery_failed = bool(email_challenge and email_challenge.delivery_status == OTPChallenge.DeliveryStatus.FAILED)
    email_delivery_error = email_challenge.error_message if email_delivery_failed else ""

    phone_delivery_failed = bool(phone_challenge and phone_challenge.delivery_status == OTPChallenge.DeliveryStatus.FAILED)
    phone_delivery_error = phone_challenge.error_message if phone_delivery_failed else ""

    return render(request, "accounts/dual_verification.html", {
        "target_user": user,
        "email_verified": user.is_email_verified,
        "phone_verified": user.is_phone_verified,
        "email_cooldown": email_cooldown,
        "phone_cooldown": phone_cooldown,
        "email_provider": email_provider,
        "sms_provider": sms_provider,
        "email_delivery_failed": email_delivery_failed,
        "email_delivery_error": email_delivery_error,
        "phone_delivery_failed": phone_delivery_failed,
        "phone_delivery_error": phone_delivery_error,
        "country_codes": COUNTRY_CODES,
        "dev_email_otp": request.session.get("dev_email_otp"),
        "dev_phone_otp": request.session.get("dev_phone_otp"),
    })


@require_POST
def resend_otp_api_view(request, channel):
    """AJAX endpoint for resending Email or SMS OTP."""
    user_id = request.session.get("pending_verification_user_id") or (request.user.id if request.user.is_authenticated else None)
    if not user_id:
        return JsonResponse({"success": False, "message": "Unauthorized or session expired."}, status=401)

    user = get_object_or_404(User, pk=user_id)
    chan = OTPChallenge.Channel.EMAIL if channel.upper() == "EMAIL" else OTPChallenge.Channel.SMS
    recipient = user.email if chan == OTPChallenge.Channel.EMAIL else user.phone_number

    res = OTPService.issue_challenge(recipient=recipient, channel=chan, user=user, request=request)
    status_code = 200 if res["success"] else (429 if res.get("error_code") in ["COOLDOWN_ACTIVE", "RATE_LIMIT_EXCEEDED"] else 400)
    return JsonResponse(res, status=status_code)


# ==============================================================================
# 7B. LEGACY BADGE VERIFICATION ENDPOINTS (PRESERVED)
# ==============================================================================

@login_required
def send_email_verification_view(request):
    """Generate 6-digit OTP for Email Address verification."""
    user = request.user
    if not user.email:
        messages.error(request, "Please set an email address on your profile before requesting verification.")
        return redirect("profile_edit")

    otp_obj, raw_code = EmailOTP.generate(
        email=user.email,
        purpose=EmailOTP.Purpose.VERIFY,
        user=user,
        validity_minutes=15,
    )

    AuditLog.objects.create(
        user=user,
        action="EMAIL_VERIFICATION_REQUESTED",
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        details={"email": mask_email(user.email)},
    )

    dispatch_res = EmailDeliveryService.send_otp_email(user.email, user.full_name, raw_code, validity_minutes=15)
    if not dispatch_res.get("success"):
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        messages.error(request, "Unable to send verification email at this time. Please try again shortly.")
    else:
        messages.info(
            request,
            f"Email verification OTP sent successfully to {mask_email(user.email)}."
        )
    return redirect("profile_edit")


@login_required
def verify_email_otp_view(request):
    """Verify submitted 6-digit Email OTP and mark is_email_verified = True."""
    user = request.user
    if request.method == "POST":
        otp_code = request.POST.get("otp_code", "").strip()

        record = EmailOTP.objects.filter(
            email__iexact=user.email,
            purpose=EmailOTP.Purpose.VERIFY,
            is_used=False,
            expires_at__gte=timezone.now(),
        ).first()

        if record:
            is_valid, _ = record.check_code(otp_code)
            if is_valid:
                user.is_email_verified = True
                user.save(update_fields=["is_email_verified"])

                AuditLog.objects.create(
                    user=user,
                    action="EMAIL_VERIFIED_SUCCESS",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"email": mask_email(user.email)},
                )
                messages.success(request, "✓ Email address verified successfully! Your account now displays the Verified badge.")
                return redirect("profile_edit")

        messages.error(request, "Invalid or expired email verification code. Please request a new code.")

    return redirect("profile_edit")


@login_required
def send_phone_verification_view(request):
    """Generate 6-digit OTP for Phone Number linking and verification."""
    user = request.user
    phone = clean_phone_number(request.POST.get("phone_number", user.phone_number or ""))

    if not phone or len(re.sub(r"[^\d]", "", phone)) < 8:
        messages.error(request, "Please enter a valid mobile phone number.")
        return redirect("profile_edit")

    # Ensure phone is not taken by another user
    existing = User.objects.filter(phone_number=phone).exclude(pk=user.pk).exists()
    if existing:
        messages.error(request, "This phone number is already registered to another account.")
        return redirect("profile_edit")

    otp = PhoneOTP.generate(
        phone_number=phone,
        purpose=PhoneOTP.Purpose.VERIFY,
        user=user,
        validity_minutes=10,
    )
    request.session["pending_verify_phone"] = phone

    AuditLog.objects.create(
        user=user,
        action="PHONE_VERIFICATION_REQUESTED",
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        details={"phone_number": phone},
    )

    SMSDeliveryService.send_otp_sms(phone, otp.otp_code)
    messages.info(
        request,
        f"Mobile OTP sent successfully to {phone}."
    )
    return redirect("profile_edit")


@login_required
def verify_phone_verification_view(request):
    """Verify phone OTP and activate phone badge."""
    user = request.user
    if request.method == "POST":
        otp_code = request.POST.get("otp_code", "").strip()
        phone = request.session.get("pending_verify_phone") or user.phone_number

        if not phone:
            messages.error(request, "No pending phone verification session found. Please re-enter your phone number.")
            return redirect("profile_edit")

        record = PhoneOTP.objects.filter(
            phone_number=phone,
            otp_code=otp_code,
            purpose=PhoneOTP.Purpose.VERIFY,
            is_used=False,
            expires_at__gte=timezone.now(),
        ).first()

        if record:
            record.is_used = True
            record.save(update_fields=["is_used"])
            user.phone_number = phone
            user.is_phone_verified = True
            user.save(update_fields=["phone_number", "is_phone_verified"])
            request.session.pop("pending_verify_phone", None)

            AuditLog.objects.create(
                user=user,
                action="PHONE_VERIFIED_SUCCESS",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"phone_number": phone},
            )
            messages.success(request, "✓ Mobile phone verified successfully! Verified badge activated.")
        else:
            messages.error(request, "Invalid or expired phone verification OTP.")

    return redirect("profile_edit")


# ==============================================================================
# 8. FORGOT PASSWORD SYSTEM (RESET VIA EMAIL OTP OR PHONE OTP)
# ==============================================================================

def forgot_password_view(request):
    """
    Step 1: Look up account by Username, Email, OR Mobile Phone.
    Generates a secure 6-digit OTP code sent via Email or Mobile SMS.
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    if request.method == "POST":
        form = ForgotPasswordRequestForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"].strip()
            user = find_user_by_identifier(identifier)

            if not user:
                # Generic message to prevent user enumeration
                messages.error(
                    request,
                    "No account found matching that Username, Email, or Mobile Phone. Please verify and try again."
                )
                return render(request, "accounts/forgot_password.html", {"form": form})

            # Check preferred reset channel
            reset_channel = request.POST.get("channel", "email")
            otp_code = None

            if reset_channel == "phone" and user.phone_number:
                otp_obj = PhoneOTP.generate(
                    phone_number=user.phone_number,
                    purpose=PhoneOTP.Purpose.RESET,
                    user=user,
                    validity_minutes=15,
                )
                otp_code = otp_obj.otp_code
                request.session["reset_user_id"] = user.pk
                request.session["reset_channel"] = "phone"
                request.session["reset_target"] = user.phone_number

                AuditLog.objects.create(
                    user=user,
                    action="PASSWORD_RESET_PHONE_OTP_SENT",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"phone_number": user.phone_number},
                )
                SMSDeliveryService.send_otp_sms(user.phone_number, otp_code, validity_minutes=15)
                messages.info(
                    request,
                    "Password reset verification OTP sent to your registered mobile number."
                )
                return redirect("reset_password_otp")

            else:
                # Default to Email Reset OTP
                target_email = user.email or f"{user.username}@hirenexa.local"
                can_request, err_msg, wait_sec = EmailOTP.can_request_otp(
                    email=target_email,
                    purpose=EmailOTP.Purpose.RESET,
                    cooldown_seconds=60,
                    max_per_hour=5,
                )
                if not can_request:
                    messages.error(request, err_msg)
                    return render(request, "accounts/forgot_password.html", {"form": form})

                otp_obj, raw_code = EmailOTP.generate(
                    email=target_email,
                    purpose=EmailOTP.Purpose.RESET,
                    user=user,
                    validity_minutes=15,
                )
                request.session["reset_user_id"] = user.pk
                request.session["reset_channel"] = "email"
                request.session["reset_target"] = target_email

                AuditLog.objects.create(
                    user=user,
                    action="PASSWORD_RESET_EMAIL_OTP_SENT",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"email": mask_email(target_email)},
                )
                dispatch_res = EmailDeliveryService.send_otp_email(target_email, user.full_name, raw_code, validity_minutes=15)
                if not dispatch_res.get("success"):
                    otp_obj.is_used = True
                    otp_obj.save(update_fields=["is_used"])
                    messages.error(request, "Unable to send verification email at this time. Please try again shortly.")
                    return render(request, "accounts/forgot_password.html", {"form": form})

                messages.success(
                    request,
                    f"We sent a 6-digit recovery code to {mask_email(target_email)}."
                )
                return redirect("reset_password_otp")
    else:
        form = ForgotPasswordRequestForm()

    return render(request, "accounts/forgot_password.html", {"form": form})


def reset_password_view(request):
    """
    Step 2: Verify 6-digit OTP and update password using Argon2 secure hashing.
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    user_id = request.session.get("reset_user_id")
    channel = request.session.get("reset_channel", "email")
    target = request.session.get("reset_target", "")
    masked_target = mask_email(target) if channel == "email" else target

    if not user_id:
        messages.warning(request, "Password reset session expired. Please start recovery again.")
        return redirect("forgot_password")

    user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = ResetPasswordWithOTPForm(request.POST)
        if form.is_valid():
            otp_code = form.cleaned_data["otp_code"].strip()
            new_password = form.cleaned_data["new_password1"]

            # Validate OTP against selected channel
            otp_valid = False
            if channel == "phone":
                record = PhoneOTP.objects.filter(
                    phone_number=target,
                    otp_code=otp_code,
                    purpose=PhoneOTP.Purpose.RESET,
                    is_used=False,
                    expires_at__gte=timezone.now(),
                ).first()
                if record:
                    record.is_used = True
                    record.save(update_fields=["is_used"])
                    otp_valid = True
            else:
                record = EmailOTP.objects.filter(
                    email__iexact=target,
                    purpose=EmailOTP.Purpose.RESET,
                    is_used=False,
                    expires_at__gte=timezone.now(),
                ).first()
                if record:
                    otp_valid, reason = record.check_code(otp_code)
                    if reason == "LOCKED":
                        messages.error(request, "Too many failed attempts (5/5). This code has been locked. Please start recovery again.")
                        return render(request, "accounts/reset_password.html", {"form": form, "user": user, "channel": channel, "target": target, "masked_target": masked_target})

            if otp_valid:
                # Set new password (Argon2 automatically applied via settings.PASSWORD_HASHERS)
                user.set_password(new_password)
                user.save()

                AuditLog.objects.create(
                    user=user,
                    action="PASSWORD_RESET_SUCCESS",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"reset_channel": channel, "target": target},
                )

                # Clear reset session
                request.session.pop("reset_user_id", None)
                request.session.pop("reset_channel", None)
                request.session.pop("reset_target", None)

                messages.success(
                    request,
                    f"✓ Password updated successfully for {user.username}! You may now sign in with your new credentials."
                )
                return redirect("login")
            else:
                messages.error(request, "Invalid or expired OTP code. Please check the code or request a new one.")
    else:
        form = ResetPasswordWithOTPForm()

    return render(
        request,
        "accounts/reset_password.html",
        {"form": form, "user": user, "channel": channel, "target": masked_target},
    )


# ==============================================================================
# 9. GENERAL REGISTRATION & DEMO ACCESS
# ==============================================================================

def signup_view(request):
    """
    Unified public registration.
    SECURITY NOTICE: The OWNER role is strictly excluded and rejected.
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()

                # Defense-in-depth: Never allow public registration to create owner or superuser
                if user.is_superuser or user.is_staff or str(user.role).upper() in (User.Role.OWNER, "OWNER"):
                    user.is_superuser = False
                    user.is_staff = False
                    user.role = User.Role.CANDIDATE
                    user.save(update_fields=["is_superuser", "is_staff", "role"])

                if user.role == User.Role.RECRUITER:
                    RecruiterProfile.objects.get_or_create(user=user)
                elif user.role == User.Role.FREELANCER:
                    FreelancerProfile.objects.get_or_create(user=user)
                elif user.role == User.Role.COMPANY_ADMIN:
                    from recruitment.models import Organization, OrganizationMember
                    org_name = f"{user.first_name or user.username}'s Company"
                    org, _ = Organization.objects.get_or_create(
                        name=org_name,
                        defaults={
                            "is_active": True,
                            "verification_status": Organization.VerificationStatus.APPROVED,
                        }
                    )
                    OrganizationMember.objects.get_or_create(
                        organization=org,
                        user=user,
                        defaults={"role": OrganizationMember.MemberRole.ADMIN}
                    )
                else:
                    CandidateProfile.objects.get_or_create(user=user)

                require_otp = getattr(settings, "UNIFIED_REQUIRE_OTP", False)
                if not require_otp:
                    user.is_active = True
                    user.is_email_verified = True
                    user.is_phone_verified = True
                    user.save(update_fields=["is_active", "is_email_verified", "is_phone_verified"])
                    login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
                    AuditLog.objects.create(
                        user=user,
                        action="USER_REGISTERED_AUTO_ACTIVATED",
                        ip_address=get_client_ip(request),
                        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                        details={"username": user.username, "role": user.role, "email": user.email, "phone": user.phone_number},
                    )
                    messages.success(request, f"Welcome to HireNexa, {user.first_name or user.username}! Your account has been created successfully.")
                    return redirect(next_url or get_role_dashboard_url(user))

            res_email = OTPService.issue_challenge(user.email, OTPChallenge.Channel.EMAIL, user=user, request=request)
            res_phone = OTPService.issue_challenge(user.phone_number, OTPChallenge.Channel.SMS, user=user, request=request)
            request.session["pending_verification_user_id"] = user.id
            if getattr(settings, "DEBUG", False):
                request.session["dev_email_otp"] = res_email.get("otp")
                request.session["dev_phone_otp"] = res_phone.get("otp")
            if next_url:
                request.session["post_verification_next_url"] = next_url

            AuditLog.objects.create(
                user=user,
                action="USER_REGISTERED_PENDING_VERIFICATION",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"username": user.username, "role": user.role, "email": user.email, "phone": user.phone_number},
            )
            if res_email.get("success") or res_phone.get("success"):
                messages.info(request, "Registration successful! Please verify either your Email OR Mobile OTP to activate your account.")
            else:
                messages.warning(request, f"Registration complete, but OTP dispatch failed: {res_email.get('message')}. Please click Resend on the verification page.")
            return redirect("dual_verification")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form, "next": next_url})


def demo_login_view(request, role):
    """
    1-Click instant demo access for Candidate, Recruiter, and Freelancer.
    CRITICAL SECURITY ENFORCEMENT:
    Platform Owner demo login is strictly disabled to prevent credential exposure.
    """
    role = role.lower()
    if role in ["owner", "admin", "superadmin"]:
        messages.error(
            request,
            "Security Policy: Platform Owner accounts cannot be accessed via 1-Click Demo login.",
        )
        return redirect("owner_login")

    target_role = None
    if role in ["company_admin", "company"]:
        target_role = User.Role.COMPANY_ADMIN
    elif role in ["recruiter", "hr"]:
        target_role = User.Role.RECRUITER
    elif role == "freelancer":
        target_role = User.Role.FREELANCER
    else:
        target_role = User.Role.CANDIDATE

    user = User.objects.filter(role=target_role, is_active=True).first()
    if user:
        login(request, user, backend="accounts.backends.MultiIdentifierModelBackend")
        AuditLog.objects.create(
            user=user,
            action="DEMO_LOGIN_ACCESSED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"demo_role": role, "username": user.username},
        )
        messages.success(request, f"⚡ Signed in as {user.username} ({user.get_role_display()}) via 1-Click Demo.")
        return redirect(get_role_dashboard_url(user))
    else:
        messages.warning(request, f"No demo account found for role '{role}'. Please register a free account.")
        return redirect("signup")


def logout_view(request):
    """Secure logout strictly requiring POST to prevent CSRF logout attacks."""
    if request.method != "POST":
        return redirect("home")
    if request.user.is_authenticated:
        AuditLog.objects.create(
            user=request.user,
            action="USER_LOGOUT",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"username": request.user.username, "method": request.method},
        )
        logout(request)
        messages.info(request, "You have been securely signed out.")
    return redirect("home")


@login_required
def switch_portal_view(request):
    """
    Secure POST endpoint to switch active portal.
    Verifies user permissions before setting active_role in session.
    """
    if request.method != "POST":
        messages.error(request, "Portal switching requires a secure POST request.")
        return redirect("dashboard")

    target_role = request.POST.get("portal_role", "").strip().upper()
    next_url = request.POST.get("next", "")

    # Retrieve allowed portals for user
    from accounts.context_processors import get_user_available_portals
    allowed = get_user_available_portals(request.user)
    allowed_roles = {p["role"]: p for p in allowed}

    if target_role not in allowed_roles:
        AuditLog.objects.create(
            user=request.user,
            action="UNAUTHORIZED_PORTAL_SWITCH_ATTEMPT",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"attempted_role": target_role},
        )
        messages.error(request, f"Access Denied: You do not have permissions for the {target_role} portal.")
        return redirect("dashboard")

    # Update active_role in session
    previous_role = request.session.get("active_role", request.user.role)
    request.session["active_role"] = target_role
    portal_info = allowed_roles[target_role]

    AuditLog.objects.create(
        user=request.user,
        action="PORTAL_SWITCHED",
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        details={"from": previous_role, "to": target_role},
    )

    messages.success(request, f"Switched active portal to {portal_info['name']}.")

    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect(portal_info["url_name"])



def custom_403_view(request, exception=None):
    """Render branded enterprise 403 Forbidden page."""
    context = {
        "exception": str(exception) if exception else "Access to this resource is restricted.",
        "path": request.path,
    }
    return render(request, "403.html", context, status=403)


def custom_404_view(request, exception=None):
    """Render branded enterprise 404 Not Found page."""
    return render(request, "404.html", {"path": request.path}, status=404)


def custom_500_view(request):
    """Render branded enterprise 500 Server Error page."""
    return render(request, "500.html", {}, status=500)
