import json
import csv
from datetime import datetime
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    User, UserSettings, NotificationPreference, LoginHistory, AuditLog, PlatformSetting, EmailOTP
)
from accounts.middleware import get_client_ip
from accounts.validators import validate_and_normalize_email
from recruitment.models import (
    Resume, Organization, OrganizationMember, Job, Application, FreelancerProfile, CandidateProfile
)


@login_required
def settings_index_view(request):
    """Entry point for /settings/ - redirects to Profile settings tab."""
    return redirect("settings_profile")


@login_required
def settings_profile_view(request):
    """Personal and professional profile details, photo upload, bio, links."""
    user = request.user
    user_settings = user.user_settings

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()

        headline = request.POST.get("headline", "").strip()
        location = request.POST.get("location", "").strip()
        bio = request.POST.get("bio", "").strip()
        website_url = request.POST.get("website_url", "").strip()
        github_url = request.POST.get("github_url", "").strip()
        linkedin_url = request.POST.get("linkedin_url", "").strip()
        twitter_url = request.POST.get("twitter_url", "").strip()

        # Update User model
        user.first_name = first_name
        user.last_name = last_name
        if phone_number and phone_number != user.phone_number:
            # If changed, mark unverified
            user.phone_number = phone_number
            user.is_phone_verified = False
        user.save(update_fields=["first_name", "last_name", "phone_number", "is_phone_verified"])

        # Update UserSettings model
        user_settings.headline = headline
        user_settings.location = location
        user_settings.bio = bio
        user_settings.website_url = website_url
        user_settings.github_url = github_url
        user_settings.linkedin_url = linkedin_url
        user_settings.twitter_url = twitter_url

        if "avatar" in request.FILES:
            user_settings.avatar = request.FILES["avatar"]

        user_settings.save()

        AuditLog.objects.create(
            user=user,
            action="PROFILE_UPDATED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"updated_fields": ["first_name", "last_name", "headline", "location"]},
        )

        messages.success(request, "Your profile information has been saved successfully.")
        return redirect("settings_profile")

    context = {
        "active_tab": "profile",
        "user_settings": user_settings,
    }
    return render(request, "accounts/settings/profile.html", context)


@login_required
def settings_account_view(request):
    """Account identity, email change with OTP challenge, language and timezone."""
    user = request.user
    user_settings = user.user_settings

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "update_account":
            username = request.POST.get("username", "").strip()
            timezone_val = request.POST.get("timezone", "Asia/Kolkata").strip()
            language_val = request.POST.get("language", "en").strip()
            date_format_val = request.POST.get("date_format", "YYYY-MM-DD").strip()
            time_format_val = request.POST.get("time_format", "24h").strip()

            if username and username != user.username:
                if User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
                    messages.error(request, f"The username '{username}' is already taken.")
                    return redirect("settings_account")
                user.username = username
                user.save(update_fields=["username"])

            user_settings.timezone = timezone_val
            user_settings.language = language_val
            user_settings.date_format = date_format_val
            user_settings.time_format = time_format_val
            user_settings.save(update_fields=["timezone", "language", "date_format", "time_format"])

            AuditLog.objects.create(
                user=user,
                action="ACCOUNT_SETTINGS_UPDATED",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"timezone": timezone_val, "language": language_val},
            )

            messages.success(request, "Account localization and preferences updated.")
            return redirect("settings_account")

        elif action == "request_email_change":
            new_email = request.POST.get("new_email", "").strip()
            is_valid, normalized, err = validate_and_normalize_email(new_email, exclude_user_id=user.id)
            if not is_valid:
                messages.error(request, err)
                return redirect("settings_account")

            # Check rate limiting / cooldown
            can_request, err_msg, _ = EmailOTP.can_request_otp(normalized, purpose=EmailOTP.Purpose.VERIFY)
            if not can_request:
                messages.error(request, err_msg)
                return redirect("settings_account")

            otp_record, raw_code = EmailOTP.generate(normalized, purpose=EmailOTP.Purpose.VERIFY, user=user)

            # Store pending email in session
            request.session["pending_new_email"] = normalized

            # Send OTP email
            try:
                send_mail(
                    subject="HireNexa Email Change Verification Code",
                    message=f"Hello {user.username},\n\nYour 6-digit verification code to update your HireNexa email to {normalized} is: {raw_code}\n\nThis code expires in 15 minutes.\nIf you did not request this change, please review your security settings immediately.",
                    from_email="HireNexa Security <security@hirenexa.com>",
                    recipient_list=[normalized],
                    fail_silently=False,
                )
                messages.info(request, f"A 6-digit confirmation code has been sent to {normalized}. Enter it below to confirm.")
            except Exception as e:
                messages.warning(request, f"Code generated ({raw_code}) - email delivery note: {e}")

            return redirect("settings_account")

        elif action == "confirm_email_change":
            otp_input = request.POST.get("email_otp", "").strip()
            pending_email = request.session.get("pending_new_email")

            if not pending_email:
                messages.error(request, "No pending email change found. Please request a new code.")
                return redirect("settings_account")

            last_otp = EmailOTP.objects.filter(
                email=pending_email,
                user=user,
                purpose=EmailOTP.Purpose.VERIFY,
                is_used=False
            ).first()

            if not last_otp:
                messages.error(request, "Verification code expired or not found. Please try again.")
                return redirect("settings_account")

            is_valid, reason = last_otp.check_code(otp_input)
            if is_valid:
                old_email = user.email
                user.email = pending_email
                user.is_email_verified = True
                user.email_verified_at = timezone.now()
                user.save(update_fields=["email", "is_email_verified", "email_verified_at"])
                del request.session["pending_new_email"]

                AuditLog.objects.create(
                    user=user,
                    action="EMAIL_CHANGED",
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"old_email": old_email, "new_email": pending_email},
                )
                messages.success(request, f"Your email address has been successfully updated to {pending_email}.")
            else:
                messages.error(request, f"Invalid verification code ({reason}). Please check and try again.")
            return redirect("settings_account")

    context = {
        "active_tab": "account",
        "user_settings": user_settings,
        "pending_email": request.session.get("pending_new_email"),
    }
    return render(request, "accounts/settings/account.html", context)


@login_required
def settings_security_view(request):
    """Password change, Argon2id strength meter, 2FA toggle, active sessions & login history."""
    user = request.user
    user_settings = user.user_settings

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "change_password":
            current_pass = request.POST.get("current_password", "")
            new_pass1 = request.POST.get("new_password1", "")
            new_pass2 = request.POST.get("new_password2", "")

            if not user.check_password(current_pass):
                messages.error(request, "The current password you entered is incorrect.")
                return redirect("settings_security")

            if new_pass1 != new_pass2:
                messages.error(request, "New passwords do not match. Please re-enter them.")
                return redirect("settings_security")

            if len(new_pass1) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return redirect("settings_security")

            user.set_password(new_pass1)
            user.save()
            update_session_auth_hash(request, user)

            AuditLog.objects.create(
                user=user,
                action="PASSWORD_CHANGED",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"method": "settings_portal"},
            )

            messages.success(request, "Your password has been changed securely (Argon2id encrypted).")
            return redirect("settings_security")

        elif action == "toggle_2fa":
            enabled = request.POST.get("two_factor_enabled") == "on"
            method = request.POST.get("two_factor_method", "EMAIL")

            user_settings.two_factor_enabled = enabled
            user_settings.two_factor_method = method
            user_settings.save(update_fields=["two_factor_enabled", "two_factor_method"])

            status_str = "enabled" if enabled else "disabled"
            AuditLog.objects.create(
                user=user,
                action=f"TWO_FACTOR_{status_str.upper()}",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"method": method},
            )
            messages.success(request, f"Two-Factor Authentication (2FA) is now {status_str}.")
            return redirect("settings_security")

        elif action == "generate_backup_codes":
            import secrets
            codes = [f"{secrets.randbelow(9000)+1000}-{secrets.randbelow(9000)+1000}" for _ in range(8)]
            user_settings.backup_codes = codes
            user_settings.save(update_fields=["backup_codes"])

            AuditLog.objects.create(
                user=user,
                action="BACKUP_CODES_GENERATED",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            )
            messages.success(request, "8 new single-use backup security codes have been generated.")
            return redirect("settings_security")

        elif action == "logout_other_devices":
            current_session_key = request.session.session_key
            try:
                for session in Session.objects.all():
                    if session.session_key != current_session_key:
                        data = session.get_decoded()
                        if str(data.get("_auth_user_id")) == str(user.id):
                            session.delete()
            except Exception:
                pass

            LoginHistory.objects.filter(user=user).exclude(session_key=current_session_key).update(is_active=False)

            AuditLog.objects.create(
                user=user,
                action="LOGOUT_ALL_OTHER_DEVICES",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            )
            messages.success(request, "Successfully terminated all other active sessions and devices.")
            return redirect("settings_security")

    # Fetch active sessions & login history
    history = LoginHistory.objects.filter(user=user).order_by("-created_at")[:10]

    context = {
        "active_tab": "security",
        "user_settings": user_settings,
        "login_history": history,
        "current_ip": get_client_ip(request),
    }
    return render(request, "accounts/settings/security.html", context)


@login_required
def settings_notifications_view(request):
    """Notification channels, categories, digest frequency, and quiet hours."""
    user = request.user
    prefs = user.notif_preferences

    if request.method == "POST":
        # Email toggles
        prefs.email_applications = request.POST.get("email_applications") == "on"
        prefs.email_interviews = request.POST.get("email_interviews") == "on"
        prefs.email_messages = request.POST.get("email_messages") == "on"
        prefs.email_job_alerts = request.POST.get("email_job_alerts") == "on"
        prefs.email_news = request.POST.get("email_news") == "on"
        prefs.email_marketing = request.POST.get("email_marketing") == "on"

        # In-App toggles
        prefs.inapp_applications = request.POST.get("inapp_applications") == "on"
        prefs.inapp_interviews = request.POST.get("inapp_interviews") == "on"
        prefs.inapp_messages = request.POST.get("inapp_messages") == "on"
        prefs.inapp_job_alerts = request.POST.get("inapp_job_alerts") == "on"
        prefs.inapp_news = request.POST.get("inapp_news") == "on"

        # Push toggle
        prefs.push_enabled = request.POST.get("push_enabled") == "on"

        # Frequency & Quiet Hours
        prefs.digest_frequency = request.POST.get("digest_frequency", "INSTANT")
        prefs.quiet_hours_enabled = request.POST.get("quiet_hours_enabled") == "on"

        start_time = request.POST.get("quiet_hours_start", "").strip()
        end_time = request.POST.get("quiet_hours_end", "").strip()
        if start_time:
            try:
                prefs.quiet_hours_start = datetime.strptime(start_time, "%H:%M").time()
            except ValueError:
                pass
        if end_time:
            try:
                prefs.quiet_hours_end = datetime.strptime(end_time, "%H:%M").time()
            except ValueError:
                pass

        prefs.save()

        AuditLog.objects.create(
            user=user,
            action="NOTIFICATION_PREFERENCES_UPDATED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )

        messages.success(request, "Your notification preferences have been saved.")
        return redirect("settings_notifications")

    context = {
        "active_tab": "notifications",
        "prefs": prefs,
    }
    return render(request, "accounts/settings/notifications.html", context)


@login_required
def settings_privacy_view(request):
    """Privacy controls, search visibility, GDPR data download, and account deletion."""
    user = request.user
    user_settings = user.user_settings

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "update_visibility":
            user_settings.profile_visibility = request.POST.get("profile_visibility", "RECRUITERS")
            user_settings.resume_visibility = request.POST.get("resume_visibility", "RECRUITERS")
            user_settings.hide_phone = request.POST.get("hide_phone") == "on"
            user_settings.hide_email = request.POST.get("hide_email") == "on"
            user_settings.save(update_fields=["profile_visibility", "resume_visibility", "hide_phone", "hide_email"])

            AuditLog.objects.create(
                user=user,
                action="PRIVACY_SETTINGS_UPDATED",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            )
            messages.success(request, "Your privacy and visibility settings have been saved.")
            return redirect("settings_privacy")

        elif action == "download_gdpr_data":
            # GDPR JSON Data Export
            data = {
                "hirenexa_export_version": "2.0",
                "exported_at": timezone.now().isoformat(),
                "user_account": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "role": user.role,
                    "is_email_verified": user.is_email_verified,
                    "is_phone_verified": user.is_phone_verified,
                    "date_joined": user.date_joined.isoformat(),
                },
                "settings": {
                    "headline": user_settings.headline,
                    "location": user_settings.location,
                    "bio": user_settings.bio,
                    "theme": user_settings.theme,
                    "language": user_settings.language,
                    "timezone": user_settings.timezone,
                    "profile_visibility": user_settings.profile_visibility,
                },
                "applications_count": Application.objects.filter(candidate=user).count(),
                "login_history_count": LoginHistory.objects.filter(user=user).count(),
            }
            response = HttpResponse(
                json.dumps(data, indent=2),
                content_type="application/json",
            )
            response["Content-Disposition"] = f'attachment; filename="hirenexa_data_{user.username}_{timezone.now():%Y%m%d}.json"'
            return response

        elif action == "delete_account":
            confirm_phrase = request.POST.get("confirm_phrase", "").strip()
            confirm_password = request.POST.get("confirm_password", "")

            if confirm_phrase != "DELETE":
                messages.error(request, "Please type 'DELETE' in uppercase to confirm account closure.")
                return redirect("settings_privacy")

            if not user.check_password(confirm_password):
                messages.error(request, "Incorrect password. Account deletion aborted.")
                return redirect("settings_privacy")

            AuditLog.objects.create(
                user=user,
                action="ACCOUNT_DEACTIVATED",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"reason": "User requested GDPR self-deletion"},
            )

            # Soft deactivate user account
            user.is_active = False
            user.save(update_fields=["is_active"])
            logout(request)
            messages.info(request, "Your HireNexa account has been deactivated and scheduled for deletion.")
            return redirect("home")

    context = {
        "active_tab": "privacy",
        "user_settings": user_settings,
    }
    return render(request, "accounts/settings/privacy.html", context)


@login_required
def settings_appearance_view(request):
    """Theme switcher (Light / Dark / System), typography size, compact density."""
    user = request.user
    user_settings = user.user_settings

    if request.method == "POST":
        theme_val = request.POST.get("theme", "system")
        font_size_val = request.POST.get("font_size", "normal")
        compact_val = request.POST.get("compact_mode") == "on"
        reduce_motion_val = request.POST.get("reduce_motion") == "on"

        user_settings.theme = theme_val
        user_settings.font_size = font_size_val
        user_settings.compact_mode = compact_val
        user_settings.reduce_motion = reduce_motion_val
        user_settings.save(update_fields=["theme", "font_size", "compact_mode", "reduce_motion"])

        AuditLog.objects.create(
            user=user,
            action="APPEARANCE_UPDATED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"theme": theme_val, "compact_mode": compact_val},
        )
        messages.success(request, "Appearance and UI display preferences saved.")
        return redirect("settings_appearance")

    context = {
        "active_tab": "appearance",
        "user_settings": user_settings,
    }
    return render(request, "accounts/settings/appearance.html", context)


@login_required
def settings_connected_accounts_view(request):
    """Connected OAuth identity providers (Google, LinkedIn, GitHub)."""
    context = {
        "active_tab": "connected_accounts",
    }
    return render(request, "accounts/settings/connected_accounts.html", context)


@login_required
def settings_preferences_view(request):
    """Candidate/Freelancer job preferences, salary expectations, remote status."""
    user = request.user
    user_settings = user.user_settings

    if request.method == "POST":
        desired_role = request.POST.get("desired_role", "").strip()
        target_salary = request.POST.get("target_salary", "").strip()
        preferred_location = request.POST.get("preferred_location", "").strip()
        remote_preference = request.POST.get("remote_preference", "ANY")
        availability = request.POST.get("availability_status", "AVAILABLE")

        user_settings.availability_status = availability
        user_settings.job_preferences = {
            "desired_role": desired_role,
            "target_salary": target_salary,
            "preferred_location": preferred_location,
            "remote_preference": remote_preference,
        }
        user_settings.save(update_fields=["availability_status", "job_preferences"])

        messages.success(request, "Job preferences and career availability saved.")
        return redirect("settings_preferences")

    prefs = user_settings.job_preferences or {}
    context = {
        "active_tab": "preferences",
        "user_settings": user_settings,
        "job_prefs": prefs,
    }
    return render(request, "accounts/settings/preferences.html", context)


@login_required
def settings_payout_view(request):
    """Freelancer bank account and payout details (masked)."""
    user = request.user
    user_settings = user.user_settings

    if request.method == "POST":
        bank_name = request.POST.get("bank_name", "").strip()
        acc_num = request.POST.get("account_number", "").strip()
        ifsc_code = request.POST.get("ifsc_swift", "").strip()
        tax_id = request.POST.get("pan_tax_id", "").strip()

        # Mask account number
        masked_num = acc_num[-4:].rjust(len(acc_num), "•") if len(acc_num) >= 4 else acc_num

        user_settings.payout_details = {
            "bank_name": bank_name,
            "account_number_masked": masked_num,
            "ifsc_swift": ifsc_code,
            "pan_tax_id": tax_id,
        }
        user_settings.save(update_fields=["payout_details"])

        AuditLog.objects.create(
            user=user,
            action="PAYOUT_DETAILS_UPDATED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
        messages.success(request, "Freelance payout and bank credentials updated securely.")
        return redirect("settings_payout")

    payout = user_settings.payout_details or {}
    context = {
        "active_tab": "payout",
        "user_settings": user_settings,
        "payout": payout,
    }
    return render(request, "accounts/settings/payout.html", context)


@login_required
def settings_company_view(request):
    """HR / Recruiter company profile, branding, and culture settings."""
    user = request.user
    org_member = OrganizationMember.objects.filter(user=user, is_active=True).first()
    org = org_member.organization if org_member else None

    if request.method == "POST" and org:
        org.name = request.POST.get("name", org.name).strip()
        org.website = request.POST.get("website", org.website).strip()
        org.industry = request.POST.get("industry", org.industry).strip()
        org.company_size = request.POST.get("company_size", org.company_size).strip()
        org.location = request.POST.get("location", org.location).strip()
        org.description = request.POST.get("description", org.description).strip()

        if "logo" in request.FILES:
            org.logo = request.FILES["logo"]

        org.save()

        AuditLog.objects.create(
            user=user,
            action="ORGANIZATION_PROFILE_UPDATED",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"org_id": org.id, "org_name": org.name},
        )
        messages.success(request, "Company branding and profile updated.")
        return redirect("settings_company")

    context = {
        "active_tab": "company",
        "org": org,
        "org_member": org_member,
    }
    return render(request, "accounts/settings/company.html", context)


@login_required
def settings_team_view(request):
    """HR / Recruiter team seats and member permissions."""
    user = request.user
    org_member = OrganizationMember.objects.filter(user=user, is_active=True).first()
    org = org_member.organization if org_member else None

    members = OrganizationMember.objects.filter(organization=org).select_related("user") if org else []

    context = {
        "active_tab": "team",
        "org": org,
        "org_member": org_member,
        "members": members,
    }
    return render(request, "accounts/settings/team.html", context)


@login_required
def settings_platform_view(request):
    """
    PLATFORM OWNER / SUPER ADMIN Governance Settings:
    General, Email & SMTP, RBAC, Feature Toggles, Moderation, Audit Logs, and System Health.
    Strictly restricted to Platform Owner / Superadmin.
    """
    user = request.user
    if not (user.is_owner or user.is_superuser):
        messages.error(request, "Access Restricted: Platform Settings require Platform Owner credentials.")
        return redirect("settings_profile")

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "save_general":
            PlatformSetting.set_value("SITE_NAME", request.POST.get("site_name", "HireNexa").strip())
            PlatformSetting.set_value("CONTACT_EMAIL", request.POST.get("contact_email", "support@hirenexa.com").strip())
            PlatformSetting.set_value("SEO_TITLE", request.POST.get("seo_title", "").strip())
            messages.success(request, "General platform parameters saved.")

        elif action == "save_features":
            features = ["AI_ASSISTANT_ENABLED", "FREELANCE_MODULE_ENABLED", "REGISTRATIONS_OPEN", "MAINTENANCE_MODE"]
            for f in features:
                val = "True" if request.POST.get(f) == "on" else "False"
                PlatformSetting.set_value(f, val)
            messages.success(request, "Platform feature toggles updated.")

        elif action == "save_security_policy":
            PlatformSetting.set_value("SESSION_TIMEOUT_MINUTES", request.POST.get("session_timeout", "240").strip())
            PlatformSetting.set_value("REQUIRE_JOB_APPROVAL", "True" if request.POST.get("require_job_approval") == "on" else "False")
            PlatformSetting.set_value("OTP_EXPIRY_MINUTES", request.POST.get("otp_expiry", "15").strip())
            messages.success(request, "Platform security policy and timeout limits updated.")

        elif action == "test_email":
            test_target = request.POST.get("test_email_target", user.email).strip()
            try:
                send_mail(
                    subject="HireNexa SMTP Diagnostic Test",
                    message="This is a test notification confirming that HireNexa SMTP configuration is operational.",
                    from_email="HireNexa System <system@hirenexa.com>",
                    recipient_list=[test_target],
                    fail_silently=False,
                )
                messages.success(request, f"Test email dispatched successfully to {test_target}.")
            except Exception as e:
                messages.error(request, f"SMTP delivery failure: {e}")

        elif action == "export_audit_csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="hirenexa_audit_log_{timezone.now():%Y%m%d_%H%M%S}.csv"'
            writer = csv.writer(response)
            writer.writerow(["Timestamp", "User", "Action", "Resource Type", "Resource ID", "IP Address", "User Agent"])
            for log in AuditLog.objects.select_related("user").all()[:1000]:
                writer.writerow([
                    log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    log.user.username if log.user else "Anonymous",
                    log.action,
                    log.resource_type,
                    log.resource_id,
                    log.ip_address,
                    log.user_agent[:60],
                ])
            return response

        return redirect("settings_platform")

    # Fetch configuration keys
    settings_map = {item.key: item.value for item in PlatformSetting.objects.all()}
    audit_logs = AuditLog.objects.select_related("user").all()[:20]

    # System Health Metrics
    total_users = User.objects.count()
    total_jobs = Job.objects.count()
    total_applications = Application.objects.count()

    context = {
        "active_tab": "platform",
        "settings_map": settings_map,
        "audit_logs": audit_logs,
        "total_users": total_users,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "server_time": timezone.now(),
    }
    return render(request, "accounts/settings/platform.html", context)
