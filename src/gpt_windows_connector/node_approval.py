from __future__ import annotations

import os
import subprocess
import sys

from .i18n import tr


def notify_access_request(actor: dict[str, object]) -> None:
    """Show a non-blocking-style local toast; clicking opens Users & Permissions."""
    try:
        import tkinter as tk
    except Exception:
        return

    try:
        root = tk.Tk()
        root.title(tr("Lucas 访问请求", "Lucas Access Request"))
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg="#ffffff")
        width, height = 390, 150
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{width}x{height}+{max(sw-width-24,0)}+{max(sh-height-72,0)}")
        display = str(actor.get("name") or actor.get("email") or actor.get("user_id") or tr("未知用户", "Unknown user"))
        email = str(actor.get("email") or "")
        frame = tk.Frame(root, bg="#ffffff", padx=18, pady=14)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=tr("Lucas 访问申请", "Lucas access request"), font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1f1f1f").pack(anchor="w")
        tk.Label(frame, text=display, font=("Segoe UI", 10, "bold"), bg="#ffffff", fg="#1f1f1f").pack(anchor="w", pady=(7, 0))
        if email and email != display:
            tk.Label(frame, text=email, font=("Segoe UI", 8), bg="#ffffff", fg="#666666").pack(anchor="w")
        tk.Label(frame, text=tr("点击打开“用户与权限”进行批准和权限设置。", "Click to open Users & Permissions to approve and configure access."), font=("Segoe UI", 8), bg="#ffffff", fg="#666666").pack(anchor="w", pady=(5, 8))

        def open_settings() -> None:
            env = os.environ.copy()
            env["LUCAS_SETTINGS_PAGE"] = "用户与权限"
            try:
                subprocess.Popen([sys.executable, "-m", "gpt_windows_connector.node", "--configure"], env=env, close_fds=True)
            except Exception:
                pass
            root.destroy()

        tk.Button(frame, text=tr("打开用户与权限", "Open Users & Permissions"), command=open_settings, bg="#0f8ce9", fg="#ffffff", relief="flat", padx=12, pady=5).pack(anchor="e")
        root.after(15000, root.destroy)
        root.mainloop()
    except Exception:
        return
