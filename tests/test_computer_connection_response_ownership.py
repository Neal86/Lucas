"""Actual composed connection modals with synthetic DOM/HTTP ordering.

These tests model dispatched POST effects separately from UI suppression. They
do not connect to devices, change backend state or establish deployed
acceptance. The Node fixture is a file to preserve Windows command-line limits.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

from gpt_windows_connector import server


class ConnectionIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.elements.append(attrs)


def test_computer_connection_response_ownership(tmp_path):
    node = shutil.which("node")
    assert node, "Node.js is required for connection modal regressions"
    html = server.webapp._dashboard_html()
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    runtime = next(s for s in scripts if "const state=" in s)
    assert runtime.endswith("\nboot();\n")
    runtime = next(s for s in scripts if "const WEB_LANG=" in s) + "\n" + runtime[:-len("boot();\n")]
    markup = ConnectionIds()
    markup.feed(html)
    script = tmp_path / "computer-connection-response-ownership.mjs"
    script.write_text("const runtime=" + json.dumps(runtime) + ";\nconst markup=" +
                      json.dumps(markup.elements) + ";\n" + CONNECTION_CASES, encoding="utf-8")
    result = subprocess.run([node, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# fail 0" in result.stdout or "fail 0" in result.stdout


CONNECTION_CASES = r'''

import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
function fixture(language='en'){
  const requests=[],effects=[],elements=new Map(),listeners={},sockets=[],stored=new Map([['lucas-setup-checklist-v1:a@example.test','1'],['lucas-setup-checklist-v1:b@example.test','1']]);
  const ctx={console,URLSearchParams,Date,navigator:{language},location:{pathname:'/dashboard',search:'',hash:'',protocol:'http:',host:'fixture.invalid'},
    setTimeout(){return 1},clearTimeout(){},setInterval(){return 1},clearInterval(){},
    localStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v)},
    NodeFilter:{SHOW_TEXT:4},Node:{ELEMENT_NODE:1,TEXT_NODE:3},MutationObserver:class{observe(){}}};
  ctx.window=ctx;
  const classes=(value='')=>{const values=new Set(value.split(/\s+/).filter(Boolean));return {
    contains:c=>values.has(c),add(...cs){cs.forEach(c=>values.add(c))},remove(...cs){cs.forEach(c=>values.delete(c))},
    toggle(c,on){on=on===undefined?!values.has(c):on;on?values.add(c):values.delete(c);return on}}};
  function element(attrs={}){
    const e={id:attrs.id||'',attrs,value:attrs.value||'',textContent:'',innerHTML:'',style:{},disabled:false,
      classList:classes(attrs.class),focus(){},setAttribute(k,v){e.attrs[k]=v},getAttribute:k=>e.attrs[k]??null,
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
    assert.ok(!options.method||options.method==='POST'&&['/api/logout','/api/nodes/request-access'].includes(url),'Only explicitly allowed synthetic POSTs or reads are allowed');
    assert.ok(['/api/nodes','/api/logs?limit=20','/api/ai-connections','/auth/me','/api/logout','/api/nodes/request-access'].includes(url),'Unexpected request '+url);
    return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  };
  vm.createContext(ctx);vm.runInContext(runtime,ctx);
  const call=code=>vm.runInContext(code,ctx);
  call("state.user={id:'user-a',email:'a@example.test',role:'user'};showApp();dashboard.classList.remove('hidden')");
  return {ctx,requests,effects,elements,listeners,sockets,stored,call,
    respond(index,data,status=200){assert.ok(requests[index],`Missing request ${index}`);assert.ok(!requests[index].settled,'Response already settled');requests[index].settled=true;if(requests[index].url==='/api/nodes/request-access'&&status===200&&(data.pending||data.authorized))effects.push({payload:JSON.parse(requests[index].options.body),result:data});requests[index].resolve({status,ok:status>=200&&status<300,json:async()=>data})}}
}
async function settle(){for(let i=0;i<18;i++)await Promise.resolve()}
function open(f,node='computer-a',code='12345678'){f.call('openConnectModal()');f.ctx.connectNodeId.value=node;f.ctx.connectCode.value=code}
function send(f){return f.call('requestNodeAccess()')}
function isOpen(f){return !f.ctx.connectModal.classList.contains('hidden')}
function busy(f){return f.ctx.connectSubmit.disabled}
function result(f){return f.ctx.connectResult.textContent}
function posts(f){return f.requests.filter(r=>r.url==='/api/nodes/request-access')}
function assertPost(f,index,node='computer-a',code='12345678'){
 const r=f.requests[index];assert.equal(r.url,'/api/nodes/request-access');assert.equal(r.options.method,'POST');assert.deepEqual(JSON.parse(r.options.body),{node_id:node,connection_code:code});assert.equal(r.options.signal,undefined);
}
async function fillRefresh(f){await settle();for(let i=0;i<f.requests.length;i++){
 const r=f.requests[i];if(r.settled||r.url==='/api/nodes/request-access'||r.url==='/auth/me'||r.url==='/api/logout')continue;
 f.respond(i,r.url==='/api/nodes'?{nodes:[]}:r.url==='/api/ai-connections'?{clients:[]}:{logs:[]});
}await settle()}
function translated(f,text){return f.call('wt('+JSON.stringify(text)+')')}
for(const language of ['en','zh-CN']){
 for(const outcome of ['pending','authorized'])test(language+': duplicate current submits dispatch one unchanged '+outcome+' request',async()=>{
  const f=fixture(language);open(f,'  computer-a  ','  12345678  ');const a=send(f),b=send(f);assert.equal(posts(f).length,1);assertPost(f,0);assert.equal(busy(f),true);assert.equal(f.ctx.connectSubmit.attrs['aria-busy'],'true');
  f.respond(0,{[outcome]:true});await settle();assert.equal(f.requests.length,4);assert.equal(busy(f),true);await send(f);assert.equal(posts(f).length,1);
  await fillRefresh(f);await Promise.all([a,b]);assert.equal(busy(f),false);assert.equal(f.ctx.connectSubmit.attrs['aria-busy'],'false');
  assert.equal(result(f),translated(f,outcome==='pending'?'Access request sent. Waiting for local approval on the target computer.':'Access approved on the target computer.'));assert.equal(f.effects.length,1);
 });
 test(language+': delayed A approval cannot replace B invalid-code error',async()=>{
  const f=fixture(language);open(f);const a=send(f);f.call("closeModal('connectModal')");open(f,'computer-b','87654321');const b=send(f);assertPost(f,1,'computer-b','87654321');
  f.respond(1,{error:'invalid connection code'});await b;const current=result(f);f.respond(0,{authorized:true});await a;
  assert.equal(result(f),current);assert.equal(current,translated(f,'Connection Code is incorrect.'));assert.equal(f.ctx.connectNodeId.value,'computer-b');assert.equal(isOpen(f),true);assert.equal(f.requests.length,2);assert.equal(f.effects.length,1);
 });
 for(const failure of ['network',503,401])test(language+': obsolete '+failure+' cannot replace B pending result',async()=>{
  const f=fixture(language);open(f);const a=send(f);f.call("closeModal('connectModal')");open(f,'computer-b','87654321');const b=send(f);f.respond(1,{pending:true});await fillRefresh(f);await b;
  const current=result(f);if(failure==='network')f.requests[0].reject(new Error('OLD_FAILURE'));else f.respond(0,{error:'OLD_FAILURE'},failure);await a;
  assert.equal(result(f),current);assert.equal(current,translated(f,'Access request sent. Waiting for local approval on the target computer.'));assert.equal(f.call('state.user.id'),'user-a');assert.equal(f.ctx.auth.classList.contains('hidden'),true);assert.equal(posts(f).length,2);
 });
 for(const close of ["closeModal('connectModal')","document.addEventListener", "view('dashboard',null)","showAuth()"])
 test(language+': dismissal invalidates UI without cancelling the dispatched POST '+close,async()=>{
  const f=fixture(language);open(f);const p=send(f);
  if(close==='document.addEventListener')f.listeners.keydown.forEach(fn=>fn({key:'Escape'}));else f.call(close);
  const before=result(f);assert.equal(isOpen(f),false);assert.equal(busy(f),false);f.respond(0,{pending:true});await p;
  assert.equal(result(f),before);assert.equal(isOpen(f),false);assert.equal(f.requests.length,1);assert.equal(f.effects.length,1);assertPost(f,0);
 });
 for(const transition of ["resetLoginVerification()","state.user={id:'user-b'}","state.user=null"])
 test(language+': session ownership suppresses stale approval '+transition,async()=>{
  const f=fixture(language);open(f);const p=send(f);f.call(transition);const before=result(f);f.respond(0,{authorized:true});await p;assert.equal(result(f),before);assert.equal(f.requests.length,1);assert.equal(f.effects.length,1);
 });
 test(language+': old session 401 cannot sign out a new account',async()=>{
  const f=fixture(language);open(f);const a=send(f);f.call("showAuth();state.user={id:'user-b',email:'b@example.test'};showApp()");open(f,'computer-b','87654321');const b=send(f);f.respond(1,{pending:true});await fillRefresh(f);await b;
  f.respond(0,{error:'OLD_401'},401);await a;assert.equal(f.call('state.user.id'),'user-b');assert.equal(isOpen(f),true);assert.equal(f.ctx.auth.classList.contains('hidden'),true);
 });
 test(language+': stale finally cannot unlock a newer request',async()=>{
  const f=fixture(language);open(f);const a=send(f);f.call("closeModal('connectModal')");open(f,'computer-b','87654321');const b=send(f);f.respond(0,{authorized:true});await a;
  assert.equal(busy(f),true);assert.equal(result(f),translated(f,'Sending access request…'));await send(f);assert.equal(posts(f).length,2);
  f.respond(1,{pending:true});await fillRefresh(f);await b;assert.equal(busy(f),false);assert.equal(f.effects.length,2);
 });
 for(const status of [200,401])test(language+': delayed JSON '+status+' rechecks modal ownership',async()=>{
  const f=fixture(language);open(f);const a=send(f);let finish;f.requests[0].resolve({status,ok:status===200,json:()=>new Promise(resolve=>{finish=resolve})});await settle();
  f.call("closeModal('connectModal')");open(f,'computer-b','87654321');const b=send(f);f.respond(1,{error:'invalid connection code'});await b;const current=result(f);finish({authorized:true,error:'OLD'});await a;assert.equal(result(f),current);assert.equal(f.call('state.user.id'),'user-a');assert.equal(f.requests.length,2);
 });
 for(const field of ['connectNodeId','connectCode'])for(const event of [true,false])test(language+': edited '+field+' suppresses old result, event='+event,async()=>{
  const f=fixture(language);open(f);const p=send(f);f.ctx[field].value=field==='connectNodeId'?'computer-b':'87654321';if(event)f.call('computerConnectionInputChanged()');
  f.respond(0,{authorized:true});await p;assert.equal(result(f),'');assert.equal(f.ctx.connectResult.classList.contains('hidden'),true);assert.equal(busy(f),false);assert.equal(f.requests.length,1);assert.equal(f.effects.length,1);assertPost(f,0);
  const retry=send(f);assert.equal(posts(f).length,2);f.respond(1,{error:'invalid connection code'});await retry;assert.equal(result(f),translated(f,'Connection Code is incorrect.'));
 });
 test(language+': edit away and back still invalidates the older approval',async()=>{
  const f=fixture(language);open(f);const p=send(f);f.ctx.connectNodeId.value='B';f.call('computerConnectionInputChanged()');f.ctx.connectNodeId.value='computer-a';f.call('computerConnectionInputChanged()');f.respond(0,{authorized:true});await p;assert.equal(result(f),'');assert.equal(f.requests.length,1);assert.equal(busy(f),false);
 });
 for(const failure of ['network',403,503])test(language+': current '+failure+' remains visible and allows a deliberate retry',async()=>{
  const f=fixture(language);open(f);const p=send(f);if(failure==='network')f.requests[0].reject(new Error('CURRENT_FAILURE'));else f.respond(0,{error:'CURRENT_FAILURE'},failure);await p;
  assert.equal(result(f),'CURRENT_FAILURE');assert.equal(busy(f),false);assert.equal(posts(f).length,1);const retry=send(f);assert.equal(posts(f).length,2);f.respond(1,{pending:true});await fillRefresh(f);await retry;assert.equal(busy(f),false);
 });
 test(language+': current 401 opens auth, closes modal and releases busy state',async()=>{
  const f=fixture(language);open(f);const p=send(f);f.respond(0,{error:'CURRENT_401'},401);await p;assert.equal(f.call('state.user'),null);assert.equal(f.ctx.auth.classList.contains('hidden'),false);assert.equal(isOpen(f),false);assert.equal(busy(f),false);assert.equal(f.requests.length,1);
 });
 test(language+': close after accepted POST suppresses the follow-up refresh 401',async()=>{
  const f=fixture(language);open(f);const p=send(f);f.respond(0,{pending:true});await settle();assert.equal(f.requests.length,4);f.call("closeModal('connectModal')");f.respond(1,{error:'OLD_REFRESH_401'},401);f.respond(2,{logs:[]});f.respond(3,{clients:[]});await p;
  assert.equal(f.call('state.user.id'),'user-a');assert.equal(isOpen(f),false);assert.equal(busy(f),false);assert.equal(f.effects.length,1);assert.equal(posts(f).length,1);
 });
 test(language+': current follow-up refresh failure stays observable without a second POST',async()=>{
  const f=fixture(language);open(f);const p=send(f);f.respond(0,{pending:true});await settle();f.respond(1,{error:'CURRENT_REFRESH_FAILURE'},503);f.respond(2,{logs:[]});f.respond(3,{clients:[]});await p;
  assert.equal(result(f),'CURRENT_REFRESH_FAILURE');assert.equal(busy(f),false);assert.equal(posts(f).length,1);assert.equal(f.effects.length,1);
 });
 test(language+': dismissed or guest valid requests do not dispatch',async()=>{
  const f=fixture(language);open(f);f.call("closeModal('connectModal')");await send(f);assert.equal(f.requests.length,0);f.call('showAuth()');open(f);await send(f);assert.equal(f.requests.length,0);
 });
 test(language+': reopen resets busy/result and leaves unrelated drafts untouched',async()=>{
  const f=fixture(language);f.ctx.aiManageNote.value='OTHER_DRAFT';f.stored.set('draft','keep');open(f);const p=send(f);f.call("closeModal('connectModal')");open(f);assert.equal(busy(f),false);assert.equal(result(f),'');assert.equal(f.ctx.aiManageNote.value,'OTHER_DRAFT');assert.equal(f.stored.get('draft'),'keep');f.respond(0,{pending:true});await p;assert.equal(result(f),'');
 });
 test(language+': input hooks and submit button are wired in actual markup',()=>{
  const f=fixture(language);assert.equal(f.ctx.connectNodeId.attrs.oninput,'computerConnectionInputChanged()');assert.equal(f.ctx.connectCode.attrs.oninput,'computerConnectionInputChanged()');assert.equal(f.ctx.connectSubmit.attrs.onclick,'requestNodeAccess()');assert.equal(f.ctx.connectSubmit.attrs.type,'button');
 });
}
'''
