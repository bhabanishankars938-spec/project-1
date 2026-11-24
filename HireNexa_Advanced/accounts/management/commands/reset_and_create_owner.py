import os
import secrets
import string
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from accounts.models import User


class Command(BaseCommand):
    help = (
        "Safely reset the DEV database, run migrations, and provision a Platform Owner account. "
        "Strictly prohibited in production environments or when DEBUG is False."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--i-understand",
            action="store_true",
            help="Mandatory confirmation flag required to acknowledge that all data will be flushed.",
        )
        parser.add_argument(
            "--username",
            type=str,
            default="",
            help="Optional CLI override for owner username (default: OWNER_USERNAME env var or 'owner').",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="Optional CLI override for owner email (default: OWNER_EMAIL env var).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="",
            help="Optional CLI override for owner password (default: OWNER_PASSWORD env var or random secrets).",
        )

    def handle(self, *args, **options):
        # 1. First Safety Guard: Refuse to run if DEBUG is False or ENVIRONMENT is production
        env_name = str(os.environ.get("ENVIRONMENT", getattr(settings, "ENVIRONMENT", "development"))).strip().lower()
        if not getattr(settings, "DEBUG", False) or env_name in ("production", "prod"):
            raise CommandError(
                "SECURITY VIOLATION: 'reset_and_create_owner' is strictly blocked when DEBUG is False "
                "or ENVIRONMENT is production. Operation permanently aborted."
            )

        # 2. Second Safety Guard: Explicit --i-understand confirmation flag
        if not options.get("i_understand"):
            raise CommandError(
                "SAFETY GUARD: This command flushes ALL data from the development database and re-applies migrations.\n"
                "To proceed, re-run with the mandatory confirmation flag:\n"
                "    python manage.py reset_and_create_owner --i-understand"
            )

        self.stdout.write(self.style.WARNING("\n[HIRENEXA DEV] Commencing safe DEV database reset and owner provisioning..."))

        # 3. Flush all database tables (non-interactive)
        self.stdout.write(self.style.MIGRATE_HEADING("1. Flushing development database tables..."))
        call_command("flush", interactive=False)
        self.stdout.write(self.style.SUCCESS("✓ Database flushed."))

        # 4. Run migrations
        self.stdout.write(self.style.MIGRATE_HEADING("2. Applying database migrations..."))
        call_command("migrate", interactive=False)
        self.stdout.write(self.style.SUCCESS("✓ Migrations applied."))

        # 5. Resolve Owner credentials
        owner_username = (
            os.environ.get("OWNER_USERNAME", "").strip()
            or options.get("username", "").strip()
            or "owner"
        )
        owner_email = (
            os.environ.get("OWNER_EMAIL", "").strip()
            or options.get("email", "").strip()
            or f"{owner_username}@hirenexa.internal"
        )
        raw_password = (
            os.environ.get("OWNER_PASSWORD", "")
            or options.get("password", "")
        )

        password_generated = False
        if not raw_password:
            # Generate cryptographically strong random password using `secrets`
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
            rand_chars = "".join(secrets.choice(alphabet) for _ in range(18))
            # Ensure complex mixture of character sets
            raw_password = f"{rand_chars}Aa1!"
            password_generated = True

        # 6. Create Platform Owner with explicit attributes and set_password()
        self.stdout.write(self.style.MIGRATE_HEADING("3. Creating fresh Platform Owner account..."))
        owner = User(
            username=owner_username,
            email=owner_email,
            is_active=True,
            is_staff=True,
            is_superuser=True,
            role="owner",
        )
        owner.set_password(raw_password)
        owner.save()

        self.stdout.write(self.style.SUCCESS(f"✓ Platform Owner '{owner_username}' provisioned successfully."))

        # 7. Print credentials ONCE to terminal (never logged or saved to disk)
        self.stdout.write("\n" + "=" * 64)
        self.stdout.write(self.style.SUCCESS("HIRENEXA PLATFORM OWNER INITIALIZED"))
        self.stdout.write(f"  Username: {owner_username}")
        self.stdout.write(f"  Email:    {owner_email}")
        self.stdout.write(f"  Role:     owner")
        self.stdout.write(f"  Status:   Active / Staff / Superuser")
        if password_generated:
            self.stdout.write(self.style.WARNING(f"  Password: {raw_password}"))
            self.stdout.write(self.style.NOTICE("  [SECURITY NOTICE: Random password printed ONCE. Never logged or saved in repo.]"))
        else:
            self.stdout.write("  Password: (configured via OWNER_PASSWORD environment variable)")
        self.stdout.write("=" * 64 + "\n")
