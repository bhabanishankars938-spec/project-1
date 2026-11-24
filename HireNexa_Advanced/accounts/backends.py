import re
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class MultiIdentifierModelBackend(ModelBackend):
    """
    Enterprise Authentication Backend for HireNexa supporting:
    1. Username (case-insensitive)
    2. Email Address (case-insensitive, whitespace trimmed, normalized)
    3. Mobile Phone Number (E.164 and local 10-digit formats)
    4. Strict portal role boundary checking when portal parameter is supplied
    """

    def authenticate(self, request, username=None, password=None, portal=None, **kwargs):
        identifier = username or kwargs.get("email") or kwargs.get("phone") or kwargs.get("identifier")
        portal_name = portal or kwargs.get("portal")
        if not identifier or not password:
            return None

        user = self.find_user(identifier)
        if user and user.check_password(password):
            if self.user_can_authenticate(user):
                if portal_name and not self.is_portal_authorized(user, portal_name):
                    return None
                return user
        return None

    @classmethod
    def is_portal_authorized(cls, user, portal: str = None) -> bool:
        """
        Validates whether a user's role is authorized for the designated portal.
        Platform Owners and superusers have Tier-0 administrative access across all portals.
        """
        if not portal or portal.lower() in ("unified", "default", "login", ""):
            return True

        p = portal.lower().strip()
        role = str(getattr(user, "role", "") or "").upper()
        is_owner = (
            role in (getattr(user.Role, "OWNER", "OWNER"), "OWNER")
            or getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or getattr(user, "is_owner", False)
        )

        if is_owner:
            return True

        if p in ("owner",):
            return is_owner
        if p in ("hr", "company", "recruiter"):
            return role in (
                getattr(user.Role, "RECRUITER", "RECRUITER"),
                getattr(user.Role, "COMPANY_ADMIN", "COMPANY_ADMIN"),
                "RECRUITER",
                "COMPANY_ADMIN",
            )
        if p in ("candidate", "student"):
            return role in (getattr(user.Role, "CANDIDATE", "CANDIDATE"), "CANDIDATE")
        if p in ("freelancer",):
            return role in (getattr(user.Role, "FREELANCER", "FREELANCER"), "FREELANCER")

        return False

    @classmethod
    def find_user(cls, identifier):
        """
        Lookup a user across Username, Email ID, or Mobile Phone Number.
        Supports local format and international E.164 formats (+91 9876543210, 9876543210).
        Handles whitespace trimming, case-insensitivity, and phone normalization.
        """
        if not identifier:
            return None
        ident = str(identifier).strip()
        if not ident:
            return None

        # 1. Direct username lookup (case-insensitive)
        user = User.objects.filter(username__iexact=ident).first()
        if user:
            return user

        # 2. Email lookup (case-insensitive, normalized)
        user = User.objects.filter(email__iexact=ident).first()
        if user:
            return user
        if ident.lower() != ident:
            user = User.objects.filter(email__iexact=ident.lower()).first()
            if user:
                return user

        # 3. Phone number lookup (match exact, E.164, or last 10 digits)
        digits = re.sub(r"[^\d]", "", ident)
        if len(digits) >= 8:
            phone_q = (
                Q(phone_number__iexact=ident)
                | Q(phone_number__iexact=f"+{digits}")
                | Q(phone_number__iexact=digits)
                | Q(phone_number__endswith=digits[-10:])
                | Q(phone_number__icontains=digits[-10:])
            )
            user = User.objects.filter(phone_q).first()
            if user:
                return user

        # 4. Fallback search across username or email
        user = User.objects.filter(Q(email__iexact=ident) | Q(email__iexact=ident.lower()) | Q(username__iexact=ident)).first()
        return user
