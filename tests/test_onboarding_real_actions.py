from pathlib import Path


def source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_setup_checklist_uses_real_account_state_and_routes():
    onboarding = source("src/gpt_windows_connector/web_onboarding_runtime.py")
    markup = source("src/gpt_windows_connector/web_dashboard_markup.py")
    assert "Setup Checklist" in onboarding
    assert "Connect your AI" in onboarding
    assert "Connect your computer" in onboarding
    assert "Set permissions" in onboarding
    assert "authorizedNodes" in onboarding
    assert "hasAi()" in onboarding
    assert "coach-close" in onboarding
    assert "gettingStartedNav" in onboarding
    assert 'id="gettingStartedNav"' in markup
    assert "Computer setup guide" not in onboarding
    assert "Review setup" not in onboarding


def test_checklist_does_not_show_over_signed_out_auth():
    onboarding = source("src/gpt_windows_connector/web_onboarding_runtime.py")
    core = source("src/gpt_windows_connector/web_core_runtime.py")
    assert "appVisible()" in onboarding
    assert "window.hideGettingStarted" in core


def test_new_onboarding_overrides_legacy_before_boot():
    assets = source("src/gpt_windows_connector/web_assets.py")
    assert assets.index("+ CORE_SCRIPT") < assets.index("+ ONBOARDING_SCRIPT") < assets.index("+ ADMIN_SCRIPT")
