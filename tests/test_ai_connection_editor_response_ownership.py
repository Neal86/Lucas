"""Actual composed AI metadata editor responses with synthetic DOM/HTTP ordering.

These tests do not connect to devices, change backend state or establish deployed
acceptance. The Node fixture is a file to preserve Windows command-line limits.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

from gpt_windows_connector import server


class AiEditorIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.elements.append(attrs)


def test_ai_connection_editor_response_ownership(tmp_path):
    node = shutil.which("node")
    assert node, "Node.js is required for AI editor response regressions"
    html = server.webapp._dashboard_html()
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    runtime = next(s for s in scripts if "const state=" in s)
    assert runtime.endswith("\nboot();\n")
    runtime = next(s for s in scripts if "const WEB_LANG=" in s) + "\n" + runtime[:-len("boot();\n")]
    markup = AiEditorIds()
    markup.feed(html)
    script = tmp_path / "ai-editor-response-ownership.mjs"
    script.write_text("const runtime=" + json.dumps(runtime) + ";\nconst markup=" +
                      json.dumps(markup.elements) + ";\n" + AI_EDITOR_CASES, encoding="utf-8")
    result = subprocess.run([node, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# fail 0" in result.stdout or "fail 0" in result.stdout


AI_EDITOR_CASES = r'''

import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
function fixture(language='en'){
  const timers=[],requests=[],elements=new Map(),listeners={},sockets=[],stored=new Map([['lucas-setup-checklist-v1:a@example.test','1'],['lucas-setup-checklist-v1:b@example.test','1']]);
  const ctx={console,URLSearchParams,Date,navigator:{language},location:{pathname:'/dashboard',search:'',hash:'',protocol:'http:',host:'fixture.invalid'},
    setTimeout(fn,delay){timers.push({fn,delay});return timers.length},clearTimeout(){},setInterval(){return 1},clearInterval(){},
    localStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v)},
    NodeFilter:{SHOW_TEXT:4},Node:{ELEMENT_NODE:1,TEXT_NODE:3},MutationObserver:class{observe(){}}};
  ctx.window=ctx;
  const classes=(value='')=>{const values=new Set(value.split(/\s+/).filter(Boolean));return {
    contains:c=>values.has(c),add(...cs){cs.forEach(c=>values.add(c))},remove(...cs){cs.forEach(c=>values.delete(c))},
    toggle(c,on){on=on===undefined?!values.has(c):on;on?values.add(c):values.delete(c);return on}}};
  function element(attrs={}){
    const e={id:attrs.id||'',attrs,value:attrs.value||'',textContent:'',innerHTML:'',style:{},disabled:false,
      classList:classes(attrs.class),focused:false,focus(){e.focused=true},setAttribute(k,v){e.attrs[k]=v},getAttribute:k=>e.attrs[k]??null,
      querySelector(){return null},querySelectorAll(){return []},addEventListener(){}};
    if(e.id){elements.set(e.id,e);ctx[e.id]=e}return e;
  }
  for(const attrs of markup)element(attrs);
  ctx.document={documentElement:{lang:''},body:element(),head:element(),visibilityState:'visible',
    getElementById:id=>elements.get(id)||null,createElement:()=>element(),createTreeWalker:()=>({nextNode:()=>false}),
    querySelector:()=>null,querySelectorAll:s=>s==='.view'?[...elements.values()].filter(e=>e.classList.contains('view')):[],
    addEventListener(event,fn){(listeners[event]??=[]).push(fn)}};
  ctx.addEventListener=ctx.document.addEventListener;
  ctx.history={pushState(_state,_title,path){ctx.location.pathname=path},replaceState(_state,_title,path){ctx.location.pathname=path}};
  ctx.WebSocket=class {static OPEN=1;static CONNECTING=0;readyState=0;
    constructor(url){assert.equal(url,'ws://fixture.invalid/ws/events');sockets.push(this)}
    close(){this.readyState=3}send(){}
  };
  ctx.fetch=(url,options)=>{
    assert.equal(options.credentials,'include');assert.equal(options.signal,undefined);
    assert.ok(!options.method||options.method==='POST'&&url==='/api/logout'||options.method==='PUT'&&['/api/ai-connections/client-a','/api/ai-connections/client-b'].includes(url),'Only explicit synthetic reads/logout/AI metadata PUT allowed');
    assert.ok(['/api/nodes','/api/logs?limit=20','/api/ai-connections','/auth/me','/api/logout','/api/ai-connections/client-a','/api/ai-connections/client-b'].includes(url),'Unexpected request '+url);
    return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  };
  vm.createContext(ctx);vm.runInContext(runtime,ctx);
  const call=code=>vm.runInContext(code,ctx);
  call("state.user={id:'user-a',email:'a@example.test',role:'user'};showApp();dashboard.classList.remove('hidden')");
  return {ctx,requests,timers,elements,listeners,sockets,stored,call,
    respond(index,data,status=200){assert.ok(requests[index],`Missing request ${index}`);requests[index].resolve({status,ok:status>=200&&status<300,json:async()=>data})}}
}
function data(mark){return [{nodes:[{node_id:mark,display_name:mark,authorized:true,online:true}],billing:{requests_used:mark==='OLD'?99:7,request_limit:100000,request_remaining:99993}},
  {logs:[{action:mark,target:mark,created_at:1}]},{clients:[{client_id:mark,display_name:mark}]}]}
function reply(f,start,mark){data(mark).forEach((d,i)=>f.respond(start+i,d))}
async function settle(){for(let i=0;i<16;i++)await Promise.resolve()}
function display(f,mark){assert.equal(f.call('state.nodes[0].node_id'),mark);assert.match(f.ctx.recentLogs.innerHTML,new RegExp(mark));assert.match(f.ctx.aiClientTable.innerHTML,new RegExp(mark));assert.equal(f.call('state.billing.requests_used'),mark==='OLD'?99:7)}
function absent(f,mark){for(const id of ['nodeTable','recentLogs','aiClientTable','metricRequests'])assert.ok(!f.ctx[id].innerHTML.includes(mark),id+' retains '+mark)}
function setup(language){const f=fixture(language);f.call("state.aiClients=[{client_id:'client-a',display_name:'A',note:'A note'},{client_id:'client-b',display_name:'B',note:'B note'}];editAiConnection('client-a')");return f}
function selectB(f){f.call("closeModal('aiManageModal');editAiConnection('client-b')")}
async function finishReads(f,start){await settle();for(let i=start;i<f.requests.length;i++){const r=f.requests[i];if(r.url==='/api/nodes')f.respond(i,{nodes:[],billing:{}});else if(r.url==='/api/logs?limit=20')f.respond(i,{logs:[]});else if(r.url==='/api/ai-connections')f.respond(i,{clients:[{client_id:'client-a',display_name:'A'},{client_id:'client-b',display_name:'B'}]});}}
for(const language of ['en','zh-CN']){
 test(language+': duplicate clicks should dispatch one AI metadata PUT',async()=>{
  const f=setup(language),a=f.call('saveAiConnection()'),b=f.call('saveAiConnection()');const count=f.requests.filter(r=>r.options.method==='PUT').length;
  f.requests.forEach((r,i)=>f.respond(i,{error:'Synthetic rejection'},403));await Promise.all([a,b]);assert.equal(count,1);
 });
 test(language+': late A save should not close newly opened B editor',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');selectB(f);f.respond(0,{});await finishReads(f,1);await p;
  assert.equal(f.ctx.aiManageModal.classList.contains('hidden'),false);assert.equal(f.ctx.aiManageName.value,'B');
 });
 test(language+': late A failure should not toast over B editor',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');selectB(f);f.respond(0,{error:'OBSOLETE_A_FAILURE'},503);await p;
  assert.notEqual(f.elements.get('toast').textContent,'OBSOLETE_A_FAILURE');
 });
 test(language+': old account save 401 should not clear a newer account',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');f.call("showAuth();state.user={id:'user-b',email:'b@example.test'};showApp()");f.respond(0,{error:'OLD_ACCOUNT_401'},401);await p;assert.equal(f.call('state.user?.id'),'user-b');
 });
 test(language+': control current save retains exact captured payload',async()=>{
  const f=setup(language);f.ctx.aiManageName.value='  Edited A  ';f.ctx.aiManageNote.value='  备注  ';const p=f.call('saveAiConnection()');assert.equal(f.requests[0].url,'/api/ai-connections/client-a');assert.deepEqual(JSON.parse(f.requests[0].options.body),{display_name:'Edited A',note:'备注'});f.respond(0,{});await finishReads(f,1);await p;assert.equal(f.ctx.aiManageModal.classList.contains('hidden'),true);assert.equal(f.requests.length,4);
 });
 test(language+': control current 401 returns to auth',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');f.respond(0,{error:'CURRENT_401'},401);await p;assert.equal(f.call('state.user'),null);assert.equal(f.ctx.auth.classList.contains('hidden'),false);
 });
 test(language+': control current failure remains visible',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');f.respond(0,{error:'CURRENT_FAILURE'},503);await p;assert.equal(f.elements.get('toast').textContent,'CURRENT_FAILURE');assert.equal(f.ctx.aiManageModal.classList.contains('hidden'),false);
 });
}

function puts(f){return f.requests.filter(r=>r.options.method==='PUT')}
function busy(f){return f.ctx.aiManageSave.disabled}
function visible(f){return !f.ctx.aiManageModal.classList.contains('hidden')}
for(const language of ['en','zh-CN']){
 test(language+': current save stays busy through its owned dashboard refresh',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');assert.equal(busy(f),true);assert.equal(f.ctx.aiManageSave.attrs['aria-busy'],'true');f.respond(0,{});await settle();
  assert.equal(visible(f),false);assert.equal(busy(f),true);await f.call('saveAiConnection()');assert.equal(puts(f).length,1);await finishReads(f,1);await p;assert.equal(busy(f),false);
 });
 for(const outcome of ['success','network',401,503])test(language+': old '+outcome+' cannot unlock a new pending save',async()=>{
  const f=setup(language),a=f.call('saveAiConnection()');selectB(f);const b=f.call('saveAiConnection()');assert.equal(busy(f),true);
  if(outcome==='network')f.requests[0].reject(new Error('OLD'));else f.respond(0,outcome==='success'?{}:{error:'OLD'},outcome==='success'?200:outcome);
  await a;assert.equal(visible(f),true);assert.equal(busy(f),true);assert.equal(f.ctx.aiManageName.value,'B');assert.equal(f.call('state.user.id'),'user-a');assert.equal(f.requests.length,2);await f.call('saveAiConnection()');assert.equal(puts(f).length,2);
  f.respond(1,{error:'B_CURRENT'},503);await b;assert.equal(busy(f),false);assert.equal(f.elements.get('toast').textContent,'B_CURRENT');
 });
 for(const transition of ['close','escape','navigation','auth'])test(language+': '+transition+' suppresses late save and preserves drafts',async()=>{
  const f=setup(language);f.ctx.aiManageNote.value='draft';f.stored.set('unrelated','keep');const p=f.call('saveAiConnection()');
  if(transition==='close')f.call("closeModal('aiManageModal')");else if(transition==='escape')f.listeners.keydown.forEach(fn=>fn({key:'Escape'}));else if(transition==='navigation')f.call("view('dashboard')");else f.call('showAuth()');
  assert.equal(visible(f),false);assert.equal(busy(f),false);const account=f.call('state.user?.id');f.respond(0,{error:'OLD'},401);await p;assert.equal(f.call('state.user?.id'),account);assert.equal(f.ctx.aiManageNote.value,'draft');assert.equal(f.stored.get('unrelated'),'keep');assert.equal(f.requests.length,1);
 });
 for(const transition of ['resetLoginVerification()',"state.user={id:'new-account'}"])
 test(language+': ownership notices '+transition,async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');f.call(transition);f.respond(0,{error:'OLD'},401);await p;assert.notEqual(f.call('state.user'),null);assert.equal(f.requests.length,1);
 });
 for(const field of ['aiManageName','aiManageNote'])for(const inputEvent of [true,false])test(language+': edit '+field+', event='+inputEvent+' suppresses old completion but preserves its payload',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');const sent=JSON.parse(f.requests[0].options.body);f.ctx[field].value='NEW_DRAFT';if(inputEvent)f.call('aiConnectionEditorInputChanged()');
  assert.equal(busy(f),true);await f.call('saveAiConnection()');assert.equal(puts(f).length,1);f.respond(0,{});await p;assert.equal(visible(f),true);assert.equal(busy(f),false);assert.equal(f.ctx[field].value,'NEW_DRAFT');assert.deepEqual(JSON.parse(f.requests[0].options.body),sent);assert.equal(f.requests.length,1);
  const retry=f.call('saveAiConnection()');assert.equal(puts(f).length,2);f.respond(1,{error:'CURRENT'},503);await retry;assert.equal(busy(f),false);
 });
 test(language+': edit then revert still invalidates the old response',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');f.ctx.aiManageName.value='temporary';f.call('aiConnectionEditorInputChanged()');f.ctx.aiManageName.value='A';f.call('aiConnectionEditorInputChanged()');f.respond(0,{});await p;assert.equal(visible(f),true);assert.equal(busy(f),false);assert.equal(f.requests.length,1);
 });
 for(const status of [200,401,503])test(language+': delayed JSON '+status+' rechecks selection ownership',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');let json;f.requests[0].resolve({status,ok:status===200,json:()=>new Promise(resolve=>{json=resolve})});await settle();selectB(f);json({error:'OLD'});await p;
  assert.equal(visible(f),true);assert.equal(f.ctx.aiManageName.value,'B');assert.equal(f.call('state.user.id'),'user-a');assert.equal(f.requests.length,1);
 });
 for(const failure of ['network',403,503])test(language+': current '+failure+' releases busy for deliberate retry',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');if(failure==='network')f.requests[0].reject(new Error('CURRENT'));else f.respond(0,{error:'CURRENT'},failure);await p;
  assert.equal(visible(f),true);assert.equal(busy(f),false);assert.equal(f.elements.get('toast').textContent,'CURRENT');const retry=f.call('saveAiConnection()');f.respond(1,{});await finishReads(f,2);await retry;assert.equal(puts(f).length,2);assert.equal(busy(f),false);
 });
 for(const status of [401,503])test(language+': reopened editor owns UI over old follow-up refresh '+status,async()=>{
  const f=setup(language),a=f.call('saveAiConnection()');f.respond(0,{});await settle();assert.equal(f.requests.length,4);selectB(f);const b=f.call('saveAiConnection()');f.respond(1,{error:'OLD_REFRESH'},status);f.respond(2,{logs:[]});f.respond(3,{clients:[]});await a;
  assert.equal(visible(f),true);assert.equal(busy(f),true);assert.equal(f.ctx.aiManageName.value,'B');assert.equal(f.call('state.user.id'),'user-a');f.respond(4,{error:'B'},503);await b;
 });
 test(language+': current follow-up refresh failure stays observable without a second PUT',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');f.respond(0,{});await settle();f.respond(1,{error:'CURRENT_REFRESH_FAILURE'},503);f.respond(2,{logs:[]});f.respond(3,{clients:[]});await p;
  assert.equal(f.elements.get('toast').textContent,'CURRENT_REFRESH_FAILURE');assert.equal(puts(f).length,1);assert.equal(busy(f),false);assert.equal(visible(f),false);
 });
 test(language+': current follow-up refresh 401 returns to auth and unlocks',async()=>{
  const f=setup(language),p=f.call('saveAiConnection()');f.respond(0,{});await settle();f.respond(1,{error:'CURRENT_REFRESH_401'},401);f.respond(2,{logs:[]});f.respond(3,{clients:[]});await p;
  assert.equal(f.call('state.user'),null);assert.equal(busy(f),false);assert.equal(visible(f),false);
 });
 test(language+': guest or dismissed editor dispatches no metadata update',async()=>{
  const f=setup(language);f.call("closeModal('aiManageModal')");await f.call('saveAiConnection()');assert.equal(f.requests.length,0);f.call("showAuth();state.aiClients=[{client_id:'client-a'}];editAiConnection('client-a')");await f.call('saveAiConnection()');assert.equal(f.requests.length,0);assert.equal(visible(f),false);
 });
 test(language+': replaced-account boot dismisses old editor before its dashboard reads finish',async()=>{
  const f=setup(language),save=f.call('saveAiConnection()'),boot=f.call('boot()');f.respond(1,{user:{id:'user-b',email:'b@example.test',role:'user'}});await settle();assert.equal(visible(f),false);assert.equal(busy(f),false);
  f.respond(0,{error:'OLD'},401);await save;assert.equal(f.call('state.user.id'),'user-b');await finishReads(f,2);await boot;
 });
 test(language+': dismissed or replaced editor cannot steal focus',()=>{
  const f=setup(language);f.call("closeModal('aiManageModal')");f.timers.filter(t=>t.delay===50).forEach(t=>t.fn());assert.equal(f.ctx.aiManageName.focused,false);
  f.call("editAiConnection('client-b')");f.timers.at(-1).fn();assert.equal(f.ctx.aiManageName.focused,true);
 });
 test(language+': editor markup wires input revisions and accessible busy button',()=>{
  const f=setup(language);assert.equal(f.ctx.aiManageName.attrs.oninput,'aiConnectionEditorInputChanged()');assert.equal(f.ctx.aiManageNote.attrs.oninput,'aiConnectionEditorInputChanged()');assert.equal(f.ctx.aiManageSave.attrs.onclick,'saveAiConnection()');assert.equal(f.ctx.aiManageSave.attrs.type,'button');
 });
}
'''
