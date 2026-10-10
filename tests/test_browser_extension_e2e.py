"""Opt-in real Chromium extension test, using raw CDP and the local WebSocket bridge."""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import websockets

from gpt_windows_connector import browser_bridge_server
from gpt_windows_connector.browser_profile_registry import BrowserProfileRegistry

CHROME = os.getenv('EXTENSION_TEST_CHROME')
ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'src/gpt_windows_connector/browser_bridge_extension'

HTML = b'''<!doctype html><title>Lucas Extension Test</title>
<style>body{font:18px system-ui;padding:30px}button,input{font:inherit;margin:8px;padding:8px}</style>
<button id="save">Save</button><input placeholder="Name" id="name"><input type="file" id="file">
<div contenteditable="true" aria-label="Note" id="note"></div><p id="out">Ready</p>
<table><tr><th>Item</th><th>Count</th></tr><tr><td>Apples</td><td>3</td></tr></table>
<iframe src="/frame"></iframe><a href="/download">Download</a>
<script>document.querySelector('#save').onclick=e=>{document.querySelector('#out').textContent=e.isTrusted?'Trusted click':'Synthetic click'};
document.querySelector('#file').onchange=e=>{document.querySelector('#out').textContent=e.target.files[0].name};</script>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/download':
            body=b'Lucas test download'; self.send_response(200); self.send_header('Content-Disposition','attachment; filename="lucas-test.txt"')
        else:
            body=b'<button>Frame button</button>' if self.path == '/frame' else HTML
            self.send_response(200); self.send_header('Content-Type','text/html')
        self.end_headers();self.wfile.write(body)
    def log_message(self,*_): pass


class CDP:
    def __init__(self, websocket):self.ws=websocket;self.counter=0
    async def send(self,method,params=None,session=None):
        self.counter+=1;id_=self.counter
        request={'id':id_,'method':method,'params':params or {}}
        if session:request['sessionId']=session
        await self.ws.send(json.dumps(request))
        while True:
            response=json.loads(await asyncio.wait_for(self.ws.recv(),15))
            if response.get('id')==id_:
                if 'error' in response:raise RuntimeError(response['error'])
                return response.get('result',{})


@pytest.mark.skipif(not CHROME, reason='Set EXTENSION_TEST_CHROME to a Chrome for Testing executable')
def test_real_browser_extension_roundtrip(tmp_path,monkeypatch):
    registry=BrowserProfileRegistry(tmp_path/'profiles.json',tmp_path/'bindings.json')
    monkeypatch.setattr(browser_bridge_server,'registry',registry)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    async def run():
        server=browser_bridge_server.BrowserBridgeServer()
        await server.start()
        profile_dir=tmp_path/'chrome';profile_dir.mkdir()
        log_file=(tmp_path/'chrome.log').open('w')
        process=subprocess.Popen([CHROME,'--headless=new','--no-sandbox','--disable-dev-shm-usage',
            '--no-first-run','--no-default-browser-check','--remote-debugging-port=0',
            '--user-data-dir='+str(profile_dir),'--disable-extensions-except='+str(EXT),'--load-extension='+str(EXT),'about:blank'],stdout=log_file,stderr=log_file)
        try:
            port_file=profile_dir/'DevToolsActivePort'
            for _ in range(100):
                if port_file.exists():break
                if process.poll() is not None:raise RuntimeError((tmp_path/'chrome.log').read_text())
                await asyncio.sleep(.1)
            port,path=port_file.read_text().splitlines()[:2]
            async with websockets.connect(f'ws://127.0.0.1:{port}{path}',max_size=32*1024*1024) as ws:
                cdp=CDP(ws)
                for _ in range(100):
                    targets=(await cdp.send('Target.getTargets'))['targetInfos']
                    workers=[t for t in targets if t['type']=='service_worker' and t['url'].endswith('/background.js')]
                    if server.pending and workers:break
                    await asyncio.sleep(.1)
                assert workers, (tmp_path/'chrome.log').read_text()
                assert server.pending, 'Browser extension did not connect to Lucas Node'
                pending=next(iter(server.pending.values()))
                iid=pending['installation_id']
                await server.pair(iid,pairing_code=pending['pairing_code'],browser_type='chrome',profile_name='Test')
                worker_session=(await cdp.send('Target.attachToTarget',{'targetId':workers[0]['targetId'],'flatten':True}))['sessionId']
                async def config(data):
                    result=await cdp.send('Runtime.evaluate',{'expression':'chrome.storage.local.set('+json.dumps(data)+')','awaitPromise':True,'returnByValue':True},worker_session)
                    assert not result.get('exceptionDetails'),result
                async def operation(action,params):
                    return await server.request(iid,action,params)
                await config({'siteMode':'all','developerMode':True})
                url=f'http://127.0.0.1:{http.server_port}/'
                tab=await operation('tab.open',{'url':url});tab_id=tab['id']
                await operation('page.wait',{'tab_id':tab_id})
                snapshot=await operation('page.snapshot',{'tab_id':tab_id})
                save=next(e['ref'] for e in snapshot['elements'] if e['text']=='Save')
                await operation('page.click',{'tab_id':tab_id,'target':save})
                snapshot=await operation('page.snapshot',{'tab_id':tab_id})
                assert 'Trusted click' in snapshot['text']
                await operation('page.type',{'tab_id':tab_id,'target':'Name','text':'Neal'})
                value=await operation('developer.evaluate',{'tab_id':tab_id,'expression':'document.querySelector("#name").value'})
                assert value['value']=='Neal'
                await operation('page.type',{'tab_id':tab_id,'target':'Note','text':'Hello'})
                value=await operation('page.evaluate_readonly',{'tab_id':tab_id,'expression':'document.querySelector("#note").textContent'})
                assert value['value']=='Hello'
                with pytest.raises(RuntimeError,match='side effects'):
                    await operation('page.evaluate_readonly',{'tab_id':tab_id,'expression':'document.querySelector("#name").value="changed"'})
                frame_list=await operation('page.frames',{'tab_id':tab_id})
                frame=next(f for f in frame_list if f['frame_id']!=0)
                snapshot=await operation('page.snapshot',{'tab_id':tab_id,'frame_id':frame['frame_id']})
                assert snapshot['elements'][0]['text']=='Frame button'
                table=await operation('page.extract',{'tab_id':tab_id})
                assert table['rows'][1]==['Apples','3']
                capture=await operation('page.screenshot',{'tab_id':tab_id})
                image=base64.b64decode(capture['base64']);assert image.startswith(b'\x89PNG')
                (tmp_path/'browser.png').write_bytes(image)
                await operation('page.upload',{'tab_id':tab_id,'target':'#file','files':[{'name':'sample.txt','type':'text/plain','base64':base64.b64encode(b'test').decode()}]})
                snapshot=await operation('page.snapshot',{'tab_id':tab_id});assert 'sample.txt' in snapshot['text']
                download=await operation('download.url',{'tab_id':tab_id,'url':url+'download','filename':'lucas-test.txt'})
                for _ in range(50):
                    downloaded=await operation('download.status',{'tab_id':tab_id,'download_id':download['download_id']})
                    if downloaded[0]['state']=='complete':break
                    await asyncio.sleep(.1)
                assert downloaded[0]['state']=='complete'
                await config({'blockedHosts':['127.0.0.1']})
                blocked=await operation('page.snapshot',{'tab_id':tab_id});assert blocked['action_type']=='website_blocked'
                await config({'blockedHosts':[],'paused':True})
                paused=await operation('page.click',{'tab_id':tab_id,'target':'Save'});assert paused['action_type']=='browser_paused'
                await config({'paused':False})
                # Render extension settings with real Chromium to catch CSP/script errors.
                extension_id=workers[0]['url'].split('/')[2]
                ui_target=(await cdp.send('Target.createTarget',{'url':f'chrome-extension://{extension_id}/options.html'}))['targetId']
                ui_session=(await cdp.send('Target.attachToTarget',{'targetId':ui_target,'flatten':True}))['sessionId']
                for _ in range(50):
                    state=await cdp.send('Runtime.evaluate',{'expression':'document.readyState','returnByValue':True},ui_session)
                    if state.get('result',{}).get('value')=='complete':break
                    await asyncio.sleep(.1)
                check=await cdp.send('Runtime.evaluate',{'expression':'document.querySelector("#siteMode").value','returnByValue':True},ui_session)
                assert check['result']['value']=='all'
                ui=await cdp.send('Page.captureScreenshot',{'format':'png'},ui_session)
                (tmp_path/'options.png').write_bytes(base64.b64decode(ui['data']))
                print('Real extension verified: trusted click, text/contenteditable, read-only JS, iframe, table, screenshot, upload, download, block/pause, settings UI')
                artifact_dir=os.getenv('EXTENSION_TEST_ARTIFACTS')
                if artifact_dir:
                    dest=Path(artifact_dir);dest.mkdir(parents=True,exist_ok=True)
                    for name in ['browser.png','options.png']:(dest/name).write_bytes((tmp_path/name).read_bytes())
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            log_file.close();await server.stop()
    try:asyncio.run(run())
    finally:http.shutdown();http.server_close()
