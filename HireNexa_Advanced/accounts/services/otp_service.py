import logging
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from accounts.models import User, OTPChallenge, OTPAttempt, VerificationEvent
from accounts.services.delivery import EmailDeliveryService, SMSDeliveryService
from accounts.services.sms_provider import normalize_to_e164
from accounts.services.rate_limiter import RateLimiter

logger = logging.getLogger("accounts.security")


def get_otp_expiry_minutes() -> int:
    secs = int(getattr(settings, "OTP_EXPIRY_SECONDS", 300))
    return max(1, secs // 60)


def get_resend_cooldown_seconds() -> int:
    return int(getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60))


def get_max_resends_per_hour() -> int:
    return int(getattr(settings, "OTP_MAX_HOURLY_SENDS", 5))


def get_max_attempts_per_challenge() -> int:
    return int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))


def _extract_ip(request) -> str:
    if not request:
        return ""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "").strip()


class OTPService:
    """
    Central Coordinator for Cryptographic OTP Lifecycle Management:
    - 6-digit secrets-based generation & Hashing (HMAC-SHA256)
    - Honest Delivery Dispatch and status reporting
    - Attempt Limiting (Max 5 attempts) & Lockout
    - 5-Minute Expiry (Configurable via OTP_EXPIRY_SECONDS)
    - 60-Second Resend Cooldown (Configurable via OTP_RESEND_COOLDOWN_SECONDS)
    - Rate-limiting per user/recipient and client IP (Max 5 sends per hour)
    - Single-use consumption (consumed_at timestamp)
    - Constant-time comparison
    - Verification Audit Trails
    """

    @classmethod
    def clean_identifier(cls, identifier: str, channel: str) -> str:
        ident = (identifier or "").strip()
        if channel == OTPChallenge.Channel.EMAIL:
            return ident.lower()
        return normalize_to_e164(ident)

    @classmethod
    def issue_challenge(
        cls,
        recipient: str = None,
        channel: str = OTPChallenge.Channel.EMAIL,
        purpose: str = OTPChallenge.Purpose.LOGIN,
        user: User = None,
        request=None,
        portal: str = None,
        identifier: str = None,
    ):
        """
        Issues and dispatches a new OTP challenge.
        Enforces cooldown and hourly limits.
        Invalidates older active challenges for this destination.
        """
        raw_ident = identifier or recipient or ""
        clean_id = cls.clean_identifier(raw_ident, channel)
        client_ip = _extract_ip(request)
        cooldown_seconds = get_resend_cooldown_seconds()
        max_hourly = get_max_resends_per_hour()
        validity_minutes = get_otp_expiry_minutes()
        max_attempts = get_max_attempts_per_challenge()

        # 1. Rate Limiting Check (per IP & Recipient)
        if client_ip:
            is_blocked, retry_after, reason = RateLimiter.is_rate_limited(
                ip=client_ip,
                identifier=clean_id,
                portal=f"otp_{portal or 'global'}",
                max_attempts=10,
                window_seconds=900,
            )
            if is_blocked:
                logger.warning(
                    "OTP issuance rate limited for IP %s / Recipient %s. %s",
                    client_ip,
                    clean_id[:4] + "***",
                    reason,
                )
                return {
                    "success": False,
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many verification requests. Please wait {retry_after} seconds before trying again.",
                    "cooldown_remaining": retry_after,
                }

        # 2. Hourly Rate Limit Check (Max per hour per destination and per IP)
        one_hour_ago = timezone.now() - timedelta(hours=1)
        hourly_count = OTPChallenge.objects.filter(
            models.Q(identifier__iexact=clean_id) | models.Q(recipient__iexact=clean_id),
            channel=channel,
            created_at__gte=one_hour_ago,
        ).count()

        if hourly_count >= max_hourly:
            return {
                "success": False,
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests for this destination. Please try again after 1 hour.",
                "cooldown_remaining": 3600,
            }

        if client_ip:
            ip_hourly_count = OTPChallenge.objects.filter(
                ip=client_ip,
                created_at__gte=one_hour_ago,
            ).count()
            if ip_hourly_count >= max_hourly * 3:
                return {
                    "success": False,
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests from your IP address. Please try again after 1 hour.",
                    "cooldown_remaining": 3600,
                }

        # 3. Resend Cooldown Check
        latest_challenge = OTPChallenge.objects.filter(
            models.Q(identifier__iexact=clean_id) | models.Q(recipient__iexact=clean_id),
            channel=channel,
            purpose=purpose,
        ).order_by("-created_at").first()

        if latest_challenge:
            cooldown_left = latest_challenge.cooldown_seconds_remaining(cooldown_seconds)
            if cooldown_left > 0:
                return {
                    "success": False,
                    "error_code": "COOLDOWN_ACTIVE",
                    "message": f"Please wait {cooldown_left} seconds before requesting a new code.",
                    "cooldown_remaining": cooldown_left,
                    "cooldown": cooldown_left,
                }

        # 4. Generate Secrets-based Challenge (HMAC-SHA256 hashed, configurable expiry and max attempts)
        challenge, raw_otp = OTPChallenge.create_challenge(
            recipient=clean_id,
            identifier=clean_id,
            channel=channel,
            purpose=purpose,
            user=user,
            validity_minutes=validity_minutes,
            max_attempts=max_attempts,
            ip=client_ip or "",
            portal=portal or "",
        )

        # Sync with legacy PhoneOTP model for backward compatibility
        if channel == OTPChallenge.Channel.SMS:
            try:
                from accounts.models import PhoneOTP
                raw_target = recipient or clean_id
                PhoneOTP.objects.filter(phone_number__in=[clean_id, raw_target], is_used=False).update(is_used=True)
                PhoneOTP.objects.create(
                    phone_number=raw_target,
                    user=user,
                    otp_code=raw_otp,
                    purpose=PhoneOTP.Purpose.LOGIN if purpose == OTPChallenge.Purpose.LOGIN else PhoneOTP.Purpose.VERIFY,
                    expires_at=timezone.now() + timedelta(minutes=validity_minutes),
                )
            except Exception:
                pass

        # 5. Dispatch via Configured Service
        recipient_name = user.full_name if user else "User"
        if channel == OTPChallenge.Channel.EMAIL:
            delivery_result = EmailDeliveryService.send_otp_email(
                recipient_email=clean_id,
                user_name=recipient_name,
                raw_otp=raw_otp,
                validity_minutes=validity_minutes,
            )
        else:
            delivery_result = SMSDeliveryService.send_otp_sms(
                e164_phone_number=clean_id,
                raw_otp=raw_otp,
                validity_minutes=validity_minutes,
            )

        is_delivered = delivery_result.get("success", False)
        challenge.delivery_status = delivery_result.get(
            "status",
            OTPChallenge.DeliveryStatus.SENT if is_delivered else OTPChallenge.DeliveryStatus.FAILED,
        )
        challenge.provider_name = delivery_result.get("provider", "")
        challenge.provider_reference_id = delivery_result.get("reference_id", "")
        if delivery_result.get("error"):
            challenge.error_message = delivery_result["error"]
        challenge.save(update_fields=["delivery_status", "provider_name", "provider_reference_id", "error_message"])

        channel_label = "Email verification" if channel == OTPChallenge.Channel.EMAIL else "Mobile"

        # 6. Status Return & Auditing
        if not is_delivered:
            logger.error(
                "Failed to dispatch %s OTP to %s: %s (code: %s)",
                channel,
                clean_id[:4] + "***",
                challenge.error_message,
                delivery_result.get("error_code"),
            )
            VerificationEvent.objects.create(
                user=user,
                event_type="OTP_DISPATCH_FAILED",
                channel=channel,
                recipient=clean_id,
                ip_address=client_ip or None,
                details={
                    "purpose": purpose,
                    "portal": portal or "",
                    "provider": challenge.provider_name,
                    "delivery_status": challenge.delivery_status,
                    "error": challenge.error_message,
                    "error_code": delivery_result.get("error_code"),
                },
            )
            return {
                "success": False,
                "challenge_id": challenge.id,
                "error_code": delivery_result.get("error_code") or "DELIVERY_FAILED",
                "message": delivery_result.get("error") or f"Unable to deliver {channel_label} code. Please try again.",
                "delivery_status": challenge.delivery_status,
                "provider": challenge.provider_name,
                "cooldown_remaining": 0,
            }

        logger.info(
            "Successfully dispatched %s OTP to %s via %s",
            channel,
            clean_id[:4] + "***",
            challenge.provider_name,
        )
        VerificationEvent.objects.create(
            user=user,
            event_type="OTP_CHALLENGE_ISSUED",
            channel=channel,
            recipient=clean_id,
            ip_address=client_ip or None,
            details={
                "purpose": purpose,
                "portal": portal or "",
                "provider": challenge.provider_name,
                "delivery_status": challenge.delivery_status,
                "challenge_id": challenge.id,
            },
        )

        return {
            "success": True,
            "challenge_id": challenge.id,
            "otp": raw_otp,
            "message": f"{channel_label} OTP sent successfully.",
            "delivery_status": challenge.delivery_status,
            "provider": challenge.provider_name,
            "cooldown_remaining": cooldown_seconds,
            "cooldown": cooldown_seconds,
        }

    @classmethod
    def verify_challenge(
        cls,
        recipient: str = None,
        channel: str = OTPChallenge.Channel.EMAIL,
        raw_code: str = "",
        purpose: str = OTPChallenge.Purpose.LOGIN,
        user: User = None,
        request=None,
        portal: str = None,
        identifier: str = None,
        otp: str = None,
        code: str = None,
    ):
        """
        Verifies the user's submitted 6-digit code against the active challenge hash.
        Performs constant-time comparison, decrements attempts, marks single-use consumed on success.
        """
        raw_code = (raw_code or otp or code or "").strip()
        raw_ident = identifier or recipient or ""
        clean_id = cls.clean_identifier(raw_ident, channel)
        client_ip = _extract_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""

        # Find latest active challenge for recipient
        challenge = None
        q_filter = models.Q(identifier__iexact=clean_id) | models.Q(recipient__iexact=clean_id)
        if purpose:
            challenge = OTPChallenge.objects.filter(
                q_filter,
                channel=channel,
                purpose=purpose,
                is_used=False,
            ).order_by("-created_at").first()

        if not challenge:
            challenge = OTPChallenge.objects.filter(
                q_filter,
                channel=channel,
                is_used=False,
            ).order_by("-created_at").first()

        if not challenge:
            challenge = OTPChallenge.objects.filter(
                q_filter,
                channel=channel,
            ).order_by("-created_at").first()

        if not challenge:
            return {
                "success": False,
                "error_code": "NO_CHALLENGE",
                "message": "No active verification request found. Please request a new code.",
            }

        is_valid, err_code, err_msg = challenge.verify(raw_code)

        # Log attempt
        OTPAttempt.objects.create(
            challenge=challenge,
            ip_address=client_ip or None,
            user_agent=user_agent,
            is_successful=is_valid,
            error_reason=err_code if not is_valid else "",
        )

        if not is_valid:
            if client_ip:
                RateLimiter.record_failed_attempt(
                    client_ip,
                    clean_id,
                    portal=f"otp_{portal or 'global'}",
                    window_seconds=900,
                )

            VerificationEvent.objects.create(
                user=user or challenge.user,
                event_type="OTP_VERIFICATION_FAILED",
                channel=channel,
                recipient=clean_id,
                ip_address=client_ip or None,
                details={
                    "reason": err_code,
                    "portal": portal or "",
                    "attempts": challenge.attempts,
                    "attempts_left": challenge.attempts_left,
                },
            )
            return {
                "success": False,
                "error_code": err_code,
                "message": err_msg,
                "attempts_left": challenge.attempts_left,
            }

        # Clear failed attempt tracking on success
        if client_ip:
            RateLimiter.reset_attempts(client_ip, clean_id, portal=f"otp_{portal or 'global'}")

        # On success: update user contact verification status & activate unverified account
        target_user = user or challenge.user
        if target_user:
            now = timezone.now()
            fields_to_update = []
            if channel == OTPChallenge.Channel.EMAIL:
                target_user.is_email_verified = True
                target_user.email_verified_at = now
                fields_to_update.extend(["is_email_verified", "email_verified_at"])
            else:
                target_user.is_phone_verified = True
                target_user.phone_verified_at = now
                fields_to_update.extend(["is_phone_verified", "phone_verified_at"])

            if not target_user.is_active:
                target_user.is_active = True
                fields_to_update.append("is_active")

            target_user.save(update_fields=fields_to_update)

            VerificationEvent.objects.create(
                user=target_user,
                event_type="EMAIL_VERIFIED" if channel == OTPChallenge.Channel.EMAIL else "PHONE_VERIFIED",
                channel=channel,
                recipient=clean_id,
                ip_address=client_ip or None,
                details={"verified_at": now.isoformat(), "portal": portal or ""},
            )

        channel_label = "Email" if channel == OTPChallenge.Channel.EMAIL else "Mobile"
        return {
            "success": True,
            "message": f"{channel_label} verification successful.",
            "channel": channel,
            "user": target_user,
            "verified_at": challenge.verified_at,
            "consumed_at": challenge.consumed_at,
        }
