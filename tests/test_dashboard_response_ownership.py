"""Actual composed dashboard snapshots with synthetic DOM/HTTP ordering.

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


class DashboardIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.elements.append(attrs)


def test_dashboard_response_ownership(tmp_path):
    node = shutil.which("node")
    assert node, "Node.js is required for dashboard snapshot regressions"
    html = server.webapp._dashboard_html()
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    runtime = next(s for s in scripts if "const state=" in s)
    assert runtime.endswith("\nboot();\n")
    runtime = next(s for s in scripts if "const WEB_LANG=" in s) + "\n" + runtime[:-len("boot();\n")]
    markup = DashboardIds()
    markup.feed(html)
    script = tmp_path / "dashboard-response-ownership.mjs"
    script.write_text("const runtime=" + json.dumps(runtime) + ";\nconst markup=" +
                      json.dumps(markup.elements) + ";\n" + DASHBOARD_CASES, encoding="utf-8")
    result = subprocess.run([node, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# fail 0" in result.stdout or "fail 0" in result.stdout


DASHBOARD_CASES = r'''
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
function fixture(language='en'){
  const requests=[],elements=new Map(),listeners={},sockets=[],stored=new Map([['lucas-setup-checklist-v1:a@example.test','1'],['lucas-setup-checklist-v1:b@example.test','1']]);
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
    assert.ok(!options.method||options.method==='POST'&&url==='/api/logout','Only synthetic logout or reads are allowed');
    assert.ok(['/api/nodes','/api/logs?limit=20','/api/ai-connections','/auth/me','/api/logout'].includes(url),'Unexpected request '+url);
    return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  };
  vm.createContext(ctx);vm.runInContext(runtime,ctx);
  const call=code=>vm.runInContext(code,ctx);
  call("state.user={id:'user-a',email:'a@example.test',role:'user'};showApp();dashboard.classList.remove('hidden')");
  return {ctx,requests,elements,listeners,sockets,stored,call,
    respond(index,data,status=200){assert.ok(requests[index],`Missing request ${index}`);requests[index].resolve({status,ok:status>=200&&status<300,json:async()=>data})}}
}
function data(mark){return [{nodes:[{node_id:mark,display_name:mark,authorized:true,online:true}],billing:{requests_used:mark==='OLD'?99:7,request_limit:100000,request_remaining:99993}},
  {logs:[{action:mark,target:mark,created_at:1}]},{clients:[{client_id:mark,display_name:mark}]}]}
function reply(f,start,mark){data(mark).forEach((d,i)=>f.respond(start+i,d))}
async function settle(){for(let i=0;i<16;i++)await Promise.resolve()}
function display(f,mark){assert.equal(f.call('state.nodes[0].node_id'),mark);assert.match(f.ctx.recentLogs.innerHTML,new RegExp(mark));assert.match(f.ctx.aiClientTable.innerHTML,new RegExp(mark));assert.equal(f.call('state.billing.requests_used'),mark==='OLD'?99:7)}
function absent(f,mark){for(const id of ['nodeTable','recentLogs','aiClientTable','metricRequests'])assert.ok(!f.ctx[id].innerHTML.includes(mark),id+' retains '+mark)}
for(const language of ['en','zh-CN']){
 test(language+': current refresh renders the unchanged snapshot and three reads',async()=>{
  const f=fixture(language),p=f.call('refresh()');assert.deepEqual(f.requests.map(r=>r.url),['/api/nodes','/api/logs?limit=20','/api/ai-connections']);reply(f,0,'CURRENT');await p;display(f,'CURRENT');
  assert.equal(f.ctx.metricAiClients.textContent,1);assert.match(f.ctx.metricRequests.innerHTML,/99,993/);
 });
 test(language+': newer refresh retains ownership after older success',async()=>{
  const f=fixture(language),old=f.call('refresh()'),fresh=f.call('refresh()');reply(f,3,'NEW');await fresh;reply(f,0,'OLD');await old;display(f,'NEW');absent(f,'OLD');
 });
 test(language+': older success is suppressed while newer request waits',async()=>{
  const f=fixture(language),old=f.call('refresh()'),fresh=f.call('refresh()');reply(f,0,'OLD');await old;absent(f,'OLD');assert.equal(f.call('state.nodes.length'),0);reply(f,3,'NEW');await fresh;display(f,'NEW');
 });
 for(const failure of ['network',503,401])test(language+': stale '+failure+' cannot affect a newer success',async()=>{
  const f=fixture(language),old=f.call('refresh()'),fresh=f.call('refresh()');reply(f,3,'NEW');await fresh;
  if(failure==='network')f.requests[0].reject(new Error('OLD'));else f.respond(0,{error:'OLD'},failure);
  f.respond(1,{logs:[]});f.respond(2,{clients:[]});await old;display(f,'NEW');assert.equal(f.call('state.user.id'),'user-a');assert.equal(f.ctx.auth.classList.contains('hidden'),true);
 });
 for(const failure of ['network',503])test(language+': current '+failure+' remains observable and retry works',async()=>{
  const f=fixture(language),p=f.call('refresh()');const rejection=assert.rejects(p,/CURRENT_FAILURE/);
  if(failure==='network')f.requests[1].reject(new Error('CURRENT_FAILURE'));else f.respond(1,{error:'CURRENT_FAILURE'},failure);
  f.respond(0,{nodes:[]});f.respond(2,{clients:[]});await rejection;
  assert.equal(f.call('state.user.id'),'user-a');const retry=f.call('refresh()');reply(f,3,'RETRY');await retry;display(f,'RETRY');
 });
 test(language+': current 401 opens auth and clears the dashboard',async()=>{
  const f=fixture(language),first=f.call('refresh()');reply(f,0,'OLD');await first;
  const p=f.call('refresh()');f.respond(3,{error:'expired'},401);f.respond(4,{logs:[]});f.respond(5,{clients:[]});await p;
  assert.equal(f.call('state.user'),null);assert.equal(f.ctx.auth.classList.contains('hidden'),false);assert.equal(f.call('state.nodes.length'),0);assert.equal(f.call('state.aiClients.length'),0);assert.equal(f.call('state.billing'),null);absent(f,'OLD');
 });
 for(const transition of ["showAuth()","resetLoginVerification()","state.user={id:'user-b'}","state.user=null"])
 test(language+': account or generation transition invalidates pending reads '+transition,async()=>{
  const f=fixture(language),p=f.call('refresh()');f.call(transition);reply(f,0,'OLD');await p;absent(f,'OLD');
 });
 for(const status of [200,401,503])test(language+': old account '+status+' cannot affect a newer session',async()=>{
  const f=fixture(language),old=f.call('refresh()');f.call("showAuth();state.user={id:'user-b',email:'b@example.test'};showApp()");const fresh=f.call('refresh()');reply(f,3,'NEW');await fresh;
  if(status===200)reply(f,0,'OLD');else{f.respond(0,{error:'OLD'},status);f.respond(1,{logs:[]});f.respond(2,{clients:[]})}await old;
  assert.equal(f.call('state.user.id'),'user-b');display(f,'NEW');absent(f,'OLD');assert.equal(f.ctx.auth.classList.contains('hidden'),true);
 });
 for(const status of [200,401])test(language+': delayed JSON '+status+' rechecks request ownership',async()=>{
  const f=fixture(language),old=f.call('refresh()');let finish;
  f.requests[0].resolve({status,ok:status===200,json:()=>new Promise(resolve=>{finish=resolve})});f.respond(1,data('OLD')[1]);f.respond(2,data('OLD')[2]);await settle();
  const fresh=f.call('refresh()');reply(f,3,'NEW');await fresh;finish(data('OLD')[0]);await old;display(f,'NEW');assert.equal(f.call('state.user.id'),'user-a');
 });
 test(language+': auth reset clears cached rows without modifying unrelated drafts',async()=>{
  const f=fixture(language),p=f.call('refresh()');reply(f,0,'OLD');await p;
  const ids=['manageNodeName','aiManageName','aiManageNote','connectNodeId','connectCode','logAction','logTarget','taskRunDays'];
  ids.forEach(id=>f.ctx[id].value='DRAFT:'+id);f.stored.set('unrelated-draft','keep');f.call("state.unrelatedDraft={text:'keep'};showAuth()");
  ids.forEach(id=>assert.equal(f.ctx[id].value,'DRAFT:'+id));assert.equal(f.stored.get('unrelated-draft'),'keep');assert.equal(f.call('state.unrelatedDraft.text'),'keep');
  assert.equal(f.call('state.nodes.length'),0);assert.equal(f.call('state.aiClients.length'),0);assert.equal(f.call('state.billing'),null);absent(f,'OLD');assert.equal(f.ctx.metricAiClients.textContent,0);assert.match(f.ctx.metricRequests.innerHTML,/—/);
 });
 for(const authReset of [true,false])test(language+': new-account boot hides old rows while refresh waits, reset='+authReset,async()=>{
  const f=fixture(language),first=f.call('refresh()');reply(f,0,'OLD');await first;if(authReset)f.call('showAuth()');
  const next=f.call('boot()');f.respond(3,{user:{id:'user-b',email:'b@example.test',role:'user'}});await settle();
  assert.equal(f.ctx.app.classList.contains('hidden'),false);absent(f,'OLD');assert.equal(f.call('state.nodes.length'),0);
  reply(f,4,'NEW');await next;display(f,'NEW');assert.equal(f.call('state.user.id'),'user-b');assert.equal(f.sockets.length,1);
 });
 test(language+': guest refresh dispatches nothing',async()=>{const f=fixture(language);f.call('showAuth()');await f.call('refresh()');assert.equal(f.requests.length,0)});
 test(language+': caller predicate prevents dispatch and suppresses later results',async()=>{
  const f=fixture(language);await f.call('refresh(()=>false)');assert.equal(f.requests.length,0);
  f.call('globalThis.callerActive=true');const p=f.call('refresh(()=>callerActive)');f.call('callerActive=false');reply(f,0,'OLD');await p;absent(f,'OLD');
 });
 test(language+': caller predicate also suppresses an obsolete 401',async()=>{
  const f=fixture(language);f.call('globalThis.callerActive=true');const p=f.call('refresh(()=>callerActive)');f.call('callerActive=false');f.respond(0,{error:'OLD'},401);f.respond(1,{logs:[]});f.respond(2,{clients:[]});await p;assert.equal(f.call('state.user.id'),'user-a');
 });
 test(language+': visibility refresh supersedes an older snapshot',async()=>{
  const f=fixture(language),old=f.call('refresh()');f.listeners.visibilitychange.forEach(fn=>fn());assert.equal(f.requests.length,6);
  reply(f,3,'NEW');await settle();reply(f,0,'OLD');await old;display(f,'NEW');assert.equal(f.sockets.length,1);
 });
 test(language+': completed logout invalidates reads without changing its request',async()=>{
  const f=fixture(language),old=f.call('refresh()'),out=f.call('logout()');assert.equal(f.requests[3].url,'/api/logout');assert.equal(f.requests[3].options.method,'POST');f.respond(3,{});await out;reply(f,0,'OLD');await old;absent(f,'OLD');assert.equal(f.call('state.user'),null);
 });
 test(language+': current failed refresh does not fall back to an older success',async()=>{
  const f=fixture(language),old=f.call('refresh()'),fresh=f.call('refresh()');const rejected=assert.rejects(fresh,/CURRENT_FAILURE/);
  f.respond(3,{error:'CURRENT_FAILURE'},503);f.respond(4,{logs:[]});f.respond(5,{clients:[]});await rejected;reply(f,0,'OLD');await old;absent(f,'OLD');
 });
 test(language+': current boot refresh error retains authenticated app and retry message',async()=>{
  const f=fixture(language);f.call('showAuth()');const p=f.call('boot()');f.respond(0,{user:{id:'user-b',email:'b@example.test',role:'user'}});await settle();
  f.respond(1,{error:'CURRENT_FAILURE'},503);f.respond(2,{logs:[]});f.respond(3,{clients:[]});await p;
  assert.equal(f.call('state.user.id'),'user-b');assert.equal(f.ctx.app.classList.contains('hidden'),false);assert.match(f.elements.get('toast').textContent,language==='en'?/Some dashboard data failed/:/部分数据加载失败/);
 });
}

for(const language of ['en','zh-CN']){
 for(let endpoint=0;endpoint<3;endpoint++){
  test(language+': stale 401 from endpoint '+endpoint+' after other old siblings finish',async()=>{
   const f=fixture(language),old=f.call('refresh()');
   data('OLD').forEach((d,i)=>{if(i!==endpoint)f.respond(i,d)});await settle();
   const fresh=f.call('refresh()');reply(f,3,'NEW');await fresh;
   f.respond(endpoint,{error:'OLD_401'},401);await old;display(f,'NEW');assert.equal(f.call('state.user.id'),'user-a');
  });
  test(language+': current 401 from endpoint '+endpoint+' rejects boot ownership',async()=>{
   const f=fixture(language);f.call('showAuth()');const p=f.call('boot()');f.respond(0,{user:{id:'user-b',email:'b@example.test',role:'user'}});await settle();
   f.respond(endpoint+1,{error:'CURRENT_401'},401);data('CURRENT').forEach((d,i)=>{if(i!==endpoint)f.respond(i+1,d)});await p;
   assert.equal(f.call('state.user'),null);assert.equal(f.ctx.app.classList.contains('hidden'),true);assert.equal(f.sockets.length,0);assert.equal(f.elements.get('toast').textContent,'');
  });
  test(language+': 401 sibling after earlier failure cannot affect newer session, endpoint '+endpoint,async()=>{
   const f=fixture(language),old=f.call('refresh()'),rejected=assert.rejects(old,/CURRENT_FAILURE/),other=(endpoint+1)%3;
   f.respond(other,{error:'CURRENT_FAILURE'},503);await rejected;
   f.call("showAuth();state.user={id:'user-b',email:'b@example.test',role:'user'};showApp()");const fresh=f.call('refresh()');reply(f,3,'NEW');await fresh;
   f.respond(endpoint,{error:'OLD_401'},401);f.respond(3-endpoint-other,data('OLD')[3-endpoint-other]);await settle();display(f,'NEW');assert.equal(f.call('state.user.id'),'user-b');
  });
 }
 test(language+': same-account boot keeps cached data while new read waits',async()=>{
  const f=fixture(language),initial=f.call('refresh()');reply(f,0,'CACHED');await initial;
  const old=f.call('refresh()'),boot=f.call('boot()');f.respond(6,{user:{id:'user-a',email:'a@example.test',role:'user'}});await settle();
  display(f,'CACHED');reply(f,3,'OLD');await old;display(f,'CACHED');reply(f,7,'NEW');await boot;display(f,'NEW');
 });
 test(language+': failed current background refresh retains committed same-account data',async()=>{
  const f=fixture(language),initial=f.call('refresh()');reply(f,0,'CACHED');await initial;
  const p=f.call('refresh()'),rejected=assert.rejects(p,/CURRENT_FAILURE/);f.respond(3,{error:'CURRENT_FAILURE'},503);f.respond(4,{logs:[]});f.respond(5,{clients:[]});await rejected;display(f,'CACHED');
 });
 test(language+': auth-me failure clears existing cached dashboard',async()=>{
  const f=fixture(language),initial=f.call('refresh()');reply(f,0,'OLD');await initial;const boot=f.call('boot()');f.respond(3,{error:'AUTH_FAILURE'},503);await boot;
  absent(f,'OLD');assert.equal(f.call('state.user'),null);assert.equal(f.ctx.app.classList.contains('hidden'),true);
 });
 test(language+': stale malformed success is never rendered',async()=>{
  const f=fixture(language),old=f.call('refresh()'),fresh=f.call('refresh()');reply(f,3,'NEW');await fresh;f.respond(0,{nodes:null});f.respond(1,{logs:null});f.respond(2,{clients:null});await old;display(f,'NEW');
 });
 test(language+': empty current refresh clears a prior successful dashboard',async()=>{
  const f=fixture(language),initial=f.call('refresh()');reply(f,0,'OLD');await initial;const p=f.call('refresh()');f.respond(3,{nodes:[]});f.respond(4,{logs:[]});f.respond(5,{});await p;
  absent(f,'OLD');assert.equal(f.call('state.nodes.length'),0);assert.equal(f.call('state.aiClients.length'),0);assert.equal(f.call('state.billing'),null);assert.equal(f.ctx.metricAiClients.textContent,0);
 });
}

'''
