"""Actual composed admin runtime under synthetic, deferred HTTP responses.

No requests leave the Node VM. Explicitly enabled PUT fixtures model completed
writes separately from UI suppression; these are not live mutation acceptance.
The generated script is a file, keeping Windows command-line size bounded.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

from gpt_windows_connector import server


class DashboardMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.admin_buttons = []
        self.in_admin_tabs = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs)
        if attrs.get("id") == "adminTabs":
            self.in_admin_tabs = True
        elif self.in_admin_tabs and tag == "button":
            self.admin_buttons.append(attrs)

    def handle_endtag(self, tag):
        if self.in_admin_tabs and tag == "div":
            self.in_admin_tabs = False


def test_admin_response_ownership(tmp_path):
    node = shutil.which("node")
    assert node, "Node.js is required for composed admin regressions"
    html = server.webapp._dashboard_html()
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    runtime = next(s for s in scripts if "const state=" in s)
    i18n = next(s for s in scripts if "const WEB_LANG=" in s)
    assert runtime.endswith("\nboot();\n")
    # Omit automatic boot only. Keep actual API/auth/navigation/close handlers.
    runtime = i18n + "\n" + runtime[:-len("boot();\n")]
    markup = DashboardMarkup()
    markup.feed(html)
    data = {"elements": markup.ids, "admin_buttons": markup.admin_buttons}
    script = tmp_path / "admin-response-ownership.mjs"
    script.write_text("const runtime=" + json.dumps(runtime) + ";\nconst markup=" +
                      json.dumps(data) + ";\n" + ADMIN_CASES, encoding="utf-8")
    result = subprocess.run([node, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# fail 0" in result.stdout or "fail 0" in result.stdout


ADMIN_CASES = r'''
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const tabs=['dashboard','users','usage','nodes','operations','subscriptions','system'];
function fixture({allowSave=false}={}){
  const requests=[],effects=[],elements=new Map(),listeners={};
  const ctx={console,URLSearchParams,Date,navigator:{language:'en'},location:{pathname:'/admin/users',search:'',hash:'',protocol:'http:',host:'fixture.invalid'},
    setTimeout(){return 1},clearTimeout(){},setInterval(){return 1},clearInterval(){}};
  ctx.window=ctx;
  const classes=(value='')=>{const values=new Set(value.split(/\s+/).filter(Boolean));return {
    contains:c=>values.has(c),add(...cs){cs.forEach(c=>values.add(c))},remove(...cs){cs.forEach(c=>values.delete(c))},
    toggle(c,on){on=on===undefined?!values.has(c):on;on?values.add(c):values.delete(c);return on}}};
  function element(attrs={}){
    let html='';const e={id:attrs.id||'',attrs,value:attrs.value||'',textContent:'',style:{},disabled:false,
      classList:classes(attrs.class),focus(){},remove(){elements.delete(e.id)},setAttribute(k,v){e.attrs[k]=v},getAttribute:k=>e.attrs[k]??null,
      querySelector(){return null},querySelectorAll(){return []},addEventListener(){}};
    Object.defineProperty(e,'innerHTML',{get:()=>html,set(value){html=String(value);for(const m of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)){
      const a={id:m[1]};for(const x of m[0].matchAll(/([\w-]+)="([^"]*)"/g))a[x[1]]=x[2];element(a)}}});
    if(e.id){elements.set(e.id,e);ctx[e.id]=e}return e;
  }
  for(const attrs of markup.elements)element(attrs);
  const buttons=markup.admin_buttons.map(element);
  ctx.document={documentElement:{lang:''},body:element(),head:element(),
    getElementById:id=>elements.get(id)||null,createElement:()=>element(),
    querySelector:()=>null,
    querySelectorAll(selector){if(selector==='#adminTabs button')return buttons;if(selector==='.view')return [...elements.values()].filter(e=>e.classList.contains('view'));return []},
    addEventListener(event,fn){(listeners[event]??=[]).push(fn)}};
  ctx.addEventListener=ctx.document.addEventListener;
  ctx.history={pushState(_state,_title,path){ctx.location.pathname=path},replaceState(_state,_title,path){ctx.location.pathname=path}};
  ctx.fetch=(url,options)=>{
    assert.equal(options.credentials,'include');assert.ok(!options.method||options.method==='GET'||allowSave&&options.method==='PUT'&&url.startsWith('/api/admin/users/'),'Only explicitly enabled synthetic saves are permitted');assert.equal(options.signal,undefined,'UI ownership must not abort a dispatched request');
    assert.ok(url.startsWith('/api/admin/'),'Unexpected non-admin request '+url);
    return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  };
  vm.createContext(ctx);vm.runInContext(runtime,ctx);
  const call=code=>vm.runInContext(code,ctx);
  call("state.user={id:'synthetic-admin',email:'admin@example.test',role:'super_admin'};showApp();admin.classList.remove('hidden')");
  return {ctx,requests,effects,elements,buttons,listeners,call,
    select(tab){return call(`adminTab('${tab}',adminButton('${tab}'))`)},
    detail(id){return call(`showAdminUser(${JSON.stringify(id)})`)},
    respond(index,data,status=200){assert.ok(requests[index],`Missing request ${index}`);if(requests[index].options.method==='PUT'&&status>=200&&status<300)effects.push({url:requests[index].url,body:JSON.parse(requests[index].options.body)});requests[index].resolve({status,ok:status>=200&&status<300,json:async()=>data})},
    close(){call("closeModal('adminUserModal')")},
    escape(){listeners.keydown.forEach(fn=>fn({key:'Escape'}))},
    modalOpen(){return !ctx.adminUserModal.classList.contains('hidden')},
    selected(){return tabs[buttons.findIndex(b=>b.classList.contains('primary'))]},
    detailEmail(){return ctx.adminUserDetail.innerHTML.match(/<h3>(.*?)<\/h3>/)?.[1]}}
}
function user(id){return {user:{id,email:id+'@example.test',role:'user',status:'active'},
  entitlements:{plan_name:'Lucas Beta',nodes_used:1,node_limit:3,ai_accounts_used:1,ai_account_limit:3,expansion_quantity:0,requests_used:10,requests_pending:5,requests_unconfirmed:11,request_remaining:99974,request_limit:100000},
  usage:{last30:10},subscription:{plan:'free'},admin_overrides:{bonus_requests:7},nodes:[],operations:[],unresolved_operations:[]}}
function payload(tab,marker){
  switch(tab){
    case 'dashboard':return {users:3,active_users_7d:2,online_nodes:1,operations_today:4,operations_30d:5,paid_users:0,recent:[{email:marker,action:'read',created_at:1}]};
    case 'users':return {users:[{id:marker,email:marker,role:'user',status:'active',plan:'free',node_count:1,operations_30d:2}]};
    case 'usage':return {operations_30d:2,execution_seconds_30d:1,success_rate:100,errors_30d:0,by_tool:{},top_users:[{email:marker,n:2}]};
    case 'nodes':return {nodes:[{node_id:marker,name:marker,platform:'fixture',online:false,allowed_folder_count:0,updated_at:1}]};
    case 'operations':return {operations:[{created_at:1,email:marker,action:'read',status:'success'}]};
    case 'subscriptions':return {subscriptions:[{email:marker,plan:'free',status:'active'}]};
    case 'system':return {gateway:marker,database:'ok',online_nodes:1,total_nodes:1,users:1,server_time:1};
  }
}
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
test('CONTROL: current user detail and edit target remain coherent',async()=>{const f=fixture(),p=f.detail('CURRENT');f.respond(0,user('CURRENT'));await p;assert.equal(f.detailEmail(),'CURRENT@example.test');assert.equal(f.modalOpen(),true);assert.ok(f.ctx.adminUserDetail.innerHTML.includes("saveAdminUser('CURRENT')"));assert.equal(f.ctx.adminDetailBonus.value,'7')});
test('CONTROL: current user ID is encoded',async()=>{const f=fixture(),p=f.detail('id / +');assert.equal(f.requests[0].url,'/api/admin/users/id%20%2F%20%2B');f.respond(0,user('SAFE'));await p});
test('CONTROL: close hides a completed user modal',async()=>{const f=fixture(),p=f.detail('A');f.respond(0,user('A'));await p;f.close();assert.equal(f.modalOpen(),false)});
test('CONTROL: current detail failure remains observable',async()=>{const f=fixture(),p=f.detail('A');f.respond(0,{error:'current detail error'},503);await assert.rejects(p,/current detail error/);assert.equal(f.modalOpen(),false)});
test('CONTROL: current tab failure is shown',async()=>{const f=fixture(),p=f.select('users');f.respond(0,{error:'current tab error'},503);await p;assert.ok(f.ctx.adminContent.innerHTML.includes('current tab error'))});
test('CONTROL: current 401 opens authentication',async()=>{const f=fixture(),p=f.select('users');f.respond(0,{error:'current unauthorized'},401);await p;assert.equal(f.call('state.user'),null);assert.equal(f.ctx.auth.classList.contains('hidden'),false)});
for(const tab of tabs)test(`CONTROL: current ${tab} tab keeps URL, selection and response aligned`,async()=>{const f=fixture(),p=f.select(tab);f.respond(0,payload(tab,'CURRENT'));await p;assert.equal(f.selected(),tab);assert.ok(f.ctx.adminContent.innerHTML.includes('CURRENT'));assert.equal(f.ctx.location.pathname,tab==='dashboard'?'/admin':'/admin/'+tab)});
test('BUG: earlier selected user must not overwrite newer user and Save account target',async()=>{const f=fixture(),a=f.detail('A'),b=f.detail('B');f.respond(1,user('B'));await b;f.respond(0,user('A'));await a;assert.equal(f.detailEmail(),'B@example.test');assert.ok(f.ctx.adminUserDetail.innerHTML.includes("saveAdminUser('B')"))});
test('BUG: earlier selected user must not appear while newer user is pending',async()=>{const f=fixture(),a=f.detail('A'),b=f.detail('B');f.respond(0,user('A'));await a;const staleVisible=f.modalOpen()&&f.detailEmail()==='A@example.test';f.respond(1,user('B'));await b;assert.equal(staleVisible,false)});
for(const close of ['close','escape'])test(`BUG: pending older detail must not reopen a modal closed by ${close}`,async()=>{const f=fixture(),a=f.detail('A'),b=f.detail('B');f.respond(1,user('B'));await b;f[close]();assert.equal(f.modalOpen(),false);f.respond(0,user('A'));await a;assert.equal(f.modalOpen(),false)});
test('BUG: pending current detail refresh must not reopen a closed modal',async()=>{const f=fixture(),initial=f.detail('A');f.respond(0,user('A'));await initial;const refresh=f.detail('A');f.close();f.respond(1,user('A'));await refresh;assert.equal(f.modalOpen(),false)});
test('BUG: detail completion must not open modal after leaving admin',async()=>{const f=fixture(),a=f.detail('A');f.call("view('dashboard',null)");f.respond(0,user('A'));await a;assert.equal(f.ctx.location.pathname,'/dashboard');assert.equal(f.modalOpen(),false)});
test('BUG: detail completion must not open modal after auth reset',async()=>{const f=fixture(),a=f.detail('A');f.call('showAuth()');f.respond(0,user('A'));await a;assert.equal(f.call('state.user'),null);assert.equal(f.modalOpen(),false)});
test('BUG: stale detail 401 must not erase the newer selected admin session',async()=>{const f=fixture(),a=f.detail('A').catch(e=>e),b=f.detail('B');f.respond(1,user('B'));await b;f.respond(0,{error:'obsolete detail unauthorized'},401);await a;assert.equal(f.call('state.user?.id'),'synthetic-admin');assert.equal(f.ctx.auth.classList.contains('hidden'),true)});
for(let i=0;i<tabs.length;i++){
 const oldTab=tabs[i],latestTab=tabs[(i+1)%tabs.length];
 test(`BUG: old ${oldTab} response must not repaint selected ${latestTab}`,async()=>{const f=fixture(),a=f.select(oldTab),b=f.select(latestTab);f.respond(1,payload(latestTab,'LATEST'));await b;f.respond(0,payload(oldTab,'OBSOLETE'));await a;assert.equal(f.selected(),latestTab);assert.equal(f.ctx.location.pathname,latestTab==='dashboard'?'/admin':'/admin/'+latestTab);assert.equal(f.ctx.adminContent.innerHTML.includes('LATEST'),true)});
}
test('BUG: repeated same-tab requests must preserve latest data',async()=>{const f=fixture(),a=f.select('users'),b=f.select('users');f.respond(1,payload('users','LATEST'));await b;f.respond(0,payload('users','OBSOLETE'));await a;assert.equal(f.ctx.adminContent.innerHTML.includes('LATEST'),true)});
for(const failure of ['network','http','401'])test(`BUG: stale ${failure} tab response must not replace newer successful tab`,async()=>{const f=fixture(),a=f.select('users'),b=f.select('system');f.respond(1,payload('system','LATEST'));await b;if(failure==='network')f.requests[0].reject(new Error('obsolete network error'));else f.respond(0,{error:'obsolete error'},failure==='401'?401:503);await a;assert.equal(f.ctx.adminContent.innerHTML.includes('LATEST'),true);assert.equal(f.call('state.user?.id'),'synthetic-admin')});
test('BUG: tab JSON completion must still belong to latest tab',async()=>{const f=fixture(),a=f.select('users');let finish;f.requests[0].resolve({status:200,ok:true,json:()=>new Promise(resolve=>{finish=resolve})});await settle();const b=f.select('system');f.respond(1,payload('system','LATEST'));await b;finish(payload('users','OBSOLETE'));await a;assert.equal(f.ctx.adminContent.innerHTML.includes('LATEST'),true)});
test('BUG: old-session tab 401 must not clear a new session',async()=>{const f=fixture(),a=f.select('users');f.call("showAuth();state.user={id:'new-admin',role:'super_admin'};showApp()");const b=f.select('system');f.respond(1,payload('system','LATEST'));await b;f.respond(0,{error:'old session'},401);await a;assert.equal(f.call('state.user?.id'),'new-admin');assert.equal(f.ctx.adminContent.innerHTML.includes('LATEST'),true)});

test('BUG: Escape invalidates the first pending hidden detail request',async()=>{const f=fixture(),p=f.detail('A');assert.equal(f.modalOpen(),false);f.escape();f.respond(0,user('A'));await p;assert.equal(f.modalOpen(),false);assert.equal(f.ctx.adminUserDetail.innerHTML,'')});
test('BUG: selecting B clears displayed A controls while B loads',async()=>{const f=fixture();let p=f.detail('A');f.respond(0,user('A'));await p;const b=f.detail('B');assert.equal(f.modalOpen(),false);assert.equal(f.ctx.adminUserDetail.innerHTML,'');f.respond(1,user('B'));await b;assert.equal(f.detailEmail(),'B@example.test')});
for(const change of ["resetLoginVerification()","state.user={id:'another-admin',role:'super_admin'}"]){
 test('BUG: same-view auth ownership changes invalidate tab and detail: '+change,async()=>{const f=fixture(),tab=f.select('users'),detail=f.detail('A');f.call(change);f.respond(0,payload('users','OLD'));f.respond(1,user('A'));await Promise.all([tab,detail]);assert.equal(f.ctx.adminContent.innerHTML.includes('OLD'),false);assert.equal(f.modalOpen(),false)});
}
test('CONTROL: independent tab and detail requests do not cancel each other',async()=>{const f=fixture(),tab=f.select('users'),detail=f.detail('A');f.respond(1,user('A'));await detail;f.respond(0,payload('users','USERS'));await tab;assert.equal(f.detailEmail(),'A@example.test');assert.equal(f.ctx.adminContent.innerHTML.includes('USERS'),true)});
test('BUG: leaving then re-entering Admin invalidates old responses',async()=>{const f=fixture(),old=f.select('users');f.call("view('dashboard',null);view('admin',null)");const i=f.requests.length-1;f.respond(i,payload('dashboard','LATEST'));await settle();f.respond(0,payload('users','OLD'));await old;assert.equal(f.ctx.adminContent.innerHTML.includes('LATEST'),true);assert.equal(f.ctx.adminContent.innerHTML.includes('OLD'),false)});
test('CONTROL: Back/Forward routing keeps Admin selection and content aligned',async()=>{const f=fixture(),old=f.select('users');f.ctx.location.pathname='/admin/system';f.listeners.popstate.forEach(fn=>fn({}));f.respond(1,payload('system','LATEST'));await settle();f.respond(0,payload('users','OLD'));await old;assert.equal(f.selected(),'system');assert.equal(f.ctx.adminContent.innerHTML.includes('LATEST'),true)});
for(const kind of ['users','operations']){
 const fn=kind==='users'?'adminSearchUsers()':'adminFilterOps()',table=kind==='users'?'adminUsersTable':'adminOpsTable';
 async function begin(f){const p=f.select(kind);f.respond(f.requests.length-1,payload(kind,'INITIAL'));await p}
 function values(f,marker){if(kind==='users')f.ctx.adminUserSearch.value=marker;else{f.ctx.adminOpUser.value=marker;f.ctx.adminOpAction.value=marker+' / &'}}
 test('CHILD: '+kind+' current query values and result are preserved',async()=>{const f=fixture();await begin(f);values(f,'query & +');const p=f.call(fn);const q=new URLSearchParams(f.requests[1].url.split('?')[1]);if(kind==='users')assert.equal(q.get('q'),'query & +');else{assert.equal(q.get('user'),'query & +');assert.equal(q.get('action'),'query & + / &');assert.equal(q.get('limit'),'300')}f.respond(1,payload(kind,'LATEST'));await p;assert.ok(f.ctx[table].innerHTML.includes('LATEST'))});
 test('CHILD: '+kind+' latest query wins and obsolete rejection is silent',async()=>{const f=fixture();await begin(f);values(f,'old');const old=f.call(fn);values(f,'new');const latest=f.call(fn);f.respond(2,payload(kind,'LATEST'));await latest;f.requests[1].reject(new Error('obsolete'));await old;assert.ok(f.ctx[table].innerHTML.includes('LATEST'))});
 test('CHILD: '+kind+' older success cannot replace a newer result',async()=>{const f=fixture();await begin(f);const old=f.call(fn),latest=f.call(fn);f.respond(2,payload(kind,'LATEST'));await latest;f.respond(1,payload(kind,'OLD'));await old;assert.ok(f.ctx[table].innerHTML.includes('LATEST'))});
 for(const status of [200,401])test('CHILD: '+kind+' cannot affect a replacement tab after status '+status,async()=>{const f=fixture();await begin(f);const old=f.call(fn),next=f.select('system');f.respond(2,payload('system','SYSTEM'));await next;const again=f.select(kind);f.respond(3,payload(kind,'NEW_TABLE'));await again;const tableBefore=f.ctx[table].innerHTML;f.respond(1,payload(kind,'OLD'),status);await old;assert.equal(f.ctx[table].innerHTML,tableBefore);assert.equal(f.call('state.user?.id'),'synthetic-admin')});
 test('CHILD: '+kind+' current server failure remains observable',async()=>{const f=fixture();await begin(f);const p=f.call(fn);f.respond(1,{error:'current child error'},503);await assert.rejects(p,/current child error/)});
 test('CHILD: '+kind+' current 401 still opens authentication',async()=>{const f=fixture();await begin(f);const p=f.call(fn);f.respond(1,{error:'current child unauthorized'},401);await p;assert.equal(f.call('state.user'),null)});
}
async function openUser(f,id='A'){const p=f.detail(id);f.respond(f.requests.length-1,user(id));await p}
const expectedSave={status:'active',plan:'free',bonus_requests:11,bonus_nodes:2,bonus_ai_accounts:3,override_expires_at:null};
function save(f,id='A'){
 for(const [name,value] of Object.entries({adminDetailStatus:'active',adminDetailPlan:'free',adminDetailBonus:'11',adminDetailBonusNodes:'2',adminDetailBonusAi:'3',adminDetailExpiry:'never'}))f.ctx[name].value=value;
 return f.call(`saveAdminUser(${JSON.stringify(id)})`);
}
function assertPut(f,index=1,id='A'){
 const r=f.requests[index];assert.equal(r.url,'/api/admin/users/'+encodeURIComponent(id));assert.equal(r.options.method,'PUT');assert.deepEqual(JSON.parse(r.options.body),expectedSave);assert.equal(r.options.signal,undefined);assert.equal(f.requests.filter(r=>r.options.method==='PUT').length,1);
}
test('SAVE: current completion preserves one PUT and current detail refresh',async()=>{const f=fixture({allowSave:true});await openUser(f,'id / +');const p=save(f,'id / +');assertPut(f,1,'id / +');f.respond(1,{ok:true});await settle();assert.equal(f.requests.length,3);assert.equal(f.requests[2].url,'/api/admin/users/id%20%2F%20%2B');f.respond(2,user('id / +'));await p;assert.equal(f.effects.length,1);assert.equal(f.modalOpen(),true);assert.equal(f.detailEmail(),'id / +@example.test')});
for(const close of ['close','escape'])test('SAVE: '+close+' suppresses UI refresh without cancelling dispatched PUT',async()=>{const f=fixture({allowSave:true});await openUser(f);const p=save(f);assertPut(f);f[close]();f.respond(1,{ok:true});await p;assert.equal(f.effects.length,1);assert.deepEqual(f.effects[0].body,expectedSave);assert.equal(f.requests.length,2);assert.equal(f.modalOpen(),false);assert.equal(f.elements.get('toast').textContent,'')});
for(const id of ['A','B'])test('SAVE: selecting '+id+' again invalidates the older save continuation',async()=>{const f=fixture({allowSave:true});await openUser(f);const p=save(f);assertPut(f);await openUser(f,id);const current=f.ctx.adminUserDetail.innerHTML;f.respond(1,{ok:true});await p;assert.equal(f.requests.length,3);assert.equal(f.effects.length,1);assert.equal(f.ctx.adminUserDetail.innerHTML,current);assert.equal(f.elements.get('toast').textContent,'')});
for(const status of [200,401,503])test('SAVE: obsolete status '+status+' cannot affect a replacement session',async()=>{const f=fixture({allowSave:true});await openUser(f);const p=save(f);assertPut(f);f.call("showAuth();state.user={id:'new-admin',role:'super_admin'};showApp();admin.classList.remove('hidden')");await openUser(f,'B');f.respond(1,{error:'old save',ok:status===200},status);await p;assert.equal(f.requests.length,3);assert.equal(f.call('state.user?.id'),'new-admin');assert.equal(f.detailEmail(),'B@example.test');assert.equal(f.effects.length,status===200?1:0);assert.equal(f.elements.get('toast').textContent,'')});
test('SAVE: current 401 still opens authentication after one unchanged PUT',async()=>{const f=fixture({allowSave:true});await openUser(f);const p=save(f);assertPut(f);f.respond(1,{error:'current unauthorized'},401);await p;assert.equal(f.call('state.user'),null);assert.equal(f.requests.length,2);assert.equal(f.effects.length,0)});
test('SAVE: current server error remains visible with no automatic retry',async()=>{const f=fixture({allowSave:true});await openUser(f);const p=save(f);assertPut(f);f.respond(1,{error:'current save error'},503);await p;assert.equal(f.elements.get('toast').textContent,'current save error');assert.equal(f.requests.length,2);assert.equal(f.effects.length,0);assert.equal(f.modalOpen(),true)});
test('SAVE: close during the post-save GET prevents reopening',async()=>{const f=fixture({allowSave:true});await openUser(f);const p=save(f);f.respond(1,{ok:true});await settle();assert.equal(f.requests.length,3);f.close();f.respond(2,user('A'));await p;assert.equal(f.effects.length,1);assert.equal(f.modalOpen(),false)});

for(const failure of ['network','http'])test('SAVE: current post-save '+failure+' read failure remains visible',async()=>{const f=fixture({allowSave:true});await openUser(f);const p=save(f);assertPut(f);f.respond(1,{ok:true});await settle();assert.equal(f.requests.length,3);if(failure==='network')f.requests[2].reject(new Error('current refresh error'));else f.respond(2,{error:'current refresh error'},503);await p;assert.equal(f.elements.get('toast').textContent,'current refresh error');assert.equal(f.effects.length,1);assert.equal(f.requests.length,3)});
test('SAVE: latest refresh read wins without replacing selection ownership',async()=>{const f=fixture();await openUser(f);f.call("globalThis.ownerBeforeRefresh=adminUserViewOwner('A')");const old=f.call("refreshAdminUser('A',ownerBeforeRefresh)"),latest=f.call("refreshAdminUser('A',ownerBeforeRefresh)");f.respond(2,user('LATEST'));await latest;f.respond(1,user('OLD'));await old;assert.equal(f.call('ownerBeforeRefresh()'),true);assert.equal(f.detailEmail(),'LATEST@example.test')});
for (const status of [200,401]) test('EDGE: detail delayed JSON '+status+' rechecks ownership', async()=>{
 const f=fixture(),a=f.detail('A');let finish;
 f.requests[0].resolve({status,ok:status===200,json:()=>new Promise(resolve=>{finish=resolve})});await settle();
 const b=f.detail('B');f.respond(1,user('B'));await b;finish(user('A'));await a;
 assert.equal(f.detailEmail(),'B@example.test');assert.equal(f.call('state.user.id'),'synthetic-admin');
});
for (const kind of ['users','operations']) for (const status of [200,401]) test('EDGE: '+kind+' child delayed JSON '+status+' rechecks parent',async()=>{
 const f=fixture(),initial=f.select(kind);f.respond(0,payload(kind,'INITIAL'));await initial;
 const old=f.call(kind==='users'?'adminSearchUsers()':'adminFilterOps()');let finish;
 f.requests[1].resolve({status,ok:status===200,json:()=>new Promise(resolve=>{finish=resolve})});await settle();
 const replacement=f.select(kind);f.respond(2,payload(kind,'REPLACEMENT'));await replacement;
 const table=kind==='users'?'adminUsersTable':'adminOpsTable',html=f.ctx[table].innerHTML;
 finish(payload(kind,'OLD'));await old;assert.equal(f.ctx[table].innerHTML,html);assert.equal(f.call('state.user.id'),'synthetic-admin');
});
for (const transition of ["state.user=null", "admin.classList.add('hidden')"]) test('EDGE: inactive admin does not dispatch reads '+transition,async()=>{
 const f=fixture();f.call(transition);await f.select('users');await f.detail('A');await f.call('adminSearchUsers()');await f.call('adminFilterOps()');assert.equal(f.requests.length,0);
});
test('EDGE: leaving Admin suppresses save UI while preserving completed PUT',async()=>{
 const f=fixture({allowSave:true});await openUser(f);const p=save(f);assertPut(f);
 f.call("view('dashboard',null)");f.respond(1,{ok:true});await p;
 assert.equal(f.effects.length,1);assert.equal(f.requests.length,2);assert.equal(f.modalOpen(),false);assert.equal(f.elements.get('toast').textContent,'');
});
for (const status of [401,503]) test('EDGE: post-save GET '+status+' after Close cannot alter auth or toast',async()=>{
 const f=fixture({allowSave:true});await openUser(f);const p=save(f);f.respond(1,{ok:true});await settle();f.close();
 const before=f.elements.get('toast').textContent;f.respond(2,{error:'late refresh'},status);await p;
 assert.equal(f.effects.length,1);assert.equal(f.requests.length,3);assert.equal(f.modalOpen(),false);assert.equal(f.elements.get('toast').textContent,before);assert.equal(f.call('state.user.id'),'synthetic-admin');
});
test('EDGE: current detail 401 opens auth',async()=>{const f=fixture(),p=f.detail('A');f.respond(0,{error:'unauthorized'},401);await p;assert.equal(f.call('state.user'),null);assert.equal(f.modalOpen(),false)});

'''
