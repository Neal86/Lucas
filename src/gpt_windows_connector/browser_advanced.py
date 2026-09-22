from __future__ import annotations

import asyncio
from typing import Any

from . import browser


def _timeout(value: int | None, default: int = 15000) -> int:
    return max(250, min(int(value or default), 120000))


async def aria_snapshot(
    session_id: str,
    page_index: int = 0,
    selector: str = "body",
    timeout_ms: int = 10000,
    max_chars: int = 50000,
) -> dict[str, Any]:
    """Return a Playwright ARIA snapshot for model-friendly semantic page reading."""
    page = browser._page(session_id, page_index)
    locator = page.locator(selector).first
    try:
        snapshot = await locator.aria_snapshot(timeout=_timeout(timeout_ms, 10000))
        return {
            "url": page.url,
            "title": await page.title(),
            "selector": selector,
            "aria": str(snapshot or "")[: max(1000, min(int(max_chars or 50000), 200000))],
            "fallback": False,
        }
    except Exception as exc:
        text = (await locator.inner_text())[: max(1000, min(int(max_chars or 50000), 200000))]
        return {
            "url": page.url,
            "title": await page.title(),
            "selector": selector,
            "aria": text,
            "fallback": True,
            "warning": f"ARIA snapshot unavailable: {type(exc).__name__}",
        }


async def wait_for(
    session_id: str,
    page_index: int = 0,
    *,
    selector: str | None = None,
    text: str | None = None,
    url_contains: str | None = None,
    state: str = "domcontentloaded",
    timeout_ms: int = 15000,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    timeout = _timeout(timeout_ms)
    if selector:
        await page.locator(selector).first.wait_for(state="visible", timeout=timeout)
        waited_for = f"selector:{selector}"
    elif text:
        await page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=timeout)
        waited_for = f"text:{text}"
    elif url_contains:
        await page.wait_for_url(f"**{url_contains}**", timeout=timeout, wait_until="domcontentloaded")
        waited_for = f"url:{url_contains}"
    else:
        allowed = {"load", "domcontentloaded", "networkidle", "commit"}
        wait_state = state if state in allowed else "domcontentloaded"
        await page.wait_for_load_state(wait_state, timeout=timeout)
        waited_for = f"state:{wait_state}"
    return {"waited": True, "waited_for": waited_for, "url": page.url, "title": await page.title()}


async def reload_page(
    session_id: str,
    page_index: int = 0,
    *,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    response = await page.reload(wait_until=wait_until, timeout=_timeout(timeout_ms, 30000))
    return {"url": page.url, "title": await page.title(), "status": response.status if response else None}


async def go_back(
    session_id: str,
    page_index: int = 0,
    *,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    response = await page.go_back(wait_until=wait_until, timeout=_timeout(timeout_ms, 30000))
    return {"url": page.url, "title": await page.title(), "status": response.status if response else None}


async def go_forward(
    session_id: str,
    page_index: int = 0,
    *,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    response = await page.go_forward(wait_until=wait_until, timeout=_timeout(timeout_ms, 30000))
    return {"url": page.url, "title": await page.title(), "status": response.status if response else None}


async def press_key(
    session_id: str,
    key: str,
    page_index: int = 0,
    *,
    target: str | None = None,
    timeout_ms: int = 10000,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    if target:
        locator = page.get_by_label(target, exact=False)
        if not await locator.count():
            locator = page.get_by_text(target, exact=False)
        if not await locator.count():
            locator = page.locator(target)
        await locator.first.press(str(key), timeout=_timeout(timeout_ms, 10000))
        strategy = "target"
    else:
        await page.keyboard.press(str(key))
        strategy = "page"
    return {"pressed": str(key), "strategy": strategy, "url": page.url}


async def hover(
    session_id: str,
    target: str,
    page_index: int = 0,
    *,
    timeout_ms: int = 10000,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    locator = page.get_by_text(target, exact=False)
    if not await locator.count():
        locator = page.locator(target)
    await locator.first.hover(timeout=_timeout(timeout_ms, 10000))
    return {"hovered": target, "url": page.url}


async def scroll(
    session_id: str,
    page_index: int = 0,
    *,
    delta_x: int = 0,
    delta_y: int = 700,
    target: str | None = None,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    if target:
        locator = page.get_by_text(target, exact=False)
        if not await locator.count():
            locator = page.locator(target)
        await locator.first.scroll_into_view_if_needed()
        return {"scrolled": True, "target": target, "url": page.url}
    await page.mouse.wheel(int(delta_x or 0), int(delta_y or 0))
    await asyncio.sleep(0.05)
    return {"scrolled": True, "delta_x": int(delta_x or 0), "delta_y": int(delta_y or 0), "url": page.url}


async def close_page(session_id: str, page_index: int = 0) -> dict[str, Any]:
    session = browser._session(session_id)
    page = browser._page(session_id, page_index)
    url = page.url
    await page.close()
    return {"closed": True, "url": url, "pages": len(session.context.pages)}


async def network_summary(
    session_id: str,
    page_index: int = 0,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Return same-page Resource Timing data without exposing cookies or request bodies."""
    page = browser._page(session_id, page_index)
    max_items = max(1, min(int(limit or 100), 500))
    resources = await page.evaluate(
        """(limit) => performance.getEntriesByType('resource').slice(-limit).map((r) => ({
          name: String(r.name || '').slice(0, 2000),
          initiatorType: String(r.initiatorType || ''),
          duration: Math.round(Number(r.duration || 0)),
          transferSize: Number(r.transferSize || 0),
          decodedBodySize: Number(r.decodedBodySize || 0)
        }))""",
        max_items,
    )
    return {"url": page.url, "resources": resources, "count": len(resources)}
