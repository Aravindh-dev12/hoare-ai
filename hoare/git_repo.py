from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class GitError(RuntimeError):
    pass


@dataclass
class RepoChangeSet:
    root: Path
    base_ref: str
    compare_ref: str
    base_sha: str
    head_sha: str
    mode: str
    files: dict[str, str]
    changed_paths: list[str]
    diff_stat: str
    instructions: str = ""

    @property
    def source(self) -> str:
        return f"git:{self.mode}:{self.base_sha[:12]}..{self.head_sha[:20]}"


def _git(root: Path, *args: str, check: bool = True) -> str:
    process = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, timeout=60
    )
    if check and process.returncode != 0:
        message = (process.stderr or process.stdout).strip()
        raise GitError(message or f"git {' '.join(args)} failed")
    return process.stdout.rstrip("\n")


def find_repo_root(path: str | os.PathLike[str] = ".") -> Path:
    start = Path(path).expanduser().resolve()
    if start.is_file():
        start = start.parent
    process = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        text=True,
        capture_output=True,
        timeout=15,
    )
    if process.returncode != 0:
        raise GitError(f"Not inside a Git repository: {start}")
    return Path(process.stdout.strip()).resolve()


def _ref_exists(root: Path, ref: str) -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    ).returncode == 0


def default_base_ref(root: Path) -> str:
    env_ref = os.getenv("HOARE_BASE_REF", "").strip()
    if env_ref and _ref_exists(root, env_ref):
        return env_ref
    for ref in ("origin/main", "main", "origin/master", "master"):
        if _ref_exists(root, ref):
            return ref
    return "HEAD"


def load_instructions(root: Path) -> str:
    path = root / ".hoareinstructions"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:12_000].strip()


def _ignore_patterns(root: Path) -> list[str]:
    path = root / ".hoareignore"
    if not path.exists():
        return []
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_ignored(path: str, patterns: list[str]) -> bool:
    ignored = False
    posix = path.replace("\\", "/")
    for raw in patterns:
        negate = raw.startswith("!")
        pattern = raw[1:] if negate else raw
        matches = fnmatch.fnmatch(posix, pattern) or PurePosixPath(posix).match(pattern)
        if matches:
            ignored = not negate
    return ignored


def _dirty_fingerprint(root: Path, paths: list[str], head: str) -> str:
    digest = hashlib.sha256()
    digest.update(head.encode())
    for rel in sorted(paths):
        digest.update(rel.encode())
        path = root / rel
        if path.is_file():
            try:
                digest.update(path.read_bytes())
            except OSError:
                pass
    return f"{head}:dirty:{digest.hexdigest()[:16]}"


def _read_worktree_file(root: Path, rel: str, max_bytes: int) -> str | None:
    path = root / rel
    if not path.is_file() or path.is_symlink():
        return None
    try:
        data = path.read_bytes()[: max_bytes + 1]
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    return text + ("\n[HOARE: FILE TRUNCATED]" if truncated else "")


def _read_git_file(root: Path, ref: str, rel: str, max_bytes: int) -> str | None:
    process = subprocess.run(
        ["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True, timeout=30
    )
    if process.returncode != 0:
        return None
    data = process.stdout
    if b"\x00" in data[:8192]:
        return None
    truncated = len(data) > max_bytes
    return data[:max_bytes].decode("utf-8", errors="replace") + (
        "\n[HOARE: FILE TRUNCATED]" if truncated else ""
    )


def _deleted_patch(root: Path, rel: str, mode: str, base: str, compare: str) -> str:
    if mode == "staged":
        args = ("diff", "--cached", "--", rel)
    elif mode == "compare":
        args = ("diff", f"{base}...{compare}", "--", rel)
    elif mode == "unstaged":
        args = ("diff", "--", rel)
    else:
        args = ("diff", f"{base}...HEAD", "--", rel)
    return _git(root, *args, check=False)[:300_000]


def _names(root: Path, *args: str) -> list[str]:
    text = _git(root, *args, check=False)
    return [line.strip() for line in text.splitlines() if line.strip()]


def collect_changes(
    path: str | os.PathLike[str] = ".",
    *,
    base: str | None = None,
    compare: str | None = None,
    staged: bool = False,
    unstaged: bool = False,
    max_files: int = 200,
    max_file_bytes: int = 300_000,
) -> RepoChangeSet:
    if staged and unstaged:
        raise ValueError("Choose either --staged or --unstaged, not both.")
    root = find_repo_root(path)
    base_ref = base or default_base_ref(root)
    compare_ref = compare or "HEAD"
    patterns = _ignore_patterns(root)

    if compare:
        mode = "compare"
        if not _ref_exists(root, base_ref) or not _ref_exists(root, compare_ref):
            raise GitError("Base or compare ref does not exist.")
        base_sha = _git(root, "merge-base", base_ref, compare_ref)
        head_sha = _git(root, "rev-parse", compare_ref)
        changed = _names(root, "diff", "--name-only", f"{base_ref}...{compare_ref}")
        stat = _git(root, "diff", "--stat", f"{base_ref}...{compare_ref}", check=False)
        read_ref = compare_ref
    elif staged:
        mode = "staged"
        base_sha = _git(root, "rev-parse", "HEAD")
        head_sha = _git(root, "write-tree")
        changed = _names(root, "diff", "--cached", "--name-only")
        stat = _git(root, "diff", "--cached", "--stat", check=False)
        read_ref = ":"
    elif unstaged:
        mode = "unstaged"
        base_sha = _git(root, "rev-parse", "HEAD")
        changed = _names(root, "diff", "--name-only") + _names(root, "ls-files", "--others", "--exclude-standard")
        changed = list(dict.fromkeys(changed))
        head_sha = _dirty_fingerprint(root, changed, base_sha)
        stat = _git(root, "diff", "--stat", check=False)
        read_ref = ""
    else:
        mode = "work"
        head_commit = _git(root, "rev-parse", "HEAD")
        if _ref_exists(root, base_ref):
            base_sha = _git(root, "merge-base", base_ref, "HEAD")
            branch_changed = _names(root, "diff", "--name-only", f"{base_ref}...HEAD")
        else:
            base_sha = head_commit
            branch_changed = []
        changed = branch_changed
        changed += _names(root, "diff", "--cached", "--name-only")
        changed += _names(root, "diff", "--name-only")
        changed += _names(root, "ls-files", "--others", "--exclude-standard")
        changed = list(dict.fromkeys(changed))
        head_sha = _dirty_fingerprint(root, changed, head_commit) if changed else head_commit
        stat = _git(root, "diff", "--stat", f"{base_ref}...HEAD", check=False) if branch_changed else ""
        read_ref = ""

    filtered = [p for p in changed if not _is_ignored(p, patterns)]
    if len(filtered) > max_files:
        raise GitError(
            f"Change set has {len(filtered)} files; limit is {max_files}. "
            "Increase review.max_files in hoare.toml if intentional."
        )

    files: dict[str, str] = {}
    for rel in filtered:
        if mode == "compare":
            text = _read_git_file(root, read_ref, rel, max_file_bytes)
        elif mode == "staged":
            process = subprocess.run(
                ["git", "show", f":{rel}"], cwd=root, capture_output=True, timeout=30
            )
            if process.returncode == 0 and b"\x00" not in process.stdout[:8192]:
                data = process.stdout
                text = data[:max_file_bytes].decode("utf-8", errors="replace")
                if len(data) > max_file_bytes:
                    text += "\n[HOARE: FILE TRUNCATED]"
            else:
                text = None
        else:
            text = _read_worktree_file(root, rel, max_file_bytes)
        if text is None:
            patch = _deleted_patch(root, rel, mode, base_ref, compare_ref)
            if patch.strip():
                files[rel] = "[HOARE: DELETED OR NON-TEXT FILE PATCH]\n" + patch
        else:
            files[rel] = text

    if not files:
        raise GitError("No reviewable text changes found.")

    return RepoChangeSet(
        root=root,
        base_ref=base_ref,
        compare_ref=compare_ref,
        base_sha=base_sha,
        head_sha=head_sha,
        mode=mode,
        files=files,
        changed_paths=list(files),
        diff_stat=stat,
        instructions=load_instructions(root),
    )
