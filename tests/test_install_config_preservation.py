from pathlib import Path


def test_updater_preserves_complete_existing_config():
    script = Path("scripts/install-node.ps1").read_text(encoding="utf-8")
    assert "$ExistingConfigRaw" in script
    assert "ConfigBackupFile" in script
    assert "Update aborted without changing local settings" in script
    assert "if ($ExistingConfig -and $ExistingConfigRaw)" in script
    assert "$ExistingConfigRaw | Set-Content -Path $ConfigFile" in script
    assert "unknown" in script.lower() or "future fields" in script.lower()
