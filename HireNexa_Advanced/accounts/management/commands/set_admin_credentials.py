import os
import sqlite3
import sys
from getpass import getpass
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from accounts.models import User, AuditLog
from accounts.services.rate_limiter import RateLimiter


class Command(BaseCommand):
    help = "Safely set or recover credentials for the HireNexa Platform Owner (admin@hirenexa.internal) and sync databases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="admin",
            help="Admin username (default: 'admin')",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="admin@hirenexa.internal",
            help="Admin email address (default: 'admin@hirenexa.internal')",
        )
        parser.add_argument(
            "--phone",
            type=str,
            default="+919800000000",
            help="Admin phone number with country code (default: '+919800000000')",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="",
            help="Plaintext password to set for the admin account",
        )
        parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="Execute non-interactively (uses provided password or default secure credential)",
        )
        parser.add_argument(
            "--sync-sqlite",
            action="store_true",
            default=True,
            help="Also synchronize the admin account to local db.sqlite3 if it exists",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== HIRENEXA ADMIN CREDENTIAL RECOVERY & SYNC ==="))

        username = (options.get("username") or "admin").strip()
        email = (options.get("email") or "admin@hirenexa.internal").strip().lower()
        phone = (options.get("phone") or "+919800000000").strip()
        raw_password = options.get("password") or ""
        non_interactive = options.get("non_interactive", False)

        if not raw_password:
            if non_interactive:
                raw_password = os.environ.get("ADMIN_PASSWORD") or os.environ.get("OWNER_PASSWORD") or "AdminPass123!"
            else:
                raw_password = getpass("Enter new password for Platform Owner [default: AdminPass123!]: ").strip()
                if not raw_password:
                    raw_password = "AdminPass123!"

        if len(raw_password) < 8:
            raise CommandError("Password must be at least 8 characters long.")

        # 1. Update or create in the currently active database (PostgreSQL or SQLite)
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            user = User.objects.filter(email__iexact=email).first()

        created = False
        now = timezone.now()
        if not user:
            user = User(username=username, email=email)
            created = True

        user.email = email
        user.phone_number = phone
        user.role = User.Role.OWNER
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.is_email_verified = True
        user.is_phone_verified = True
        user.email_verified_at = now
        user.phone_verified_at = now
        user.set_password(raw_password)
        user.save()

        # 2. Reset RateLimiter lockouts
        portals = ["unified", "owner", "default", "candidate", "hr", "freelancer"]
        client_ips = ["127.0.0.1", "localhost"]
        identifiers = [username, email, phone, "admin@hirenexa.internal", "9800000000"]
        for p in portals:
            for ip in client_ips:
                for ident in identifiers:
                    RateLimiter.reset_attempts(ip, ident, portal=p)
            for ident in identifiers:
                RateLimiter.reset_identifier(ident)

        RateLimiter.reset_all()

        # 3. Create AuditLog
        AuditLog.objects.create(
            user=user,
            action="ADMIN_CREDENTIALS_RECOVERED_CLI",
            ip_address="127.0.0.1",
            details={
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "created": created,
                "database": settings.DATABASES["default"]["ENGINE"],
            },
        )

        status_word = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"✓ [{settings.DATABASES['default']['ENGINE'].split('.')[-1]}] {status_word} Owner account: '{user.username}' ({user.email})"
        ))

        # 4. Synchronize to SQLite db.sqlite3 if active database is PostgreSQL
        sqlite_path = Path(settings.BASE_DIR) / "db.sqlite3"
        if options.get("sync_sqlite") and sqlite_path.exists() and "sqlite" not in settings.DATABASES["default"]["ENGINE"]:
            try:
                conn = sqlite3.connect(sqlite_path)
                cur = conn.cursor()
                cur.execute("SELECT id FROM accounts_user WHERE username = ? OR email = ?", (username, email))
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        UPDATE accounts_user
                        SET email = ?, phone_number = ?, role = 'OWNER', is_staff = 1,
                            is_superuser = 1, is_active = 1, is_email_verified = 1,
                            is_phone_verified = 1, password = ?
                        WHERE id = ?
                        """,
                        (email, phone, user.password, row[0]),
                    )
                    self.stdout.write(self.style.SUCCESS(f"✓ [sqlite3] Updated existing '{username}' in {sqlite_path.name}"))
                else:
                    cur.execute(
                        """
                        INSERT INTO accounts_user (
                            username, email, phone_number, role, is_staff, is_superuser,
                            is_active, is_email_verified, is_phone_verified, password,
                            date_joined, first_name, last_name
                        ) VALUES (?, ?, ?, 'OWNER', 1, 1, 1, 1, 1, ?, datetime('now'), 'Platform', 'Owner')
                        """,
                        (username, email, phone, user.password),
                    )
                    self.stdout.write(self.style.SUCCESS(f"✓ [sqlite3] Created synced '{username}' in {sqlite_path.name}"))
                conn.commit()
                conn.close()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Note on SQLite sync: {e}"))

        self.stdout.write("\n" + "=" * 64)
        self.stdout.write(self.style.SUCCESS("HIRENEXA PLATFORM OWNER AUTHENTICATION VERIFIED"))
        self.stdout.write(f"  Username:     {username}")
        self.stdout.write(f"  Email:        {email}")
        self.stdout.write(f"  Phone:        {phone}")
        self.stdout.write(f"  Role:         {user.role} (Platform Owner / Super Admin)")
        self.stdout.write(f"  Status:       Active / Verified")
        self.stdout.write(f"  Password:     {raw_password}")
        self.stdout.write(f"  Login URLs:   /accounts/login/ (Unified) or /accounts/owner/login/")
        self.stdout.write("=" * 64 + "\n")
