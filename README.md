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

Hoare AI is a multi-language, always-on code quality reviewer built for engineering teams shipping growing volumes of human- and AI-generated code. It combines three modern review ideas:

- **Change chapters:** related files are grouped by intent so reviewers understand a change rather than reading files in arbitrary order.
- **Architecture-aware review:** Hoare AI extracts lightweight dependency context and asks Gemini to reason about architectural impact.
- **Validation planning:** it identifies affected flows and proposes focused checks without executing untrusted code.
- **Quality memory:** every review becomes structured data. Historical review rules and recurring user patterns are retrieved into future reviews.

The differentiator is the last layer: **not only “what is wrong with this PR?” but “what has this team repeatedly gotten wrong, and is this change repeating the pattern?”**

## Features

- Multi-language code and diff review
- GitHub PR diff ingestion
- Security, correctness, performance, reliability, architecture and maintainability findings
- Deterministic **1–10 quality score** (the LLM does not choose its own score)
- Logical change chapters
- Architecture dependency map
- Validation plan
- Historical CSV ingestion: `id,type,description`
- Per-user review history and recurring issue patterns
- Hugging Face OAuth authentication
- Cloud Run / IAP compatible user identity
- Secret redaction before Gemini analysis
- Raw source code is not persisted in review history
- Optional BigQuery-backed persistent quality memory

## Architecture

```text
Hugging Face OAuth / Cloud Run IAP
                 │
                 ▼
           Gradio UI / API
                 │
      ┌──────────┼───────────┐
      │          │           │
      ▼          ▼           ▼
  Paste/files  GitHub PR   Historical CSV
      │          │           │
      └──────┬───┴───────┬───┘
             ▼           ▼
      Safe ingestion   Rule retrieval
             │           │
             ├──────┬────┘
             ▼      ▼
      Static checks + Gemini
             │
             ▼
       Structured findings
             │
       Deterministic scoring
             │
      ┌──────┴───────────┐
      ▼                  ▼
 SQLite fallback     BigQuery (GCP)
      │                  │
      └──── quality memory ────► future reviews
```

## GCP stack

- **Gemini (`google-genai`)**: code understanding, change intent, architectural reasoning, evidence-backed findings, and validation planning. Defaults to `gemini-3.8-flash` and supports Gemini on Google Cloud through `GOOGLE_GENAI_USE_ENTERPRISE=true`.
- **BigQuery**: persistent review intelligence — review IDs, quality scores, risk levels, finding payloads and longitudinal quality trends. Set `HOARE_BIGQUERY_TABLE=project.dataset.table`.
- **Cloud Run**: stateless scalable application deployment from the included Dockerfile. Put Cloud Run behind **Identity-Aware Proxy (IAP)** for authenticated access.

For the lightweight Hugging Face demo, SQLite is used as a fallback history store.

## Historical data

```csv
id,type,description
1,formatting,Avoid single-character variable names — they hurt readability
2,performance,Cache repeated database lookups inside the request loop
3,security,Never interpolate raw user input directly into SQL queries
```

Hoare AI parses, de-duplicates and retrieves the most relevant historical rules for each submission instead of dumping the entire dataset into every prompt.

## Quality scoring

The score is deterministic and computed in application code:

- Critical: -2.0 × confidence
- High: -1.0 × confidence
- Medium: -0.4 × confidence
- Low: -0.15 × confidence
- Info: no penalty

Any critical finding caps the score at 5.0. Final scores are clamped to 1.0–10.0.

## Security model

1. Source, comments and diffs are treated as **untrusted data**; prompt instructions inside submitted code are ignored.
2. Secret-like values are redacted before Gemini sees the submission.
3. Hoare AI **never executes submitted code**.
4. Upload size and extensions are bounded.
5. Only the source hash and structured review are stored by default; raw code is not persisted.
6. Users are separated by HF OAuth identity or Cloud Run IAP identity.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY='...'
export HOARE_ALLOW_ANONYMOUS=true
python app.py
```

## Deploy to Cloud Run

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/hoare/hoare-ai
gcloud run deploy hoare-ai \
  --image REGION-docker.pkg.dev/PROJECT/hoare/hoare-ai \
  --region REGION \
  --set-env-vars GOOGLE_GENAI_USE_ENTERPRISE=true,GOOGLE_CLOUD_PROJECT=PROJECT,GOOGLE_CLOUD_LOCATION=us-central1,HOARE_BIGQUERY_TABLE=PROJECT.hoare.reviews
```

Grant the Cloud Run service account permission to use Gemini and BigQuery, then protect the service with IAP.

## Hugging Face Space

This repository is ready to mirror to a Gradio Space. Keep `hf_oauth: true` in this README and add `GEMINI_API_KEY` as a **Space Secret** (or configure Google Cloud credentials if using Gemini on Google Cloud).

## Why “Hoare”?

The name nods to Tony Hoare and the idea that software quality should be reasoned about, not guessed. Hoare AI is designed as a **quality and trust layer** for an era where producing code is becoming cheap but validating it remains expensive.
