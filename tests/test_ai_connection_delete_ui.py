from gpt_windows_connector.web_core_runtime import CORE_SCRIPT


def test_ai_connection_delete_flow_is_guarded_and_updates_ui_locally():
    assert "async function deleteAiConnection(id)" in CORE_SCRIPT
    assert "AI connection not found. Refresh and try again." in CORE_SCRIPT
    assert "This removes the Lucas OAuth connection. You can reconnect it later." in CORE_SCRIPT
    assert "method:'DELETE'" in CORE_SCRIPT
    assert "state.aiClients=state.aiClients.filter(x=>x.client_id!==clientId)" in CORE_SCRIPT
    assert "renderAiClients()" in CORE_SCRIPT
    assert "metricAiClients.textContent=state.aiClients.length" in CORE_SCRIPT
