from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

APP_NAME = "Lucas"
TASK_NAME = "Lucas Node"
DASHBOARD_URL = "https://lucasmcp.com/nodes"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"
STATE_FILE = CONFIG_DIR / "node-state.json"
STATUS_FILE = CONFIG_DIR / "node-status.json"
LOG_FILE = CONFIG_DIR / "lucas-node.log"
TRAY_LOG_FILE = CONFIG_DIR / "lucas-tray.log"
PID_FILE = CONFIG_DIR / "lucas-tray.pid"

log = logging.getLogger("lucas.tray")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_config() -> dict[str, Any]:
    return _load_json(CONFIG_FILE)


def _save_config(config: dict[str, Any]) -> None:
    _save_json(CONFIG_FILE, config)


def _connection_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("connection_enabled", True))


def _startup_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("launch_at_startup", True))


def _setup_logging() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.FileHandler(TRAY_LOG_FILE, encoding="utf-8")
        handler.setFormatter(formatter)
        root.addHandler(handler)


def _message_box(text: str, title: str = APP_NAME, flags: int = 0x40) -> int:
    try:
        import ctypes

        return int(ctypes.windll.user32.MessageBoxW(None, text, title, flags))
    except Exception:
        return 0


class LucasTray:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._process: subprocess.Popen[Any] | None = None
        self._status = "Offline"
        self._detail = ""
        self._icon: Any = None
        self._last_icon_state = ""
        self._last_menu_state = ""

    def _node_executable(self) -> Path:
        scripts = Path(sys.executable).resolve().parent
        for name in ("lucas-node.exe", "gwc-node.exe"):
            candidate = scripts / name
            if candidate.exists():
                return candidate
        raise FileNotFoundError("Lucas Node launcher is missing. Run the Lucas installer again.")

    def _spawn_node(self) -> None:
        with self._lock:
            if self._process and self._process.poll() is None:
                return
            executable = self._node_executable()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._process = subprocess.Popen(
                [str(executable)],
                cwd=str(CONFIG_DIR),
                creationflags=flags,
                close_fds=True,
            )
            self._status = "Connecting"
            self._detail = ""
            log.info("Started Lucas Node pid=%s", self._process.pid)

    def _stop_node(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if not process or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        except Exception:
            log.exception("Failed stopping Lucas Node")
        log.info("Stopped Lucas Node")

    def _set_connection_enabled(self, enabled: bool) -> None:
        config = _load_config()
        config["connection_enabled"] = bool(enabled)
        _save_config(config)

    def _toggle_connection(self, icon: Any = None, item: Any = None) -> None:
        enabled = _connection_enabled(_load_config())
        if enabled:
            self._set_connection_enabled(False)
            self._stop_node()
            self._status = "Offline"
            self._detail = "Disconnected by user"
            self._write_local_status()
        else:
            self._set_connection_enabled(True)
            try:
                self._spawn_node()
            except Exception as exc:
                log.exception("Could not connect Lucas Node")
                self._status = "Offline"
                self._detail = str(exc)
                _message_box(str(exc), "Lucas Node")
        self._refresh_icon(force=True)

    def _reconnect(self, icon: Any = None, item: Any = None) -> None:
        self._set_connection_enabled(True)
        self._stop_node()
        try:
            self._spawn_node()
        except Exception as exc:
            log.exception("Could not reconnect Lucas Node")
            self._status = "Offline"
            self._detail = str(exc)
            _message_box(str(exc), "Lucas Node")
        self._refresh_icon(force=True)

    def _toggle_startup(self, icon: Any = None, item: Any = None) -> None:
        config = _load_config()
        enabled = not _startup_enabled(config)
        command = ["schtasks", "/Change", "/TN", TASK_NAME, "/ENABLE" if enabled else "/DISABLE"]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "Could not update Windows startup task.").strip()
            log.error("Startup task update failed: %s", message)
            _message_box(message, "Lucas startup")
            return
        config["launch_at_startup"] = enabled
        _save_config(config)
        log.info("Launch at startup=%s", enabled)
        self._refresh_icon(force=True)

    def _open_dashboard(self, icon: Any = None, item: Any = None) -> None:
        webbrowser.open(DASHBOARD_URL)

    def _view_logs(self, icon: Any = None, item: Any = None) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        target = LOG_FILE if LOG_FILE.exists() else CONFIG_DIR
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
        except Exception as exc:
            log.exception("Could not open logs")
            _message_box(str(exc), "Lucas logs")

    def _repair(self, icon: Any = None, item: Any = None) -> None:
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            code = simpledialog.askstring(
                "Re-pair Lucas",
                "Generate a new pairing code in Lucas > Computer Nodes,\nthen enter it here:",
                parent=root,
            )
            root.destroy()
        except Exception as exc:
            log.exception("Could not open re-pair dialog")
            _message_box(str(exc), "Re-pair Lucas")
            return
        if not code or not code.strip():
            return
        self._stop_node()
        config = _load_config()
        config["pairing_code"] = code.strip()
        config["connection_enabled"] = True
        _save_config(config)
        try:
            STATE_FILE.unlink(missing_ok=True)
        except OSError:
            log.exception("Could not remove previous pairing state")
            _message_box("Could not reset the previous pairing token.", "Re-pair Lucas")
            return
        try:
            self._spawn_node()
        except Exception as exc:
            log.exception("Could not start re-pair")
            _message_box(str(exc), "Re-pair Lucas")
            return
        self._refresh_icon(force=True)

    def _exit(self, icon: Any = None, item: Any = None) -> None:
        self._stop.set()
        self._stop_node()
        self._status = "Offline"
        self._detail = "Lucas tray exited"
        self._write_local_status()
        if self._icon is not None:
            self._icon.stop()

    def _write_local_status(self) -> None:
        try:
            _save_json(
                STATUS_FILE,
                {
                    "status": self._status,
                    "detail": self._detail,
                    "time": time.time(),
                },
            )
        except Exception:
            log.exception("Could not write tray status")

    def _read_node_status(self) -> None:
        process = self._process
        if process and process.poll() is not None:
            exit_code = process.returncode
            with self._lock:
                if self._process is process:
                    self._process = None
            self._status = "Reconnecting" if _connection_enabled(_load_config()) else "Offline"
            self._detail = f"Node exited with code {exit_code}"
        status = _load_json(STATUS_FILE)
        value = str(status.get("status") or "").strip()
        if value in {"Online", "Connecting", "Offline", "Reconnecting"}:
            self._status = value
            self._detail = str(status.get("detail") or "")

    def _make_icon(self, status: str) -> Any:
        from PIL import Image, ImageDraw, ImageFont

        palette = {
            "Online": (33, 180, 92, 255),
            "Connecting": (245, 166, 35, 255),
            "Reconnecting": (245, 166, 35, 255),
            "Offline": (120, 126, 137, 255),
        }
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        fill = palette.get(status, palette["Offline"])
        draw.rounded_rectangle((5, 5, 59, 59), radius=14, fill=fill)
        try:
            font = ImageFont.truetype("segoeuib.ttf", 37)
        except OSError:
            font = ImageFont.load_default()
        draw.text((20, 9), "L", fill=(255, 255, 255, 255), font=font)
        return image

    def _refresh_icon(self, force: bool = False) -> None:
        icon = self._icon
        if icon is None:
            return
        config = _load_config()
        menu_state = f"{_connection_enabled(config)}:{_startup_enabled(config)}:{self._status}"
        if force or self._last_icon_state != self._status:
            icon.icon = self._make_icon(self._status)
            icon.title = f"Lucas Node - {self._status}"
            self._last_icon_state = self._status
        if force or self._last_menu_state != menu_state:
            icon.update_menu()
            self._last_menu_state = menu_state

    def _supervise(self) -> None:
        while not self._stop.wait(1.0):
            config = _load_config()
            enabled = _connection_enabled(config)
            if enabled:
                process = self._process
                if process is None or process.poll() is not None:
                    self._status = "Reconnecting" if process is not None else "Connecting"
                    try:
                        self._spawn_node()
                    except Exception as exc:
                        self._status = "Offline"
                        self._detail = str(exc)
                        log.warning("Node launch failed; retrying: %s", exc)
                self._read_node_status()
            else:
                self._status = "Offline"
                self._detail = "Disconnected by user"
            self._refresh_icon()

    def run(self) -> None:
        import pystray

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()), encoding="ascii")
        config = _load_config()
        config.setdefault("connection_enabled", True)
        config.setdefault("launch_at_startup", True)
        _save_config(config)

        menu = pystray.Menu(
            pystray.MenuItem(lambda item: f"Lucas Node: {self._status}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "Disconnect" if _connection_enabled(_load_config()) else "Connect",
                self._toggle_connection,
            ),
            pystray.MenuItem(
                "Reconnect now",
                self._reconnect,
                enabled=lambda item: _connection_enabled(_load_config()),
            ),
            pystray.MenuItem(
                "Launch at startup",
                self._toggle_startup,
                checked=lambda item: _startup_enabled(_load_config()),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Lucas Dashboard", self._open_dashboard, default=True),
            pystray.MenuItem("View logs", self._view_logs),
            pystray.MenuItem("Re-pair this computer", self._repair),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Lucas Node", self._exit),
        )
        self._icon = pystray.Icon("Lucas", self._make_icon("Connecting"), "Lucas Node - Connecting", menu)
        worker = threading.Thread(target=self._supervise, name="lucas-tray-supervisor", daemon=True)
        worker.start()
        try:
            self._icon.run()
        finally:
            self._stop.set()
            self._stop_node()
            try:
                PID_FILE.unlink(missing_ok=True)
            except OSError:
                pass


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Lucas tray is available on Windows only.")
    _setup_logging()
    log.info("Lucas tray starting")
    LucasTray().run()


if __name__ == "__main__":
    main()
