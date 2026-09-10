from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _command(command: str, shell_type: str) -> list[str]:
    shell_type = shell_type.lower().strip()
    if shell_type in {"powershell", "pwsh"}:
        return ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    if shell_type in {"cmd", "cmd.exe"}:
        return ["cmd.exe", "/d", "/s", "/c", command]
    raise ValueError("shell_type must be 'powershell' or 'cmd'")


def run(spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    job_dir = spec_path.parent
    result_path = job_dir / "result.json"
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"
    state_path = job_dir / "state.json"
    workspace = Path(str(spec["workspace"])).resolve()
    shell_type = str(spec.get("shell_type") or "powershell")
    timeout = max(1, min(int(spec.get("timeout") or 120), 3600))
    started_at = time.time()
    _write_json(state_path, {"state": "running", "pid": os.getpid(), "started_at": started_at})
    exit_code: int | None = None
    timed_out = False
    error = ""
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr:
            proc = subprocess.Popen(
                _command(str(spec.get("command") or ""), shell_type),
                cwd=workspace,
                stdout=stdout,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                shell=False,
            )
            _write_json(state_path, {"state": "running", "pid": os.getpid(), "child_pid": proc.pid, "started_at": started_at})
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                exit_code = proc.wait(timeout=10)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    payload = {
        "exit_code": exit_code,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "shell": shell_type,
        "timed_out": timed_out,
        "error": error or None,
        "started_at": started_at,
        "ended_at": time.time(),
    }
    _write_json(result_path, payload)
    _write_json(state_path, {"state": "completed", "pid": os.getpid(), "ended_at": payload["ended_at"]})
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    args = parser.parse_args()
    raise SystemExit(run(Path(args.spec)))


if __name__ == "__main__":
    main()
