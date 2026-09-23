from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .settings_constants import CONFIG_DIR

SOURCE_DIR = Path(__file__).with_name("browser_bridge_extension")
INSTALL_DIR = CONFIG_DIR / "browser-bridge-extension"


def prepare_extension() -> dict[str, Any]:
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(f"Packaged Browser Bridge extension is missing: {SOURCE_DIR}")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in SOURCE_DIR.iterdir():
        if not source.is_file():
            continue
        destination = INSTALL_DIR / source.name
        if not destination.exists() or destination.read_bytes() != source.read_bytes():
            shutil.copy2(source, destination)
            copied += 1
    return {
        "source": str(SOURCE_DIR),
        "path": str(INSTALL_DIR),
        "copied_files": copied,
        "manifest": str(INSTALL_DIR / "manifest.json"),
    }


def extension_status() -> dict[str, Any]:
    manifest = INSTALL_DIR / "manifest.json"
    return {
        "installed": manifest.exists(),
        "path": str(INSTALL_DIR),
        "manifest": str(manifest),
    }
