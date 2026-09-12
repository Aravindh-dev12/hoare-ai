from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .git_repo import RepoChangeSet
from .models import ReviewResult
from .validation import ValidationRun


def session_root(repo_root: str | Path) -> Path:
    path = Path(repo_root) / ".hoare" / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_review_session(
    review: ReviewResult,
    graph: str,
    changes: RepoChangeSet,
    validation: ValidationRun | None = None,
) -> Path:
    root = session_root(changes.root)
    target = root / review.review_id
    target.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "review_id": review.review_id,
        "created_at": review.created_at,
        "base_ref": changes.base_ref,
        "compare_ref": changes.compare_ref,
        "base_sha": changes.base_sha,
        "head_sha": changes.head_sha,
        "mode": changes.mode,
        "changed_paths": changes.changed_paths,
        "diff_stat": changes.diff_stat,
        "model_backend": review.model_backend,
        "model_name": review.model_name,
        "quality_score": review.quality_score,
        "risk_level": review.risk_level,
        "validation": validation.to_dict() if validation else None,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (target / "review.json").write_text(review.model_dump_json(indent=2), encoding="utf-8")
    (target / "architecture.mmd").write_text(graph, encoding="utf-8")
    (root / "latest").write_text(review.review_id, encoding="utf-8")
    return target


def list_sessions(repo_root: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    root = session_root(repo_root)
    rows: list[dict[str, Any]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        manifest = path / "manifest.json"
        if not manifest.exists():
            continue
        try:
            rows.append(json.loads(manifest.read_text(encoding="utf-8")))
        except Exception:
            continue
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows[: max(1, min(int(limit), 100))]


def load_session(repo_root: str | Path, review_id: str) -> tuple[dict[str, Any], ReviewResult, str]:
    root = session_root(repo_root)
    if review_id == "latest":
        latest = root / "latest"
        if not latest.exists():
            raise FileNotFoundError("No Hoare reviews have been saved yet.")
        review_id = latest.read_text(encoding="utf-8").strip()
    target = root / review_id
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    review = ReviewResult.model_validate_json((target / "review.json").read_text(encoding="utf-8"))
    graph = (target / "architecture.mmd").read_text(encoding="utf-8")
    return manifest, review, graph
