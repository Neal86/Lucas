from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .auth import (
    AuthStore,
    current_user,
    google_authorize_url,
    google_exchange_code,
    reset_current_user,
    set_current_user,
)
from .bindings import BindingStore
from .config import GatewaySettings
from .oauth import OAuthProvider

settings = GatewaySettings.from_env()
db_path = settings.data_dir / "gateway.db"
auth = AuthStore(db_path, settings.jwt_secret, settings.jwt_ttl_seconds)
bindings = BindingStore(db_path)
oauth = OAuthProvider(db_path, auth, settings.public_base_url)


class AuthMiddleware:
    PUBLIC_PATHS = {
        "/health",
        "/auth/register",
        "/auth/login",
        "/auth/google/start",
        "/auth/google/callback",
    }

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or path in self.PUBLIC_PATHS or path.startswith("/oauth/") or path.startswith("/.well-known/"):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        token = None
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if not token:
            token = request.cookies.get("gwc_access_token")
        try:
            user = auth.verify_token(token or "")
        except Exception:
            headers = {}
            if path.startswith("/mcp"):
                headers["WWW-Authenticate"] = f'Bearer resource_metadata="{settings.public_base_url}/.well-known/oauth-protected-resource", scope="lucas"'
            await JSONResponse({"error": "authentication_required"}, status_code=401, headers=headers)(scope, receive, send)
            return
        ctx = set_current_user(user)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_user(ctx)


class NodeAuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    token TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(nodes)").fetchall()}
            if "permission_level" not in columns:
                db.execute("ALTER TABLE nodes ADD COLUMN permission_level TEXT NOT NULL DEFAULT 'operate'")
            if "allowed_roots" not in columns:
                db.execute("ALTER TABLE nodes ADD COLUMN allowed_roots TEXT NOT NULL DEFAULT '[]'")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    async def record_for(self, node_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    async def save(self, node_id: str, owner_user_id: str, name: str, token: str, permission_level: str = "operate", allowed_roots: list[str] | None = None) -> None:
        roots_json = json.dumps(allowed_roots or [])
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO nodes(node_id,owner_user_id,name,token,updated_at,permission_level,allowed_roots) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(node_id) DO UPDATE SET owner_user_id=excluded.owner_user_id,name=excluded.name,token=excluded.token,updated_at=excluded.updated_at,permission_level=excluded.permission_level,allowed_roots=excluded.allowed_roots
                """,
                (node_id, owner_user_id, name, token, time.time(), permission_level, roots_json),
            )

    async def update_config(self, node_id: str, owner_user_id: str, name: str, permission_level: str, allowed_roots: list[str]) -> dict:
        with self._connect() as db:
            cur = db.execute("UPDATE nodes SET name=?,permission_level=?,allowed_roots=?,updated_at=? WHERE node_id=? AND owner_user_id=?", (name, permission_level, json.dumps(allowed_roots), time.time(), node_id, owner_user_id))
            if cur.rowcount != 1:
                raise PermissionError("Node not found or not owned by this account")
        return await self.record_for(node_id)

    async def delete(self, node_id: str, owner_user_id: str) -> bool:
        with self._connect() as db:
            cur = db.execute("DELETE FROM nodes WHERE node_id=? AND owner_user_id=?", (node_id, owner_user_id))
            return cur.rowcount == 1


auth_store = NodeAuthStore(db_path)
_pairings: dict[str, dict] = {}


@dataclass
class NodeConnection:
    node_id: str
    owner_user_id: str
    name: str
    permission_level: str
    allowed_roots: list[str]
    websocket: WebSocket
    last_seen: float = field(default_factory=time.time)
    pending: dict[str, asyncio.Future] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class ControlLock:
    owner_user_id: str
    project_id: str
    expires_at: float


class NodeRegistry:
    def __init__(self) -> None:
        self.nodes: dict[str, NodeConnection] = {}
        self.control_locks: dict[str, ControlLock] = {}

    def list(self, user_id: str) -> list[dict]:
        now = time.time()
        out = []
        for node in self.nodes.values():
            if node.owner_user_id != user_id:
                continue
            lock = self.control_locks.get(node.node_id)
            if lock and lock.expires_at <= now:
                self.control_locks.pop(node.node_id, None)
                lock = None
            out.append({
                "node_id": node.node_id,
                "name": node.name,
                "permission_level": node.permission_level,
                "allowed_roots": node.allowed_roots,
                "online": True,
                "last_seen": node.last_seen,
                "control_project": lock.project_id if lock else None,
                "control_expires_at": lock.expires_at if lock else None,
            })
        return out

    def require_owned(self, node_id: str, user_id: str) -> NodeConnection:
        node = self.nodes.get(node_id)
        if not node:
            raise RuntimeError(f"Node is offline: {node_id}")
        if node.owner_user_id != user_id:
            raise PermissionError("Node does not belong to the authenticated user")
        return node

    def acquire_control(self, node_id: str, user_id: str, project_id: str, ttl_seconds: int = 120) -> dict:
        self.require_owned(node_id, user_id)
        now = time.time()
        ttl_seconds = max(15, min(ttl_seconds, 1800))
        current = self.control_locks.get(node_id)
        if current and current.expires_at > now and (current.owner_user_id != user_id or current.project_id != project_id):
            raise RuntimeError(f"Node {node_id} is controlled by another project")
        lock = ControlLock(owner_user_id=user_id, project_id=project_id, expires_at=now + ttl_seconds)
        self.control_locks[node_id] = lock
        return {"node_id": node_id, "project_id": project_id, "expires_at": lock.expires_at}

    def release_control(self, node_id: str, user_id: str, project_id: str) -> dict:
        current = self.control_locks.get(node_id)
        if current and current.owner_user_id == user_id and current.project_id == project_id:
            self.control_locks.pop(node_id, None)
            return {"released": True, "node_id": node_id, "project_id": project_id}
        return {"released": False, "node_id": node_id, "project_id": project_id}

    def control_status(self, node_id: str, user_id: str) -> dict:
        self.require_owned(node_id, user_id)
        now = time.time()
        current = self.control_locks.get(node_id)
        if current and current.expires_at <= now:
            self.control_locks.pop(node_id, None)
            current = None
        return {
            "node_id": node_id,
            "project_id": current.project_id if current and current.owner_user_id == user_id else None,
            "expires_at": current.expires_at if current and current.owner_user_id == user_id else None,
        }

    async def rpc(self, node_id: str, user_id: str, method: str, params: dict, timeout: float = 180.0) -> Any:
        node = self.require_owned(node_id, user_id)
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


def _user():
    return current_user(required=True)


def _binding(project_id: str):
    user = _user()
    binding = bindings.get(user.id, project_id)
    if not binding:
        raise RuntimeError(f"Project is not bound: {project_id}")
    return user, binding


async def _project_rpc(project_id: str, method: str, params: dict | None = None, include_workspace: bool = True):
    user, binding = _binding(project_id)
    payload = dict(params or {})
    if include_workspace:
        payload["workspace"] = binding.workspace
    result = await registry.rpc(binding.node_id, user.id, method, payload)
    auth.audit(user.id, method, project_id, {"node_id": binding.node_id})
    return result


def _desktop_lock(project_id: str, ttl_seconds: int = 120) -> None:
    user, binding = _binding(project_id)
    registry.acquire_control(binding.node_id, user.id, project_id, ttl_seconds)


async def auth_register(request: Request):
    try:
        body = await request.json()
        user = auth.register(body.get("email", ""), body.get("password", ""), body.get("name"))
        token = auth.issue_token(user)
        auth.audit(user.id, "auth.register")
        response = JSONResponse({"access_token": token, "token_type": "bearer", "user": user.__dict__}, status_code=201)
        response.set_cookie("gwc_access_token", token, httponly=True, secure=settings.public_base_url.startswith("https://"), samesite="lax", max_age=settings.jwt_ttl_seconds)
        return response
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def auth_login(request: Request):
    try:
        body = await request.json()
        user = auth.login(body.get("email", ""), body.get("password", ""))
        token = auth.issue_token(user)
        auth.audit(user.id, "auth.login")
        response = JSONResponse({"access_token": token, "token_type": "bearer", "user": user.__dict__})
        response.set_cookie("gwc_access_token", token, httponly=True, secure=settings.public_base_url.startswith("https://"), samesite="lax", max_age=settings.jwt_ttl_seconds)
        return response
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)


async def auth_me(_: Request):
    return JSONResponse({"user": _user().__dict__})


async def auth_google_start(_: Request):
    if not settings.google_client_id or not settings.google_redirect_uri:
        return JSONResponse({"error": "google_login_not_configured"}, status_code=503)
    state = auth.new_oauth_state()
    return RedirectResponse(google_authorize_url(settings.google_client_id, settings.google_redirect_uri, state), status_code=302)


async def auth_google_callback(request: Request):
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
        return JSONResponse({"error": "google_login_not_configured"}, status_code=503)
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not state or not code:
        return JSONResponse({"error": "missing_oauth_parameters"}, status_code=400)
    try:
        auth.consume_oauth_state(state)
        info = await google_exchange_code(settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri, code)
        user = auth.google_login(sub=str(info.get("sub", "")), email=str(info.get("email", "")), name=info.get("name"), picture=info.get("picture"))
        token = auth.issue_token(user)
        auth.audit(user.id, "auth.google_login")
        if settings.auth_success_url:
            response = RedirectResponse(f"{settings.auth_success_url}#access_token={quote(token)}", status_code=302)
        else:
            response = JSONResponse({"access_token": token, "token_type": "bearer", "user": user.__dict__})
        response.set_cookie("gwc_access_token", token, httponly=True, secure=settings.public_base_url.startswith("https://"), samesite="lax", max_age=settings.jwt_ttl_seconds)
        return response
    except Exception as exc:
        return JSONResponse({"error": f"google_login_failed: {exc}"}, status_code=400)


transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=list(settings.allowed_hosts),
    allowed_origins=list(settings.allowed_origins),
)

mcp = FastMCP(
    "Lucas",
    instructions="Multi-user remote Windows execution layer. Every authenticated user has isolated projects and nodes. Project bindings are the only workspace context: (user_id, project_id) -> Windows node + workspace. No conversation binding is used.",
    stateless_http=True,
    json_response=True,
    transport_security=transport_security,
)


@mcp.tool()
async def project_bind(project_id: str, node_id: str, workspace: str, name: str | None = None) -> dict:
    user = _user()
    registry.require_owned(node_id, user.id)
    verified = await registry.rpc(node_id, user.id, "workspace.info", {"workspace": workspace})
    binding = bindings.set(user.id, project_id, node_id, str(verified["path"]), name)
    auth.audit(user.id, "project.bind", project_id, {"node_id": node_id, "workspace": binding.workspace})
    return binding.__dict__


@mcp.tool()
def project_get(project_id: str) -> dict | None:
    user = _user()
    item = bindings.get(user.id, project_id)
    return item.__dict__ if item else None


@mcp.tool()
def project_list() -> list[dict]:
    user = _user()
    return [item.__dict__ for item in bindings.list(user.id)]


@mcp.tool()
def project_unbind(project_id: str) -> dict:
    user = _user()
    item = bindings.get(user.id, project_id)
    if item:
        registry.release_control(item.node_id, user.id, project_id)
    removed = bindings.remove(user.id, project_id)
    auth.audit(user.id, "project.unbind", project_id)
    return {"removed": removed}


@mcp.tool()
def node_pair(node_id: str, name: str | None = None, ttl_seconds: int = 600) -> dict:
    user = _user()
    ttl_seconds = max(60, min(ttl_seconds, 3600))
    code = f"{secrets.randbelow(1_000_000):06d}"
    _pairings[code] = {"node_id": node_id, "name": name or node_id, "owner_user_id": user.id, "expires": time.time() + ttl_seconds}
    auth.audit(user.id, "node.pair_code", node_id)
    return {"node_id": node_id, "pairing_code": code, "expires_in": ttl_seconds}


@mcp.tool()
def node_list() -> list[dict]:
    user = _user()
    return registry.list(user.id)


@mcp.tool()
def control_acquire(project_id: str, ttl_seconds: int = 120) -> dict:
    user, binding = _binding(project_id)
    return registry.acquire_control(binding.node_id, user.id, project_id, ttl_seconds)


@mcp.tool()
def control_release(project_id: str) -> dict:
    user, binding = _binding(project_id)
    return registry.release_control(binding.node_id, user.id, project_id)


@mcp.tool()
def control_status(project_id: str) -> dict:
    user, binding = _binding(project_id)
    return registry.control_status(binding.node_id, user.id)


@mcp.tool()
async def workspace_info(project_id: str) -> dict:
    return await _project_rpc(project_id, "workspace.info")


@mcp.tool()
async def files_tool(project_id: str, action: str, params: dict | None = None) -> object:
    allowed = {"list", "read", "write", "patch", "search", "stat", "mkdir", "move", "copy", "delete"}
    if action not in allowed:
        raise ValueError(f"Unsupported files action: {action}")
    return await _project_rpc(project_id, f"files.{action}", params)


@mcp.tool()
async def shell_run(project_id: str, command: str, timeout: int = 120, shell_type: str = "powershell") -> dict:
    return await _project_rpc(project_id, "shell.run", {"command": command, "timeout": timeout, "shell_type": shell_type})


@mcp.tool()
async def process_tool(project_id: str, action: str, params: dict | None = None) -> dict:
    if action not in {"start", "poll", "stop", "list"}:
        raise ValueError(f"Unsupported process action: {action}")
    return await _project_rpc(project_id, f"process.{action}", params, include_workspace=True)


@mcp.tool()
async def git_tool(project_id: str, action: str, params: dict | None = None) -> dict:
    allowed = {"status", "diff", "log", "branch", "branch_create", "branch_switch", "add", "commit", "pull", "push", "show"}
    if action not in allowed:
        raise ValueError(f"Unsupported git action: {action}")
    return await _project_rpc(project_id, f"git.{action}", params)


@mcp.tool()
async def browser_tool(project_id: str, action: str, params: dict | None = None) -> object:
    allowed = {"discover", "connect_cdp", "launch_persistent", "pages", "new_page", "navigate", "inspect", "click", "type", "select", "upload", "download", "screenshot", "close"}
    if action not in allowed:
        raise ValueError(f"Unsupported browser action: {action}")
    if action not in {"discover", "pages", "inspect", "screenshot"}:
        _desktop_lock(project_id)
    return await _project_rpc(project_id, f"browser.{action}", params, include_workspace=True)


@mcp.tool()
async def computer_tool(project_id: str, action: str, params: dict | None = None) -> object:
    allowed = {"info", "processes", "launch", "windows", "activate", "screenshot", "click", "move", "drag", "type", "hotkey", "press", "scroll", "clipboard_get", "clipboard_set", "ui_elements", "ui_click", "ui_set_text"}
    if action not in allowed:
        raise ValueError(f"Unsupported computer action: {action}")
    if action not in {"info", "processes", "windows", "screenshot", "clipboard_get", "ui_elements"}:
        _desktop_lock(project_id)
    return await _project_rpc(project_id, f"computer.{action}", params, include_workspace=True)


async def health(_: Request):
    return JSONResponse({"ok": True, "online_nodes": len(registry.nodes), "auth": "multi-user"})


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
        hello_roots = [str(item) for item in (hello.get("allowed_roots") or []) if str(item).strip()]
        supplied_token = hello.get("node_token")
        pairing_code = hello.get("pairing_code")
        record = await auth_store.record_for(node_id)
        authorized = bool(record and supplied_token and secrets.compare_digest(str(record["token"]), str(supplied_token)))
        issued_token = None
        owner_user_id = str(record["owner_user_id"]) if authorized and record else None
        if not authorized and pairing_code:
            pairing = _pairings.get(str(pairing_code))
            if pairing and (not pairing.get("node_id") or pairing["node_id"] == node_id) and pairing["expires"] >= time.time():
                owner_user_id = pairing["owner_user_id"]
                issued_token = secrets.token_urlsafe(32)
                await auth_store.save(node_id, owner_user_id, str(pairing.get("name") or name), issued_token, "operate", hello_roots)
                _pairings.pop(str(pairing_code), None)
                authorized = True
                record = await auth_store.record_for(node_id)
        if not authorized or not owner_user_id:
            await websocket.send_json({"type": "welcome", "ok": False, "error": "pairing or node token required"})
            await websocket.close(code=4401)
            return
        record = record or await auth_store.record_for(node_id)
        if record:
            try:
                stored_roots = json.loads(record.get("allowed_roots") or "[]")
            except json.JSONDecodeError:
                stored_roots = []
            if authorized and not stored_roots and hello_roots:
                await auth_store.update_config(node_id, owner_user_id, str(record.get("name") or name), permission_level, hello_roots)
                record = await auth_store.record_for(node_id) or record
                stored_roots = hello_roots
            name = str(record.get("name") or name)
            permission_level = str(record.get("permission_level") or permission_level)
            allowed_roots = stored_roots or hello_roots
        else:
            allowed_roots = hello_roots
        connection = NodeConnection(node_id=node_id, owner_user_id=owner_user_id, name=name, permission_level=permission_level, allowed_roots=allowed_roots, websocket=websocket)
        old = registry.nodes.get(node_id)
        if old:
            with contextlib.suppress(Exception):
                await old.websocket.close(code=4001)
        registry.nodes[node_id] = connection
        await websocket.send_json({"type": "welcome", "ok": True, "node_token": issued_token, "config": {"node_name": name, "permission_level": permission_level, "allowed_roots": allowed_roots}})
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
            registry.control_locks.pop(node_id, None)
            for future in connection.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError(f"Node disconnected: {node_id}"))


mcp_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/.well-known/oauth-authorization-server", oauth.as_meta, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", oauth.resource_meta, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource/mcp", oauth.resource_meta, methods=["GET"]),
        Route("/oauth/register", oauth.register, methods=["POST"]),
        Route("/oauth/authorize", oauth.authorize, methods=["GET"]),
        Route("/oauth/authorize/login", oauth.authorize_login, methods=["POST"]),
        Route("/oauth/authorize/decision", oauth.authorize_decision, methods=["POST"]),
        Route("/oauth/token", oauth.token, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/auth/register", auth_register, methods=["POST"]),
        Route("/auth/login", auth_login, methods=["POST"]),
        Route("/auth/me", auth_me, methods=["GET"]),
        Route("/auth/google/start", auth_google_start, methods=["GET"]),
        Route("/auth/google/callback", auth_google_callback, methods=["GET"]),
        WebSocketRoute("/ws/node", node_websocket),
        Mount("/", app=mcp_app),
    ],
    lifespan=lifespan,
)
app = AuthMiddleware(app)


def main() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
