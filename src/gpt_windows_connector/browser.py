from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


@dataclass
class BrowserSession:
    context: BrowserContext
    browser: Browser | None = None
    playwright: object | None = None


_SESSIONS: dict[str, BrowserSession] = {}
_LOCK = asyncio.Lock()


async def connect_cdp(endpoint: str = "http://127.0.0.1:9222") -> dict:
    async with _LOCK:
        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(endpoint)
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        session_id = uuid.uuid4().hex
        _SESSIONS[session_id] = BrowserSession(context=context, browser=browser, playwright=pw)
        return {"session_id": session_id, "pages": len(context.pages), "endpoint": endpoint}


async def launch_persistent(user_data_dir: str, executable_path: str | None = None, headless: bool = False) -> dict:
    async with _LOCK:
        pw = await async_playwright().start()
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(Path(user_data_dir).expanduser().resolve()),
            executable_path=executable_path,
            headless=headless,
        )
        session_id = uuid.uuid4().hex
        _SESSIONS[session_id] = BrowserSession(context=context, playwright=pw)
        return {"session_id": session_id, "pages": len(context.pages)}


def _session(session_id: str) -> BrowserSession:
    session = _SESSIONS.get(session_id)
    if not session:
        raise KeyError(f"Unknown browser session: {session_id}")
    return session


def _page(session_id: str, page_index: int = 0) -> Page:
    pages = _session(session_id).context.pages
    if not pages:
        raise RuntimeError("Browser context has no pages")
    if page_index < 0 or page_index >= len(pages):
        raise IndexError(f"page_index out of range: {page_index}")
    return pages[page_index]


async def pages(session_id: str) -> list[dict]:
    result = []
    for index, page in enumerate(_session(session_id).context.pages):
        result.append({"index": index, "url": page.url, "title": await page.title()})
    return result


async def new_page(session_id: str, url: str | None = None) -> dict:
    page = await _session(session_id).context.new_page()
    if url:
        await page.goto(url, wait_until="domcontentloaded")
    return {"index": len(_session(session_id).context.pages) - 1, "url": page.url, "title": await page.title()}


async def navigate(session_id: str, url: str, page_index: int = 0) -> dict:
    page = _page(session_id, page_index)
    response = await page.goto(url, wait_until="domcontentloaded")
    return {"url": page.url, "title": await page.title(), "status": response.status if response else None}


async def inspect(session_id: str, page_index: int = 0, selector: str = "body", max_chars: int = 30000) -> dict:
    page = _page(session_id, page_index)
    locator = page.locator(selector).first
    return {"url": page.url, "title": await page.title(), "text": (await locator.inner_text())[:max_chars]}


async def click(session_id: str, selector: str, page_index: int = 0) -> dict:
    page = _page(session_id, page_index)
    await page.locator(selector).first.click()
    return {"selector": selector, "url": page.url}


async def type_text(session_id: str, selector: str, text: str, page_index: int = 0, clear: bool = True) -> dict:
    locator = _page(session_id, page_index).locator(selector).first
    if clear:
        await locator.fill(text)
    else:
        await locator.press_sequentially(text)
    return {"selector": selector, "characters": len(text)}


async def select_option(session_id: str, selector: str, value: str, page_index: int = 0) -> dict:
    selected = await _page(session_id, page_index).locator(selector).first.select_option(value=value)
    return {"selector": selector, "selected": selected}


async def upload(session_id: str, selector: str, paths: list[str], page_index: int = 0) -> dict:
    await _page(session_id, page_index).locator(selector).first.set_input_files(paths)
    return {"selector": selector, "files": paths}


async def screenshot(session_id: str, page_index: int = 0, full_page: bool = False) -> dict:
    import base64
    data = await _page(session_id, page_index).screenshot(full_page=full_page)
    return {"mime_type": "image/png", "base64": base64.b64encode(data).decode("ascii")}


async def close(session_id: str) -> dict:
    session = _SESSIONS.pop(session_id, None)
    if not session:
        return {"closed": False}
    await session.context.close()
    if session.browser:
        await session.browser.close()
    if session.playwright:
        await session.playwright.stop()
    return {"closed": True}
