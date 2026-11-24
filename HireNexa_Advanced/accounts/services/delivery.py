import os
import logging
import urllib.request
import urllib.parse
import urllib.error
import json
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from accounts.utils import mask_email

logger = logging.getLogger("accounts.security")


class EmailDeliveryService:
    """
    Enterprise Email Delivery Service supporting Resend, SendGrid, AWS SES, and SMTP.
    """

    @classmethod
    def get_provider_status(cls):
        """Returns whether a real email provider is configured."""
        if os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", ""):
            return "CONNECTED", "Resend API"
        if os.environ.get("SENDGRID_API_KEY"):
            return "CONNECTED", "SendGrid API"
        if os.environ.get("AWS_SES_REGION") and os.environ.get("AWS_ACCESS_KEY_ID"):
            return "CONNECTED", "Amazon SES"
        if "console" in getattr(settings, "EMAIL_BACKEND", "").lower():
            return "CONNECTED_DEV", "Django Console Backend (Local Development / Fallback)"
        if getattr(settings, "EMAIL_HOST", None) and getattr(settings, "EMAIL_HOST_USER", None):
            return "CONNECTED", f"SMTP ({settings.EMAIL_HOST})"
        return "NOT_CONFIGURED", "No Email Provider Configured"

    @classmethod
    def send_otp_email(cls, recipient_email, user_name, raw_otp, validity_minutes=15):
        """
        Sends the real OTP email to the user's email address.
        Never logs or exposes the raw_otp in production logs.
        """
        recipient_name = user_name or "User"
        subject = "Your HireNexa verification code"

        if getattr(settings, "DEBUG", False):
            print("\n" + "=" * 65)
            print(f"  [HIRENEXA DEV] VERIFICATION OTP DISPATCHED")
            print(f"  • Recipient : {recipient_email}")
            print(f"  • OTP Code  : {raw_otp}")
            print(f"  • Note      : Check Gmail SPAM / PROMOTIONS folder if not in Inbox.")
            print("=" * 65 + "\n")

        plain_message = (
            f"Hello {recipient_name},\n\n"
            f"Your HireNexa verification code is: {raw_otp}\n\n"
            f"This code is valid for {validity_minutes} minutes.\n"
            f"If you did not request this, ignore this email. Never share this code.\n\n"
            f"Regards,\n"
            f"HireNexa Security Team"
        )

        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 24px; margin: 0; }}
            .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 36px; max-width: 520px; margin: 0 auto; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }}
            .brand {{ font-size: 22px; font-weight: 800; color: #f59e0b; letter-spacing: -0.02em; margin-bottom: 24px; display: flex; align-items: center; gap: 8px; }}
            .otp-box {{ background: #0f172a; border: 2px solid #d97706; border-radius: 10px; padding: 20px; text-align: center; margin: 24px 0; }}
            .otp-code {{ font-size: 38px; font-weight: 800; letter-spacing: 0.35em; color: #fbbf24; font-family: 'Courier New', Courier, monospace; }}
            .footer {{ font-size: 12px; color: #94a3b8; margin-top: 28px; border-top: 1px solid #334155; padding-top: 18px; line-height: 1.6; }}
            .alert {{ background: rgba(245, 158, 11, 0.1); border-left: 3px solid #f59e0b; padding: 12px 14px; margin: 20px 0; font-size: 13px; color: #fde68a; border-radius: 4px; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="brand">🛡️ HIRENEXA CORE</div>
            <p style="font-size: 16px; margin: 0 0 12px 0;">Hello <strong>{recipient_name}</strong>,</p>
            <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5; margin: 0 0 20px 0;">
              Use the 6-digit verification code below to complete your HireNexa authentication:
            </p>
            <div class="otp-box">
              <div class="otp-code">{raw_otp}</div>
            </div>
            <p style="color: #94a3b8; font-size: 13px; margin: 0 0 16px 0;">
              This code is valid for <strong>{validity_minutes} minutes</strong>.
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

        # In test mode or when using Django locmem backend, use Django's core email dispatch directly
        if getattr(settings, "IS_TESTING", False) or "locmem" in getattr(settings, "EMAIL_BACKEND", "").lower():
            from accounts.services.email_service import send_otp_email as core_send_otp_email
            send_res = core_send_otp_email(
                email=recipient_email,
                otp=raw_otp,
                purpose="VERIFY",
                expiry_minutes=validity_minutes,
            )
            return {
                "success": send_res.success,
                "status": "SENT" if send_res.success else "FAILED",
                "provider": "Django Test Backend",
                "reference_id": f"mail_{mask_email(recipient_email)}",
                "error": send_res.error_message,
                "error_code": send_res.error_code,
            }

        resend_key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")
        if resend_key:
            res = cls._send_via_resend(resend_key, recipient_email, recipient_name, subject, html_message, plain_message)
            if res.get("success"):
                return res
            logger.warning("Resend delivery failed (%s), falling back to Django core email backend.", res.get("error"))

        sendgrid_key = os.environ.get("SENDGRID_API_KEY")
        if sendgrid_key:
            res = cls._send_via_sendgrid(sendgrid_key, recipient_email, recipient_name, subject, html_message, plain_message)
            if res.get("success"):
                return res
            logger.warning("SendGrid delivery failed (%s), falling back to Django core email backend.", res.get("error"))

        from accounts.services.email_service import send_otp_email as core_send_otp_email
        send_res = core_send_otp_email(
            email=recipient_email,
            otp=raw_otp,
            purpose="VERIFY",
            expiry_minutes=validity_minutes,
        )
        provider_status, provider_name = cls.get_provider_status()
        return {
            "success": send_res.success,
            "status": "SENT" if send_res.success else "FAILED",
            "provider": provider_name,
            "reference_id": f"mail_{mask_email(recipient_email)}",
            "error": send_res.error_message,
            "error_code": send_res.error_code,
        }

    @classmethod
    def _send_via_resend(cls, api_key, recipient_email, recipient_name, subject, html_content, text_content):
        from_email = os.environ.get("RESEND_FROM_EMAIL") or getattr(settings, "RESEND_FROM_EMAIL", "onboarding@resend.dev")
        # Try official Resend Python SDK if available
        try:
            import resend
            resend.api_key = api_key
            r = resend.Emails.send({
                "from": from_email,
                "to": [recipient_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            })
            msg_id = getattr(r, "id", None) or (r.get("id") if isinstance(r, dict) else "resend_ok")
            logger.info("Resend SDK dispatched email successfully. Message ID: %s", msg_id)
            return {
                "success": True,
                "status": "DELIVERED",
                "provider": "Resend API",
                "reference_id": msg_id,
                "error": None,
            }
        except ImportError:
            pass
        except Exception as sdk_exc:
            logger.warning("Resend SDK dispatch failed, falling back to HTTP REST API: %s", str(sdk_exc))

        # Direct HTTP REST API via urllib (zero external dependency)
        payload = {
            "from": from_email,
            "to": [recipient_email],
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "HireNexa-Auth/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                msg_id = resp_data.get("id", "resend_ok")
                logger.info("Resend REST API dispatched email successfully. Message ID: %s", msg_id)
                return {
                    "success": True,
                    "status": "DELIVERED",
                    "provider": "Resend API",
                    "reference_id": msg_id,
                    "error": None,
                }
        except urllib.error.HTTPError as http_exc:
            err_body = ""
            try:
                err_body = http_exc.read().decode("utf-8")
            except Exception:
                pass
            err_msg = f"{http_exc}: {err_body}" if err_body else str(http_exc)
            logger.error("Resend HTTP delivery failure: %s", err_msg)
            return {
                "success": False,
                "status": "FAILED",
                "provider": "Resend API",
                "reference_id": "",
                "error": err_msg,
            }
        except Exception as exc:
            logger.error("Resend delivery failure: %s", str(exc))
            return {
                "success": False,
                "status": "FAILED",
                "provider": "Resend API",
                "reference_id": "",
                "error": str(exc),
            }

    @classmethod
    def _send_via_sendgrid(cls, api_key, recipient_email, recipient_name, subject, html_content, text_content):
        from_email = os.environ.get("SENDGRID_FROM_EMAIL", "security@hirenexa.internal")
        payload = {
            "personalizations": [{"to": [{"email": recipient_email, "name": recipient_name}]}],
            "from": {"email": from_email, "name": "HireNexa Security Team"},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_content},
                {"type": "text/html", "value": html_content},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "HireNexa-Auth/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {
                    "success": True,
                    "status": "SENT",
                    "provider": "SendGrid API",
                    "reference_id": resp.headers.get("X-Message-Id", "sg_ok"),
                    "error": None,
                }
        except Exception as exc:
            return {
                "success": False,
                "status": "FAILED",
                "provider": "SendGrid API",
                "reference_id": "",
                "error": str(exc),
            }


class SMSDeliveryService:
    """
    Enterprise SMS Delivery Service supporting Twilio, MSG91, and Mock Console Provider.
    Adheres strictly to Indian DLT standards and required text format.
    Delegates to provider abstraction in accounts.services.sms_provider.
    """

    @classmethod
    def get_provider(cls):
        from accounts.services.sms_provider import get_sms_provider
        return get_sms_provider()

    @classmethod
    def get_provider_status(cls):
        """Returns whether a real or mock SMS provider is configured."""
        return cls.get_provider().get_status()

    @classmethod
    def send_otp_sms(cls, e164_phone_number, raw_otp, validity_minutes=10):
        """
        Sends the real OTP SMS to the user's mobile number via configured provider abstraction.
        Message Format:
          HireNexa verification code: ******
          This code expires in 10 minutes. Do not share it with anyone.
        """
        provider = cls.get_provider()
        return provider.send_otp(
            to_number=e164_phone_number,
            otp_code=raw_otp,
            validity_minutes=validity_minutes,
        )

