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


def _drain(stream, sink: list[str]) -> None:
    for line in iter(stream.readline, ""):
        sink.append(line)
    stream.close()


def start_process(workspace: Path, command: str) -> dict:
    proc = subprocess.Popen(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command],
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
    _PROCESSES[process_id] = managed
    threading.Thread(target=_drain, args=(proc.stdout, managed.stdout), daemon=True).start()
    threading.Thread(target=_drain, args=(proc.stderr, managed.stderr), daemon=True).start()
    return {"process_id": process_id, "pid": proc.pid}


def poll_process(process_id: str, tail: int = 200) -> dict:
    managed = _PROCESSES.get(process_id)
    if managed is None:
        raise KeyError(f"Unknown process_id: {process_id}")
    code = managed.process.poll()
    return {
        "process_id": process_id,
        "running": code is None,
        "exit_code": code,
        "stdout": "".join(managed.stdout[-tail:]),
        "stderr": "".join(managed.stderr[-tail:]),
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
    return poll_process(process_id)
