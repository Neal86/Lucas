from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_settings_update_stays_inside_app_and_hides_console():
    text = (ROOT / "src/gpt_windows_connector/settings_ui.py").read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in text
    assert '"-UpdateFromApp"' in text
    assert "LUCAS_PROGRESS|" in text
    assert "root.after(300,root.destroy)" not in text
    assert 'title.set(T("正在更新 Lucas","Updating Lucas"))' in text
    assert 'update_widgets["return_button"]' in text

def test_installer_has_fast_in_app_update_mode():
    text = (ROOT / "scripts/install-node.ps1").read_text(encoding="utf-8")
    assert "[switch]$UpdateFromApp" in text
    assert "[int]$KeepProcessId = 0" in text
    assert "--force-reinstall --no-deps --no-cache-dir" in text
    assert 'Write-LucasProgress 100 "complete"' in text
    assert '($_.ProcessId -ne $KeepProcessId)' in text
