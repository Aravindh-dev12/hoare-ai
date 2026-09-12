# Hoare AI CLI

The CLI is the primary local developer workflow. The web app is a companion dashboard.

## Install

From the repository:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
hoare --version
```

For direct in-process Qwen loading:

```bash
pip install -e '.[local-model]'
```

## Configure Qwen

Recommended local/production layout: serve the downloaded model with vLLM and point Hoare at its OpenAI-compatible API.

```bash
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
bash deploy/start-qwen-local.sh

export HOARE_LLM_BACKEND=openai
export HOARE_LLM_MODEL=Qwen/Qwen3.5-4B
export HOARE_LLM_BASE_URL=http://127.0.0.1:8000/v1
export HOARE_LLM_API_KEY=EMPTY

hoare doctor
```

Direct Transformers mode:

```bash
export HOARE_LLM_BACKEND=transformers
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
hoare doctor
```

## Initialize a repository

```bash
cd your-repository
hoare init
```

This creates:

- `.hoareinstructions` — persistent project-specific review guidance.
- `.hoareignore` — generated/vendor paths to exclude from model analysis.
- `hoare.toml` — base ref, limits, optional validation command and score gate.

Runtime review data is stored in `.hoare/` and is locally ignored through `.git/info/exclude`.

## Review your current branch/worktree

```bash
hoare review
```

Default scope includes committed branch changes against the detected main branch plus current staged, unstaged and untracked changes.

Review only staged changes:

```bash
hoare review --staged
```

Review only unstaged/untracked changes:

```bash
hoare review --unstaged
```

Review two pinned refs:

```bash
hoare review --base origin/main --compare HEAD
```

Add one-off reviewer guidance:

```bash
hoare review --instructions 'Focus on backward compatibility and auth boundaries.'
```

## Validate behavior locally

Hoare never executes code by default. To explicitly run a test/build command after review:

```bash
hoare review --test-command 'pytest -q'
```

Or configure a command in `hoare.toml` and explicitly opt into it:

```toml
[review]
test_command = "pytest -q"
```

```bash
hoare review --run-tests
```

A failed/timed-out validation becomes a high-severity finding and changes the deterministic quality score.

## Quality gates

Fail the command when the score is below a threshold:

```bash
hoare review --fail-below 7.5
```

Or persist the gate:

```toml
[quality]
fail_below = 7.5
```

Exit codes:

- `0` review/gate passed
- `1` configuration/Git/input error
- `2` quality threshold failed
- `3` explicit validation command failed
- `130` interrupted

## Output formats

Human terminal output:

```bash
hoare review
```

Markdown report:

```bash
hoare review --format markdown -o hoare-review.md
```

Structured JSON:

```bash
hoare review --format json -o hoare-review.json
```

SARIF for CI/code-scanning integrations:

```bash
hoare review --format sarif -o hoare.sarif
```

## GitHub pull requests

Review a PR without checking out its branch:

```bash
export GITHUB_TOKEN=...
hoare pr 42 --repo owner/repository
```

The review source includes the exact base and head commit SHAs returned by GitHub.

## History

```bash
hoare history
hoare show latest
hoare show <review-id> --meta
hoare show <review-id> --architecture
```

Local sessions live in `.hoare/reviews/` and contain structured results and metadata, not raw source.

## Web dashboard

From a source checkout:

```bash
hoare serve
```

or:

```bash
python app.py
```

Both the CLI and web app use the same reviewer, scoring, history, historical-rule and inference modules.
