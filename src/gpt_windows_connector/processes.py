from __future__ import annotations

import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ManagedProcess:
    process: subprocess.Popen[str]
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)


_PROCESSES: dict[str, ManagedProcess] = {}
_LOCK = threading.RLock()


def _drain(stream, sink: list[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
    finally:
        stream.close()


def _command(command: str, shell_type: str) -> list[str]:
    shell_type = shell_type.lower().strip()
    if shell_type in {"powershell", "pwsh"}:
        return ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command]
    if shell_type in {"cmd", "cmd.exe"}:
        return ["cmd.exe", "/d", "/s", "/c", command]
    raise ValueError("shell_type must be 'powershell' or 'cmd'")


def start_process(workspace: Path, command: str, shell_type: str = "powershell") -> dict:
    proc = subprocess.Popen(
        _command(command, shell_type),
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        shell=False,
    )
    process_id = uuid.uuid4().hex
    managed = ManagedProcess(proc)
    with _LOCK:
        _PROCESSES[process_id] = managed
    threading.Thread(target=_drain, args=(proc.stdout, managed.stdout), daemon=True).start()
    threading.Thread(target=_drain, args=(proc.stderr, managed.stderr), daemon=True).start()
    return {"process_id": process_id, "pid": proc.pid, "shell": shell_type}


def poll_process(process_id: str, stdout_cursor: int = 0, stderr_cursor: int = 0, max_lines: int = 500) -> dict:
    managed = _PROCESSES.get(process_id)
    if managed is None:
        raise KeyError(f"Unknown process_id: {process_id}")
    max_lines = max(1, min(max_lines, 5000))
    stdout_cursor = max(0, stdout_cursor)
    stderr_cursor = max(0, stderr_cursor)
    stdout_end = min(len(managed.stdout), stdout_cursor + max_lines)
    stderr_end = min(len(managed.stderr), stderr_cursor + max_lines)
    code = managed.process.poll()
    return {
        "process_id": process_id,
        "pid": managed.process.pid,
        "running": code is None,
        "exit_code": code,
        "stdout": "".join(managed.stdout[stdout_cursor:stdout_end]),
        "stderr": "".join(managed.stderr[stderr_cursor:stderr_end]),
        "stdout_cursor": stdout_end,
        "stderr_cursor": stderr_end,
    }


def stop_process(process_id: str) -> dict:
    managed = _PROCESSES.get(process_id)
    if managed is None:
        raise KeyError(f"Unknown process_id: {process_id}")
    if managed.process.poll() is None:
        managed.process.terminate()
        try:
            managed.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            managed.process.kill()
            managed.process.wait(timeout=5)
    return poll_process(process_id)


def list_managed_processes() -> list[dict]:
    result = []
    for process_id, managed in list(_PROCESSES.items()):
        code = managed.process.poll()
        result.append({"process_id": process_id, "pid": managed.process.pid, "running": code is None, "exit_code": code})
    return result
