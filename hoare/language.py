from __future__ import annotations

from collections import Counter
from pathlib import Path

EXT_TO_LANGUAGE = {
    '.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TypeScript',
    '.java': 'Java', '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby', '.php': 'PHP', '.cs': 'C#',
    '.cpp': 'C++', '.cc': 'C++', '.c': 'C', '.h': 'C/C++', '.hpp': 'C++', '.kt': 'Kotlin',
    '.kts': 'Kotlin', '.swift': 'Swift', '.scala': 'Scala', '.sql': 'SQL', '.html': 'HTML',
    '.css': 'CSS', '.scss': 'SCSS', '.vue': 'Vue', '.svelte': 'Svelte', '.sh': 'Shell', '.bash': 'Shell'
}


def detect_language(files: dict[str, str], hint: str = 'Auto') -> str:
    if hint and hint != 'Auto':
        return hint
    counts: Counter[str] = Counter()
    for name in files:
        language = EXT_TO_LANGUAGE.get(Path(name).suffix.lower())
        if language:
            counts[language] += 1
    if counts:
        return counts.most_common(1)[0][0]
    if not files:
        return 'Unknown'
    text = '\n'.join(files.values())[:6000]
    if 'def ' in text and 'import ' in text:
        return 'Python'
    if 'function ' in text or 'const ' in text or '=>' in text:
        return 'JavaScript/TypeScript'
    if 'public class ' in text:
        return 'Java'
    return 'Unknown'
