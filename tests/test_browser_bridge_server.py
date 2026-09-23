import asyncio

import pytest

from gpt_windows_connector.browser_bridge_server import BrowserBridgeServer


class DummySocket:
    async def send(self, _payload):
        return None


def test_pending_bridge_does_not_expose_pairing_code():
    server = BrowserBridgeServer()
    server.pending["install-1"] = {
        "installation_id": "install-1",
        "pairing_code": "123456",
        "connected_at": 1.0,
    }

    pending = server.list_pending()

    assert pending == [{"installation_id": "install-1", "connected_at": 1.0}]
    assert "pairing_code" not in pending[0]


def test_pair_requires_local_extension_code():
    server = BrowserBridgeServer()
    server.pending["install-1"] = {
        "installation_id": "install-1",
        "extension_id": "ext",
        "browser_type": "ixbrowser",
        "profile_name": "Jarvis",
        "profile_id": "11",
        "pairing_code": "123456",
        "connected_at": 1.0,
    }

    class Client:
        installation_id = "install-1"
        extension_id = "ext"
        websocket = DummySocket()
        browser_type = "ixbrowser"
        profile_name = "Jarvis"
        profile_id = "11"
        alias = ""
        tags = []
        groups = []
        paired = False

    server.clients["install-1"] = Client()

    with pytest.raises(PermissionError, match="pairing code is required"):
        asyncio.run(server.pair("install-1"))
    with pytest.raises(PermissionError, match="does not match"):
        asyncio.run(server.pair("install-1", pairing_code="654321"))
