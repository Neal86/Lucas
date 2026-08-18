from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .bindings import BindingStore
from .config import GatewaySettings

settings = GatewaySettings.from_env()
bindings = BindingStore(settings.data_dir / "projects.json")


class BearerMiddleware:
    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if not self.token or scope["type"] != "http" or scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if headers.get("authorization") != f"Bearer {self.token}":
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


class NodeAuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        if not path.exists():
            path.write_text(json.dumps({"nodes": {}}, indent=2), encoding="utf-8")

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"nodes": {}}

    async def token_for(self, node_id: str) -> str | None:
        return self._read().get("nodes", {}).get(node_id, {}).get("token")

    async def save(self, node_id: str, name: str, token: str) -> None:
        async with self._lock:
            data = self._read()
            data.setdefault("nodes", {})[node_id] = {"name": name, "token": token, "updated_at": time.time()}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)


auth_store = NodeAuthStore(settings.data_dir / "nodes.json")
_pairings: dict[str, dict] = {}


@dataclass
class NodeConnection:
    node_id: str
    name: str
    permission_level: str
    websocket: WebSocket
    last_seen: float = field(default_factory=time.time)
    pending: dict[str, asyncio.Future] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class ControlLock:
    project_id: str
    expires_at: float


class NodeRegistry:
    def __init__(self) -> None:
        self.nodes: dict[str, NodeConnection] = {}
        self.control_locks: dict[str, ControlLock] = {}

    def list(self) -> list[dict]:
        now = time.time()
        out = []
        for node in self.nodes.values():
            lock = self.control_locks.get(node.node_id)
            if lock and lock.expires_at <= now:
                self.control_locks.pop(node.node_id, None)
                lock = None
            out.append({
                "node_id": node.node_id,
                "name": node.name,
                "permission_level": node.permission_level,
                "online": True,
                "last_seen": node.last_seen,
                "control_project": lock.project_id if lock else None,
                "control_expires_at": lock.expires_at if lock else None,
            })
        return out

    def acquire_control(self, node_id: str, project_id: str, ttl_seconds: int = 120) -> dict:
        if node_id not in self.nodes:
            raise RuntimeError(f"Node is offline: {node_id}")
        now = time.time()
        ttl_seconds = max(15, min(ttl_seconds, 1800))
        current = self.control_locks.get(node_id)
        if current and current.expires_at > now and current.project_id != project_id:
            raise RuntimeError(f"Node {node_id} is controlled by project {current.project_id}")
        lock = ControlLock(project_id=project_id, expires_at=now + ttl_seconds)
        self.control_locks[node_id] = lock
        return {"node_id": node_id, "project_id": project_id, "expires_at": lock.expires_at}

    def release_control(self, node_id: str, project_id: str) -> dict:
        current = self.control_locks.get(node_id)
        if current and current.project_id == project_id:
            self.control_locks.pop(node_id, None)
            return {"released": True, "node_id": node_id, "project_id": project_id}
        return {"released": False, "node_id": node_id, "project_id": project_id}

    def control_status(self, node_id: str) -> dict:
        now = time.time()
        current = self.control_locks.get(node_id)
        if current and current.expires_at <= now:
            self.control_locks.pop(node_id, None)
            current = None
        return {
            "node_id": node_id,
            "project_id": current.project_id if current else None,
            "expires_at": current.expires_at if current else None,
        }

    async def rpc(self, node_id: str, method: str, params: dict, timeout: float = 180.0) -> Any:
        node = self.nodes.get(node_id)
        if not node:
            raise RuntimeError(f"Node is offline: {node_id}")
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        node.pending[request_id] = future
        try:
            async with node.send_lock:
                await node.websocket.send_json({"type": "request", "id": request_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            node.pending.pop(request_id, None)

    def resolve(self, node_id: str, message: dict) -> None:
        node = self.nodes.get(node_id)
        if not node:
            return
        node.last_seen = time.time()
        future = node.pending.get(message.get("id", ""))
        if not future or future.done():
            return
        if message.get("ok"):
            future.set_result(message.get("result"))
        else:
            future.set_exception(RuntimeError(message.get("error") or "Node execution failed"))


registry = NodeRegistry()


def _binding(project_id: str):
    binding = bindings.get(project_id)
    if not binding:
        raise RuntimeError(f"Project is not bound: {project_id}")
    return binding


async def _project_rpc(project_id: str, method: str, params: dict | None = None, include_workspace: bool = True):
    binding = _binding(project_id)
    payload = dict(params or {})
    if include_workspace:
        payload["workspace"] = binding.workspace
    return await registry.rpc(binding.node_id, method, payload)


def _desktop_lock(project_id: str, ttl_seconds: int = 120) -> None:
    binding = _binding(project_id)
    registry.acquire_control(binding.node_id, project_id, ttl_seconds)


mcp = FastMCP(
    "GPT Windows Connector",
    instructions="Remote Windows execution layer. Project bindings are the only workspace context: project_id -> Windows node + workspace. No conversation binding is used.",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def project_bind(project_id: str, node_id: str, workspace: str, name: str | None = None) -> dict:
    """Bind one AI project to one online Windows node and workspace folder."""
    if node_id not in registry.nodes:
        raise RuntimeError(f"Node is offline: {node_id}")
    verified = await registry.rpc(node_id, "workspace.info", {"workspace": workspace})
    normalized = str(verified["path"])
    return bindings.set(project_id, node_id, normalized, name).__dict__


@mcp.tool()
def project_get(project_id: str) -> dict | None:
    """Get the Windows node/workspace bound to a project."""
    item = bindings.get(project_id)
    return item.__dict__ if item else None


@mcp.tool()
def project_list() -> list[dict]:
    """List all project bindings."""
    return [item.__dict__ for item in bindings.list()]


@mcp.tool()
def project_unbind(project_id: str) -> dict:
    """Remove a project binding."""
    item = bindings.get(project_id)
    if item:
        registry.release_control(item.node_id, project_id)
    return {"removed": bindings.remove(project_id)}


@mcp.tool()
def node_pair(node_id: str, name: str | None = None, ttl_seconds: int = 600) -> dict:
    """Create a one-time pairing code for a Windows node."""
    ttl_seconds = max(60, min(ttl_seconds, 3600))
    code = f"{secrets.randbelow(1_000_000):06d}"
    _pairings[code] = {"node_id": node_id, "name": name or node_id, "expires": time.time() + ttl_seconds}
    return {"node_id": node_id, "pairing_code": code, "expires_in": ttl_seconds}


@mcp.tool()
def node_list() -> list[dict]:
    """List currently connected Windows nodes."""
    return registry.list()


@mcp.tool()
def control_acquire(project_id: str, ttl_seconds: int = 120) -> dict:
    """Reserve the project's Windows node for browser/desktop interaction."""
    binding = _binding(project_id)
    return registry.acquire_control(binding.node_id, project_id, ttl_seconds)


@mcp.tool()
def control_release(project_id: str) -> dict:
    """Release the project's browser/desktop control reservation."""
    binding = _binding(project_id)
    return registry.release_control(binding.node_id, project_id)


@mcp.tool()
def control_status(project_id: str) -> dict:
    """Return browser/desktop control ownership for the project's node."""
    binding = _binding(project_id)
    return registry.control_status(binding.node_id)


@mcp.tool()
async def workspace_info(project_id: str) -> dict:
    """Return the bound workspace information from its Windows node."""
    return await _project_rpc(project_id, "workspace.info")


@mcp.tool()
async def files_tool(project_id: str, action: str, params: dict | None = None) -> object:
    """File actions: list, read, write, patch, search, stat, mkdir, move, copy, delete."""
    allowed = {"list", "read", "write", "patch", "search", "stat", "mkdir", "move", "copy", "delete"}
    if action not in allowed:
        raise ValueError(f"Unsupported files action: {action}")
    return await _project_rpc(project_id, f"files.{action}", params)


@mcp.tool()
async def shell_run(project_id: str, command: str, timeout: int = 120, shell_type: str = "powershell") -> dict:
    """Run a PowerShell or CMD command in the project's workspace."""
    return await _project_rpc(project_id, "shell.run", {"command": command, "timeout": timeout, "shell_type": shell_type})


@mcp.tool()
async def process_tool(project_id: str, action: str, params: dict | None = None) -> dict:
    """Long-running process actions: start, poll, stop, list."""
    if action not in {"start", "poll", "stop", "list"}:
        raise ValueError(f"Unsupported process action: {action}")
    return await _project_rpc(project_id, f"process.{action}", params, include_workspace=True)


@mcp.tool()
async def git_tool(project_id: str, action: str, params: dict | None = None) -> dict:
    """Git actions: status, diff, log, branch, branch_create, branch_switch, add, commit, pull, push, show."""
    allowed = {"status", "diff", "log", "branch", "branch_create", "branch_switch", "add", "commit", "pull", "push", "show"}
    if action not in allowed:
        raise ValueError(f"Unsupported git action: {action}")
    return await _project_rpc(project_id, f"git.{action}", params)


@mcp.tool()
async def browser_tool(project_id: str, action: str, params: dict | None = None) -> object:
    """Playwright actions on the project's Windows node."""
    allowed = {"connect_cdp", "launch_persistent", "pages", "new_page", "navigate", "inspect", "click", "type", "select", "upload", "screenshot", "close"}
    if action not in allowed:
        raise ValueError(f"Unsupported browser action: {action}")
    if action not in {"pages", "inspect", "screenshot"}:
        _desktop_lock(project_id)
    return await _project_rpc(project_id, f"browser.{action}", params, include_workspace=True)


@mcp.tool()
async def computer_tool(project_id: str, action: str, params: dict | None = None) -> object:
    """Windows desktop actions on the project's node."""
    allowed = {"info", "processes", "launch", "windows", "activate", "screenshot", "click", "move", "drag", "type", "hotkey", "press", "scroll", "clipboard_get", "clipboard_set"}
    if action not in allowed:
        raise ValueError(f"Unsupported computer action: {action}")
    if action not in {"info", "processes", "windows", "screenshot", "clipboard_get"}:
        _desktop_lock(project_id)
    return await _project_rpc(project_id, f"computer.{action}", params, include_workspace=True)


async def health(_: Request):
    return JSONResponse({"ok": True, "nodes": len(registry.nodes), "projects": len(bindings.list())})


async def node_websocket(websocket: WebSocket):
    await websocket.accept()
    node_id = None
    try:
        hello = await asyncio.wait_for(websocket.receive_json(), timeout=15)
        if hello.get("type") != "hello":
            await websocket.close(code=4400)
            return
        node_id = str(hello.get("node_id", "")).strip()
        if not node_id:
            await websocket.close(code=4400)
            return
        name = str(hello.get("name") or node_id)
        permission_level = str(hello.get("permission_level") or "operate")
        supplied_token = hello.get("node_token")
        pairing_code = hello.get("pairing_code")
        expected_token = await auth_store.token_for(node_id)
        authorized = bool(expected_token and supplied_token and secrets.compare_digest(str(expected_token), str(supplied_token)))
        issued_token = None
        if not authorized and pairing_code:
            pairing = _pairings.get(str(pairing_code))
            if pairing and pairing["node_id"] == node_id and pairing["expires"] >= time.time():
                issued_token = secrets.token_urlsafe(32)
                await auth_store.save(node_id, name, issued_token)
                _pairings.pop(str(pairing_code), None)
                authorized = True
        if not authorized:
            await websocket.send_json({"type": "welcome", "ok": False, "error": "pairing or node token required"})
            await websocket.close(code=4401)
            return
        connection = NodeConnection(node_id=node_id, name=name, permission_level=permission_level, websocket=websocket)
        old = registry.nodes.get(node_id)
        if old:
            with contextlib.suppress(Exception):
                await old.websocket.close(code=4001)
        registry.nodes[node_id] = connection
        await websocket.send_json({"type": "welcome", "ok": True, "node_token": issued_token})
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "heartbeat":
                connection.last_seen = time.time()
                await websocket.send_json({"type": "heartbeat_ack", "time": time.time()})
            elif message.get("type") == "response":
                registry.resolve(node_id, message)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if node_id and registry.nodes.get(node_id) and registry.nodes[node_id].websocket is websocket:
            connection = registry.nodes.pop(node_id)
            for future in connection.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError(f"Node disconnected: {node_id}"))


mcp_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[Route("/health", health, methods=["GET"]), WebSocketRoute("/ws/node", node_websocket), Mount("/", app=mcp_app)],
    lifespan=lifespan,
)
app = BearerMiddleware(app, settings.admin_token)


def main() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
