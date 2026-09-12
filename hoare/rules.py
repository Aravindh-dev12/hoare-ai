from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Rule:
    id: str
    type: str
    description: str


def load_rules(path: str = 'historical_rules.csv') -> list[Rule]:
    p = Path(path)
    if not p.exists():
        packaged = Path(__file__).with_name('default_rules.csv')
        if packaged.exists():
            p = packaged
        else:
            return []
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        return _parse_rows(csv.DictReader(f))


def parse_rules_csv(text: str) -> list[Rule]:
    return _parse_rows(csv.DictReader(io.StringIO(text)))


def _parse_rows(rows) -> list[Rule]:
    output: list[Rule] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        rid = str(row.get('id', '')).strip()
        rtype = str(row.get('type', '')).strip().lower()
        description = str(row.get('description', '')).strip()
        if not description:
            continue
        key = (rtype, description.lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(Rule(id=rid or str(len(output) + 1), type=rtype or 'general', description=description))
    return output


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', text.lower()) if t not in {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'into', 'your'}}


def retrieve_rules(rules: list[Rule], files: dict[str, str], top_k: int = 8) -> list[dict]:
    corpus = '\n'.join(files.values())[:180_000]
    code_tokens = _tokens(corpus)
    scored: list[tuple[float, Rule]] = []
    for rule in rules:
        rt = _tokens(rule.description + ' ' + rule.type)
        if not rt:
            continue
        overlap = len(rt & code_tokens)
        score = overlap / max(1, len(rt))
        keywords = {
            'security': ['sql', 'input', 'token', 'password', 'auth', 'secret'],
            'performance': ['loop', 'cache', 'database', 'query', 'async', 'latency'],
            'formatting': ['variable', 'name', 'format', 'readability'],
        }
        corpus_lower = corpus.lower()
        desc_lower = rule.description.lower()
        if any(k in corpus_lower for k in keywords.get(rule.type, [])):
            score += 0.15
        if 'sql' in desc_lower and any(k in corpus_lower for k in ('select ', 'insert ', 'update ', 'delete ', '.execute(')):
            score += 0.6
        if rule.type == 'performance' and any(k in corpus_lower for k in ('.execute(', 'select ', 'database', 'cursor')):
            score += 0.2
        if rule.type == 'security' and any(k in corpus_lower for k in ('password', 'token', 'secret', 'authorization')):
            score += 0.35
        scored.append((score, rule))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [item for item in scored if item[0] > 0][:top_k]
    if not selected:
        selected = scored[: min(top_k, len(scored))]
    return [
        {'id': rule.id, 'type': rule.type, 'description': rule.description, 'relevance': round(score, 3)}
        for score, rule in selected
    ]
