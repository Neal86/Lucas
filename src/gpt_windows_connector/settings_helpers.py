from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import uuid
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any

from .settings_constants import (
    CONFIG_DIR,
    CONFIG_FILE,
    LATEST_VERSION_URL,
    PRESETS,
    STATUS_FILE,
    TRAY_PID_FILE,
    UI_STATE_FILE,
)

def detect_security_preset(approval_policy: dict[str,str], network_external: str, network_lan: str, block_silent_network: bool, allowed_domains: list[str] | tuple[str, ...] | None = None) -> str:
    domains = [str(value).strip() for value in (allowed_domains or []) if str(value).strip()]
    for name,preset in PRESETS.items():
        if network_external != preset["network_external"] or network_lan != preset["network_lan"] or bool(block_silent_network) != bool(preset["block_silent_network"]):
            continue
        if name == "完全访问权限" and domains:
            continue
        if all(str(approval_policy.get(k)) == str(v) for k,v in preset["approval_policy"].items()):
            return name
    return "自定义"


def _version_key(value: str) -> tuple[int,...]:
    return tuple(int(x) for x in re.findall(r"\d+", value)[:4]) or (0,)


def _fetch_latest_version(timeout: float = 5.0) -> str | None:
    try:
        request = urllib.request.Request(
            f"{LATEST_VERSION_URL}?t={int(time.time())}",
            headers={"Cache-Control":"no-cache","Pragma":"no-cache","User-Agent":"Lucas-Node-Updater"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text=response.read().decode("utf-8",errors="replace")
        for line in text.splitlines():
            if line.strip().startswith("version ="):
                return line.split("=",1)[1].strip().strip(chr(34)).strip(chr(39))
        return None
    except Exception:
        return None


def _has_saved_token() -> bool:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return bool(str(data.get("node_token") or "").strip()) if isinstance(data, dict) else False
    except (OSError, json.JSONDecodeError):
        return False


def _app_version() -> str:
    try:
        return package_version("gpt-windows-connector")
    except PackageNotFoundError:
        return "dev"


def _default_node_id() -> str:
    return f"lucas-{uuid.uuid4().hex}"


def _load_config_file() -> dict[str, Any]:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_FILE)


def _load_last_page() -> str:
    allowed = {"常规", "安全", "用户与权限", "文件访问", "网络", "任务记录", "日志", "系统访问"}
    requested = str(os.environ.get("LUCAS_SETTINGS_PAGE") or "").strip()
    if requested in allowed:
        return requested
    try:
        data = json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
        page = str(data.get("last_page") or "") if isinstance(data, dict) else ""
        return page if page in allowed else "常规"
    except (OSError, json.JSONDecodeError):
        return "常规"


def _save_last_page(page: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        temp = UI_STATE_FILE.with_name(f"{UI_STATE_FILE.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps({"last_page": page}, ensure_ascii=False), encoding="utf-8")
        temp.replace(UI_STATE_FILE)
    except OSError:
        pass


def _restart_node_for_apply() -> None:
    """Ask the running tray to recreate Node by safely terminating its managed child."""
    try:
        import psutil
        if not TRAY_PID_FILE.exists():
            return
        tray_pid=int(TRAY_PID_FILE.read_text(encoding="ascii").strip())
        tray=psutil.Process(tray_pid)
        tray_cmd=" ".join(tray.cmdline()).lower()
        if "gpt_windows_connector.tray" not in tray_cmd:
            return
        data=json.loads(STATUS_FILE.read_text(encoding="utf-8")) if STATUS_FILE.exists() else {}
        node_pid=int(data.get("pid") or 0) if isinstance(data,dict) else 0
        if node_pid <= 0 or node_pid == os.getpid():
            return
        node=psutil.Process(node_pid)
        node_cmd=" ".join(node.cmdline()).lower()
        if "gpt_windows_connector.node" in node_cmd and "--configure" not in node_cmd:
            node.terminate()
    except Exception:
        pass

