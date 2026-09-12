from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests


@dataclass
class PRContext:
    repo: str
    number: int
    title: str
    base_sha: str
    head_sha: str
    base_ref: str
    head_ref: str
    files: dict[str, str]

    @property
    def source(self) -> str:
        return f"github:{self.repo}#{self.number}:{self.base_sha[:12]}..{self.head_sha[:12]}"


def _headers() -> dict[str, str]:
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    token = os.getenv('GITHUB_TOKEN', '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _validate(repo: str, pr_number: int) -> str:
    repo = repo.strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Repository must be in owner/name format.')
    if pr_number <= 0:
        raise ValueError('PR number must be positive.')
    return repo


def fetch_pr_context(repo: str, pr_number: int) -> PRContext:
    repo = _validate(repo, pr_number)
    headers = _headers()
    pr_url = f'https://api.github.com/repos/{repo}/pulls/{pr_number}'
    pr_response = requests.get(pr_url, headers=headers, timeout=20)
    if pr_response.status_code >= 400:
        raise ValueError(f'GitHub returned {pr_response.status_code}: {pr_response.text[:180]}')
    pr = pr_response.json()

    files: dict[str, str] = {}
    page = 1
    while page <= 20:
        response = requests.get(
            f'{pr_url}/files', headers=headers,
            params={'per_page': 100, 'page': page}, timeout=20,
        )
        if response.status_code >= 400:
            raise ValueError(f'GitHub returned {response.status_code}: {response.text[:180]}')
        batch = response.json()
        for item in batch:
            patch = item.get('patch')
            if patch:
                files[item['filename']] = patch
        if len(batch) < 100:
            break
        page += 1

    if not files:
        raise ValueError('No textual patches were available for this PR.')
    return PRContext(
        repo=repo,
        number=pr_number,
        title=str(pr.get('title', '')),
        base_sha=str(pr.get('base', {}).get('sha', '')),
        head_sha=str(pr.get('head', {}).get('sha', '')),
        base_ref=str(pr.get('base', {}).get('ref', '')),
        head_ref=str(pr.get('head', {}).get('ref', '')),
        files=files,
    )


def fetch_pr_files(repo: str, pr_number: int) -> dict[str, str]:
    return fetch_pr_context(repo, pr_number).files
