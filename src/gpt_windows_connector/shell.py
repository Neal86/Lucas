from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
JOB_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Lucas" / "jobs"


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _job_key(request_id: str) -> str:
    clean = "".join(ch for ch in request_id if ch.isalnum() or ch in "-_")[:96]
    return clean or hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def _command_fingerprint(workspace: Path, command: str, shell_type: str) -> str:
    raw = f"{workspace.resolve()}\0{shell_type.lower().strip()}\0{command}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _legacy_run(workspace: Path, command: str, timeout: int, shell_type: str) -> dict:
    shell_type = shell_type.lower().strip()
    if shell_type in {"powershell", "pwsh"}:
        executable = ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    elif shell_type in {"cmd", "cmd.exe"}:
        executable = ["cmd.exe", "/d", "/s", "/c", command]
    else:
        raise ValueError("shell_type must be 'powershell' or 'cmd'")
    completed = subprocess.run(
        executable, cwd=workspace, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=max(1, min(timeout, 3600)), creationflags=CREATE_NO_WINDOW, shell=False,
    )
    return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "shell": shell_type}


def _state_alive(state: dict | None) -> bool:
    if not state:
        return False
    for key in ("child_pid", "pid"):
        try:
            pid = int(state.get(key) or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid > 0 and psutil.pid_exists(pid):
            return True
    return False


def run_powershell(workspace: Path, command: str, timeout: int = 120, shell_type: str = "powershell", _request_id: str | None = None) -> dict:
    """Run a shell command; Gateway-originated calls are durable across Node restarts.

    A tiny detached worker owns the real child process and writes stdout/stderr/result
    to LOCALAPPDATA. Replaying the same request ID therefore attaches to the existing
    job instead of executing the command twice.
    """
    workspace = workspace.resolve()
    timeout = max(1, min(int(timeout), 3600))
    shell_type = shell_type.lower().strip()
    if not _request_id:
        return _legacy_run(workspace, command, timeout, shell_type)

    job_dir = JOB_ROOT / _job_key(str(_request_id))
    spec_path = job_dir / "spec.json"
    state_path = job_dir / "state.json"
    result_path = job_dir / "result.json"
    fingerprint = _command_fingerprint(workspace, command, shell_type)
    existing = _read_json(spec_path)
    if existing and str(existing.get("fingerprint") or "") != fingerprint:
        raise RuntimeError("Durable shell request ID was reused for a different command")

    result = _read_json(result_path)
    if result is not None:
        result["recovered"] = True
        return result

    if not existing:
        job_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "request_id": str(_request_id), "workspace": str(workspace), "command": command,
            "shell_type": shell_type, "timeout": timeout, "fingerprint": fingerprint, "created_at": time.time(),
        }
        _atomic_json(spec_path, spec)
        _atomic_json(state_path, {"state": "launching", "created_at": spec["created_at"]})
        subprocess.Popen(
            [sys.executable, "-m", "gpt_windows_connector.shell_job", str(spec_path)],
            cwd=workspace, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True, shell=False,
        )

    deadline = time.monotonic() + timeout + 15
    while time.monotonic() < deadline:
        result = _read_json(result_path)
        if result is not None:
            result["recovered"] = bool(existing)
            return result
        state = _read_json(state_path)
        if state and state.get("state") == "completed":
            time.sleep(0.05)
            continue
        if existing and state and not _state_alive(state) and time.time() - float(state.get("started_at") or state.get("created_at") or 0) > 3:
            raise RuntimeError("Durable shell job was interrupted before producing a result; command was not re-executed")
        time.sleep(0.1)
    raise TimeoutError(f"Durable shell job did not publish a result within {timeout + 15}s")
