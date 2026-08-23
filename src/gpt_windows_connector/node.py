from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlencode

import websockets

from .config import NodeSettings
from .executor import Executor

APP_NAME = "Lucas"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"
LOG_FILE = CONFIG_DIR / "lucas-node.log"
DEFAULT_GATEWAY = "wss://lucas.autozon.xyz/ws/node"
log = logging.getLogger("lucas.node")


def _default_node_id() -> str:
    machine = os.environ.get("COMPUTERNAME") or socket.gethostname() or "windows-node"
    return f"{machine}-{uuid.getnode():012x}".lower()


def _load_config() -> dict[str, object]:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(config: dict[str, object]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CONFIG_FILE)


def _configure_gui(existing: dict[str, object]) -> dict[str, object] | None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception as exc:
        raise RuntimeError(f"Lucas configuration UI is unavailable: {exc}") from exc

    result: dict[str, object] | None = None
    root = tk.Tk()
    root.title("Lucas Windows Node Setup")
    root.geometry("620x560")
    root.minsize(560, 500)

    gateway = tk.StringVar(value=str(existing.get("gateway_ws_url") or DEFAULT_GATEWAY))
    node_id = tk.StringVar(value=str(existing.get("node_id") or _default_node_id()))
    node_name = tk.StringVar(value=str(existing.get("node_name") or os.environ.get("COMPUTERNAME") or socket.gethostname()))
    pairing_code = tk.StringVar(value=str(existing.get("pairing_code") or ""))
    permission = tk.StringVar(value=str(existing.get("permission_level") or "operate"))
    roots = [str(item) for item in existing.get("allowed_roots", []) if str(item).strip()]
    if not roots:
        roots = [str(Path.home().resolve())]

    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Lucas Windows Node", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Connect this Windows PC securely to your Lucas gateway.").pack(anchor="w", pady=(0, 16))

    form = ttk.Frame(frame)
    form.pack(fill="x")

    def add_field(label: str, variable: tk.StringVar, show: str | None = None) -> None:
        ttk.Label(form, text=label).pack(anchor="w")
        ttk.Entry(form, textvariable=variable, show=show or "").pack(fill="x", pady=(2, 10))

    add_field("Gateway WebSocket URL", gateway)
    add_field("Node name", node_name)
    add_field("Node ID", node_id)
    add_field("Pairing code", pairing_code)

    ttk.Label(form, text="Permission level").pack(anchor="w")
    ttk.Combobox(form, textvariable=permission, values=("read", "operate", "admin"), state="readonly").pack(fill="x", pady=(2, 10))

    ttk.Label(form, text="Allowed folders").pack(anchor="w")
    roots_frame = ttk.Frame(form)
    roots_frame.pack(fill="both", expand=True, pady=(2, 10))
    roots_list = tk.Listbox(roots_frame, height=6)
    roots_list.pack(side="left", fill="both", expand=True)
    for item in roots:
        roots_list.insert("end", item)
    buttons = ttk.Frame(roots_frame)
    buttons.pack(side="left", fill="y", padx=(8, 0))

    def add_root() -> None:
        selected = filedialog.askdirectory(title="Choose a folder Lucas may access")
        if selected and selected not in roots_list.get(0, "end"):
            roots_list.insert("end", selected)

    def remove_root() -> None:
        selected = roots_list.curselection()
        if selected:
            roots_list.delete(selected[0])

    ttk.Button(buttons, text="Add folder", command=add_root).pack(fill="x", pady=(0, 6))
    ttk.Button(buttons, text="Remove", command=remove_root).pack(fill="x")

    status = ttk.Label(frame, text=r"Configuration is stored locally in %LOCALAPPDATA%\Lucas.")
    status.pack(anchor="w", pady=(8, 12))

    def save() -> None:
        nonlocal result
        gateway_value = gateway.get().strip()
        pairing_value = pairing_code.get().strip()
        roots_value = [str(Path(value).expanduser().resolve()) for value in roots_list.get(0, "end") if str(value).strip()]
        if not gateway_value.startswith(("ws://", "wss://")):
            messagebox.showerror(APP_NAME, "Gateway URL must start with ws:// or wss://")
            return
        if not node_name.get().strip() or not node_id.get().strip():
            messagebox.showerror(APP_NAME, "Node name and Node ID are required.")
            return
        if not roots_value:
            messagebox.showerror(APP_NAME, "Add at least one allowed folder.")
            return
        result = {
            "gateway_ws_url": gateway_value.rstrip("/"),
            "node_name": node_name.get().strip(),
            "node_id": node_id.get().strip(),
            "pairing_code": pairing_value or None,
            "permission_level": permission.get(),
            "allowed_roots": roots_value,
        }
        _save_config(result)
        root.destroy()

    actions = ttk.Frame(frame)
    actions.pack(fill="x", side="bottom")
    ttk.Button(actions, text="Cancel", command=root.destroy).pack(side="right")
    ttk.Button(actions, text="Save and connect", command=save).pack(side="right", padx=(0, 8))
    root.mainloop()
    return result


def _apply_config(config: dict[str, object]) -> None:
    mapping = {
        "GWC_GATEWAY_WS": config.get("gateway_ws_url"),
        "GWC_NODE_ID": config.get("node_id"),
        "GWC_NODE_NAME": config.get("node_name"),
        "GWC_PAIRING_CODE": config.get("pairing_code"),
        "GWC_PERMISSION_LEVEL": config.get("permission_level"),
    }
    for key, value in mapping.items():
        if value is not None and str(value).strip():
            os.environ[key] = str(value).strip()
        elif key == "GWC_PAIRING_CODE":
            os.environ.pop(key, None)
    roots = config.get("allowed_roots")
    if isinstance(roots, list) and roots:
        os.environ["GWC_ALLOWED_ROOTS"] = os.pathsep.join(str(item) for item in roots)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GWC_NODE_STATE", str(CONFIG_DIR / "node-state.json"))


def _setup_logging() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)
    if not any(isinstance(handler, RotatingFileHandler) for handler in root_logger.handlers):
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def _load_saved_token(settings: NodeSettings) -> str | None:
    if settings.node_token:
        return settings.node_token
    try:
        data = json.loads(settings.state_file.read_text(encoding="utf-8"))
        return data.get("node_token")
    except (OSError, json.JSONDecodeError):
        return None


def _save_token(settings: NodeSettings, token: str) -> None:
    settings.state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.state_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"node_id": settings.node_id, "node_token": token}, indent=2), encoding="utf-8")
    temporary.replace(settings.state_file)


async def _serve_connection(settings: NodeSettings, executor: Executor) -> None:
    query = urlencode({"node_id": settings.node_id})
    uri = settings.gateway_ws_url + ("&" if "?" in settings.gateway_ws_url else "?") + query
    token = _load_saved_token(settings)
    async with websockets.connect(uri, ping_interval=20, ping_timeout=20, max_size=32 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "type": "hello",
            "node_id": settings.node_id,
            "name": settings.node_name,
            "node_token": token,
            "pairing_code": settings.pairing_code,
            "permission_level": settings.permission_level,
            "allowed_roots": [str(path) for path in settings.allowed_roots],
        }))
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if not welcome.get("ok"):
            raise RuntimeError(welcome.get("error") or "Gateway rejected node")
        if welcome.get("node_token"):
            _save_token(settings, welcome["node_token"])
            config = _load_config()
            if config.get("pairing_code"):
                config["pairing_code"] = None
                _save_config(config)
        server_config = welcome.get("config")
        if isinstance(server_config, dict):
            config = _load_config()
            changed = False
            for key in ("node_name", "permission_level"):
                value = server_config.get(key)
                if value is not None and config.get(key) != value:
                    config[key] = value
                    changed = True
            roots = server_config.get("allowed_roots")
            if isinstance(roots, list) and roots and config.get("allowed_roots") != roots:
                config["allowed_roots"] = roots
                changed = True
            if changed:
                _save_config(config)
                configured_roots = config.get("allowed_roots") or [str(path) for path in settings.allowed_roots]
                executor.allowed_roots = tuple(Path(item).expanduser().resolve() for item in configured_roots if str(item).strip())
                executor.policy = type(executor.policy)(str(config.get("permission_level") or settings.permission_level))
                log.info("Applied Lucas web configuration without reconnecting")
        log.info("Connected as %s (%s), permission=%s", settings.node_name, settings.node_id, settings.permission_level)
        send_lock = asyncio.Lock()
        request_tasks: set[asyncio.Task[None]] = set()

        async def send_json(payload: dict[str, object]) -> None:
            async with send_lock:
                await ws.send(json.dumps(payload, ensure_ascii=False))

        async def execute_request(request_id: object, method: str, params: dict) -> None:
            try:
                result = await executor.call(method, params)
                response = {"type": "response", "id": request_id, "ok": True, "result": result}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("Execution failed: %s", method)
                response = {"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            try:
                await send_json(response)
            except Exception:
                log.exception("Failed sending response for %s", method)

        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                except asyncio.TimeoutError:
                    await send_json({"type": "heartbeat", "time": time.time()})
                    continue
                message = json.loads(raw)
                if message.get("type") != "request":
                    continue
                request_id = message.get("id")
                method = message.get("method", "")
                params = message.get("params") or {}
                if method == "node.configure":
                    try:
                        config = _load_config()
                        name = str(params.get("node_name") or config.get("node_name") or settings.node_name).strip()
                        permission = str(params.get("permission_level") or config.get("permission_level") or "operate").strip().lower()
                        roots = [str(Path(item).expanduser().resolve()) for item in (params.get("allowed_roots") or config.get("allowed_roots") or []) if str(item).strip()]
                        if permission not in {"read", "operate", "admin"}:
                            raise ValueError("permission_level must be read, operate, or admin")
                        if not roots or any(not Path(item).is_dir() for item in roots):
                            raise ValueError("Every allowed folder must exist on this Windows PC")
                        config.update({"node_name": name, "permission_level": permission, "allowed_roots": roots})
                        _save_config(config)
                        executor.allowed_roots = tuple(Path(item).expanduser().resolve() for item in roots)
                        executor.policy = type(executor.policy)(permission)
                        response = {"type": "response", "id": request_id, "ok": True, "result": {"node_name": name, "permission_level": permission, "allowed_roots": roots}}
                        await send_json(response)
                        log.info("Applied Lucas web configuration without reconnecting")
                        continue
                    except RuntimeError:
                        raise
                    except Exception as exc:
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                        continue
                if method == "node.logs":
                    try:
                        limit = max(20, min(int(params.get("limit", 200)), 1000))
                        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:] if LOG_FILE.exists() else []
                        await send_json({"type": "response", "id": request_id, "ok": True, "result": {"lines": lines}})
                    except Exception as exc:
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    continue

                task = asyncio.create_task(execute_request(request_id, method, params), name=f"lucas:{method}:{request_id}")
                request_tasks.add(task)
                task.add_done_callback(request_tasks.discard)
        finally:
            if request_tasks:
                for task in request_tasks:
                    task.cancel()
                await asyncio.gather(*request_tasks, return_exceptions=True)


async def run_node() -> None:
    delay = 1.0
    while True:
        try:
            config = _load_config()
            _apply_config(config)
            settings = NodeSettings.from_env()
            executor = Executor(settings.allowed_roots, settings.permission_level)
            await _serve_connection(settings, executor)
            delay = 1.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Disconnected: %s; retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


def main() -> None:
    parser = argparse.ArgumentParser(prog="lucas-node")
    parser.add_argument("--configure", action="store_true", help="Open the Lucas Node configuration window")
    args = parser.parse_args()
    _setup_logging()
    config = _load_config()
    if not config:
        settings = NodeSettings.from_env()
        config = {"gateway_ws_url": settings.gateway_ws_url, "node_id": settings.node_id, "node_name": settings.node_name, "pairing_code": settings.pairing_code, "permission_level": settings.permission_level, "allowed_roots": [str(path) for path in settings.allowed_roots]}
        _save_config(config)
    if args.configure:
        log.info("Local setup UI is disabled. Manage this node from the Lucas web dashboard.")
    _apply_config(config)
    log.info("Lucas Node starting. config=%s log=%s", CONFIG_FILE, LOG_FILE)
    try:
        asyncio.run(run_node())
    except KeyboardInterrupt:
        log.info("Lucas Node stopped by user.")


if __name__ == "__main__":
    main()
