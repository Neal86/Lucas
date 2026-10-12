"""Real extension + browser test using raw Chromium CDP, without Playwright."""
import asyncio
import json
import os
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from websockets.asyncio.client import connect

from gpt_windows_connector import browser_extension
from gpt_windows_connector.browser_extension import ExtensionBridge
from gpt_windows_connector.executor import Executor
from gpt_windows_connector.access_control import preset_security

pytestmark = pytest.mark.skipif(os.getenv('RUN_EXTENSION_E2E') != '1' or not os.getenv('CHROME_BIN'), reason='RUN_EXTENSION_E2E=1 and CHROME_BIN required')


class CDP:
    def __init__(self, ws): self.ws=ws; self.sequence=0
    async def call(self, method, params=None, session=None):
        self.sequence+=1
        request={'id':self.sequence,'method':method,'params':params or {}}
        if session: request['sessionId']=session
        await self.ws.send(json.dumps(request))
        while True:
            response=json.loads(await asyncio.wait_for(self.ws.recv(),15))
            if response.get('id')==request['id']:
                assert 'error' not in response, response
                return response.get('result',{})
    async def evaluate(self, expression, session):
        result=await self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True},session)
        assert 'exceptionDetails' not in result, result
        return result['result'].get('value')


def test_real_extension_controls_only_granted_tab(tmp_path, monkeypatch):
    (tmp_path/'index.html').write_text('''<title>Lucas test</title><h1>Fixture</h1><label>Name<input id="name" aria-label="Name"></label><button id="click" onclick="document.querySelector('h1').textContent='Clicked'">Submit</button><input id="file" type="file"><a id="download" href="payload.txt" download>Download</a><select id="pick"><option value="a">A</option><option value="b">B</option></select><div style="height:3000px"></div>''')
    (tmp_path/'payload.txt').write_text('browser download content')
    (tmp_path/'upload.txt').write_text('upload content')
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    httpd=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(tmp_path)))
    thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{httpd.server_port}'
    async def run():
        bridge=ExtensionBridge('e'*40,lambda:[{'user_id':'owner','name':'Test owner'}])
        await bridge.start(0)
        monkeypatch.setattr(browser_extension,'bridge',bridge)
        port=bridge.server.sockets[0].getsockname()[1]
        extension=Path('extensions/lucas-browser').resolve()
        profile=tmp_path/'chrome-profile'
        proc=subprocess.Popen([os.environ['CHROME_BIN'],'--headless=new','--no-sandbox','--disable-dev-shm-usage','--remote-debugging-port=0',f'--user-data-dir={profile}',f'--disable-extensions-except={extension}',f'--load-extension={extension}',base],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    pytest.fail(f'Chromium could not start: {proc.stderr.read().decode(errors="replace")}')
                if (profile/'DevToolsActivePort').exists(): break
                await asyncio.sleep(.1)
            debug_port=(profile/'DevToolsActivePort').read_text().splitlines()[0]
            async with httpx.AsyncClient() as http:
                version=(await http.get(f'http://127.0.0.1:{debug_port}/json/version')).json()
            async with connect(version['webSocketDebuggerUrl'],max_size=32*1024*1024) as ws:
                cdp=CDP(ws)
                worker=None
                for _ in range(60):
                    targets=(await cdp.call('Target.getTargets'))['targetInfos']
                    worker=next((x for x in targets if x['type']=='service_worker' and 'background.js' in x['url']),None)
                    if worker:break
                    await asyncio.sleep(.1)
                assert worker, targets
                extension_origin=worker['url'].rsplit('/',1)[0]
                popup=(await cdp.call('Target.createTarget',{'url':extension_origin+'/popup.html'}))['targetId']
                session=(await cdp.call('Target.attachToTarget',{'targetId':popup,'flatten':True}))['sessionId']
                for _ in range(50):
                    ready=await cdp.evaluate("Boolean(globalThis.chrome?.runtime?.sendMessage)",session)
                    if ready: break
                    await asyncio.sleep(.1)
                assert ready, await cdp.evaluate("({url:location.href,text:document.body?.innerText})",session)
                paired=await cdp.evaluate(f"chrome.runtime.sendMessage({{type:'pair',token:'{'e'*40}',port:{port}}})",session)
                assert paired.get('ok'),paired
                for _ in range(30):
                    state=await cdp.evaluate("chrome.runtime.sendMessage({type:'status'})",session)
                    if state['owners']:break
                    await asyncio.sleep(.1)
                tab_id=await cdp.evaluate(f"chrome.tabs.query({{}}).then(t=>t.find(x=>x.url.startsWith('{base}')).id)",session)
                granted=await cdp.evaluate(f"chrome.runtime.sendMessage({{type:'grant',owner_id:'owner',tab_id:{tab_id}}})",session)
                assert granted.get('ok'),granted
                for _ in range(30):
                    sessions=bridge.list_sessions('owner')['sessions']
                    if sessions:break
                    await asyncio.sleep(.1)
                sid=sessions[0]['session_id']
                executor=Executor((tmp_path,),{'security':preset_security('full_access')},owner_id='owner')
                async def action(name,**params):
                    return await executor.call('browser.'+name,{'session_id':sid,'workspace':str(tmp_path),**params})
                assert 'Fixture' in (await action('inspect'))['text']
                await action('semantic_type',target='Name',text='Neal')
                observed=await action('observe')
                assert next(x for x in observed['elements'] if x['id']=='name')['text']=='Neal'
                await action('semantic_click',target='Submit')
                assert 'Clicked' in (await action('inspect'))['text']
                await action('select',selector='#pick',value='b')
                await action('upload',selector='#file',paths=['upload.txt'])
                assert 'upload.txt' in json.dumps(await action('observe'))
                await action('scroll',y=500)
                image=await action('screenshot',full_page=True)
                assert image['mime_type']=='image/png' and len(image['base64'])>100
                result=await asyncio.wait_for(action('download',selector='#download',save_path='saved.txt'),75)
                assert result['path']==str(tmp_path/'saved.txt')
                assert (tmp_path/'saved.txt').read_text()=='browser download content'
                assert (await action('handoff'))['handoff_required']
                with pytest.raises(PermissionError):
                    await Executor((tmp_path,),{'security':preset_security('full_access')},owner_id='other').call('browser.inspect',{'session_id':sid})
                # Actual foreground selection remains on another tab during work.
                await cdp.call('Target.createTarget',{'url':base+'/?other'})
                other=await cdp.evaluate(f"chrome.tabs.query({{}}).then(t=>t.find(x=>x.url==='{base}/?other').id)",session)
                await cdp.evaluate(f"chrome.tabs.update({other},{{active:true}})",session)
                await action('screenshot')
                active=await cdp.evaluate("chrome.tabs.query({active:true}).then(t=>t.map(x=>x.id))",session)
                assert other in active and tab_id not in active
                await action('navigate',url=base+'/index.html')
                await asyncio.sleep(.2)
                assert 'Fixture' in (await action('inspect'))['text']
                await cdp.evaluate("chrome.runtime.sendMessage({type:'revoke'})",session)
                await asyncio.sleep(.1)
                assert not bridge.list_sessions('owner')['sessions']
        finally:
            proc.terminate();proc.wait(timeout=10)
            await bridge.stop()
    try: asyncio.run(run())
    finally: httpd.shutdown();httpd.server_close()
