from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Convenience automation to reset database, migrate, provision owner, and seed demo data (DEBUG only)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Explicit confirmation flag required to execute database reset",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "DEBUG", False):
            raise CommandError("Security Violation: reset_hirenexa can only be executed in development mode (DEBUG=True).")

        if not options.get("yes"):
            raise CommandError(
                "Refusing to reset database without explicit confirmation. "
                "Pass the '--yes' flag: python manage.py reset_hirenexa --yes"
            )

        self.stdout.write(self.style.WARNING("\n[WARNING] Commencing HireNexa database reset, migration, owner setup, and demo seeding..."))

        # 1. Flush database with zero interactive prompts
        self.stdout.write(self.style.MIGRATE_HEADING("1. Flushing database tables..."))
        call_command("flush", interactive=False)

        # 2. Run migrations
        self.stdout.write(self.style.MIGRATE_HEADING("2. Applying migrations..."))
        call_command("migrate", interactive=False)

        # 3. Create platform owner
        self.stdout.write(self.style.MIGRATE_HEADING("3. Provisioning Platform Owner..."))
        call_command("create_platform_owner", non_interactive=True)

        # 4. Seed demo data
        self.stdout.write(self.style.MIGRATE_HEADING("4. Seeding multi-role demo data..."))
        call_command("seed_demo_data")

        # 5. Clear login lockouts
        self.stdout.write(self.style.MIGRATE_HEADING("5. Clearing login lockouts..."))
        call_command("reset_login_lockout", all=True)

        self.stdout.write(self.style.SUCCESS("\n✓ HireNexa platform reset and bootstrapping completed successfully!\n"))
