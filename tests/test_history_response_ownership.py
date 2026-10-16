"""Run the actual dashboard history runtime with deterministic HTTP completion order.

The DOM/HTTP fixtures are synthetic; these tests are not browser, Windows Node,
provider-email, or deployed staging acceptance evidence.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from gpt_windows_connector import server


def run_history_js(body: str, loader: str = "tasks"):
    node = shutil.which("node")
    assert node, "Node.js is required for dashboard history race regressions"
    html = server.webapp._dashboard_html()
    runtime = html[html.index("const WEB_ZH="):html.index("function localizeWeb(")]
    # Account reset in core reuses the real usage renderer; keep the history
    # unresolved-record observer below independent of that renderer.
    runtime += html[html.index("function operationNumber("):html.index("function unresolvedOperationsHtml(")]
    runtime += html[html.index("const BILLING_PLAN_RANK="):html.index("async function billingChangePlan(")]
    runtime += html[html.index("async function api("):html.index("function adminMetric(")]
    # Use the rendered API/auth/history code, including final localization changes.
    ids = re.findall(r'\bid="([^"]+)"', html)
    harness = r'''
const assert=require('node:assert/strict'),window=globalThis;
const elements=new Map(),requests=[],listeners={};
function element(id){
  const classes=new Set(['hidden']);
  const e={id,value:'',innerHTML:'',textContent:'',style:{},disabled:false,
    focus(){},setAttribute(){},querySelector(){return null},querySelectorAll(){return []},
    classList:{add(c){classes.add(c)},remove(c){classes.delete(c)},contains(c){return classes.has(c)},
      toggle(c,on){on=on===undefined?!classes.has(c):on;on?classes.add(c):classes.delete(c);return on}}};
  elements.set(id,e);globalThis[id]=e;return e;
}
''' + "\n".join(f"element({json.dumps(id)});" for id in ids) + r'''
const state={user:{id:'synthetic-user',email:'fixture@example.test'}};
const document={getElementById:id=>elements.get(id)||null,
  querySelector:()=>null,querySelectorAll:s=>s==='.view'?['dashboard','tasks','logs'].map(id=>elements.get(id)):[],
  addEventListener(){}};
const location={pathname:'/task-runs',search:'',hash:''},history={
  pushState(_s,_t,path){location.pathname=path},replaceState(_s,_t,path){location.pathname=path}};
window.addEventListener=(event,fn)=>{listeners[event]=fn};
const WEB_LANG='en';
function setInterval(){return 1}function clearInterval(){}function setTimeout(){return 1}function clearTimeout(){}
function stopRealtime(){}
let unresolved=[];
function renderTaskUnresolvedOperations(value){unresolved=value||[]}
function fetch(url,options){
  assert.equal(options.credentials,'include');
  assert.ok(!options.method||options.method==='POST'&&url==='/api/logout','History must stay read-only');
  return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
}
function respond(index,data,status=200){requests[index].resolve({status,ok:status>=200&&status<300,json:async()=>data})}
function payload(marker,count=7){return {summary:{task_runs:count,operations:count,duration_ms:1000},
  runs:[{title:marker,node_id:'synthetic',started_at:1,status:'done',steps:[]}],
  unresolved_operations:[{reservation_id:marker}],logs:[{created_at:1,action:marker,target:marker,details:{marker}}]}}
async function settle(){for(let i=0;i<12;i++)await Promise.resolve()}
function screen(){return LOADER==='tasks'?taskRunTable.innerHTML:logTable.innerHTML}
function select(n){taskRunDays.value=String(n);logAction.value='action '+n;logTarget.value='target & '+n}
function load(){return LOADER==='tasks'?loadTaskRuns():loadLogs()}
'''.replace("LOADER", json.dumps(loader))
    script = "(function(){\n" + harness + runtime + r'''
(async()=>{
showApp();taskRunDays.value='all';
''' + body + r'''
console.log('history-response-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
})();
'''
    result = subprocess.run([node, "-"], input=script, capture_output=True,
                            text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    assert "history-response-complete" in result.stdout, "A request was left unsettled"


@pytest.mark.parametrize("loader", ["tasks", "logs"])
def test_latest_success_owns_rows_and_task_totals(loader):
    run_history_js(r'''
const old=load();select(7);const latest=load();
respond(1,payload('LATEST',7));await latest;
const summary=taskRunSummary.innerHTML,evidence=unresolved;
respond(0,payload('OLD',99));await old;
assert.match(screen(),/LATEST/);assert.doesNotMatch(screen(),/>OLD</);
assert.equal(taskRunSummary.innerHTML,summary);assert.equal(unresolved,evidence);
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
def test_old_success_cannot_render_while_newer_request_is_pending(loader):
    run_history_js(r'''
const old=load();select(7);const latest=load();respond(0,payload('OLD'));await old;
assert.equal(screen(),'');assert.equal(taskRunSummary.innerHTML,'');assert.deepEqual(unresolved,[]);
respond(1,payload('LATEST'));await latest;assert.match(screen(),/LATEST/);
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
@pytest.mark.parametrize("failure", ["network", "http", "unauthorized"])
def test_obsolete_failures_cannot_affect_a_new_success(loader, failure):
    response = {
        "network": "requests[0].reject(new Error('old network failure'))",
        "http": "respond(0,{error:'old server failure'},500)",
        "unauthorized": "respond(0,{error:'old unauthorized'},401)",
    }[failure]
    run_history_js(r'''
const old=load();select(7);const latest=load();respond(1,payload('LATEST'));await latest;
''' + response + r''';await old;
assert.match(screen(),/LATEST/);assert.ok(state.user);assert.equal(auth.classList.contains('hidden'),true);
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
def test_current_failure_is_observable_and_old_success_is_not_a_fallback(loader):
    run_history_js(r'''
const old=load();select(7);const latest=load();
respond(1,{error:'current server failure'},503);await assert.rejects(latest,/current server failure/);
respond(0,payload('OLD'));await old;assert.equal(screen(),'');
const retry=load();respond(2,payload('RETRY'));await retry;assert.match(screen(),/RETRY/);
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
def test_current_network_failure_is_observable(loader):
    run_history_js(r'''
const current=load();requests[0].reject(new Error('current network failure'));
await assert.rejects(current,/current network failure/);assert.equal(screen(),'');
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
def test_current_401_opens_auth_and_invalidates_other_history(loader):
    other_loader = "loadLogs()" if loader == "tasks" else "loadTaskRuns()"
    run_history_js("const current=load();const other=" + other_loader + ";\n" + r'''
respond(0,{error:'current unauthorized'},401);await current;
assert.equal(state.user,null);assert.equal(auth.classList.contains('hidden'),false);
respond(1,payload('OLD_SESSION'));await other;
assert.equal(taskRunTable.innerHTML,'');assert.equal(logTable.innerHTML,'');assert.equal(taskRunSummary.innerHTML,'');
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
@pytest.mark.parametrize("transition", ["showAuth()", "showRegister(true)", "resetLoginVerification()", "state.user={id:'another-user'}", "state.user=null"])
def test_auth_or_account_transition_invalidates_history(loader, transition):
    run_history_js(r'''
const old=load();
''' + transition + r''';
respond(0,payload('OLD_SESSION'));await old;assert.equal(screen(),'');assert.equal(taskRunSummary.innerHTML,'');
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
def test_new_session_is_not_affected_by_old_401(loader):
    run_history_js(r'''
const old=load();showAuth();state.user={id:'new-user'};showApp();
const latest=load();respond(1,payload('NEW_SESSION'));await latest;
respond(0,{error:'old session expired'},401);await old;
assert.equal(state.user.id,'new-user');assert.match(screen(),/NEW_SESSION/);assert.equal(auth.classList.contains('hidden'),true);
''', loader)


@pytest.mark.parametrize("loader", ["tasks", "logs"])
@pytest.mark.parametrize("status", [200, 401])
def test_response_json_completion_rechecks_ownership(loader, status):
    run_history_js(r'''
let finishJson;const old=load();
requests[0].resolve({status:STATUS,ok:STATUS===200,json:()=>new Promise(resolve=>{finishJson=resolve})});await settle();
select(7);const latest=load();respond(1,payload('LATEST'));await latest;
finishJson(payload('OLD'));await old;assert.match(screen(),/LATEST/);assert.ok(state.user);
'''.replace("STATUS", str(status)), loader)


def test_task_and_activity_loads_are_independent_and_filters_are_encoded():
    run_history_js(r'''
select('7');const task=loadTaskRuns(),log=loadLogs();
assert.equal(requests[0].url,'/api/task-runs?limit=500&days=7');
const q=new URLSearchParams(requests[1].url.split('?')[1]);
assert.equal(q.get('action'),'action 7');assert.equal(q.get('target'),'target & 7');assert.equal(q.get('limit'),'200');
respond(1,payload('LOG'));await log;respond(0,payload('TASK'));await task;
assert.match(logTable.innerHTML,/LOG/);assert.match(taskRunTable.innerHTML,/TASK/);
assert.match(taskRunSummary.innerHTML,/>7</);assert.equal(unresolved[0].reservation_id,'TASK');
''')


def test_repeated_navigation_and_popstate_keep_newest_history():
    run_history_js(r'''
view('tasks',null);view('logs',null);view('tasks',null);
location.pathname='/task-runs';listeners.popstate();
assert.equal(requests.length,4);respond(3,payload('LATEST_TASK'));await settle();
respond(2,payload('OLDER_TASK'));respond(0,payload('OLDEST_TASK'));respond(1,payload('LOG'));await settle();
assert.match(taskRunTable.innerHTML,/LATEST_TASK/);assert.doesNotMatch(taskRunTable.innerHTML,/OLDER_TASK|OLDEST_TASK/);
assert.match(logTable.innerHTML,/LOG/);assert.equal(location.pathname,'/task-runs');
''')


def test_completed_logout_invalidates_pending_history():
    run_history_js(r'''
const task=loadTaskRuns(),log=loadLogs(),out=logout();
assert.equal(requests[2].url,'/api/logout');respond(2,{});await out;
respond(0,payload('OLD'));respond(1,payload('OLD'));await Promise.all([task,log]);
assert.equal(state.user,null);assert.equal(taskRunTable.innerHTML,'');assert.equal(logTable.innerHTML,'');
''')


def test_guest_history_does_not_dispatch_requests():
    run_history_js(r'''
showAuth();await loadTaskRuns();await loadLogs();assert.equal(requests.length,0);
''')
