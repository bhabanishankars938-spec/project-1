import logging
import re
from typing import Optional, Dict, Any, Tuple
from django.conf import settings
from django.urls import reverse
from django.contrib.auth import authenticate
from accounts.models import User, AuditLog
from accounts.backends import MultiIdentifierModelBackend
from accounts.services.rate_limiter import RateLimiter
from accounts.decorators import get_client_ip

logger = logging.getLogger("accounts.security")

PORTAL_NAMES = {
    "owner": "Platform Owner Portal",
    "hr": "HR & Recruiter Portal",
    "company": "Company Administration Portal",
    "candidate": "Student & Candidate Portal",
    "student": "Student & Candidate Portal",
    "freelancer": "Freelancer Portal",
    "unified": "Unified Sign-In Portal",
}


class AuthService:
    """
    Unified Authentication Service for HireNexa:
    - Normalizes username, email, and phone identifiers (case-insensitive, whitespace stripped)
    - Enforces portal-isolated rate limiting (per-portal + per-IP + per-identifier)
    - Enforces strict portal role boundaries
    - Differentiates error states (INVALID_CREDENTIALS, RATE_LIMITED, UNVERIFIED, WRONG_PORTAL, DEACTIVATED)
    - Never increments rate-limiting lockout on unverified accounts, deactivated accounts, or wrong portal attempts
    - Clears rate-limiting lockout immediately upon successful authentication
    - Zero user enumeration: returns identical generic error messages for invalid credentials
    """

    @classmethod
    def normalize_identifier(cls, identifier: str) -> str:
        """Standardizes user identifier string for lookups and rate limiting."""
        if not identifier:
            return ""
        ident = str(identifier).strip()
        if "@" in ident:
            return ident.lower()
        # If identifier contains alphabetic characters, treat as username (preserve letters, do not strip)
        if re.search(r"[a-zA-Z]", ident):
            return ident.lower()
        # Phone numbers: remove spaces, hyphens, and brackets
        cleaned_phone = re.sub(r"[^\d+]", "", ident)
        digits = re.sub(r"\D", "", cleaned_phone)
        if len(digits) >= 8:
            return cleaned_phone
        return ident.lower()

    @classmethod
    def resolve_user(cls, identifier: str) -> Optional[User]:
        """Resolves User instance from identifier across Username, Email, or Phone."""
        return MultiIdentifierModelBackend.find_user(identifier)

    @classmethod
    def is_portal_authorized(cls, user: User, portal: str) -> bool:
        """Checks if a user is permitted to sign in to the requested portal."""
        return MultiIdentifierModelBackend.is_portal_authorized(user, portal)

    @classmethod
    def get_portal_display_name(cls, portal: str) -> str:
        return PORTAL_NAMES.get((portal or "").lower(), "Designated Portal")

    @classmethod
    def get_designated_portal_url(cls, user: User) -> str:
        """Determines the correct login portal URL for a user based on role."""
        if not user:
            return reverse("login")
        role = str(getattr(user, "role", "") or "").upper()
        if role in (User.Role.OWNER, "OWNER") or getattr(user, "is_superuser", False) or getattr(user, "is_owner", False):
            return reverse("owner_login")
        if role in (User.Role.RECRUITER, User.Role.COMPANY_ADMIN, "RECRUITER", "COMPANY_ADMIN"):
            return reverse("hr_login")
        if role in (User.Role.FREELANCER, "FREELANCER"):
            return reverse("freelancer_login")
        return reverse("candidate_login")

    @classmethod
    def authenticate_portal(
        cls,
        request,
        identifier: str,
        password: str,
        portal: str = "unified",
    ) -> Dict[str, Any]:
        """
        Authenticates a user for a specific portal:
        Returns dictionary with 'status' and context details:
          - SUCCESS: credentials valid, active, authorized for portal
          - RATE_LIMITED: client IP / identifier exceeded maximum failed attempts
          - INVALID_CREDENTIALS: unknown user OR incorrect password
          - UNVERIFIED: credentials valid, but account pending email/phone verification
          - DEACTIVATED: credentials valid, but account disabled by admin
          - WRONG_PORTAL: credentials valid, but role not permitted on this portal
        """
        client_ip = get_client_ip(request) if request else "127.0.0.1"
        clean_id = cls.normalize_identifier(identifier)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""
        portal_clean = (portal or "unified").lower().strip()

        # 1. Check Rate Limiter (strictly isolated per portal, identifier, and IP)
        is_blocked, retry_after, reason = RateLimiter.is_rate_limited(
            ip=client_ip,
            identifier=clean_id,
            portal=portal_clean,
        )
        if is_blocked:
            minutes = max(1, (retry_after + 59) // 60)
            AuditLog.objects.create(
                action="LOGIN_RATE_LIMIT_EXCEEDED",
                ip_address=client_ip,
                user_agent=user_agent,
                details={
                    "portal": portal_clean.upper(),
                    "identifier": clean_id,
                    "retry_after": retry_after,
                    "reason": reason,
                },
            )
            return {
                "status": "RATE_LIMITED",
                "message": f"Too many failed login attempts. For security, please wait {minutes} minute(s) before trying again.",
                "retry_after": retry_after,
                "retry_minutes": minutes,
                "user": None,
            }

        # 2. Look up user by normalized identifier
        resolved_user = cls.resolve_user(clean_id)
        password_valid = bool(resolved_user and resolved_user.check_password(password))

        # 3. Invalid credentials (Anti-enumeration: identical response whether user exists or not)
        if not resolved_user or not password_valid:
            RateLimiter.record_failed_attempt(
                ip=client_ip,
                identifier=clean_id,
                portal=portal_clean,
            )
            failed_action = f"FAILED_{portal_clean.upper()}_PORTAL_LOGIN" if portal_clean != "unified" else "FAILED_LOGIN_ATTEMPT"
            AuditLog.objects.create(
                user=resolved_user if resolved_user else None,
                action=failed_action,
                ip_address=client_ip,
                user_agent=user_agent,
                details={
                    "portal": portal_clean.upper(),
                    "attempted_identifier": clean_id,
                    "user_exists": bool(resolved_user),
                    "reason": "INVALID_PASSWORD" if resolved_user else "ACCOUNT_NOT_FOUND",
                },
            )
            return {
                "status": "INVALID_CREDENTIALS",
                "message": "Invalid credentials. Please verify your Username/Email/Phone and Password.",
                "user": None,
            }

        # 4. Handle Inactive / Unverified Accounts
        if not resolved_user.is_active:
            if portal_clean == "owner":
                RateLimiter.record_failed_attempt(
                    ip=client_ip,
                    identifier=clean_id,
                    portal=portal_clean,
                )
                AuditLog.objects.create(
                    user=resolved_user,
                    action="FAILED_OWNER_PORTAL_LOGIN",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    details={
                        "reason": "ACCOUNT_INACTIVE",
                        "username": resolved_user.username,
                        "attempted_identifier": clean_id,
                        "portal": "OWNER",
                    },
                )
                return {
                    "status": "INVALID_CREDENTIALS",
                    "user": None,
                    "message": "Access Denied: Invalid administrator credentials. Please check your username/email and password.",
                }

            is_unverified = not resolved_user.is_email_verified and not resolved_user.is_phone_verified
            if is_unverified:
                AuditLog.objects.create(
                    user=resolved_user,
                    action=f"LOGIN_UNVERIFIED_{portal_clean.upper()}_ATTEMPT",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    details={
                        "username": resolved_user.username,
                        "email": resolved_user.email,
                        "phone": resolved_user.phone_number,
                        "portal": portal_clean.upper(),
                    },
                )
                return {
                    "status": "UNVERIFIED",
                    "user": resolved_user,
                    "message": "Your account has been registered but is not yet verified. Please verify your email or phone number.",
                }
            else:
                failed_action = f"FAILED_{portal_clean.upper()}_PORTAL_LOGIN" if portal_clean != "unified" else "FAILED_LOGIN_ATTEMPT"
                AuditLog.objects.create(
                    user=resolved_user,
                    action=failed_action,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    details={
                        "reason": "ACCOUNT_INACTIVE",
                        "username": resolved_user.username,
                        "attempted_identifier": clean_id,
                        "portal": portal_clean.upper(),
                    },
                )
                return {
                    "status": "DEACTIVATED",
                    "user": resolved_user,
                    "message": "Your account has been deactivated. Please contact support.",
                }

        # 5. Check Portal-Specific Role Boundaries
        if not cls.is_portal_authorized(resolved_user, portal_clean):
            if portal_clean == "owner":
                RateLimiter.record_failed_attempt(
                    ip=client_ip,
                    identifier=clean_id,
                    portal=portal_clean,
                )
            AuditLog.objects.create(
                user=resolved_user,
                action=f"UNAUTHORIZED_{portal_clean.upper()}_PORTAL_ATTEMPT",
                ip_address=client_ip,
                user_agent=user_agent,
                details={
                    "identifier": clean_id,
                    "actual_role": resolved_user.role,
                    "target_portal": portal_clean,
                },
            )
            portal_display = cls.get_portal_display_name(portal_clean)
            correct_url = cls.get_designated_portal_url(resolved_user)
            if portal_clean == "owner":
                portal_msg = "Access Denied: Invalid administrator credentials. Please check your username/email and password."
            else:
                portal_msg = (
                    f"Access Denied: Your account role ({resolved_user.get_role_display()}) "
                    f"is not authorized for the {portal_display}. "
                    f"Please sign in via your designated portal."
                )
            return {
                "status": "WRONG_PORTAL",
                "user": resolved_user,
                "portal": portal_clean,
                "portal_display": portal_display,
                "correct_url": correct_url,
                "message": portal_msg,
            }

        # 6. Django Authentication & Lifecycle Integration
        auth_user = authenticate(
            request=request,
            username=clean_id,
            password=password,
            portal=portal_clean,
        )
        final_user = auth_user or resolved_user
        final_user.backend = getattr(final_user, "backend", None) or "accounts.backends.MultiIdentifierModelBackend"

        # Authentication Successful: Reset rate-limiting counter immediately
        RateLimiter.reset_attempts(
            ip=client_ip,
            identifier=clean_id,
            portal=portal_clean,
        )
        if final_user.username != clean_id:
            RateLimiter.reset_attempts(
                ip=client_ip,
                identifier=final_user.username,
                portal=portal_clean,
            )
        if getattr(final_user, "email", None) and final_user.email != clean_id:
            RateLimiter.reset_attempts(
                ip=client_ip,
                identifier=final_user.email,
                portal=portal_clean,
            )

        AuditLog.objects.create(
            user=final_user,
            action=f"{portal_clean.upper()}_LOGIN_SUCCESS",
            ip_address=client_ip,
            user_agent=user_agent,
            details={
                "username": final_user.username,
                "role": final_user.role,
                "portal": portal_clean,
                "login_method": "PASSWORD",
            },
        )

        return {
            "status": "SUCCESS",
            "user": final_user,
            "message": "Authentication successful.",
        }
