from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"

def test_settings_uses_extracted_in_app_updater():
    settings = (PKG / "settings_ui.py").read_text(encoding="utf-8")
    updater = (PKG / "update_ui.py").read_text(encoding="utf-8")
    assert "from .update_ui import InAppUpdater" in settings
    assert "updater.start_auto_check()" in settings
    assert "CREATE_NO_WINDOW" in updater
    assert '"-UpdateFromApp"' in updater
    assert '"-ExpectedVersion"' in updater
    assert "Lucas-Node-update-" in updater
    assert "LUCAS_PROGRESS|" in updater
    assert "root.after(300,root.destroy)" not in settings
    assert "Updating Lucas" in updater
    assert "return_button" in updater

def test_installer_has_fast_in_app_update_mode():
    text = (ROOT / "scripts/install-node.ps1").read_text(encoding="utf-8")
    assert "[switch]$UpdateFromApp" in text
    assert "[int]$KeepProcessId = 0" in text
    assert '[string]$ExpectedVersion = ""' in text
    assert "expected $ExpectedVersion but runtime reports $InstalledVersion" in text
    assert "Previous Settings closed during update" in text
    assert "--upgrade --no-cache-dir $PackageUrl" in text
    assert "--force-reinstall --no-deps" not in text
    assert 'Write-LucasProgress 100 "complete"' in text
    assert '($_.ProcessId -ne $KeepProcessId)' in text
