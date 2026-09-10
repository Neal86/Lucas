from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from starlette.websockets import WebSocket

DISCONNECT_GRACE_SECONDS = 20.0
DURABLE_DISCONNECT_GRACE_SECONDS = 180.0
log = logging.getLogger("lucas.gateway")


@dataclass
class NodeConnection:
    node_id: str
    name: str
    allowed_roots: list[str]
    websocket: WebSocket
    runtime_id: str = ""
    last_seen: float = field(default_factory=time.time)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class ControlLock:
    owner_user_id: str
    context_id: str
    expires_at: float


class NodeRegistry:
    def __init__(self, bindings=None) -> None:
        self.bindings = bindings
        self.nodes: dict[str, NodeConnection] = {}
        self.control_locks: dict[str, ControlLock] = {}
        self.pending_requests: dict[str, dict[str, asyncio.Future]] = {}
        self.pending_payloads: dict[str, dict[str, dict[str, Any]]] = {}
        self.runtime_ids: dict[str, str] = {}
        self.disconnect_epochs: dict[str, int] = {}

    async def list(self, user) -> list[dict]:
        now = time.time()
        out = []
        actor = {"user_id": user.id, "email": user.email, "name": user.name or ""}
        for node_id in self.bindings.node_ids(user.id):
            node = self.nodes.get(node_id)
            if not node:
                continue
            try:
                access = await self.rpc(node.node_id, user.id, "access.check", {}, actor=actor, timeout=3.0)
            except Exception:
                continue
            if not isinstance(access, dict) or not access.get("authorized"):
                self.bindings.remove(user.id, node.node_id)
                continue
            preset = str(access.get("preset") or "request_approval")
            allowed_roots = [str(item) for item in access.get("allowed_roots") or []]
            lock = self.control_locks.get(node.node_id)
            if lock and lock.expires_at <= now:
                self.control_locks.pop(node.node_id, None)
                lock = None
            out.append({
                "node_id": node.node_id, "name": node.name, "preset": preset,
                "allowed_roots": allowed_roots, "online": True, "last_seen": node.last_seen,
                "shared": True, "local_authority": True,
                "control_context": lock.context_id if lock and lock.owner_user_id == user.id else None,
                "control_expires_at": lock.expires_at if lock and lock.owner_user_id == user.id else None,
            })
        return out

    def require_online(self, node_id: str) -> NodeConnection:
        node = self.nodes.get(node_id)
        if not node:
            raise RuntimeError(f"Node is offline: {node_id}")
        return node

    async def wait_online(self, node_id: str, timeout: float = DISCONNECT_GRACE_SECONDS) -> NodeConnection:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            node = self.nodes.get(node_id)
            if node:
                return node
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Node is offline: {node_id}")
            await asyncio.sleep(0.1)

    def register_connection(self, node_id: str, runtime_id: str) -> bool:
        previous = self.runtime_ids.get(node_id)
        self.runtime_ids[node_id] = runtime_id
        self.disconnect_epochs[node_id] = self.disconnect_epochs.get(node_id, 0) + 1
        same_runtime = not previous or not runtime_id or previous == runtime_id
        if previous and runtime_id and previous != runtime_id:
            pending = self.pending_requests.get(node_id, {})
            payloads = self.pending_payloads.get(node_id, {})
            for request_id, future in list(pending.items()):
                method = str((payloads.get(request_id) or {}).get("method") or "")
                if method == "shell.run":
                    continue
                pending.pop(request_id, None)
                payloads.pop(request_id, None)
                if not future.done():
                    future.set_exception(RuntimeError(f"Node restarted during non-durable operation: {node_id}"))
            if not pending:
                self.pending_requests.pop(node_id, None)
            if not payloads:
                self.pending_payloads.pop(node_id, None)
        return same_runtime

    def begin_disconnect_grace(self, node_id: str) -> None:
        epoch = self.disconnect_epochs.get(node_id, 0) + 1
        self.disconnect_epochs[node_id] = epoch

        async def expire() -> None:
            await asyncio.sleep(DISCONNECT_GRACE_SECONDS)
            if self.disconnect_epochs.get(node_id) != epoch or node_id in self.nodes:
                return
            self.control_locks.pop(node_id, None)
            pending = self.pending_requests.get(node_id, {})
            payloads = self.pending_payloads.get(node_id, {})
            for request_id, future in list(pending.items()):
                method = str((payloads.get(request_id) or {}).get("method") or "")
                if method == "shell.run":
                    continue
                pending.pop(request_id, None)
                payloads.pop(request_id, None)
                if not future.done():
                    future.set_exception(RuntimeError(f"Node disconnected: {node_id}"))
            if not pending:
                self.pending_requests.pop(node_id, None)
            if not payloads:
                self.pending_payloads.pop(node_id, None)
                return

            await asyncio.sleep(max(0.0, DURABLE_DISCONNECT_GRACE_SECONDS - DISCONNECT_GRACE_SECONDS))
            if self.disconnect_epochs.get(node_id) != epoch or node_id in self.nodes:
                return
            pending = self.pending_requests.pop(node_id, {})
            self.pending_payloads.pop(node_id, None)
            for future in pending.values():
                if not future.done():
                    future.set_exception(RuntimeError(f"Node did not recover durable operation in time: {node_id}"))

        asyncio.create_task(expire())

    async def replay_pending(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if not node:
            return
        payloads = list(self.pending_payloads.get(node_id, {}).values())
        for payload in payloads:
            async with node.send_lock:
                await node.websocket.send_json(payload)
        if payloads:
            log.info("Replayed %d pending RPC(s) after Node reconnect node_id=%s", len(payloads), node_id)

    def acquire_control(self, node_id: str, user_id: str, context_id: str, ttl_seconds: int = 120) -> dict:
        now = time.time()
        ttl_seconds = max(15, min(ttl_seconds, 1800))
        current = self.control_locks.get(node_id)
        if current and current.expires_at > now and (current.owner_user_id != user_id or current.context_id != context_id):
            raise RuntimeError(f"Node {node_id} is controlled by another AI context")
        lock = ControlLock(owner_user_id=user_id, context_id=context_id, expires_at=now + ttl_seconds)
        self.control_locks[node_id] = lock
        return {"node_id": node_id, "context": context_id, "expires_at": lock.expires_at}

    def release_control(self, node_id: str, user_id: str, context_id: str) -> dict:
        current = self.control_locks.get(node_id)
        if current and current.owner_user_id == user_id and current.context_id == context_id:
            self.control_locks.pop(node_id, None)
            return {"released": True, "node_id": node_id, "context": context_id}
        return {"released": False, "node_id": node_id, "context": context_id}

    def control_status(self, node_id: str, user_id: str) -> dict:
        now = time.time()
        current = self.control_locks.get(node_id)
        if current and current.expires_at <= now:
            self.control_locks.pop(node_id, None)
            current = None
        return {
            "node_id": node_id,
            "context": current.context_id if current and current.owner_user_id == user_id else None,
            "expires_at": current.expires_at if current and current.owner_user_id == user_id else None,
        }

    async def rpc(self, node_id: str, user_id: str, method: str, params: dict, timeout: float = 180.0, actor: dict | None = None) -> Any:
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        payload = {"type": "request", "id": request_id, "method": method, "params": params, "actor": actor or {"user_id": user_id}}
        pending = self.pending_requests.setdefault(node_id, {})
        payloads = self.pending_payloads.setdefault(node_id, {})
        pending[request_id] = future
        payloads[request_id] = payload
        started = time.monotonic()
        try:
            node = await self.wait_online(node_id, min(DISCONNECT_GRACE_SECONDS, timeout))
            try:
                async with node.send_lock:
                    await node.websocket.send_json(payload)
            except Exception:
                remaining = max(0.1, min(DISCONNECT_GRACE_SECONDS, timeout - (time.monotonic() - started)))
                node = await self.wait_online(node_id, remaining)
                async with node.send_lock:
                    await node.websocket.send_json(payload)
            remaining = max(0.1, timeout - (time.monotonic() - started))
            return await asyncio.wait_for(future, timeout=remaining)
        finally:
            pending.pop(request_id, None)
            payloads.pop(request_id, None)
            if not pending:
                self.pending_requests.pop(node_id, None)
            if not payloads:
                self.pending_payloads.pop(node_id, None)

    def resolve(self, node_id: str, message: dict) -> None:
        node = self.nodes.get(node_id)
        if node:
            node.last_seen = time.time()
        future = self.pending_requests.get(node_id, {}).get(str(message.get("id") or ""))
        if not future or future.done():
            return
        if message.get("ok"):
            future.set_result(message.get("result"))
        else:
            future.set_exception(RuntimeError(message.get("error") or "Node execution failed"))
