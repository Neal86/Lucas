"""Authenticated loopback bridge for explicitly granted browser tabs.

The extension is the local authority for tab grants. Remote tool parameters can
neither create grants nor select tabs outside an existing owner-bound session.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from websockets.asyncio.server import serve


@dataclass
class TabGrant:
    owner_id: str
    tab_id: int
    connection: object
    expires_at: float
    title: str = ""
    url: str = ""


class ExtensionBridge:
    def __init__(self, token: str, owners: Callable[[], list[dict]] = lambda: []) -> None:
        self.token = token
        self.owners = owners
        self.sessions: dict[str, TabGrant] = {}
        self.pending: dict[str, tuple[object, str, asyncio.Future]] = {}
        self.server = None

    async def start(self, port: int = 8766) -> None:
        # No public bind, no query-string credentials, no website origins.
        self.server = await serve(self.handle, "127.0.0.1", port, max_size=32 * 1024 * 1024)

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    def revoke(self, sid: str) -> None:
        self.sessions.pop(sid, None)
        for _, pending_sid, future in list(self.pending.values()):
            if pending_sid == sid and not future.done():
                future.set_exception(PermissionError("Browser tab authorization revoked"))

    async def handle(self, connection) -> None:
        origin = connection.request.headers.get("Origin", "")
        if not origin.startswith("chrome-extension://"):
            await connection.close(code=1008, reason="Extension origin required")
            return
        try:
            hello = json.loads(await asyncio.wait_for(connection.recv(), 5))
            if hello.get("type") != "hello" or not secrets.compare_digest(str(hello.get("token", "")), self.token):
                await connection.close(code=1008, reason="Pairing failed")
                return
            await connection.send(json.dumps({"type": "ready", "owners": self.owners()}))
            async for raw in connection:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await connection.send(json.dumps({"type":"pong"}))
                elif msg.get("type") == "grant":
                    owner = str(msg.get("owner_id") or "")
                    if owner not in {str(x["user_id"]) for x in self.owners()}:
                        await connection.send(json.dumps({"type": "grant_error", "error": "Account must first be approved in Lucas Settings"}))
                        continue
                    tab = msg.get("tab_id")
                    if not isinstance(tab, int) or isinstance(tab, bool) or tab < 0:
                        raise ValueError("Invalid tab")
                    sid = "ext-" + secrets.token_hex(16)
                    self.sessions[sid] = TabGrant(owner, tab, connection, time.time() + 8 * 3600, str(msg.get("title", ""))[:300], str(msg.get("url", ""))[:2000])
                    await connection.send(json.dumps({"type": "granted", "session_id": sid, "tab_id": tab, "owner_id": owner}))
                elif msg.get("type") == "revoke":
                    sid = str(msg.get("session_id") or "")
                    grant = self.sessions.get(sid)
                    if grant and grant.connection is connection:
                        self.revoke(sid)
                elif msg.get("type") == "response":
                    item = self.pending.get(str(msg.get("id") or ""))
                    if item and item[0] is connection and not item[2].done():
                        if msg.get("ok"):
                            item[2].set_result(msg.get("result"))
                        else:
                            item[2].set_exception(RuntimeError(str(msg.get("error") or "Extension action failed")))
        except (ValueError, TimeoutError):
            await connection.close(code=1008, reason="Invalid bridge message")
        finally:
            for sid, grant in list(self.sessions.items()):
                if grant.connection is connection:
                    self.revoke(sid)

    def grant(self, sid: str, owner: str) -> TabGrant:
        grant = self.sessions.get(sid)
        if not grant or grant.owner_id != owner or grant.expires_at <= time.time() or owner not in {str(x["user_id"]) for x in self.owners()}:
            raise PermissionError("No active browser tab grant for this Lucas account; authorize it in the Lucas Browser extension")
        return grant

    def list_sessions(self, owner: str) -> dict:
        return {"sessions": [{"session_id": sid, "tab_id": g.tab_id, "title": g.title, "url": g.url, "expires_at": g.expires_at} for sid, g in self.sessions.items() if g.owner_id == owner and g.expires_at > time.time()]}

    async def call(self, owner: str, action: str, params: dict) -> object:
        if action == "extension_sessions":
            return self.list_sessions(owner)
        sid = str(params.get("session_id") or "")
        grant = self.grant(sid, owner)
        if action == "close":
            # Close the automation session, never the user's browser/tab.
            await grant.connection.send(json.dumps({"type": "revoked", "session_id": sid}))
            self.revoke(sid)
            return {"closed": True}
        allowed = {"resolve", "new_page", "pages", "navigate", "inspect", "observe", "click", "type", "semantic_click", "semantic_type", "select", "scroll", "upload", "download", "screenshot", "handoff"}
        if action not in allowed:
            raise ValueError(f"Unsupported extension action: {action}")
        if int(params.get("page_index", 0)) != 0:
            raise PermissionError("An extension session grants exactly one tab")
        rid = secrets.token_hex(16)
        future = asyncio.get_running_loop().create_future()
        self.pending[rid] = (grant.connection, sid, future)
        try:
            await grant.connection.send(json.dumps({"type": "request", "id": rid, "session_id": sid, "tab_id": grant.tab_id, "action": action, "params": {k: v for k, v in params.items() if k not in {"session_id", "owner_id", "tab_id", "page_index"}}}))
            return await asyncio.wait_for(future, timeout=90)
        finally:
            self.pending.pop(rid, None)


bridge: ExtensionBridge | None = None


def pairing_token(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    if __import__("os").name != "nt":
        path.chmod(0o600)
    return token


async def start_node_bridge(config_dir: Path, access_store, port: int = 8766) -> None:
    import logging
    global bridge
    bridge = ExtensionBridge(pairing_token(config_dir / "browser-extension-token.txt"), lambda: [
        {"user_id": str(u["user_id"]), "name": u.get("name", ""), "email": u.get("email", "")}
        for u in access_store.list_users() if u.get("enabled", True) and u.get("user_id")
    ])
    try:
        await bridge.start(port)
    except OSError:
        logging.getLogger("lucas.node").exception("Browser bridge unavailable; other Node tools remain available")
