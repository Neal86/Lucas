"""Source-distribution boundary for the Windows in-app updater.

Review builds must not replace themselves with an unrelated production branch.
Changing this marker is an explicit release change, never an environment toggle.
The stable channel retains the existing main-based distribution contract; this
review candidate does not activate it or publish a new version.
"""
from __future__ import annotations

UPDATE_CHANNEL = "review"
STABLE_VERSION_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/pyproject.toml"
STABLE_INSTALLER_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/scripts/install-node.ps1"


def in_app_updates_allowed(*, installer_url: str = STABLE_INSTALLER_URL) -> bool:
    return UPDATE_CHANNEL == "stable" and installer_url == STABLE_INSTALLER_URL


def review_update_message(translate) -> str:
    return translate(
        "此测试版本不使用生产自动更新。请使用已审核的配套安装包；不会下载或运行 main 安装器。",
        "This review build does not use production updates. Use a reviewed matching distribution; the main installer will not be downloaded or run.",
    )
