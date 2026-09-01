from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import socket
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlencode

import websockets

from .access_control import LocalAccessStore, clamp_roots, intersect_security, normalize_preset, preset_security
from .config import NodeSettings
from .executor import Executor
from .i18n import tr
from .settings_ui import configure_gui as _configure_gui
from .task_runs import TaskRunStore

APP_NAME = "Lucas"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"
LOG_FILE = CONFIG_DIR / "lucas-node.log"
STATUS_FILE = CONFIG_DIR / "node-status.json"
TASK_RUNS_FILE = CONFIG_DIR / "task-runs.db"
ACCESS_FILE = CONFIG_DIR / "node-access.json"
DEVICE_CREDENTIAL_FILE = CONFIG_DIR / "node-device-credential.json"
local_task_runs = TaskRunStore(TASK_RUNS_FILE)
local_access = LocalAccessStore(ACCESS_FILE)
DEFAULT_GATEWAY = "wss://lucasmcp.com/ws/node"
FALLBACK_GATEWAY = "wss://lucas.autozon.xyz/ws/node"
log = logging.getLogger("lucas.node")


def _acquire_node_mutex() -> object | None:
    if sys.platform != "win32":
        return object()
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\LucasNodeSingleInstance")
        if not handle:
            return None
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        log.exception("Could not create node single-instance mutex")
        return object()


def _default_node_id() -> str:
    return f"lucas-{uuid.uuid4().hex}"


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


def _ensure_connection_code(config: dict[str, object]) -> str:
    code = str(config.get("connection_code") or "").strip()
    if len(code) == 8 and code.isdigit():
        return code
    code = f"{secrets.randbelow(100_000_000):08d}"
    config["connection_code"] = code
    _save_config(config)
    return code


def _write_status(status: str, detail: str = "") -> None:
    """Best-effort status publishing; UI file-lock races must never drop WebSocket."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_FILE.with_name(f"{STATUS_FILE.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps({"status": status, "detail": detail, "time": time.time(), "pid": os.getpid(), "source": "node"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for attempt in range(5):
            try:
                temporary.replace(STATUS_FILE)
                return
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    except OSError as exc:
        log.debug("Could not update status file: %s", exc)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass




def _apply_config(config: dict[str, object]) -> None:
    mapping = {
        "GWC_GATEWAY_WS": config.get("gateway_ws_url"),
        "GWC_NODE_ID": config.get("node_id"),
        "GWC_NODE_NAME": config.get("node_name"),
    }
    for key, value in mapping.items():
        if value is not None and str(value).strip():
            os.environ[key] = str(value).strip()
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


def _read_token_file(path: Path, node_id: str) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        stored_node_id = str(data.get("node_id") or "").strip()
        token = str(data.get("node_token") or "").strip()
        if token and (not stored_node_id or stored_node_id == node_id):
            return token
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def _load_saved_token(settings: NodeSettings) -> str:
    if settings.node_token:
        return settings.node_token
    candidates = [
        settings.state_file,
        DEVICE_CREDENTIAL_FILE,
        settings.state_file.with_name(settings.state_file.name + ".pre-update"),
        settings.state_file.with_name(settings.state_file.name + ".bak"),
    ]
    for path in candidates:
        token = _read_token_file(path, settings.node_id)
        if token:
            # Heal all credential stores so future updates cannot silently create a
            # second token for the same Node ID.
            _save_token(settings, token)
            return token
    token = secrets.token_urlsafe(32)
    _save_token(settings, token)
    log.warning("No existing device credential found for %s; generated a new credential", settings.node_id)
    return token


def _write_token_file(path: Path, node_id: str, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"node_id": node_id, "node_token": token}, indent=2), encoding="utf-8")
    temporary.replace(path)


def _save_token(settings: NodeSettings, token: str) -> None:
    _write_token_file(settings.state_file, settings.node_id, token)
    _write_token_file(DEVICE_CREDENTIAL_FILE, settings.node_id, token)


def _grants_full_access(access: dict[str, object]) -> bool:
    preset = normalize_preset(str(access.get("preset") or "request_approval"))
    security = access.get("security") if isinstance(access.get("security"), dict) else preset_security(preset)
    full = preset_security("full_access")
    policy = security.get("approval_policy") if isinstance(security.get("approval_policy"), dict) else {}
    required = full.get("approval_policy") if isinstance(full.get("approval_policy"), dict) else {}
    domains = [str(value).strip() for value in (security.get("allowed_domains") or []) if str(value).strip()]
    return (
        all(str(policy.get(key) or "").lower() == "allow" for key in required)
        and str(security.get("network_external") or "").lower() == "allow"
        and str(security.get("network_lan") or "").lower() == "allow"
        and not bool(security.get("block_silent_network", True))
        and not domains
    )


def _prompt_access_request(actor: dict[str, object], node_roots: list[str]) -> dict[str, object]:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        return {"decision": "deny", "error": f"approval UI unavailable: {exc}"}

    result: dict[str, object] = {"decision": "deny"}
    root = tk.Tk()
    root.title(tr("Lucas 访问请求", "Lucas Access Request"))
    root.geometry("580x540")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    frame = tk.Frame(root, padx=24, pady=22)
    frame.pack(fill="both", expand=True)
    display = str(actor.get("name") or actor.get("email") or actor.get("user_id") or tr("未知用户", "Unknown user"))
    email = str(actor.get("email") or "")
    tk.Label(frame, text=tr("新的 Lucas 用户请求访问此电脑", "A Lucas user is requesting access to this computer"), font=("Segoe UI", 15, "bold")).pack(anchor="w")
    tk.Label(frame, text=display, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(18, 2))
    if email and email != display:
        tk.Label(frame, text=email, font=("Segoe UI", 9), fg="#666666").pack(anchor="w")
    tk.Label(frame, text=tr("连接码已验证。请选择一个快捷权限模式；详细权限可以稍后在 Lucas 设置 → 用户与权限 中修改。", "The connection code is verified. Choose a quick access mode; detailed permissions can be changed later in Lucas Settings → Users & Permissions."), font=("Segoe UI", 9), fg="#555555", wraplength=520, justify="left").pack(anchor="w", pady=(10, 18))

    tk.Label(frame, text=tr("快捷权限", "Quick access mode"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
    preset_display = tk.StringVar(value=tr("请求批准（Recommended）", "Ask for approval (Recommended)"))
    preset_values = [tr("请求批准（Recommended）", "Ask for approval (Recommended)"), tr("帮我批准", "Auto-approve safe actions"), tr("完全访问权限", "Full Access")]
    ttk.Combobox(frame, textvariable=preset_display, values=preset_values, state="readonly", width=34).pack(anchor="w", pady=(5, 14))

    tk.Label(frame, text=tr("允许访问的文件夹", "Allowed folders"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
    folders = tk.Listbox(frame, selectmode="multiple", height=min(max(len(node_roots), 4), 9), width=72)
    folders.pack(fill="x", pady=(5, 8))
    for index, path in enumerate(node_roots):
        folders.insert("end", path)
        folders.selection_set(index)
    tk.Label(frame, text=tr("该账号只能访问这里选择的文件夹；Windows UAC 仍然是最终系统权限边界。", "This account can access only the selected folders; Windows UAC remains the final system privilege boundary."), font=("Segoe UI", 8), fg="#777777", wraplength=520, justify="left").pack(anchor="w")

    actions = tk.Frame(frame)
    actions.pack(side="bottom", fill="x", pady=(24, 0))

    def finish(decision: str) -> None:
        selected = [node_roots[i] for i in folders.curselection()]
        preset_map = {preset_values[0]: "request_approval", preset_values[1]: "auto_approve", preset_values[2]: "full_access"}
        result.update({"decision": decision, "preset": preset_map.get(preset_display.get(), "request_approval"), "allowed_roots": selected})
        root.destroy()

    tk.Button(actions, text=tr("拒绝", "Deny"), command=lambda: finish("deny"), padx=14, pady=7).pack(side="right")
    tk.Button(actions, text=tr("允许一次", "Allow once"), command=lambda: finish("once"), padx=14, pady=7).pack(side="right", padx=(0, 8))
    tk.Button(actions, text=tr("长期允许", "Always allow"), command=lambda: finish("always"), padx=14, pady=7).pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", lambda: finish("deny"))
    root.mainloop()
    return result


async def _serve_connection(
    settings: NodeSettings,
    gateway_ws_url: str | None = None,
    *,
    force_ipv4: bool = False,
    proxy_mode: bool | None = True,
) -> None:
    base_gateway = (gateway_ws_url or settings.gateway_ws_url).rstrip("/")
    query = urlencode({"node_id": settings.node_id})
    uri = base_gateway + ("&" if "?" in base_gateway else "?") + query
    token = _load_saved_token(settings)
    connection_code = _ensure_connection_code(_load_config())
    connect_kwargs: dict[str, object] = {
        "ping_interval": 20,
        "ping_timeout": 20,
        "open_timeout": 12,
        "max_size": 32 * 1024 * 1024,
        "proxy": proxy_mode,
    }
    if force_ipv4:
        connect_kwargs["family"] = socket.AF_INET
    async with websockets.connect(uri, **connect_kwargs) as ws:
        await ws.send(json.dumps({
            "type": "hello",
            "node_id": settings.node_id,
            "name": settings.node_name,
            "node_token": token,
            "allowed_roots": [str(path) for path in settings.allowed_roots],
            "authorized_user_ids": [str(item.get("user_id")) for item in local_access.list_users() if item.get("enabled", True) and item.get("user_id")],
            "credential_format": 2,
        }))
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if not welcome.get("ok"):
            raise RuntimeError(welcome.get("error") or "Gateway rejected node")
        # Security policy is authoritative on the Windows computer. The gateway may
        # report status, but it is never allowed to overwrite local permissions.
        log.info("Connected as %s (%s)", settings.node_name, settings.node_id)
        _write_status("Online")
        node_roots = [str(path) for path in settings.allowed_roots]
        session_grants: dict[str, dict[str, object]] = {}
        access_file_mtime = ACCESS_FILE.stat().st_mtime if ACCESS_FILE.exists() else 0.0
        access_attempts: dict[str, list[float]] = {}

        def effective_access(actor: dict[str, object]) -> dict[str, object] | None:
            user_id = str(actor.get("user_id") or "").strip()
            if not user_id:
                return None
            temporary = session_grants.get(user_id)
            if temporary:
                if float(temporary.get("expires_at") or 0) > time.time():
                    return dict(temporary)
                session_grants.pop(user_id, None)
            saved = local_access.effective(user_id, node_roots)
            return dict(saved) if saved else None

        async def request_access(actor: dict[str, object], supplied_connection_code: str) -> dict[str, object]:
            user_id = str(actor.get("user_id") or "").strip()
            if not user_id:
                return {"authorized": False, "error": "missing user identity"}
            current = effective_access(actor)
            if current:
                return {"authorized": True, **current}
            now = time.time()
            attempts = [stamp for stamp in access_attempts.get(user_id, []) if now - stamp < 60]
            access_attempts[user_id] = attempts
            if len(attempts) >= 5:
                log.warning("Local connection-code rate limit user=%s", user_id)
                return {"authorized": False, "error": "too many connection attempts"}
            if not supplied_connection_code or not secrets.compare_digest(connection_code, supplied_connection_code.strip()):
                attempts.append(now)
                access_attempts[user_id] = attempts
                log.warning("Invalid connection code for access request user=%s", user_id)
                return {"authorized": False, "error": "invalid connection code"}
            access_attempts.pop(user_id, None)
            decision = await asyncio.to_thread(_prompt_access_request, actor, node_roots)
            choice = str(decision.get("decision") or "deny")
            roots = clamp_roots([str(item) for item in decision.get("allowed_roots") or []], node_roots)
            preset = normalize_preset(str(decision.get("preset") or "request_approval"))
            security = preset_security(preset)
            if choice not in {"once", "always"} or not roots:
                log.info("Local access denied for user %s", user_id)
                return {"authorized": False, "decision": "deny"}
            grant = {"user_id": user_id, "email": str(actor.get("email") or ""), "name": str(actor.get("name") or ""), "preset": preset, "security": security, "allowed_roots": roots}
            if choice == "once":
                grant["grant_id"] = uuid.uuid4().hex
                grant["expires_at"] = time.time() + 3600
            if choice == "always":
                saved = local_access.upsert(actor, preset, roots, security=security)
                grant.update(saved)
            else:
                session_grants[user_id] = dict(grant)
            log.info("Local access approved for user %s preset=%s mode=%s", user_id, preset, choice)
            return {"authorized": True, "decision": choice, **grant}

        send_lock = asyncio.Lock()
        request_tasks: set[asyncio.Task[None]] = set()

        async def send_json(payload: dict[str, object]) -> None:
            async with send_lock:
                await ws.send(json.dumps(payload, ensure_ascii=False))

        async def sync_local_access_if_changed() -> None:
            nonlocal access_file_mtime
            current = ACCESS_FILE.stat().st_mtime if ACCESS_FILE.exists() else 0.0
            if current == access_file_mtime:
                return
            access_file_mtime = current
            user_ids = [str(item.get("user_id")) for item in local_access.list_users() if item.get("enabled", True) and item.get("user_id")]
            await send_json({"type": "access.sync", "authorized_user_ids": user_ids})

        async def execute_request(request_id: object, method: str, params: dict, actor: dict[str, object]) -> None:
            wall_started=time.time(); status="success"; error_type=None
            try:
                access = effective_access(actor)
                if not access:
                    raise PermissionError("This Lucas user has not been approved on the Windows Node")
                user_id = str(access.get("user_id") or "")
                roots = tuple(Path(str(item)).resolve() for item in access.get("allowed_roots") or [])
                user_config = _load_config()
                node_security = user_config.get("security") if isinstance(user_config.get("security"), dict) else {}
                account_security = access.get("security") if isinstance(access.get("security"), dict) else preset_security(str(access.get("preset") or "request_approval"))
                user_config["security"] = intersect_security(dict(node_security), dict(account_security))
                active_executor = Executor(roots, user_config)
                result = await active_executor.call(method, params)
                if user_id and user_id not in session_grants:
                    local_access.touch(user_id)
                response = {"type": "response", "id": request_id, "ok": True, "result": result}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status="failed"; error_type=type(exc).__name__
                log.exception("Execution failed: %s", method)
                response = {"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            wall_ended=time.time()
            try:
                workspace=str(params.get("workspace") or "")
                local_task_runs.record_operation(owner_id="local",node_id=settings.node_id,action=method,target=workspace or None,started_at=wall_started,ended_at=wall_ended,status=status,details={"error_type":error_type} if error_type else {},context_key=workspace or "default")
            except Exception:
                log.exception("Could not record local Task Run")
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
                    await sync_local_access_if_changed()
                    _write_status("Online")
                    continue
                _write_status("Online")
                await sync_local_access_if_changed()
                message = json.loads(raw)
                if message.get("type") != "request":
                    continue
                request_id = message.get("id")
                method = message.get("method", "")
                params = message.get("params") or {}
                actor = message.get("actor") if isinstance(message.get("actor"), dict) else {}
                if method == "access.request":
                    try:
                        result = await request_access(actor, str(params.get("connection_code") or ""))
                        await send_json({"type": "response", "id": request_id, "ok": True, "result": result})
                    except Exception as exc:
                        log.exception("Access approval failed")
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    continue
                if method == "access.check":
                    access = effective_access(actor)
                    await send_json({"type": "response", "id": request_id, "ok": True, "result": ({"authorized": True, **access} if access else {"authorized": False})})
                    continue
                if method == "node.configure":
                    await send_json({
                        "type": "response", "id": request_id, "ok": False,
                        "error": "PermissionError: Security settings are local-only. Open Lucas Settings from the Windows tray.",
                    })
                    continue
                if method == "node.logs":
                    log_access = effective_access(actor)
                    if not log_access or not _grants_full_access(log_access):
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": "PermissionError: Full Access is required for Node logs"})
                        continue
                    try:
                        limit = max(20, min(int(params.get("limit", 200)), 1000))
                        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:] if LOG_FILE.exists() else []
                        await send_json({"type": "response", "id": request_id, "ok": True, "result": {"lines": lines}})
                    except Exception as exc:
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    continue

                task = asyncio.create_task(execute_request(request_id, method, params, actor), name=f"lucas:{method}:{request_id}")
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
            primary = settings.gateway_ws_url.rstrip("/")
            candidates = [primary]
            aliases = {DEFAULT_GATEWAY.rstrip("/"), FALLBACK_GATEWAY.rstrip("/")}
            if primary in aliases:
                alternate = FALLBACK_GATEWAY.rstrip("/") if primary == DEFAULT_GATEWAY.rstrip("/") else DEFAULT_GATEWAY.rstrip("/")
                if alternate not in candidates:
                    candidates.append(alternate)
            strategies = [
                ("auto", False, True),
                ("ipv4", True, True),
                ("direct-ipv4", True, None),
            ]
            last_error: Exception | None = None
            connected = False
            for candidate_index, candidate in enumerate(candidates):
                if candidate_index:
                    log.warning("Primary Gateway unavailable; trying fallback %s", candidate)
                for strategy_name, force_ipv4, proxy_mode in strategies:
                    try:
                        detail = f"Connecting to {candidate} via {strategy_name}"
                        _write_status("Connecting", detail)
                        log.info("Gateway attempt %s via %s", candidate, strategy_name)
                        await _serve_connection(
                            settings,
                            candidate,
                            force_ipv4=force_ipv4,
                            proxy_mode=proxy_mode,
                        )
                        delay = 1.0
                        connected = True
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception as candidate_error:
                        last_error = candidate_error
                        log.warning(
                            "Gateway connection failed %s via %s: %s",
                            candidate,
                            strategy_name,
                            candidate_error,
                        )
                        _write_status(
                            "Reconnecting",
                            f"{candidate_error}; failed {candidate} via {strategy_name}",
                        )
                if connected:
                    break
            if not connected:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("No Gateway connection strategy succeeded")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Disconnected: %s; retrying in %.1fs", exc, delay)
            _write_status("Reconnecting", str(exc))
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
        config = {"gateway_ws_url": settings.gateway_ws_url, "node_id": settings.node_id, "node_name": settings.node_name, "allowed_roots": [str(path) for path in settings.allowed_roots]}
        _save_config(config)
    _ensure_connection_code(config)
    if args.configure:
        updated = _configure_gui(config)
        if updated is not None:
            log.info("Saved local Lucas security settings")
        return
    mutex = _acquire_node_mutex()
    if mutex is None:
        log.info("Another Lucas Node instance is already running; exiting duplicate process")
        return
    _apply_config(config)
    log.info("Lucas Node starting. config=%s log=%s", CONFIG_FILE, LOG_FILE)
    try:
        asyncio.run(run_node())
    except KeyboardInterrupt:
        _write_status("Offline", "Stopped by user")
        log.info("Lucas Node stopped by user.")


if __name__ == "__main__":
    main()
