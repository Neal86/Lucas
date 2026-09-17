from pathlib import Path


def source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_onboarding_uses_real_dashboard_controls():
    onboarding = source("src/gpt_windows_connector/web_onboarding_runtime.py")
    markup = source("src/gpt_windows_connector/web_dashboard_markup.py")
    for control_id in ("addAiTopBtn", "downloadNodeBtn", "connectComputerBtn", "managePermissionText"):
        assert control_id in onboarding
        assert control_id in markup or control_id == "managePermissionText"
    assert "lucas-onboarding-v2" in onboarding
    assert "authorizedNodes().length" in onboarding
    assert "hasAi()" in onboarding


def test_new_onboarding_overrides_slide_tutorial_before_boot():
    assets = source("src/gpt_windows_connector/web_assets.py")
    assert assets.index("CORE_SCRIPT") < assets.index("ONBOARDING_SCRIPT") < assets.index("ADMIN_SCRIPT")
