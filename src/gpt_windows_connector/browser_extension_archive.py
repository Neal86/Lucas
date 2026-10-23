"""A reproducible store-upload ZIP containing only extension assets."""
from __future__ import annotations

import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .browser_bridge_extension_files import SOURCE_DIR

EXTENSION_FILES = (
    "manifest.json", "background.js", "content.js", "popup.html", "popup.js",
    "options.html", "options.js", "icon16.png", "icon48.png", "icon128.png",
)


def extension_archive(source: Path = SOURCE_DIR) -> bytes:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 3:
        raise ValueError("The extension must use Manifest V3")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name in EXTENSION_FILES:
            path = source / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Missing or unsafe extension asset: {name}")
            item = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, path.read_bytes())
    return buffer.getvalue()
