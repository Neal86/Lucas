from pathlib import Path


def test_local_account_ui_is_isolated_and_syncs_only_plugin_metadata():
    account = Path("src/gpt_windows_connector/local_account.py").read_text(encoding="utf-8")
    ui = Path("src/gpt_windows_connector/settings_account_ui.py").read_text(encoding="utf-8")
    settings = Path("src/gpt_windows_connector/settings_ui.py").read_text(encoding="utf-8")

    assert "protect_text(token)" in account
    assert '"/api/plugins"' in account
    assert '"/auth/desktop/login"' in account
    assert "verify_login" in account
    assert "Allowed Folders" in ui
    assert "build_account_page" in settings
    assert 'pages["账号与插件"]' in settings


def test_plugin_api_does_not_accept_synced_credentials():
    source = Path("src/gpt_windows_connector/plugin_sync.py").read_text(encoding="utf-8")
    assert '"access_token"' in source
    assert "_clean_manifest" in source
    assert "plugin_device_state" in source
