import subprocess
from pathlib import Path

import pytest

from hoare.git_repo import GitError, collect_changes


def git(root: Path, *args: str):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Hoare Test")
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(root, "add", "app.py")
    git(root, "commit", "-m", "initial")
    return root


def test_collects_unstaged_and_pins_dirty_state(tmp_path):
    root = make_repo(tmp_path)
    (root / "app.py").write_text("value = 2\n", encoding="utf-8")
    changes = collect_changes(root, base="HEAD", unstaged=True)
    assert changes.mode == "unstaged"
    assert changes.changed_paths == ["app.py"]
    assert changes.files["app.py"] == "value = 2\n"
    assert ":dirty:" in changes.head_sha


def test_collects_staged_index(tmp_path):
    root = make_repo(tmp_path)
    (root / "new.py").write_text("print('hello')\n", encoding="utf-8")
    git(root, "add", "new.py")
    changes = collect_changes(root, staged=True)
    assert changes.mode == "staged"
    assert "new.py" in changes.files
    assert changes.files["new.py"] == "print('hello')\n"


def test_hoareignore_filters_generated_files(tmp_path):
    root = make_repo(tmp_path)
    (root / ".hoareignore").write_text("generated/**\n", encoding="utf-8")
    (root / "generated").mkdir()
    (root / "generated" / "x.py").write_text("bad = True\n", encoding="utf-8")
    with pytest.raises(GitError, match="No reviewable text changes"):
        collect_changes(root, unstaged=True)
