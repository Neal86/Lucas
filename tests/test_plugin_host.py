from gpt_windows_connector.plugin_host import normalize_plugin_descriptor


def test_normalize_openai_style_plugin_manifest():
    plugin = normalize_plugin_descriptor(
        {
            "manifest": {
                "id": "calendar",
                "name": "Calendar",
                "mcp": {"url": "https://calendar.example/mcp", "transport": "streamable-http"},
            }
        }
    )
    assert plugin["plugin_id"] == "calendar"
    assert plugin["name"] == "Calendar"
    assert plugin["server_url"] == "https://calendar.example/mcp"
    assert plugin["transport"] == "streamable_http"


def test_normalize_requires_mcp_url():
    try:
        normalize_plugin_descriptor({"name": "No server"})
    except ValueError as exc:
        assert "MCP server URL" in str(exc)
    else:
        raise AssertionError("descriptor without server must fail")
