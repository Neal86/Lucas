import asyncio

from gpt_windows_connector import browser_router
from gpt_windows_connector.browser_profile_registry import BrowserProfileRegistry


class FakeBridge:
    def __init__(self):
        self.clients = []
        self.calls = []

    def list_clients(self):
        return list(self.clients)

    def list_pending(self):
        return []

    async def request(self, installation_id, action, params=None, timeout=30):
        self.calls.append((installation_id, action, dict(params or {})))
        return {"url": "https://example.com", "title": "Example", "text": "ok", "elements": [], "blocker": None}


def make_registry(tmp_path):
    return BrowserProfileRegistry(tmp_path / "profiles.json", tmp_path / "bindings.json")


def test_profile_open_uses_connected_bridge_and_locks_task(tmp_path, monkeypatch):
    store = make_registry(tmp_path)
    profile = store.upsert_profile({
        "browser_type": "ixbrowser",
        "profile_id": "11",
        "profile_name": "Jarvis",
        "aliases": ["jarvis"],
        "bridge_installation_id": "bridge-11",
    })
    bridge = FakeBridge()
    bridge.clients = [{
        "installation_id": "bridge-11",
        "extension_id": "ext",
        "paired": True,
        "profile_id": "11",
        "profile_name": "Jarvis",
        "profile": profile,
    }]
    monkeypatch.setattr(browser_router, "registry", store)
    monkeypatch.setattr(browser_router, "bridge_server", bridge)

    result = asyncio.run(browser_router.open_profile(
        {"alias": "jarvis", "task_key": "task-1"},
        {"client_name": "Test Agent"},
    ))

    assert result["status"] == "ready"
    assert result["transport"] == "bridge"
    assert store.task_binding("task-1")["profile_key"] == profile["profile_key"]


def test_profile_action_stays_on_bound_profile(tmp_path, monkeypatch):
    store = make_registry(tmp_path)
    profile = store.upsert_profile({
        "browser_type": "ixbrowser",
        "profile_name": "Jarvis",
        "aliases": ["jarvis"],
        "bridge_installation_id": "bridge-11",
    })
    store.bind_task("task-1", profile["profile_key"], transport="bridge", bridge_installation_id="bridge-11")
    bridge = FakeBridge()
    bridge.clients = [{
        "installation_id": "bridge-11",
        "paired": True,
        "profile": profile,
        "profile_name": "Jarvis",
        "profile_id": "",
        "alias": "jarvis",
    }]
    monkeypatch.setattr(browser_router, "registry", store)
    monkeypatch.setattr(browser_router, "bridge_server", bridge)

    result = asyncio.run(browser_router.profile_action(
        {"task_key": "task-1", "operation": "snapshot", "operation_params": {}},
        {"client_name": "Test Agent"},
        None,
    ))

    assert result["profile"]["profile_key"] == profile["profile_key"]
    assert bridge.calls[0][0] == "bridge-11"
    assert bridge.calls[0][1] == "page.snapshot"


def test_closed_profile_returns_resumable_user_handoff(tmp_path, monkeypatch):
    store = make_registry(tmp_path)
    store.upsert_profile({
        "browser_type": "ixbrowser",
        "profile_name": "Jarvis",
        "aliases": ["jarvis"],
    })
    bridge = FakeBridge()
    monkeypatch.setattr(browser_router, "registry", store)
    monkeypatch.setattr(browser_router, "bridge_server", bridge)
    monkeypatch.setattr(browser_router.ixbrowser_bridge, "api_status", lambda: {"available": False})

    result = asyncio.run(browser_router.open_profile(
        {"alias": "jarvis", "task_key": "task-2"},
        {"client_name": "Test Agent"},
    ))

    assert result["requires_user_action"] is True
    assert result["action_type"] == "open_browser_profile"
    assert result["resume_token"]
    assert "Jarvis" in result["chat_message"]
