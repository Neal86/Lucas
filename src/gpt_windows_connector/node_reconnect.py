from __future__ import annotations

import asyncio
import secrets
import sys
import time

RUNTIME_ID = secrets.token_hex(8)
RESPONSE_CACHE_SECONDS = 600.0
_active_sender = None
request_tasks: set[asyncio.Task[None]] = set()
inflight_request_ids: set[str] = set()
completed_responses: dict[str, tuple[float, dict[str, object]]] = {}


class NodeSessionDisconnected(ConnectionError):
    """A previously established Gateway session was lost. Retry direct immediately."""


def disconnect_reason(exc: Exception) -> str:
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


def is_gateway_restart_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(term in text for term in ("1012", "service restart", "http 502", "http 503", "bad gateway", "service unavailable"))


def set_active_sender(sender) -> None:
    global _active_sender
    _active_sender = sender


def clear_active_sender(sender) -> None:
    global _active_sender
    if _active_sender is sender:
        _active_sender = None


async def deliver_response(response: dict[str, object]) -> None:
    request_id = str(response.get("id") or "")
    now = time.time()
    for cached_id, (created_at, _) in list(completed_responses.items()):
        if now - created_at > RESPONSE_CACHE_SECONDS:
            completed_responses.pop(cached_id, None)
    if request_id:
        completed_responses[request_id] = (now, response)
    sender = _active_sender
    if sender is None:
        return
    try:
        await sender(response)
    except Exception:
        return


async def flush_completed_responses(sender) -> None:
    for _, response in list(completed_responses.values()):
        await sender(response)


def acquire_node_mutex(log) -> object | None:
    if sys.platform != "win32":
        return object()
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\LucasNodeSingleInstance")
        if not handle:
            return None
        if kernel32.GetLastError() == 183:
            kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        log.exception("Could not create node single-instance mutex")
        return object()
