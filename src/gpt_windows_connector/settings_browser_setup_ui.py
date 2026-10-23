"""Consumer browser installation and management, separate from profile editing."""
from __future__ import annotations

import os
import queue
import threading
import time

from .browser_bridge_extension_files import prepare_extension
from .browser_bridge_settings import settings_request
from .browser_extension_setup import BROWSERS, browser_key, browser_state, open_store_url, store_url


def build_browser_setup(*, tk, parent, colors, font, translate, on_change):
    from tkinter import messagebox, simpledialog

    T, C = translate, colors
    frame = tk.Frame(parent, bg=C["window"])
    frame.pack(fill="x", pady=(18, 12))
    tk.Label(frame, text=T("连接浏览器", "Connect your browser"), font=(font, 12, "bold"), fg=C["text"], bg=C["window"]).pack(anchor="w")
    tk.Label(frame, text=T("安装扩展后，回到这里完成配对，即可复用浏览器的登录状态。", "Install the extension, then return here to pair and use your signed-in browser."), font=(font, 9), fg=C["muted"], bg=C["window"], wraplength=720, justify="left").pack(anchor="w", pady=(6, 14))
    hint = tk.StringVar()
    state = {"running": False, "clients": []}
    widgets = {}
    results = queue.SimpleQueue()
    actions = queue.SimpleQueue()
    busy, alive, next_poll = False, True, 0.0
    managers = {}

    def button(where, text, command):
        return tk.Button(where, text=text, command=command, font=(font, 9, "bold"), bg=C["blue"], fg="#ffffff", relief="flat", padx=14, pady=7, cursor="hand2")

    def request(action, callback=None, **params):
        nonlocal busy
        if busy:
            if action != "status":
                actions.put((action, callback, params))
            return
        busy = True
        def worker():
            try:
                results.put((action, callback, settings_request(action, **params), None))
            except Exception as exc:
                results.put((action, callback, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def update_cards():
        labels = {
            "connected": T("已连接", "Connected"),
            "pairing": T("扩展已连接，等待配对", "Extension detected — pairing required"),
            "not_connected": T("未连接；请安装扩展或打开已安装扩展的浏览器", "Not connected — install the extension or open your browser"),
            "node_offline": T("Lucas Node 未连接；请启动或重启 Node", "Lucas Node unavailable — start or restart it"),
        }
        for browser, (label, action_button) in widgets.items():
            current = browser_state(browser, state)
            label.set(labels[current])
            action_button.configure(text=T("管理", "Manage") if current in {"connected", "pairing"} else T("安装", "Install"))
        for browser, manager in list(managers.items()):
            if manager[0].winfo_exists():
                manager[1]()
            else:
                managers.pop(browser, None)

    def guide(browser, listing=None):
        try:
            info = prepare_extension()
        except Exception as exc:
            hint.set(str(exc))
            return
        win = tk.Toplevel(frame)
        win.title(T("安装 Lucas 浏览器扩展", "Install the Lucas browser extension"))
        win.geometry("620x360")
        win.transient(frame.winfo_toplevel())
        text = T(
            "扩展商店版本尚未配置。现在可以通过本地安装使用：\n\n1. 在目标浏览器中打开扩展管理页。\n2. 开启“开发者模式”。\n3. 点击“加载已解压的扩展程序”，选择下方文件夹。\n4. 返回 Lucas，点击“管理”，输入扩展弹窗显示的配对码。",
            "A store listing is not configured yet. You can install locally now:\n\n1. Open the extensions page in your target browser.\n2. Enable Developer mode.\n3. Choose Load unpacked and select the folder below.\n4. Return to Lucas, select Manage, and enter the code shown in the extension popup.",
        )
        if listing:
            text = T("请在目标浏览器或 Profile 中打开下方商店链接，安装扩展后返回 Lucas 配对。", "Open the store link below in your target browser/profile, install the extension, then return to Lucas to pair.")
        tk.Label(win, text=text, justify="left", wraplength=570, font=(font, 10)).pack(anchor="w", padx=20, pady=16)
        page = "edge://extensions" if browser == "edge" else "chrome://extensions"
        tk.Label(win, text=page, font=(font, 10, "bold")).pack(anchor="w", padx=20)
        path_var = tk.StringVar(value=listing or info["path"])
        tk.Entry(win, textvariable=path_var, state="readonly").pack(fill="x", padx=20, pady=10)
        def copy(value):
            win.clipboard_clear()
            win.clipboard_append(value)
        actions = tk.Frame(win)
        actions.pack(fill="x", padx=20)
        button(actions, T("复制扩展页地址", "Copy extensions URL"), lambda: copy(page)).pack(side="left")
        button(actions, T("复制链接或路径", "Copy link or folder"), lambda: copy(listing or info["path"])).pack(side="left", padx=8)
        if os.name == "nt":
            button(actions, T("打开文件夹", "Open folder"), lambda: os.startfile(info["path"])).pack(side="left")

    def manage(browser):
        previous = managers.get(browser)
        if previous and previous[0].winfo_exists():
            previous[0].lift()
            return
        win = tk.Toplevel(frame)
        win.title(T("管理浏览器连接", "Manage browser connections"))
        win.geometry("640x350")
        win.transient(frame.winfo_toplevel())
        tk.Label(win, text=T("选择要授权或断开连接的浏览器。配对码在浏览器的 Lucas 扩展弹窗里。", "Select a browser connection. The pairing code is in its Lucas extension popup."), justify="left", wraplength=590, font=(font, 10)).pack(anchor="w", padx=20, pady=16)
        items = tk.Listbox(win, height=7, exportselection=False, font=(font, 10))
        items.pack(fill="both", expand=True, padx=20)
        records = []
        def render():
            selected = items.curselection()
            identity = records[selected[0]]["installation_id"] if selected and selected[0] < len(records) else None
            records[:] = [c for c in state.get("clients", []) if browser_key(c) == browser]
            items.delete(0, "end")
            for index, client in enumerate(records):
                profile = client.get("profile") or {}
                name = profile.get("profile_name") or client.get("profile_name") or client["installation_id"][:8]
                status = T("已授权", "Authorized") if client.get("paired") else T("等待配对", "Pairing required")
                items.insert("end", f"{name} · {status}")
                if client["installation_id"] == identity:
                    items.selection_set(index)
            if records and not items.curselection():
                items.selection_set(0)
        def chosen():
            selection = items.curselection()
            return records[selection[0]] if selection else None
        def changed(_result):
            nonlocal next_poll
            on_change()
            next_poll = 0
            hint.set(T("浏览器授权已更新。", "Browser authorization updated."))
        def pair():
            client = chosen()
            if not client or client.get("paired"):
                return
            code = simpledialog.askstring(T("配对浏览器", "Pair browser"), T("输入浏览器 Lucas 扩展弹窗里的六位配对码：", "Enter the six-digit code from the Lucas extension popup:"), parent=win)
            if code is not None:
                request("pair", changed, installation_id=client["installation_id"], pairing_code=code.strip())
        def disconnect():
            client = chosen()
            if client and messagebox.askyesno(T("断开授权", "Disconnect"), T("停止 AI 控制这个浏览器连接？之后需要重新配对。", "Stop AI control of this browser connection? Pair it again to reconnect."), parent=win):
                request("disconnect", changed, installation_id=client["installation_id"])
        actions = tk.Frame(win)
        actions.pack(fill="x", padx=20, pady=16)
        button(actions, T("配对", "Pair"), pair).pack(side="left")
        button(actions, T("断开授权", "Disconnect"), disconnect).pack(side="left", padx=8)
        button(actions, T("关闭", "Close"), win.destroy).pack(side="right")
        managers[browser] = (win, render)
        render()

    def activate(browser):
        if browser_state(browser, state) in {"connected", "pairing"}:
            manage(browser)
        elif url := store_url(browser):
            try:
                opened = open_store_url(browser, url)
            except OSError:
                opened = False
            if not opened:
                guide(browser, url)
            hint.set(T("安装后返回此处；Lucas 会自动检测连接。", "Return here after installation; Lucas detects the connection automatically."))
        else:
            guide(browser)

    for browser, name in BROWSERS:
        row = tk.Frame(frame, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        row.pack(fill="x", pady=(0, 8))
        text = tk.Frame(row, bg=C["card"])
        text.pack(side="left", fill="both", expand=True, padx=18, pady=14)
        tk.Label(text, text=name, font=(font, 10, "bold"), bg=C["card"], fg=C["text"]).pack(anchor="w")
        label = tk.StringVar(value=T("正在检测…", "Checking…"))
        tk.Label(text, textvariable=label, wraplength=540, justify="left", font=(font, 9), bg=C["card"], fg=C["muted"]).pack(anchor="w", pady=(4, 0))
        action_button = button(row, T("安装", "Install"), lambda browser=browser: activate(browser))
        action_button.pack(side="right", padx=18)
        widgets[browser] = (label, action_button)
    tk.Label(frame, textvariable=hint, font=(font, 9), fg=C["muted"], bg=C["window"], wraplength=720, justify="left").pack(anchor="w", pady=6)

    def tick():
        nonlocal busy, next_poll
        if not alive:
            return
        while not results.empty():
            action, callback, result, error = results.get()
            busy = False
            if error:
                if action == "status":
                    state.update(running=False, clients=[])
                else:
                    hint.set(T("操作未完成：", "Action failed: ") + error)
            elif action == "status":
                state.update(result)
            elif callback:
                callback(result)
            update_cards()
        if not busy and not actions.empty():
            action, callback, params = actions.get()
            request(action, callback, **params)
        if not busy and time.monotonic() >= next_poll:
            next_poll = time.monotonic() + 3
            request("status")
        frame.after(150, tick)
    def destroyed(event):
        nonlocal alive
        if event.widget == frame:
            alive = False
    frame.bind("<Destroy>", destroyed)
    frame.after(100, tick)
    return frame
