# Hoare AI architecture

Hoare AI is built as a local-first review engine with two surfaces: a CLI for engineers and CI, and a web dashboard for interactive review/history. Both use the same deterministic scoring, historical-rule retrieval, static analysis, and model inference code.

## Design principles

1. **The review is tied to code state.** Local reviews record a base SHA and a head SHA or dirty-worktree fingerprint. GitHub PR reviews record the PR base/head SHAs.
2. **The review unit is a logical change, not a file.** Qwen groups related changes into ordered chapters and explains the dependency/read order.
3. **Model output is evidence, not authority.** The model proposes findings; application code computes the 1–10 score deterministically.
4. **History is product data.** Structured findings, scores, categories, historical rule matches, and trends are persisted; raw source is not stored in review history.
5. **Execution is explicit.** Server-side code review never runs submitted code. The local CLI can run a test/build command only when the engineer explicitly requests it.
6. **Model serving is separate from the review service in production.** Qwen3.5-4B is best served behind vLLM/SGLang/another OpenAI-compatible endpoint; Hoare remains horizontally scalable.

## End-to-end local review

```text
Developer repository
      │
      ├─ hoare.toml
      ├─ .hoareinstructions
      └─ .hoareignore
      │
      ▼
hoare review
      │
      ├─ detect Git root/base
      ├─ collect branch/staged/unstaged changes
      ├─ pin base SHA + head/worktree fingerprint
      └─ discard ignored/binary/oversized inputs
      │
      ▼
Review context
      ├──────── static analyzers
      ├──────── historical CSV rule retrieval
      ├──────── previous-user pattern retrieval
      └──────── architecture/dependency extraction
      │
      ▼
Qwen3.5-4B
      │
      ├─ change intent
      ├─ dependency-ordered chapters
      ├─ evidence-backed findings
      ├─ architecture notes
      └─ validation plan
      │
      ▼
Deterministic quality/risk engine
      │
      ├─ optional explicit local test/build command
      ├─ terminal / Markdown / JSON / SARIF output
      ├─ .hoare/reviews/<review-id>/ session
      └─ SQLite / optional BigQuery quality memory
```

## Review session layout

Hoare deliberately does not persist raw source in the session directory.

```text
.hoare/
  history.db
  reviews/
    latest
    <review-id>/
      manifest.json       # pinned refs, score, risk, validation metadata
      review.json         # structured findings/chapters/history matches
      architecture.mmd    # generated Mermaid dependency graph
```

A manifest includes the exact `base_sha`, `head_sha` or dirty fingerprint, review mode, changed paths, model/backend identity, score, risk, and optional local-validation result.

## Core modules

| Module | Responsibility |
|---|---|
| `hoare/git_repo.py` | Git root discovery, diff scopes, commit/worktree pinning, ignore rules and safe text collection |
| `hoare/reviewer.py` | Orchestrates static checks, retrieval, Qwen review and deterministic scoring |
| `hoare/inference.py` | Qwen/OpenAI-compatible, local Transformers, Gemini fallback and static-only backends |
| `hoare/architecture.py` | Lightweight dependency graph generation |
| `hoare/rules.py` | Historical CSV parsing, deduplication and relevance retrieval |
| `hoare/history.py` | Per-user SQLite and optional BigQuery history |
| `hoare/session.py` | Repository-local immutable review session artifacts |
| `hoare/validation.py` | Explicit local test/build execution with timeout and captured result |
| `hoare/exporters.py` | Terminal, Markdown, JSON and SARIF output |
| `hoare/cli.py` | Local/CI product surface |
| `app.py` | Authenticated Gradio web dashboard |

## Git scopes

`hoare review` supports four useful code states:

- **work** (default): committed branch changes plus staged, unstaged and untracked files.
- **staged**: exactly what is currently in the Git index.
- **unstaged**: working-tree and untracked changes only.
- **compare**: an explicit `base...compare` revision comparison.

This prevents a review from silently drifting while a developer continues editing: the resulting session records the code identity it reviewed.

## GitHub PR mode

`hoare pr <number> --repo owner/repository` talks to GitHub without requiring checkout. Hoare paginates changed files, stores the exact PR base/head SHAs in the source identity, and reviews the textual patches. `GITHUB_TOKEN` enables private repository access.

## Historical learning

Historical data is not treated as model fine-tuning. It is structured retrieval and longitudinal analytics:

```text
historical rules CSV ─┐
previous findings ────┼─► relevance retrieval ─► current review prompt
previous scores ──────┘
```

The supplied assessment schema is directly supported:

```csv
id,type,description
1,formatting,Avoid single-character variable names — they hurt readability
2,performance,Cache repeated database lookups inside the request loop
3,security,Never interpolate raw user input directly into SQL queries
```

Over time, recurring issue categories/titles become context for future reviews. In GCP deployments the same structured review payloads can live in BigQuery for team-level quality trends.

## Scoring

The model never returns the final score. Hoare applies penalties to deduplicated findings:

- critical: `-2.0 × confidence`
- high: `-1.0 × confidence`
- medium: `-0.4 × confidence`
- low: `-0.15 × confidence`
- info: no penalty

A critical finding caps the final score at 5.0. Scores are clamped to 1.0–10.0. Local validation failures are converted into deterministic high-severity findings and therefore affect the same scoring system.

## Inference topology

### Recommended production

```text
CLI / Cloud Run / HF Space
          │ HTTPS
          ▼
OpenAI-compatible inference API
          │
          ▼
Qwen3.5-4B on GPU (vLLM/SGLang)
```

This keeps model weights out of every application replica and allows inference to scale independently.

### Local single-machine

Hoare can also lazy-load a downloaded Qwen model through Transformers by setting `HOARE_LLM_BACKEND=transformers` and `HOARE_QWEN_MODEL_PATH`.

## GCP topology

```text
Users / CI
    │
    ▼
Cloud Run + IAP
    │
    ├────────► GPU Qwen endpoint
    │
    ├────────► BigQuery review memory
    │
    └────────► GitHub API (optional)
```

Cloud Run contains the lightweight review/API layer only. BigQuery stores structured quality history. Secrets belong in Secret Manager/environment bindings, not source or review records.

## Security boundaries

- Code, comments, diffs and historical text are untrusted model data.
- Secret-looking values are redacted before model inference.
- Raw source is not written to review history/session artifacts.
- The web service never executes submitted code.
- Local validation is opt-in and runs in the caller's repository/process environment; it is intentionally not automatic.
- Upload/file limits prevent unbounded context ingestion.
- HF OAuth or Cloud Run IAP separates user histories in hosted deployments.
- Model endpoint credentials are environment secrets.

## Scale behavior

For large changes, Hoare caps file count/file size before inference and caps prompt serialization. Production evolution should add semantic chunking for repository-scale changes and queue-based asynchronous processing for very large PRs. The current architecture already separates inference, application replicas and persistent analytics so these additions do not require changing the review data model.
