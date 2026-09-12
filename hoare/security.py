from __future__ import annotations

import hashlib
import re
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*["\']([^"\'\n]{8,})["\']'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}'),
    re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
]

ALLOWED_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', '.rb', '.php',
    '.cs', '.cpp', '.cc', '.c', '.h', '.hpp', '.kt', '.kts', '.swift', '.scala',
    '.sql', '.html', '.css', '.scss', '.vue', '.svelte', '.sh', '.bash', '.json',
    '.yaml', '.yml', '.toml', '.md', '.txt', '.xml'
}

MAX_FILE_BYTES = 350_000
MAX_TOTAL_BYTES = 1_500_000


def hash_submission(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode('utf-8', 'ignore'))
        h.update(b'\0')
        h.update(files[name].encode('utf-8', 'ignore'))
        h.update(b'\0')
    return h.hexdigest()


def redact_secrets(text: str) -> tuple[str, int]:
    redacted = text
    count = 0
    for pattern in SECRET_PATTERNS:
        def repl(match: re.Match) -> str:
            nonlocal count
            count += 1
            if match.lastindex and match.lastindex >= 2:
                return f'{match.group(1)}="[REDACTED]"'
            return '[REDACTED_SECRET]'
        redacted = pattern.sub(repl, redacted)
    return redacted, count


def read_uploaded_files(paths: list[str] | None) -> dict[str, str]:
    if not paths:
        return {}
    output: dict[str, str] = {}
    total = 0
    for raw in paths:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            continue
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError('Upload is too large. Keep total source text under 1.5 MB.')
        output[path.name] = path.read_text(encoding='utf-8', errors='replace')
    return output
