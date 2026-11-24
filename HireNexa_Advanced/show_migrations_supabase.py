import os
import sys

os.environ["USE_SQLITE"] = "0"
os.environ["DATABASE_URL"] = "postgresql://postgres.lnvmixljyhujzkoxlfvw:ceaJaMms8ka8DOsc@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.core.management import call_command
call_command("showmigrations")
