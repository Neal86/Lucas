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


def _write_native_target_fixtures(directory):
    # All destinations are disposable loopback pages. Capture-phase listeners
    # expose a click/submit even when the native navigation itself is blocked.
    controls = """
      <title>Native target fixture</title><output id="effects">untouched</output>
      <a id="named-anchor" href="destination.html?case=named-link" target="lucas-ungranted-context"><span>Named link</span></a>
      <a id="new-context" href="destination.html?case=new-context" target="lucas-new-context">New context</a>
      <a id="blank-anchor" href="destination.html?case=blank" target="_blank">Blank link</a>
      <a id="mixed-blank-anchor" href="destination.html?case=mixed-blank" target="_BlAnK">Mixed blank link</a>
      <a id="inherited-anchor" href="destination.html?case=inherited-link">Inherited link</a>
      <a id="empty-anchor" href="destination.html?case=empty-link" target="">Empty link</a>
      <a id="self-anchor" href="destination.html?case=self-link" target="_SeLf">Self link</a>
      <a id="parent-anchor" href="destination.html?case=parent-link" target="_PARENT">Parent link</a>
      <a id="top-anchor" href="destination.html?case=top-link" target="_top">Top link</a>
      <form id="named-form" action="destination.html" target="lucas-ungranted-context">
        <button><span>Named submit</span></button>
        <button id="non-submit" type="button">Non-submit control</button>
      </form>
      <form id="overridden-form" action="destination.html" target="_self">
        <button formtarget="lucas-ungranted-context">Submitter override</button>
      </form>
      <input id="external-submitter" form="overridden-form" type="submit" formtarget="lucas-ungranted-context" value="External submitter">
      <input id="image-submitter" form="overridden-form" type="image" formtarget="_blank" alt="Image submitter"
        src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='30' height='30'%3E%3Crect width='30' height='30'/%3E%3C/svg%3E">
      <label id="external-label" for="external-submitter"><span>External submit label</span></label>
      <label id="image-label" for="image-submitter"><span>Image submit label</span></label>
      <form action="destination.html" target="lucas-ungranted-context">
        <label id="wrapped-label"><span>Wrapped submit label</span><input type="submit" value="Wrapped submit"></label>
      </form>
      <label for="external-submitter"><a id="label-link" href="destination.html?case=label-link" target="_self"><span>Interactive label link</span></a></label>
      <label id="text-label" for="label-text"><span>Text field label</span></label><input id="label-text">
      <label id="checkbox-label" for="label-checkbox"><span>Checkbox label</span></label><input id="label-checkbox" type="checkbox"
        onchange="document.getElementById('label-result').textContent=this.checked?'checked':'unchecked'">
      <output id="label-result">unchecked</output>
      <form id="inherited-form" action="destination.html">
        <input type="hidden" name="case" value="inherited-form">
        <button>Inherited submit</button><input type="submit" value="Inherited input submit">
      </form>
      <form id="empty-form" action="destination.html" target="">
        <input type="hidden" name="case" value="empty-form"><button>Empty form target</button>
      </form>
      <form action="destination.html" target="lucas-ungranted-context">
        <input type="hidden" name="case" value="empty-submitter"><button id="empty-submitter" formtarget="">Empty submitter target</button>
      </form>
      <form action="destination.html" target="lucas-ungranted-context">
        <input type="hidden" name="case" value="self-submitter"><button id="self-submitter" formtarget="_self">Self submitter target</button>
      </form>
      <form id="self-form" action="destination.html" target="_self">
        <input type="hidden" name="case" value="self-form"><button>Self form target</button>
      </form>
      <form action="destination.html" target="_self">
        <input type="hidden" name="case" value="empty-self-submitter"><button id="empty-self-submitter" formtarget="">Empty override of self form</button>
      </form>
      <script>
        document.addEventListener('click', () => document.querySelector('#effects').textContent = 'clicked', true);
        document.addEventListener('submit', () => document.querySelector('#effects').textContent = 'submitted', true);
      </script>
    """
    for filename, base_target in (
        ('native.html', ''),
        ('native-base.html', '<base target="lucas-ungranted-context">'),
        ('native-blank-base.html', '<base target="_blank">'),
    ):
        (directory / filename).write_text('<!doctype html>' + base_target + controls)
    (directory / 'destination.html').write_text('<title>Native target destination</title><h1>Native destination</h1>')
    (directory / 'named-tab.html').write_text('<title>Unrelated named tab</title><h1>Named tab sentinel</h1>')


def test_real_extension_controls_only_granted_tab(tmp_path, monkeypatch):
    (tmp_path/'index.html').write_text('''<title>Lucas test</title><h1>Fixture</h1><label>Name<input id="name" aria-label="Name"></label><label>Password<input id="password" type="password" name="password" aria-label="Password" placeholder="Enter password"></label><label>Confirm password<input id="confirm-password" type="PASSWORD" aria-label="Confirm password"></label><button id="click" onclick="document.querySelector('h1').textContent='Clicked'">Submit</button><input id="file" type="file"><a id="download" href="payload.txt" download>Download</a><select id="pick"><option value="a">A</option><option value="b">B</option></select><div style="height:3000px"></div>''')
    (tmp_path/'payload.txt').write_text('browser download content')
    (tmp_path/'upload.txt').write_text('upload content')
    _write_native_target_fixtures(tmp_path)
    destination_requests = []
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()
        def do_GET(self):
            if self.path.split('?', 1)[0] == '/destination.html':
                destination_requests.append(self.path)
            super().do_GET()
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
                    ready=await cdp.evaluate("Boolean(globalThis.chrome?.runtime?.sendMessage && document.getElementById('connect')?.onclick && document.getElementById('action-error'))",session)
                    if ready: break
                    await asyncio.sleep(.1)
                assert ready, await cdp.evaluate("({url:location.href,text:document.body?.innerText})",session)
                # Exercise the shipped popup DOM and button handler, rather
                # than sending the pairing message directly from the test.
                invalid_token = 'synthetic-invalid-token'
                await cdp.evaluate(f"document.getElementById('token').value={json.dumps(invalid_token)}; document.getElementById('port').value='1'; document.getElementById('connect').click()",session)
                for _ in range(30):
                    error=await cdp.evaluate("document.getElementById('action-error').textContent",session)
                    if error: break
                    await asyncio.sleep(.1)
                assert error == 'Pairing request failed: Invalid token or port'
                await cdp.evaluate("document.getElementById('status').textContent='Waiting for automatic status poll'",session)
                for _ in range(30):
                    popup_state=await cdp.evaluate("({status:document.getElementById('status').textContent,error:document.getElementById('action-error').textContent,token:document.getElementById('token').value})",session)
                    if popup_state['status'] != 'Waiting for automatic status poll': break
                    await asyncio.sleep(.1)
                assert popup_state['status'] != 'Waiting for automatic status poll'
                assert popup_state['error'] == error and popup_state['token'] == invalid_token
                assert not bridge.list_sessions('owner')['sessions']
                await cdp.evaluate(f"document.getElementById('token').value='{'e'*40}'; document.getElementById('port').value='{port}'; document.getElementById('connect').click()",session)
                for _ in range(30):
                    state=await cdp.evaluate("chrome.runtime.sendMessage({type:'status'})",session)
                    if state['owners']:break
                    await asyncio.sleep(.1)
                assert state['can_grant'], state
                for _ in range(30):
                    popup_state=await cdp.evaluate("({error:document.getElementById('action-error').textContent,token:document.getElementById('token').value})",session)
                    if not popup_state['error'] and not popup_state['token']: break
                    await asyncio.sleep(.1)
                assert popup_state == {'error':'', 'token':''}
                tab_id=await cdp.evaluate(f"chrome.tabs.query({{}}).then(t=>t.find(x=>x.url.startsWith('{base}')).id)",session)
                # Prepare a genuinely related named browsing context before
                # granting the source tab. Independent chrome.tabs.create tabs
                # need not be eligible destinations for a native named target.
                targets=(await cdp.call('Target.getTargets'))['targetInfos']
                source=next(t for t in targets if t['type']=='page' and t['url'].startswith(base))
                setup_session=(await cdp.call('Target.attachToTarget',{'targetId':source['targetId'],'flatten':True}))['sessionId']
                try:
                    opened=await cdp.call('Runtime.evaluate',{'expression':f"Boolean(window.open('{base}/named-tab.html','lucas-ungranted-context'))",'returnByValue':True,'userGesture':True},setup_session)
                    assert opened['result'].get('value') is True, opened
                finally:
                    await cdp.call('Target.detachFromTarget',{'sessionId':setup_session})
                for _ in range(30):
                    named_tab=await cdp.evaluate(f"chrome.tabs.query({{}}).then(t=>t.find(x=>x.url==='{base}/named-tab.html' && x.status==='complete'))",session)
                    if named_tab: break
                    await asyncio.sleep(.1)
                assert named_tab and named_tab['id'] != tab_id
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

                async def tab_snapshot():
                    return await cdp.evaluate("chrome.tabs.query({}).then(t=>t.map(x=>({id:x.id,url:x.url,active:x.active})).sort((a,b)=>a.id-b.id))",session)

                async def assert_only_original_grant():
                    state=await cdp.evaluate("chrome.runtime.sendMessage({type:'status'})",session)
                    assert [(x['session_id'],x['tab_id']) for x in state['sessions']] == [(sid,tab_id)]
                    assert [(x['session_id'],x['tab_id']) for x in bridge.list_sessions('owner')['sessions']] == [(sid,tab_id)]
                    active=await cdp.evaluate("chrome.tabs.query({active:true}).then(t=>t.map(x=>x.id))",session)
                    assert other in active and tab_id not in active and named_tab['id'] not in active

                blocked_cases = {
                    'native.html': [
                        ('click', '#named-anchor span'), ('semantic_click', 'Named link'),
                        ('click', '#new-context'), ('click', '#blank-anchor'),
                        ('click', '#mixed-blank-anchor'), ('click', '#named-form button span'),
                        ('semantic_click', 'Named submit'), ('click', '#overridden-form button'),
                        ('click', '#external-submitter'), ('click', '#image-submitter'),
                        ('click', '#external-label'), ('click', '#external-label span'),
                        ('click', '#image-label span'), ('click', '#wrapped-label span'),
                    ],
                    'native-base.html': [
                        ('click', '#inherited-anchor'), ('semantic_click', 'Inherited submit'),
                        ('click', '#inherited-form input[type=submit]'),
                        ('click', '#empty-anchor'), ('click', '#empty-form button'),
                        ('click', '#empty-submitter'), ('click', '#empty-self-submitter'),
                    ],
                    'native-blank-base.html': [
                        ('semantic_click', 'Inherited link'), ('click', '#inherited-form button'),
                        ('click', '#empty-anchor'), ('click', '#empty-form button'),
                        ('click', '#empty-submitter'), ('click', '#empty-self-submitter'),
                    ],
                }
                for fixture, cases in blocked_cases.items():
                    await action('navigate',url=f'{base}/{fixture}')
                    before=await tab_snapshot()
                    requests_before=list(destination_requests)
                    for method, control in cases:
                        result=await action(method,**{('target' if method=='semantic_click' else 'selector'):control})
                        assert result.get('handoff_required') is True, (fixture,control,result)
                        assert result.get('reason'), result
                        # Give any mistakenly dispatched native navigation time
                        # to appear in both Chrome and the loopback HTTP log.
                        await asyncio.sleep(.1)
                        assert (await action('inspect',selector='#effects'))['text'] == 'untouched', (fixture,control)
                        assert await tab_snapshot() == before, (fixture,control)
                        assert destination_requests == requests_before, (fixture,control)
                        await assert_only_original_grant()

                # Real Chromium CI caught empty targets falling back to the
                # document's cross-context base target. Keep those in the
                # blocked set above, and prove empty targets work without a
                # base while explicit _self still overrides any base target.
                same_tab_cases = [
                    ('native.html', '#inherited-anchor', 'inherited-link'),
                    ('native.html', '#inherited-form button', 'inherited-form'),
                    ('native.html', '#parent-anchor', 'parent-link'),
                    ('native.html', '#top-anchor', 'top-link'),
                    ('native.html', '#empty-anchor', 'empty-link'),
                    ('native.html', '#empty-form button', 'empty-form'),
                    ('native.html', '#empty-submitter', 'empty-submitter'),
                    ('native.html', '#empty-self-submitter', 'empty-self-submitter'),
                    ('native-base.html', '#label-link span', 'label-link'),
                    ('native-base.html', '#self-anchor', 'self-link'),
                    ('native-base.html', '#self-form button', 'self-form'),
                    ('native-base.html', '#self-submitter', 'self-submitter'),
                    ('native-blank-base.html', '#self-anchor', 'self-link'),
                    ('native-blank-base.html', '#self-form button', 'self-form'),
                    ('native-blank-base.html', '#self-submitter', 'self-submitter'),
                ]
                for fixture, selector, destination in same_tab_cases:
                    await action('navigate',url=f'{base}/{fixture}')
                    before=await tab_snapshot()
                    requests_before=len(destination_requests)
                    result=await action('click',selector=selector)
                    assert not result.get('handoff_required'), (fixture,selector,result)
                    expected=f'{base}/destination.html?case={destination}'
                    for _ in range(50):
                        current=await cdp.evaluate(f"chrome.tabs.get({tab_id})",session)
                        if current['url']==expected and current['status']=='complete': break
                        await asyncio.sleep(.1)
                    assert current['url']==expected and current['status']=='complete', (fixture,selector,current,await tab_snapshot(),destination_requests[requests_before:])
                    assert 'Native destination' in (await action('inspect'))['text']
                    assert len(destination_requests)==requests_before+1
                    assert [x for x in await tab_snapshot() if x['id']!=tab_id] == [x for x in before if x['id']!=tab_id]
                    await assert_only_original_grant()
                await action('navigate',url=base+'/native-base.html')
                before=await tab_snapshot()
                requests_before=list(destination_requests)
                result=await action('click',selector='#non-submit')
                assert not result.get('handoff_required'), result
                assert (await action('inspect',selector='#effects'))['text'] == 'clicked'
                assert await tab_snapshot() == before and destination_requests == requests_before
                for selector in ('#text-label span', '#checkbox-label span'):
                    result=await action('click',selector=selector)
                    assert not result.get('handoff_required'), result
                    assert await tab_snapshot() == before and destination_requests == requests_before
                assert (await action('inspect',selector='#label-result'))['text'] == 'checked'
                await assert_only_original_grant()
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
