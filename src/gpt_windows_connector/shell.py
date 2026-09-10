from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import shutil
import threading
from pathlib import Path

import psutil

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
CREATE_BREAKAWAY_FROM_JOB = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
JOB_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Lucas" / "jobs"
JOB_RETENTION_SECONDS = 7 * 24 * 3600
JOB_STALE_SECONDS = 24 * 3600
JOB_DISK_LIMIT_BYTES = 512 * 1024 * 1024
JOB_CLEANUP_INTERVAL_SECONDS = 300.0
_CLEANUP_LOCK = threading.Lock()
_LAST_CLEANUP = 0.0


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except OSError:
            if attempt == 7:
                raise
            time.sleep(0.02 * (attempt + 1))


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


def _job_dir_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def cleanup_jobs(*, force: bool = False, now: float | None = None) -> dict[str, int]:
    """Best-effort bounded cleanup for durable shell history. Never deletes live jobs."""
    global _LAST_CLEANUP
    current = time.time() if now is None else float(now)
    with _CLEANUP_LOCK:
        if not force and current - _LAST_CLEANUP < JOB_CLEANUP_INTERVAL_SECONDS:
            return {"removed": 0, "freed_bytes": 0}
        _LAST_CLEANUP = current
        try:
            JOB_ROOT.mkdir(parents=True, exist_ok=True)
            jobs = [p for p in JOB_ROOT.iterdir() if p.is_dir()]
        except OSError:
            return {"removed": 0, "freed_bytes": 0}

        removable: list[tuple[float, Path, int]] = []
        total_bytes = 0
        for job in jobs:
            state = _read_json(job / "state.json")
            if _state_alive(state):
                total_bytes += _job_dir_size(job)
                continue
            result = _read_json(job / "result.json")
            spec = _read_json(job / "spec.json") or {}
            try:
                mtime = job.stat().st_mtime
            except OSError:
                continue
            age = current - float((result or {}).get("ended_at") or state and state.get("ended_at") or spec.get("created_at") or mtime)
            size = _job_dir_size(job)
            total_bytes += size
            completed = result is not None or bool(state and state.get("state") == "completed")
            stale = age > JOB_STALE_SECONDS
            expired = completed and age > JOB_RETENTION_SECONDS
            if expired or stale:
                removable.append((mtime, job, size))

        removed = 0
        freed = 0
        for _, job, size in sorted(removable, key=lambda item: item[0]):
            try:
                shutil.rmtree(job)
                removed += 1
                freed += size
                total_bytes -= size
            except OSError:
                pass

        if total_bytes > JOB_DISK_LIMIT_BYTES:
            candidates = []
            for job in JOB_ROOT.iterdir():
                if not job.is_dir():
                    continue
                state = _read_json(job / "state.json")
                if _state_alive(state):
                    continue
                try:
                    mtime = job.stat().st_mtime
                except OSError:
                    continue
                candidates.append((mtime, job, _job_dir_size(job)))
            for _, job, size in sorted(candidates, key=lambda item: item[0]):
                if total_bytes <= JOB_DISK_LIMIT_BYTES:
                    break
                try:
                    shutil.rmtree(job)
                    removed += 1
                    freed += size
                    total_bytes -= size
                except OSError:
                    pass
        return {"removed": removed, "freed_bytes": freed}


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

    cleanup_jobs()
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
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB, close_fds=True, shell=False,
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
