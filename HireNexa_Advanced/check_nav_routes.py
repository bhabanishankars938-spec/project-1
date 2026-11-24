import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["USE_SQLITE"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client
from accounts.models import User
from recruitment.models import Organization, OrganizationMember, Job

client = Client()

# Provision or fetch test users for all 5 roles
owner_user, _ = User.objects.get_or_create(
    username="test_audit_owner",
    defaults={"email": "owner@hirenexa.internal", "role": User.Role.OWNER, "is_superuser": True, "is_staff": True}
)
owner_user.set_password("AuditPass123!")
owner_user.save()

company_admin_user, _ = User.objects.get_or_create(
    username="test_audit_co_admin",
    defaults={"email": "company_admin@hirenexa.internal", "role": User.Role.COMPANY_ADMIN}
)
company_admin_user.set_password("AuditPass123!")
company_admin_user.save()

recruiter_user, _ = User.objects.get_or_create(
    username="test_audit_recruiter",
    defaults={"email": "recruiter@hirenexa.internal", "role": User.Role.RECRUITER}
)
recruiter_user.set_password("AuditPass123!")
recruiter_user.save()

candidate_user, _ = User.objects.get_or_create(
    username="test_audit_candidate",
    defaults={"email": "candidate@hirenexa.internal", "role": User.Role.CANDIDATE}
)
candidate_user.set_password("AuditPass123!")
candidate_user.save()

freelancer_user, _ = User.objects.get_or_create(
    username="test_audit_freelancer",
    defaults={"email": "freelancer@hirenexa.internal", "role": User.Role.FREELANCER}
)
freelancer_user.set_password("AuditPass123!")
freelancer_user.save()

# Ensure company org exists and link recruiter & company admin
test_org, _ = Organization.objects.get_or_create(
    name="HireNexa Tech Labs",
    defaults={"slug": "hirenexa-tech-labs", "verification_status": Organization.VerificationStatus.APPROVED, "is_active": True}
)
OrganizationMember.objects.get_or_create(
    organization=test_org,
    user=company_admin_user,
    defaults={"role": OrganizationMember.MemberRole.ADMIN, "is_active": True}
)
OrganizationMember.objects.get_or_create(
    organization=test_org,
    user=recruiter_user,
    defaults={"role": OrganizationMember.MemberRole.HR, "is_active": True}
)

# Test job
test_job, _ = Job.objects.get_or_create(
    title="Senior Backend Engineer",
    organization=test_org,
    defaults={
        "recruiter": recruiter_user,
        "company_name": test_org.name,
        "status": Job.Status.ACTIVE,
        "is_active": True,
        "location": "Bhubaneswar, Odisha",
        "city": "Bhubaneswar",
        "state": "Odisha",
    }
)

nav_tests = [
    # Core Public Navigation
    ("Home", "/", 200, None),
    ("Find Jobs", "/jobs/", 200, None),
    ("Companies", "/companies/", 200, None),
    ("AI Career", "/candidate/career-assistant/", 200, candidate_user),
    ("Explore - Freelance Gigs", "/projects/", 200, None),
    ("Explore - AI Intelligence", "/ai/", 200, None),
    ("Explore - MCQ Entrance Hub", "/assessments/entrance-prep/", 200, None),
    ("Explore - MCQ Entrance Canonical", "/assessments/entrance/", 200, None),
    ("Explore - Career Resources", "/career-guidance/", 200, None),
    ("Explore - Market Intelligence", "/market-intelligence/", 200, None),
    ("Explore - Announcements & Bulletins", "/news/", 200, None),
    ("Premium Pricing", "/pricing/", 200, None),
    ("Unified Login", "/accounts/login/", 200, None),
    ("Unified Signup", "/accounts/signup/", 200, None),
    
    # Vanity / Dedicated Portals
    ("Candidate Login", "/candidate/login/", 200, None),
    ("HR Login", "/hr/login/", 200, None),
    ("Company Login", "/company/login/", 200, None),
    ("Owner Login", "/owner/login/", 200, None),
    ("Freelancer Login", "/freelancer/login/", 200, None),
    
    # Dashboards by Role
    ("Owner Dashboard", "/owner/", 200, owner_user),
    ("Company Dashboard", "/company/", 200, company_admin_user),
    ("Recruiter Dashboard", "/hr/", 200, recruiter_user),
    ("Candidate Dashboard", "/candidate/", 200, candidate_user),
    ("Freelancer Dashboard", "/freelancer/", 200, freelancer_user),
    
    # Section 5.1 Examination Routes
    ("Exam List", "/assessments/exams/", 200, candidate_user),
    ("Entrance Chapters", "/assessments/entrance/chapters/", 200, candidate_user),
    ("Entrance Practice", "/assessments/entrance/practice/", 200, candidate_user),
    ("Entrance Mock Test", "/assessments/entrance/mock-test/", 200, candidate_user),
    ("Entrance Results", "/assessments/entrance/results/", 200, candidate_user),
    ("Entrance Analytics", "/assessments/entrance/analytics/", 200, candidate_user),

    # HireNexa Connect Routes (V4 Upgrade)
    ("Connect Dashboard", "/connect/", 200, candidate_user),
    ("Connect My Meetings", "/connect/my-meetings/", 200, candidate_user),
    ("Connect Upcoming Interviews", "/connect/upcoming-interviews/", 200, candidate_user),
    ("Connect Schedule Form", "/connect/schedule/", 200, recruiter_user),
    ("Connect Public Events Directory", "/connect/events/", 200, None),
    ("Connect Meeting History", "/connect/history/", 200, candidate_user),
    ("Connect Meeting Settings", "/connect/settings/", 200, candidate_user),
    ("Connect Smart Calendar", "/connect/calendar/", 200, candidate_user),
    ("Robots.txt SEO & Privacy Endpoint", "/robots.txt", 200, None),
    
    # Candidate Sub-modules
    ("Candidate Applications", "/candidate/applications/", 200, candidate_user),
    ("Candidate Saved Jobs", "/candidate/saved-jobs/", 200, candidate_user),
    ("Candidate Portfolio", "/candidate/portfolio/", 200, candidate_user),
    ("Candidate Profile Edit", "/profile/", 200, candidate_user),
    ("Candidate Account Settings", "/settings/account/", 200, candidate_user),
    ("Candidate Security Settings", "/settings/security/", 200, candidate_user),

    # HR Sub-modules
    ("HR Job Create Page", "/jobs/create/", 200, recruiter_user),
    ("HR Job Applicants Page", f"/jobs/{test_job.id}/applicants/", 200, recruiter_user),

    # Location Search and Hierarchy APIs
    ("Location Autocomplete API (Blank)", "/api/locations/autocomplete/", 200, None),
    ("Location Autocomplete API (Query)", "/api/locations/autocomplete/?q=Bhubaneswar", 200, None),
    ("Location Hierarchy API (States)", "/api/locations/hierarchy/?level=states", 200, None),
    ("Location Hierarchy API (Cities)", "/api/locations/hierarchy/?level=cities&state_name=Odisha", 200, None),
    ("Location Hierarchy API (Districts)", "/api/locations/hierarchy/?level=districts&state_name=Odisha", 200, None),
]

print("="*70)
print("RUNNING COMPLETE COMPREHENSIVE NAVIGATION & MODULE AUDIT")
print("="*70)

all_passed = True
for label, path, expected_status, user in nav_tests:
    if user:
        client.force_login(user)
    else:
        client.logout()

    try:
        resp = client.get(path)
        status = resp.status_code
        if status == expected_status:
            print(f"[PASS] {label:<35} | {path:<40} -> HTTP {status}")
        elif status == 302 and expected_status == 200:
            print(f"[WARN: REDIRECT] {label:<35} | {path:<40} -> HTTP 302 to {resp.url}")
            all_passed = False
        else:
            print(f"[FAIL] {label:<35} | {path:<40} -> HTTP {status} (Expected {expected_status})")
            all_passed = False
    except Exception as e:
        print(f"[ERROR] {label:<35} | {path:<40} -> Exception: {e}")
        all_passed = False

if all_passed:
    print("\nALL MODULES & NAVIGATION AUDITS PASSED!")
    sys.exit(0)
else:
    print("\nSome routes encountered warnings or errors.")
    sys.exit(1)
