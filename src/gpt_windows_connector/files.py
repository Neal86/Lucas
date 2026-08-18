from __future__ import annotations

import re
from pathlib import Path

from .config import resolve_in_workspace


def list_files(workspace: Path, path: str = ".", recursive: bool = False, limit: int = 500) -> list[str]:
    root = resolve_in_workspace(workspace, path)
    if not root.exists():
        raise FileNotFoundError(path)
    iterator = root.rglob("*") if recursive else root.iterdir()
    out: list[str] = []
    for item in iterator:
        out.append(str(item.relative_to(workspace)))
        if len(out) >= limit:
            break
    return out


def read_text(workspace: Path, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    target = resolve_in_workspace(workspace, path)
    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = max(start_line - 1, 0)
    stop = end_line if end_line is not None else len(lines)
    return "\n".join(lines[start:stop])


def write_text(workspace: Path, path: str, content: str, create_parents: bool = True) -> dict:
    target = resolve_in_workspace(workspace, path)
    if create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": str(target.relative_to(workspace)), "bytes": len(content.encode("utf-8"))}


def patch_text(workspace: Path, path: str, old_text: str, new_text: str, expected_matches: int = 1) -> dict:
    target = resolve_in_workspace(workspace, path)
    current = target.read_text(encoding="utf-8")
    matches = current.count(old_text)
    if matches != expected_matches:
        raise ValueError(f"Expected {expected_matches} exact match(es), found {matches}; file left unchanged")
    updated = current.replace(old_text, new_text)
    target.write_text(updated, encoding="utf-8")
    return {"path": str(target.relative_to(workspace)), "matches": matches}


def search_text(workspace: Path, query: str, path: str = ".", regex: bool = False, limit: int = 200) -> list[dict]:
    root = resolve_in_workspace(workspace, path)
    pattern = re.compile(query if regex else re.escape(query), re.IGNORECASE)
    results: list[dict] = []
    files = root.rglob("*") if root.is_dir() else [root]
    for file in files:
        if not file.is_file():
            continue
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for index, line in enumerate(lines, 1):
            if pattern.search(line):
                results.append({"path": str(file.relative_to(workspace)), "line": index, "text": line[:1000]})
                if len(results) >= limit:
                    return results
    return results
