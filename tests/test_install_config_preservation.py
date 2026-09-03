from pathlib import Path


def test_updater_preserves_complete_existing_config():
    script = Path("scripts/install-node.ps1").read_text(encoding="utf-8")
    assert "$ExistingConfigRaw" in script
    assert "ConfigBackupFile" in script
    assert "Update aborted without changing local settings" in script
    assert "if ($ExistingConfig -and $ExistingConfigRaw)" in script
    assert "Copy-Item -Force -Path $ConfigBackupFile -Destination $ConfigFile" in script
    assert "node-config.json changed during update" in script
    assert "unknown" in script.lower() or "future fields" in script.lower()


def test_updater_preserves_user_permissions_and_folder_scopes():
    script = Path("scripts/install-node.ps1").read_text(encoding="utf-8")
    assert '$AccessFile = Join-Path $InstallDir "node-access.json"' in script
    assert '$AccessBackupFile = "$AccessFile.pre-update"' in script
    assert "ExistingAccessRaw" in script
    assert "Copy-Item -Force -Path $AccessBackupFile -Destination $AccessFile" in script
    assert "node-access.json changed during update" in script
