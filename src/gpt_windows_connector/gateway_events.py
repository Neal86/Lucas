from __future__ import annotations

import asyncio
from starlette.websockets import WebSocket

class BrowserEventHub:
    def __init__(self) -> None:
        self.clients: dict[str, set[WebSocket]] = {}

    def subscribe(self, user_id: str, websocket: WebSocket) -> None:
        self.clients.setdefault(user_id, set()).add(websocket)

    def unsubscribe(self, user_id: str, websocket: WebSocket) -> None:
        sockets = self.clients.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self.clients.pop(user_id, None)

    async def publish(self, user_id: str, event_type: str, payload: dict | None = None) -> None:
        sockets = tuple(self.clients.get(user_id, ()))
        if not sockets:
            return
        message = {"type": event_type, **(payload or {})}
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await asyncio.wait_for(socket.send_json(message), timeout=2)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.unsubscribe(user_id, socket)
