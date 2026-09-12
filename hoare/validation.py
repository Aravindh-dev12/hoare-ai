from __future__ import annotations

import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Finding


@dataclass
class ValidationRun:
    command: str
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def run_validation(command: str, cwd: str | Path, timeout_seconds: int = 180) -> ValidationRun:
    if not command.strip():
        raise ValueError("Validation command cannot be empty.")
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=Path(cwd),
            shell=True,
            text=True,
            capture_output=True,
            timeout=max(5, min(int(timeout_seconds), 3600)),
        )
        return ValidationRun(
            command=command,
            exit_code=proc.returncode,
            duration_seconds=round(time.monotonic() - started, 2),
            stdout=proc.stdout[-20_000:],
            stderr=proc.stderr[-20_000:],
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ValidationRun(
            command=command,
            exit_code=124,
            duration_seconds=round(time.monotonic() - started, 2),
            stdout=stdout[-20_000:],
            stderr=stderr[-20_000:],
            timed_out=True,
        )


def validation_finding(result: ValidationRun) -> Finding | None:
    if result.exit_code == 0:
        return None
    if result.timed_out:
        return Finding(
            category="testing",
            severity="high",
            title="Validation command timed out",
            description=f"The explicit local validation command exceeded its timeout: {result.command}",
            evidence=(result.stderr or result.stdout)[-1000:],
            recommendation="Inspect the hanging test/build and rerun it before merging.",
            confidence=1.0,
        )
    return Finding(
        category="correctness",
        severity="high",
        title="Local validation failed",
        description=f"The explicit validation command exited with status {result.exit_code}: {result.command}",
        evidence=(result.stderr or result.stdout)[-1000:],
        recommendation="Fix the failing tests/build before merging this change.",
        confidence=1.0,
    )
