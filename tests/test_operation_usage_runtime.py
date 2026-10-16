"""Execute the composed usage UI and exercise its owner/admin API projections.

The lightweight DOM is a deterministic JavaScript runtime harness, not browser
layout evidence. Separate Chromium tests cover the real page and responsive UI.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    for name in ("HOME", "LOCALAPPDATA", "GWC_DATA_DIR"):
        path = tmp_path / name.lower()
        path.mkdir()
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")


def run_usage_js(body: str, language: str = "en"):
    from gpt_windows_connector import server

    html = server.webapp._dashboard_html()
    node = shutil.which("node")
    assert node, "Node.js is required for rendered operation usage tests"

    def between(start, end):
        return html[html.index(start):html.index(end, html.index(start))]

    # All runtime and markup come from the actual composed production response.
    runtime = "\n".join((
        between("const WEB_LANG=", "</script>"),
        between("function operationNumber(", "const state="),
        between("const state=", "async function billingChangePlan("),
        between("function esc(", "async function boot("),
        between("let dashboardRefreshSequence=", "function updateNodeMetrics("),
        between("const historyRequestSequences=", "function renderRecent("),
        between("function adminMetric(", "if(WEB_LANG==='zh'){localizeWeb();"),
    ))
    markup = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.S)
    harness = r'''
const assert=require('node:assert/strict'),window=globalThis;
const navigator={language:LANGUAGE},responses=new Map(),requests=[];
function descendants(root){return root.children.flatMap(n=>[n,...(n.children?descendants(n):[])])}
function decode(s){return String(s).replace(/&(amp|lt|gt|quot|#39);/g,(_,x)=>({amp:'&',lt:'<',gt:'>',quot:'"','#39':"'"}[x]))}
function matches(el,selector){
  if(el.nodeType!==1)return false;
  const tag=selector.match(/^[\w-]+/),id=selector.match(/#([\w-]+)/),cls=selector.match(/\.([\w-]+)/);
  if(tag&&el.tagName!==tag[0]||id&&el.id!==id[1]||cls&&!el.classList.contains(cls[1]))return false;
  for(const [,key,value] of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)){
    if(el.getAttribute(key)===null||value!==undefined&&el.getAttribute(key)!==value)return false;
  }
  return true;
}
class Element{
  constructor(tag){this.tagName=tag;this.nodeType=1;this.children=[];this.attrs={};this.style={};this.value='';
    this.classList={contains:c=>(this.attrs.class||'').split(/\s+/).includes(c),
      add:(...cs)=>{this.attrs.class=[...new Set([...(this.attrs.class||'').split(/\s+/).filter(Boolean),...cs])].join(' ')},
      remove:(...cs)=>{this.attrs.class=(this.attrs.class||'').split(/\s+/).filter(c=>!cs.includes(c)).join(' ')},
      toggle:(c,on)=>{on=on===undefined?!this.classList.contains(c):on;on?this.classList.add(c):this.classList.remove(c);return on}};
  }
  get id(){return this.attrs.id||''}set id(v){this.setAttribute('id',v)}
  setAttribute(k,v){this.attrs[k]=String(v);if(k==='id'&&!(v in globalThis))globalThis[v]=this;if(k==='value')this.value=String(v)}
  getAttribute(k){return this.attrs[k]??null}
  appendChild(n){n.parentNode=this;this.children.push(n);return n}
  insertBefore(n,before){n.parentNode=this;this.children.splice(this.children.indexOf(before),0,n);return n}
  set textContent(v){this.children=[{nodeType:3,nodeValue:String(v),get textContent(){return this.nodeValue}}]}
  get textContent(){return this.children.map(n=>n.textContent).join('')}
  set innerHTML(v){this.children=[];this.rawHtml=v;parseInto(this,v)}get innerHTML(){return this.rawHtml||''}
  querySelectorAll(s){return descendants(this).filter(n=>s.split(',').some(x=>matches(n,x.trim())))}
  querySelector(s){return this.querySelectorAll(s)[0]||null}
}
function parseInto(root,html){
  const stack=[root],voids=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  for(const token of html.match(/<!--[\s\S]*?-->|<[^>]+>|[^<]+/g)||[]){
    if(token.startsWith('<!'))continue;
    if(token.startsWith('</')){if(stack.length>1)stack.pop();continue}
    if(token.startsWith('<')){
      const match=token.match(/^<([\w-]+)/);if(!match)continue;
      const el=new Element(match[1].toLowerCase());
      for(const [,key,dq,sq,bare]of token.slice(match[0].length,-1).matchAll(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))el.setAttribute(key,decode(dq??sq??bare??''));
      stack.at(-1).appendChild(el);if(!voids.has(el.tagName)&&!token.endsWith('/>'))stack.push(el);
    }else stack.at(-1).appendChild({nodeType:3,nodeValue:decode(token),get textContent(){return this.nodeValue}});
  }
}
const document={documentElement:new Element('html'),body:new Element('body'),
  createElement:tag=>new Element(tag),getElementById:id=>document.body.querySelector('#'+id),
  createTreeWalker(root){const nodes=descendants(root).filter(n=>n.nodeType===3);let i=0;return {nextNode(){this.currentNode=nodes[i++];return !!this.currentNode}}}};
const NodeFilter={SHOW_TEXT:4};
async function api(url,opt={}){requests.push({url,opt});assert.equal(opt.method,undefined,'Rendering must be read-only');assert.ok(responses.has(url),'Unexpected API request '+url);return responses.get(url)}
function renderNodes(){}function renderRecent(){}function renderAiClients(){}function updateNodeMetrics(){}
function counter(root,key){return root.querySelector('[data-operation-count="'+key+'"]').textContent}
let loginGeneration=0;
const snapshot={plan:'free',plan_name:'Lucas Beta',beta_free:true,request_limit:100000,requests_used:10,
  requests_pending:5,requests_unconfirmed:11,request_remaining:99974,period_end:1793491200,
  node_limit:3,nodes_used:1,ai_account_limit:3,ai_accounts_used:1};
const pending={id:'pending',action:'shell.run',node_id:'synthetic-node',target:'synthetic-workspace',status:'pending',reserved_operations:5,started_at:1792051200,deadline_at:1792054800,period_end:1793491200,currently_held:true};
const unknown={...pending,id:'unknown',status:'outcome_unconfirmed',reserved_operations:11};
const historical={...unknown,id:'historical',reserved_operations:71,period_end:1790812800,currently_held:false};
document.body.innerHTML=MARKUP;
'''.replace("LANGUAGE", json.dumps(language)).replace("MARKUP", json.dumps(markup))
    script = harness + "\n" + runtime + "\n(async()=>{\nstate.user={id:123};document.getElementById('admin').classList.remove('hidden');\n" + body + r'''
console.log('operation-usage-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run([node, "-"], input=script, capture_output=True,
                            text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    assert "operation-usage-complete" in result.stdout


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_dashboard_billing_render_separate_counts_and_preserve_beta_notice(language):
    run_usage_js(r'''
responses.set('/api/nodes',{nodes:[],billing:snapshot});responses.set('/api/logs?limit=20',{logs:[]});responses.set('/api/ai-connections',{clients:[]});
await refresh();
responses.set('/api/billing/summary',{...snapshot,existing_paid_subscription:true});await loadBillingView();
for(const root of [metricRequests,billingRequests]){
  assert.equal(counter(root,'completed'),'10');assert.equal(counter(root,'pending'),'5');assert.equal(counter(root,'unconfirmed'),'11');
  assert.equal(counter(root,'remaining'),'99,974');assert.equal(counter(root,'limit'),'100,000');
  assert.ok(root.textContent.includes(wt('Completed Operations')));assert.ok(root.textContent.includes(wt('Unconfirmed held units')));
  assert.ok(root.textContent.includes(wt('There is no automatic retry or quota refund.')));
  assert.ok(root.querySelector('[data-operation-reset]').textContent.includes(wt('Period reset')));
}
assert.equal(billingPrice.textContent,'$0');
const notice=document.getElementById('billingNotice');assert.ok(notice.textContent.includes('existing paid subscription'));assert.equal(notice.classList.contains('hidden'),false);
assert.equal(billingError.classList.contains('hidden'),true);
assert.equal(billingRequestsBar.querySelector('i').style.width,'0%');
// Progress uses the authoritative server remainder, not a parallel accounting formula.
renderOperationUsage('billingRequests',{...snapshot,request_remaining:40000},'billingRequestsBar');
assert.equal(counter(billingRequests,'remaining'),'40,000');assert.equal(billingRequestsBar.querySelector('i').style.width,'60%');
''', language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_missing_additive_fields_and_zero_usage_stay_compatible(language):
    run_usage_js(r'''
const legacy={...snapshot,requests_used:0,request_remaining:100000};delete legacy.requests_pending;delete legacy.requests_unconfirmed;
renderOperationUsage('metricRequests',legacy);
for(const key of ['completed','pending','unconfirmed'])assert.equal(counter(metricRequests,key),'0');
assert.equal(counter(metricRequests,'remaining'),'100,000');
renderOperationUsage('metricRequests',null);
assert.equal(counter(metricRequests,'completed'),'—');assert.equal(counter(metricRequests,'pending'),'0');assert.equal(counter(metricRequests,'unconfirmed'),'0');assert.equal(counter(metricRequests,'remaining'),'—');
responses.set('/api/task-runs?limit=500&days=all',{runs:[],summary:{}});await loadTaskRuns();
assert.equal(taskRunUnresolved.querySelectorAll('[data-operation-id]').length,0);
assert.ok(taskRunUnresolved.textContent.includes(wt('No unresolved actions in this view.')));
assert.ok(taskRunTable.textContent.includes('No Task Runs recorded yet.'));
''', language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_task_reservations_are_distinct_historical_and_escaped(language):
    run_usage_js(r'''
const evil='<img src=x onerror="globalThis.pwned=1">';
const malicious={...unknown,id:'"><svg onload=alert(1)>',action:evil,node_id:evil,target:evil,details:{command:'private-command',stdout:'private-output',source:'oauth',agent:evil,session_id:evil,task_title:evil}};
const runs=[{title:'Completed batch',node_id:'synthetic-node',status:'completed',duration_ms:1200,started_at:1792051200,
  steps:[{action:'shell.run',status:'success',duration_ms:1200,operation_count:10,details:{sub_operations:['shell.run','shell.run']}}]}];
responses.set('/api/task-runs?limit=500&days=7',{runs,summary:{task_runs:1,operations:10,duration_ms:1200},unresolved_operations:[pending,unknown,historical,malicious]});
taskRunDays.value='7';await loadTaskRuns();
assert.equal(taskRunSummary.querySelectorAll('.metric')[1].textContent,'10');
assert.equal(taskRunUnresolved.querySelector('[data-unresolved-count]').textContent,'4');
assert.equal(taskRunUnresolved.querySelectorAll('[data-operation-status="outcome_unconfirmed"]').length,3);
assert.equal(taskRunUnresolved.querySelectorAll('[data-currently-held="false"]').length,1);
assert.ok(taskRunUnresolved.textContent.includes(wt('Historical · not currently held')));
assert.ok(taskRunUnresolved.textContent.includes(wt('Pending')));assert.ok(taskRunUnresolved.textContent.includes(wt('Outcome unconfirmed')));
assert.ok(taskRunUnresolved.textContent.includes(wt('Confirmation deadline')));
assert.equal(taskRunUnresolved.querySelectorAll('img,svg,script,button,input,a').length,0);
assert.ok(!taskRunUnresolved.textContent.includes('private-command'));assert.ok(!taskRunUnresolved.textContent.includes('private-output'));
assert.ok(taskRunUnresolved.innerHTML.includes('&lt;img'));assert.equal(globalThis.pwned,undefined);
for(const label of ['Source','AI client','Session','Task title'])assert.ok(taskRunUnresolved.textContent.includes(wt(label)));
assert.equal(taskRunTable.querySelectorAll('.task-run-card').length,1);assert.ok(taskRunTable.textContent.includes('10 operations'));
assert.ok(taskRunTable.textContent.includes('2 parsed operations'));assert.ok(!taskRunTable.textContent.includes('71'));
setAllTaskRuns(true);assert.equal(taskRunTable.querySelector('.task-run-card').getAttribute('aria-expanded'),'true');
await loadTaskRuns();assert.equal(document.body.querySelectorAll('#taskRunUnresolved').length,1);
''', language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_admin_uses_shared_renderers_and_preserves_reviewed_bonus_controls(language):
    run_usage_js(r'''
responses.set('/api/admin/users/synthetic-user',{
  user:{id:'synthetic-user',email:'synthetic@example.test',role:'user',status:'active'},
  entitlements:snapshot,subscription:{plan:'free'},admin_overrides:{bonus_requests:9},nodes:[],usage:{last30:10},
  operations:[{action:'browser.inspect',status:'success',created_at:1792051200,target:'synthetic-workspace'}],
  unresolved_operations:[pending,unknown,historical]});
await showAdminUser('synthetic-user');
assert.equal(adminUserModal.classList.contains('hidden'),false);
assert.equal(counter(adminUserDetail,'completed'),'10');assert.equal(counter(adminUserDetail,'pending'),'5');
assert.equal(counter(adminUserDetail,'unconfirmed'),'11');assert.equal(counter(adminUserDetail,'remaining'),'99,974');
assert.equal(adminDetailBonus.value,'9');assert.equal(adminUserDetail.querySelectorAll('[data-operation-id]').length,3);
const review='After review, an administrator can grant replacement capacity with the existing Extra Operations control. This does not resolve the execution outcome.';
assert.ok(adminUserDetail.textContent.includes(wt(review)));
assert.ok(adminUserDetail.textContent.includes('browser.inspect'));
const unresolved=adminUserDetail.querySelector('[data-unresolved-operations]');
assert.equal(unresolved.querySelectorAll('button,input,a').length,0);
assert.ok(adminUserDetail.querySelectorAll('button').some(b=>b.textContent==='Save account'));
''', language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_accounting_unknown_does_not_discard_confirmed_execution_signal(language):
    run_usage_js(r'''
renderTaskUnresolvedOperations(['success','failed'].map(confirmed_outcome=>({...unknown,id:confirmed_outcome,details:{reason:'accounting_failed',confirmed_outcome,error_type:'AccountingError'}})));
assert.ok(taskRunUnresolved.textContent.includes(wt('Accounting unconfirmed')));
assert.ok(taskRunUnresolved.textContent.includes(wt('Confirmed execution outcome')));
for(const outcome of ['Success','Failure'])assert.ok(taskRunUnresolved.textContent.includes(wt(outcome)));
assert.ok(taskRunUnresolved.querySelector('[data-operation-review="accounting"]').textContent.includes(wt('Execution result received; accounting needs review.')));
assert.equal(taskRunUnresolved.querySelector('[data-operation-status="outcome_unconfirmed"]').getAttribute('data-currently-held'),'true');
assert.equal(taskRunUnresolved.querySelectorAll('button,input,a').length,0);
''', language)


@pytest.fixture
def usage_api(tmp_path, monkeypatch):
    import time
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from gpt_windows_connector import admin, gateway, webapp
    from gpt_windows_connector.auth import AuthStore
    from gpt_windows_connector.gateway_stores import NodeAuthStore, UserNodeBindingStore
    from gpt_windows_connector.operation_admission import OperationAdmissionStore
    from gpt_windows_connector.task_runs import TaskRunStore

    path = tmp_path / "usage-api.db"
    auth = AuthStore(path, "synthetic-operation-usage-signing-key-" * 2)
    owner = auth.register("usage-owner@example.invalid", "synthetic-password")
    other = auth.register("usage-other@example.invalid", "synthetic-password")
    actor = auth.register("usage-admin@example.invalid", "synthetic-password")
    with sqlite3.connect(path) as db:
        db.execute("UPDATE users SET role='admin' WHERE id=?", (actor.id,))
    NodeAuthStore(path)
    UserNodeBindingStore(path)
    tasks = TaskRunStore(path)
    store = OperationAdmissionStore(path, auth_store=auth, task_store=tasks)
    monkeypatch.setattr(gateway, "db_path", path)
    monkeypatch.setattr(gateway, "auth", auth)
    monkeypatch.setattr(gateway, "task_runs", tasks)
    now = time.time()

    def reserve(user, node, units):
        return store.reserve(owner_id=user.id, node_id=node, action="shell.run", target="synthetic-workspace",
                             requested_operations=units, timeout_seconds=3600,
                             details={"source": "account", "command": "private-command", "token": "private-token"})

    pending = reserve(owner, "selected-node", 5)
    unknown = reserve(owner, "selected-node", 11)
    store.mark_unconfirmed(unknown["id"], error_type="TimeoutError")
    historical = reserve(owner, "selected-node", 71)
    store.mark_unconfirmed(historical["id"], error_type="TimeoutError")
    wrong_node = reserve(owner, "other-node", 3)
    foreign = reserve(other, "selected-node", 91)
    # Synthetic fixture timestamps establish deterministic filter ordering and a
    # previous-period unresolved record, without dispatching any Node operation.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE operation_reservations SET started_at=? WHERE id=?", (now - 20, pending["id"]))
        db.execute("UPDATE operation_reservations SET started_at=? WHERE id=?", (now - 10, unknown["id"]))
        db.execute("UPDATE operation_reservations SET started_at=?,period_start=?,period_end=? WHERE id=?",
                   (now - 40 * 86400, now - 50 * 86400, now - 30 * 86400, historical["id"]))
        db.execute("UPDATE operation_reservations SET started_at=? WHERE id=?", (now - 1, wrong_node["id"]))
    tasks.record_operation(owner_id=owner.id, node_id="selected-node", action="shell.run", target="synthetic-workspace",
                           started_at=now - 100, ended_at=now - 99, status="success", details={}, operation_count=10)
    tasks.record_operation(owner_id=other.id, node_id="selected-node", action="shell.run", target="foreign-workspace",
                           started_at=now - 100, ended_at=now - 99, status="failed", details={}, operation_count=99)
    client = TestClient(Starlette(routes=[Route("/api/task-runs", webapp.api_task_runs), *admin.admin_routes]))
    return SimpleNamespace(client=client, owner=owner, other=other, pending=pending, unknown=unknown,
                           historical=historical, foreign=foreign,
                           owner_headers={"Authorization": "Bearer " + auth.issue_token(owner)},
                           admin_headers={"Authorization": "Bearer " + auth.issue_token(auth.get_user(actor.id))})


def test_task_api_owner_scope_filter_before_limit_and_completed_totals(usage_api):
    x = usage_api
    response = x.client.get("/api/task-runs?node_id=selected-node&days=7&limit=1&owner_id=" + x.other.id,
                            headers=x.owner_headers)
    assert response.status_code == 200
    data = response.json()
    assert [row["id"] for row in data["unresolved_operations"]] == [x.unknown["id"]]
    assert data["summary"]["operations"] == 10
    assert sum(step["operation_count"] for run in data["runs"] for step in run["steps"]) == 10
    assert "private-command" not in response.text and "private-token" not in response.text
    all_data = x.client.get("/api/task-runs?node_id=selected-node&days=all", headers=x.owner_headers).json()
    rows = {row["id"]: row for row in all_data["unresolved_operations"]}
    assert set(rows) == {x.pending["id"], x.unknown["id"], x.historical["id"]}
    assert rows[x.pending["id"]]["currently_held"] is True
    assert rows[x.historical["id"]]["currently_held"] is False
    assert all(row["owner_id"] == x.owner.id for row in rows.values())
    assert all_data["summary"]["operations"] == 10


def test_admin_detail_permission_scope_filters_and_entitlement_projection(usage_api):
    x = usage_api
    url = f"/api/admin/users/{x.owner.id}?node_id=selected-node&days=7&limit=1"
    denied = x.client.get(url, headers=x.owner_headers)
    assert denied.status_code == 403 and "unresolved_operations" not in denied.json()
    response = x.client.get(url, headers=x.admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert [row["id"] for row in data["unresolved_operations"]] == [x.unknown["id"]]
    assert len(data["operations"]) == 1
    assert data["usage"]["total"] == 10
    assert data["entitlements"]["requests_used"] == 10
    assert data["entitlements"]["requests_pending"] == 8
    assert data["entitlements"]["requests_unconfirmed"] == 11
    assert data["entitlements"]["request_remaining"] == 99971
    assert "private-command" not in response.text and "private-token" not in response.text
    historical = x.client.get(f"/api/admin/users/{x.owner.id}?days=all", headers=x.admin_headers).json()
    assert any(row["id"] == x.historical["id"] and row["currently_held"] is False for row in historical["unresolved_operations"])
    missing = x.client.get("/api/admin/users/no-such-user", headers=x.admin_headers)
    assert missing.status_code == 404
