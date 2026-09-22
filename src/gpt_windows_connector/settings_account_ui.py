from __future__ import annotations

import threading
import time
from typing import Any


def build_account_page(
    *,
    tk,
    parent,
    colors: dict[str, str],
    font: str,
    client,
    device_id: str,
    translate,
):
    """Build the isolated Account & Integrations settings page."""
    C = colors
    T = translate
    wrapper = tk.Frame(parent, bg=C["window"])
    body = tk.Frame(wrapper, bg=C["window"])
    body.pack(fill="both", expand=True)

    status_text = tk.StringVar(value="")
    plugin_text = tk.StringVar(value="")
    email_var = tk.StringVar(value="")
    password_var = tk.StringVar(value="")
    plugin_name_var = tk.StringVar(value="")
    plugin_url_var = tk.StringVar(value="")
    verify_code_var = tk.StringVar(value="")
    pending_challenge = {"id": "", "email": ""}

    def section(text: str):
        tk.Label(body, text=text, font=(font, 12, "bold"), fg=C["text"], bg=C["window"]).pack(anchor="w", pady=(18, 10))

    def card():
        frame = tk.Frame(body, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        frame.pack(fill="x", pady=(0, 16))
        return frame

    def button(parent_widget, text: str, command, primary: bool = False):
        bg = C["blue"] if primary else C["control"]
        fg = C["white"] if primary else C["text"]
        active = C["blue_dark"] if primary else C["control_hover"]
        return tk.Button(
            parent_widget, text=text, command=command, font=(font, 9),
            bg=bg, fg=fg, activebackground=active, activeforeground=fg,
            relief="flat", bd=0, padx=14, pady=7, cursor="hand2",
        )

    section(T("Lucas 账号", "Lucas Account"))
    account_card = card()
    account_content = tk.Frame(account_card, bg=C["card"])
    account_content.pack(fill="x", padx=18, pady=16)

    status_label = tk.Label(
        account_content, textvariable=status_text, font=(font, 10, "bold"),
        fg=C["text"], bg=C["card"], justify="left", anchor="w",
    )
    status_label.pack(fill="x")

    form = tk.Frame(account_content, bg=C["card"])
    tk.Label(form, text=T("邮箱", "Email"), font=(font, 9), fg=C["muted"], bg=C["card"]).grid(row=0, column=0, sticky="w", pady=(12, 4))
    email_entry = tk.Entry(form, textvariable=email_var, font=(font, 10), bg=C["control"], fg=C["text"], relief="flat", bd=0, width=42)
    email_entry.grid(row=1, column=0, sticky="ew", ipady=7)
    tk.Label(form, text=T("密码", "Password"), font=(font, 9), fg=C["muted"], bg=C["card"]).grid(row=2, column=0, sticky="w", pady=(12, 4))
    password_entry = tk.Entry(form, textvariable=password_var, show="*", font=(font, 10), bg=C["control"], fg=C["text"], relief="flat", bd=0, width=42)
    password_entry.grid(row=3, column=0, sticky="ew", ipady=7)
    actions = tk.Frame(form, bg=C["card"])
    actions.grid(row=4, column=0, sticky="w", pady=(14, 0))
    form.grid_columnconfigure(0, weight=1)

    verify_form = tk.Frame(account_content, bg=C["card"])
    verify_label = tk.Label(verify_form, text="", font=(font, 9), fg=C["muted"], bg=C["card"], justify="left")
    verify_label.pack(anchor="w", pady=(12, 4))
    verify_entry = tk.Entry(verify_form, textvariable=verify_code_var, font=(font, 11), bg=C["control"], fg=C["text"], relief="flat", bd=0, width=18)
    verify_entry.pack(anchor="w", ipady=7)
    verify_actions = tk.Frame(verify_form, bg=C["card"])
    verify_actions.pack(anchor="w", pady=(12, 0))

    section(T("插件同步", "Integration Sync"))
    plugin_card = card()
    plugin_content = tk.Frame(plugin_card, bg=C["card"])
    plugin_content.pack(fill="x", padx=18, pady=16)
    tk.Label(
        plugin_content,
        text=T(
            "插件列表会跟随 Lucas 账号同步；Allowed Folders、前台控制和系统权限仍只在本机生效。",
            "Plugin metadata follows your Lucas account. Allowed Folders, foreground control and OS permissions remain local-only.",
        ),
        font=(font, 9), fg=C["muted"], bg=C["card"], wraplength=720, justify="left",
    ).pack(anchor="w")
    tk.Label(
        plugin_content, textvariable=plugin_text, font=(font, 9), fg=C["text"],
        bg=C["card"], justify="left", anchor="w", wraplength=760,
    ).pack(fill="x", pady=(12, 0))
    add_form = tk.Frame(plugin_content, bg=C["card"])
    add_form.pack(fill="x", pady=(14, 0))
    tk.Label(add_form, text=T("名称", "Name"), font=(font, 9), fg=C["muted"], bg=C["card"]).grid(row=0, column=0, sticky="w")
    tk.Label(add_form, text="MCP URL", font=(font, 9), fg=C["muted"], bg=C["card"]).grid(row=0, column=1, sticky="w", padx=(10, 0))
    tk.Entry(add_form, textvariable=plugin_name_var, font=(font, 9), bg=C["control"], relief="flat", bd=0, width=24).grid(row=1, column=0, sticky="ew", ipady=6)
    tk.Entry(add_form, textvariable=plugin_url_var, font=(font, 9), bg=C["control"], relief="flat", bd=0, width=48).grid(row=1, column=1, sticky="ew", padx=(10, 0), ipady=6)
    add_form.grid_columnconfigure(1, weight=1)
    plugin_actions = tk.Frame(plugin_content, bg=C["card"])
    plugin_actions.pack(anchor="w", pady=(14, 0))

    busy = {"value": False}

    def render() -> None:
        state = client.status()
        signed_in = bool(state.get("signed_in"))
        if signed_in:
            pending_challenge["id"] = ""
            verify_form.pack_forget()
            who = state.get("name") or state.get("email") or state.get("user_id")
            last = state.get("last_sync_at")
            suffix = ""
            if last:
                try:
                    suffix = T(
                        f" · 上次同步 {time.strftime('%Y-%m-%d %H:%M', time.localtime(float(last)))}",
                        f" · Last sync {time.strftime('%Y-%m-%d %H:%M', time.localtime(float(last)))}",
                    )
                except Exception:
                    suffix = ""
            status_text.set(T(f"已登录：{who}{suffix}", f"Signed in: {who}{suffix}"))
            form.pack_forget()
        else:
            if pending_challenge["id"]:
                form.pack_forget()
                verify_label.configure(text=T(
                    f"验证码已发送到 {pending_challenge['email']}。请输入 6 位验证码。",
                    f"A verification code was sent to {pending_challenge['email']}. Enter the 6-digit code.",
                ))
                if not verify_form.winfo_manager():
                    verify_form.pack(fill="x")
            else:
                verify_form.pack_forget()
                status_text.set(T("未登录。登录后可在这台电脑同步你的插件和集成。", "Not signed in. Sign in to sync plugins and integrations on this computer."))
                if not form.winfo_manager():
                    form.pack(fill="x")
        plugins = client.cached_plugins()
        if not plugins:
            plugin_text.set(T("暂无已同步插件。", "No synced integrations yet."))
        else:
            lines = []
            for item in plugins[:30]:
                enabled = T("开启", "On") if item.get("enabled", True) else T("关闭", "Off")
                device = item.get("device") if isinstance(item.get("device"), dict) else {}
                local = T(" · 本机已安装", " · Installed locally") if device.get("installed_locally") else ""
                lines.append(f"• {item.get('name') or item.get('plugin_id')}  [{enabled}]{local}")
            plugin_text.set("\n".join(lines))

    def run_async(work, on_ok=None):
        if busy["value"]:
            return
        busy["value"] = True
        status_label.configure(fg=C["orange"])
        def worker():
            try:
                result = work()
                def success():
                    busy["value"] = False
                    status_label.configure(fg=C["text"])
                    if on_ok:
                        on_ok(result)
                    render()
                wrapper.after(0, success)
            except Exception as exc:
                def failure(message=str(exc)):
                    busy["value"] = False
                    status_label.configure(fg=C["red"])
                    status_text.set(message)
                wrapper.after(0, failure)
        threading.Thread(target=worker, daemon=True).start()

    def sign_in():
        email = email_var.get().strip()
        password = password_var.get()
        if not email or not password:
            status_text.set(T("请输入邮箱和密码。", "Enter your email and password."))
            return
        def signed(result):
            password_var.set("")
            if isinstance(result, dict) and result.get("verification_required"):
                pending_challenge["id"] = str(result.get("challenge_id") or "")
                pending_challenge["email"] = str(result.get("email") or email)
                verify_code_var.set("")
                render()
                wrapper.after(50, verify_entry.focus_set)
            else:
                pending_challenge["id"] = ""
        run_async(lambda: client.login(email, password), signed)

    def verify_login():
        challenge = pending_challenge["id"]
        code = verify_code_var.get().strip()
        if not challenge or not code:
            status_text.set(T("请输入验证码。", "Enter the verification code."))
            return
        def verified(_):
            pending_challenge["id"] = ""
            verify_code_var.set("")
        run_async(lambda: client.verify_login(challenge, code), verified)

    def resend_login():
        challenge = pending_challenge["id"]
        if challenge:
            run_async(lambda: client.resend_login(challenge))

    def sign_out():
        client.logout()
        render()

    def sync_now():
        run_async(lambda: client.sync_plugins(device_id))

    def add_plugin():
        name = plugin_name_var.get().strip()
        url = plugin_url_var.get().strip()
        if not url:
            status_text.set(T("请输入 MCP URL。", "Enter an MCP URL."))
            return
        def work():
            client.install_plugin(name, url)
            return client.sync_plugins(device_id)
        def clear(_):
            plugin_name_var.set("")
            plugin_url_var.set("")
        run_async(work, clear)

    sign_in_button = button(actions, T("登录", "Sign in"), sign_in, primary=True)
    sign_in_button.pack(side="left")
    verify_button = button(verify_actions, T("验证并登录", "Verify and sign in"), verify_login, primary=True)
    verify_button.pack(side="left")
    resend_button = button(verify_actions, T("重新发送", "Resend"), resend_login)
    resend_button.pack(side="left", padx=(10, 0))
    sync_button = button(plugin_actions, T("立即同步", "Sync now"), sync_now, primary=True)
    sync_button.pack(side="left")
    add_button = button(plugin_actions, T("添加插件", "Add integration"), add_plugin)
    add_button.pack(side="left", padx=(10, 0))
    sign_out_button = button(plugin_actions, T("退出登录", "Sign out"), sign_out)
    sign_out_button.pack(side="left", padx=(10, 0))

    render()
    return wrapper
