"""Account settings presentation; network and lifetime behavior live separately."""
from __future__ import annotations

from .settings_account_lifecycle import AccountPageLifecycle


def build_account_page(*, tk, parent, colors: dict[str, str], font: str, client,
                       translate, scroll_page=None):
    """Return the page wrapper; reuse the Settings scrolling wrapper when supplied."""
    C, T = colors, translate
    if scroll_page is not None:
        wrapper, body = scroll_page()
    else:
        wrapper = tk.Frame(parent, bg=C["window"])
        body = tk.Frame(wrapper, bg=C["window"])
        body.pack(fill="both", expand=True)
    status_text = tk.StringVar(value="")
    email_var, password_var = tk.StringVar(value=""), tk.StringVar(value="")
    verify_code_var = tk.StringVar(value="")
    pending = {"id": "", "email": "", "generation": None}
    displayed = {"generation": None}
    lifecycle = None

    def section(text):
        tk.Label(body, text=text, font=(font, 12, "bold"), fg=C["text"], bg=C["window"]).pack(anchor="w", pady=(18, 10))

    def card():
        frame = tk.Frame(body, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        frame.pack(fill="x", pady=(0, 16))
        content = tk.Frame(frame, bg=C["card"])
        content.pack(fill="x", padx=18, pady=16)
        return content

    def button(parent_widget, text, command, primary=False):
        return tk.Button(parent_widget, text=text, command=command, font=(font, 9),
                         bg=C["blue"] if primary else C["control"], fg=C["white"] if primary else C["text"],
                         activebackground=C["blue_dark"] if primary else C["control_hover"],
                         relief="flat", bd=0, padx=14, pady=7, cursor="hand2")

    def entry(parent_widget, variable, width=42, **kwargs):
        return tk.Entry(parent_widget, textvariable=variable, font=(font, 10), bg=C["control"],
                        fg=C["text"], relief="flat", bd=0, width=width, **kwargs)

    section(T("Lucas 账号", "Lucas Account"))
    account = card()
    status_label = tk.Label(account, textvariable=status_text, font=(font, 10, "bold"),
                            fg=C["text"], bg=C["card"], justify="left", anchor="w", wraplength=680)
    status_label.pack(fill="x")
    form = tk.Frame(account, bg=C["card"])
    tk.Label(form, text=T("邮箱", "Email"), bg=C["card"], fg=C["muted"]).pack(anchor="w", pady=(12, 4))
    email_entry = entry(form, email_var)
    email_entry.pack(fill="x", ipady=7)
    tk.Label(form, text=T("密码", "Password"), bg=C["card"], fg=C["muted"]).pack(anchor="w", pady=(12, 4))
    password_entry = entry(form, password_var, show="*")
    password_entry.pack(fill="x", ipady=7)
    actions = tk.Frame(form, bg=C["card"])
    actions.pack(anchor="w", pady=(14, 0))
    verify_form = tk.Frame(account, bg=C["card"])
    verify_label = tk.Label(verify_form, text="", font=(font, 9), fg=C["muted"], bg=C["card"], justify="left", wraplength=680)
    verify_label.pack(anchor="w", pady=(12, 4))
    verify_entry = entry(verify_form, verify_code_var, 18)
    verify_entry.pack(anchor="w", ipady=7)
    verify_actions = tk.Frame(verify_form, bg=C["card"])
    verify_actions.pack(anchor="w", pady=(12, 0))

    account_actions = tk.Frame(account, bg=C["card"])
    account_actions.pack(anchor="w", pady=(14, 0))

    def clear_pending():
        pending.update(id="", email="", generation=None)
        verify_code_var.set("")

    def controls(_busy=None):
        busy = bool(lifecycle and lifecycle.busy)
        signed = client.status()["signed_in"]
        for control in (sign_in_button, email_entry, password_entry):
            control.configure(state="disabled" if busy else "normal")
        for control in (verify_button, resend_button, verify_entry):
            control.configure(state="disabled" if busy or not pending["id"] else "normal")
        sign_out_button.configure(state="normal" if signed else "disabled")
        cancel_button.configure(state="normal" if busy else "disabled")

    def render():
        state = client.status()
        displayed["generation"] = state["generation"]
        if pending["generation"] is not None and pending["generation"] != state["generation"]:
            clear_pending()
        status_label.configure(fg=C["text"])
        if state["signed_in"]:
            clear_pending()
            form.pack_forget()
            verify_form.pack_forget()
            who = state["name"] or state["email"] or state["user_id"]
            status_text.set(T(f"本机已保存账号会话：{who}", f"Saved account session: {who}"))
        elif pending["id"]:
            form.pack_forget()
            verify_form.pack(fill="x")
            status_text.set(T("等待邮箱验证。", "Email verification required."))
            verify_label.configure(text=T(f"验证码已发送到 {pending['email']}。请输入 6 位验证码。",
                                           f"A code was sent to {pending['email']}. Enter the 6-digit code."))
        else:
            verify_form.pack_forget()
            form.pack(fill="x")
            status_text.set(T("未登录。请登录 Lucas 账号。", "Not signed in. Sign in to your Lucas account."))
        controls()

    def error(exc):
        render()
        status_label.configure(fg=C["red"])
        status_text.set(str(exc))

    def run(work, on_ok=None, *, generation):
        def success(result):
            if on_ok:
                on_ok(result)
            render()
        accepted = lifecycle.submit(work, on_ok=success, on_error=error,
                                    expected_generation=generation)
        if accepted:
            status_label.configure(fg=C["orange"])
            status_text.set(T("正在处理…", "Working…"))
        return accepted

    def sign_in():
        email, password = email_var.get().strip(), password_var.get()
        if not email or not password:
            error(ValueError(T("请输入邮箱和密码。", "Enter your email and password.")))
            return
        def signed(result):
            if result.get("verification_required"):
                pending.update(id=result["challenge_id"], email=result["email"], generation=result["generation"])
                verify_code_var.set("")
            else:
                clear_pending()
        if run(lambda op: client.login(email, password, operation=op), signed,
               generation=displayed["generation"]):
            password_var.set("")

    def verify_login():
        challenge, code = pending["id"], verify_code_var.get().strip()
        if not challenge or len(code) != 6 or not code.isascii() or not code.isdigit():
            error(ValueError(T("请输入 6 位验证码。", "Enter the 6-digit verification code.")))
            return
        if run(lambda op: client.verify_login(challenge, code, operation=op), lambda _: clear_pending(),
               generation=pending["generation"]):
            verify_code_var.set("")

    def resend_login():
        challenge = pending["id"]
        if challenge:
            run(lambda op: client.resend_login(challenge, operation=op), generation=pending["generation"])

    def cancel_login():
        generation = pending["generation"]
        lifecycle.cancel()
        if generation is not None:
            client.cancel_pending_login(generation=generation)
        clear_pending()
        password_var.set("")
        render()

    def sign_out():
        generation = displayed["generation"]
        lifecycle.cancel()
        try:
            client.logout(generation=generation)
        except Exception as exc:
            clear_pending()
            password_var.set("")
            error(exc)
            return
        clear_pending()
        password_var.set("")
        render()

    sign_in_button = button(actions, T("登录", "Sign in"), sign_in, True)
    sign_in_button.pack(side="left")
    cancel_button = button(actions, T("取消", "Cancel"), cancel_login)
    cancel_button.pack(side="left", padx=(10, 0))
    verify_button = button(verify_actions, T("验证并登录", "Verify and sign in"), verify_login, True)
    verify_button.pack(side="left")
    resend_button = button(verify_actions, T("重新发送", "Resend"), resend_login)
    resend_button.pack(side="left", padx=(10, 0))
    button(verify_actions, T("取消", "Cancel"), cancel_login).pack(side="left", padx=(10, 0))
    sign_out_button = button(account_actions, T("退出登录", "Sign out"), sign_out)
    sign_out_button.pack(side="left")
    lifecycle = AccountPageLifecycle(wrapper, client, on_change=render, on_busy=controls)
    wrapper._lucas_account_lifecycle = lifecycle
    render()
    return wrapper
