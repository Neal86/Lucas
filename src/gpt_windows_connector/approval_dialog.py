"""Closable, fail-closed approval dialog. X/Escape/No all deny."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


APPROVAL_TIMEOUT_SECONDS = 45


def confirm_operation(title: str, text: str) -> bool:
    # Tk owns its main thread and interpreter in this short-lived helper process.
    # Node authorization itself runs in worker threads.
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    result = subprocess.run(
        [str(executable), "-m", "gpt_windows_connector.approval_dialog"],
        input=json.dumps({"title": title, "text": text}),
        text=True, encoding="utf-8", capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=APPROVAL_TIMEOUT_SECONDS,
    )
    return result.returncode == 0 and result.stdout.strip() == "allow"


def _show_dialog(title: str, text: str) -> bool:
    import tkinter as tk
    from tkinter import scrolledtext

    root = tk.Tk()
    allowed = False
    try:
        root.title(title)
        root.geometry("680x560")
        root.minsize(440, 300)
        root.attributes("-topmost", True)

        def finish(value: bool = False) -> None:
            nonlocal allowed
            allowed = value
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", finish)
        root.bind("<Escape>", lambda event: finish())
        root.after(APPROVAL_TIMEOUT_SECONDS * 1000, finish)
        details = scrolledtext.ScrolledText(root, wrap="word", padx=16, pady=16)
        details.insert("1.0", text)
        details.configure(state="disabled")
        details.pack(fill="both", expand=True)
        buttons = tk.Frame(root, padx=16, pady=12)
        buttons.pack(fill="x")
        deny = tk.Button(buttons, text="No / 拒绝", command=finish, width=16)
        deny.pack(side="right")
        tk.Button(buttons, text="Yes / 允许", command=lambda: finish(True), width=16).pack(side="right", padx=12)
        deny.focus_set()
        root.mainloop()
        return allowed
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print("allow" if _show_dialog(payload["title"], payload["text"]) else "deny")
    except Exception:
        print("deny")
        sys.exit(1)
