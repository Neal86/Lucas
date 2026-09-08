from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"
SOURCE_COMMIT = "37a21dcf4003be2d18884ecc7e2a2ddfc0e39a54"


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _py_string(name: str, value: str) -> str:
    return "from __future__ import annotations\n\n" + name + " = " + repr(value) + "\n"


def _original_html() -> str:
    source = subprocess.check_output(
        ["git", "show", f"{SOURCE_COMMIT}:src/gpt_windows_connector/web_assets.py"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DASHBOARD_HTML" for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("Original DASHBOARD_HTML not found")


def main() -> None:
    html = _original_html()
    style_start = html.index("<style>")
    style_end = html.index("</style>", style_start) + len("</style>")
    landing_start = html.index('<section id="landing"')
    auth_start = html.index('<div id="auth"', landing_start)
    app_start = html.index('<div id="app"', auth_start)
    script_start = html.index("<script>\n", app_start)

    i18n_end_marker = "const state={user:null,nodes:[],aiClients:[],billing:null};\n"
    billing_end_marker = "window.loadBillingView=loadBillingView;window.billingChangePlan=billingChangePlan;window.billingAddExpansion=billingAddExpansion;window.billingPortal=billingPortal;\n"
    admin_start_marker = "function adminMetric(label,value)"
    i18n_end = html.index(i18n_end_marker, script_start)
    billing_end = html.index(billing_end_marker, i18n_end) + len(billing_end_marker)
    admin_start = html.index(admin_start_marker, billing_end)

    head_prefix = html[:style_start]
    style_html = html[style_start:style_end]
    body_prefix = html[style_end:landing_start]
    landing_html = html[landing_start:auth_start]
    auth_html = html[auth_start:app_start]
    dashboard_html = html[app_start:script_start]
    i18n_script = html[script_start:i18n_end]
    billing_script = html[i18n_end:billing_end]
    core_script = html[billing_end:admin_start]
    admin_script = html[admin_start:]

    old_hero = '<h1>Let your AI leave<br><span>the chat box.</span></h1><p class="hero-copy">Give any MCP-compatible AI secure access to the computer where your real work happens — files, terminal, browser, Git and desktop apps.</p>'
    new_hero = '<h1>Let AI Work for You —<br><span>With $0 Token Fees</span></h1><p class="hero-copy">Connect the newest and smartest AI models to your computer, apps, files, and browser — and let them get real work done.</p>'
    if old_hero not in landing_html:
        raise RuntimeError("Legacy hero copy missing from source snapshot")
    landing_html = landing_html.replace(old_hero, new_hero, 1)

    old_i18n = "'Let your AI leave':'让你的 AI 走出','the chat box.':'聊天框。','Connect your computer':'连接电脑','See how it works ↓':'查看工作原理 ↓',"
    new_i18n = "'Let AI Work for You —':'让 AI 为你工作 —','With $0 Token Fees':'$0 Token 费用','Connect the newest and smartest AI models to your computer, apps, files, and browser — and let them get real work done.':'连接最新、最智能的 AI 模型到你的电脑、应用、文件和浏览器，让它们真正完成工作。','Connect your computer':'连接电脑','See how it works ↓':'查看工作原理 ↓',"
    if old_i18n not in i18n_script:
        raise RuntimeError("Legacy hero translation missing from source snapshot")
    i18n_script = i18n_script.replace(old_i18n, new_i18n, 1)

    _write(PKG / "web_document.py", _py_string("WEB_HEAD", head_prefix) + "\nWEB_BODY_PREFIX = " + repr(body_prefix) + "\n")
    _write(PKG / "web_styles.py", _py_string("WEB_STYLE", style_html))
    _write(PKG / "web_landing.py", _py_string("LANDING_HTML", landing_html))
    _write(PKG / "web_auth_markup.py", _py_string("AUTH_HTML", auth_html))
    _write(PKG / "web_dashboard_markup.py", _py_string("DASHBOARD_MARKUP", dashboard_html))
    _write(PKG / "web_i18n_runtime.py", _py_string("I18N_SCRIPT", i18n_script))
    _write(PKG / "web_billing_runtime.py", _py_string("BILLING_SCRIPT", billing_script))
    _write(PKG / "web_core_runtime.py", _py_string("CORE_SCRIPT", core_script))
    _write(PKG / "web_admin_runtime.py", _py_string("ADMIN_SCRIPT", admin_script))

    test_path = ROOT / "tests" / "test_ui_isolation.py"
    test = test_path.read_text(encoding="utf-8")
    marker = '        "function loadBillingView()", "__TURNSTILE_SITE_KEY__", "__TURNSTILE_CLASS__",\n'
    replacement = '        "function loadBillingView()", "__TURNSTILE_SITE_KEY__", "__TURNSTILE_CLASS__",\n        \'class="token-section"\', \'id="security"\', \'id="how"\', \'class="final-cta"\', \'class="landing-footer"\',\n'
    if marker in test and 'class="token-section"' not in test:
        test = test.replace(marker, replacement)
        _write(test_path, test)

    from gpt_windows_connector.web_assets import DASHBOARD_HTML
    required = [
        'id="landing"', 'class="token-section"', 'id="security"', 'id="how"',
        'class="final-cta"', 'class="landing-footer"', 'id="auth"', 'id="app"',
        "Let AI Work for You —", "With $0 Token Fees",
    ]
    missing = [item for item in required if item not in DASHBOARD_HTML]
    if missing:
        raise RuntimeError("Reassembled web UI is incomplete: " + ", ".join(missing))


if __name__ == "__main__":
    main()
