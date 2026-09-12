---
title: Hoare AI
emoji: 🛡️
colorFrom: indigo
colorTo: purple
sdk: gradio
python_version: 3.12
app_file: app.py
pinned: false
hf_oauth: true
hf_oauth_expiration_minutes: 480
---

# Hoare AI — engineering quality intelligence

**AI writes code. Hoare AI decides what deserves to be trusted.**

Hoare AI is a local-first, multi-language code review and quality-memory system for engineering teams shipping human- and AI-generated code. The primary workflow is the **`hoare` CLI**; the Gradio application is a companion web dashboard for interactive submissions, history and hosted demos.

The default open model is **Qwen/Qwen3.5-4B**. Production deployments should serve Qwen behind a vLLM/SGLang/OpenAI-compatible endpoint so model inference scales separately from Hoare's review/API layer. A direct Transformers backend is included for a model already downloaded on the same machine.

## Why Hoare is different

Most reviewers answer one question: **“What is wrong with this PR?”**

Hoare adds two more:

- **“What code state did we actually review?”** Every local session is pinned to a base SHA and a head SHA or dirty-worktree fingerprint.
- **“Is this team repeating something that failed before?”** Historical rules and recurring findings are retrieved into future reviews, while scores and issue patterns become longitudinal quality data.

The resulting review is not a disposable chat response. It is a structured quality record containing findings, logical review chapters, architecture context, validation guidance, model identity, risk and a deterministic 1–10 score.

## Local quickstart

```bash
git clone https://github.com/Aravindh-dev12/hoare-ai.git
cd hoare-ai
python -m venv .venv
source .venv/bin/activate
pip install -e .

hoare --version
hoare doctor
```

Point Hoare at your downloaded Qwen model using the recommended vLLM topology:

```bash
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
bash deploy/start-qwen-local.sh
```

In another terminal:

```bash
export HOARE_LLM_BACKEND=openai
export HOARE_LLM_MODEL=Qwen/Qwen3.5-4B
export HOARE_LLM_BASE_URL=http://127.0.0.1:8000/v1
export HOARE_LLM_API_KEY=EMPTY

cd /path/to/your/project
hoare init
hoare review
```

Useful scopes:

```bash
hoare review --staged
hoare review --unstaged
hoare review --base origin/main --compare HEAD
hoare review --instructions 'Focus on backward compatibility and auth boundaries.'
```

Explicitly validate behavior after review:

```bash
hoare review --test-command 'pytest -q'
```

Hoare **does not execute repository code by default**. A test/build command runs only when the engineer explicitly requests it with `--test-command` or `--run-tests`.

## CLI product surface

```text
hoare init                         repository config / ignore / guidance
hoare review                       review local Git changes
hoare review --staged              review the Git index only
hoare review --unstaged            review worktree + untracked changes
hoare review --base A --compare B  review two pinned revisions
hoare pr 42 --repo owner/repo      review a GitHub PR without checkout
hoare history                      list local quality sessions
hoare show latest                  inspect the latest saved review
hoare show latest --architecture   print the Mermaid dependency graph
hoare doctor                       verify model/runtime configuration
hoare serve                        launch the companion web dashboard
```

Outputs are available as terminal text, Markdown, JSON or SARIF:

```bash
hoare review --format markdown -o review.md
hoare review --format json -o review.json
hoare review --format sarif -o hoare.sarif
hoare review --fail-below 7.5
```

See [`docs/CLI.md`](docs/CLI.md) for the full command reference.

## What a review produces

- Security, correctness, performance, reliability, maintainability, architecture, readability and testing findings.
- Logical **review chapters** ordered as a human should read the dependency chain.
- Change intent and architecture/data-flow notes.
- A Mermaid dependency map.
- A focused validation plan.
- Relevant matches from historical review rules.
- A deterministic **1–10 quality score**.
- A pinned review session under `.hoare/reviews/<review-id>/`.
- Optional explicit local test/build evidence.
- SQLite history locally and optional BigQuery history in GCP.

Raw source code is not written into review history/session artifacts.

## Architecture

```text
                     ┌───────────────────────────┐
                     │       Developer / CI      │
                     └─────────────┬─────────────┘
                                   │
                     ┌─────────────▼─────────────┐
                     │        hoare CLI          │
                     │ Git / PR / config / gate  │
                     └─────────────┬─────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
            ▼                      ▼                      ▼
     Git change capture       Historical rules       Previous reviews
 base/head/worktree pinning     CSV retrieval        recurring patterns
            │                      │                      │
            └──────────────┬───────┴──────────────┬───────┘
                           ▼                      ▼
                    Static analysis       Architecture context
                           │                      │
                           └──────────┬───────────┘
                                      ▼
                              Qwen3.5-4B
                         vLLM API / Transformers
                                      │
                         ┌────────────┼─────────────┐
                         ▼            ▼             ▼
                      Findings     Chapters     Validation plan
                         └────────────┼─────────────┘
                                      ▼
                           Deterministic score/risk
                                      │
                       ┌──────────────┼──────────────┐
                       ▼              ▼              ▼
                  .hoare session    SQLite        BigQuery
                                      │
                                      └──── quality memory ───► next review
```

Detailed component/data/security architecture is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Design references

Hoare uses public product ideas from modern AI-era review tools as architecture references while implementing its own review engine and data model:

- **Stage** — local-first review and logical “chapters” instead of forcing humans through an arbitrary file order: <https://github.com/ReviewStage/stage-cli>
- **Alchemize** — dependency-ordered review context and validation of affected workflows: <https://tryalchemize.com/>
- **/dev/fast Review** — architecture-level understanding and reviews tied to exact code/version-control state: <https://github.com/devdotfast/review>

Hoare's differentiating layer is **quality memory**: it combines the current code state with historical engineering rules and recurring review patterns, then stores the resulting structured quality record for future reviews.

## Repository configuration

Run:

```bash
hoare init
```

Hoare creates three optional files:

```text
.hoareinstructions   persistent project review guidance
.hoareignore         generated/vendor files excluded from analysis
hoare.toml           base ref, limits, validation command, score gate, extra rule CSVs
```

Example:

```toml
[review]
base = "origin/main"
language = "Auto"
test_command = "pytest -q"
max_files = 200
max_file_bytes = 300000

[quality]
fail_below = 7.5

[data]
rules_files = ["engineering-rules.csv"]
```

A configured test command is not run automatically; invoke `hoare review --run-tests` to explicitly execute it.

## Historical data

The assessment CSV schema is supported directly:

```csv
id,type,description
1,formatting,Avoid single-character variable names — they hurt readability
2,performance,Cache repeated database lookups inside the request loop
3,security,Never interpolate raw user input directly into SQL queries
```

Hoare parses, de-duplicates and retrieves relevant rules instead of placing the entire dataset in every model prompt. Previous structured findings are also summarized into recurring user/team patterns.

## Quality scoring

Qwen does **not** choose the final numeric score. Application code computes it from deduplicated findings:

- Critical: `-2.0 × confidence`
- High: `-1.0 × confidence`
- Medium: `-0.4 × confidence`
- Low: `-0.15 × confidence`
- Info: no penalty

Any critical finding caps the score at 5.0. Scores are clamped to 1.0–10.0. Explicit local test/build failures become high-severity findings and flow through the same scoring model.

## Qwen production inference

Recommended topology:

```text
Hoare CLI / Web / Cloud Run
            │
            │ OpenAI-compatible HTTP
            ▼
       vLLM / SGLang
            │
            ▼
       Qwen3.5-4B GPU
```

Start the downloaded model locally:

```bash
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
bash deploy/start-qwen-local.sh
```

Or start Qwen + Hoare together:

```bash
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
docker compose -f docker-compose.qwen.yml up --build
```

### Direct model mode

For a single-machine development environment:

```bash
pip install -e '.[local-model]'
export HOARE_LLM_BACKEND=transformers
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
hoare review
```

For concurrency, prefer a separate model server rather than loading one 4B model into every web worker.

## Web dashboard / Hugging Face Space

The existing Gradio app remains available:

```bash
hoare serve
# or
python app.py
```

On Hugging Face, keep `hf_oauth: true` so hosted histories can be associated with authenticated users. For production, point the Space at a dedicated Qwen inference endpoint instead of forcing a CPU Space to host the 4B weights itself.

## GCP deployment

A production GCP topology uses:

- **Cloud Run** for the stateless Hoare UI/API.
- **IAP** for authenticated access.
- **BigQuery** for persistent quality history and longitudinal analytics.
- A separate GPU inference endpoint for Qwen3.5-4B.

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/hoare/hoare-ai

gcloud run deploy hoare-ai \
  --image REGION-docker.pkg.dev/PROJECT/hoare/hoare-ai \
  --region REGION \
  --set-env-vars HOARE_LLM_BACKEND=openai,HOARE_LLM_MODEL=Qwen/Qwen3.5-4B,HOARE_LLM_BASE_URL=https://YOUR-QWEN-ENDPOINT/v1,HOARE_BIGQUERY_TABLE=PROJECT.hoare.reviews
```

## Security boundaries

1. Code, diffs, comments, file names and historical descriptions are untrusted model data.
2. Secret-like values are redacted before model inference.
3. The hosted reviewer does not execute submitted code.
4. Local validation requires explicit engineer opt-in.
5. File count/size and model-context ingestion are bounded.
6. Raw source is not persisted in review history by default.
7. HF OAuth / Cloud Run IAP separates hosted user histories.
8. Model and GitHub credentials come from environment secrets and are never returned to the UI.

## Inference configuration

| Variable | Purpose |
|---|---|
| `HOARE_LLM_BACKEND` | `auto`, `openai`, `transformers`, `gemini`, or `static` |
| `HOARE_LLM_MODEL` | Defaults to `Qwen/Qwen3.5-4B` |
| `HOARE_LLM_BASE_URL` | OpenAI-compatible endpoint, e.g. `http://localhost:8000/v1` |
| `HOARE_LLM_API_KEY` | Endpoint token; `EMPTY` for local vLLM |
| `HOARE_QWEN_MODEL_PATH` | Local downloaded model directory |
| `HOARE_LOAD_MODEL_FROM_HUB` | Allow direct model download from Hugging Face |
| `HOARE_BIGQUERY_TABLE` | `project.dataset.table` for persistent hosted quality history |
| `HOARE_USER_ID` | Optional stable local/CI user identifier |

## Why “Hoare”?

The name nods to Tony Hoare and the idea that software quality should be reasoned about rather than guessed. Hoare AI is designed as a quality and trust layer for an era where producing code is becoming cheap while validation and engineering judgment remain expensive.
