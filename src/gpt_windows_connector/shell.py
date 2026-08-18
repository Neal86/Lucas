from __future__ import annotations

import subprocess
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000


def run_powershell(workspace: Path, command: str, timeout: int = 120, shell_type: str = "powershell") -> dict:
    shell_type = shell_type.lower().strip()
    if shell_type in {"powershell", "pwsh"}:
        executable = ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    elif shell_type in {"cmd", "cmd.exe"}:
        executable = ["cmd.exe", "/d", "/s", "/c", command]
    else:
        raise ValueError("shell_type must be 'powershell' or 'cmd'")
    completed = subprocess.run(
        executable,
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1, min(timeout, 3600)),
        creationflags=CREATE_NO_WINDOW,
        shell=False,
    )
    return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "shell": shell_type}
