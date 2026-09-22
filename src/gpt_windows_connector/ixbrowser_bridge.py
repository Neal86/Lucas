from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from . import browser

DEFAULT_TARGET = "127.0.0.1"
DEFAULT_PORT = 53200

_SENSITIVE_PROFILE_FIELDS = {
    "password",
    "tfa_secret",
    "cookies",
    "cookie",
    "token",
    "access_token",
    "secret",
}


def _client(target: str = DEFAULT_TARGET, port: int = DEFAULT_PORT):
    try:
        from ixbrowser_local_api import IXBrowserClient
    except ImportError as exc:  # pragma: no cover - exercised only on nodes missing the optional runtime
        raise RuntimeError(
            "ixBrowser Local API support is not installed. Update Lucas Node, then enable "
            "Local API in ixBrowser before using ix_* browser actions."
        ) from exc
    return IXBrowserClient(target=str(target or DEFAULT_TARGET), port=int(port or DEFAULT_PORT))


def _close_client(client: object) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _error(client: object, operation: str) -> RuntimeError:
    code = getattr(client, "code", None)
    message = str(getattr(client, "message", "") or "unknown ixBrowser Local API error")
    return RuntimeError(f"ixBrowser {operation} failed (code={code}): {message}")


def normalize_debugging_address(value: object) -> str:
    address = str(value or "").strip()
    if not address:
        raise RuntimeError("ixBrowser did not return a debugging_address")
    if address.startswith(("http://", "https://", "ws://", "wss://")):
        return address
    return "http://" + address.lstrip("/")


def sanitize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Return useful ixBrowser profile metadata without credentials or 2FA secrets."""
    allowed = {
        "profile_id",
        "name",
        "group_id",
        "group_name",
        "tag_id",
        "tag_name",
        "site_url",
        "last_open_time",
        "proxy_mode",
        "proxy_type",
        "real_ip",
        "cache_path",
        "color",
        "note",
    }
    return {
        key: value
        for key, value in dict(profile or {}).items()
        if key in allowed and key not in _SENSITIVE_PROFILE_FIELDS
    }


def list_profiles(
    *,
    target: str = DEFAULT_TARGET,
    port: int = DEFAULT_PORT,
    profile_id: int | None = None,
    name: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    client = _client(target, port)
    try:
        kwargs: dict[str, Any] = {}
        if profile_id is not None:
            kwargs["profile_id"] = int(profile_id)
        if str(name or "").strip():
            kwargs["name"] = str(name).strip()
        kwargs["page"] = 1
        kwargs["limit"] = max(1, min(int(limit or 100), 1000))
        try:
            result = client.get_profile_list(**kwargs)
        except TypeError:
            # Keep compatibility with older SDK builds whose helper accepted no kwargs.
            result = client.get_profile_list()
        if result is None:
            raise _error(client, "profile list")
        items = list(result or [])
        if profile_id is not None:
            items = [item for item in items if int(item.get("profile_id") or 0) == int(profile_id)]
        if str(name or "").strip():
            wanted = str(name).strip().lower()
            items = [item for item in items if wanted in str(item.get("name") or "").lower()]
        return {
            "available": True,
            "target": str(target or DEFAULT_TARGET),
            "port": int(port or DEFAULT_PORT),
            "profiles": [sanitize_profile(item) for item in items[: max(1, min(int(limit or 100), 1000))]],
        }
    finally:
        _close_client(client)


def open_profile(
    profile_id: int,
    *,
    target: str = DEFAULT_TARGET,
    port: int = DEFAULT_PORT,
    cookies_backup: bool = False,
    load_profile_info_page: bool = False,
) -> dict[str, Any]:
    """Open an ixBrowser profile and return only the automation attachment metadata."""
    client = _client(target, port)
    try:
        result = client.open_profile(
            int(profile_id),
            cookies_backup=bool(cookies_backup),
            load_profile_info_page=bool(load_profile_info_page),
        )
        if result is None:
            raise _error(client, "open profile")
        data = dict(result or {})
        endpoint = normalize_debugging_address(data.get("debugging_address"))
        webdriver = str(data.get("webdriver") or "")
        return {
            "profile_id": int(profile_id),
            "debugging_address": str(data.get("debugging_address") or ""),
            "endpoint": endpoint,
            "webdriver": Path(webdriver).name if webdriver else None,
            "background_protocol": True,
        }
    finally:
        _close_client(client)


async def attach_profile(
    profile_id: int,
    *,
    target: str = DEFAULT_TARGET,
    port: int = DEFAULT_PORT,
    debugging_address: str | None = None,
    cookies_backup: bool = False,
    load_profile_info_page: bool = False,
) -> dict[str, Any]:
    """Open or attach to an ixBrowser profile, then reuse Lucas' Playwright/CDP engine."""
    if debugging_address:
        opened = {
            "profile_id": int(profile_id),
            "debugging_address": debugging_address,
            "endpoint": normalize_debugging_address(debugging_address),
            "webdriver": None,
            "background_protocol": True,
        }
    else:
        opened = await asyncio.to_thread(
            open_profile,
            int(profile_id),
            target=target,
            port=port,
            cookies_backup=cookies_backup,
            load_profile_info_page=load_profile_info_page,
        )
    session = await browser.connect_cdp(
        endpoint=str(opened["endpoint"]),
        browser_name="ixbrowser",
        profile=str(profile_id),
    )
    return {
        **session,
        "ixbrowser": True,
        "ix_profile_id": int(profile_id),
        "debugging_address": opened["debugging_address"],
        "background_protocol": True,
    }


def close_profile(
    profile_id: int,
    *,
    target: str = DEFAULT_TARGET,
    port: int = DEFAULT_PORT,
) -> dict[str, Any]:
    client = _client(target, port)
    try:
        close = getattr(client, "close_profile", None)
        if not callable(close):
            raise RuntimeError("Installed ixBrowser SDK does not expose close_profile")
        result = close(int(profile_id))
        if result is None and getattr(client, "code", 0) not in (0, None):
            raise _error(client, "close profile")
        return {"closed": True, "profile_id": int(profile_id)}
    finally:
        _close_client(client)


def api_status(*, target: str = DEFAULT_TARGET, port: int = DEFAULT_PORT) -> dict[str, Any]:
    try:
        result = list_profiles(target=target, port=port, limit=1)
        return {
            "available": bool(result.get("available")),
            "target": str(target or DEFAULT_TARGET),
            "port": int(port or DEFAULT_PORT),
        }
    except Exception as exc:
        return {
            "available": False,
            "target": str(target or DEFAULT_TARGET),
            "port": int(port or DEFAULT_PORT),
            "error": f"{type(exc).__name__}: {exc}",
        }
