"""Store distribution and truthful browser connection states."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .settings_constants import CONFIG_DIR

STORE_FILE = Path(__file__).with_name("browser_extension_stores.json")
LOCAL_STORE_FILE = CONFIG_DIR / "browser-extension-stores.json"
BROWSERS = (("chrome", "Google Chrome"), ("edge", "Microsoft Edge"), ("ixbrowser", "ixBrowser / Chromium"))


def store_url(browser: str, *, path: Path | None = None) -> str | None:
    paths = [path] if path else [LOCAL_STORE_FILE, STORE_FILE]
    for filename in paths:
        try:
            url = str(json.loads(filename.read_text(encoding="utf-8")).get(browser) or "").strip()
            parsed = urlsplit(url)
        except (OSError, ValueError, AttributeError):
            continue
        host = "microsoftedge.microsoft.com" if browser == "edge" else "chromewebstore.google.com"
        if parsed.scheme != "https" or parsed.netloc != host or parsed.query or parsed.fragment:
            continue
        pattern = r"/addons/detail/(?:[^/]+/)?[a-p]{32}" if browser == "edge" else r"/detail/(?:[^/]+/)?[a-p]{32}"
        if re.fullmatch(pattern, parsed.path.rstrip("/")):
            return url
    return None


def browser_executable(browser: str) -> str | None:
    executable = {"chrome": "chrome.exe", "edge": "msedge.exe"}.get(browser)
    if not executable:
        return None
    relative = "Google/Chrome/Application/chrome.exe" if browser == "chrome" else "Microsoft/Edge/Application/msedge.exe"
    for key in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        if root := os.environ.get(key):
            path = Path(root) / relative
            if path.is_file():
                return str(path)
    return shutil.which(executable)


def open_store_url(browser: str, url: str) -> bool:
    executable = browser_executable(browser)
    if not executable:
        return False
    subprocess.Popen([executable, url], close_fds=True)
    return True


def browser_state(browser: str, status: dict) -> str:
    if not status.get("running"):
        return "node_offline"
    clients = [item for item in status.get("clients", []) if browser_key(item) == browser]
    if any(item.get("connected") and item.get("paired") for item in clients):
        return "connected"
    if any(item.get("connected") for item in clients):
        return "pairing"
    # A prepared folder doesn't establish that Chrome has installed the extension.
    return "not_connected"


def browser_key(client: dict) -> str:
    kind = str((client.get("profile") or {}).get("browser_type") or client.get("browser_type") or "chromium").lower()
    return kind if kind in {"chrome", "edge"} else "ixbrowser"
