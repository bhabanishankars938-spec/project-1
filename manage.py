#!/usr/bin/env python
"""
HireNexa V4 Root Directory Management Script.
Delegates to HireNexa_Advanced/manage.py with automated sys.path resolution.
Enables running `python manage.py <command>` from the project root.
"""
import os
import sys
from pathlib import Path

# Add the inner HireNexa_Advanced directory to sys.path so config and apps resolve cleanly
ROOT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ROOT_DIR / "HireNexa_Advanced"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Ensure working directory is set to PROJECT_DIR for relative path lookups
os.chdir(PROJECT_DIR)

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
