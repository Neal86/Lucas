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

from .i18n import tr
from .app_icon import make_square_icon

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
STATUS_STALE_SECONDS = 45.0

log = logging.getLogger("lucas.tray")


def _acquire_single_instance_mutex() -> object | None:
    if sys.platform != "win32":
        return object()
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\LucasTraySingleInstance")
        if not handle:
            return None
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        log.exception("Could not create tray single-instance mutex")
        return object()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        # Windows PowerShell 5.1 writes -Encoding UTF8 with a BOM. Accept both
        # BOM and non-BOM local JSON so an updater rewrite can never make the tray
        # misread a valid config as empty and overwrite the user's settings.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
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


def _display_status(status: str) -> str:
    return {
        "Online": tr("在线", "Online"),
        "Connecting": tr("连接中…", "Connecting…"),
        "Reconnecting": tr("重新连接中…", "Reconnecting…"),
        "Disconnected": tr("已断开", "Disconnected"),
        "Offline": tr("离线", "Offline"),
    }.get(status, status or tr("离线", "Offline"))


def _status_label(status: str) -> str:
    icon = {"Online": "●", "Connecting": "◐", "Reconnecting": "↻", "Disconnected": "○", "Offline": "○"}.get(status, "○")
    return f"{icon}  {_display_status(status)}"


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
        self._ever_online = False
        self._restart_attempts = 0
        self._settings_process: subprocess.Popen[Any] | None = None

    def _runtime_pythonw(self) -> Path:
        executable = Path(sys.executable).resolve()
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
        if executable.exists():
            return executable
        raise FileNotFoundError("Lucas Python runtime is missing. Run the Lucas installer again.")

    def _spawn_node(self) -> None:
        with self._lock:
            if self._process and self._process.poll() is None:
                return
            pythonw = self._runtime_pythonw()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._process = subprocess.Popen([str(pythonw), "-m", "gpt_windows_connector.node"], cwd=str(CONFIG_DIR), creationflags=flags, close_fds=True)
            self._status = "Reconnecting" if self._ever_online else "Connecting"
            self._detail = ""
            self._restart_attempts += 1
            log.info("Started Lucas Node pid=%s attempt=%s", self._process.pid, self._restart_attempts)

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
            self._status = "Disconnected"
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
        self._status = "Reconnecting"
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
        completed = subprocess.run(
            ["schtasks", "/Change", "/TN", TASK_NAME, "/ENABLE" if enabled else "/DISABLE"],
            capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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

    def _focus_settings_window(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            found = []
            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def enum_proc(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title in {"Lucas Settings", "Lucas 设置"}:
                    found.append(hwnd)
                    return False
                return True
            user32.EnumWindows(enum_proc, 0)
            if not found:
                return False
            hwnd = found[0]
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception:
            log.exception("Could not focus Lucas Settings window")
            return False

    def _open_settings(self, icon: Any = None, item: Any = None) -> None:
        process = self._settings_process
        if process is not None and process.poll() is None:
            self._focus_settings_window()
            return
        if self._focus_settings_window():
            return
        try:
            pythonw = self._runtime_pythonw()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen([str(pythonw), "-m", "gpt_windows_connector.node", "--configure"], cwd=str(CONFIG_DIR), creationflags=flags, close_fds=True)
            self._settings_process = process
        except Exception as exc:
            log.exception("Could not open Lucas Settings")
            _message_box(str(exc), "Lucas Settings")
            return

        def wait_for_settings() -> None:
            try:
                process.wait()
                if process.returncode == 0:
                    if _connection_enabled(_load_config()):
                        self._reconnect()
                    else:
                        self._stop_node()
                        self._status = "Disconnected"
                        self._detail = "Disconnected by local settings"
                        self._write_local_status()
            except Exception:
                log.exception("Could not apply Lucas Settings")
            finally:
                self._settings_process = None
                self._refresh_icon(force=True)

        threading.Thread(target=wait_for_settings, name="lucas-settings-watcher", daemon=True).start()

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

    def _restart_lucas(self, icon: Any = None, item: Any = None) -> None:
        try:
            self._stop_node()
            pythonw = Path(sys.executable).resolve()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            current_pid = os.getpid()
            helper = (
                "import subprocess,time,psutil; "
                f"pid={current_pid}; "
                "[(time.sleep(0.1)) for _ in range(50) if psutil.pid_exists(pid)]; "
                f"subprocess.Popen({[str(pythonw), '-m', 'gpt_windows_connector.tray']!r}, cwd={str(CONFIG_DIR)!r}, creationflags={flags}, close_fds=True)"
            )
            subprocess.Popen([str(pythonw), "-c", helper], cwd=str(CONFIG_DIR), creationflags=flags, close_fds=True)
            log.info("Restarting Lucas tray and node")
        except Exception as exc:
            log.exception("Could not restart Lucas")
            _message_box(str(exc), "Restart Lucas")
            return
        self._stop.set()
        if self._icon is not None:
            self._icon.stop()

    def _exit(self, icon: Any = None, item: Any = None) -> None:
        self._stop.set()
        self._stop_node()
        # Exit Lucas means exit the whole local app, not just the tray. Settings can
        # also be opened by the desktop launcher, so close every configure process.
        try:
            for process in psutil.process_iter(["pid","cmdline"]):
                if process.pid == os.getpid(): continue
                command=" ".join(process.info.get("cmdline") or []).lower()
                if "gpt_windows_connector.node" in command and "--configure" in command:
                    try: process.terminate()
                    except psutil.Error: pass
        except Exception:
            log.exception("Could not close Lucas Settings during exit")
        self._status = "Offline"
        self._detail = "Lucas exited"
        self._write_local_status()
        if self._icon is not None:
            self._icon.stop()

    def _write_local_status(self) -> None:
        try:
            _save_json(STATUS_FILE, {"status": self._status, "detail": self._detail, "time": time.time(), "source": "tray"})
        except Exception:
            log.exception("Could not write tray status")

    def _read_node_status(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is not None:
            exit_code = process.returncode
            with self._lock:
                if self._process is process:
                    self._process = None
            self._status = "Reconnecting" if _connection_enabled(_load_config()) else "Disconnected"
            self._detail = f"Node exited with code {exit_code}"
            log.warning("Lucas Node exited unexpectedly with code %s", exit_code)
            return

        status = _load_json(STATUS_FILE)
        value = str(status.get("status") or "").strip()
        try:
            status_time = float(status.get("time") or 0.0)
        except (TypeError, ValueError):
            status_time = 0.0
        age = time.time() - status_time if status_time else float("inf")
        if age > STATUS_STALE_SECONDS:
            if self._status == "Online":
                self._status = "Reconnecting"
                self._detail = "Waiting for node heartbeat"
            return
        if value in {"Online", "Connecting", "Offline", "Reconnecting"}:
            self._status = value
            self._detail = str(status.get("detail") or "")
            if value == "Online":
                self._ever_online = True
                self._restart_attempts = 0

    def _make_icon(self, status: str) -> Any:
        return make_square_icon(status=status, size=64)

    def _refresh_icon(self, force: bool = False) -> None:
        icon = self._icon
        if icon is None:
            return
        config = _load_config()
        menu_state = f"{_connection_enabled(config)}:{_startup_enabled(config)}:{self._status}:{self._detail}"
        if force or self._last_icon_state != self._status:
            icon.icon = self._make_icon(self._status)
            icon.title = f"Lucas • {_display_status(self._status)}"
            self._last_icon_state = self._status
        if force or self._last_menu_state != menu_state:
            try:
                icon.update_menu()
            except Exception:
                log.exception("Could not refresh tray menu")
            self._last_menu_state = menu_state

    def _supervise(self) -> None:
        while not self._stop.wait(1.0):
            try:
                config = _load_config()
                enabled = _connection_enabled(config)
                if enabled:
                    process = self._process
                    if process is None or process.poll() is not None:
                        self._status = "Reconnecting" if self._ever_online else "Connecting"
                        try:
                            self._spawn_node()
                        except Exception as exc:
                            self._status = "Offline"
                            self._detail = str(exc)
                            log.warning("Node launch failed; retrying: %s", exc)
                    self._read_node_status()
                else:
                    self._status = "Disconnected"
                    self._detail = "Disconnected by user"
                self._refresh_icon()
            except Exception:
                log.exception("Tray supervisor iteration failed; continuing")

    def run(self) -> None:
        import pystray
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()), encoding="ascii")
        config = _load_config()
        config.setdefault("connection_enabled", True)
        config.setdefault("launch_at_startup", True)
        _save_config(config)

        menu = pystray.Menu(
            pystray.MenuItem("Lucas", lambda icon, item: None, enabled=False),
            pystray.MenuItem(lambda item: _status_label(self._status), lambda icon, item: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: tr("断开连接", "Disconnect") if _connection_enabled(_load_config()) else tr("连接", "Connect"), self._toggle_connection),
            pystray.MenuItem(tr("立即重新连接", "Reconnect now"), self._reconnect, enabled=lambda item: _connection_enabled(_load_config())),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("开机启动", "Launch at startup"), self._toggle_startup, checked=lambda item: _startup_enabled(_load_config())),
            pystray.Menu.SEPARATOR,
            # On Windows pystray invokes the default menu item when the tray icon
            # is double-clicked, so Settings is the single primary tray action.
            pystray.MenuItem(tr("设置", "Settings"), self._open_settings, default=True),
            pystray.MenuItem(tr("打开 Dashboard", "Open Dashboard"), self._open_dashboard),
            pystray.MenuItem(tr("查看日志", "View logs"), self._view_logs),
            pystray.MenuItem(tr("重启 Lucas", "Restart Lucas"), self._restart_lucas),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("退出 Lucas", "Exit Lucas"), self._exit),
        )
        initial = "Disconnected" if not _connection_enabled(config) else "Connecting"
        self._status = initial
        self._icon = pystray.Icon("Lucas", self._make_icon(initial), f"Lucas • {_display_status(initial)}", menu)
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
    mutex = _acquire_single_instance_mutex()
    if mutex is None:
        log.info("Another Lucas tray instance is already running; exiting duplicate process")
        return
    log.info("Lucas tray starting pid=%s", os.getpid())
    try:
        LucasTray().run()
    except Exception:
        log.exception("Lucas tray crashed")
        raise


if __name__ == "__main__":
    main()
