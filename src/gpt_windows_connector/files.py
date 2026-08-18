from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import resolve_in_workspace


def list_files(workspace: Path, path: str = ".", recursive: bool = False, limit: int = 500) -> list[dict]:
    root = resolve_in_workspace(workspace, path)
    if not root.exists():
        raise FileNotFoundError(path)
    iterator = root.rglob("*") if recursive else root.iterdir()
    out: list[dict] = []
    for item in iterator:
        stat = item.stat()
        out.append({
            "path": str(item.relative_to(workspace)),
            "type": "dir" if item.is_dir() else "file",
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        })
        if len(out) >= max(1, min(limit, 5000)):
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
    target.write_text(current.replace(old_text, new_text), encoding="utf-8")
    return {"path": str(target.relative_to(workspace)), "matches": matches}


def search_text(workspace: Path, query: str, path: str = ".", regex: bool = False, limit: int = 200) -> list[dict]:
    root = resolve_in_workspace(workspace, path)
    pattern = re.compile(query if regex else re.escape(query), re.IGNORECASE)
    results: list[dict] = []
    candidates = root.rglob("*") if root.is_dir() else [root]
    for file in candidates:
        if not file.is_file():
            continue
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for index, line in enumerate(lines, 1):
            if pattern.search(line):
                results.append({"path": str(file.relative_to(workspace)), "line": index, "text": line[:1000]})
                if len(results) >= max(1, min(limit, 5000)):
                    return results
    return results


def stat_path(workspace: Path, path: str) -> dict:
    target = resolve_in_workspace(workspace, path)
    stat = target.stat()
    return {
        "path": str(target.relative_to(workspace)),
        "type": "dir" if target.is_dir() else "file",
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def make_dir(workspace: Path, path: str, parents: bool = True) -> dict:
    target = resolve_in_workspace(workspace, path)
    target.mkdir(parents=parents, exist_ok=True)
    return {"path": str(target.relative_to(workspace))}


def move_path(workspace: Path, source: str, destination: str) -> dict:
    src = resolve_in_workspace(workspace, source)
    dst = resolve_in_workspace(workspace, destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"from": source, "to": destination}


def copy_path(workspace: Path, source: str, destination: str) -> dict:
    src = resolve_in_workspace(workspace, source)
    dst = resolve_in_workspace(workspace, destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return {"from": source, "to": destination}


def delete_path(workspace: Path, path: str, recursive: bool = False) -> dict:
    target = resolve_in_workspace(workspace, path)
    if target == workspace:
        raise PermissionError("Refusing to delete workspace root")
    if target.is_dir():
        if recursive:
            shutil.rmtree(target)
        else:
            target.rmdir()
    else:
        target.unlink()
    return {"deleted": path}
