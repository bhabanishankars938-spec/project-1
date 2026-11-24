import os
import re
from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from accounts.models import User, AuditLog, EmailOTP
from accounts.services.delivery import EmailDeliveryService
from recruitment.models import NewsAnnouncement


class Command(BaseCommand):
    help = "Secure First-Time Platform Owner & Super Admin Account Initialization"

    def add_arguments(self, parser):
        parser.add_argument("--full-name", type=str, default="", help="Owner Full Name")
        parser.add_argument("--username", type=str, default="", help="Owner Username")
        parser.add_argument("--email", type=str, default="", help="Owner Email Address")
        parser.add_argument("--phone", type=str, default="", help="Owner Mobile Phone")
        parser.add_argument("--password", type=str, default="", help="Master Password")
        parser.add_argument("--skip-otp", action="store_true", help="Skip interactive OTP confirmation (automated/CI only)")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== HIRENEXA PLATFORM OWNER INITIALIZATION ==="))

        # Strict single-owner enforcement: prevent duplicate owner creation
        existing_owner = User.objects.filter(role=User.Role.OWNER).first()
        if existing_owner:
            self.stdout.write(self.style.ERROR(
                f"\n[SECURITY LOCKOUT] A Platform Owner account already exists in this database: "
                f"'{existing_owner.username}' ({existing_owner.email}).\n"
                "Public or multiple Owner creation is strictly disabled.\n"
                "To reset the master password, use: python manage.py changepassword " + existing_owner.username
            ))
            return

        full_name = options["full_name"].strip()
        username = options["username"].strip()
        email = options["email"].strip()
        phone = options["phone"].strip()
        password = options["password"]
        skip_otp = options["skip_otp"]

        # Interactive prompts if not supplied via CLI flags
        if not full_name:
            full_name = input("Enter Owner Full Name: ").strip()
            while not full_name:
                self.stdout.write(self.style.WARNING("Full Name cannot be blank."))
                full_name = input("Enter Owner Full Name: ").strip()

        if not username:
            username = input("Enter Platform Owner Username: ").strip()
            while not username or User.objects.filter(username__iexact=username).exists():
                if not username:
                    self.stdout.write(self.style.WARNING("Username cannot be blank."))
                else:
                    self.stdout.write(self.style.WARNING(f"Username '{username}' already exists. Choose a different one."))
                username = input("Enter Platform Owner Username: ").strip()

        if not email:
            email = input("Enter Platform Owner Official Email: ").strip()
            while not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email) or User.objects.filter(email__iexact=email).exists():
                if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    self.stdout.write(self.style.WARNING("Please enter a valid email address."))
                else:
                    self.stdout.write(self.style.WARNING(f"Email '{email}' is already in use by another user."))
                email = input("Enter Platform Owner Official Email: ").strip()

        if not phone:
            phone = input("Enter Platform Owner Mobile Phone: ").strip()

        if not password:
            while True:
                p1 = getpass("Enter Master Security Password (min 8 chars): ")
                if len(p1) < 8:
                    self.stdout.write(self.style.WARNING("Password must be at least 8 characters long."))
                    continue
                p2 = getpass("Confirm Master Security Password: ")
                if p1 != p2:
                    self.stdout.write(self.style.WARNING("Passwords do not match. Please re-enter."))
                    continue
                password = p1
                break

        # Split full name into first and last
        name_parts = full_name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        # Step 2: Email Verification OTP Dispatch (Cryptographically Hashed)
        otp_record, raw_code = EmailOTP.generate(
            email=email,
            purpose=EmailOTP.Purpose.OWNER_SETUP,
            validity_minutes=15,
        )
        dispatch_result = EmailDeliveryService.send_otp_email(
            recipient_email=email,
            user_name=full_name,
            raw_otp=raw_code,
            validity_minutes=15,
        )

        self.stdout.write(self.style.SUCCESS(f"\n✓ 6-Digit Email Verification Code dispatched to: {email}"))
        if not dispatch_result["success"]:
            self.stdout.write(self.style.WARNING(f"[WARNING] Email delivery issue: {dispatch_result.get('error')}. Please verify SMTP settings."))

        if not skip_otp:
            entered_otp = input("\nEnter the 6-digit OTP code sent to your email: ").strip()
            is_valid, reason = otp_record.check_code(entered_otp)
            while not is_valid:
                if reason == "LOCKED":
                    raise CommandError("Maximum OTP verification attempts exceeded (5/5). Owner initialization aborted.")
                self.stdout.write(self.style.ERROR(f"Invalid OTP code ({5 - otp_record.attempts} attempts remaining). Please try again."))
                entered_otp = input("Enter the 6-digit OTP code: ").strip()
                is_valid, reason = otp_record.check_code(entered_otp)

        # Create Dedicated Platform Owner Account
        owner = User(
            username=username,
            email=email.lower().strip(),
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
            is_active=True,
            is_email_verified=True,
            email_verified_at=timezone.now(),
        )
        owner.set_password(password)
        owner.save()

        # Reassign existing news announcements to the new owner
        reassigned_news = NewsAnnouncement.objects.filter(author__isnull=False).update(author=owner)

        # Audit Log
        AuditLog.objects.create(
            user=owner,
            action="PLATFORM_OWNER_INITIALIZED",
            ip_address="127.0.0.1",
            details={
                "username": owner.username,
                "email": owner.email,
                "phone": owner.phone_number,
                "role": owner.role,
                "reassigned_announcements": reassigned_news,
                "security_hasher": "Argon2id",
            },
        )

        self.stdout.write(self.style.SUCCESS("\n======================================================="))
        self.stdout.write(self.style.SUCCESS("✓ PLATFORM OWNER SUCCESSFULLY INITIALIZED AND ACTIVATED!"))
        self.stdout.write(self.style.SUCCESS(f"  Owner Username : {owner.username}"))
        self.stdout.write(self.style.SUCCESS(f"  Email Address  : {owner.email}"))
        self.stdout.write(self.style.SUCCESS(f"  Role           : {owner.get_role_display()} (Tier-0)"))
        self.stdout.write(self.style.SUCCESS(f"  Login Portal   : http://127.0.0.1:8000/accounts/owner/login/"))
        self.stdout.write(self.style.SUCCESS("=======================================================\n"))
