from __future__ import annotations

from typing import Any

from .i18n import tr

STATUS_STALE_SECONDS = 90.0
RESUME_GAP_SECONDS = 30.0
NODE_STARTUP_GRACE_SECONDS = 20.0


def display_status(status: str) -> str:
    return {
        "Online": tr("在线", "Online"), "Connecting": tr("连接中…", "Connecting…"),
        "Reconnecting": tr("重新连接中…", "Reconnecting…"), "Disconnected": tr("已断开", "Disconnected"),
        "Offline": tr("离线", "Offline"),
    }.get(status, status or tr("离线", "Offline"))


def status_label(status: str) -> str:
    icon = {"Online": "●", "Connecting": "◐", "Reconnecting": "↻", "Disconnected": "○", "Offline": "○"}.get(status, "○")
    return f"{icon}  {display_status(status)}"


def status_requests_recovery(status: dict[str, Any], current_pid: int) -> bool:
    try:
        status_pid = int(status.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    return status_pid == current_pid and str(status.get("status") or "") == "Reconnecting"


def supervisor_gap_requires_recovery(gap_seconds: float) -> bool:
    return gap_seconds > RESUME_GAP_SECONDS


def stale_status_requires_recovery(status_age: float, process_age: float) -> bool:
    return status_age > STATUS_STALE_SECONDS and process_age > NODE_STARTUP_GRACE_SECONDS
