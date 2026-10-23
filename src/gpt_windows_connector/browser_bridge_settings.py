"""Authenticated loopback IPC for the separate local Settings process."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any

from .settings_constants import CONFIG_DIR

TOKEN_FILE = CONFIG_DIR / "browser-settings-token"


class BridgeSettingsEndpoint:
    def __init__(self, bridge, registry, token_file: Path = TOKEN_FILE) -> None:
        self.bridge = bridge
        self.registry = registry
        self.token_file = token_file
        self.token = secrets.token_urlsafe(32)

    def activate(self) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        # Token is local to this Windows account, never returned by remote MCP.
        fd = os.open(self.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(self.token)

    async def handle(self, websocket) -> None:
        headers = websocket.request.headers
        supplied = str(headers.get("Authorization") or "")
        if headers.get("Origin") or not secrets.compare_digest(supplied, "Bearer " + self.token):
            await websocket.close(code=4403, reason="local Settings authorization required")
            return
        try:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
            result = await self.dispatch(message)
            await websocket.send(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        except Exception as exc:
            await websocket.send(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))

    async def dispatch(self, message: dict[str, Any]) -> Any:
        action = message.get("action")
        installation_id = str(message.get("installation_id") or "")
        if action == "status":
            return {"running": True, "clients": self.bridge.list_clients()}
        if action == "pair":
            pending = self.bridge.pending.get(installation_id) or {}
            return await self.bridge.pair(
                installation_id, pairing_code=str(message.get("pairing_code") or ""),
                browser_type=str(pending.get("browser_type") or "chrome"),
                profile_name=str(message.get("profile_name") or pending.get("profile_name") or ""),
            )
        if action == "disconnect":
            profile = self.registry.profile_for_bridge(installation_id)
            if profile:
                # Disable this identity without deleting its profiles or task history.
                self.registry.upsert_profile({**profile, "enabled": False})
            client = self.bridge.clients.get(installation_id)
            if client:
                client.paired = False
                await client.websocket.close(code=4003, reason="authorization revoked locally")
            return {"disconnected": True}
        raise ValueError("Unknown local browser settings action")


def settings_request(action: str = "status", *, token_file: Path = TOKEN_FILE, port: int = 8766, **params) -> Any:
    from websockets.sync.client import connect

    token = token_file.read_text(encoding="utf-8").strip()
    with connect(
        f"ws://127.0.0.1:{int(port)}/settings",
        additional_headers={"Authorization": "Bearer " + token},
        proxy=None, open_timeout=2, close_timeout=1, max_size=1024 * 1024,
    ) as websocket:
        websocket.send(json.dumps({"action": action, **params}))
        response = json.loads(websocket.recv(timeout=3))
    if not response.get("ok"):
        raise RuntimeError(response.get("error") or "Local browser settings request failed")
    return response["result"]
