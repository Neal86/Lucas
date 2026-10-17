"""Settings account composition; login is independent of Node authorization."""
from .local_account import LocalAccountClient
from .settings_account_ui import build_account_page
from .settings_constants import CONFIG_DIR


def install_account_page(pages, tk, parent, colors, font, gateway_url, translate, scroll_page):
    # Server edits apply when Settings is reopened. Persisted sessions are bound
    # to their server and never silently follow a new configured gateway.
    try:
        client = LocalAccountClient(gateway_url, CONFIG_DIR / "account-session.json")
    except ValueError:
        wrap, body = scroll_page()
        tk.Label(body, text=translate("账号登录不可用：请检查 Gateway 地址并重新打开设置。",
                 "Account sign-in is unavailable. Check the Gateway URL and reopen Settings."),
                 bg=colors["window"], fg=colors["text"], wraplength=600, justify="left").pack(fill="x")
        pages["账号"] = wrap
        return
    pages["账号"] = build_account_page(tk=tk, parent=parent, colors=colors, font=font,
        client=client, translate=translate, scroll_page=scroll_page)
