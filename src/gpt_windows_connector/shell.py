from __future__ import annotations

import subprocess
from pathlib import Path


CREATE_NO_WINDOW = 0x08000000


def run_powershell(workspace: Path, command: str, timeout: int = 120) -> dict:
    completed = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
        shell=False,
    )
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
