import os
import secrets
import string
from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from accounts.models import User, AuditLog


class Command(BaseCommand):
    help = "Initializes or updates the HireNexa Platform Owner / Super Admin account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=os.environ.get("OWNER_USERNAME", os.environ.get("HIRENEXA_OWNER_USERNAME", "")),
            help="Owner username (or via OWNER_USERNAME / HIRENEXA_OWNER_USERNAME env var)",
        )
        parser.add_argument(
            "--email",
            type=str,
            default=os.environ.get("OWNER_EMAIL", os.environ.get("HIRENEXA_OWNER_EMAIL", "")),
            help="Owner email (or via OWNER_EMAIL / HIRENEXA_OWNER_EMAIL env var)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=os.environ.get("OWNER_PASSWORD", os.environ.get("HIRENEXA_OWNER_PASSWORD", "")),
            help="Owner password (or via OWNER_PASSWORD / HIRENEXA_OWNER_PASSWORD env var)",
        )
        parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="Execute without interactive prompts",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        email = options["email"].strip()
        password = options["password"]
        non_interactive = options["non_interactive"]

        # Prompt for username if missing
        if not username:
            if non_interactive:
                username = "platform_owner"
            else:
                username = input("Enter Platform Owner username [default: platform_owner]: ").strip() or "platform_owner"

        # Prompt for email if missing
        if not email:
            if non_interactive:
                email = f"{username}@hirenexa.internal"
            else:
                email = input(f"Enter Platform Owner email [default: {username}@hirenexa.internal]: ").strip() or f"{username}@hirenexa.internal"

        # Prompt or generate password
        generated_password = False
        if not password:
            if non_interactive:
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
                password = "".join(secrets.choice(alphabet) for _ in range(16))
                generated_password = True
            else:
                password = getpass("Enter Platform Owner password (leave blank to auto-generate): ")
                if not password:
                    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
                    password = "".join(secrets.choice(alphabet) for _ in range(16))
                    generated_password = True

        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters long for security.")

        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.role = User.Role.OWNER
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.is_email_verified = True
        user.email_verified_at = timezone.now()
        user.set_password(password)
        user.save()

        # Audit log creation
        AuditLog.objects.create(
            user=user,
            action="OWNER_ACCOUNT_SETUP",
            ip_address="127.0.0.1",
            details={
                "created": created,
                "username": username,
                "email": email,
                "role": user.role,
                "is_superuser": True,
            },
        )

        status_msg = "Created new" if created else "Updated existing"
        self.stdout.write(self.style.SUCCESS(f"✓ {status_msg} Platform Owner account: '{username}' ({email})"))
        self.stdout.write(self.style.SUCCESS("✓ Role assigned: OWNER / SUPER ADMIN"))
        self.stdout.write(self.style.SUCCESS("✓ Privileges granted: Full Platform Administration"))

        if generated_password:
            self.stdout.write(self.style.WARNING("=" * 60))
            self.stdout.write(self.style.WARNING(f"Generated One-Time Owner Password: {password}"))
            self.stdout.write(self.style.WARNING("Save this password securely. It will NOT be shown again."))
            self.stdout.write(self.style.WARNING("=" * 60))
