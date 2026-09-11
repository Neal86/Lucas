from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import os
import secrets
import hashlib
import importlib.metadata
import sqlite3
import time
import uuid

import httpx
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
from .config import GatewaySettings
from .billing import BillingService
from .meta_capi import MetaConversionsAPI
from .entitlements import ensure_node_active, ensure_node_capacity, ensure_request_capacity
from .oauth import OAuthProvider
from .registration_security import RegistrationSecurity, email_verification_enabled, send_verification_email
from .task_runs import TaskRunStore
from .gateway_readiness import readiness_checks, critical_ready
from .gateway_referral import claim_referral_cookie

settings = GatewaySettings.from_env()
db_path = settings.data_dir / "gateway.db"
auth = AuthStore(db_path, settings.jwt_secret, settings.jwt_ttl_seconds)
meta_capi = MetaConversionsAPI(settings.public_base_url)
billing = BillingService(db_path, settings.public_base_url, meta_capi=meta_capi)
oauth = OAuthProvider(db_path, auth, settings.public_base_url)
registration_security = RegistrationSecurity(db_path)
task_runs = TaskRunStore(db_path)
log = logging.getLogger("lucas.gateway")


class AuthMiddleware:
    PUBLIC_PATHS = {
        "/health",
        "/live",
        "/auth/register",
        "/auth/verify-email",
        "/auth/resend-verification",
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
        if path.startswith("/mcp"):
            auth.record_request(user.id)
        ctx = set_current_user(user)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_user(ctx)


from .gateway_stores import NodeAuthStore, UserNodeBindingStore



auth_store = NodeAuthStore(db_path)


def _token_digest(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()




bindings = UserNodeBindingStore(db_path)


from .gateway_registry import NodeConnection, NodeRegistry

registry = NodeRegistry(bindings)


from .gateway_events import BrowserEventHub


dashboard_events = BrowserEventHub()


def _user():
    return current_user(required=True)


def _actor(user) -> dict:
    return {"user_id": user.id, "email": user.email, "name": user.name or ""}


_SHELL_STRUCTURAL = re.compile(
    r"^(?:if|elseif|else|foreach|for|while|switch|try|catch|finally|function|filter|class|param|begin|process|end|do)\b",
    re.IGNORECASE,
)
_SHELL_NON_ACTION = re.compile(
    r"^(?:return|break|continue|throw|exit|Write-(?:Host|Output|Verbose|Debug|Warning|Information)|Start-Sleep)\b",
    re.IGNORECASE,
)
_SHELL_NON_BILLABLE_COMMANDS = {
    "join-path", "split-path", "foreach-object", "where-object", "select-object",
    "sort-object", "group-object", "measure-object", "compare-object",
    "write-output", "write-host", "write-debug", "write-verbose", "write-warning",
    "write-information", "out-string", "format-table", "format-list", "format-wide",
    "format-custom", "convertto-json", "convertfrom-json", "convertto-csv",
    "convertfrom-csv", "get-date", "get-random", "start-sleep", "set-psdebug",
    "new-object", "set-variable", "get-variable",
}
_SHELL_TRACE_RE = re.compile(r"^DEBUG:\s+\d+\+\s*.*?>>>>\s*(.*)$")


def _split_pipeline(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote and (i == 0 or text[i - 1] != "`"):
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in "([": depth += 1
        elif ch in ")]": depth = max(0, depth - 1)
        if ch == "|" and depth == 0 and text[i:i+2] != "||":
            item = "".join(buf).strip()
            if item:
                out.append(item)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    item = "".join(buf).strip()
    if item:
        out.append(item)
    return out


def _billable_commands_from_statement(statement: str) -> list[str]:
    text = str(statement or "").strip()
    if not text:
        return []
    if text.startswith(("{", "}")):
        return []
    if "{" in text:
        text = text.split("{", 1)[0].strip()
    if not text or _SHELL_STRUCTURAL.match(text) or _SHELL_NON_ACTION.match(text):
        return []
    assignment = re.match(r"^\$[A-Za-z_][\w:.-]*\s*(?:=|\+=|-=|\*=|/=)\s*(.+)$", text)
    if assignment:
        text = assignment.group(1).strip()
    labels: list[str] = []
    for stage in _split_pipeline(text):
        stage = stage.strip()
        if not stage:
            continue
        match = re.match(r"^(?:&\s*)?([A-Za-z][\w.-]*)\b", stage)
        if not match:
            continue
        command = match.group(1)
        if command.lower() in _SHELL_NON_BILLABLE_COMMANDS:
            continue
        labels.append(re.sub(r"\s+", " ", stage).strip()[:240])
    return labels


def _instrument_powershell(command: str) -> str:
    return "Set-PSDebug -Trace 1\ntry {\n" + str(command or "") + "\n} finally { Set-PSDebug -Off }"


def _extract_runtime_shell_operations(stdout: str) -> tuple[str, list[str]]:
    clean: list[str] = []
    actions: list[str] = []
    for line in str(stdout or "").splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        match = _SHELL_TRACE_RE.match(plain)
        if not match:
            clean.append(line)
            continue
        actions.extend(_billable_commands_from_statement(match.group(1)))
    return "".join(clean), actions


def _split_shell_statements(command: str) -> list[str]:
    """Split shell text on real statement separators, not separators inside quotes."""
    text = str(command or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    text = re.sub(r"@'(?s:.*?)'@", "'<here-string>'", text)
    text = re.sub(r'@"(?s:.*?)"@', '"<here-string>"', text)
    text = text.replace("`\n", " ")
    out: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escaped:
            buf.append(ch); escaped = False; i += 1; continue
        if ch == "`" and quote == '"':
            buf.append(ch); escaped = True; i += 1; continue
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1; continue
        if ch in {"'", '"'}:
            quote = ch; buf.append(ch); i += 1; continue
        pair = text[i:i+2]
        if ch in {";", "\n"} or pair in {"&&", "||"}:
            item = "".join(buf).strip()
            if item:
                out.append(item)
            buf = []
            i += 2 if pair in {"&&", "||"} else 1
            continue
        buf.append(ch); i += 1
    item = "".join(buf).strip()
    if item:
        out.append(item)
    return out


def _shell_operations(command: str) -> list[str]:
    """Static fallback for shell accounting when runtime tracing is unavailable."""
    actions: list[str] = []
    for raw in _split_shell_statements(command):
        line = re.sub(r"^[{}()]+|[{}()]+$", "", raw.strip()).strip()
        if not line or line.startswith("#"):
            continue
        actions.extend(_billable_commands_from_statement(line))
    return actions or ["shell.run"]


def _shell_operation_count(command: str) -> int:
    return len(_shell_operations(command))


def _operation_count(method: str, params: dict | None = None) -> int:
    if method == "shell.run":
        return _shell_operation_count(str((params or {}).get("command") or ""))
    return 1


async def _node_rpc(node_id: str, workspace: str, method: str, params: dict | None = None, include_workspace: bool = True, task_title: str | None = None):
    user = _user()
    payload = dict(params or {})
    original_command = str(payload.get("command") or "") if method == "shell.run" else ""
    sub_operations = _shell_operations(original_command) if method == "shell.run" else []
    operation_count = len(sub_operations) if sub_operations else _operation_count(method, payload)
    shell_type = str(payload.get("shell_type") or "powershell").lower().strip()
    trace_shell = method == "shell.run" and shell_type in {"powershell", "pwsh"} and "Set-PSDebug" not in original_command
    if trace_shell:
        payload["command"] = _instrument_powershell(original_command)
    # A shell may execute a dynamic number of actions. Require at least one unit up front;
    # the exact runtime count is recorded after execution and the next call enforces quota.
    ensure_request_capacity(db_path, user.id, 1 if method == "shell.run" else operation_count)
    ensure_node_active(db_path, user.id, node_id)
    workspace = str(workspace or "").strip()
    if not workspace:
        raise ValueError("workspace is required and must be inside an Allowed folder")
    task_title = " ".join(str(task_title or "").split())[:180] or None
    run_context = workspace
    if include_workspace:
        payload["workspace"] = workspace
    wall_started = time.time()
    started = time.monotonic()
    try:
        rpc_timeout = 180.0
        if method == "shell.run":
            try:
                rpc_timeout = max(180.0, min(float(payload.get("timeout") or 120) + 60.0, 3660.0))
            except (TypeError, ValueError):
                rpc_timeout = 180.0
        result = await registry.rpc(node_id, user.id, method, payload, actor=_actor(user), timeout=rpc_timeout)
        if trace_shell and isinstance(result, dict):
            clean_stdout, runtime_operations = _extract_runtime_shell_operations(str(result.get("stdout") or ""))
            result["stdout"] = clean_stdout
            if runtime_operations:
                sub_operations = runtime_operations
                operation_count = len(runtime_operations)
    except Exception as exc:
        duration = time.monotonic() - started; wall_ended = time.time()
        auth.record_operation(user.id, False, duration, operation_count)
        auth.audit(user.id, method, workspace, {"node_id": node_id, "status": "failed", "duration_ms": round(duration * 1000), "operation_count": operation_count, "error_type": type(exc).__name__})
        task_runs.record_operation(owner_id=user.id,node_id=node_id,action=method,target=workspace,started_at=wall_started,ended_at=wall_ended,status="failed",details={"error_type":type(exc).__name__,"sub_operations":sub_operations},operation_count=operation_count,context_key=run_context,task_title=task_title)
        raise
    duration = time.monotonic() - started; wall_ended = time.time()
    auth.record_operation(user.id, True, duration, operation_count)
    auth.audit(user.id, method, workspace, {"node_id": node_id, "status": "success", "duration_ms": round(duration * 1000), "operation_count": operation_count})
    task_runs.record_operation(owner_id=user.id,node_id=node_id,action=method,target=workspace,started_at=wall_started,ended_at=wall_ended,status="success",details={"sub_operations":sub_operations},operation_count=operation_count,context_key=run_context,task_title=task_title)
    return result


async def _desktop_lock(node_id: str, workspace: str, ttl_seconds: int = 120) -> None:
    user = _user()
    workspace = str(workspace or "").strip()
    if not workspace:
        raise ValueError("workspace is required")
    registry.acquire_control(node_id, user.id, workspace, ttl_seconds)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def meta_request_context(request: Request) -> dict[str, str]:
    return {
        "source_url": str(request.url),
        "client_ip": _client_ip(request),
        "user_agent": request.headers.get("user-agent", ""),
        "fbp": request.cookies.get("_fbp", ""),
        "fbc": request.cookies.get("_fbc", ""),
    }


def _registration_rate_ok(request: Request, email: str, *, resend: bool = False) -> bool:
    ip = _client_ip(request)
    if resend:
        return registration_security.allow(f"verify-ip:{ip}", 10, 3600) and registration_security.allow(f"verify-email:{email.lower()}", 6, 3600)
    return registration_security.allow(f"register-ip:{ip}", 3, 600) and registration_security.allow(f"register-email:{email.lower()}", 3, 3600)


async def _verify_turnstile(request: Request, token: str) -> bool:
    secret = os.getenv("GWC_TURNSTILE_SECRET_KEY", "").strip()
    if not secret:
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", data={"secret": secret, "response": token, "remoteip": _client_ip(request)})
            return bool(response.json().get("success"))
    except Exception:
        return False


async def auth_register(request: Request):
    try:
        body = await request.json()
        email = str(body.get("email", "")).strip().lower()
        meta_event_id = str(body.get("meta_event_id") or f"register_{uuid.uuid4().hex}")[:200]
        if str(body.get("website", "")).strip():
            return JSONResponse({"error": "Registration could not be completed"}, status_code=400)
        if not _registration_rate_ok(request, email):
            return JSONResponse({"error": "Too many registration attempts. Try again later."}, status_code=429)
        if not await _verify_turnstile(request, str(body.get("turnstile_token", ""))):
            return JSONResponse({"error": "Human verification failed"}, status_code=400)
        if email_verification_enabled():
            email, code = registration_security.start(email, body.get("password", ""), body.get("name"))
            send_verification_email(email, code)
            return JSONResponse({"verification_required": True, "email": email}, status_code=202)
        user = auth.register(email, body.get("password", ""), body.get("name"))
        token = auth.issue_token(user)
        auth.audit(user.id, "auth.register")
        await meta_capi.send_async("CompleteRegistration", event_id=meta_event_id, email=user.email, user_id=user.id, custom_data={"content_name":"Email Registration","status":"completed"}, **meta_request_context(request))
        claim_referral_cookie(request, billing.referrals, user.id)
        response = JSONResponse({"access_token": token, "token_type": "bearer", "user": user.__dict__}, status_code=201)
        response.set_cookie("gwc_access_token", token, httponly=True, secure=settings.public_base_url.startswith("https://"), samesite="lax", max_age=settings.jwt_ttl_seconds)
        return response
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


async def auth_verify_email(request: Request):
    if not email_verification_enabled():
        return JSONResponse({"error": "Email verification is not configured"}, status_code=503)
    try:
        body = await request.json()
        meta_event_id = str(body.get("meta_event_id") or f"verify_{uuid.uuid4().hex}")[:200]
        user_id = registration_security.verify(str(body.get("email", "")), str(body.get("code", "")))
        user = auth.get_user(user_id)
        token = auth.issue_token(user)
        auth.audit(user.id, "auth.email_verified")
        await meta_capi.send_async("CompleteRegistration", event_id=meta_event_id, email=user.email, user_id=user.id, custom_data={"content_name":"Email Registration","status":"verified"}, **meta_request_context(request))
        claim_referral_cookie(request, billing.referrals, user.id)
        response = JSONResponse({"access_token": token, "token_type": "bearer", "user": user.__dict__})
        response.set_cookie("gwc_access_token", token, httponly=True, secure=settings.public_base_url.startswith("https://"), samesite="lax", max_age=settings.jwt_ttl_seconds)
        return response
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def auth_resend_verification(request: Request):
    if not email_verification_enabled():
        return JSONResponse({"error": "Email verification is not configured"}, status_code=503)
    try:
        body = await request.json()
        email = str(body.get("email", "")).strip().lower()
        if not _registration_rate_ok(request, email, resend=True):
            return JSONResponse({"error": "Too many verification requests. Try again later."}, status_code=429)
        email, code = registration_security.resend(email)
        send_verification_email(email, code)
        return JSONResponse({"ok": True})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


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


async def auth_google_start(request: Request):
    if not settings.google_client_id or not settings.google_redirect_uri:
        return JSONResponse({"error": "google_login_not_configured"}, status_code=503)
    state = auth.new_oauth_state()
    meta_event_id = f"google_registration_{uuid.uuid4().hex}"
    response = RedirectResponse(google_authorize_url(settings.google_client_id, settings.google_redirect_uri, state), status_code=302)
    response.set_cookie("lucas_meta_google_registration", meta_event_id, httponly=True, secure=settings.public_base_url.startswith("https://"), samesite="lax", max_age=600)
    return response


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
        sub = str(info.get("sub", "")); email = str(info.get("email", ""))
        is_new_user = not auth.google_identity_exists(sub=sub, email=email)
        user = auth.google_login(sub=sub, email=email, name=info.get("name"), picture=info.get("picture"))
        token = auth.issue_token(user)
        auth.audit(user.id, "auth.google_login")
        meta_event_id = str(request.cookies.get("lucas_meta_google_registration") or f"google_registration_{uuid.uuid4().hex}")[:200]
        if is_new_user:
            await meta_capi.send_async("CompleteRegistration", event_id=meta_event_id, email=user.email, user_id=user.id, custom_data={"content_name":"Google Registration","status":"completed"}, **meta_request_context(request))
        claim_referral_cookie(request, billing.referrals, user.id)
        target = "/dashboard?meta_registration=" + quote(meta_event_id, safe="") if is_new_user else "/dashboard"
        response = RedirectResponse(target, status_code=302)
        response.set_cookie("gwc_access_token", token, httponly=True, secure=settings.public_base_url.startswith("https://"), samesite="lax", max_age=settings.jwt_ttl_seconds)
        response.delete_cookie("lucas_meta_google_registration")
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
    instructions="Multi-user remote computer access layer. New accounts connect with a Node ID plus the local Connection Code, then the Windows Node is the final authority for approval, Codex-style access policy, and Allowed folders. Previously authorized accounts reuse their local grant. Every workspace is validated locally before execution. IMPORTANT: for every user-requested execution task, automatically derive one concise, human-readable task_title from the CURRENT USER'S ORIGINAL PROMPT and pass that same title on every execution tool call. The user does NOT need to write a special 'task title' field. Prefer the main action + object from the prompt (for example, 'Create Task Manager Web App', 'Review software service contract', or 'Analyze accounting transactions'). Never use a tool name, shell command, workspace, or file path as the task title. Lucas groups all calls with that derived title into one Task Run.",
    stateless_http=True,
    json_response=True,
    transport_security=transport_security,
)


@mcp.tool()
async def node_list() -> list[dict]:
    user = _user()
    return await registry.list(user)


@mcp.tool()
async def node_request_access(node_id: str, connection_code: str) -> dict:
    user = _user()
    node_id = str(node_id or "").strip()
    connection_code = str(connection_code or "").strip()
    if not node_id:
        raise ValueError("node_id is required")
    if not connection_code:
        raise ValueError("connection_code is required for a new account")
    registry.require_online(node_id)
    ensure_node_capacity(db_path, user.id, node_id)
    if not registration_security.allow(f"node-access:{user.id}:{node_id}", 5, 60):
        raise PermissionError("Too many connection attempts. Try again in a minute.")
    result = await registry.rpc(node_id, user.id, "access.request", {"connection_code": connection_code}, actor=_actor(user), timeout=180.0)
    if isinstance(result, dict) and result.get("authorized"):
        bindings.upsert(user.id, node_id)
    auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized"))})
    return result


@mcp.tool()
async def control_acquire(node_id: str, workspace: str, ttl_seconds: int = 120) -> dict:
    user = _user()
    workspace = str(workspace or "").strip()
    if not workspace:
        raise ValueError("workspace is required")
    return registry.acquire_control(node_id, user.id, workspace, ttl_seconds)


@mcp.tool()
def control_release(node_id: str, workspace: str) -> dict:
    user = _user()
    return registry.release_control(node_id, user.id, workspace)


@mcp.tool()
def control_status(node_id: str) -> dict:
    user = _user()
    return registry.control_status(node_id, user.id)


@mcp.tool()
async def workspace_info(node_id: str, workspace: str, task_title: str | None = None) -> dict:
    return await _node_rpc(node_id, workspace, "workspace.info", {"workspace": workspace}, include_workspace=False, task_title=task_title)


@mcp.tool()
async def files_tool(node_id: str, workspace: str, action: str, params: dict | None = None, task_title: str | None = None) -> object:
    allowed = {"list", "read", "write", "patch", "search", "stat", "mkdir", "move", "copy", "delete"}
    if action not in allowed:
        raise ValueError(f"Unsupported files action: {action}")
    return await _node_rpc(node_id, workspace, f"files.{action}", params, task_title=task_title)


@mcp.tool()
async def shell_run(node_id: str, workspace: str, command: str, timeout: int = 120, shell_type: str = "powershell", task_title: str | None = None) -> dict:
    return await _node_rpc(node_id, workspace, "shell.run", {"command": command, "timeout": timeout, "shell_type": shell_type}, task_title=task_title)


@mcp.tool()
async def process_tool(node_id: str, workspace: str, action: str, params: dict | None = None, task_title: str | None = None) -> dict:
    if action not in {"start", "poll", "stop", "list"}:
        raise ValueError(f"Unsupported process action: {action}")
    return await _node_rpc(node_id, workspace, f"process.{action}", params, task_title=task_title)


@mcp.tool()
async def git_tool(node_id: str, workspace: str, action: str, params: dict | None = None, task_title: str | None = None) -> dict:
    allowed = {"status", "diff", "log", "branch", "branch_create", "branch_switch", "add", "commit", "pull", "push", "show"}
    if action not in allowed:
        raise ValueError(f"Unsupported git action: {action}")
    return await _node_rpc(node_id, workspace, f"git.{action}", params, task_title=task_title)


@mcp.tool()
async def browser_tool(node_id: str, workspace: str, action: str, params: dict | None = None, task_title: str | None = None) -> object:
    allowed = {"discover", "connect_cdp", "launch_persistent", "pages", "new_page", "navigate", "inspect", "click", "type", "select", "upload", "download", "screenshot", "close"}
    if action not in allowed:
        raise ValueError(f"Unsupported browser action: {action}")
    if action not in {"discover", "pages", "inspect", "screenshot"}:
        await _desktop_lock(node_id, workspace)
    return await _node_rpc(node_id, workspace, f"browser.{action}", params, task_title=task_title)


@mcp.tool()
async def computer_tool(node_id: str, workspace: str, action: str, params: dict | None = None, task_title: str | None = None) -> object:
    allowed = {"info", "processes", "launch", "windows", "activate", "screenshot", "click", "move", "drag", "type", "hotkey", "press", "scroll", "clipboard_get", "clipboard_set", "ui_elements", "ui_click", "ui_set_text"}
    if action not in allowed:
        raise ValueError(f"Unsupported computer action: {action}")
    if action not in {"info", "processes", "windows", "screenshot", "clipboard_get", "ui_elements"}:
        await _desktop_lock(node_id, workspace)
    return await _node_rpc(node_id, workspace, f"computer.{action}", params, task_title=task_title)


async def live(_: Request):
    return JSONResponse({"ok": True, "service": "lucas-gateway"})


async def health(_: Request):
    try: version=importlib.metadata.version("gpt-windows-connector")
    except importlib.metadata.PackageNotFoundError: version="unknown"
    checks=readiness_checks(db_path,settings,billing,email_verification_enabled); ready=critical_ready(checks)
    return JSONResponse({"ok":ready,"version":version,"online_nodes":len(registry.nodes),"auth":"multi-user","checks":checks},status_code=200 if ready else 503)


async def browser_events_websocket(websocket: WebSocket):
    authorization = websocket.headers.get("authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        token = websocket.cookies.get("gwc_access_token", "")
    try:
        user = auth.verify_token(token)
    except Exception:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    dashboard_events.subscribe(user.id, websocket)
    try:
        await websocket.send_json({"type": "ready", "time": time.time()})
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "heartbeat":
                await websocket.send_json({"type": "heartbeat_ack", "time": time.time()})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        dashboard_events.unsubscribe(user.id, websocket)


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
        hello_roots = [str(item) for item in (hello.get("allowed_roots") or []) if str(item).strip()]
        authorized_user_ids = [str(v) for v in hello.get("authorized_user_ids") or [] if str(v).strip()]
        supplied_token = str(hello.get("node_token") or "").strip()
        runtime_id = str(hello.get("runtime_id") or "").strip()
        if not supplied_token:
            log.warning("Node rejected node_id=%s reason=missing-device-token", node_id)
            await websocket.send_json({"type": "welcome", "ok": False, "error": "node device token required"})
            await websocket.close(code=4401)
            return
        record = await auth_store.record_for(node_id)
        log.info("Node hello received node_id=%s name=%s", node_id, name)
        if not record:
            await auth_store.save(node_id, name, _token_digest(supplied_token), hello_roots)
            record = await auth_store.record_for(node_id)
        else:
            stored_token = str(record.get("token") or "")
            if not stored_token:
                await auth_store.update_token(node_id, _token_digest(supplied_token))
            elif stored_token.startswith("sha256:"):
                if not secrets.compare_digest(stored_token, _token_digest(supplied_token)):
                    log.warning("Node rejected node_id=%s reason=device-token-mismatch", node_id)
                    await websocket.send_json({"type": "welcome", "ok": False, "error": "invalid node device token"})
                    await websocket.close(code=4401)
                    return
            elif secrets.compare_digest(stored_token, supplied_token):
                await auth_store.update_token(node_id, _token_digest(supplied_token))
            else:
                log.warning("Node rejected node_id=%s reason=legacy-device-token-mismatch", node_id)
                await websocket.send_json({"type": "welcome", "ok": False, "error": "invalid node device token"})
                await websocket.close(code=4401)
                return
        stored_roots: list[str] = []
        if record:
            try:
                stored_roots = json.loads(record.get("allowed_roots") or "[]")
            except json.JSONDecodeError:
                stored_roots = []
        allowed_roots = hello_roots or stored_roots
        display_name = str(record.get("name") or name) if record else name
        await auth_store.update_config(node_id, display_name, allowed_roots)
        connection = NodeConnection(node_id=node_id, name=display_name, allowed_roots=allowed_roots, websocket=websocket, runtime_id=runtime_id)
        registry.register_connection(node_id, runtime_id)
        old = registry.nodes.get(node_id)
        if old:
            with contextlib.suppress(Exception):
                await old.websocket.close(code=4001)
        registry.nodes[node_id] = connection
        log.info("Node connected node_id=%s name=%s authorized_users=%d runtime=%s", node_id, display_name, len(authorized_user_ids), runtime_id or "legacy")
        bindings.reconcile_node(node_id, authorized_user_ids)
        await websocket.send_json({"type": "welcome", "ok": True, "config": {"local_security_authority": True, "multi_user_access": True, "pairing_required": False, "node_auth_required": True}})
        await registry.replay_pending(node_id)
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "heartbeat":
                connection.last_seen = time.time()
                await websocket.send_json({"type": "heartbeat_ack", "time": time.time()})
            elif message.get("type") == "response":
                registry.resolve(node_id, message)
                async with connection.send_lock:
                    await websocket.send_json({"type": "response.ack", "id": message.get("id")})
            elif message.get("type") == "access.sync":
                added, removed = bindings.reconcile_node(node_id, [str(v) for v in message.get("authorized_user_ids") or []])
                for user_id in added:
                    try:
                        user = auth.get_user(user_id)
                        visible = await registry.list(user)
                        node_payload = next((item for item in visible if item.get("node_id") == node_id), None)
                        if node_payload:
                            await dashboard_events.publish(user_id, "node.upsert", {"node": node_payload})
                    except Exception:
                        log.exception("Could not publish approved node for user=%s node=%s", user_id, node_id)
                for user_id in removed:
                    current = registry.control_locks.get(node_id)
                    if current and current.owner_user_id == user_id:
                        registry.control_locks.pop(node_id, None)
                    await dashboard_events.publish(user_id, "node.remove", {"node_id": node_id})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if node_id and registry.nodes.get(node_id) and registry.nodes[node_id].websocket is websocket:
            registry.nodes.pop(node_id, None)
            registry.begin_disconnect_grace(node_id)
            log.info("Node transport disconnected; holding RPCs for %.1fs grace node_id=%s", DISCONNECT_GRACE_SECONDS, node_id)


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
        Route("/live", live, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/auth/register", auth_register, methods=["POST"]),
        Route("/auth/verify-email", auth_verify_email, methods=["POST"]),
        Route("/auth/resend-verification", auth_resend_verification, methods=["POST"]),
        Route("/auth/login", auth_login, methods=["POST"]),
        Route("/auth/me", auth_me, methods=["GET"]),
        Route("/auth/google/start", auth_google_start, methods=["GET"]),
        Route("/auth/google/callback", auth_google_callback, methods=["GET"]),
        WebSocketRoute("/ws/events", browser_events_websocket),
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
