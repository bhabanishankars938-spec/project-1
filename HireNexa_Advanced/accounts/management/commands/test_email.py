import os
import smtplib
import socket
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from accounts.utils import mask_email


class Command(BaseCommand):
    help = "Diagnose and verify Gmail SMTP email deliverability step-by-step."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            type=str,
            default=getattr(settings, "EMAIL_HOST_USER", "") or "test@example.com",
            help="Recipient email address to test delivery.",
        )
        parser.add_argument(
            "--resend",
            action="store_true",
            help="Test email delivery via Resend API directly.",
        )

    def handle(self, *args, **options):
        recipient = options["to"].strip()
        use_resend = options.get("resend")

        if use_resend:
            self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 65))
            self.stdout.write(self.style.MIGRATE_HEADING("  HIRENEXA RESEND EMAIL SERVICE TEST"))
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 65 + "\n"))
            from accounts.services.delivery import EmailDeliveryService
            resend_key = getattr(settings, "RESEND_API_KEY", "") or os.environ.get("RESEND_API_KEY", "")
            if not resend_key:
                self.stdout.write(self.style.ERROR("  [FAIL] RESEND_API_KEY is not configured in .env or settings."))
                return
            self.stdout.write(f"  • Provider: Resend API")
            self.stdout.write(f"  • API Key : {resend_key[:8]}...{resend_key[-4:]}")
            self.stdout.write(f"  • To      : {recipient}\n")
            res = EmailDeliveryService.send_otp_email(
                recipient_email=recipient,
                user_name="Candidate",
                raw_otp="123456",
                validity_minutes=15,
            )
            if res.get("success"):
                self.stdout.write(self.style.SUCCESS(f"  [PASS] Email sent successfully via Resend! ID: {res.get('reference_id')}"))
            else:
                self.stdout.write(self.style.ERROR(f"  [FAIL] Resend dispatch failed: {res.get('error')}"))
            return
        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 65))
        self.stdout.write(self.style.MIGRATE_HEADING("  HIRENEXA EMAIL DELIVERABILITY & SMTP DIAGNOSTIC TOOL"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 65 + "\n"))

        # ----------------------------------------------------------------------
        # 1. CONFIGURATION SUMMARY
        # ----------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_LABEL("[1] CONFIGURATION SUMMARY:"))
        backend_mode = getattr(settings, "EMAIL_BACKEND_MODE", "smtp")
        backend_class = getattr(settings, "EMAIL_BACKEND", "")
        host = getattr(settings, "EMAIL_HOST", "smtp.gmail.com")
        port = getattr(settings, "EMAIL_PORT", 587)
        use_tls = getattr(settings, "EMAIL_USE_TLS", True)
        use_ssl = getattr(settings, "EMAIL_USE_SSL", False)
        user = getattr(settings, "EMAIL_HOST_USER", "")
        pwd = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        timeout = getattr(settings, "EMAIL_TIMEOUT", 20)

        pwd_display = f"Set (length: {len(pwd)} chars, spaces stripped: {' ' not in pwd})" if pwd else "EMPTY / NOT SET"

        self.stdout.write(f"  • EMAIL_BACKEND_MODE : {backend_mode}")
        self.stdout.write(f"  • EMAIL_BACKEND      : {backend_class}")
        self.stdout.write(f"  • EMAIL_HOST         : {host}")
        self.stdout.write(f"  • EMAIL_PORT         : {port}")
        self.stdout.write(f"  • EMAIL_USE_TLS      : {use_tls}")
        self.stdout.write(f"  • EMAIL_USE_SSL      : {use_ssl}")
        self.stdout.write(f"  • EMAIL_HOST_USER    : {mask_email(user) if user else 'EMPTY / NOT SET'}")
        self.stdout.write(f"  • EMAIL_HOST_PASSWORD: {pwd_display}")
        self.stdout.write(f"  • DEFAULT_FROM_EMAIL : {from_email}")
        self.stdout.write(f"  • EMAIL_TIMEOUT      : {timeout}s")
        self.stdout.write(f"  • Target Recipient   : {recipient}\n")

        # ----------------------------------------------------------------------
        # 2. BACKEND & CREDENTIALS CHECK
        # ----------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_LABEL("[2] PRE-FLIGHT VALIDATION:"))
        if "console" in backend_class.lower() or backend_mode == "console":
            self.stdout.write(
                self.style.WARNING(
                    "  [WARN] Console backend is active! Emails are dumped to the terminal and NOT sent over the internet.\n"
                    "  --> FIX: Set EMAIL_BACKEND_MODE=smtp in .env and restart server."
                )
            )

        if not user or not pwd:
            self.stdout.write(
                self.style.ERROR(
                    "  [FAIL] Empty EMAIL_HOST_USER or EMAIL_HOST_PASSWORD detected!\n"
                    "  --> FIX: .env load nahi ho rahi, path aur variable name check karo.\n"
                    "           .env me dalein:\n"
                    "           EMAIL_HOST_USER=aapka-gmail@gmail.com\n"
                    "           EMAIL_HOST_PASSWORD=abcdefghijklmnop\n"
                    "           EMAIL_BACKEND_MODE=smtp"
                )
            )
            return

        self.stdout.write(self.style.SUCCESS("  [PASS] Pre-flight credentials check passed.\n"))

        # ----------------------------------------------------------------------
        # 3. NETWORK SOCKET CONNECTION
        # ----------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_LABEL(f"[3] TCP SOCKET CONNECTION ({host}:{port}):"))
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            self.stdout.write(self.style.SUCCESS(f"  [PASS] Successfully connected to {host}:{port} via TCP socket.\n"))
        except (socket.timeout, TimeoutError):
            self.stdout.write(
                self.style.ERROR(
                    f"  [FAIL] Connection timed out after {timeout}s connecting to {host}:{port}.\n"
                    "  --> FIX: Port 587/465 network me block hai, dusra network ya hotspot try karo."
                )
            )
            return
        except OSError as e:
            self.stdout.write(
                self.style.ERROR(
                    f"  [FAIL] TCP Socket connection refused or blocked: {e}\n"
                    "  --> FIX: Port 587/465 network me block hai, firewall check karo ya dusra network/hotspot try karo."
                )
            )
            return

        # ----------------------------------------------------------------------
        # 4. SMTP HANDSHAKE & TLS ENCRYPTION
        # ----------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_LABEL("[4] SMTP PROTOCOL & ENCRYPTION HANDSHAKE:"))
        smtp_client = None
        try:
            if use_ssl:
                smtp_client = smtplib.SMTP_SSL(host, port, timeout=timeout)
                smtp_client.ehlo()
                self.stdout.write(self.style.SUCCESS("  [PASS] Connected with direct SSL/TLS."))
            else:
                smtp_client = smtplib.SMTP(host, port, timeout=timeout)
                smtp_client.ehlo()
                if use_tls:
                    smtp_client.starttls()
                    smtp_client.ehlo()
                    self.stdout.write(self.style.SUCCESS("  [PASS] Connected and upgraded session via STARTTLS."))
                else:
                    self.stdout.write(self.style.WARNING("  [WARN] Connected without encryption."))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"  [FAIL] SMTP handshake failed: {e}\n"
                    "  --> FIX: Check firewall / proxy or switch port to 465 (SSL) in .env."
                )
            )
            return

        # ----------------------------------------------------------------------
        # 5. SMTP AUTHENTICATION (App Password)
        # ----------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_LABEL("\n[5] SMTP AUTHENTICATION:"))
        try:
            smtp_client.login(user, pwd)
            self.stdout.write(self.style.SUCCESS("  [PASS] SMTP Authentication succeeded with Google servers."))
        except smtplib.SMTPAuthenticationError as exc:
            self.stdout.write(
                self.style.ERROR(
                    f"  [FAIL] Authentication failed (Code {exc.smtp_code}: {exc.smtp_error})\n"
                    "  --> FIX: 535 Error: App Password galat hai ya regular account password dala hai.\n"
                    "           16-letter App Password banao:\n"
                    "           Google Account > Security > 2-Step Verification ON > App passwords\n"
                    "           Naya 'HireNexa' app password generate karke .env me update karo."
                )
            )
            smtp_client.quit()
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  [FAIL] Authentication failed with unexpected error: {e}"))
            smtp_client.quit()
            return

        # Close direct client before Django mailer test
        try:
            smtp_client.quit()
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # 6. DISPATCH REAL TEST EMAIL VIA DJANGO EMAIL SERVICE
        # ----------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_LABEL("\n[6] DISPATCHING TEST EMAIL VIA DJANGO:"))
        try:
            subject = "Your HireNexa verification code"
            text_body = (
                "Hello,\n\n"
                "Your HireNexa verification code is: 849201\n\n"
                "Purpose: Deliverability Diagnostic Test\n"
                "This code will expire in 15 minutes.\n\n"
                "If you did not request this, ignore this email. Never share this code.\n\n"
                "Regards,\n"
                "HireNexa Security Team"
            )
            html_body = """
            <!DOCTYPE html>
            <html>
            <body style="font-family:sans-serif; background:#0f172a; color:#f8fafc; padding:24px;">
              <div style="background:#1e293b; border-radius:12px; padding:28px; max-width:480px; margin:0 auto; border:1px solid #334155;">
                <h2 style="color:#f59e0b; margin:0 0 16px 0;">🛡️ HIRENEXA CORE</h2>
                <p>Hello,</p>
                <p style="color:#cbd5e1;">Your HireNexa test verification code is:</p>
                <div style="background:#0f172a; border:2px solid #d97706; border-radius:8px; padding:16px; text-align:center; font-size:32px; font-weight:800; letter-spacing:8px; color:#fbbf24; margin:20px 0;">
                  849201
                </div>
                <p style="color:#94a3b8; font-size:12px;">This email confirms that your HireNexa Gmail SMTP integration is <strong>100% WORKING</strong>.</p>
              </div>
            </body>
            </html>
            """
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=from_email,
                to=[recipient],
            )
            msg.attach_alternative(html_body, "text/html")
            sent_count = msg.send(fail_silently=False)

            if sent_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [PASS] Test email successfully dispatched to: {recipient}!\n"
                        "  --> Status: Check your Gmail Inbox (and Spam/Junk folder if not in Inbox)."
                    )
                )
            else:
                self.stdout.write(self.style.ERROR("  [FAIL] Mail dispatch call returned 0 messages sent."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  [FAIL] Failed to dispatch test email: {exc}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 65 + "\n"))
