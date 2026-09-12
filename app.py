from __future__ import annotations

import json
import os
from pathlib import Path

import gradio as gr
import pandas as pd

from hoare.github_source import fetch_pr_files
from hoare.history import HistoryStore
from hoare.reviewer import review_code
from hoare.rules import Rule, load_rules, parse_rules_csv
from hoare.security import read_uploaded_files

store = HistoryStore()
BASE_RULES = load_rules()
IS_HF_SPACE = bool(os.getenv('SPACE_ID') or os.getenv('OAUTH_CLIENT_ID'))

CSS = '''
:root { --hoare-border: rgba(120,120,120,.22); }
.hoare-hero {padding: 22px 24px; border: 1px solid var(--hoare-border); border-radius: 18px; margin-bottom: 12px;}
.hoare-kicker {font-size: .78rem; letter-spacing: .16em; text-transform: uppercase; opacity: .65;}
.hoare-title {font-size: 2.1rem; font-weight: 760; margin: .25rem 0;}
.hoare-sub {font-size: 1rem; opacity: .78; max-width: 900px;}
.score-card {padding: 14px 18px; border: 1px solid var(--hoare-border); border-radius: 14px;}
'''


def _user_id(profile, request: gr.Request | None) -> str:
    if profile and getattr(profile, 'username', None):
        return f'hf:{profile.username}'
    if request:
        headers = getattr(request, 'headers', {}) or {}
        iap_user = headers.get('x-goog-authenticated-user-email') or headers.get('X-Goog-Authenticated-User-Email')
        if iap_user:
            return str(iap_user)
    if os.getenv('HOARE_ALLOW_ANONYMOUS', 'false').lower() in {'1', 'true', 'yes'}:
        return 'demo:anonymous'
    raise gr.Error('Sign in first. On Hugging Face use the Login button; on Cloud Run place the service behind IAP.')


def _collect_files(code: str, uploaded, repo: str, pr_number: float | int | None) -> tuple[dict[str, str], str]:
    files: dict[str, str] = {}
    source = []
    if code and code.strip():
        files['pasted_code.txt'] = code.strip()
        source.append('paste')
    paths = []
    if uploaded:
        for item in uploaded:
            paths.append(item if isinstance(item, str) else getattr(item, 'name', str(item)))
    upload_files = read_uploaded_files(paths)
    files.update(upload_files)
    if upload_files:
        source.append('upload')
    if repo and repo.strip() and pr_number:
        pr_files = fetch_pr_files(repo.strip(), int(pr_number))
        files.update(pr_files)
        source.append(f'github:{repo.strip()}#{int(pr_number)}')
    return files, '+'.join(source) or 'unknown'


def _rules_from_state(state) -> list[Rule]:
    custom = []
    for item in (state or []):
        try:
            custom.append(Rule(**item))
        except Exception:
            continue
    return BASE_RULES + custom


def _run_review_for_user(code, language, uploaded, repo, pr_number, rules_state, user_id: str):
    files, source = _collect_files(code, uploaded, repo, pr_number)
    patterns = store.recent_patterns(user_id)
    review, graph = review_code(files, user_id, _rules_from_state(rules_state), patterns, language, source)
    store.save(review.model_dump())

    score_md = f'''<div class="score-card"><b>Quality score</b><br><span style="font-size:2rem;font-weight:750">{review.quality_score}/10</span><br><b>Risk:</b> {review.risk_level} · {review.language} · {review.file_count} file(s)</div>'''
    summary_md = f'### Review summary\n{review.summary}\n\n**Change intent:** {review.change_intent or "Not confidently inferred."}'

    findings = pd.DataFrame([
        {
            'Severity': f.severity.upper(), 'Category': f.category, 'Finding': f.title,
            'File': f.file, 'Line': f.line or '', 'Evidence': f.evidence,
            'Recommendation': f.recommendation, 'Historical rule': f.historical_rule_id or '',
            'Confidence': round(f.confidence, 2),
        } for f in review.findings
    ])
    if findings.empty:
        findings = pd.DataFrame(columns=['Severity','Category','Finding','File','Line','Evidence','Recommendation','Historical rule','Confidence'])

    chapters_md = '\n\n'.join(
        f'#### {c.name} · {c.risk.upper()} risk\n{c.purpose}\n\nFiles: ' + ', '.join(f'`{x}`' for x in c.files)
        for c in review.chapters
    ) or 'No chapters generated.'

    architecture_md = '### Architecture notes\n' + ('\n'.join(f'- {x}' for x in review.architecture_notes) or '- No architecture concerns identified.')
    architecture_md += '\n\n### Dependency map\n```mermaid\n' + graph + '\n```'

    validation_md = '\n\n'.join(
        f'**{i+1}. {v.scenario}**  \nWhy: {v.why}  \nCheck: {v.suggested_check}'
        for i, v in enumerate(review.validation_plan)
    )
    rules_df = pd.DataFrame(review.matched_rules)
    strengths_md = '\n'.join(f'- {x}' for x in review.strengths) or '- No explicit strengths returned.'
    return score_md, summary_md, findings, chapters_md, architecture_md, validation_md, rules_df, strengths_md


def _history_for_user(user_id: str):
    rows = store.recent(user_id, 40)
    data = pd.DataFrame([
        {
            'Time': r['created_at'], 'Score': r['quality_score'], 'Risk': r['risk_level'],
            'Language': r['language'], 'Summary': r['summary'][:120], 'Review ID': r['review_id'][:8]
        } for r in rows
    ])
    if data.empty:
        data = pd.DataFrame(columns=['Time','Score','Risk','Language','Summary','Review ID'])
    trend = data[['Time','Score']].copy() if not data.empty else pd.DataFrame({'Time': [], 'Score': []})
    return data, trend


if IS_HF_SPACE:
    def run_review_handler(code, language, uploaded, repo, pr_number, rules_state, profile: gr.OAuthProfile, request: gr.Request):
        return _run_review_for_user(code, language, uploaded, repo, pr_number, rules_state, _user_id(profile, request))

    def refresh_history_handler(profile: gr.OAuthProfile, request: gr.Request):
        return _history_for_user(_user_id(profile, request))
else:
    def run_review_handler(code, language, uploaded, repo, pr_number, rules_state, request: gr.Request):
        return _run_review_for_user(code, language, uploaded, repo, pr_number, rules_state, _user_id(None, request))

    def refresh_history_handler(request: gr.Request):
        return _history_for_user(_user_id(None, request))


def import_rules(file_path, text):
    raw = text or ''
    if file_path:
        path = file_path if isinstance(file_path, str) else getattr(file_path, 'name', str(file_path))
        raw = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    if not raw.strip():
        raise gr.Error('Upload a CSV or paste CSV text first.')
    parsed = parse_rules_csv(raw)
    state = [r.__dict__ for r in parsed]
    preview = pd.DataFrame(state)
    return state, f'Loaded {len(parsed)} custom historical rules for this session.', preview


with gr.Blocks(title='Hoare AI') as demo:
    rules_state = gr.State([])
    gr.HTML('''<div class="hoare-hero"><div class="hoare-kicker">Engineering quality intelligence</div><div class="hoare-title">Hoare AI</div><div class="hoare-sub">AI writes code. Hoare AI decides what deserves to be trusted — using change-aware review, architecture context, validation planning, deterministic quality scoring, and historical engineering memory.</div></div>''')
    with gr.Row():
        if IS_HF_SPACE:
            gr.LoginButton(value='Sign in with Hugging Face')
        else:
            gr.Markdown('**Identity:** Cloud Run IAP is supported; set `HOARE_ALLOW_ANONYMOUS=true` only for local demos.')
        gr.Markdown('**Privacy:** submitted code is analyzed, but raw source is not stored in review history. Secret-like values are redacted before Gemini analysis.')

    with gr.Tabs():
        with gr.Tab('Review'):
            with gr.Row():
                with gr.Column(scale=3):
                    code = gr.Code(label='Paste code / diff', language=None, lines=20)
                    uploaded = gr.File(label='Or upload source files', file_count='multiple', type='filepath')
                    language = gr.Dropdown(['Auto','Python','JavaScript','TypeScript','Java','Go','Rust','C','C++','C#','Ruby','PHP','Kotlin','Swift','SQL'], value='Auto', label='Primary language')
                with gr.Column(scale=2):
                    gr.Markdown('### GitHub PR (optional)\nLoad a public PR diff, or set `GITHUB_TOKEN` for private repositories.')
                    repo = gr.Textbox(label='Repository', placeholder='owner/repository')
                    pr_number = gr.Number(label='PR number', precision=0)
                    run = gr.Button('Run Hoare Review', variant='primary')
                    score = gr.HTML()
                    summary = gr.Markdown()

            with gr.Tab('Findings'):
                findings = gr.Dataframe(label='Evidence-backed findings', interactive=False, wrap=True)
                strengths = gr.Markdown(label='Strengths')
            with gr.Tab('Change chapters'):
                chapters = gr.Markdown()
            with gr.Tab('Architecture'):
                architecture = gr.Markdown()
            with gr.Tab('Validation plan'):
                validation = gr.Markdown()
            with gr.Tab('Historical matches'):
                matched_rules = gr.Dataframe(interactive=False, wrap=True)

            run.click(
                run_review_handler,
                inputs=[code, language, uploaded, repo, pr_number, rules_state],
                outputs=[score, summary, findings, chapters, architecture, validation, matched_rules, strengths],
                api_name='review',
            )

        with gr.Tab('Quality history'):
            gr.Markdown('Every review becomes a quality data point. Hoare AI stores scores and findings, not raw source code.')
            refresh = gr.Button('Refresh my history')
            history_table = gr.Dataframe(interactive=False, wrap=True)
            trend = gr.LinePlot(x='Time', y='Score', y_lim=[1,10], title='Code quality trend')
            refresh.click(refresh_history_handler, outputs=[history_table, trend], api_name='history')

        with gr.Tab('Historical rules'):
            gr.Markdown('Import the assessment CSV schema: `id,type,description`. Rules are retrieved only when relevant to the current review.')
            rules_file = gr.File(label='Historical rules CSV', file_types=['.csv'], type='filepath')
            rules_text = gr.Textbox(label='Or paste CSV', lines=8, value='id,type,description\n1,formatting,Avoid single-character variable names — they hurt readability\n2,performance,Cache repeated database lookups inside the request loop\n3,security,Never interpolate raw user input directly into SQL queries')
            load = gr.Button('Load historical rules')
            status = gr.Markdown()
            rules_preview = gr.Dataframe(interactive=False)
            load.click(import_rules, inputs=[rules_file, rules_text], outputs=[rules_state, status, rules_preview], api_name='rules')

    gr.Markdown('---\n**Hoare AI does not execute submitted code.** Runtime/browser validation should happen in an isolated sandbox or CI environment; this prototype generates the validation plan and risk model safely.')


if __name__ == '__main__':
    port = int(os.getenv('PORT', '7860'))
    demo.queue(default_concurrency_limit=int(os.getenv('HOARE_CONCURRENCY', '4'))).launch(server_name='0.0.0.0', server_port=port, theme=gr.themes.Soft(), css=CSS, max_file_size='2mb')
