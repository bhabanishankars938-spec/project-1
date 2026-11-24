import random
import secrets
from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Platform Owner / Super Admin"
        COMPANY_ADMIN = "COMPANY_ADMIN", "Company Admin"
        RECRUITER = "RECRUITER", "HR / Recruiter"
        FREELANCER = "FREELANCER", "Freelancer"
        CANDIDATE = "CANDIDATE", "Student / Candidate"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CANDIDATE,
        help_text="Primary platform role with strict role-based access control.",
    )
    phone_number = models.CharField(
        max_length=25,
        blank=True,
        null=True,
        unique=True,
        help_text="User mobile phone number with country code (e.g. +91 9876543210)",
    )
    is_phone_verified = models.BooleanField(
        default=False,
        help_text="Designates whether the user's mobile number has been OTP-verified.",
    )
    is_email_verified = models.BooleanField(
        default=False,
        help_text="Designates whether the user's email address has been verified.",
    )
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    @property
    def phone_verified(self):
        return self.is_phone_verified

    @phone_verified.setter
    def phone_verified(self, value):
        self.is_phone_verified = value

    @property
    def email_verified(self):
        return self.is_email_verified

    @email_verified.setter
    def email_verified(self, value):
        self.is_email_verified = value

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.username

    @property
    def is_owner(self):
        role_str = str(self.role or "").upper()
        return role_str in (self.Role.OWNER, "OWNER") or bool(self.is_superuser)

    @property
    def is_platform_owner(self):
        return self.is_owner

    @property
    def is_company_admin(self):
        return str(self.role or "").upper() in (self.Role.COMPANY_ADMIN, "COMPANY_ADMIN")

    @property
    def is_recruiter(self):
        return str(self.role or "").upper() in (self.Role.RECRUITER, "RECRUITER")

    @property
    def is_freelancer(self):
        return str(self.role or "").upper() in (self.Role.FREELANCER, "FREELANCER")

    @property
    def is_candidate(self):
        return str(self.role or "").upper() in (self.Role.CANDIDATE, "CANDIDATE")

    @property
    def role_short_display(self):
        mapping = {
            self.Role.OWNER: "Platform Owner",
            "OWNER": "Platform Owner",
            self.Role.COMPANY_ADMIN: "Company Admin",
            "COMPANY_ADMIN": "Company Admin",
            self.Role.RECRUITER: "HR Recruiter",
            "RECRUITER": "HR Recruiter",
            self.Role.FREELANCER: "Freelancer",
            "FREELANCER": "Freelancer",
            self.Role.CANDIDATE: "Candidate",
            "CANDIDATE": "Candidate",
        }
        role_key = str(self.role or "").upper()
        return mapping.get(self.role, mapping.get(role_key, self.get_role_display()))

    @property
    def user_settings(self):
        settings_obj, _ = UserSettings.objects.get_or_create(user=self)
        return settings_obj

    @property
    def notif_preferences(self):
        prefs_obj, _ = NotificationPreference.objects.get_or_create(user=self)
        return prefs_obj

    def get_role_badge_class(self):
        mapping = {
            self.Role.OWNER: "owner",
            self.Role.COMPANY_ADMIN: "company_admin",
            self.Role.RECRUITER: "recruiter",
            self.Role.FREELANCER: "freelancer",
            self.Role.CANDIDATE: "candidate",
        }
        return mapping.get(self.role, "candidate")

    def clean(self):
        super().clean()
        if self.phone_number:
            self.phone_number = self.phone_number.strip()
        if not self.phone_number:
            self.phone_number = None

    def save(self, *args, **kwargs):
        if self.phone_number:
            self.phone_number = self.phone_number.strip()
        if not self.phone_number:
            self.phone_number = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class PhoneOTP(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "LOGIN", "Phone Login / 2FA"
        VERIFY = "VERIFY", "Phone Number Verification"
        RESET = "RESET", "Password Reset via Phone"

    phone_number = models.CharField(max_length=25, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="phone_otps",
    )
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.LOGIN)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Phone OTP"
        verbose_name_plural = "Phone OTPs"

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at

    @classmethod
    def generate(cls, phone_number, purpose=Purpose.LOGIN, user=None, validity_minutes=10):
        cls.objects.filter(phone_number=phone_number, purpose=purpose, is_used=False).update(is_used=True)
        code = f"{random.randint(100000, 999999)}"
        expires = timezone.now() + timedelta(minutes=validity_minutes)
        return cls.objects.create(
            phone_number=phone_number,
            user=user,
            otp_code=code,
            purpose=purpose,
            expires_at=expires,
        )

    def __str__(self):
        return f"OTP for {self.phone_number} ({self.purpose}): {self.otp_code}"


class EmailOTP(models.Model):
    class Purpose(models.TextChoices):
        VERIFY = "VERIFY", "Email Address Verification"
        RESET = "RESET", "Password Reset via Email"
        LOGIN = "LOGIN", "Login Two-Factor Email Verification"
        OWNER_SETUP = "OWNER_SETUP", "Platform Owner Initialization"

    email = models.EmailField(db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="email_otps",
    )
    otp_hash = models.CharField(max_length=255, db_index=True, default="")
    otp_code = models.CharField(max_length=6, blank=True, default="")  # Zero plaintext: kept blank
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.VERIFY)
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Email OTP"
        verbose_name_plural = "Email OTPs"

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at and self.attempts < 5

    @classmethod
    def can_request_otp(cls, email, purpose=Purpose.VERIFY, cooldown_seconds=60, max_per_hour=5):
        """
        Abuse prevention:
        - 60-second cooldown between requests for the same email & purpose.
        - Maximum 5 requests per hour per email.
        Returns: (can_request: bool, error_message: str, remaining_seconds: int)
        """
        now = timezone.now()
        normalized_email = email.lower().strip()

        # Check per-email hourly limit
        hour_ago = now - timedelta(hours=1)
        hourly_count = cls.objects.filter(
            email__iexact=normalized_email,
            created_at__gte=hour_ago
        ).count()
        if hourly_count >= max_per_hour:
            return False, "Rate limit reached: Maximum 5 verification codes per hour. Please wait before trying again.", 3600

        # Check cooldown from latest OTP request
        last_otp = cls.objects.filter(
            email__iexact=normalized_email,
            purpose=purpose
        ).order_by("-created_at").first()

        if last_otp:
            elapsed = (now - last_otp.created_at).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = int(cooldown_seconds - elapsed)
                return False, f"Please wait {remaining} seconds before requesting a new code.", remaining

        return True, "", 0

    @classmethod
    def generate(cls, email, purpose=Purpose.VERIFY, user=None, validity_minutes=15):
        """
        Generates a cryptographically secure 6-digit OTP using secrets.randbelow.
        Stores ONLY the Argon2/Django hash in database.
        Returns: (otp_instance, raw_code)
        """
        normalized_email = email.lower().strip()

        # Invalidate any existing unused OTPs for this email and purpose
        cls.objects.filter(
            email__iexact=normalized_email,
            purpose=purpose,
            is_used=False
        ).update(is_used=True)

        # Cryptographically secure 6-digit integer from 100000 to 999999
        raw_code = f"{secrets.randbelow(900000) + 100000}"
        otp_hash = make_password(raw_code)
        expires = timezone.now() + timedelta(minutes=validity_minutes)

        record = cls.objects.create(
            email=normalized_email,
            user=user,
            otp_hash=otp_hash,
            otp_code="",  # Zero plaintext code in database
            purpose=purpose,
            expires_at=expires,
            attempts=0,
            is_used=False,
        )
        return record, raw_code

    def check_code(self, candidate_code):
        """
        Validates candidate_code in constant-time using check_password.
        Increments attempts on failure.
        Locks and marks is_used=True if attempts >= 5.
        Marks is_used=True upon successful verification.
        Returns: (is_valid: bool, status_reason: str)
        """
        if self.is_used:
            return False, "ALREADY_USED"

        if timezone.now() > self.expires_at:
            return False, "EXPIRED"

        if self.attempts >= 5:
            self.is_used = True
            self.save(update_fields=["is_used"])
            return False, "LOCKED"

        clean_code = str(candidate_code).strip()
        if check_password(clean_code, self.otp_hash):
            self.is_used = True
            self.save(update_fields=["is_used"])
            return True, "SUCCESS"
        else:
            self.attempts += 1
            if self.attempts >= 5:
                self.is_used = True
                self.save(update_fields=["attempts", "is_used"])
                return False, "LOCKED"
            self.save(update_fields=["attempts"])
            return False, "INVALID"

    def __str__(self):
        return f"Email OTP for {self.email} ({self.purpose}) [Used={self.is_used}, Attempts={self.attempts}]"


class AuditLog(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    organization_id = models.IntegerField(null=True, blank=True)
    organization_name = models.CharField(max_length=160, blank=True)
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=60, blank=True)
    resource_id = models.CharField(max_length=60, blank=True)
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        actor = self.user.username if self.user else "Anonymous"
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {actor}: {self.action}"


class PlatformSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "Platform Setting"
        verbose_name_plural = "Platform Settings"

    def __str__(self):
        return f"{self.key}={self.value}"

    @classmethod
    def get_value(cls, key, default=""):
        from django.core.cache import cache
        cache_key = f"platform_setting_{key}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        try:
            item = cls.objects.filter(key=key).first()
            val = item.value if item else default
            cache.set(cache_key, val, timeout=300)
            return val
        except Exception:
            return default

    @classmethod
    def set_value(cls, key, value, description=""):
        from django.core.cache import cache
        obj, _ = cls.objects.update_or_create(
            key=key,
            defaults={"value": str(value), "description": description},
        )
        cache.set(f"platform_setting_{key}", str(value), timeout=300)
        cache.delete("platform_settings_all_dict")
        return obj


# ==============================================================================
# ENTERPRISE OTP VERIFICATION & AUDIT MODELS
# ==============================================================================

class OTPChallenge(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"

    class Purpose(models.TextChoices):
        LOGIN = "LOGIN", "Login Authentication"
        VERIFY = "VERIFY", "Verification"
        RESET = "RESET", "Password Reset"
        REGISTRATION = "REGISTRATION", "Registration Verification"
        PASSWORD_RESET = "PASSWORD_RESET", "Password Reset"
        CHANGE_CONTACT = "CHANGE_CONTACT", "Change Contact Info"

    class DeliveryStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        NOT_CONFIGURED = "NOT_CONFIGURED", "Provider Not Configured"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="otp_challenges"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=255, db_index=True)
    identifier = models.CharField(max_length=255, db_index=True, blank=True, default="")
    purpose = models.CharField(max_length=30, choices=Purpose.choices, default=Purpose.LOGIN)
    otp_hash = models.CharField(max_length=128)  # HMAC-SHA256 salted hash
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    attempts_left = models.PositiveIntegerField(default=5)
    max_attempts = models.PositiveIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    consumed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    ip = models.CharField(max_length=45, blank=True, default="")
    portal = models.CharField(max_length=30, blank=True, default="")
    delivery_status = models.CharField(
        max_length=30, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    provider_name = models.CharField(max_length=60, blank=True)
    provider_reference_id = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "OTP Challenge"
        verbose_name_plural = "OTP Challenges"
        indexes = [
            models.Index(fields=["recipient", "channel", "is_used"]),
            models.Index(fields=["identifier", "channel", "is_used"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["portal"]),
            models.Index(fields=["ip"]),
        ]

    def save(self, *args, **kwargs):
        if not self.identifier and self.recipient:
            self.identifier = self.recipient
        elif not self.recipient and self.identifier:
            self.recipient = self.identifier
        if not self.attempts_left and self.max_attempts:
            self.attempts_left = max(0, self.max_attempts - self.attempts)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def can_attempt(self):
        return not self.is_used and not self.is_expired() and self.attempts_left > 0

    def cooldown_seconds_remaining(self, cooldown_period=60):
        elapsed = (timezone.now() - self.created_at).total_seconds()
        remaining = cooldown_period - elapsed
        return max(0, int(remaining))

    def check_otp(self, raw_code, salt=None):
        """Validates candidate code using verify(), returning boolean."""
        is_valid, _, _ = self.verify(raw_code, salt=salt)
        return is_valid

    def verify(self, raw_code, salt=None):
        if not self.can_attempt():
            if self.is_used:
                return False, "REUSED", "This verification code has already been used. Please request a new code."
            if self.is_expired():
                return False, "EXPIRED", "OTP has expired. Request a new code."
            return False, "MAX_ATTEMPTS", "Too many attempts. Please try again later."

        import hmac, hashlib
        from django.conf import settings
        secret = salt or settings.SECRET_KEY
        candidate_hash = hmac.new(secret.encode("utf-8"), str(raw_code).strip().encode("utf-8"), hashlib.sha256).hexdigest()

        if hmac.compare_digest(self.otp_hash, candidate_hash):
            now = timezone.now()
            self.is_used = True
            self.consumed_at = now
            self.verified_at = now
            self.save(update_fields=["is_used", "consumed_at", "verified_at"])
            if self.channel == self.Channel.SMS:
                try:
                    PhoneOTP.objects.filter(phone_number__in=[self.recipient, self.identifier], is_used=False).update(is_used=True)
                except Exception:
                    pass
            return True, "SUCCESS", "Verification successful."
        else:
            self.attempts += 1
            self.attempts_left = max(0, self.max_attempts - self.attempts)
            if self.attempts >= self.max_attempts or self.attempts_left == 0:
                self.is_used = True
                self.save(update_fields=["attempts", "attempts_left", "is_used"])
                return False, "MAX_ATTEMPTS", "Too many attempts. Please try again later."
            self.save(update_fields=["attempts", "attempts_left"])
            return False, "INVALID", "Invalid OTP. Please try again."

    @classmethod
    def create_challenge(cls, recipient=None, channel=Channel.EMAIL, purpose=Purpose.LOGIN, user=None, validity_minutes=None, max_attempts=None, identifier=None, ip="", portal=""):
        import secrets, hmac, hashlib
        from django.conf import settings

        target_identifier = (identifier or recipient or "").strip()
        if channel == cls.Channel.EMAIL:
            target_identifier = target_identifier.lower()

        # Invalidate previous unverified challenges for same identifier and purpose
        cls.objects.filter(
            models.Q(recipient__iexact=target_identifier) | models.Q(identifier__iexact=target_identifier),
            channel=channel,
            purpose=purpose,
            is_used=False
        ).update(is_used=True)

        if validity_minutes is None:
            validity_minutes = int(getattr(settings, "OTP_EXPIRY_SECONDS", 300)) // 60
            if validity_minutes < 1:
                validity_minutes = 5
        if max_attempts is None:
            max_attempts = int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))

        otp_length = int(getattr(settings, "OTP_LENGTH", 6))
        min_v = 10 ** (otp_length - 1)
        max_v = (10 ** otp_length) - 1
        raw_code = f"{secrets.randbelow(max_v - min_v + 1) + min_v}"

        secret = settings.SECRET_KEY
        otp_hash = hmac.new(secret.encode("utf-8"), raw_code.encode("utf-8"), hashlib.sha256).hexdigest()
        expires = timezone.now() + timedelta(minutes=validity_minutes)

        challenge = cls.objects.create(
            user=user,
            channel=channel,
            recipient=target_identifier,
            identifier=target_identifier,
            purpose=purpose,
            otp_hash=otp_hash,
            expires_at=expires,
            attempts=0,
            attempts_left=max_attempts,
            max_attempts=max_attempts,
            ip=ip or "",
            portal=portal or "",
            delivery_status=cls.DeliveryStatus.PENDING,
        )
        return challenge, raw_code

    def check_otp(self, raw_code: str) -> bool:
        """Constant-time verification of raw OTP code against HMAC-SHA256 salted hash."""
        import hmac, hashlib
        from django.conf import settings
        from django.utils.crypto import constant_time_compare

        if not raw_code:
            return False
        clean_code = str(raw_code).strip()
        expected_hash = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            clean_code.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return constant_time_compare(self.otp_hash, expected_hash)

    def __str__(self):
        status = "Used" if self.is_used else ("Expired" if self.is_expired() else "Active")
        return f"{self.channel} OTP for {self.recipient} ({status}) [{self.attempts_left} attempts left]"


class OTPAttempt(models.Model):
    challenge = models.ForeignKey(OTPChallenge, on_delete=models.CASCADE, related_name="attempt_logs")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    is_successful = models.BooleanField(default=False)
    error_reason = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "OTP Attempt"
        verbose_name_plural = "OTP Attempts"


class VerificationEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="verification_events")
    event_type = models.CharField(max_length=60)
    channel = models.CharField(max_length=20, blank=True)
    recipient = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Verification Event"
        verbose_name_plural = "Verification Events"

    def __str__(self):
        target = self.user.username if self.user else self.recipient
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {self.event_type} for {target}"


# ==============================================================================
# PRO SETTINGS & SESSION GOVERNANCE MODELS
# ==============================================================================

class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")

    # Appearance
    theme = models.CharField(
        max_length=20,
        choices=[("light", "Light"), ("dark", "Dark"), ("system", "System Default")],
        default="system",
    )
    font_size = models.CharField(
        max_length=20,
        choices=[("normal", "Normal (Default)"), ("medium", "Medium (+2px)"), ("large", "Large (+4px)")],
        default="normal",
    )
    compact_mode = models.BooleanField(default=False)
    reduce_motion = models.BooleanField(default=False)

    # Account & Localization
    timezone = models.CharField(max_length=60, default="Asia/Kolkata")
    language = models.CharField(max_length=10, default="en")
    date_format = models.CharField(max_length=20, default="YYYY-MM-DD")
    time_format = models.CharField(max_length=10, default="24h")

    # Extended Profile Details
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    headline = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    website_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)

    # Security & 2FA
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_method = models.CharField(
        max_length=20,
        choices=[("EMAIL", "Email OTP"), ("TOTP", "Authenticator App (TOTP)")],
        default="EMAIL",
    )
    backup_codes = models.JSONField(default=list, blank=True)
    suspicious_login_alerts = models.BooleanField(default=True)

    # Privacy & Access
    profile_visibility = models.CharField(
        max_length=20,
        choices=[
            ("PUBLIC", "Public (Visible to everyone)"),
            ("RECRUITERS", "Verified Recruiters Only"),
            ("PRIVATE", "Private (Only applied jobs)"),
        ],
        default="RECRUITERS",
    )
    resume_visibility = models.CharField(
        max_length=20,
        choices=[
            ("PUBLIC", "Public"),
            ("RECRUITERS", "Verified Recruiters Only"),
            ("PRIVATE", "Private"),
        ],
        default="RECRUITERS",
    )
    hide_phone = models.BooleanField(default=False)
    hide_email = models.BooleanField(default=False)

    # Candidate & Freelancer Preferences
    availability_status = models.CharField(
        max_length=30,
        choices=[
            ("AVAILABLE", "Available Immediately"),
            ("NOTICE", "Serving Notice / Open to Offers"),
            ("NOT_LOOKING", "Not Looking Currently"),
        ],
        default="AVAILABLE",
    )
    job_preferences = models.JSONField(default=dict, blank=True)
    payout_details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Settings"
        verbose_name_plural = "User Settings"

    def __str__(self):
        return f"Settings for {self.user.username}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_preferences")

    # Email Channels
    email_applications = models.BooleanField(default=True)
    email_interviews = models.BooleanField(default=True)
    email_messages = models.BooleanField(default=True)
    email_job_alerts = models.BooleanField(default=True)
    email_news = models.BooleanField(default=False)
    email_marketing = models.BooleanField(default=False)

    # In-App Channels
    inapp_applications = models.BooleanField(default=True)
    inapp_interviews = models.BooleanField(default=True)
    inapp_messages = models.BooleanField(default=True)
    inapp_job_alerts = models.BooleanField(default=True)
    inapp_news = models.BooleanField(default=True)

    # Push Notification Channel
    push_enabled = models.BooleanField(default=False)

    # Delivery & Quiet Hours
    digest_frequency = models.CharField(
        max_length=20,
        choices=[
            ("INSTANT", "Instant Delivery"),
            ("DAILY", "Daily Digest Summary"),
            ("WEEKLY", "Weekly Digest"),
        ],
        default="INSTANT",
    )
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"Notification Preferences for {self.user.username}"


class LoginHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_history")
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    device_type = models.CharField(max_length=60, blank=True)
    location_city = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Login History"
        verbose_name_plural = "Login History"

    def __str__(self):
        return f"{self.user.username} from {self.ip_address} on {self.created_at:%Y-%m-%d %H:%M}"


