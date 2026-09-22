from __future__ import annotations

import asyncio

from gpt_windows_connector import ixbrowser_bridge


class FakeClient:
    code = 0
    message = "success"

    def __init__(self):
        self.closed = False
        self.closed_profiles = []

    def get_profile_list(self, **kwargs):
        return [{
            "profile_id": 42,
            "name": "Loopora",
            "group_name": "Marketing",
            "password": "do-not-return",
            "tfa_secret": "do-not-return",
            "proxy_type": "direct",
        }]

    def open_profile(self, profile_id, **kwargs):
        return {
            "webdriver": r"C:\\ix\\driver.exe",
            "debugging_address": "127.0.0.1:9333",
        }

    def close_profile(self, profile_id):
        self.closed_profiles.append(profile_id)
        return True

    def close(self):
        self.closed = True


def test_ixbrowser_profiles_redact_credentials(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(ixbrowser_bridge, "_client", lambda target, port: client)

    result = ixbrowser_bridge.list_profiles(name="Loopora")

    assert result["available"] is True
    assert result["profiles"][0]["profile_id"] == 42
    assert result["profiles"][0]["name"] == "Loopora"
    assert "password" not in result["profiles"][0]
    assert "tfa_secret" not in result["profiles"][0]
    assert client.closed is True


def test_ixbrowser_open_normalizes_debugging_address(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(ixbrowser_bridge, "_client", lambda target, port: client)

    result = ixbrowser_bridge.open_profile(42)

    assert result["endpoint"] == "http://127.0.0.1:9333"
    assert result["webdriver"] == "driver.exe"
    assert result["background_protocol"] is True


def test_ixbrowser_attach_uses_playwright_cdp(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(ixbrowser_bridge, "_client", lambda target, port: client)

    calls = []

    async def fake_connect_cdp(endpoint, browser_name=None, profile=None):
        calls.append((endpoint, browser_name, profile))
        return {"session_id": "session-1", "pages": 1}

    monkeypatch.setattr(ixbrowser_bridge.browser, "connect_cdp", fake_connect_cdp)

    result = asyncio.run(ixbrowser_bridge.attach_profile(42))

    assert calls == [("http://127.0.0.1:9333", "ixbrowser", "42")]
    assert result["session_id"] == "session-1"
    assert result["ixbrowser"] is True
    assert result["ix_profile_id"] == 42
