from pathlib import Path

from gpt_windows_connector.plugin_sync import PluginSyncStore


def test_plugin_sync_redacts_secrets_and_tracks_device_and_agent(tmp_path: Path):
    store = PluginSyncStore(tmp_path / "gateway.db")
    plugin = store.upsert(
        "u1",
        {
            "name": "Example",
            "server_url": "https://example.com/mcp",
            "manifest": {
                "name": "Example",
                "access_token": "do-not-sync",
                "nested": {"client_secret": "also-secret", "safe": "yes"},
            },
        },
    )
    assert plugin["manifest"]["name"] == "Example"
    assert "access_token" not in plugin["manifest"]
    assert plugin["manifest"]["nested"] == {"safe": "yes"}

    store.set_device_state("u1", plugin["plugin_id"], "device-a", installed_locally=True, local_version="1.2")
    store.set_agent_permission("u1", plugin["plugin_id"], "agent-a", False)
    synced = store.list("u1", device_id="device-a")[0]
    assert synced["device"]["installed_locally"] is True
    assert synced["device"]["local_version"] == "1.2"
    assert synced["agent_permissions"]["agent-a"] is False


def test_plugin_sync_is_user_isolated(tmp_path: Path):
    store = PluginSyncStore(tmp_path / "gateway.db")
    one = store.upsert("u1", {"name": "One", "server_url": "https://example.com/mcp"})
    store.upsert("u2", {"name": "Two", "server_url": "https://example.com/mcp"})
    assert [p["name"] for p in store.list("u1")] == ["One"]
    assert [p["name"] for p in store.list("u2")] == ["Two"]
    assert store.remove("u1", one["plugin_id"]) is True
    assert store.list("u1") == []
    assert len(store.list("u2")) == 1


def test_plugin_sync_requires_https_for_remote_servers(tmp_path: Path):
    store = PluginSyncStore(tmp_path / "gateway.db")
    try:
        store.upsert("u1", {"name": "Bad", "server_url": "http://example.com/mcp"})
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("remote HTTP plugin should be rejected")
