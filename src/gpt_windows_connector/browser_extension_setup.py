"""Local-only pairing UI and distributable extension package."""
from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile


def extension_zip() -> bytes:
    root = Path(__file__).parent / "assets" / "lucas-browser"
    if not root.exists():
        root = Path(__file__).parents[2] / "extensions" / "lucas-browser"
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for name in ("manifest.json", "background.js", "grant_lifecycle.js", "page_actions.js", "popup.html", "popup.js", "popup.css"):
            archive.write(root / name, "Lucas-Browser/" + name)
    return stream.getvalue()


def show_pairing(parent, config_dir: Path) -> None:
    import tkinter as tk
    from .browser_extension import pairing_token
    window = tk.Toplevel(parent)
    window.title("Lucas Browser / 浏览器插件配对")
    window.geometry("540x250")
    tk.Label(window, text="Install Lucas Browser, then copy this token into its popup.\n安装浏览器插件后，将配对码粘贴到插件弹窗。\nOnly share it with your own browser. / 仅用于你自己的浏览器。", wraplength=500).pack(padx=16,pady=16)
    token = pairing_token(config_dir / "browser-extension-token.txt")
    value = tk.Entry(window, width=65, show="•")
    value.insert(0, token)
    value.pack(padx=16,pady=8)
    def copy():
        window.clipboard_clear()
        window.clipboard_append(token)
    tk.Button(window, text="Copy pairing token / 复制配对码", command=copy).pack(pady=8)
    tk.Label(window, text="Default port / 默认端口: 8766\nChoose your approved account, then authorize the current tab.\n选择已批准的账号，再授权当前标签页。", wraplength=500).pack()
