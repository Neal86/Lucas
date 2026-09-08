from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"
TESTS = ROOT / "tests"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _py_string(name: str, value: str) -> str:
    return "from __future__ import annotations\n\n" + name + " = " + repr(value) + "\n"


def _dashboard_html_from_source(source: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "DASHBOARD_HTML" for t in targets):
                return ast.literal_eval(node.value)
    raise RuntimeError("DASHBOARD_HTML assignment not found")


def split_web_assets() -> None:
    source_path = PKG / "web_assets.py"
    source = _read(source_path)
    if "from .web_landing import LANDING_HTML" in source:
        return
    html = _dashboard_html_from_source(source)

    style_start = html.index("<style>")
    style_end = html.index("</style>", style_start) + len("</style>")
    landing_start = html.index('<section id="landing"')
    landing_end = html.index("</section>", landing_start) + len("</section>")
    auth_start = html.index('<div id="auth"', landing_end)
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
    landing_html = html[landing_start:landing_end]
    auth_html = html[auth_start:app_start]
    dashboard_html = html[app_start:script_start]
    i18n_script = html[script_start:i18n_end]
    billing_script = html[i18n_end:billing_end]
    core_script = html[billing_end:admin_start]
    admin_script = html[admin_start:]

    old_hero = '<h1>Let your AI leave<br><span>the chat box.</span></h1><p class="hero-copy">Give any MCP-compatible AI secure access to the computer where your real work happens — files, terminal, browser, Git and desktop apps.</p>'
    new_hero = '<h1>Let AI Work for You —<br><span>With $0 Token Fees</span></h1><p class="hero-copy">Connect the newest and smartest AI models to your computer, apps, files, and browser — and let them get real work done.</p>'
    if old_hero not in landing_html:
        raise RuntimeError("Expected legacy hero copy not found; refusing unsafe rewrite")
    landing_html = landing_html.replace(old_hero, new_hero, 1)

    old_i18n = "'Let your AI leave':'让你的 AI 走出','the chat box.':'聊天框。','Connect your computer':'连接电脑','See how it works ↓':'查看工作原理 ↓',"
    new_i18n = "'Let AI Work for You —':'让 AI 为你工作 —','With $0 Token Fees':'$0 Token 费用','Connect the newest and smartest AI models to your computer, apps, files, and browser — and let them get real work done.':'连接最新、最智能的 AI 模型到你的电脑、应用、文件和浏览器，让它们真正完成工作。','Connect your computer':'连接电脑','See how it works ↓':'查看工作原理 ↓',"
    if old_i18n not in i18n_script:
        raise RuntimeError("Expected legacy hero translation not found; refusing unsafe rewrite")
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

    assembler = '''from __future__ import annotations

from .web_admin_runtime import ADMIN_SCRIPT
from .web_auth_markup import AUTH_HTML
from .web_billing_runtime import BILLING_SCRIPT
from .web_core_runtime import CORE_SCRIPT
from .web_dashboard_markup import DASHBOARD_MARKUP
from .web_document import WEB_BODY_PREFIX, WEB_HEAD
from .web_i18n_runtime import I18N_SCRIPT
from .web_landing import LANDING_HTML
from .web_styles import WEB_STYLE

DASHBOARD_HTML = (
    WEB_HEAD
    + WEB_STYLE
    + WEB_BODY_PREFIX
    + LANDING_HTML
    + AUTH_HTML
    + DASHBOARD_MARKUP
    + I18N_SCRIPT
    + BILLING_SCRIPT
    + CORE_SCRIPT
    + ADMIN_SCRIPT
)
'''
    _write(source_path, assembler)


def _node_range(source: str, name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            return start, end, "".join(lines[start:end])
    raise RuntimeError(f"Top-level function {name} not found")


def split_settings_helpers() -> None:
    path = PKG / "settings_ui.py"
    source = _read(path)
    if "from .settings_helpers import (" in source:
        return
    names = [
        "detect_security_preset",
        "_version_key",
        "_fetch_latest_version",
        "_has_saved_token",
        "_app_version",
        "_default_node_id",
        "_load_config_file",
        "_save_config",
        "_load_last_page",
        "_save_last_page",
        "_restart_node_for_apply",
    ]
    ranges = [_node_range(source, name) for name in names]
    blocks = [block for _, _, block in ranges]
    helper_header = '''from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import uuid
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any

from .settings_constants import (
    CONFIG_DIR,
    CONFIG_FILE,
    LATEST_VERSION_URL,
    PRESETS,
    STATUS_FILE,
    TRAY_PID_FILE,
    UI_STATE_FILE,
)

'''
    _write(PKG / "settings_helpers.py", helper_header + "\n\n".join(blocks) + "\n")

    lines = source.splitlines(keepends=True)
    first = min(start for start, _, _ in ranges)
    for start, end, _ in sorted(ranges, reverse=True):
        lines[start:end] = []
    import_block = "from .settings_helpers import (\n    " + ",\n    ".join(names) + ",\n)\n\n"
    lines.insert(first, import_block)
    _write(path, "".join(lines))


def update_architecture_docs() -> None:
    path = ROOT / "ARCHITECTURE.md"
    text = _read(path)
    text = text.replace(
        "- `webapp.py`: HTTP composition and route wiring only. Large HTML/CSS/JS payloads live in `web_assets.py`.",
        "- `webapp.py`: HTTP composition and route wiring only. `web_assets.py` is assembly only; landing, auth/dashboard markup, styles, i18n, billing runtime, core runtime and admin runtime each live in dedicated modules.",
    )
    text = text.replace(
        "- `settings_ui.py`: settings window composition. Shared constants and presets live in `settings_constants.py`. New settings pages should be added as separate modules instead of growing this file.",
        "- `settings_ui.py`: settings window composition. Shared constants/presets live in `settings_constants.py`; reusable file/version/restart helpers live in `settings_helpers.py`. New settings pages should be added as separate modules instead of growing this file.",
    )
    _write(path, text)


def write_tests() -> None:
    test = '''from pathlib import Path

from gpt_windows_connector.web_assets import DASHBOARD_HTML

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"


def test_web_ui_is_split_into_stable_modules():
    required = {
        "web_document.py", "web_styles.py", "web_landing.py", "web_auth_markup.py",
        "web_dashboard_markup.py", "web_i18n_runtime.py", "web_billing_runtime.py",
        "web_core_runtime.py", "web_admin_runtime.py", "settings_helpers.py",
    }
    assert required <= {p.name for p in PKG.iterdir() if p.is_file()}
    assert (PKG / "web_assets.py").stat().st_size < 5000


def test_public_hero_copy_is_the_approved_version():
    assert "Let AI Work for You —" in DASHBOARD_HTML
    assert "With $0 Token Fees" in DASHBOARD_HTML
    assert "Connect the newest and smartest AI models to your computer, apps, files, and browser — and let them get real work done." in DASHBOARD_HTML
    assert "Let your AI leave" not in DASHBOARD_HTML
    assert "the chat box." not in DASHBOARD_HTML


def test_web_assembly_keeps_critical_contracts():
    for required in (
        'id="landing"', 'id="auth"', 'id="app"', 'id="billing"',
        'id="nodeModal"', 'id="aiModal"', 'id="connectModal"',
        "function boot()", "function startRealtime()", "function adminTab(",
        "function loadBillingView()", "__TURNSTILE_SITE_KEY__", "__TURNSTILE_CLASS__",
    ):
        assert required in DASHBOARD_HTML


def test_settings_ui_uses_extracted_helpers():
    source = (PKG / "settings_ui.py").read_text(encoding="utf-8")
    assert "from .settings_helpers import (" in source
    assert "def _fetch_latest_version" not in source
    assert "def _restart_node_for_apply" not in source
'''
    _write(TESTS / "test_ui_isolation.py", test)


def tighten_architecture_test() -> None:
    path = TESTS / "test_architecture_boundaries.py"
    text = _read(path)
    if '"web_assets.py": 5000' not in text:
        marker = 'budgets = {\n'
        text = text.replace(marker, marker + '        "web_assets.py": 5000,\n')
    if '"settings_helpers.py"' not in text:
        text = text.replace(
            '"web_assets.py", "gateway_stores.py", "gateway_events.py",\n        "node_approval.py", "settings_constants.py",',
            '"web_assets.py", "gateway_stores.py", "gateway_events.py",\n        "node_approval.py", "settings_constants.py", "settings_helpers.py",\n        "web_landing.py", "web_billing_runtime.py", "web_core_runtime.py", "web_admin_runtime.py",',
        )
    _write(path, text)


def main() -> None:
    split_web_assets()
    split_settings_helpers()
    update_architecture_docs()
    write_tests()
    tighten_architecture_test()


if __name__ == "__main__":
    main()
