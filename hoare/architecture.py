from __future__ import annotations

import ast
import re
from pathlib import Path


def dependency_edges(files: dict[str, str]) -> list[tuple[str, str]]:
    names = set(files)
    stems = {Path(n).stem: n for n in names}
    edges: set[tuple[str, str]] = set()

    for name, text in files.items():
        if name.endswith('.py'):
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    targets: list[str] = []
                    if isinstance(node, ast.Import):
                        targets.extend(alias.name.split('.')[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        targets.append(node.module.split('.')[0])
                    for target in targets:
                        if target in stems and stems[target] != name:
                            edges.add((name, stems[target]))
            except SyntaxError:
                pass
        elif Path(name).suffix.lower() in {'.js', '.jsx', '.ts', '.tsx'}:
            for target in re.findall(r'(?:from\s+["\']|require\(["\'])([^"\']+)', text):
                stem = Path(target).stem
                if stem in stems and stems[stem] != name:
                    edges.add((name, stems[stem]))
    return sorted(edges)


def mermaid_graph(files: dict[str, str]) -> str:
    edges = dependency_edges(files)
    if not files:
        return 'graph TD\n  empty[No files]'
    ids = {name: f'N{i}' for i, name in enumerate(sorted(files), start=1)}
    lines = ['graph TD']
    for name in sorted(files):
        safe = name.replace('"', "'")
        lines.append(f'  {ids[name]}["{safe}"]')
    for source, target in edges:
        lines.append(f'  {ids[source]} --> {ids[target]}')
    return '\n'.join(lines)
