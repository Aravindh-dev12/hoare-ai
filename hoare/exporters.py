from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ReviewResult


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "finding"


def render_terminal(review: ReviewResult) -> str:
    lines = [
        f"Hoare AI · {review.quality_score}/10 · {review.risk_level}",
        f"{review.language} · {review.file_count} file(s) · {review.model_backend}:{review.model_name}",
        "",
        review.summary,
        "",
        f"Intent: {review.change_intent or 'Unknown'}",
    ]
    if review.findings:
        lines += ["", "Findings"]
        for index, finding in enumerate(review.findings, 1):
            where = finding.file or "submission"
            if finding.line:
                where += f":{finding.line}"
            lines.append(f"  {index}. [{finding.severity.upper()}] {finding.title} — {where}")
            if finding.recommendation:
                lines.append(f"     Fix: {finding.recommendation}")
    else:
        lines += ["", "No concrete findings."]
    if review.chapters:
        lines += ["", "Review chapters"]
        for index, chapter in enumerate(review.chapters, 1):
            lines.append(f"  {index}. {chapter.name} [{chapter.risk}] — {', '.join(chapter.files)}")
    return "\n".join(lines)


def render_markdown(review: ReviewResult) -> str:
    out = [
        "# Hoare AI review",
        "",
        f"**Quality:** {review.quality_score}/10  ",
        f"**Risk:** {review.risk_level}  ",
        f"**Language:** {review.language}  ",
        f"**Model:** `{review.model_backend}:{review.model_name}`",
        "",
        "## Summary",
        review.summary,
        "",
        "## Change intent",
        review.change_intent or "Unknown",
        "",
        "## Findings",
    ]
    if not review.findings:
        out.append("No concrete findings.")
    for finding in review.findings:
        location = finding.file or "submission"
        if finding.line:
            location += f":{finding.line}"
        out += [
            "",
            f"### {finding.severity.upper()} · {finding.title}",
            f"**Category:** {finding.category} · **Location:** `{location}` · **Confidence:** {finding.confidence:.2f}",
            "",
            finding.description,
            "",
            f"**Recommendation:** {finding.recommendation}",
        ]
    out += ["", "## Review chapters"]
    for chapter in review.chapters:
        out += [
            "",
            f"### {chapter.name} · {chapter.risk} risk",
            chapter.purpose,
            "",
            "Files: " + ", ".join(f"`{x}`" for x in chapter.files),
        ]
    out += ["", "## Validation plan"]
    for item in review.validation_plan:
        out += ["", f"- **{item.scenario}** — {item.why} Check: {item.suggested_check}"]
    return "\n".join(out) + "\n"


def render_sarif(review: ReviewResult) -> dict:
    rules: dict[str, dict] = {}
    results: list[dict] = []
    level_map = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "note"}
    for finding in review.findings:
        rule_id = f"hoare/{finding.category}/{_slug(finding.title)}"
        rules.setdefault(rule_id, {
            "id": rule_id,
            "name": _slug(finding.title),
            "shortDescription": {"text": finding.title},
            "help": {"text": finding.recommendation},
        })
        result = {
            "ruleId": rule_id,
            "level": level_map.get(finding.severity, "warning"),
            "message": {"text": finding.description},
        }
        if finding.file:
            result["locations"] = [{
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.file},
                    "region": {"startLine": max(1, finding.line or 1)},
                }
            }]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "Hoare AI",
                "informationUri": "https://github.com/Aravindh-dev12/hoare-ai",
                "rules": list(rules.values()),
            }},
            "results": results,
        }],
    }


def render(review: ReviewResult, fmt: str) -> str:
    if fmt == "terminal":
        return render_terminal(review)
    if fmt == "markdown":
        return render_markdown(review)
    if fmt == "json":
        return review.model_dump_json(indent=2)
    if fmt == "sarif":
        return json.dumps(render_sarif(review), indent=2)
    raise ValueError(f"Unsupported output format: {fmt}")


def write_output(review: ReviewResult, fmt: str, output: str | None) -> str:
    text = render(review, fmt)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    return text
