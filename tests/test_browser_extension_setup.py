import asyncio
import json

import pytest
import websockets
from websockets.exceptions import ConnectionClosed

from gpt_windows_connector import browser_bridge_server as bridge_module
from gpt_windows_connector.browser_bridge_settings import settings_request
from gpt_windows_connector.browser_extension_setup import browser_state, store_url
from gpt_windows_connector.browser_profile_registry import BrowserProfileRegistry


@pytest.mark.parametrize('value', [None, '', 'https://[invalid', 'https://example.com/detail/'+'a'*32, 'https://chromewebstore.google.com.evil.test/detail/'+'a'*32, 'javascript:alert(1)', 'https://chromewebstore.google.com/detail/example', 'https://chromewebstore.google.com/detail/'+'a'*32+'?redirect=evil'])
def test_unpublished_or_invalid_store_url_has_no_fake_install_link(tmp_path, value):
    path = tmp_path / 'stores.json'
    path.write_text(json.dumps({'chrome': value}))
    assert store_url('chrome', path=path) is None


def test_real_store_url_and_edge_domain_are_validated(tmp_path):
    path = tmp_path / 'stores.json'
    chrome = 'https://chromewebstore.google.com/detail/lucas/'+'a'*32
    edge = 'https://microsoftedge.microsoft.com/addons/detail/lucas/'+'b'*32
    path.write_text(json.dumps({'chrome': chrome, 'edge': edge}))
    assert store_url('chrome', path=path) == chrome
    assert store_url('edge', path=path) == edge


def test_only_live_paired_browser_shows_connected():
    assert browser_state('chrome', {}) == 'node_offline'
    assert browser_state('chrome', {'running': True, 'extension_folder_ready': True}) == 'not_connected'
    client = {'browser_type': 'chrome', 'connected': True, 'paired': False}
    status = {'running': True, 'clients': [client]}
    assert browser_state('chrome', status) == 'pairing'
    client['paired'] = True
    assert browser_state('chrome', status) == 'connected'
    assert browser_state('edge', status) == 'not_connected'
    client['connected'] = False
    assert browser_state('chrome', status) == 'not_connected'


def test_local_settings_pair_disconnect_and_repair_over_real_socket(tmp_path, monkeypatch):
    registry = BrowserProfileRegistry(tmp_path/'profiles.json', tmp_path/'tasks.json')
    monkeypatch.setattr(bridge_module, 'registry', registry)

    async def scenario():
        server = bridge_module.BrowserBridgeServer(port=0)
        token_file = tmp_path/'token'
        server.local_settings.token_file = token_file
        await server.start()
        port = server.server.sockets[0].getsockname()[1]
        try:
            extension = await websockets.connect(f'ws://127.0.0.1:{port}/bridge', origin='chrome-extension://'+'a'*32, proxy=None)
            hello = {'type': 'hello', 'installation_id': 'test-browser', 'extension_id': 'a'*32, 'browser_type': 'chrome', 'profile_name': 'My browser'}
            await extension.send(json.dumps(hello))
            ack = json.loads(await extension.recv())
            assert ack['paired'] is False
            code = ack['pairing_code']
            async def local(action='status', **params):
                return await asyncio.to_thread(settings_request, action, token_file=token_file, port=port, **params)
            status = await local()
            assert browser_state('chrome', status) == 'pairing'
            assert code not in json.dumps(status)
            with pytest.raises(RuntimeError, match='does not match'):
                await local('pair', installation_id='test-browser', pairing_code='wrong')
            await local('pair', installation_id='test-browser', pairing_code=code)
            assert json.loads(await extension.recv())['type'] == 'paired'
            assert browser_state('chrome', await local()) == 'connected'
            command = asyncio.create_task(server.request('test-browser', 'ping'))
            message = json.loads(await extension.recv())
            await extension.send(json.dumps({'type': 'response', 'id': message['id'], 'result': {'pong': True}}))
            assert await command == {'pong': True}
            await local('disconnect', installation_id='test-browser')
            assert registry.profile_for_bridge('test-browser')['enabled'] is False
            assert not registry.list_profiles()
            await extension.close()
            # Reconnection after local revocation requires a fresh proof-of-presence code.
            async with websockets.connect(f'ws://127.0.0.1:{port}/bridge', origin='chrome-extension://'+'a'*32, proxy=None) as extension:
                await extension.send(json.dumps(hello))
                ack = json.loads(await extension.recv())
                assert ack['paired'] is False
                await local('pair', installation_id='test-browser', pairing_code=ack['pairing_code'])
                assert registry.profile_for_bridge('test-browser')['enabled'] is True
            assert 'agent_policies' in registry._load()
        finally:
            await server.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize('origin', [None, 'https://evil.example', 'chrome-extension://'+'a'*32])
def test_settings_requires_local_token_and_rejects_browser_origins(tmp_path, origin):
    async def scenario():
        server = bridge_module.BrowserBridgeServer(port=0)
        server.local_settings.token_file = tmp_path/'token'
        await server.start()
        port = server.server.sockets[0].getsockname()[1]
        try:
            token = server.local_settings.token if origin else 'wrong-token'
            async with websockets.connect(f'ws://127.0.0.1:{port}/settings', additional_headers={'Authorization': 'Bearer '+token}, origin=origin, proxy=None) as client:
                with pytest.raises(ConnectionClosed) as denied:
                    await client.recv()
                assert denied.value.rcvd.code == 4403
        finally:
            await server.stop()
    asyncio.run(scenario())


def test_store_launch_targets_selected_browser_without_default_browser_fallback(monkeypatch):
    from gpt_windows_connector import browser_extension_setup as setup
    launched = []
    monkeypatch.setattr(setup, 'browser_executable', lambda browser: {'chrome': 'chrome.exe', 'edge': 'msedge.exe'}.get(browser))
    monkeypatch.setattr(setup.subprocess, 'Popen', lambda args, **kwargs: launched.append(args))
    assert setup.open_store_url('chrome', 'https://chromewebstore.google.com/detail/'+'a'*32)
    assert setup.open_store_url('edge', 'https://microsoftedge.microsoft.com/addons/detail/'+'b'*32)
    assert not setup.open_store_url('ixbrowser', 'https://chromewebstore.google.com/detail/'+'a'*32)
    assert [entry[0] for entry in launched] == ['chrome.exe', 'msedge.exe']
