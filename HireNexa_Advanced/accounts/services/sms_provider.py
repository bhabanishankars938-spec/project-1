import os
import sys
import json
import logging
import uuid
import base64
import re
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger("accounts.sms")


def mask_phone(phone: str) -> str:
    """Masks phone number for privacy in logs (e.g., +919876543210 -> +9198*****210)."""
    if not phone or len(phone) < 6:
        return "****"
    return phone[:5] + "*****" + phone[-2:]


def normalize_to_e164(phone: str, default_country: str = "+91") -> str:
    """
    Normalizes a given mobile phone number to standard E.164 format.
    Defaults to India (+91) for standard 10-digit numbers.
    Examples:
      '9876543210'     -> '+919876543210'
      '09876543210'    -> '+919876543210'
      '+91 9876543210' -> '+919876543210'
      '+14155552671'   -> '+14155552671'
    """
    if not phone:
        return ""
    cleaned = str(phone).strip()
    digits = re.sub(r"[^\d]", "", cleaned)

    if cleaned.startswith("+"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"{default_country}{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"{default_country}{digits[1:]}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    return f"+{digits}" if digits else ""


class BaseSMSBackend(ABC):
    """Abstract Base Class for Pluggable SMS Gateway Backends."""

    @abstractmethod
    def send_otp(self, to_number: str, otp_code: str, validity_minutes: int = 5) -> Dict[str, Any]:
        """
        Dispatches OTP SMS to destination mobile number.
        Returns dictionary with keys:
            - success (bool)
            - status (str: SENT, DELIVERED, FAILED, NOT_CONFIGURED)
            - provider (str)
            - reference_id (str)
            - error (Optional[str])
            - error_code (Optional[str])
        """
        pass

    @abstractmethod
    def get_status(self) -> Tuple[str, str]:
        """Returns tuple (status_code, display_name)."""
        pass


BaseSMSProvider = BaseSMSBackend  # Backward compatibility alias


class ConsoleSMSBackend(BaseSMSBackend):
    """
    Development & Debug Mock SMS Backend.
    Outputs clear, formatted OTP banner to stdout/console and logs.
    Zero external HTTP calls, zero SMS cost.
    """

    def get_status(self) -> Tuple[str, str]:
        return "CONNECTED_DEV", "Console SMS Backend (Terminal / Mock Output)"

    def send_otp(self, to_number: str, otp_code: str, validity_minutes: int = 5) -> Dict[str, Any]:
        normalized = normalize_to_e164(to_number)
        sms_text = (
            f"HireNexa verification code: {otp_code}\n"
            f"This code expires in {validity_minutes} minutes. Do not share it with anyone."
        )

        banner = (
            f"\n"
            f"{'=' * 75}\n"
            f"[HIRENEXA CONSOLE SMS GATEWAY - DEBUG MODE]\n"
            f"Destination Mobile : {normalized or to_number}\n"
            f"Verification OTP   : {otp_code}\n"
            f"Validity Period    : {validity_minutes} minutes\n"
            f"Message Body       :\n"
            f"---------------------------------------------------------------------------\n"
            f"{sms_text}\n"
            f"{'=' * 75}\n"
        )
        print(banner, flush=True)

        logger.info(
            "Console SMS dispatched to %s. OTP Code: %s (expires in %dm)",
            mask_phone(normalized or to_number),
            otp_code,
            validity_minutes
        )

        ref_id = f"console_{uuid.uuid4().hex[:12]}"
        return {
            "success": True,
            "status": "DELIVERED",
            "provider": "Mock ConsoleSMSBackend",
            "reference_id": ref_id,
            "error": None,
            "error_code": None,
        }


MockSMSProvider = ConsoleSMSBackend  # Backward compatibility alias


class MSG91SMSBackend(BaseSMSBackend):
    """Production MSG91 Indian DLT SMS Gateway Backend."""

    def __init__(self):
        self.auth_key = os.environ.get("MSG91_AUTH_KEY", "").strip() or getattr(settings, "MSG91_AUTH_KEY", "").strip()
        self.flow_id = os.environ.get("MSG91_FLOW_ID", "").strip() or getattr(settings, "MSG91_FLOW_ID", "").strip()
        self.sender_id = os.environ.get("MSG91_SENDER_ID", "HIRNEX").strip()

    def is_configured(self) -> bool:
        return bool(self.auth_key and self.flow_id)

    def get_status(self) -> Tuple[str, str]:
        if self.is_configured():
            return "CONNECTED", "MSG91 Indian DLT Gateway"
        if getattr(settings, "DEBUG", False):
            return "CONNECTED_DEV", "MSG91 (Fallback to Console in DEBUG)"
        return "NOT_CONFIGURED", "MSG91 Indian DLT Gateway (Unconfigured)"

    def send_otp(self, to_number: str, otp_code: str, validity_minutes: int = 5) -> Dict[str, Any]:
        if not self.is_configured():
            if getattr(settings, "DEBUG", False):
                logger.warning("MSG91 credentials not found; DEBUG=True falling back to ConsoleSMSBackend.")
                return ConsoleSMSBackend().send_otp(to_number, otp_code, validity_minutes)
            return {
                "success": False,
                "status": "NOT_CONFIGURED",
                "provider": "MSG91 Indian DLT Gateway",
                "reference_id": "",
                "error": "MSG91 configuration incomplete in environment variables",
                "error_code": "CONFIG_INCOMPLETE",
            }

        cleaned_phone = normalize_to_e164(to_number).replace("+", "").replace(" ", "").replace("-", "")
        url = (
            f"https://control.msg91.com/api/v5/otp"
            f"?template_id={self.flow_id}&mobile={cleaned_phone}&authkey={self.auth_key}&otp={otp_code}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "HireNexa-MSG91/2.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                msg_type = resp_data.get("type", "")
                if msg_type == "success":
                    msg_id = resp_data.get("message", "msg91_ok")
                    logger.info("MSG91 OTP dispatched successfully to %s. ID: %s", mask_phone(to_number), msg_id)
                    return {
                        "success": True,
                        "status": "SENT",
                        "provider": "MSG91",
                        "reference_id": str(msg_id),
                        "error": None,
                        "error_code": None,
                    }
                else:
                    err_msg = resp_data.get("message", "MSG91 API error")
                    logger.error("MSG91 returned error for %s: %s", mask_phone(to_number), err_msg)
                    return {
                        "success": False,
                        "status": "FAILED",
                        "provider": "MSG91",
                        "reference_id": "",
                        "error": "Failed to deliver SMS. Please try again.",
                        "error_code": "PROVIDER_ERROR",
                    }
        except Exception as exc:
            logger.exception("MSG91 delivery failure for %s: %s", mask_phone(to_number), str(exc))
            if getattr(settings, "DEBUG", False):
                logger.info("Falling back to ConsoleSMSBackend due to exception in DEBUG.")
                return ConsoleSMSBackend().send_otp(to_number, otp_code, validity_minutes)
            return {
                "success": False,
                "status": "FAILED",
                "provider": "MSG91",
                "reference_id": "",
                "error": "SMS delivery service temporarily unavailable.",
                "error_code": "DISPATCH_FAILED",
            }


MSG91SMSProvider = MSG91SMSBackend  # Backward compatibility alias


class Fast2SMSBackend(BaseSMSBackend):
    """Production Fast2SMS Indian Quick SMS Gateway Backend."""

    def __init__(self):
        self.api_key = os.environ.get("FAST2SMS_API_KEY", "").strip() or getattr(settings, "FAST2SMS_API_KEY", "").strip()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def get_status(self) -> Tuple[str, str]:
        if self.is_configured():
            return "CONNECTED", "Fast2SMS Quick SMS Gateway"
        if getattr(settings, "DEBUG", False):
            return "CONNECTED_DEV", "Fast2SMS (Fallback to Console in DEBUG)"
        return "NOT_CONFIGURED", "Fast2SMS (Unconfigured)"

    def send_otp(self, to_number: str, otp_code: str, validity_minutes: int = 5) -> Dict[str, Any]:
        if not self.is_configured():
            if getattr(settings, "DEBUG", False):
                logger.warning("FAST2SMS_API_KEY not found; DEBUG=True falling back to ConsoleSMSBackend.")
                return ConsoleSMSBackend().send_otp(to_number, otp_code, validity_minutes)
            return {
                "success": False,
                "status": "NOT_CONFIGURED",
                "provider": "Fast2SMS",
                "reference_id": "",
                "error": "Fast2SMS API key is not configured in environment",
                "error_code": "CONFIG_INCOMPLETE",
            }

        digits = re.sub(r"[^\d]", "", str(to_number))
        phone_10 = digits[-10:] if len(digits) >= 10 else digits

        payload = {
            "route": "otp",
            "variables_values": str(otp_code),
            "numbers": phone_10,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://www.fast2sms.com/dev/bulkV2",
            data=data,
            headers={
                "authorization": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "HireNexa-Fast2SMS/2.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                if resp_data.get("return") is True:
                    req_id = resp_data.get("request_id", "fast2sms_ok")
                    logger.info("Fast2SMS OTP dispatched successfully to %s. ID: %s", mask_phone(to_number), req_id)
                    return {
                        "success": True,
                        "status": "SENT",
                        "provider": "Fast2SMS",
                        "reference_id": str(req_id),
                        "error": None,
                        "error_code": None,
                    }
                else:
                    err_msg = resp_data.get("message", "Fast2SMS returned failure")
                    logger.error("Fast2SMS error for %s: %s", mask_phone(to_number), err_msg)
                    return {
                        "success": False,
                        "status": "FAILED",
                        "provider": "Fast2SMS",
                        "reference_id": "",
                        "error": "Failed to deliver SMS. Please try again.",
                        "error_code": "PROVIDER_ERROR",
                    }
        except Exception as exc:
            logger.exception("Fast2SMS delivery exception for %s: %s", mask_phone(to_number), str(exc))
            if getattr(settings, "DEBUG", False):
                return ConsoleSMSBackend().send_otp(to_number, otp_code, validity_minutes)
            return {
                "success": False,
                "status": "FAILED",
                "provider": "Fast2SMS",
                "reference_id": "",
                "error": "SMS delivery service temporarily unavailable.",
                "error_code": "DISPATCH_FAILED",
            }


class TwilioSMSBackend(BaseSMSBackend):
    """Production Twilio SMS Gateway Backend."""

    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip() or getattr(settings, "TWILIO_ACCOUNT_SID", "").strip()
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip() or getattr(settings, "TWILIO_AUTH_TOKEN", "").strip()
        self.from_number = os.environ.get("TWILIO_FROM_NUMBER", "").strip() or getattr(settings, "TWILIO_FROM_NUMBER", "").strip()

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)

    def get_status(self) -> Tuple[str, str]:
        if self.is_configured():
            return "CONNECTED", "Twilio SMS Gateway"
        if getattr(settings, "DEBUG", False):
            return "CONNECTED_DEV", "Twilio (Fallback to Console in DEBUG)"
        return "NOT_CONFIGURED", "Twilio SMS Gateway (Unconfigured)"

    def send_otp(self, to_number: str, otp_code: str, validity_minutes: int = 5) -> Dict[str, Any]:
        if not self.is_configured():
            if getattr(settings, "DEBUG", False):
                logger.warning("Twilio credentials not found; DEBUG=True falling back to ConsoleSMSBackend.")
                return ConsoleSMSBackend().send_otp(to_number, otp_code, validity_minutes)
            return {
                "success": False,
                "status": "NOT_CONFIGURED",
                "provider": "Twilio SMS Gateway",
                "reference_id": "",
                "error": "Twilio configuration incomplete in environment variables",
                "error_code": "CONFIG_INCOMPLETE",
            }

        normalized = normalize_to_e164(to_number)
        body = (
            f"HireNexa verification code: {otp_code}\n"
            f"This code expires in {validity_minutes} minutes. Do not share it with anyone."
        )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = urllib.parse.urlencode({
            "To": normalized,
            "From": self.from_number,
            "Body": body,
        }).encode("utf-8")

        auth_header = "Basic " + base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode("utf-8")).decode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "HireNexa-SMS/2.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                sid = resp_data.get("sid", "twilio_ok")
                logger.info("Twilio SMS dispatched successfully to %s. SID: %s", mask_phone(to_number), sid)
                return {
                    "success": True,
                    "status": "SENT",
                    "provider": "Twilio",
                    "reference_id": str(sid),
                    "error": None,
                    "error_code": None,
                }
        except Exception as exc:
            logger.exception("Twilio SMS delivery failure for %s: %s", mask_phone(to_number), str(exc))
            if getattr(settings, "DEBUG", False):
                return ConsoleSMSBackend().send_otp(to_number, otp_code, validity_minutes)
            return {
                "success": False,
                "status": "FAILED",
                "provider": "Twilio",
                "reference_id": "",
                "error": "SMS delivery failed. Please try again.",
                "error_code": "DISPATCH_FAILED",
            }


TwilioSMSProvider = TwilioSMSBackend  # Backward compatibility alias


class CustomHTTPGatewaySMSProvider(BaseSMSBackend):
    """Custom HTTP SMS Gateway."""

    def __init__(self):
        self.gateway_url = os.environ.get("CUSTOM_SMS_GATEWAY_URL", "").strip() or getattr(settings, "CUSTOM_SMS_GATEWAY_URL", "").strip()

    def is_configured(self) -> bool:
        return bool(self.gateway_url)

    def get_status(self) -> Tuple[str, str]:
        if self.is_configured():
            return "CONNECTED", "Custom HTTP SMS Gateway"
        return "NOT_CONFIGURED", "Custom HTTP SMS Gateway (Unconfigured)"

    def send_otp(self, to_number: str, otp_code: str, validity_minutes: int = 5) -> Dict[str, Any]:
        if not self.is_configured():
            if getattr(settings, "DEBUG", False):
                return ConsoleSMSBackend().send_otp(to_number, otp_code, validity_minutes)
            return {
                "success": False,
                "status": "NOT_CONFIGURED",
                "provider": "Custom SMS Gateway",
                "reference_id": "",
                "error": "CUSTOM_SMS_GATEWAY_URL is not configured in .env",
                "error_code": "CONFIG_INCOMPLETE",
            }

        body = (
            f"HireNexa verification code: {otp_code}\n"
            f"This code expires in {validity_minutes} minutes. Do not share it with anyone."
        )
        payload = {"to": normalize_to_e164(to_number), "message": body, "otp": otp_code}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.gateway_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {
                    "success": True,
                    "status": "SENT",
                    "provider": "Custom SMS Gateway",
                    "reference_id": f"custom_{uuid.uuid4().hex[:8]}",
                    "error": None,
                    "error_code": None,
                }
        except Exception as exc:
            return {
                "success": False,
                "status": "FAILED",
                "provider": "Custom SMS Gateway",
                "reference_id": "",
                "error": "SMS gateway error.",
                "error_code": "DISPATCH_FAILED",
            }


def get_sms_backend(backend_name: Optional[str] = None) -> BaseSMSBackend:
    """
    Factory function returning the configured pluggable SMS Backend instance.
    Configured via SMS_BACKEND in .env (or SMS_PROVIDER).
    Options:
      - 'console' or 'mock' (default in DEBUG)
      - 'msg91'
      - 'fast2sms'
      - 'twilio'
      - 'custom'
    """
    name = (
        backend_name
        or os.environ.get("SMS_BACKEND")
        or getattr(settings, "SMS_BACKEND", "")
        or os.environ.get("SMS_PROVIDER")
        or getattr(settings, "SMS_PROVIDER", "")
    ).strip().lower()

    if not name:
        name = "console" if getattr(settings, "DEBUG", False) else "twilio"

    if name in ("console", "mock", "dev"):
        return ConsoleSMSBackend()
    if name in ("fast2sms", "fast_sms"):
        return Fast2SMSBackend()
    if name in ("msg91", "dlt"):
        return MSG91SMSBackend()
    if name in ("twilio",):
        return TwilioSMSBackend()
    if name in ("custom", "http"):
        return CustomHTTPGatewaySMSProvider()

    # Fallback
    if getattr(settings, "DEBUG", False):
        return ConsoleSMSBackend()
    return TwilioSMSBackend()


get_sms_provider = get_sms_backend  # Backward compatibility alias

