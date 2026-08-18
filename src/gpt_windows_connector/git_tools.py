from __future__ import annotations

import subprocess
from pathlib import Path


def _git(workspace: Path, *args: str, timeout: int = 120) -> dict:
    completed = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
    )
    return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def status(workspace: Path) -> dict:
    return _git(workspace, "status", "--short", "--branch")


def diff(workspace: Path, staged: bool = False, path: str | None = None) -> dict:
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        args.extend(["--", path])
    return _git(workspace, *args)


def log(workspace: Path, limit: int = 20) -> dict:
    return _git(workspace, "log", f"-{limit}", "--oneline", "--decorate")


def branch(workspace: Path) -> dict:
    return _git(workspace, "branch", "--show-current")


def add(workspace: Path, paths: list[str] | None = None) -> dict:
    return _git(workspace, "add", "--", *(paths or ["."]))


def commit(workspace: Path, message: str) -> dict:
    return _git(workspace, "commit", "-m", message)


def pull(workspace: Path, remote: str = "origin", branch_name: str | None = None) -> dict:
    args = ["pull", remote]
    if branch_name:
        args.append(branch_name)
    return _git(workspace, *args, timeout=300)


def push(workspace: Path, remote: str = "origin", branch_name: str | None = None) -> dict:
    args = ["push", remote]
    if branch_name:
        args.append(branch_name)
    return _git(workspace, *args, timeout=300)
