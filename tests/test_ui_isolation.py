from pathlib import Path

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
        'id="landing"', 'id="auth"', 'id="app"',
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
