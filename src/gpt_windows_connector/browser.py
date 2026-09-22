from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
import psutil


@dataclass
class BrowserSession:
    context: BrowserContext
    browser: Browser | None = None
    playwright: object | None = None
    browser_name: str | None = None
    profile: str | None = None
    user_data_dir: str | None = None
    endpoint: str | None = None


_SESSIONS: dict[str, BrowserSession] = {}
_LOCK = asyncio.Lock()


def discover_browsers() -> list[dict]:
    """Discover common Chromium browsers and profile directories on Windows."""
    env = os.environ
    candidates = [
        ("chrome", Path(env.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe", Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"),
        ("chrome", Path(env.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe", Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"),
        ("chrome", Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe", Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"),
        ("edge", Path(env.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe", Path(env.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data"),
        ("edge", Path(env.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe", Path(env.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data"),
        ("ixbrowser", Path(env.get("LOCALAPPDATA", "")) / "ixbrowser/ixbrowser.exe", Path(env.get("LOCALAPPDATA", "")) / "ixbrowser"),
    ]
    seen: set[str] = set()
    out: list[dict] = []
    for name, executable, user_data in candidates:
        if not executable or not executable.exists():
            continue
        key = str(executable.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        profiles: list[str] = []
        if user_data.exists() and user_data.is_dir():
            for child in user_data.iterdir():
                if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile ")):
                    profiles.append(child.name)
        out.append({
            "name": name,
            "executable_path": str(executable.resolve()),
            "user_data_dir": str(user_data.resolve()) if user_data.exists() else str(user_data),
            "profiles": profiles,
        })
    return out


def _local_cdp_port(endpoint: str) -> int | None:
    text = str(endpoint or "").strip().lower()
    if not (text.startswith("http://127.0.0.1:") or text.startswith("http://localhost:")):
        return None
    try:
        return int(text.rsplit(":", 1)[1].split("/", 1)[0])
    except Exception:
        return None


def _dedicated_profile_dir(profile: str | None) -> Path | None:
    if not profile:
        return None
    return (Path.home() / ".lucas" / "browser-profiles" / profile).resolve()


def _chrome_executable(browser_name: str | None = None) -> Path | None:
    wanted = (browser_name or "chrome").lower()
    for item in discover_browsers():
        if str(item.get("name") or "").lower() == wanted:
            p = Path(str(item.get("executable") or ""))
            if p.exists():
                return p
    return None


def _wait_cdp_http(endpoint: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    url = endpoint.rstrip("/") + "/json/version"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            if payload.get("webSocketDebuggerUrl"):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _restart_dedicated_browser(endpoint: str, browser_name: str | None, profile: str | None) -> bool:
    port = _local_cdp_port(endpoint)
    profile_dir = _dedicated_profile_dir(profile)
    executable = _chrome_executable(browser_name)
    if port is None or profile_dir is None or executable is None:
        return False
    marker = str(profile_dir).lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if marker in cmd:
                proc.terminate()
        except Exception:
            pass
    time.sleep(1.0)
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if marker in cmd and proc.is_running():
                proc.kill()
        except Exception:
            pass
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = " ".join(
        [
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={port}",
            f'--user-data-dir="{profile_dir}"',
            "--no-first-run",
            "--no-default-browser-check",
            "https://www.google.com",
        ]
    )
    if os.name == "nt":
        # ShellExecute is more reliable for restarting an interactive browser
        # from the tray/background Node than CreateProcess/Popen.
        os.startfile(str(executable), "open", args, None, 1)
    else:
        subprocess.Popen(
            [str(executable), *args.split()],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return _wait_cdp_http(endpoint, timeout=10.0)


async def _connect_cdp_once(endpoint: str, browser_name: str | None, profile: str | None) -> dict:
    pw = None
    browser = None
    try:
        pw = await asyncio.wait_for(async_playwright().start(), timeout=8.0)
        browser = await asyncio.wait_for(
            pw.chromium.connect_over_cdp(endpoint, timeout=7000),
            timeout=10.0,
        )
        contexts = browser.contexts
        context = contexts[0] if contexts else await asyncio.wait_for(browser.new_context(), timeout=5.0)
        from . import browser_diagnostics
        browser_diagnostics.attach_context(context)
        session_id = uuid.uuid4().hex
        async with _LOCK:
            _SESSIONS[session_id] = BrowserSession(
                context=context,
                browser=browser,
                playwright=pw,
                browser_name=browser_name,
                profile=profile,
                endpoint=endpoint,
            )
        return {"session_id": session_id, "pages": len(context.pages), "endpoint": endpoint, "browser_name": browser_name, "profile": profile, "reused": False}
    except Exception:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if pw is not None:
            try:
                await pw.stop()
            except Exception:
                pass
        raise


async def connect_cdp(endpoint: str = "http://127.0.0.1:9222", browser_name: str | None = None, profile: str | None = None) -> dict:
    # First try the existing dedicated browser. If its DevTools socket is stale,
    # restart only that isolated profile and retry once.
    try:
        return await _connect_cdp_once(endpoint, browser_name, profile)
    except Exception as first_error:
        if not profile:
            raise
        restarted = await asyncio.to_thread(_restart_dedicated_browser, endpoint, browser_name, profile)
        if not restarted:
            raise first_error
        result = await _connect_cdp_once(endpoint, browser_name, profile)
        result["restarted_browser"] = True
        return result


async def ensure_cdp(endpoint: str = "http://127.0.0.1:9222", browser_name: str | None = None, profile: str | None = None) -> dict:
    """Reuse an existing CDP session for the target browser, or connect once if needed."""
    async with _LOCK:
        for session_id, session in list(_SESSIONS.items()):
            if session.endpoint != endpoint:
                continue
            if browser_name and session.browser_name and session.browser_name.lower() != browser_name.lower():
                continue
            if profile and session.profile and session.profile.lower() != profile.lower():
                continue
            try:
                pages = len(session.context.pages)
            except Exception:
                continue
            return {"session_id": session_id, "pages": pages, "endpoint": endpoint, "browser_name": session.browser_name or browser_name, "profile": session.profile or profile, "reused": True}
    # Important: connect_cdp acquires _LOCK itself. Call it only after releasing
    # the ensure_cdp lookup lock, otherwise a fresh Node session deadlocks.
    return await connect_cdp(endpoint=endpoint, browser_name=browser_name, profile=profile)


async def launch_persistent(user_data_dir: str, executable_path: str | None = None, headless: bool = False, profile: str | None = None, browser_name: str | None = None) -> dict:
    async with _LOCK:
        pw = await async_playwright().start()
        resolved_data_dir = str(Path(user_data_dir).expanduser().resolve())
        args = [f"--profile-directory={profile}"] if profile else None
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=resolved_data_dir,
            executable_path=executable_path,
            headless=headless,
            accept_downloads=True,
            args=args,
        )
        from . import browser_diagnostics
        browser_diagnostics.attach_context(context)
        session_id = uuid.uuid4().hex
        _SESSIONS[session_id] = BrowserSession(context=context, playwright=pw, browser_name=browser_name, profile=profile, user_data_dir=resolved_data_dir)
        return {"session_id": session_id, "pages": len(context.pages), "browser_name": browser_name, "profile": profile, "user_data_dir": resolved_data_dir, "reused": False}


async def ensure_profile(user_data_dir: str, executable_path: str | None = None, headless: bool = False, profile: str | None = None, browser_name: str | None = None) -> dict:
    """Reuse or launch a persistent browser profile managed by Lucas."""
    resolved_data_dir = str(Path(user_data_dir).expanduser().resolve())
    async with _LOCK:
        for session_id, session in list(_SESSIONS.items()):
            if str(session.user_data_dir or "").lower() != resolved_data_dir.lower():
                continue
            if browser_name and session.browser_name and session.browser_name.lower() != browser_name.lower():
                continue
            if profile and session.profile and session.profile.lower() != profile.lower():
                continue
            try:
                pages = len(session.context.pages)
            except Exception:
                continue
            return {
                "session_id": session_id,
                "pages": pages,
                "browser_name": session.browser_name or browser_name,
                "profile": session.profile or profile,
                "user_data_dir": resolved_data_dir,
                "reused": True,
            }
    try:
        return await launch_persistent(
            user_data_dir=resolved_data_dir,
            executable_path=executable_path,
            headless=headless,
            profile=profile,
            browser_name=browser_name,
        )
    except Exception as first_error:
        marker = resolved_data_dir.lower()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = " ".join(proc.info.get("cmdline") or []).lower()
                if marker in cmd:
                    proc.terminate()
            except Exception:
                pass
        await asyncio.sleep(1.0)
        return await launch_persistent(
            user_data_dir=resolved_data_dir,
            executable_path=executable_path,
            headless=headless,
            profile=profile,
            browser_name=browser_name,
        )


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
        result.append({"index": index, "url": page.url, "title": await page.title(), "browser_name": _session(session_id).browser_name, "profile": _session(session_id).profile})
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


async def download(session_id: str, selector: str, save_path: str, page_index: int = 0) -> dict:
    page = _page(session_id, page_index)
    destination = Path(save_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with page.expect_download() as info:
        await page.locator(selector).first.click()
    item = await info.value
    await item.save_as(str(destination))
    return {"path": str(destination), "suggested_filename": item.suggested_filename}


async def screenshot(session_id: str, page_index: int = 0, full_page: bool = False, timeout_ms: int = 8000) -> dict:
    import base64
    page = _page(session_id, page_index)
    timeout_ms = max(1000, min(int(timeout_ms or 8000), 10000))
    try:
        data = await page.screenshot(full_page=full_page, timeout=timeout_ms)
        return {"mime_type": "image/png", "base64": base64.b64encode(data).decode("ascii"), "fallback": False}
    except Exception as exc:
        # Some pages can stall while Playwright waits for web fonts during screenshot.
        # Do not let a visual fallback block the whole browser workflow.
        try:
            data = await page.locator("body").screenshot(timeout=min(timeout_ms, 4000))
            return {
                "mime_type": "image/png",
                "base64": base64.b64encode(data).decode("ascii"),
                "fallback": True,
                "warning": f"Page screenshot fallback used: {type(exc).__name__}",
            }
        except Exception:
            return {
                "mime_type": None,
                "base64": None,
                "fallback": True,
                "warning": f"Screenshot unavailable: {type(exc).__name__}. Use observe/inspect instead.",
            }


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
