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
DEVICE_ID_FILE = CONFIG_DIR / "node-device-id.txt"
local_task_runs = TaskRunStore(TASK_RUNS_FILE)
local_access = LocalAccessStore(ACCESS_FILE)
DEFAULT_GATEWAY = "wss://lucasmcp.com/ws/node"
log = logging.getLogger("lucas.node")


class NodeSessionDisconnected(ConnectionError):
    """A previously established Gateway session was lost. Retry direct immediately."""


def _disconnect_reason(exc: Exception) -> str:
    text = str(exc).lower()
    if "keepalive ping timeout" in text or "ping timeout" in text:
        return "ping_timeout"
    if "1012" in text or "service restart" in text:
        return "gateway_restart"
    if "1006" in text or "connection closed" in text or "closed" in text:
        return "connection_closed"
    if "timed out" in text or "timeout" in text:
        return "network_timeout"
    return type(exc).__name__


def _is_gateway_restart_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "1012" in text
        or "service restart" in text
        or "http 502" in text
        or "http 503" in text
        or "bad gateway" in text
        or "service unavailable" in text
    )


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


def _lock_device_id(config: dict[str, object]) -> dict[str, object]:
    """Persist the first production Node ID forever; updates may never rotate it."""
    configured = str(config.get("node_id") or "").strip()
    locked = ""
    try:
        locked = DEVICE_ID_FILE.read_text(encoding="utf-8-sig").strip()
    except OSError:
        pass
    if locked:
        if configured != locked:
            config["node_id"] = locked
            _save_config(config)
            log.warning("Restored permanent Node ID %s (ignored transient value %s)", locked, configured or "<empty>")
        return config
    if not configured:
        configured = _default_node_id()
        config["node_id"] = configured
        _save_config(config)
    try:
        DEVICE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEVICE_ID_FILE.write_text(configured, encoding="utf-8")
    except OSError as exc:
        log.warning("Could not persist permanent Node ID lock: %s", exc)
    return config


def _load_config() -> dict[str, object]:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return {}
        gateway = str(data.get("gateway_ws_url") or "").strip().rstrip("/")
        # Older local-development builds persisted localhost as the Gateway. Once
        # installed on another PC that makes the Node connect back to itself forever.
        # Heal those stale configs automatically; users never need to edit JSON.
        if gateway in {
            "ws://127.0.0.1:8787/ws/node",
            "ws://localhost:8787/ws/node",
            "wss://127.0.0.1:8787/ws/node",
            "wss://localhost:8787/ws/node",
        }:
            data["gateway_ws_url"] = DEFAULT_GATEWAY
            _save_config(data)
            log.warning("Migrated stale local Gateway %s -> %s", gateway, DEFAULT_GATEWAY)
        return _lock_device_id(data)
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


from .node_approval import notify_access_request as _notify_access_request


async def _serve_connection(
    settings: NodeSettings,
    gateway_ws_url: str | None = None,
    *,
    force_ipv4: bool = False,
    proxy_mode: bool | None = None,
) -> None:
    base_gateway = (gateway_ws_url or settings.gateway_ws_url).rstrip("/")
    query = urlencode({"node_id": settings.node_id})
    uri = base_gateway + ("&" if "?" in base_gateway else "?") + query
    token = _load_saved_token(settings)
    # Do not cache the Connection Code for the lifetime of the WebSocket. The
    # settings UI can rotate it while the Node remains connected, and existing
    # authorized users must stay connected. New access requests always validate
    # against the current on-disk config instead.
    _ensure_connection_code(_load_config())
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
        }))
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if not welcome.get("ok"):
            error = str(welcome.get("error") or "Gateway rejected node")
            if error == "invalid node device token":
                raise RuntimeError("device credential mismatch; permanent Node ID preserved")
            raise RuntimeError(error)
        # Security policy is authoritative on the Windows computer. The gateway may
        # report status, but it is never allowed to overwrite local permissions.
        log.info("Connected as %s (%s)", settings.node_name, settings.node_id)
        _write_status("Online")
        def current_node_roots() -> list[str]:
            config=_load_config()
            configured=config.get("allowed_roots")
            if isinstance(configured,list) and configured:
                return [str(Path(str(path)).expanduser().resolve()) for path in configured if str(path).strip()]
            return [str(path) for path in settings.allowed_roots]

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
            saved = local_access.effective(user_id, current_node_roots())
            return dict(saved) if saved else None

        async def request_access(actor: dict[str, object], supplied_connection_code: str) -> dict[str, object]:
            user_id = str(actor.get("user_id") or "").strip()
            if not user_id:
                return {"authorized": False, "error": "missing user identity"}
            current = await asyncio.to_thread(effective_access, actor)
            if current:
                return {"authorized": True, **current}
            now = time.time()
            attempts = [stamp for stamp in access_attempts.get(user_id, []) if now - stamp < 60]
            access_attempts[user_id] = attempts
            if len(attempts) >= 5:
                log.warning("Local connection-code rate limit user=%s", user_id)
                return {"authorized": False, "error": "too many connection attempts"}
            current_connection_code = _ensure_connection_code(_load_config())
            if not supplied_connection_code or not secrets.compare_digest(current_connection_code, supplied_connection_code.strip()):
                attempts.append(now)
                access_attempts[user_id] = attempts
                log.warning("Invalid connection code for access request user=%s", user_id)
                return {"authorized": False, "error": "invalid connection code"}
            access_attempts.pop(user_id, None)
            pending = local_access.add_pending(actor)
            asyncio.create_task(asyncio.to_thread(_notify_access_request, actor))
            log.info("Local access request pending approval for user %s", user_id)
            return {"authorized": False, "pending": True, "decision": "pending", "user_id": user_id, "requested_at": pending.get("requested_at")}

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

        def prepare_executor(access: dict[str, object]) -> tuple[str, Executor]:
            # Path.resolve() can block on cloud/network drives. Keep all filesystem-
            # touching access preparation off the WebSocket asyncio event loop.
            user_id = str(access.get("user_id") or "")
            roots = tuple(Path(str(item)).resolve() for item in access.get("allowed_roots") or [])
            user_config = _load_config()
            node_security = user_config.get("security") if isinstance(user_config.get("security"), dict) else {}
            account_security = access.get("security") if isinstance(access.get("security"), dict) else preset_security(str(access.get("preset") or "request_approval"))
            user_config["security"] = intersect_security(dict(node_security), dict(account_security))
            return user_id, Executor(roots, user_config)

        async def execute_request(request_id: object, method: str, params: dict, actor: dict[str, object]) -> None:
            wall_started=time.time(); status="success"; error_type=None
            try:
                access = await asyncio.to_thread(effective_access, actor)
                if not access:
                    raise PermissionError("This Lucas user has not been approved on the Windows Node")
                user_id, active_executor = await asyncio.to_thread(prepare_executor, access)
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
                    access = await asyncio.to_thread(effective_access, actor)
                    await send_json({"type": "response", "id": request_id, "ok": True, "result": ({"authorized": True, **access} if access else {"authorized": False})})
                    continue
                if method == "node.configure":
                    await send_json({
                        "type": "response", "id": request_id, "ok": False,
                        "error": "PermissionError: Security settings are local-only. Open Lucas Settings from the Windows tray.",
                    })
                    continue
                if method == "node.logs":
                    log_access = await asyncio.to_thread(effective_access, actor)
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reason = _disconnect_reason(exc)
            log.warning("Node session disconnected reason=%s error=%s", reason, exc)
            raise NodeSessionDisconnected(f"{reason}: {exc}") from exc
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
            primary = settings.gateway_ws_url.rstrip("/") or DEFAULT_GATEWAY
            # Keep the reconnect path deliberately small: primary direct first, then
            # the Windows system proxy only for genuine client/network failures. The
            # retired autozon.xyz fallback and the duplicate direct-ipv4 pass made a
            # short Gateway restart look like minutes of reconnect churn.
            strategies = [
                ("direct", False, None),
                ("system-proxy", False, True),
            ]
            last_error: Exception | None = None
            retry_primary = False
            for strategy_name, force_ipv4, proxy_mode in strategies:
                try:
                    detail = f"Connecting to {primary} via {strategy_name}"
                    _write_status("Connecting", detail)
                    log.info("Gateway attempt %s via %s", primary, strategy_name)
                    await _serve_connection(
                        settings,
                        primary,
                        force_ipv4=force_ipv4,
                        proxy_mode=proxy_mode,
                    )
                    delay = 1.0
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as candidate_error:
                    last_error = candidate_error
                    log.warning(
                        "Gateway connection failed %s via %s: %s",
                        primary,
                        strategy_name,
                        candidate_error,
                    )
                    if isinstance(candidate_error, NodeSessionDisconnected):
                        detail = f"Session lost ({candidate_error}); requesting fresh Node process"
                        log.info(detail)
                        _write_status("Reconnecting", detail)
                        raise SystemExit(75)
                    if _is_gateway_restart_error(candidate_error):
                        detail = "Gateway restarting; requesting fresh Node process"
                        log.info(detail)
                        _write_status("Reconnecting", detail)
                        raise SystemExit(75)
                    _write_status(
                        "Reconnecting",
                        f"{candidate_error}; failed {primary} via {strategy_name}",
                    )
            if retry_primary:
                delay = 1.0
                continue
            if last_error is not None:
                raise last_error
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reason = _disconnect_reason(exc)
            log.warning("Disconnected reason=%s error=%s; requesting fresh Node process", reason, exc)
            _write_status("Reconnecting", f"{reason}: {exc}")
            raise SystemExit(75)


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
