"""Composed Billing reads with controlled, account-independent HTTP responses.

The shared dashboard fixture supplies only DOM/transport. All state, rendering,
request ownership and authentication effects execute the production page code.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from gpt_windows_connector import server
from test_dashboard_response_ownership import DASHBOARD_CASES, DashboardIds


def test_billing_response_ownership(tmp_path):
    html = server.webapp._dashboard_html()
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    runtime = next(s for s in scripts if "const state=" in s)
    assert runtime.endswith("\nboot();\n")
    runtime = next(s for s in scripts if "const WEB_LANG=" in s) + "\n" + runtime[:-len("boot();\n")]
    markup = DashboardIds()
    markup.feed(html)
    # Reuse the established actual-page fixture, without executing its cases.
    fixture = DASHBOARD_CASES.split("for(const language of ['en','zh-CN']){")[0]
    allowed = "['/api/nodes','/api/logs?limit=20','/api/ai-connections','/auth/me','/api/logout']"
    assert fixture.count(allowed) == 1
    fixture = fixture.replace(allowed, allowed[:-1] + ",'/api/billing/summary']")
    script = tmp_path / "billing-response-ownership.mjs"
    script.write_text("const runtime=" + json.dumps(runtime) + ";\nconst markup=" +
                      json.dumps(markup.elements) + ";\n" + fixture + BILLING_CASES,
                      encoding="utf-8")
    node = shutil.which("node")
    assert node, "Node.js is required for Billing read regressions"
    result = subprocess.run([node, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fail 0" in result.stdout


BILLING_CASES = r'''
const billingTest=(name,body)=>test(name,{timeout:1500},body);
function summary(mark,extra={}){return {beta_free:true,existing_paid_subscription:mark==='OLD',
 plan:'free',plan_name:'Lucas Beta',billing_configured:false,requests_used:mark==='OLD'?7:99,
 requests_pending:2,requests_unconfirmed:1,request_limit:100000,request_remaining:99898,
 nodes_used:2,nodes_connected:4,node_limit:3,ai_accounts_used:1,ai_account_limit:3,...extra}}
function dashboardReply(f,start,mark){const rows=data(mark);rows[0].billing=summary(mark);rows.forEach((d,i)=>f.respond(start+i,d))}
function assertSnapshot(f,mark){
 const count=mark==='OLD'?7:99;
 assert.equal(f.call('state.billing.requests_used'),count);
 for(const id of ['billingRequests','metricRequests'])assert.match(f.elements.get(id).innerHTML,new RegExp('data-operation-count="completed">'+count+'<'),id);
 assert.equal(f.elements.get('billingPrice').textContent,'$0');
 assert.equal(f.elements.get('billingPlan').textContent,'Lucas Beta');
 assert.equal(f.elements.get('billingAi').textContent,'1 / 3');
 assert.equal(f.elements.get('billingNotice').textContent.includes('existing paid subscription'),mark==='OLD');
}
async function bill(f,mark){const i=f.requests.length,p=f.call('loadBillingView()');f.respond(i,summary(mark));await p;assertSnapshot(f,mark)}
function signedInB(f){f.call("showAuth();state.user={id:'user-b',email:'b@example.test',role:'user'};showApp()")}
function assertCleared(f){
 assert.equal(f.call('state.billing'),null);
 for(const id of ['billingNotice','billingError','billingRenew'])assert.equal(f.elements.get(id).textContent,'',id);
 for(const id of ['billingPlan','billingPrice','billingAi','billingComputers'])assert.equal(f.elements.get(id).textContent,'—',id);
 assert.ok(f.elements.get('billingNotice').classList.contains('hidden'));
 assert.ok(f.elements.get('billingError').classList.contains('hidden'));
}
for(const language of ['en','zh-CN']){
 billingTest(language+': current Billing request and price retain their established contract',async()=>{
  const f=fixture(language),pending=f.call('loadBillingView()');assert.equal(f.requests.length,1);assert.equal(f.requests[0].url,'/api/billing/summary');assert.equal(f.requests[0].options.credentials,'include');assert.equal(f.requests[0].options.method,undefined);assert.equal(f.requests[0].options.body,undefined);f.respond(0,summary('NEW'));await pending;assert.equal(f.elements.get('billingPrice').textContent,'$0');assert.equal(f.call('state.billing.ai_account_limit'),3);
 });
 billingTest(language+': existing Beta upgrade callback retains its no-purchase guard',async()=>{
  const f=fixture(language);f.call('state.billing='+JSON.stringify(summary('NEW')));await f.call("billingChangePlan('pro')");assert.equal(f.requests.length,0);assert.equal(f.elements.get('billingNotice').textContent,'Lucas Beta is free during testing. Paid upgrades are unavailable.');
 });
 billingTest(language+': current Beta snapshot keeps both views and shared quota consistent',async()=>{
  const f=fixture(language);await bill(f,'NEW');assert.equal(f.requests[0].url,'/api/billing/summary');assert.equal(f.requests[0].options.method,undefined);
  assert.equal(f.elements.get('billingComputers').textContent,'2 / 3 active · 4 connected');
 });
 billingTest(language+': older billing success cannot overwrite a newer success',async()=>{
  const f=fixture(language),old=f.call('loadBillingView()'),fresh=f.call('loadBillingView()');f.respond(1,summary('NEW'));await fresh;f.respond(0,summary('OLD'));await old;assertSnapshot(f,'NEW');
 });
 billingTest(language+': older success is suppressed while the newer request is pending',async()=>{
  const f=fixture(language),old=f.call('loadBillingView()'),fresh=f.call('loadBillingView()');f.respond(0,summary('OLD'));await old;assert.equal(f.call('state.billing'),null);f.respond(1,summary('NEW'));await fresh;assertSnapshot(f,'NEW');
 });
 for(const failure of ['network',503,401])billingTest(language+': stale '+failure+' cannot replace current feedback or auth',async()=>{
  const f=fixture(language),old=f.call('loadBillingView()');await bill(f,'NEW');
  if(failure==='network')f.requests[0].reject(new Error('OLD_FAILURE'));else f.respond(0,{error:'OLD_FAILURE'},failure);
  await old;assertSnapshot(f,'NEW');assert.equal(f.call('state.user.id'),'user-a');assert.equal(f.elements.get('billingError').textContent,'');
 });
 for(const failure of ['network',503])billingTest(language+': current '+failure+' remains visible and explicit retry succeeds',async()=>{
  const f=fixture(language),p=f.call('loadBillingView()');if(failure==='network')f.requests[0].reject(new Error('CURRENT_FAILURE'));else f.respond(0,{error:'CURRENT_FAILURE'},failure);await p;
  assert.equal(f.elements.get('billingError').textContent,'CURRENT_FAILURE');assert.equal(f.elements.get('billingError').classList.contains('hidden'),false);
  await bill(f,'NEW');assert.equal(f.elements.get('billingError').textContent,'');
 });
 billingTest(language+': current 401 opens authentication and clears account-specific billing',async()=>{
  const f=fixture(language);await bill(f,'OLD');const p=f.call('loadBillingView()');f.respond(1,{error:'expired'},401);await p;assert.equal(f.call('state.user'),null);assertCleared(f);assert.equal(f.ctx.auth.classList.contains('hidden'),false);
 });
 for(const outcome of [200,401,503,'network'])billingTest(language+': old account '+outcome+' cannot affect the new account',async()=>{
  const f=fixture(language),old=f.call('loadBillingView()');signedInB(f);await bill(f,'NEW');
  if(outcome==='network')f.requests[0].reject(new Error('OLD_FAILURE'));else f.respond(0,outcome===200?summary('OLD',{ai_account_limit:5}):{error:'OLD_FAILURE'},outcome);
  await old;assertSnapshot(f,'NEW');assert.equal(f.call('state.user.id'),'user-b');assert.equal(f.ctx.auth.classList.contains('hidden'),true);
 });
 for(const outcome of [200,401])billingTest(language+': delayed JSON '+outcome+' rechecks the shared read owner',async()=>{
  const f=fixture(language),old=f.call('loadBillingView()');let finish;
  f.requests[0].resolve({status:outcome,ok:outcome===200,json:()=>new Promise(resolve=>{finish=resolve})});await settle();await bill(f,'NEW');finish(outcome===200?summary('OLD'):{error:'OLD_401'});await old;assertSnapshot(f,'NEW');assert.equal(f.call('state.user.id'),'user-a');
 });
 for(const transition of ['showAuth()','resetLoginVerification()',"state.user={id:'user-b',email:'b@example.test'}",'state.user=null'])billingTest(language+': session transition invalidates pending success '+transition,async()=>{
  const f=fixture(language),old=f.call('loadBillingView()');f.call(transition);f.respond(0,summary('OLD'));await old;assert.equal(f.call('state.billing'),null);assert.equal(f.elements.get('billingNotice').textContent,'');
 });
 billingTest(language+': guest dispatches no billing request',async()=>{const f=fixture(language);f.call('showAuth()');const pending=f.call('loadBillingView()');assert.equal(f.requests.length,0);await pending});
 billingTest(language+': account reset clears only account-owned displays and preserves drafts',async()=>{
  const f=fixture(language);await bill(f,'OLD');const ids=['aiManageName','aiManageNote','connectNodeId','connectCode','taskRunDays','logAction','logTarget'];ids.forEach(id=>f.elements.get(id).value='DRAFT');f.stored.set('unrelated','keep');f.call("state.unrelatedDraft='keep';showAuth()");assertCleared(f);
  ids.forEach(id=>assert.equal(f.elements.get(id).value,'DRAFT'));assert.equal(f.stored.get('unrelated'),'keep');assert.equal(f.call('state.unrelatedDraft'),'keep');
 });
 billingTest(language+': new account boot clears the old view before pending reads settle',async()=>{
  const f=fixture(language);await bill(f,'OLD');const boot=f.call('boot()');f.respond(1,{user:{id:'user-b',email:'b@example.test',role:'user'}});await settle();assertCleared(f);dashboardReply(f,2,'NEW');await boot;assertSnapshot(f,'NEW');
 });
 billingTest(language+': newer Billing snapshot wins over older dashboard quota but not its unrelated rows',async()=>{
  const f=fixture(language),old=f.call('refresh()');await bill(f,'NEW');dashboardReply(f,0,'OLD');await old;assertSnapshot(f,'NEW');assert.equal(f.call('state.nodes[0].node_id'),'OLD');
 });
 billingTest(language+': newer dashboard snapshot wins over older Billing response',async()=>{
  const f=fixture(language),old=f.call('loadBillingView()'),fresh=f.call('refresh()');dashboardReply(f,1,'NEW');await fresh;f.respond(0,summary('OLD'));await old;assertSnapshot(f,'NEW');
 });
 billingTest(language+': older Billing 401 cannot invalidate a newer dashboard read',async()=>{
  const f=fixture(language),old=f.call('loadBillingView()'),fresh=f.call('refresh()');dashboardReply(f,1,'NEW');await fresh;f.respond(0,{error:'OLD_401'},401);await old;assertSnapshot(f,'NEW');assert.equal(f.call('state.user.id'),'user-a');
 });
 billingTest(language+': pending newer Billing read already suppresses older dashboard quota',async()=>{
  const f=fixture(language),old=f.call('refresh()'),fresh=f.call('loadBillingView()');dashboardReply(f,0,'OLD');await old;assert.equal(f.call('state.billing'),null);f.respond(3,summary('NEW'));await fresh;assertSnapshot(f,'NEW');
 });
 billingTest(language+': failed newer Billing read does not fall back to an older dashboard snapshot',async()=>{
  const f=fixture(language);await bill(f,'NEW');const old=f.call('refresh()'),fresh=f.call('loadBillingView()');f.respond(4,{error:'CURRENT_FAILURE'},503);await fresh;dashboardReply(f,1,'OLD');await old;assertSnapshot(f,'NEW');assert.equal(f.elements.get('billingError').textContent,'CURRENT_FAILURE');
 });
 billingTest(language+': failed newer dashboard read does not permit older Billing to commit',async()=>{
  const f=fixture(language);await bill(f,'NEW');const old=f.call('loadBillingView()'),fresh=f.call('refresh()'),failed=assert.rejects(fresh,/CURRENT_FAILURE/);
  f.respond(2,{error:'CURRENT_FAILURE'},503);f.respond(3,{logs:[]});f.respond(4,{clients:[]});await failed;f.respond(1,summary('OLD'));await old;assertSnapshot(f,'NEW');
 });
 billingTest(language+': invalidated dashboard caller cannot overwrite a later Billing snapshot',async()=>{
  const f=fixture(language);f.call('globalThis.active=true');const old=f.call('refresh(()=>active)');f.call('active=false');await bill(f,'NEW');dashboardReply(f,0,'OLD');await old;assertSnapshot(f,'NEW');assert.equal(f.call('state.nodes.length'),0);
 });
 billingTest(language+': legacy rendering and a subsequent Beta snapshot clear obsolete renewal and warning',async()=>{
  const f=fixture(language),p=f.call('loadBillingView()');f.respond(0,summary('OLD',{beta_free:false,plan:'pro_plus',plan_name:'Pro+',billing_configured:true,expansion_quantity:2,billing_interval:'year',billing_total:499.97,renewal_at:1792065600}));await p;
  assert.equal(f.elements.get('billingPrice').textContent,'$499.97/yr');assert.equal(f.elements.get('billingPlan').textContent,'Pro+ + 2 Packs');assert.ok(f.elements.get('billingRenew').textContent.startsWith('Renews '));assert.equal(f.elements.get('billingNotice').textContent,'');
  await bill(f,'NEW');assert.equal(f.elements.get('billingRenew').textContent,'');
 });
}
'''
