import os
import secrets
import string
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from accounts.models import User, AuditLog
from accounts.utils import mask_email
from recruitment.models import CandidateProfile, RecruiterProfile, FreelancerProfile


class Command(BaseCommand):
    help = "Seed test users across all platform roles for local development and testing (DEBUG-only)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            type=str,
            default="",
            help="Custom password for all test users (defaults to TEST_USER_PASSWORD in .env)",
        )

    def handle(self, *args, **options):
        # SEC: Strict DEBUG-only guard
        if not getattr(settings, "DEBUG", False):
            raise CommandError("Refusing to run: 'seed_test_users' is strictly restricted to DEBUG=True environments.")

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== HIRENEXA TEST USER SEEDING (DEBUG MODE) ==="))

        env_password = (
            options.get("password")
            or os.environ.get("TEST_USER_PASSWORD", "").strip()
            or getattr(settings, "TEST_USER_PASSWORD", "")
        )

        generated_password = False
        if not env_password:
            # Cryptographically secure random password satisfying all password validators
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
            password = "".join(secrets.choice(alphabet) for _ in range(16)) + "1aA!"
            generated_password = True
        else:
            password = env_password

        # Test users definition
        test_accounts = [
            {
                "username": "test_student",
                "email": "student@hirenexa.local",
                "phone_number": "+919899000001",
                "first_name": "Priya",
                "last_name": "Sharma",
                "role": User.Role.CANDIDATE,
                "profile_model": CandidateProfile,
                "profile_kwargs": {
                    "full_name": "Priya Sharma",
                    "university": "Indian Institute of Technology",
                    "cgpa": "9.2",
                    "skills": "Python, Django, PostgreSQL, React",
                },
            },
            {
                "username": "test_hr",
                "email": "hr@hirenexa.local",
                "phone_number": "+919899000002",
                "first_name": "Rajesh",
                "last_name": "Kumar",
                "role": User.Role.RECRUITER,
                "profile_model": RecruiterProfile,
                "profile_kwargs": {
                    "company_name": "TechCorp Innovations",
                    "designation": "Lead Technical Recruiter",
                },
            },
            {
                "username": "test_company_admin",
                "email": "admin@hirenexa.local",
                "phone_number": "+919899000003",
                "first_name": "Amit",
                "last_name": "Verma",
                "role": User.Role.COMPANY_ADMIN,
                "profile_model": RecruiterProfile,
                "profile_kwargs": {
                    "company_name": "TechCorp Innovations",
                    "designation": "Director of Engineering & Hiring",
                },
            },
            {
                "username": "test_freelancer",
                "email": "freelancer@hirenexa.local",
                "phone_number": "+919899000004",
                "first_name": "Alex",
                "last_name": "Rivers",
                "role": User.Role.FREELANCER,
                "profile_model": FreelancerProfile,
                "profile_kwargs": {
                    "full_name": "Alex Rivers",
                    "headline": "Full-Stack Software Contractor & DevOps",
                    "hourly_rate": 75.00,
                    "skills": "Python, Django, Docker, AWS, React, Kubernetes",
                },
            },
        ]

        now = timezone.now()
        seeded_count = 0

        for acct in test_accounts:
            user = User.objects.filter(username=acct["username"]).first()
            created = False
            if not user:
                user = User(username=acct["username"])
                created = True

            user.email = acct["email"]
            user.phone_number = acct["phone_number"]
            user.first_name = acct["first_name"]
            user.last_name = acct["last_name"]
            user.role = acct["role"]
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True
            user.is_email_verified = True
            user.is_phone_verified = True
            user.email_verified_at = now
            user.phone_verified_at = now
            user.set_password(password)
            user.save()

            # Ensure profile exists
            profile_model = acct.get("profile_model")
            if profile_model:
                profile_model.objects.update_or_create(
                    user=user,
                    defaults=acct.get("profile_kwargs", {}),
                )

            action_type = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ {action_type} {acct['role']} test account: '{user.username}' ({user.email})"
                )
            )
            seeded_count += 1

        AuditLog.objects.create(
            action="TEST_USERS_SEEDED_CLI",
            ip_address="127.0.0.1",
            details={"seeded_count": seeded_count, "generated_password": generated_password},
        )

        self.stdout.write(self.style.SUCCESS(f"\n✓ Successfully seeded {seeded_count} test accounts!"))
        if generated_password:
            self.stdout.write(self.style.WARNING("=" * 70))
            self.stdout.write(self.style.WARNING(f"Generated Test User Password: {password}"))
            self.stdout.write(self.style.WARNING("All 4 seeded accounts share this password. Keep it for testing."))
            self.stdout.write(self.style.WARNING("=" * 70))
        else:
            self.stdout.write(self.style.SUCCESS("✓ Seeded accounts configured with TEST_USER_PASSWORD from environment."))
