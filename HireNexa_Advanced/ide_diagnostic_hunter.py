import os
import ast
import re
import sys

def check_file(filepath):
    issues = []
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        lines = content.splitlines()

    # 1. Parse AST
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as e:
        issues.append({
            'file': filepath,
            'line': e.lineno,
            'col': e.offset,
            'code': 'syntax-error',
            'severity': 'Critical',
            'msg': f"SyntaxError: {e.msg}"
        })
        return issues

    # 2. Check for invalid escape sequences
    for i, line in enumerate(lines, 1):
        # find non-raw strings with invalid escape sequences
        for match in re.finditer(r'(?<!r)(["\'])(?:(?=(\\?))\2.)*?\1', line):
            s = match.group(0)
            # check backslashes not followed by valid escapes
            bad_escapes = re.findall(r'\\[^abfnrtv\\\'"0-7xuU]', s)
            if bad_escapes:
                issues.append({
                    'file': filepath,
                    'line': i,
                    'col': match.start(),
                    'code': 'W605',
                    'severity': 'Low',
                    'msg': f"SyntaxWarning: invalid escape sequence '{bad_escapes[0]}'"
                })

    # 3. Check imports and undefined names
    imported_names = set()
    used_names = set()
    
    class ImportVisitor(ast.NodeVisitor):
        def visit_Import(self, node):
            for alias in node.names:
                imported_names.add((alias.asname or alias.name.split('.')[0], node.lineno))
            self.generic_visit(node)
            
        def visit_ImportFrom(self, node):
            for alias in node.names:
                imported_names.add((alias.asname or alias.name, node.lineno))
            self.generic_visit(node)

        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Load, ast.Del)):
                used_names.add(node.id)
            self.generic_visit(node)

    visitor = ImportVisitor()
    visitor.visit(tree)

    # Check for unused imports (typical IDE diagnostic)
    for name, lineno in imported_names:
        if name not in used_names and name not in ('_', '__all__'):
            issues.append({
                'file': filepath,
                'line': lineno,
                'col': 1,
                'code': 'unused-import',
                'severity': 'Low',
                'msg': f"'{name}' imported but unused"
            })

    return issues

all_issues = []
for root, dirs, files in os.walk('.'):
    if any(p in root for p in ['.git', '__pycache__', 'venv', 'site-packages', 'brain']):
        continue
    for f in files:
        if f.endswith('.py'):
            fp = os.path.join(root, f)
            all_issues.extend(check_file(fp))

print(f"Total Python AST/Linter issues detected: {len(all_issues)}")
for issue in all_issues[:30]:
    print(f"[{issue['severity']}] {issue['file']}:{issue['line']} - {issue['code']}: {issue['msg']}")

with open('all_ide_diagnostics_found.txt', 'w', encoding='utf-8') as out:
    for idx, iss in enumerate(all_issues, 1):
        out.write(f"#{idx} [{iss['severity']}] {iss['file']}:{iss['line']} - {iss['code']}: {iss['msg']}\n")
