from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from . import browser


@dataclass
class _PageDiagnostics:
    console: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=300))
    page_errors: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=100))
    request_failures: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))
    http_errors: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))


_BUFFERS: dict[int, _PageDiagnostics] = {}
_ATTACHED: set[int] = set()


def _buffer(page) -> _PageDiagnostics:
    key = id(page)
    existing = _BUFFERS.get(key)
    if existing is None:
        existing = _PageDiagnostics()
        _BUFFERS[key] = existing
    return existing


def attach_page(page) -> None:
    key = id(page)
    if key in _ATTACHED:
        return
    _ATTACHED.add(key)
    buf = _buffer(page)

    def on_console(message) -> None:
        try:
            buf.console.append({
                "type": str(message.type or ""),
                "text": str(message.text or "")[:4000],
                "location": dict(message.location or {}),
            })
        except Exception:
            pass

    def on_page_error(error) -> None:
        try:
            buf.page_errors.append({
                "message": str(error)[:4000],
                "name": type(error).__name__,
            })
        except Exception:
            pass

    def on_request_failed(request) -> None:
        try:
            buf.request_failures.append({
                "method": str(request.method or ""),
                "url": str(request.url or "")[:3000],
                "resource_type": str(request.resource_type or ""),
                "failure": str(request.failure or "")[:2000],
            })
        except Exception:
            pass

    def on_response(response) -> None:
        try:
            if int(response.status or 0) >= 400:
                buf.http_errors.append({
                    "status": int(response.status or 0),
                    "status_text": str(response.status_text or "")[:500],
                    "url": str(response.url or "")[:3000],
                })
        except Exception:
            pass

    def on_close() -> None:
        _ATTACHED.discard(key)
        _BUFFERS.pop(key, None)

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)
    page.on("close", lambda *_: on_close())


def attach_context(context) -> None:
    for page in context.pages:
        attach_page(page)
    context.on("page", attach_page)


async def diagnostics(
    session_id: str,
    page_index: int = 0,
    *,
    limit: int = 100,
    clear: bool = False,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    attach_page(page)
    buf = _buffer(page)
    n = max(1, min(int(limit or 100), 300))
    result = {
        "url": page.url,
        "title": await page.title(),
        "console": list(buf.console)[-n:],
        "page_errors": list(buf.page_errors)[-n:],
        "request_failures": list(buf.request_failures)[-n:],
        "http_errors": list(buf.http_errors)[-n:],
    }
    if clear:
        buf.console.clear()
        buf.page_errors.clear()
        buf.request_failures.clear()
        buf.http_errors.clear()
        result["cleared"] = True
    return result
