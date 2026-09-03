from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psutil

APP_NAME = "Lucas"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
PID_FILE = CONFIG_DIR / "lucas-tray.pid"


def _tray_is_running() -> bool:
    try:
        pid = int(PID_FILE.read_text(encoding="ascii").strip())
        process = psutil.Process(pid)
        command = " ".join(process.cmdline()).lower()
        return process.is_running() and "gpt_windows_connector.tray" in command
    except (OSError, ValueError, psutil.Error):
        return False


def _pythonw() -> Path:
    executable = Path(sys.executable).resolve()
    candidate = executable.with_name("pythonw.exe")
    return candidate if candidate.exists() else executable


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Lucas launcher is available on Windows only.")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    pythonw = _pythonw()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # The Lucas shortcut always means "open the app". If the background tray is
    # not running, start it first, but never stop there: Settings must also become
    # visible so Start-menu/Desktop launches behave like a normal Windows app.
    if not _tray_is_running():
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        subprocess.Popen(
            [str(pythonw), "-m", "gpt_windows_connector.tray"],
            cwd=str(CONFIG_DIR),
            creationflags=flags,
            close_fds=True,
        )

    subprocess.Popen(
        [str(pythonw), "-m", "gpt_windows_connector.node", "--configure"],
        cwd=str(CONFIG_DIR),
        creationflags=flags,
        close_fds=True,
    )


if __name__ == "__main__":
    main()
