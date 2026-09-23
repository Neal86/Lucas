from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any


def launch_configured_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Start a locally configured browser/profile launcher without using a shell.

    The launcher definition is local-only profile metadata. Remote agents can select
    a profile but cannot write launcher commands through browser_tool.
    """
    launcher = profile.get("launcher") if isinstance(profile.get("launcher"), dict) else {}
    kind = str(launcher.get("kind") or "").strip().lower()
    if not kind:
        return {"started": False, "reason": "No local launcher is configured for this profile."}
    if kind != "command":
        return {"started": False, "reason": f"Unsupported launcher kind: {kind}"}

    executable = Path(str(launcher.get("executable") or "")).expanduser()
    if not executable.is_file():
        return {"started": False, "reason": f"Configured launcher executable does not exist: {executable}"}
    args = [str(value) for value in launcher.get("args") or []]
    cwd_raw = str(launcher.get("cwd") or "").strip()
    cwd = str(Path(cwd_raw).expanduser()) if cwd_raw else str(executable.parent)
    process = subprocess.Popen(
        [str(executable), *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {
        "started": True,
        "pid": int(process.pid),
        "kind": kind,
        "started_at": time.time(),
    }
