from __future__ import annotations

import os
import re
import requests


def fetch_pr_files(repo: str, pr_number: int) -> dict[str, str]:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo.strip()):
        raise ValueError('Repository must be in owner/name format.')
    if pr_number <= 0:
        raise ValueError('PR number must be positive.')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    token = os.getenv('GITHUB_TOKEN', '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    url = f'https://api.github.com/repos/{repo}/pulls/{pr_number}/files'
    response = requests.get(url, headers=headers, params={'per_page': 100}, timeout=15)
    if response.status_code >= 400:
        raise ValueError(f'GitHub returned {response.status_code}: {response.text[:180]}')
    files: dict[str, str] = {}
    for item in response.json():
        patch = item.get('patch')
        if patch:
            files[item['filename']] = patch
    if not files:
        raise ValueError('No textual patches were available for this PR.')
    return files
