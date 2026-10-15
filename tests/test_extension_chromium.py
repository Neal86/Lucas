"""Real extension via raw CDP, plus the production Playwright CDP observer."""
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

from gpt_windows_connector import browser, browser_extension
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
    (tmp_path/'index.html').write_text('''<title>Lucas test</title><h1>Fixture</h1><label>Name<input id="name" aria-label="Name"></label><label>Password<input id="password" type="password" name="password" aria-label="Password" placeholder="Enter password"></label><label>Confirm password<input id="confirm-password" type="PASSWORD" aria-label="Confirm password"></label><button id="click" onclick="document.querySelector('h1').textContent='Clicked'">Submit</button><input id="file" type="file"><a id="download" href="payload.txt" download>Download</a><select id="pick"><option value="a">A</option><option value="b">B</option></select><div style="height:3000px"></div>''')
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
        cdp_sid=None
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
                    for candidate in targets:
                        if candidate['type']!='service_worker' or not candidate['url'].startswith('chrome-extension://'):
                            continue
                        attached=(await cdp.call('Target.attachToTarget',{'targetId':candidate['targetId'],'flatten':True}))['sessionId']
                        await cdp.call('Runtime.enable',session=attached)
                        name=await cdp.evaluate('globalThis.chrome?.runtime?.getManifest?.().name',attached)
                        await cdp.call('Target.detachFromTarget',{'sessionId':attached})
                        if name=='Lucas Browser':
                            worker=candidate
                            break
                    if worker:break
                    await asyncio.sleep(.1)
                assert worker, targets
                extension_origin='chrome-extension://'+worker['url'].split('/')[2]
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
                assert state['can_grant'], state
                tab_id=await cdp.evaluate(f"chrome.tabs.query({{}}).then(t=>t.find(x=>x.url.startsWith('{base}')).id)",session)
                granted=await cdp.evaluate(f"chrome.runtime.sendMessage({{type:'grant',owner_id:'owner',tab_id:{tab_id}}})",session)
                assert granted.get('ok'),granted
                for _ in range(30):
                    sessions=bridge.list_sessions('owner')['sessions']
                    state=await cdp.evaluate("chrome.runtime.sendMessage({type:'status'})",session)
                    if sessions and state['sessions']:break
                    await asyncio.sleep(.1)
                assert sessions and state['sessions']
                sid=sessions[0]['session_id']
                executor=Executor((tmp_path,),{'security':preset_security('full_access')},owner_id='owner')
                async def action(name,**params):
                    return await executor.call('browser.'+name,{'session_id':sid,'workspace':str(tmp_path),**params})
                assert 'Fixture' in (await action('inspect'))['text']
                await action('semantic_type',target='Name',text='Neal')
                password='SYNTHETIC-PASSWORD-DO-NOT-USE'
                confirmation='SYNTHETIC-CONFIRMATION-DO-NOT-USE'
                await action('type',selector='#password',text=password)
                await action('type',selector='#confirm-password',text=confirmation)
                observed=await action('observe')
                assert next(x for x in observed['elements'] if x['id']=='name')['text']=='Neal'
                assert next(x for x in observed['elements'] if x['id']=='password')['text']==''
                assert next(x for x in observed['elements'] if x['id']=='confirm-password')['text']==''
                assert password not in json.dumps(observed) and confirmation not in json.dumps(observed)
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
                other=await cdp.evaluate(f"chrome.tabs.create({{url:'{base}/?other',active:true}}).then(t=>t.id)",session)
                await action('screenshot')
                active=await cdp.evaluate("chrome.tabs.query({active:true}).then(t=>t.map(x=>x.id))",session)
                assert other in active and tab_id not in active
                await action('navigate',url=base+'/index.html')
                await asyncio.sleep(.2)
                assert 'Fixture' in (await action('inspect'))['text']
                await cdp.evaluate("chrome.runtime.sendMessage({type:'revoke'})",session)
                await asyncio.sleep(.1)
                assert not bridge.list_sessions('owner')['sessions']
                with pytest.raises(PermissionError):
                    await action('inspect')
                # A new explicit grant still works after cancellation/cleanup,
                # and reauthorization must not select the background tab.
                granted=await cdp.evaluate(f"chrome.runtime.sendMessage({{type:'grant',owner_id:'owner',tab_id:{tab_id}}})",session)
                assert granted.get('ok'),granted
                for _ in range(30):
                    sessions=bridge.list_sessions('owner')['sessions']
                    state=await cdp.evaluate("chrome.runtime.sendMessage({type:'status'})",session)
                    if sessions and state['sessions']:break
                    await asyncio.sleep(.1)
                assert sessions and state['sessions']
                sid=sessions[0]['session_id']
                assert 'Fixture' in (await action('inspect'))['text']
                active=await cdp.evaluate("chrome.tabs.query({active:true}).then(t=>t.map(x=>x.id))",session)
                assert other in active and tab_id not in active
                await cdp.evaluate("chrome.runtime.sendMessage({type:'revoke'})",session)
                for _ in range(30):
                    target=await cdp.evaluate(f"chrome.debugger.getTargets().then(targets=>targets.find(t=>t.tabId==={tab_id}))",session)
                    if target and not target['attached'] and not bridge.list_sessions('owner')['sessions']:
                        break
                    await asyncio.sleep(.1)
                assert target and not target['attached']
                assert not bridge.list_sessions('owner')['sessions']
                # Exercise the actual fallback adapter against the same isolated
                # Chromium after releasing the extension's debugger grant.
                connected=await executor.call('browser.connect_cdp',{'endpoint':f'http://127.0.0.1:{debug_port}'})
                cdp_sid=connected['session_id']
                pages=await executor.call('browser.pages',{'session_id':cdp_sid})
                page_index=next(page['index'] for page in pages if page['url']==base+'/index.html')
                async def cdp_action(name,**params):
                    return await executor.call('browser.'+name,{'session_id':cdp_sid,'page_index':page_index,**params})
                await cdp_action('semantic_type',target='#name',text='Synthetic user')
                await cdp_action('semantic_type',target='#password',text=password)
                await cdp_action('semantic_type',target='#confirm-password',text=confirmation)
                observed=await cdp_action('observe')
                elements={item['id']:item for item in observed['elements']}
                assert elements['name']['text']=='Synthetic user'
                assert elements['password']['text']=='' and elements['confirm-password']['text']==''
                assert elements['password']['name']=='password' and elements['password']['type']=='password'
                assert elements['password']['aria_label']=='Password'
                assert elements['password']['placeholder']=='Enter password'
                assert elements['confirm-password']['type']=='PASSWORD'
                assert password not in json.dumps(observed) and confirmation not in json.dumps(observed)
                with pytest.raises(PermissionError,match='another Lucas account'):
                    await Executor((tmp_path,),{'security':preset_security('full_access')},owner_id='other').call('browser.observe',{'session_id':cdp_sid})
                assert await executor.call('browser.close',{'session_id':cdp_sid})=={'closed':True}
                cdp_sid=None
                assert proc.poll() is None
                active=await cdp.evaluate("chrome.tabs.query({active:true}).then(t=>t.map(x=>x.id))",session)
                assert other in active and tab_id not in active
                targets=(await cdp.call('Target.getTargets'))['targetInfos']
                assert any(target['url']==base+'/index.html' for target in targets)
        finally:
            try:
                if cdp_sid is not None:
                    await browser.close(cdp_sid)
            finally:
                proc.terminate();proc.wait(timeout=10)
                await bridge.stop()
    try: asyncio.run(run())
    finally: httpd.shutdown();httpd.server_close()
