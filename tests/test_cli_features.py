import sys
from pathlib import Path

from hoare.cli import build_parser
from hoare.exporters import render_sarif
from hoare.models import Finding, ReviewResult
from hoare.validation import run_validation, validation_finding


def sample_review() -> ReviewResult:
    return ReviewResult(
        review_id="r1",
        user_id="u1",
        created_at="2026-09-12T00:00:00+00:00",
        language="Python",
        code_hash="abc",
        quality_score=8.0,
        risk_level="MEDIUM",
        summary="Review summary",
        change_intent="Change behavior",
        findings=[Finding(
            category="security",
            severity="high",
            title="Unsafe query",
            description="Query includes untrusted input.",
            file="db.py",
            line=12,
            recommendation="Use parameters.",
            confidence=0.95,
        )],
        chapters=[],
        architecture_notes=[],
        validation_plan=[],
        strengths=[],
        matched_rules=[],
        file_count=1,
        source="test",
        model_backend="static",
        model_name="",
    )


def test_sarif_has_location_and_rule():
    sarif = render_sarif(sample_review())
    run = sarif["runs"][0]
    assert run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "db.py"
    assert run["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 12
    assert run["tool"]["driver"]["rules"]


def test_validation_pass_and_failure(tmp_path: Path):
    ok = run_validation(f'"{sys.executable}" -c "print(123)"', tmp_path, 30)
    assert ok.exit_code == 0
    assert validation_finding(ok) is None

    bad = run_validation(f'"{sys.executable}" -c "raise SystemExit(2)"', tmp_path, 30)
    assert bad.exit_code == 2
    finding = validation_finding(bad)
    assert finding is not None
    assert finding.severity == "high"


def test_cli_parses_local_review_scope():
    args = build_parser().parse_args(["review", ".", "--staged", "--format", "sarif"])
    assert args.command == "review"
    assert args.staged is True
    assert args.format == "sarif"
