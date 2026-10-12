import asyncio
import io
import json
import time
from zipfile import ZipFile

import pytest
from websockets.asyncio.client import connect

from gpt_windows_connector.browser_extension import ExtensionBridge, TabGrant, pairing_token
from gpt_windows_connector.browser_extension_setup import extension_zip
from gpt_windows_connector.executor import Executor
from gpt_windows_connector import browser, browser_extension
from gpt_windows_connector.access_control import preset_security


def test_token_persists_and_archive_is_installable(tmp_path):
    path = tmp_path / 'token'
    assert pairing_token(path) == pairing_token(path)
    assert len(path.read_text()) >= 32
    with ZipFile(io.BytesIO(extension_zip())) as z:
        manifest = json.loads(z.read('Lucas-Browser/manifest.json'))
        assert manifest['manifest_version'] == 3
        assert 'debugger' in manifest['permissions']
        assert 'host_permissions' not in manifest
        assert z.read('Lucas-Browser/background.js')


def test_bridge_rejects_bad_origin_and_token():
    async def run():
        bridge = ExtensionBridge('x' * 40)
        await bridge.start(0)
        port = bridge.server.sockets[0].getsockname()[1]
        try:
            for origin in ('https://malicious.example', 'chrome-extension://test'):
                async with connect(f'ws://127.0.0.1:{port}', origin=origin) as ws:
                    if origin.startswith('chrome-extension:'):
                        await ws.send(json.dumps({'type':'hello','token':'wrong'}))
                    with pytest.raises(Exception):
                        await ws.recv()
                    assert ws.close_code == 1008
        finally:
            await bridge.stop()
    asyncio.run(run())


def test_real_websocket_grant_rpc_revoke_and_disconnect():
    async def run():
        owners = [{'user_id':'user-a'}]
        bridge = ExtensionBridge('x' * 40, lambda: owners)
        await bridge.start(0)
        port = bridge.server.sockets[0].getsockname()[1]
        try:
            async with connect(f'ws://127.0.0.1:{port}', origin='chrome-extension://test') as ws:
                await ws.send(json.dumps({'type':'hello','token':'x'*40}))
                assert json.loads(await ws.recv())['type'] == 'ready'
                await ws.send(json.dumps({'type':'grant','owner_id':'unapproved','tab_id':5}))
                assert json.loads(await ws.recv())['type'] == 'grant_error'
                await ws.send(json.dumps({'type':'grant','owner_id':'user-a','tab_id':5}))
                sid = json.loads(await ws.recv())['session_id']
                with pytest.raises(PermissionError):
                    await bridge.call('user-b', 'inspect', {'session_id':sid})
                assert not bridge.list_sessions('user-b')['sessions']
                task = asyncio.create_task(bridge.call('user-a','inspect',{'session_id':sid,'tab_id':999,'owner_id':'user-b'}))
                request = json.loads(await ws.recv())
                assert request['tab_id'] == 5
                assert 'tab_id' not in request['params']
                await ws.send(json.dumps({'type':'response','id':request['id'],'ok':True,'result':{'text':'real response'}}))
                assert (await task)['text'] == 'real response'
                bridge.sessions[sid].expires_at = time.time()-1
                with pytest.raises(PermissionError):
                    bridge.grant(sid,'user-a')
                bridge.sessions[sid].expires_at = time.time()+60
                pending = asyncio.create_task(bridge.call('user-a','click',{'session_id':sid}))
                await ws.recv()
                await ws.send(json.dumps({'type':'revoke','session_id':sid}))
                with pytest.raises(PermissionError):
                    await pending
                assert sid not in bridge.sessions
                await ws.send(json.dumps({'type':'grant','owner_id':'user-a','tab_id':5}))
                sid = json.loads(await ws.recv())['session_id']
            await asyncio.sleep(.02)
            assert not bridge.sessions
        finally:
            await bridge.stop()
    asyncio.run(run())


def test_executor_browser_sessions_are_account_scoped(tmp_path):
    async def run():
        sid = 'test-cdp-session'
        browser._SESSIONS[sid] = browser.BrowserSession(context=None,owner_id='user-a')
        try:
            executor=Executor((tmp_path,),{'security':preset_security('full_access')},owner_id='user-b')
            with pytest.raises(PermissionError,match='another Lucas account'):
                await executor.call('browser.inspect',{'session_id':sid})
        finally:
            browser._SESSIONS.pop(sid)
    asyncio.run(run())


def test_cdp_close_does_not_close_user_context_or_browser():
    class Existing:
        async def close(self):
            raise AssertionError('Must not close user browser')
    class PlaywrightConnection:
        stopped=False
        async def stop(self): self.stopped=True
    async def run():
        pw=PlaywrightConnection()
        browser._SESSIONS['existing']=browser.BrowserSession(context=Existing(),browser=Existing(),playwright=pw,endpoint='http://127.0.0.1:9222')
        assert await browser.close('existing') == {'closed':True}
        assert pw.stopped
    asyncio.run(run())


def test_no_automatic_browser_restart(monkeypatch):
    async def broken(*args): raise ConnectionError('No CDP')
    monkeypatch.setattr(browser,'_connect_cdp_once',broken)
    monkeypatch.setattr(browser,'_restart_dedicated_browser',lambda *args: pytest.fail('Automatic foreground restart'))
    with pytest.raises(ConnectionError):
        asyncio.run(browser.connect_cdp(profile='optional'))


def test_extension_download_route():
    from starlette.testclient import TestClient
    from gpt_windows_connector.webapp import app
    response=TestClient(app).get('/download/Lucas-Browser.zip')
    assert response.status_code==200
    assert response.headers['content-type']=='application/zip'
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None


def test_failed_cdp_attachment_preserves_user_browser(monkeypatch):
    class ExistingBrowser:
        @property
        def contexts(self): raise RuntimeError("Failed after attachment")
        async def close(self): pytest.fail("Closed the user browser")
    class Playwright:
        stopped=False
        @property
        def chromium(self): return self
        async def connect_over_cdp(self,*args,**kwargs): return ExistingBrowser()
        async def start(self): return self
        async def stop(self): self.stopped=True
    pw=Playwright()
    monkeypatch.setattr(browser,"async_playwright",lambda:pw)
    with pytest.raises(RuntimeError,match="Failed after attachment"):
        asyncio.run(browser.connect_cdp())
    assert pw.stopped
