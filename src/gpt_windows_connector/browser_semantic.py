from __future__ import annotations

import re
from typing import Any

from . import browser


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def score_page(title: str, url: str, query: str = "", title_contains: str = "", url_contains: str = "") -> int:
    title_n, url_n, query_n = _norm(title), _norm(url), _norm(query)
    score = 0
    if title_contains and _norm(title_contains) in title_n:
        score += 70
    if url_contains and _norm(url_contains) in url_n:
        score += 80
    if query_n:
        terms = [term for term in re.split(r"[^a-z0-9._-]+", query_n) if len(term) > 1]
        for term in terms:
            if term in url_n:
                score += 18
            if term in title_n:
                score += 12
        if query_n in url_n:
            score += 45
        if query_n in title_n:
            score += 35
    return score


async def resolve_target(session_id: str | None = None, query: str = "", title_contains: str = "", url_contains: str = "", prefer_page_index: int | None = None) -> dict:
    """Resolve the most likely connected browser tab from semantic hints."""
    session_ids = [session_id] if session_id else list(browser._SESSIONS)
    candidates: list[dict[str, Any]] = []
    for sid in session_ids:
        session = browser._session(sid)
        for index, page in enumerate(session.context.pages):
            title = await page.title()
            score = score_page(title, page.url, query, title_contains, url_contains)
            if prefer_page_index is not None and index == prefer_page_index:
                score += 8
            candidates.append({"session_id": sid, "page_index": index, "url": page.url, "title": title, "score": score})
    candidates.sort(key=lambda item: item["score"], reverse=True)
    if not candidates:
        return {"resolved": False, "reason": "No connected browser sessions. Use browser.discover, then connect_cdp or launch_persistent.", "candidates": []}
    best = candidates[0]
    return {"resolved": True, **best, "candidates": candidates[:10]}


async def observe(session_id: str, page_index: int = 0, limit: int = 300) -> dict:
    page = browser._page(session_id, page_index)
    items = await page.locator("button,a,input,textarea,select,[role=button],[role=link],[contenteditable=true]").evaluate_all(
        """(els, limit) => els.slice(0, limit).map((e, i) => ({
          index:i, tag:e.tagName.toLowerCase(), role:e.getAttribute('role')||'',
          text:(e.innerText||e.value||'').trim().slice(0,300), name:e.getAttribute('name')||'',
          aria_label:e.getAttribute('aria-label')||'', placeholder:e.getAttribute('placeholder')||'',
          type:e.getAttribute('type')||'', id:e.id||'', disabled:!!e.disabled,
          visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length)
        }))""",
        limit,
    )
    return {"url": page.url, "title": await page.title(), "elements": [item for item in items if item.get("visible")][:limit]}


def _looks_like_selector(target: str) -> bool:
    target = target.strip()
    return target.startswith(("#", ".", "[", "//", "xpath=", "css=")) or any(ch in target for ch in (">", "[", "="))


async def _locator(page, target: str, *, editable: bool):
    target = str(target or "").strip()
    if not target:
        raise ValueError("target is required")
    candidates = []
    if _looks_like_selector(target):
        candidates.append((page.locator(target), "selector"))
    if editable:
        candidates.extend([
            (page.get_by_label(target, exact=False), "label"),
            (page.get_by_placeholder(target, exact=False), "placeholder"),
            (page.get_by_role("textbox", name=target, exact=False), "textbox-role"),
        ])
    else:
        candidates.extend([
            (page.get_by_role("button", name=target, exact=False), "button-role"),
            (page.get_by_role("link", name=target, exact=False), "link-role"),
            (page.get_by_label(target, exact=False), "label"),
            (page.get_by_text(target, exact=False), "text"),
        ])
    for locator, strategy in candidates:
        try:
            if await locator.count():
                return locator.first, strategy
        except Exception:
            continue
    raise LookupError(f"No semantic browser element matched: {target}")


async def semantic_click(session_id: str, target: str, page_index: int = 0, timeout_ms: int = 10000) -> dict:
    page = browser._page(session_id, page_index)
    locator, strategy = await _locator(page, target, editable=False)
    await locator.scroll_into_view_if_needed(timeout=timeout_ms)
    await locator.click(timeout=timeout_ms)
    return {"target": target, "strategy": strategy, "url": page.url, "title": await page.title()}


async def semantic_type(session_id: str, target: str, text: str, page_index: int = 0, clear: bool = True, timeout_ms: int = 10000) -> dict:
    page = browser._page(session_id, page_index)
    locator, strategy = await _locator(page, target, editable=True)
    await locator.scroll_into_view_if_needed(timeout=timeout_ms)
    if clear:
        await locator.fill(text, timeout=timeout_ms)
    else:
        await locator.press_sequentially(text, timeout=timeout_ms)
    return {"target": target, "strategy": strategy, "characters": len(text), "url": page.url}
