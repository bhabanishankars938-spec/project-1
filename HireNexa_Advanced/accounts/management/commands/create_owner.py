import os
import secrets
import string
from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from accounts.models import User, AuditLog
from accounts.utils import mask_email
from accounts.services.rate_limiter import RateLimiter
from recruitment.models import NewsAnnouncement


class Command(BaseCommand):
    help = "Idempotently create or update the HireNexa Platform Owner / Super Admin account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="",
            help="Owner username (or via OWNER_USERNAME / HIRENEXA_OWNER_USERNAME env var)",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="Owner email (or via OWNER_EMAIL / HIRENEXA_OWNER_EMAIL env var)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="",
            help="Owner password (or via OWNER_PASSWORD / HIRENEXA_OWNER_PASSWORD env var)",
        )
        parser.add_argument(
            "--phone",
            type=str,
            default="",
            help="Owner mobile phone (or via OWNER_PHONE / HIRENEXA_OWNER_PHONE env var)",
        )
        parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="Execute without interactive prompts (reads CLI args, env vars, or auto-generates securely)",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== HIRENEXA PLATFORM OWNER PROVISIONING ==="))

        # 1. Resolve values from CLI options, then environment variables
        username = (
            options.get("username", "").strip()
            or os.environ.get("OWNER_USERNAME", "").strip()
            or os.environ.get("HIRENEXA_OWNER_USERNAME", "").strip()
        )
        email = (
            options.get("email", "").strip()
            or os.environ.get("OWNER_EMAIL", "").strip()
            or os.environ.get("HIRENEXA_OWNER_EMAIL", "").strip()
        )
        password = (
            options.get("password", "")
            or os.environ.get("OWNER_PASSWORD", "")
            or os.environ.get("HIRENEXA_OWNER_PASSWORD", "")
        )
        phone = (
            options.get("phone", "").strip()
            or os.environ.get("OWNER_PHONE", "").strip()
            or os.environ.get("HIRENEXA_OWNER_PHONE", "").strip()
        )
        non_interactive = options.get("non_interactive", False)

        # 2. Interactive prompts if missing and not non-interactive
        if not username:
            if non_interactive:
                username = "owner"
            else:
                entered = input("Enter Platform Owner username [default: owner]: ").strip()
                username = entered or "owner"

        if not email:
            if non_interactive:
                email = f"{username}@hirenexa.internal"
            else:
                default_email = f"{username}@hirenexa.internal"
                entered = input(f"Enter Platform Owner email [default: {default_email}]: ").strip()
                email = entered or default_email

        if not password:
            if non_interactive:
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                password = "".join(secrets.choice(alphabet) for _ in range(18)) + "1aA!"
            else:
                while True:
                    p1 = getpass("Enter Master Security Password (min 8 chars, blank to auto-generate): ")
                    if not p1:
                        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                        password = "".join(secrets.choice(alphabet) for _ in range(18)) + "1aA!"
                        break
                    p2 = getpass("Confirm Master Security Password: ")
                    if p1 != p2:
                        self.stdout.write(self.style.WARNING("Passwords do not match. Please re-enter."))
                        continue
                    password = p1
                    break

        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters long for security.")

        # Validate password strength with Django validators
        temp_user = User(username=username, email=email)
        try:
            validate_password(password, user=temp_user)
        except ValidationError as e:
            raise CommandError(f"Password validation failed: {'; '.join(e.messages)}")

        # 3. Idempotent User Lookup:
        # Match by username, or by email, or existing owner
        user = User.objects.filter(username__iexact=username).first()
        if not user and email:
            user = User.objects.filter(email__iexact=email).first()
        if not user:
            user = User.objects.filter(Q(role=User.Role.OWNER) | Q(is_superuser=True)).first()

        created = False
        email_clean = email.lower().strip()
        now = timezone.now()

        if user:
            user.username = username
            user.email = email_clean
            if phone:
                user.phone_number = phone
            user.role = User.Role.OWNER
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.is_email_verified = True
            user.email_verified_at = now
            user.set_password(password)
            user.save()
        else:
            created = True
            user = User(
                username=username,
                email=email_clean,
                phone_number=phone or None,
                role=User.Role.OWNER,
                is_staff=True,
                is_superuser=True,
                is_active=True,
                is_email_verified=True,
                email_verified_at=now,
            )
            user.set_password(password)
            user.save()

        # Reassign existing news announcements to the owner
        NewsAnnouncement.objects.all().update(author=user)

        # Clear login lockouts for owner
        RateLimiter.reset_attempts(ip="127.0.0.1", identifier=username, portal="owner")
        RateLimiter.reset_attempts(ip="127.0.0.1", identifier=email_clean, portal="owner")
        if phone:
            RateLimiter.reset_attempts(ip="127.0.0.1", identifier=phone, portal="owner")

        # Audit log creation (NEVER log real passwords)
        AuditLog.objects.create(
            user=user,
            action="PLATFORM_OWNER_PROVISIONED_CLI",
            ip_address="127.0.0.1",
            details={
                "created": created,
                "username": user.username,
                "email": mask_email(user.email),
                "role": user.role,
                "is_superuser": True,
                "is_staff": True,
                "is_active": True,
            },
        )

        status_msg = "Created new" if created else "Updated existing"
        self.stdout.write(self.style.SUCCESS(f"✓ {status_msg} Platform Owner account: '{user.username}' ({user.email})"))
        self.stdout.write(self.style.SUCCESS("✓ Role assigned: OWNER / SUPER ADMIN (Tier-0 Privileges)"))
        self.stdout.write(self.style.SUCCESS("✓ Status: is_active=True, is_staff=True, is_superuser=True, is_email_verified=True"))
        self.stdout.write(self.style.SUCCESS("✓ Master password securely hashed via set_password()."))
        self.stdout.write(self.style.SUCCESS("✓ Login Portal: http://127.0.0.1:8000/accounts/owner/login/"))
