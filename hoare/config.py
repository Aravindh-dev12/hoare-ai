from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HoareConfig:
    base_ref: str | None = None
    language: str = "Auto"
    instructions: str = ""
    test_command: str = ""
    fail_below: float = 0.0
    rules_files: list[str] = field(default_factory=list)
    max_files: int = 200
    max_file_bytes: int = 300_000


def load_config(root: str | Path) -> HoareConfig:
    root = Path(root)
    path = root / "hoare.toml"
    config = HoareConfig()
    if not path.exists():
        return config
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    review = raw.get("review", {}) if isinstance(raw, dict) else {}
    quality = raw.get("quality", {}) if isinstance(raw, dict) else {}
    data = raw.get("data", {}) if isinstance(raw, dict) else {}
    config.base_ref = review.get("base") or None
    config.language = str(review.get("language", "Auto"))
    config.instructions = str(review.get("instructions", ""))
    config.test_command = str(review.get("test_command", ""))
    config.max_files = max(1, min(int(review.get("max_files", 200)), 1000))
    config.max_file_bytes = max(10_000, min(int(review.get("max_file_bytes", 300_000)), 2_000_000))
    config.fail_below = max(0.0, min(float(quality.get("fail_below", 0.0)), 10.0))
    rules = data.get("rules_files", [])
    if isinstance(rules, str):
        rules = [rules]
    config.rules_files = [str(x) for x in rules if str(x).strip()]
    return config
