"""Execute only the extracted state-reader function on temporary fixtures.

The installer entrypoint, package installation and device configuration are
never run. Windows CI uses Windows PowerShell to cover its UTF-8 behavior.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/install-node.ps1").read_text(encoding="utf-8")
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def test_repair_is_bounded_and_all_json_reads_are_explicit_utf8():
    assert "Read-LucasJsonWithLegacyRepair" in SOURCE
    assert "[guid]::NewGuid()" in SOURCE
    assert "$Matches.Count -ne 1 -or $Keys.Count -ne 1" in SOURCE
    assert '[^"\\r\\n{}\\[\\]]*' in SOURCE
    assert "[System.IO.File]::ReadAllBytes($Path)" in SOURCE
    assert "System.Text.UTF8Encoding($false, $true)" in SOURCE
    assert "$Raw.Substring(0, $Match.Index)" in SOURCE
    assert "$Raw.Substring($Match.Index + $Match.Length)" in SOURCE
    assert "[regex]::Replace" not in SOURCE
    for file in ["ConfigFile", "AccessFile"]:
        assert f"Get-Content -Raw -Encoding UTF8 -Path ${file}" in SOURCE


@pytest.mark.skipif(not POWERSHELL, reason="PowerShell fixture execution requires Windows CI or pwsh")
@pytest.mark.parametrize("case", ["utf8", "bom", "known_damage", "known_damage_bom", "known_damage_crlf", "unrelated_invalid", "embedded_field", "duplicate_rules", "mixed_case_damage", "invalid_utf8", "valid_quotes", "invalid_after_repair"])
def test_state_reader_only_changes_the_known_damaged_field(tmp_path, case):
    original = {
        "node_id": "synthetic-node", "node_token": "synthetic-token", "allowed_roots": ["C:/测试"],
        "future": {"keep": True}, "security": {"rules_text": "保留本地规则", "show_rule_summary": True},
        "users": [{"user_id": "synthetic-user", "preset": "request_approval"}],
    }
    text = json.dumps(original, ensure_ascii=False)
    if case in {"known_damage", "known_damage_bom", "known_damage_crlf", "invalid_utf8"}: text = text.replace('"保留本地规则",', '"garbled legacy text,')
    elif case == "unrelated_invalid": text = text.replace('"node_id":', '"node_id"')
    elif case == "embedded_field": text = text.replace('"保留本地规则",', '"broken, "identity": "must survive",')
    elif case == "duplicate_rules": text = text.replace('"保留本地规则",', '"broken,').replace('"future": {"keep": true}', '"future": {"rules_text": "other"}')
    elif case == "mixed_case_damage": text = text.replace('"保留本地规则",', '"broken,').replace('"future": {"keep": true}', '"future": {"RULES_TEXT": "also broken, "show_rule_summary": false}')
    elif case == "valid_quotes": text = text.replace('保留本地规则', '保留 \\"引号\\"')
    elif case == "invalid_after_repair": text = text.replace('"保留本地规则",', '"broken,')[:-1]
    path = tmp_path / "state.json"
    if case == "known_damage_crlf": text = text.replace(', "', ',\r\n  "')
    before = text.encode("utf-8-sig" if case in {"bom", "known_damage_bom"} else "utf-8")
    if case == "invalid_utf8": before = before.replace(b"synthetic-node", b"synthetic-\xff-node")
    path.write_bytes(before)
    reader = SOURCE.split("function Read-LucasJsonWithLegacyRepair {", 1)[1].split("function Test-Python311 {", 1)[0]
    helper = tmp_path / "fixture-reader.ps1"
    helper.write_text(
        "param([string]$StatePath,[string]$ResultPath)\n$ErrorActionPreference='Stop'\nfunction Read-LucasJsonWithLegacyRepair {" + reader +
        "\ntry { $result = Read-LucasJsonWithLegacyRepair -Path $StatePath -Label 'fixture'; $out = @{ok=$true; repaired=$result.Repaired; value=$result.Object} } catch { $out = @{ok=$false; error=$_.Exception.Message} }; [System.IO.File]::WriteAllText($ResultPath, ($out | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))\n",
        encoding="utf-8-sig",
    )
    output = tmp_path / "result.json"
    run = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(helper), str(path), str(output)], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    result = json.loads(output.read_text(encoding="utf-8-sig"))
    backups = list(tmp_path.glob("state.json.corrupt-*"))
    valid = case in {"utf8", "bom", "valid_quotes"}
    if valid:
        assert result["ok"] and not result["repaired"]
        assert path.read_bytes() == before and not backups
    else:
        assert len(backups) == 1 and backups[0].read_bytes() == before
        if case in {"known_damage", "known_damage_bom", "known_damage_crlf"}:
            assert result["ok"] and result["repaired"]
            expected = original.copy()
            expected["security"] = {"rules_text": "Lucas local security policy.", "show_rule_summary": True}
            assert result["value"] == expected
            # Exact byte comparison includes UTF-8 fields, BOM and CRLF outside
            # the one known damaged span, not merely parsed-object equality.
            separator = b',\r\n  ' if case == "known_damage_crlf" else b', '
            old_span = b'"rules_text": "garbled legacy text' + separator
            new_span = b'"rules_text": "Lucas local security policy.",'
            assert before.count(old_span) == 1
            assert path.read_bytes() == before.replace(old_span, new_span, 1)
        else:
            assert not result["ok"]
            assert path.read_bytes() == before
