import os
import re
import sys
import glob
import ast
import django

os.environ["USE_SQLITE"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.urls import get_resolver
from django.template.loader import get_template
from django.conf import settings
from django.apps import apps

diagnostics = []

def add_diag(severity, category, file_path, line_no, message):
    diagnostics.append({
        "severity": severity,
        "category": category,
        "file": file_path,
        "line": line_no,
        "message": message
    })

# 1. URL pattern registry
resolver = get_resolver()
all_url_names = set()

def extract_urls(urlpatterns, prefix=""):
    for pattern in urlpatterns:
        if hasattr(pattern, 'name') and pattern.name:
            all_url_names.add(pattern.name)
        if hasattr(pattern, 'url_patterns'):
            extract_urls(pattern.url_patterns, prefix)

extract_urls(resolver.url_patterns)
print(f"Total Registered URL names: {len(all_url_names)}")

# 2. Check all templates for broken {% url %} tags
template_dirs = settings.TEMPLATES[0]["DIRS"]
template_files = []
for td in template_dirs:
    for root, _, files in os.walk(td):
        for f in files:
            if f.endswith(".html"):
                template_files.append((td, os.path.relpath(os.path.join(root, f), td)))

url_tag_pattern = re.compile(r"\{%\s*url\s+['\"]([a-zA-Z0-9_:\-]+)['\"]")

for td, rel_path in template_files:
    full_path = os.path.join(td, rel_path)
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            for lno, line in enumerate(f, 1):
                matches = url_tag_pattern.findall(line)
                for m in matches:
                    # check if m exists in registered url names
                    # Handle namespace:
                    clean_name = m.split(":")[-1] if ":" in m else m
                    if m not in all_url_names and clean_name not in all_url_names:
                        add_diag("High", "Broken URL Reference", rel_path, lno, f"URL name '{m}' not found in registered URL patterns")
    except Exception as e:
        add_diag("High", "Template Read Error", rel_path, 0, str(e))

# 3. Python files AST & Syntax Warnings & Reverse calls
py_files = glob.glob("**/*.py", recursive=True)
for pf in py_files:
    if "venv" in pf or ".git" in pf or "site-packages" in pf:
        continue
    with open(pf, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()
    
    # Check invalid escape sequences
    raw_lines = code.split("\n")
    for lno, line in enumerate(raw_lines, 1):
        if re.search(r'(?<!r)("|\')[^"\']*?\\[a-zA-Z][^"\']*?("|\')', line):
            # check common valid escapes: \n, \t, \r, \b, \f, \v, \', \", \\
            m = re.findall(r'\\[^ntrbfva\'"\\0-9]', line)
            if m:
                add_diag("Low", "Syntax Warning / Escape Sequence", pf, lno, f"Invalid escape sequence: {m}")

    try:
        tree = ast.parse(code, filename=pf)
    except SyntaxError as e:
        add_diag("Critical", "Syntax Error", pf, e.lineno, str(e))
        continue

    # Check for reverse('...') calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("reverse", "reverse_lazy"):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    target_url = node.args[0].value
                    clean_target = target_url.split(":")[-1] if ":" in target_url else target_url
                    if target_url not in all_url_names and clean_target not in all_url_names:
                        add_diag("High", "Broken Reverse URL", pf, node.lineno, f"Reverse call to unknown URL '{target_url}'")

# 4. Check for undefined fields or broken model calls in views
print(f"Diagnostics identified so far: {len(diagnostics)}")
for d in diagnostics[:20]:
    print(f"[{d['severity']}] {d['category']} in {d['file']}:{d['line']} - {d['message']}")

if len(diagnostics) > 20:
    print(f"... and {len(diagnostics) - 20} more")

# Output full diagnostics to a log file
with open("audit_76_diagnostics.txt", "w", encoding="utf-8") as out:
    for idx, d in enumerate(diagnostics, 1):
        out.write(f"#{idx} [{d['severity']}] {d['category']} | {d['file']}:{d['line']} | {d['message']}\n")

print(f"\nWritten {len(diagnostics)} diagnostics to audit_76_diagnostics.txt")
