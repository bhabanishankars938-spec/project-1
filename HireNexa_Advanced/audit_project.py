import os
import sys
import django

# Add HireNexa_Advanced to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.urls import get_resolver, URLPattern, URLResolver
from django.db import connection

print("="*60)
print("HIRENEXA FULL AUDIT REPORT")
print("="*60)
print(f"DATABASE: {settings.DATABASES['default']['ENGINE']}")
print(f"DEBUG: {settings.DEBUG}")

# 1. URL Pattern Audit
print("\n--- 1. URL AUDIT ---")
resolver = get_resolver()

def extract_urls(urlpatterns, prefix=""):
    patterns = []
    for p in urlpatterns:
        if isinstance(p, URLPattern):
            full_pattern = prefix + str(p.pattern)
            name = p.name
            callback = p.callback.__name__ if hasattr(p, 'callback') and p.callback else str(p.callback)
            patterns.append((full_pattern, name, callback))
        elif isinstance(p, URLResolver):
            full_pattern = prefix + str(p.pattern)
            patterns.extend(extract_urls(p.url_patterns, full_pattern))
    return patterns

all_urls = extract_urls(resolver.url_patterns)
print(f"Total Registered URLs: {len(all_urls)}")
unnamed_urls = [u for u in all_urls if not u[1]]
print(f"Unnamed URLs: {len(unnamed_urls)}")

# 2. Database Model Counts
print("\n--- 2. DATABASE MODEL COUNTS ---")
from django.apps import apps
for model in apps.get_models():
    try:
        cnt = model.objects.count()
        print(f"  {model._meta.app_label}.{model.__name__}: {cnt}")
    except Exception as e:
        print(f"  {model._meta.app_label}.{model.__name__}: ERROR ({e})")

# 3. Location Data Health
print("\n--- 3. LOCATION INTELLIGENCE AUDIT ---")
from recruitment.models import Country, State, District, City, Area, PinCode
print(f"  Countries: {Country.objects.count()}")
print(f"  States: {State.objects.count()}")
print(f"  Districts: {District.objects.count()}")
print(f"  Cities: {City.objects.count()}")
print(f"  Areas: {Area.objects.count()}")
print(f"  PinCodes: {PinCode.objects.count()}")

# Test search_india_locations
from recruitment.api_views import search_india_locations
test_queries = ["Bhubaneswar", "Bangalore", "Deogarh", "Mumbai", "751024", "Remote", "Odisha", "Reamal", "Patia"]
print("\n  Testing search_india_locations:")
for tq in test_queries:
    res = search_india_locations(tq, limit=5)
    print(f"    Query '{tq}' -> {len(res)} results. First: {[r.get('label') for r in res[:1]]}")

# 4. Assessment Engine Audit
print("\n--- 4. ASSESSMENT & EXAM AUDIT ---")
from assessments.models import EntranceTrack, Subject, Topic, Question, Examination, ExamAttempt
print(f"  Tracks: {EntranceTrack.objects.count()}")
print(f"  Subjects: {Subject.objects.count()}")
print(f"  Topics: {Topic.objects.count()}")
print(f"  Questions: {Question.objects.count()}")
print(f"  Approved Questions: {Question.objects.filter(status=Question.Status.APPROVED).count()}")
print(f"  Examinations: {Examination.objects.count()}")
print(f"  Exam Attempts: {ExamAttempt.objects.count()}")

exams = Examination.objects.all()[:10]
for ex in exams:
    q_cnt = ex.questions.count() or ex.exam_questions.count()
    print(f"    Exam: '{ex.title}' | Slug: '{ex.slug}' | Duration: {ex.duration_minutes}m | Max Attempts: {ex.max_attempts} | Qs: {q_cnt}")

# 5. Accounts / Users Audit
print("\n--- 5. ACCOUNTS & USERS AUDIT ---")
from accounts.models import User
print(f"  Total Users: {User.objects.count()}")
for r, r_name in User.Role.choices:
    print(f"    Role {r_name} ({r}): {User.objects.filter(role=r).count()}")

print("\nAUDIT COMPLETE.")
