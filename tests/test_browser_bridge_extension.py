import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "src" / "gpt_windows_connector" / "browser_bridge_extension"


def test_browser_bridge_manifest_is_mv3_and_local_only():
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["background"]["service_worker"] == "background.js"
    assert manifest["content_scripts"][0]["js"] == ["content.js"]
    assert "<all_urls>" in manifest["host_permissions"]


def test_browser_bridge_extension_has_profile_identity_and_background_commands():
    background = (EXT / "background.js").read_text(encoding="utf-8")
    content = (EXT / "content.js").read_text(encoding="utf-8")

    assert 'ws://127.0.0.1:8766/bridge' in background
    assert "installationId" in background
    assert 'chrome.tabs.create({url:p.url||"about:blank",active:false})' in background
    assert 'action.startsWith("page.")' in background
    assert 'message.type !== "lucas_command"' in content
    assert 'action === "page.snapshot"' in content
    assert 'action === "page.upload"' in content


def test_browser_bridge_extension_does_not_request_cookie_permission():
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert "cookies" not in manifest["permissions"]
    assert "debugger" not in manifest["permissions"]
