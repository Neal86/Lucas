from __future__ import annotations

import json
import subprocess
from pathlib import Path


CREATE_NO_WINDOW = 0x08000000


def _ps(command: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
        shell=False,
    )


def list_processes(limit: int = 100) -> list[dict]:
    command = (
        "Get-Process | Sort-Object CPU -Descending | Select-Object -First "
        f"{max(1, min(limit, 500))} Id,ProcessName,MainWindowTitle,Path | ConvertTo-Json -Compress"
    )
    completed = _ps(command)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Unable to list processes")
    raw = completed.stdout.strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def launch_app(target: str, arguments: str = "") -> dict:
    safe_target = target.replace("'", "''")
    safe_args = arguments.replace("'", "''")
    command = f"$p = Start-Process -FilePath '{safe_target}'"
    if arguments:
        command += f" -ArgumentList '{safe_args}'"
    command += " -PassThru; $p | Select-Object Id,ProcessName | ConvertTo-Json -Compress"
    completed = _ps(command)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"Unable to launch {target}")
    return json.loads(completed.stdout)


def system_info() -> dict:
    command = (
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$cs=Get-CimInstance Win32_ComputerSystem;"
        "[pscustomobject]@{ComputerName=$env:COMPUTERNAME;UserName=$env:USERNAME;"
        "Windows=$os.Caption;Version=$os.Version;Architecture=$os.OSArchitecture;"
        "RAMBytes=$cs.TotalPhysicalMemory} | ConvertTo-Json -Compress"
    )
    completed = _ps(command)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Unable to get system information")
    return json.loads(completed.stdout)
