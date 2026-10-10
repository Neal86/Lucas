"""Page-local, observation-scoped references for background browser interaction."""
from __future__ import annotations

import uuid
from typing import Any


TARGET_SELECTOR = "button,a,input,textarea,select,[role=button],[role=link],[role=checkbox],[role=radio],[contenteditable=true]"

# Never read input values: snapshots must not return passwords or entered secrets.
DESCRIBE = """e => ({
  tag:e.tagName.toLowerCase(), role:e.getAttribute('role')||'',
  text:(e.innerText||'').trim().slice(0,300), name:e.getAttribute('name')||'',
  aria_label:e.getAttribute('aria-label')||'', placeholder:e.getAttribute('placeholder')||'',
  type:e.getAttribute('type')||'', id:e.id||'', disabled:!!e.disabled,
  connected:e.isConnected,
  visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length) &&
    getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none'
})"""


def identity(item: dict[str, Any]) -> tuple:
    return tuple(item.get(key) for key in ("tag", "role", "text", "name", "aria_label", "placeholder", "type", "id"))


async def observe_page(page, limit: int = 300) -> dict:
    limit = max(1, min(int(limit), 1000))
    previous = getattr(page, "_lucas_targets", {})
    page._lucas_targets = {}
    for handle, _ in previous.values():
        await handle.dispose()
    prefix = "ref:" + uuid.uuid4().hex[:12] + ":"
    elements = []
    # Handles retain DOM identity even if the page inserts/reorders elements.
    handles = await page.locator(TARGET_SELECTOR).element_handles()
    try:
        for handle in handles:
            item = await handle.evaluate(DESCRIBE)
            if not item.get("visible") or not item.get("connected") or len(elements) >= limit:
                await handle.dispose()
                continue
            ref = prefix + str(len(elements))
            page._lucas_targets[ref] = (handle, identity(item))
            elements.append({"index": len(elements), "ref": ref, **item})
    except Exception:
        for handle in handles:
            await handle.dispose()
        page._lucas_targets = {}
        raise
    return {"url": page.url, "title": await page.title(), "elements": elements,
            "target_hint": "Use an element ref as semantic_click/semantic_type target. Re-observe after navigation or stale-target errors."}


async def reference_target(page, target: str):
    record = getattr(page, "_lucas_targets", {}).get(target)
    if record is None:
        raise LookupError("Unknown or expired element ref on this tab. Call observe again.")
    handle, expected = record
    try:
        item = await handle.evaluate(DESCRIBE)
    except Exception as exc:
        raise LookupError("Stale element ref. Call observe again.") from exc
    if not item.get("connected") or not item.get("visible") or identity(item) != expected:
        raise LookupError("Element changed or disappeared. Call observe again.")
    if item.get("disabled"):
        raise LookupError("Referenced element is disabled.")
    return handle


async def unique_visible(locator, target: str):
    matches = []
    for index in range(await locator.count()):
        item = locator.nth(index)
        if await item.is_visible():
            matches.append(item)
    if len(matches) > 1:
        raise LookupError(f"Ambiguous browser target: {target}. Call observe and use an element ref.")
    return matches[0] if matches else None
