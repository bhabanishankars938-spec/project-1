import smtplib
import socket
import logging
from dataclasses import dataclass
from typing import Optional
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from accounts.utils import mask_email

logger = logging.getLogger("accounts.email")


@dataclass
class EmailSendResult:
    success: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def __bool__(self):
        return self.success


def send_otp_email(email: str, otp: str, purpose: str = "VERIFY", expiry_minutes: int = 15) -> EmailSendResult:
    """
    Production-grade OTP email dispatch using Django's configured EmailBackend.
    Strict security:
    - Raw OTP is NEVER logged or exposed.
    - Specific SMTP/Network exceptions are caught and logged via logger.exception.
    - Returns EmailSendResult with success boolean and error metadata.
    """
    recipient_email = (email or "").strip().lower()
    if not recipient_email:
        logger.error("send_otp_email called with empty recipient email.")
        return EmailSendResult(
            success=False,
            error_code="EMPTY_RECIPIENT",
            error_message="Recipient email address is required.",
        )

    subject = "Your HireNexa verification code"
    purpose_label = purpose.replace("_", " ").title()

    plain_message = (
        f"Hello,\n\n"
        f"Your HireNexa verification code is: {otp}\n\n"
        f"Purpose: {purpose_label}\n"
        f"This code will expire in {expiry_minutes} minutes.\n\n"
        f"If you did not request this, ignore this email. Never share this code.\n\n"
        f"Regards,\n"
        f"HireNexa Security Team"
    )

    html_message = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 24px; margin: 0; }}
        .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 36px; max-width: 520px; margin: 0 auto; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }}
        .brand {{ font-size: 22px; font-weight: 800; color: #f59e0b; letter-spacing: -0.02em; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }}
        .otp-box {{ background: #0f172a; border: 2px solid #d97706; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0; }}
        .otp-code {{ font-size: 38px; font-weight: 800; letter-spacing: 0.35em; color: #fbbf24; font-family: 'Courier New', Courier, monospace; }}
        .footer {{ font-size: 12px; color: #94a3b8; margin-top: 28px; border-top: 1px solid #334155; padding-top: 18px; line-height: 1.6; }}
        .alert {{ background: rgba(245, 158, 11, 0.1); border-left: 3px solid #f59e0b; padding: 12px 14px; margin: 20px 0; font-size: 13px; color: #fde68a; border-radius: 4px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="brand">🛡️ HIRENEXA CORE</div>
        <p style="font-size: 16px; margin: 0 0 12px 0;">Hello,</p>
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5; margin: 0 0 20px 0;">
          Use the 6-digit verification code below to verify your email address:
        </p>
        <div class="otp-box">
          <div class="otp-code">{otp}</div>
        </div>
        <p style="color: #94a3b8; font-size: 13px; margin: 0 0 16px 0;">
          This code is valid for <strong>{expiry_minutes} minutes</strong>.
        </p>
        <div class="alert">
          ⚠️ <strong>Security Notice:</strong> If you did not request this, ignore this email. Never share this code.
        </div>
        <div class="footer">
          <p style="margin: 0;">Regards,<br><strong style="color: #f1f5f9;">HireNexa Security Team</strong></p>
        </div>
      </div>
    </body>
    </html>
    """

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or f"HireNexa <{getattr(settings, 'EMAIL_HOST_USER', 'noreply@hirenexa.com')}>"

    # Pre-flight check: if SMTP backend is configured, credentials must be present
    if "smtp" in getattr(settings, "EMAIL_BACKEND", "").lower():
        if not getattr(settings, "EMAIL_HOST_USER", "") or not getattr(settings, "EMAIL_HOST_PASSWORD", ""):
            logger.error("Cannot dispatch email: EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is not configured in .env")
            return EmailSendResult(
                success=False,
                error_code="MISSING_CREDENTIALS",
                error_message="SMTP credentials (EMAIL_HOST_USER, EMAIL_HOST_PASSWORD) are missing in .env.",
            )

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=from_email,
            to=[recipient_email],
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)

        logger.info("OTP verification email dispatched to recipient: %s [purpose=%s]", mask_email(recipient_email), purpose)
        return EmailSendResult(success=True)

    except smtplib.SMTPAuthenticationError as exc:
        logger.exception("SMTP Authentication failed (535) for %s: Code %s (%s)", mask_email(recipient_email), exc.smtp_code, exc.smtp_error)
        return EmailSendResult(
            success=False,
            error_code="SMTP_AUTH_FAILED",
            error_message="SMTP Authentication failed. Please verify your Gmail App Password.",
        )

    except smtplib.SMTPRecipientsRefused as exc:
        logger.exception("SMTP Recipient refused: %s", mask_email(recipient_email))
        return EmailSendResult(
            success=False,
            error_code="RECIPIENT_REFUSED",
            error_message="The recipient address was rejected by the mail server.",
        )

    except smtplib.SMTPSenderRefused as exc:
        logger.exception("SMTP Sender refused for %s: %s", mask_email(recipient_email), str(exc))
        return EmailSendResult(
            success=False,
            error_code="SENDER_REFUSED",
            error_message="The sender address was rejected by the mail server.",
        )

    except smtplib.SMTPServerDisconnected as exc:
        logger.exception("SMTP Server disconnected unexpectedly during dispatch to %s", mask_email(recipient_email))
        return EmailSendResult(
            success=False,
            error_code="SERVER_DISCONNECTED",
            error_message="The SMTP server unexpectedly disconnected.",
        )

    except (socket.timeout, TimeoutError) as exc:
        logger.exception("SMTP Connection timeout during dispatch to %s", mask_email(recipient_email))
        return EmailSendResult(
            success=False,
            error_code="TIMEOUT",
            error_message="Connection timed out while connecting to the email server.",
        )

    except (OSError, ConnectionRefusedError) as exc:
        logger.exception("Network/Port connection error connecting to %s for %s", getattr(settings, "EMAIL_HOST", "SMTP"), mask_email(recipient_email))
        return EmailSendResult(
            success=False,
            error_code="CONNECTION_ERROR",
            error_message="Network error: Port 587/465 may be blocked or unreachable.",
        )

    except smtplib.SMTPException as exc:
        logger.exception("SMTPException occurred while dispatching email to %s: %s", mask_email(recipient_email), str(exc))
        return EmailSendResult(
            success=False,
            error_code="SMTP_ERROR",
            error_message="A mail delivery error occurred.",
        )

    except Exception as exc:
        logger.exception("Unexpected error dispatching verification email to %s: %s", mask_email(recipient_email), str(exc))
        return EmailSendResult(
            success=False,
            error_code="UNKNOWN_ERROR",
            error_message="An unexpected error occurred while dispatching email.",
        )
