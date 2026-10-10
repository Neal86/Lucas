import asyncio
from gpt_windows_connector import browser_agent_policy, browser_router, gateway
from gpt_windows_connector.browser_profile_registry import BrowserProfileRegistry

def test_legacy_and_configured_profile_rules_are_inactive(tmp_path):
    store = BrowserProfileRegistry(tmp_path / 'profiles.json', tmp_path / 'bindings.json')
    store.set_agent_policy('agent', {'allow_aliases': ['eva']})
    for actor in ('agent', browser_agent_policy.LEGACY_EVA_CLIENT_ID):
        assert browser_agent_policy.effective_policy({'client_id': actor}, registry=store) is None
    assert store.get_agent_policy(['agent'])

def test_gateway_preserves_explicit_session_and_endpoint(monkeypatch):
    calls = []
    async def rpc(node, workspace, method, payload, **kwargs):
        calls.append((method, payload)); return {'session_id': payload.get('session_id', 'selected')}
    async def lock(*_): pass
    monkeypatch.setattr(gateway, '_node_rpc', rpc)
    monkeypatch.setattr(gateway, '_desktop_lock', lock)
    asyncio.run(gateway.browser_tool('ali-bc0358dd0a5d', 'workspace', 'connect_cdp',
                                     {'endpoint': 'http://127.0.0.1:9333', 'profile': 'work'}))
    asyncio.run(gateway.browser_tool('ali-bc0358dd0a5d', 'workspace', 'observe',
                                     {'session_id': 'work-session', 'page_index': 2}))
    assert calls[0] == ('browser.connect_cdp', {'endpoint': 'http://127.0.0.1:9333', 'profile': 'work'})
    assert calls[1] == ('browser.observe', {'session_id': 'work-session', 'page_index': 2})

def test_profile_action_switches_without_prior_binding(tmp_path, monkeypatch):
    store = BrowserProfileRegistry(tmp_path / 'profiles.json', tmp_path / 'bindings.json')
    first = store.upsert_profile({'browser_type': 'chrome', 'profile_name': 'First', 'bridge_installation_id': 'one'})
    second = store.upsert_profile({'browser_type': 'chrome', 'profile_name': 'Second', 'bridge_installation_id': 'two'})
    class Bridge:
        calls = []
        def list_clients(self):
            return [{'installation_id': key, 'paired': True, 'profile': profile}
                    for key, profile in [('one', first), ('two', second)]]
        async def request(self, installation_id, action, params, **kwargs):
            self.calls.append(installation_id); return {'elements': []}
    bridge = Bridge()
    monkeypatch.setattr(browser_router, 'registry', store)
    monkeypatch.setattr(browser_router, 'bridge_server', bridge)
    async def run():
        for profile in (first, second):
            result = await browser_router.profile_action(
                {'task_key': 'same-task', 'profile_key': profile['profile_key'], 'operation': 'observe'},
                {'client_id': browser_agent_policy.LEGACY_EVA_CLIENT_ID}, None)
            assert result['profile']['profile_key'] == profile['profile_key']
        await browser_router.profile_action({'profile_key': first['profile_key'], 'operation': 'observe'}, None, None)
    asyncio.run(run())
    assert bridge.calls == ['one', 'two', 'one']
