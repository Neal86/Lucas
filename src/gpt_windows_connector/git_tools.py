from __future__ import annotations

import subprocess
from pathlib import Path


def _git(workspace: Path, *args: str, timeout: int = 120) -> dict:
    completed = subprocess.run(
        ["git", *args], cwd=workspace, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, shell=False,
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
    return _git(workspace, "log", f"-{max(1, min(limit, 200))}", "--oneline", "--decorate")


def branch(workspace: Path) -> dict:
    current = _git(workspace, "branch", "--show-current")
    branches = _git(workspace, "branch", "--format=%(refname:short)")
    return {"exit_code": max(current["exit_code"], branches["exit_code"]), "current": current["stdout"].strip(), "branches": [x for x in branches["stdout"].splitlines() if x], "stderr": current["stderr"] + branches["stderr"]}


def branch_create(workspace: Path, name: str, checkout: bool = True) -> dict:
    return _git(workspace, "switch", "-c", name) if checkout else _git(workspace, "branch", name)


def branch_switch(workspace: Path, name: str) -> dict:
    return _git(workspace, "switch", name)


def add(workspace: Path, paths: list[str] | None = None) -> dict:
    return _git(workspace, "add", "--", *(paths or ["."]))


def commit(workspace: Path, message: str) -> dict:
    return _git(workspace, "commit", "-m", message)


def pull(workspace: Path, remote: str = "origin", branch_name: str | None = None) -> dict:
    args = ["pull", remote]
    if branch_name:
        args.append(branch_name)
    return _git(workspace, *args, timeout=300)


def push(workspace: Path, remote: str = "origin", branch_name: str | None = None, set_upstream: bool = False) -> dict:
    args = ["push"]
    if set_upstream:
        args.append("--set-upstream")
    args.append(remote)
    if branch_name:
        args.append(branch_name)
    return _git(workspace, *args, timeout=300)


def show(workspace: Path, revision: str = "HEAD", path: str | None = None) -> dict:
    target = f"{revision}:{path}" if path else revision
    return _git(workspace, "show", "--stat" if path is None else "--format=", target)
