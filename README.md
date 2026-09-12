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

Hoare AI is an always-on, multi-language code quality reviewer for engineering teams shipping human- and AI-generated code. It combines change comprehension, architecture-aware review, validation planning, deterministic quality scoring, and historical quality memory.

The default open model is **Qwen/Qwen3.5-4B**. Production deployments should serve Qwen through vLLM/SGLang/Transformers Serve and let Hoare AI call the OpenAI-compatible endpoint. A direct Transformers backend is also included for a model already downloaded on the same machine.

## What Hoare AI does

- Reviews pasted code, uploaded source files, and GitHub PR diffs.
- Detects security, correctness, performance, reliability, maintainability, architecture, readability, and testing risks.
- Groups changes into logical **review chapters** rather than reviewing files in isolation.
- Builds a lightweight dependency/architecture map.
- Generates focused validation scenarios without executing untrusted submissions.
- Produces a deterministic **1–10 quality score** from evidence-backed findings.
- Imports historical CSV rules using `id,type,description` and retrieves only relevant rules for each review.
- Stores structured review history so recurring engineering patterns influence future reviews.
- Redacts secret-like values before model analysis and does not persist raw source by default.

## Architecture

```text
HF OAuth / Cloud Run IAP
          │
          ▼
     Hoare AI UI/API
          │
 ┌────────┼──────────┐
 ▼        ▼          ▼
Code   GitHub PR   CSV rules
 └────────┼──────────┘
          ▼
 Safe ingestion + static analysis
          │
          ├────────► historical rule / review retrieval
          │
          ▼
 Qwen3.5-4B inference layer
 (vLLM/SGLang API or local Transformers)
          │
          ▼
 Structured findings + chapters + architecture + validation
          │
          ▼
 Deterministic risk / 1–10 quality scoring
          │
     ┌────┴─────┐
     ▼          ▼
  SQLite     BigQuery
     └── quality memory ──► future reviews
```

## Recommended production inference

Qwen3.5 is designed to be served through OpenAI-compatible APIs. For production/high-throughput review, run the downloaded model with vLLM and keep Hoare AI as a stateless review/API layer.

```bash
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
bash deploy/start-qwen-local.sh
```

In another shell:

```bash
export HOARE_LLM_BACKEND=openai
export HOARE_LLM_MODEL=Qwen/Qwen3.5-4B
export HOARE_LLM_BASE_URL=http://127.0.0.1:8000/v1
export HOARE_LLM_API_KEY=EMPTY
export HOARE_ALLOW_ANONYMOUS=true
python app.py
```

Or run both containers:

```bash
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
docker compose -f docker-compose.qwen.yml up --build
```

## Direct local model mode

If you do not want a model server, Hoare AI can lazy-load the downloaded model in-process:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-local.txt
export HOARE_LLM_BACKEND=transformers
export HOARE_QWEN_MODEL_PATH=/absolute/path/to/Qwen3.5-4B
export HOARE_LLM_MODEL=Qwen/Qwen3.5-4B
export HOARE_ALLOW_ANONYMOUS=true
python app.py
```

The direct backend uses non-thinking/instruct generation for predictable structured code-review output. For production concurrency, prefer vLLM/SGLang instead of loading one model inside each web worker.

## Hugging Face Space

The Space can run in two modes:

1. **Recommended:** set `HOARE_LLM_BASE_URL` as a Space Secret/Variable pointing to a Qwen3.5-4B inference service.
2. **Single-Space demo:** let the Space load `Qwen/Qwen3.5-4B` directly from the Hub. The app auto-detects Spaces; GPU hardware is strongly recommended.

Keep `hf_oauth: true` so every review history is tied to the authenticated HF user.

## GCP deployment

Deploy the Hoare UI/API on **Cloud Run**, protect it with IAP, and persist quality memory in **BigQuery**.

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/hoare/hoare-ai
gcloud run deploy hoare-ai \
  --image REGION-docker.pkg.dev/PROJECT/hoare/hoare-ai \
  --region REGION \
  --set-env-vars HOARE_LLM_BACKEND=openai,HOARE_LLM_MODEL=Qwen/Qwen3.5-4B,HOARE_LLM_BASE_URL=https://YOUR-QWEN-ENDPOINT/v1,HOARE_BIGQUERY_TABLE=PROJECT.hoare.reviews
```

For a production Qwen endpoint, use a dedicated GPU service. Hoare AI itself remains stateless and horizontally scalable on Cloud Run.

## Historical data

```csv
id,type,description
1,formatting,Avoid single-character variable names — they hurt readability
2,performance,Cache repeated database lookups inside the request loop
3,security,Never interpolate raw user input directly into SQL queries
```

Hoare AI parses, de-duplicates, ranks, and retrieves relevant historical rules rather than placing the entire dataset into every prompt.

## Quality score

The model never chooses the final score. Application code computes it consistently:

- Critical: -2.0 × confidence
- High: -1.0 × confidence
- Medium: -0.4 × confidence
- Low: -0.15 × confidence
- Info: no penalty

Any critical finding caps the score at 5.0. Scores are clamped to 1.0–10.0.

## Security boundaries

1. Code, diffs, comments, file names, and historical descriptions are **untrusted data** and cannot override reviewer instructions.
2. Secret-like values are redacted before LLM inference.
3. Submitted code is analyzed, never executed by the reviewer process.
4. Upload types and sizes are bounded.
5. Raw source is not stored in review history by default.
6. HF OAuth / Cloud Run IAP separates user histories.
7. Model endpoint keys are read from environment secrets and are never returned to the UI.

## Inference configuration

| Variable | Purpose |
|---|---|
| `HOARE_LLM_BACKEND` | `auto`, `openai`, `transformers`, `gemini`, or `static` |
| `HOARE_LLM_MODEL` | Defaults to `Qwen/Qwen3.5-4B` |
| `HOARE_LLM_BASE_URL` | OpenAI-compatible Qwen endpoint, e.g. `http://localhost:8000/v1` |
| `HOARE_LLM_API_KEY` | Endpoint token; `EMPTY` for local vLLM |
| `HOARE_QWEN_MODEL_PATH` | Local downloaded model directory |
| `HOARE_LOAD_MODEL_FROM_HUB` | Allow direct model download from Hugging Face |
| `HOARE_BIGQUERY_TABLE` | `project.dataset.table` for persistent quality history |

## Why “Hoare”?

The name nods to Tony Hoare and the idea that software quality should be reasoned about rather than guessed. Hoare AI is a quality and trust layer for an era where producing code is becoming cheap but validating it remains expensive.
