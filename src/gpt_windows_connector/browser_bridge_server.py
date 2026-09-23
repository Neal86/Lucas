from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets

from .browser_profile_registry import registry

log = logging.getLogger("lucas.browser_bridge")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


@dataclass
class BridgeClient:
    installation_id: str
    extension_id: str
    websocket: Any
    browser_type: str = "chromium"
    profile_name: str = ""
    profile_id: str = ""
    alias: str = ""
    tags: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    paired: bool = False
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class BrowserBridgeServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = int(port)
        self.server = None
        self.clients: dict[str, BridgeClient] = {}
        self.pending: dict[str, dict[str, Any]] = {}
        self.waiters: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self.server is not None:
            return
        self.server = await websockets.serve(
            self._handler,
            self.host,
            self.port,
            max_size=32 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=30,
            origins=None,
        )
        log.info("Browser Bridge listening on ws://%s:%s/bridge", self.host, self.port)

    async def stop(self) -> None:
        if self.server is None:
            return
        self.server.close()
        await self.server.wait_closed()
        self.server = None

    async def _handler(self, websocket) -> None:
        request = getattr(websocket, "request", None)
        path = getattr(request, "path", "/") if request is not None else "/"
        headers = getattr(request, "headers", {}) if request is not None else {}
        origin = str(headers.get("Origin") or headers.get("origin") or "")
        if path.split("?", 1)[0] != "/bridge":
            await websocket.close(code=4404, reason="unknown path")
            return
        if origin and not origin.startswith("chrome-extension://"):
            await websocket.close(code=4403, reason="extension origin required")
            return

        client: BridgeClient | None = None
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
            hello = json.loads(raw)
            if hello.get("type") != "hello":
                await websocket.close(code=4400, reason="hello required")
                return
            installation_id = str(hello.get("installation_id") or "").strip()
            extension_id = str(hello.get("extension_id") or "").strip()
            if not installation_id or not extension_id:
                await websocket.close(code=4400, reason="bridge identity required")
                return
            profile = registry.profile_for_bridge(installation_id)
            paired = profile is not None
            client = BridgeClient(
                installation_id=installation_id,
                extension_id=extension_id,
                websocket=websocket,
                browser_type=str(hello.get("browser_type") or (profile or {}).get("browser_type") or "chromium").strip().lower(),
                profile_name=str(hello.get("profile_name") or (profile or {}).get("profile_name") or ""),
                profile_id=str(hello.get("profile_id") or (profile or {}).get("profile_id") or ""),
                alias=str(hello.get("alias") or ""),
                tags=[str(v) for v in hello.get("tags") or [] if str(v).strip()],
                groups=[str(v) for v in hello.get("groups") or [] if str(v).strip()],
                paired=paired,
            )
            async with self._lock:
                old = self.clients.get(installation_id)
                if old and old.websocket is not websocket:
                    try:
                        await old.websocket.close(code=4001, reason="replaced")
                    except Exception:
                        pass
                self.clients[installation_id] = client
                if paired:
                    self.pending.pop(installation_id, None)
                else:
                    self.pending[installation_id] = {
                        "installation_id": installation_id,
                        "extension_id": extension_id,
                        "browser_type": client.browser_type,
                        "profile_name": client.profile_name,
                        "profile_id": client.profile_id,
                        "alias": client.alias,
                        "pairing_code": f"{secrets.randbelow(1_000_000):06d}",
                        "connected_at": client.connected_at,
                    }
            await websocket.send(json.dumps({
                "type": "hello_ack",
                "paired": paired,
                "installation_id": installation_id,
                "profile": profile,
                "pairing_code": None if paired else self.pending[installation_id]["pairing_code"],
            }, ensure_ascii=False))

            async for raw in websocket:
                message = json.loads(raw)
                client.last_seen = time.time()
                if message.get("type") == "heartbeat":
                    await websocket.send(json.dumps({"type": "heartbeat_ack", "time": time.time()}))
                    continue
                if message.get("type") != "response":
                    continue
                request_id = str(message.get("id") or "")
                waiter = self.waiters.pop(request_id, None)
                if waiter and not waiter.done():
                    if message.get("ok", True):
                        waiter.set_result(message.get("result"))
                    else:
                        waiter.set_exception(RuntimeError(str(message.get("error") or "Browser Bridge command failed")))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("Browser Bridge client disconnected: %s", exc)
        finally:
            if client:
                async with self._lock:
                    if self.clients.get(client.installation_id) is client:
                        self.clients.pop(client.installation_id, None)

    def list_clients(self) -> list[dict[str, Any]]:
        out = []
        for client in self.clients.values():
            profile = registry.profile_for_bridge(client.installation_id)
            out.append({
                "installation_id": client.installation_id,
                "extension_id": client.extension_id,
                "browser_type": client.browser_type,
                "profile_name": client.profile_name,
                "profile_id": client.profile_id,
                "alias": client.alias,
                "paired": client.paired,
                "connected": True,
                "connected_at": client.connected_at,
                "last_seen": client.last_seen,
                "profile": profile,
            })
        return sorted(out, key=lambda item: (not item["paired"], item["browser_type"], item["profile_name"]))

    def list_pending(self) -> list[dict[str, Any]]:
        # The pairing code is deliberately shown only inside the local browser
        # extension popup. Remote MCP clients may discover a pending bridge, but
        # cannot read the proof-of-presence code from Lucas itself.
        values = []
        for raw in self.pending.values():
            item = {key: value for key, value in dict(raw).items() if key != "pairing_code"}
            values.append(item)
        return sorted(values, key=lambda item: item.get("connected_at", 0))

    async def pair(
        self,
        installation_id: str,
        *,
        pairing_code: str | None = None,
        browser_type: str = "ixbrowser",
        profile_id: str | int | None = None,
        profile_name: str | None = None,
        aliases: list[str] | None = None,
        tags: list[str] | None = None,
        groups: list[str] | None = None,
    ) -> dict[str, Any]:
        installation_id = str(installation_id or "").strip()
        pending = self.pending.get(installation_id)
        if not pending:
            raise KeyError("No pending Browser Bridge with this installation_id")
        expected = str(pending.get("pairing_code") or "")
        supplied = str(pairing_code or "").strip()
        if not supplied:
            raise PermissionError("Browser Bridge pairing code is required. Read it from the local extension popup.")
        if not secrets.compare_digest(supplied, expected):
            raise PermissionError("Browser Bridge pairing code does not match")
        client = self.clients.get(installation_id)
        if client is None:
            raise RuntimeError("Browser Bridge disconnected before pairing")
        profile = registry.upsert_profile({
            "browser_type": browser_type or client.browser_type,
            "profile_id": profile_id if profile_id is not None else client.profile_id,
            "profile_name": profile_name or client.profile_name or f"Bridge {installation_id[:8]}",
            "aliases": aliases or ([client.alias] if client.alias else []),
            "tags": tags or client.tags,
            "groups": groups or client.groups,
            "bridge_installation_id": installation_id,
            "extension_id": client.extension_id,
            "last_seen": time.time(),
        })
        client.paired = True
        client.browser_type = str(profile.get("browser_type") or client.browser_type)
        client.profile_name = str(profile.get("profile_name") or client.profile_name)
        client.profile_id = str(profile.get("profile_id") or client.profile_id)
        self.pending.pop(installation_id, None)
        try:
            await client.websocket.send(json.dumps({"type": "paired", "profile": profile}, ensure_ascii=False))
        except Exception:
            pass
        return profile

    async def request(
        self,
        installation_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> Any:
        client = self.clients.get(str(installation_id or ""))
        if client is None:
            raise RuntimeError("Browser Bridge profile is not connected")
        if not client.paired:
            raise PermissionError("Browser Bridge is not paired with Lucas")
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        self.waiters[request_id] = waiter
        try:
            await client.websocket.send(json.dumps({
                "type": "command",
                "id": request_id,
                "action": str(action),
                "params": dict(params or {}),
            }, ensure_ascii=False))
            return await asyncio.wait_for(waiter, timeout=max(1.0, min(float(timeout), 120.0)))
        finally:
            self.waiters.pop(request_id, None)


bridge_server = BrowserBridgeServer()


async def ensure_started(port: int = DEFAULT_PORT) -> BrowserBridgeServer:
    if bridge_server.server is None:
        bridge_server.port = int(port or DEFAULT_PORT)
        await bridge_server.start()
    return bridge_server
