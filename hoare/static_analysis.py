from __future__ import annotations

import ast
import re
from .models import Finding


def _finding(category: str, severity: str, title: str, description: str, recommendation: str, file: str, evidence: str = '', line: int | None = None) -> Finding:
    return Finding(
        category=category,
        severity=severity,
        title=title,
        description=description,
        recommendation=recommendation,
        file=file,
        evidence=evidence[:240],
        line=line,
        confidence=0.92,
    )


def analyze_file(name: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()

    patterns = [
        (r'(?i)(?:execute\s*\(\s*f["\']|execute\s*\([^\n]*(?:\+|\.format\())', 'security', 'critical', 'Possible SQL injection', 'SQL appears to be built through interpolation or concatenation.', 'Use parameterized queries / prepared statements.'),
        (r'(?i)\beval\s*\(|\bexec\s*\(', 'security', 'high', 'Dynamic code execution', 'Dynamic evaluation can execute attacker-controlled input.', 'Remove eval/exec or strictly constrain and parse allowed input.'),
        (r'subprocess\.[A-Za-z_]+\([^\n]*shell\s*=\s*True', 'security', 'high', 'Shell execution enabled', 'shell=True increases command-injection risk.', 'Pass an argument list with shell=False and validate inputs.'),
        (r'\.innerHTML\s*=|dangerouslySetInnerHTML', 'security', 'high', 'Potential HTML injection', 'Untrusted data written as HTML can create XSS.', 'Escape/sanitize untrusted content or use safe text rendering.'),
        (r'(?i)SELECT\s+\*\s+FROM', 'performance', 'low', 'Broad SELECT * query', 'Fetching every column can increase IO and couple code to schema changes.', 'Select only the columns required by the caller.'),
        (r'(?i)TODO|FIXME|HACK', 'maintainability', 'info', 'Unresolved implementation marker', 'A TODO/FIXME/HACK marker remains in submitted code.', 'Track it explicitly or resolve it before production merge.'),
    ]

    for idx, line in enumerate(lines, start=1):
        for pattern, category, severity, title, desc, rec in patterns:
            if re.search(pattern, line):
                findings.append(_finding(category, severity, title, desc, rec, name, line.strip(), idx))

    if name.endswith('.py'):
        try:
            tree = ast.parse(text, filename=name)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(node.body) > 50:
                    findings.append(_finding('maintainability', 'medium', 'Large function', f'Function `{node.name}` is large and harder to test/review.', 'Split the function into smaller units with one responsibility.', name, line=node.lineno))
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    findings.append(_finding('reliability', 'medium', 'Bare except block', 'A bare except can hide system-exiting and unexpected errors.', 'Catch specific exception types and preserve context.', name, line=node.lineno))
        except SyntaxError as exc:
            findings.append(_finding('correctness', 'high', 'Python syntax error', str(exc), 'Fix the parse error before deeper review.', name, line=exc.lineno))

    return findings


def run_static_analysis(files: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    for name, text in files.items():
        findings.extend(analyze_file(name, text))
    return findings
