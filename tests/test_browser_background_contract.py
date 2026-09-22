from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "gpt_windows_connector"


def test_gateway_exposes_background_ixbrowser_and_handoff_actions():
    source = (SRC / "gateway.py").read_text(encoding="utf-8")

    for action in (
        '"ix_status"',
        '"ix_profiles"',
        '"ix_attach"',
        '"snapshot"',
        '"diagnostics"',
        '"check_user_action"',
        '"request_user_action"',
        '"resume"',
    ):
        assert action in source
    assert "requires_user_action=true" in source
    assert "computer_tool is only for OS-native UI" in source


def test_executor_routes_new_browser_modules():
    source = (SRC / "executor.py").read_text(encoding="utf-8")

    assert '"browser.ix_attach": ixbrowser_bridge.attach_profile' in source
    assert '"browser.snapshot": browser_advanced.aria_snapshot' in source
    assert '"browser.diagnostics": browser_diagnostics.diagnostics' in source
    assert '"browser.check_user_action": browser_handoff.check_user_action' in source
    assert '"browser.resume": browser_handoff.resume' in source


def test_browser_protocol_actions_do_not_become_foreground_control():
    source = (SRC / "security.py").read_text(encoding="utf-8")

    foreground_block = source.split("FOREGROUND_CONTROL_METHODS = {", 1)[1].split("}", 1)[0]
    assert "browser." not in foreground_block
    assert '"browser.ix_attach"' in source
    assert '"browser.scroll"' in source
    assert '"browser.diagnostics"' in source
