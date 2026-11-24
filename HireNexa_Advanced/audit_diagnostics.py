import os
import sys
import glob
import re
import ast
import django

os.environ["USE_SQLITE"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.template.loader import get_template
from django.conf import settings

print("=" * 60)
print("HIRENEXA V6 ENTERPRISE AUDIT & DIAGNOSTIC SCANNER")
print("=" * 60)

# 1. AST Python Syntax Scan across all py files
py_errors = []
py_files = glob.glob("**/*.py", recursive=True)
for pf in py_files:
    if "venv" in pf or ".git" in pf or "site-packages" in pf:
        continue
    try:
        with open(pf, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
            ast.parse(code, filename=pf)
    except SyntaxError as e:
        py_errors.append((pf, f"SyntaxError at line {e.lineno}: {e.msg}"))
    except Exception as e:
        py_errors.append((pf, f"ParseError: {e}"))

print(f"Python Files Scanned: {len(py_files)}")
print(f"Python Syntax Errors Found: {len(py_errors)}")
for pf, err in py_errors:
    print(f"  [ERROR] {pf}: {err}")

# 2. Template Compilation & Raw Variable Scan
template_dirs = settings.TEMPLATES[0]["DIRS"]
template_files = []
for td in template_dirs:
    for root, _, files in os.walk(td):
        for f in files:
            if f.endswith(".html"):
                template_files.append(os.path.relpath(os.path.join(root, f), td))

template_compile_errors = []
raw_tag_warnings = []
empty_tag_warnings = []

# Pattern to detect raw unrendered template tags in static/literal output or malformed syntax
for tf in template_files:
    try:
        t = get_template(tf)
    except Exception as e:
        template_compile_errors.append((tf, str(e)))
        continue
    
    # Check source file content for unclosed or empty tags
    full_path = os.path.join(template_dirs[0], tf)
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            for idx, line in enumerate(lines, 1):
                # Detect empty {{ }} or {% %}
                if re.search(r"\{\{\s*\}\}", line):
                    empty_tag_warnings.append((tf, idx, "Empty {{ }} tag found"))
                if re.search(r"\{%\s*%\}", line):
                    empty_tag_warnings.append((tf, idx, "Empty {% %} tag found"))

print(f"\nHTML Templates Scanned: {len(template_files)}")
print(f"Template Compilation Errors: {len(template_compile_errors)}")
for tf, err in template_compile_errors:
    print(f"  [FAIL] {tf}: {err}")
print(f"Empty/Malformed Template Tags Found: {len(empty_tag_warnings)}")
for tf, idx, msg in empty_tag_warnings:
    print(f"  [WARN] {tf}:{idx} -> {msg}")

# 3. Model & Relationship Check
from accounts.models import User
from recruitment.models import Organization, Job, Application, Interview
from assessments.models import Question, Examination, Subject, Topic, ExamAttempt

print("\nDatabase Models & Record Counts (SQLite):")
print(f"  Users: {User.objects.count()}")
print(f"  Organizations: {Organization.objects.count()}")
print(f"  Jobs: {Job.objects.count()}")
print(f"  Applications: {Application.objects.count()}")
print(f"  Interviews: {Interview.objects.count()}")
print(f"  Examinations: {Examination.objects.count()}")
print(f"  Subjects: {Subject.objects.count()}")
print(f"  Topics: {Topic.objects.count()}")
print(f"  Questions: {Question.objects.count()}")
print(f"  Exam Attempts: {ExamAttempt.objects.count()}")

# 4. Check for PYQ and Question Model fields
print("\nQuestion Model Schema Audit:")
q_fields = [f.name for f in Question._meta.get_fields()]
print(f"  Fields on Question: {q_fields}")
has_year = "year" in q_fields
has_exam_name = "exam_name" in q_fields or "examination" in q_fields
has_source = "source_reference" in q_fields or "source" in q_fields or "source_exam" in q_fields
has_qtype = "question_type" in q_fields
print(f"  has_year: {has_year}, has_source: {has_source}, has_question_type: {has_qtype}")

# 5. Check Zoom and Interview model fields
print("\nInterview Model Schema Audit:")
i_fields = [f.name for f in Interview._meta.get_fields()]
print(f"  Fields on Interview: {i_fields}")
has_meeting_id = "meeting_id" in i_fields
has_provider = "provider" in i_fields
has_join_url = "meeting_link" in i_fields or "join_url" in i_fields
print(f"  has_meeting_id: {has_meeting_id}, has_provider: {has_provider}, has_join_url: {has_join_url}")

# 6. Check Location Models & Organization Address fields
print("\nOrganization Address Fields Audit:")
org_fields = [f.name for f in Organization._meta.get_fields()]
print(f"  State/City/Area refs on Organization: 'state_ref' in org={ 'state_ref' in org_fields }, 'city_ref'={ 'city_ref' in org_fields }")
print(f"  Building/Office/Formatted Address: 'building_name' in org={ 'building_name' in org_fields }, 'formatted_address'={ 'formatted_address' in org_fields }")

print("\n" + "=" * 60)
print("AUDIT SCAN COMPLETE")
print("=" * 60)
