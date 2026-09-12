from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests

from .config import load_config
from .exporters import render, render_terminal, write_output
from .git_repo import GitError, collect_changes, find_repo_root
from .github_source import fetch_pr_context
from .history import HistoryStore
from .inference import get_config as get_inference_config, inference_status
from .reviewer import quality_score, review_code, risk_level
from .rules import Rule, load_rules
from .session import list_sessions, load_session, save_review_session
from .validation import run_validation, validation_finding

VERSION = "0.2.0"


def _user_id() -> str:
    explicit = os.getenv("HOARE_USER_ID", "").strip()
    if explicit:
        return explicit
    raw = f"{getpass.getuser()}@{os.uname().nodename if hasattr(os, 'uname') else 'local'}"
    return "local:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _global_state_dir() -> Path:
    base = os.getenv("XDG_STATE_HOME", "").strip()
    root = Path(base).expanduser() if base else Path.home() / ".local" / "state"
    path = root / "hoare-ai"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_rules_path() -> Path:
    return Path(__file__).resolve().parent.parent / "historical_rules.csv"


def _load_rules(root: Path | None, configured: list[str], extra: list[str]) -> list[Rule]:
    rules = load_rules(str(_default_rules_path()))
    seen = {(r.type, r.description.lower()) for r in rules}
    for item in [*configured, *extra]:
        path = Path(item).expanduser()
        if not path.is_absolute() and root is not None:
            path = root / path
        for rule in load_rules(str(path)):
            key = (rule.type, rule.description.lower())
            if key not in seen:
                seen.add(key)
                rules.append(rule)
    return rules


def _apply_validation(review, result) -> None:
    finding = validation_finding(result)
    if finding:
        review.findings.append(finding)
        review.quality_score = quality_score(review.findings)
        review.risk_level = risk_level(review.quality_score, review.findings)
    else:
        review.strengths.append(f"Local validation passed: {result.command}")


def _review_local(args: argparse.Namespace) -> int:
    root = find_repo_root(args.path)
    config = load_config(root)
    base = args.base or config.base_ref
    changes = collect_changes(
        root,
        base=base,
        compare=args.compare,
        staged=args.staged,
        unstaged=args.unstaged,
        max_files=config.max_files,
        max_file_bytes=config.max_file_bytes,
    )
    rules = _load_rules(root, config.rules_files, args.rules or [])
    state_db = root / ".hoare" / "history.db"
    store = HistoryStore(str(state_db))
    user_id = _user_id()
    patterns = store.recent_patterns(user_id)
    instructions = "\n\n".join(
        x for x in (changes.instructions, config.instructions, args.instructions or "") if x.strip()
    )
    review, graph = review_code(
        changes.files,
        user_id,
        rules,
        patterns,
        args.language or config.language,
        changes.source,
        review_instructions=instructions,
    )

    validation = None
    command = (args.test_command or "").strip()
    if args.run_tests and not command:
        command = config.test_command.strip()
    if command:
        print(f"Hoare validation: {command}", file=sys.stderr)
        validation = run_validation(command, root, args.test_timeout)
        _apply_validation(review, validation)

    store.save(review.model_dump(mode="json"))
    session_path = None
    if not args.no_save:
        session_path = save_review_session(review, graph, changes, validation)

    output_text = write_output(review, args.format, args.output)
    if args.output:
        print(render_terminal(review))
        print(f"\nExported: {Path(args.output).resolve()}")
    else:
        print(output_text)
    print(f"\nPinned: {changes.base_sha[:12]} → {changes.head_sha[:28]}")
    if session_path:
        print(f"Session: {session_path}")
    if validation:
        print(f"Validation: exit {validation.exit_code} in {validation.duration_seconds}s")

    threshold = args.fail_below if args.fail_below is not None else config.fail_below
    if validation and validation.exit_code != 0:
        return 3
    if threshold and review.quality_score < threshold:
        print(f"Hoare gate failed: {review.quality_score} < {threshold}", file=sys.stderr)
        return 2
    return 0


def _review_pr(args: argparse.Namespace) -> int:
    ctx = fetch_pr_context(args.repo, args.number)
    rules = _load_rules(None, [], args.rules or [])
    store = HistoryStore(str(_global_state_dir() / "history.db"))
    user_id = _user_id()
    review, _ = review_code(
        ctx.files,
        user_id,
        rules,
        store.recent_patterns(user_id),
        args.language,
        ctx.source,
        review_instructions=args.instructions or "",
    )
    store.save(review.model_dump(mode="json"))
    text = write_output(review, args.format, args.output)
    print(f"PR #{ctx.number}: {ctx.title}")
    print(f"Pinned: {ctx.base_sha[:12]} → {ctx.head_sha[:12]}\n")
    print(render_terminal(review) if args.output else text)
    if args.output:
        print(f"\nExported: {Path(args.output).resolve()}")
    if args.fail_below and review.quality_score < args.fail_below:
        return 2
    return 0


def _history(args: argparse.Namespace) -> int:
    root = find_repo_root(args.path)
    rows = list_sessions(root, args.limit)
    if not rows:
        print("No saved Hoare review sessions in this repository.")
        return 0
    print("DATE                     SCORE  RISK      MODE       REVIEW")
    for row in rows:
        created = str(row.get("created_at", ""))[:19].replace("T", " ")
        score = str(row.get("quality_score", "-"))
        risk = str(row.get("risk_level", "-"))
        mode = str(row.get("mode", "-"))
        rid = str(row.get("review_id", ""))[:12]
        print(f"{created:<24} {score:<6} {risk:<9} {mode:<10} {rid}")
    return 0


def _show(args: argparse.Namespace) -> int:
    root = find_repo_root(args.path)
    manifest, review, graph = load_session(root, args.review_id)
    if args.architecture:
        print(graph)
        return 0
    print(render(review, args.format))
    if args.meta:
        print("\nPinned:", manifest.get("base_sha", ""), "→", manifest.get("head_sha", ""))
    return 0


def _doctor(_: argparse.Namespace) -> int:
    status = inference_status()
    print(f"Hoare AI {VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Git: {'ok' if shutil.which('git') else 'missing'}")
    print(f"Backend: {status['backend']}")
    print(f"Model: {status['model']}")
    cfg = get_inference_config()
    if cfg.backend == "openai":
        try:
            headers = {}
            if cfg.api_key and cfg.api_key != "EMPTY":
                headers["Authorization"] = f"Bearer {cfg.api_key}"
            response = requests.get(f"{cfg.base_url}/models", headers=headers, timeout=5)
            print(f"Qwen endpoint: {'ok' if response.ok else 'HTTP ' + str(response.status_code)}")
        except Exception as exc:
            print(f"Qwen endpoint: unavailable ({exc})")
            return 1
    elif cfg.backend == "transformers":
        ref = cfg.model_path or cfg.model
        print(f"Local model: {ref}")
        if cfg.model_path and not Path(cfg.model_path).exists():
            print("Local model path: missing")
            return 1
    elif cfg.backend == "static":
        print("Model inference is disabled; only deterministic/static checks will run.")
    return 0


def _init(args: argparse.Namespace) -> int:
    root = find_repo_root(args.path)
    templates = {
        ".hoareinstructions": "Focus on correctness, security, compatibility, data flow, and regressions.\n",
        ".hoareignore": "# Generated/build artifacts\ndist/**\nbuild/**\n*.min.js\n*.lock\n",
        "hoare.toml": "[review]\nlanguage = \"Auto\"\n# base = \"origin/main\"\n# test_command = \"pytest -q\"\nmax_files = 200\nmax_file_bytes = 300000\n\n[quality]\nfail_below = 0\n\n[data]\nrules_files = []\n",
    }
    for name, content in templates.items():
        path = root / name
        if path.exists() and not args.force:
            print(f"keep {name} (already exists)")
        else:
            path.write_text(content, encoding="utf-8")
            print(f"write {name}")
    exclude = root / ".git" / "info" / "exclude"
    if exclude.exists():
        current = exclude.read_text(encoding="utf-8", errors="replace")
        if ".hoare/" not in current.splitlines():
            with exclude.open("a", encoding="utf-8") as fh:
                if current and not current.endswith("\n"):
                    fh.write("\n")
                fh.write(".hoare/\n")
            print("ignore .hoare/ locally via .git/info/exclude")
    return 0


def _serve(args: argparse.Namespace) -> int:
    app = Path(__file__).resolve().parent.parent / "app.py"
    if not app.exists():
        print("app.py was not found. Run this command from a Hoare AI source checkout.", file=sys.stderr)
        return 1
    env = os.environ.copy()
    if args.port:
        env["PORT"] = str(args.port)
    return subprocess.call([sys.executable, str(app)], env=env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hoare", description="Local-first code quality and risk review")
    parser.add_argument("--version", action="version", version=f"Hoare AI {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", help="Review local Git changes")
    review.add_argument("path", nargs="?", default=".")
    review.add_argument("--base", help="Base branch/ref (auto-detected by default)")
    review.add_argument("--compare", help="Review base...compare instead of the working tree")
    scope = review.add_mutually_exclusive_group()
    scope.add_argument("--staged", action="store_true", help="Review only staged changes")
    scope.add_argument("--unstaged", action="store_true", help="Review only unstaged and untracked changes")
    review.add_argument("--language", default=None)
    review.add_argument("--instructions", default="")
    review.add_argument("--rules", action="append", default=[], metavar="CSV")
    review.add_argument("--run-tests", action="store_true", help="Run review.test_command from hoare.toml")
    review.add_argument("--test-command", default="", help="Explicit local validation command to execute")
    review.add_argument("--test-timeout", type=int, default=180)
    review.add_argument("--format", choices=["terminal", "markdown", "json", "sarif"], default="terminal")
    review.add_argument("--output", "-o")
    review.add_argument("--fail-below", type=float, default=None, metavar="SCORE")
    review.add_argument("--no-save", action="store_true")
    review.set_defaults(func=_review_local)

    pr = sub.add_parser("pr", help="Review a GitHub pull request without checking it out")
    pr.add_argument("number", type=int)
    pr.add_argument("--repo", required=True, help="owner/repository")
    pr.add_argument("--language", default="Auto")
    pr.add_argument("--instructions", default="")
    pr.add_argument("--rules", action="append", default=[], metavar="CSV")
    pr.add_argument("--format", choices=["terminal", "markdown", "json", "sarif"], default="terminal")
    pr.add_argument("--output", "-o")
    pr.add_argument("--fail-below", type=float, default=0.0)
    pr.set_defaults(func=_review_pr)

    history = sub.add_parser("history", help="List repository review history")
    history.add_argument("path", nargs="?", default=".")
    history.add_argument("--limit", type=int, default=20)
    history.set_defaults(func=_history)

    show = sub.add_parser("show", help="Show a saved review")
    show.add_argument("review_id", nargs="?", default="latest")
    show.add_argument("--path", default=".")
    show.add_argument("--format", choices=["terminal", "markdown", "json", "sarif"], default="terminal")
    show.add_argument("--architecture", action="store_true")
    show.add_argument("--meta", action="store_true")
    show.set_defaults(func=_show)

    init = sub.add_parser("init", help="Create Hoare repository configuration")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=_init)

    doctor = sub.add_parser("doctor", help="Check local model and runtime configuration")
    doctor.set_defaults(func=_doctor)

    serve = sub.add_parser("serve", help="Launch the Hoare web dashboard")
    serve.add_argument("--port", type=int)
    serve.set_defaults(func=_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (GitError, ValueError, FileNotFoundError) as exc:
        print(f"hoare: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nhoare: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
