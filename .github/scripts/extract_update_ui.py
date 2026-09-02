from pathlib import Path

settings_path = Path("src/gpt_windows_connector/settings_ui.py")
settings = settings_path.read_text(encoding="utf-8")
settings = settings.replace("import subprocess\nimport sys\n", "import subprocess\n", 1)
import_anchor = "from .task_runs import TaskRunStore\n"
if "from .update_ui import InAppUpdater\n" not in settings:
    settings = settings.replace(import_anchor, import_anchor + "from .update_ui import InAppUpdater\n", 1)
start = settings.index('    current_version=_app_version(); version_status=')
end_marker = '    threading.Thread(target=check_update_worker,daemon=True).start()\n'
end = settings.index(end_marker, start) + len(end_marker)
replacement = '''    current_version=_app_version(); version_status=tk.StringVar(value=f"当前版本 {current_version} · 正在检查更新…")\n    updater=InAppUpdater(\n        root=root,tk=tk,ttk=ttk,page_host=page_host,pages=pages,nav_buttons=nav_buttons,button_factory=button,\n        get_footer=lambda: footer,show_page=lambda name: show_page(name),title=title,subtitle=subtitle,translate=T,colors=C,font=FONT,\n        current_version=current_version,version_status=version_status,fetch_latest_version=_fetch_latest_version,version_key=_version_key,\n        installer_url=INSTALLER_URL,load_last_page=_load_last_page,save_last_page=_save_last_page,\n    )\n    row(c,"Lucas Node","自动检查新版本；也可手动检测并在有新版本时更新。",updater.build_control)\n    updater.start_auto_check()\n'''
settings = settings[:start] + replacement + settings[end:]
settings_path.write_text(settings, encoding="utf-8")

test_path = Path("tests/test_update_ui_contract.py")
test_path.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\nPKG = ROOT / "src" / "gpt_windows_connector"\n\ndef test_settings_uses_extracted_in_app_updater():\n    settings = (PKG / "settings_ui.py").read_text(encoding="utf-8")\n    updater = (PKG / "update_ui.py").read_text(encoding="utf-8")\n    assert "from .update_ui import InAppUpdater" in settings\n    assert "updater.start_auto_check()" in settings\n    assert "CREATE_NO_WINDOW" in updater\n    assert '"-UpdateFromApp"' in updater\n    assert "LUCAS_PROGRESS|" in updater\n    assert "root.after(300,root.destroy)" not in settings\n    assert "Updating Lucas" in updater\n    assert "return_button" in updater\n\ndef test_installer_has_fast_in_app_update_mode():\n    text = (ROOT / "scripts/install-node.ps1").read_text(encoding="utf-8")\n    assert "[switch]$UpdateFromApp" in text\n    assert "[int]$KeepProcessId = 0" in text\n    assert "--force-reinstall --no-deps --no-cache-dir" in text\n    assert 'Write-LucasProgress 100 "complete"' in text\n    assert '($_.ProcessId -ne $KeepProcessId)' in text\n''', encoding="utf-8")
