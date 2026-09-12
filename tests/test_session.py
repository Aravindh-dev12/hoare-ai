from pathlib import Path

from hoare.git_repo import RepoChangeSet
from hoare.models import ReviewResult
from hoare.session import load_session, save_review_session


def test_session_persists_pins_without_raw_source(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()

    review = ReviewResult(
        review_id="review-123",
        user_id="local:test",
        created_at="2026-09-12T00:00:00+00:00",
        language="Python",
        code_hash="hash",
        quality_score=9.2,
        risk_level="LOW",
        summary="Looks good.",
        change_intent="Refactor service boundary.",
        findings=[],
        chapters=[],
        architecture_notes=[],
        validation_plan=[],
        strengths=["Small change"],
        matched_rules=[],
        file_count=1,
        source="git:work:abc..def",
        model_backend="openai",
        model_name="Qwen/Qwen3.5-4B",
    )
    changes = RepoChangeSet(
        root=root,
        base_ref="main",
        compare_ref="HEAD",
        base_sha="a" * 40,
        head_sha="b" * 40,
        mode="work",
        files={"secret.py": "TOP_SECRET_SOURCE_CONTENT"},
        changed_paths=["secret.py"],
        diff_stat="1 file changed",
    )

    path = save_review_session(review, "graph TD\n", changes)
    manifest, loaded, graph = load_session(root, "latest")

    assert manifest["base_sha"] == "a" * 40
    assert manifest["head_sha"] == "b" * 40
    assert loaded.review_id == "review-123"
    assert graph == "graph TD\n"

    persisted_text = "\n".join(
        p.read_text(encoding="utf-8") for p in path.iterdir() if p.is_file()
    )
    assert "TOP_SECRET_SOURCE_CONTENT" not in persisted_text
