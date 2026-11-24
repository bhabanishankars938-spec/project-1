import os
import sys
import django

os.environ["USE_SQLITE"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client
from accounts.models import User

client = Client()

test_recruiter, _ = User.objects.get_or_create(username="test_recruiter", defaults={"email": "recruiter@example.com", "role": User.Role.RECRUITER})
test_candidate, _ = User.objects.get_or_create(username="test_candidate", defaults={"email": "candidate@example.com", "role": User.Role.CANDIDATE})

routes = [
    ("/", 200, None),
    ("/about/", 200, None),
    ("/contact/", 200, None),
    ("/career-guidance/", 200, None),
    ("/interview-prep/", 200, None),
    ("/resume-builder/", 200, None),
    ("/salary-insights/", 200, None),
    ("/help/", 200, None),
    ("/faq/", 200, None),
    ("/jobs/", 200, None),
    ("/ai/", 200, None),
    ("/resume-analyzer/", 200, None),
    ("/companies/", 200, None),
    ("/projects/", 200, None),
    ("/news/", 200, None),
    # Authenticated checks
    ("/recruiter/dashboard/", 200, test_recruiter),
    ("/candidate/", 200, test_candidate),
    ("/candidate/portfolio/", 200, test_candidate),
    ("/candidate/career-assistant/", 200, test_candidate),
    ("/career/aco/", 200, test_candidate),
    ("/market-intelligence/", 200, None),
    ("/jobs/discovery/", 200, None),
    ("/assessments/", 200, test_candidate),
    ("/assessments/entrance-prep/", 200, test_candidate),
]

print("Executing comprehensive route & role verification suite...")
all_passed = True
for r, expected_status, user in routes:
    if user:
        client.force_login(user)
    else:
        client.logout()
    try:
        resp = client.get(r)
        status = resp.status_code
        is_ok = (status == expected_status)
        symbol = "✓" if is_ok else f"✗ (Got {status}, expected {expected_status})"
        role_label = f"[{user.role if user else 'ANON'}]"
        print(f"[{symbol}] {role_label} {r} -> HTTP {status}")
        if not is_ok:
            all_passed = False
    except Exception as e:
        print(f"[ERROR] {r} -> Exception: {e}")
        all_passed = False

if all_passed:
    print("\nALL VERIFICATIONS PASSED: 100% ROUTE RELIABILITY ACROSS ALL PORTALS!")
    sys.exit(0)
else:
    print("\nSome routes did not return expected status.")
    sys.exit(1)
