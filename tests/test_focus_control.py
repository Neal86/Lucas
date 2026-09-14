from gpt_windows_connector.access_control import preset_security
from gpt_windows_connector.security import LocalSecurityPolicy


def category(method: str, **params):
    return LocalSecurityPolicy({"security": {}})._category(method, params)


def test_background_uia_does_not_require_focus_confirmation():
    assert category("computer.ui_click") == "background_control"
    assert category("computer.ui_set_text") == "background_control"


def test_uia_foreground_fallback_is_focus_controlled():
    assert category("computer.ui_click", allow_foreground_fallback=True) == "desktop_control"
    assert category("computer.ui_set_text", allow_foreground_fallback=True) == "desktop_control"


def test_real_input_and_visible_browser_are_focus_controlled():
    for method in ("computer.activate", "computer.click", "computer.type", "computer.hotkey", "computer.scroll"):
        assert category(method) == "desktop_control"
    assert category("browser.launch_persistent", headless=False) == "desktop_control"
    assert category("browser.launch_persistent", headless=True) == "browser_control"


def test_full_access_never_disables_focus_or_dangerous_confirmations():
    policy = preset_security("full_access")["approval_policy"]
    assert policy["background_control"] == "allow"
    assert policy["desktop_control"] == "always_ask"
    assert policy["git_push"] == "always_ask"
    assert policy["software_install"] == "always_ask"
    assert policy["registry_system"] == "always_ask"
    assert policy["high_risk"] == "always_ask"
