"""Execute the rendered computer/checklist/i18n functions with controlled DOM/HTTP.

This is a deterministic runtime regression harness, not a browser substitute.
The Chromium suite covers the same production page in the real browser.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    for variable in ("HOME", "LOCALAPPDATA", "GWC_DATA_DIR"):
        directory = tmp_path / variable.lower()
        directory.mkdir()
        monkeypatch.setenv(variable, str(directory))
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")


def run_computer_js(body: str, language: str = "en"):
    from gpt_windows_connector import server

    node = shutil.which("node")
    assert node, "Node.js is required for computer onboarding runtime regressions"
    html = server.webapp._dashboard_html()
    # Extract actual composed production functions/catalog; never copy their logic.
    def between(start, end):
        return html[html.index(start):html.index(end, html.index(start))]

    runtime = "\n".join((
        between("const WEB_LANG=", "</script>"),
        between("function operationNumber(", "const state="),
        between("const state=", "async function billingChangePlan("),
        between("async function api(", "function showAuth("),
        between("function closeModal(", "let onboardingStep="),
        between("function esc(", "async function boot("),
        between("function accessMode(", "function renderNodes("),
        between("function openConnectModal(", "\n(() => {\n  let active = false;"),
        between("(() => {\n  let active = false;", "function adminMetric("),
        between("if(WEB_LANG==='zh'){localizeWeb();", "\ndocument.addEventListener('keydown'"),
    ))
    markup = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.S)
    script = r'''
const assert = require('node:assert/strict');
const focused=[],requests=[],timeouts=[],mutations=[],stored=new Map(),routes=[];
let observer=null,refreshes=0,signedOut=0,loginGeneration=0;
const Node={ELEMENT_NODE:1,TEXT_NODE:3},NodeFilter={SHOW_TEXT:4};
function descendants(root){return root.children.flatMap(n=>[n,...(n.children?descendants(n):[])])}
function changed(target,nodes){if(observer && (target===document.body || descendants(document.body).includes(target)))mutations.push({addedNodes:nodes})}
function textNode(value){return {nodeType:3,nodeValue:value,get textContent(){return this.nodeValue}}}
function matches(el,selector){
  if(el.nodeType!==1)return false;
  const tag=selector.match(/^[\w-]+/),id=selector.match(/#([\w-]+)/),cls=selector.match(/\.([\w-]+)/);
  if(tag&&el.tagName!==tag[0])return false;
  if(id&&el.id!==id[1])return false;
  if(cls&&!el.classList.contains(cls[1]))return false;
  for(const [,name,value] of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)){
    if(el.getAttribute(name)===null || (value!==undefined&&el.getAttribute(name)!==value))return false;
  }
  return true;
}
class Element {
  constructor(tag){this.tagName=tag;this.nodeType=1;this.children=[];this.attrs={};this.style={};this.value='';this.dataset={};
    this.classList={contains:c=>(this.attrs.class||'').split(/\s+/).includes(c),
      add:(...cs)=>{this.attrs.class=[...new Set([...(this.attrs.class||'').split(/\s+/).filter(Boolean),...cs])].join(' ')},
      remove:(...cs)=>{this.attrs.class=(this.attrs.class||'').split(/\s+/).filter(c=>!cs.includes(c)).join(' ')},
      toggle:(c,on)=>{on=on===undefined?!this.classList.contains(c):on;on?this.classList.add(c):this.classList.remove(c);return on}};
  }
  get id(){return this.attrs.id||''} set id(v){this.setAttribute('id',v)}
  get placeholder(){return this.attrs.placeholder||''} set placeholder(v){this.setAttribute('placeholder',v)}
  setAttribute(k,v){this.attrs[k]=String(v);if(k==='id'&&!(v in globalThis))globalThis[v]=this;if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v}
  getAttribute(k){return this.attrs[k]??null}
  appendChild(n){n.parent=this;this.children.push(n);changed(this,[n]);return n}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this)}
  set textContent(v){this.children=[];if(v!=='')this.appendChild(textNode(String(v)))}
  get textContent(){return this.children.map(n=>n.textContent).join('')}
  set innerHTML(v){this.children=[];parseInto(this,v)}
  querySelectorAll(s){return descendants(this).filter(n=>s.split(',').some(x=>matches(n,x.trim())))}
  querySelector(s){return this.querySelectorAll(s)[0]||null}
  focus(){focused.push(this.id)}
  getBoundingClientRect(){return {right:170,top:260}}
  get offsetWidth(){return 280} get offsetHeight(){return 80}
}
function parseInto(root,html){
  const stack=[root],voids=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  for(const token of html.match(/<!--[\s\S]*?-->|<[^>]+>|[^<]+/g)||[]){
    if(token.startsWith('<!'))continue;
    if(token.startsWith('</')){if(stack.length>1)stack.pop();continue}
    if(token.startsWith('<')){
      const match=token.match(/^<([\w-]+)/);if(!match)continue;
      const el=new Element(match[1].toLowerCase());
      for(const [,name,dq,sq,bare] of token.slice(match[0].length,-1).matchAll(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))el.setAttribute(name,dq??sq??bare??'');
      stack.at(-1).appendChild(el);if(!voids.has(el.tagName)&&!token.endsWith('/>'))stack.push(el);
    }else stack.at(-1).appendChild(textNode(token));
  }
}
const document={documentElement:new Element('html'),head:new Element('head'),body:new Element('body'),addEventListener(){},
  createElement:tag=>new Element(tag),getElementById:id=>document.body.querySelector('#'+id),
  querySelector:s=>document.body.querySelector(s),querySelectorAll:s=>document.body.querySelectorAll(s),
  createTreeWalker(root){const nodes=descendants(root).filter(n=>n.nodeType===3);let i=0;return {nextNode(){this.currentNode=nodes[i++];return !!this.currentNode}}}};
class MutationObserver {constructor(callback){this.callback=callback}observe(){observer=this.callback}}
function flushMutations(){for(let i=0;mutations.length&&i<20;i++)observer(mutations.splice(0));assert.equal(mutations.length,0)}
const window=globalThis,location={href:'/nodes'},navigator={language:LANGUAGE};
window.addEventListener=()=>{};window.innerWidth=1280;window.innerHeight=800;
const localStorage={getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)};
function setTimeout(f,delay){timeouts.push({f,delay});return timeouts.length}
function runTimers(delay){const due=timeouts.filter(t=>delay===undefined||t.delay===delay);for(const t of due){timeouts.splice(timeouts.indexOf(t),1);t.f()}flushMutations()}
function fetch(url,options){return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))}
function response(index,data,status=200){requests[index].resolve({status,ok:status>=200&&status<300,json:async()=>data})}
async function refresh(){refreshes++}
function showAuth(){signedOut++}
window.view=(id,nav)=>routes.push({id,nav});
function visible(id){return !document.getElementById(id).classList.contains('hidden')}
function signIn(){state.user={email:'synthetic@example.test'};auth.classList.add('hidden');app.classList.remove('hidden')}
function offlineBindings(count){return Array.from({length:count},(_,i)=>({node_id:'offline-'+i,online:false,authorized:i%2===0,access_state:'authorized',plan_limited:i>=3}))}
document.body.innerHTML=MARKUP;
'''.replace("LANGUAGE", json.dumps(language)).replace("MARKUP", json.dumps(markup))
    script += "\n" + runtime + "\n(async()=>{\n" + body + r'''
flushMutations();console.log('computer-onboarding-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    # stdin avoids command-line length limits on Windows CI.
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    assert "computer-onboarding-complete" in result.stdout, "Runtime left an unexpected request pending"


@pytest.mark.parametrize("count", [0, 2, 3, 5], ids=["none", "below-limit", "at-limit", "above-limit"])
def test_connect_opens_and_resets_without_counting_offline_bindings(count):
    run_computer_js(f"""
signIn();state.billing={{node_limit:3}};state.nodes=offlineBindings({count});
const before=JSON.stringify(state);connectNodeId.value='old-node';connectCode.value='11111111';
connectResult.textContent='old result';connectResult.classList.remove('hidden');
openConnectModal();assert.equal(visible('connectModal'),true);
assert.equal(connectNodeId.value,'');assert.equal(connectCode.value,'');
assert.equal(connectResult.textContent,'');assert.equal(visible('connectResult'),false);
runTimers();assert.deepEqual(focused,['connectNodeId']);assert.equal(location.href,'/nodes');
assert.equal(requests.length,0);assert.equal(refreshes,0);assert.equal(JSON.stringify(state),before);
""")


@pytest.mark.parametrize("count", [3, 5])
def test_reconnect_prefills_node_but_requires_new_code_and_explicit_submit(count):
    run_computer_js(f"""
signIn();state.billing={{node_limit:3}};state.nodes=offlineBindings({count});
connectCode.value='11111111';connectResult.textContent='old request';
openConnectModalForNode(encodeURIComponent('computer-synthetic / 1'));
assert.equal(visible('connectModal'),true);assert.equal(connectNodeId.value,'computer-synthetic / 1');
assert.equal(connectCode.value,'');assert.equal(connectResult.textContent,'');
assert.equal(visible('connectResult'),false);assert.equal(focused[0],'connectCode');
runTimers();assert.equal(location.href,'/nodes');assert.equal(requests.length,0);
""")


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("node_id,code,error", [
    ("  ", "12345678", "Node ID is required"),
    ("computer-test", "", "Enter the 8-digit Connection Code"),
    ("computer-test", "1234567", "Enter the 8-digit Connection Code"),
    ("computer-test", "123456789", "Enter the 8-digit Connection Code"),
    ("computer-test", "1234abcd", "Enter the 8-digit Connection Code"),
    ("computer-test", "１２３４５６７８", "Enter the 8-digit Connection Code"),
])
def test_connection_code_validation_prevents_requests(language, node_id, code, error):
    expected = error if language == "en" else {
        "Node ID is required": "请输入 Node ID",
        "Enter the 8-digit Connection Code": "请输入 8 位连接码",
    }[error]
    run_computer_js(f"""
openConnectModal();connectNodeId.value={json.dumps(node_id)};connectCode.value={json.dumps(code)};
await requestNodeAccess();flushMutations();assert.equal(toast.textContent,{json.dumps(expected)});
assert.equal(requests.length,0);assert.equal(refreshes,0);assert.equal(visible('connectResult'),false);
""".replace("toast.textContent", "document.getElementById('toast').textContent"), language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("data,status,expected,refresh_count", [
    ({"pending": True}, 200, ("Access request sent. Waiting for local approval on the target computer.", "访问申请已发送，正在等待目标电脑本地批准。"), 1),
    ({"authorized": True}, 200, ("Access approved on the target computer.", "访问已在目标电脑本地批准。"), 1),
    ({"error": "invalid connection code"}, 200, ("Connection Code is incorrect.", "连接码不正确。"), 0),
    ({"error": "not accepted"}, 200, ("Access request was not accepted.", "访问申请未被接受。"), 0),
    ({"error": "Synthetic server refusal"}, 403, ("Synthetic server refusal", "Synthetic server refusal"), 0),
])
def test_explicit_access_request_preserves_local_approval_and_server_response(language, data, status, expected, refresh_count):
    text = expected[language != "en"]
    sending = "Sending access request…" if language == "en" else "正在发送访问申请…"
    run_computer_js(f"""
signIn();state.billing={{node_limit:3}};state.nodes=offlineBindings(5);const before=JSON.stringify(state);
openConnectModal();connectNodeId.value='  computer-synthetic  ';connectCode.value='  12345678  ';
assert.equal(requests.length,0);const pending=requestNodeAccess();flushMutations();
assert.equal(connectResult.textContent,{json.dumps(sending)});assert.equal(visible('connectResult'),true);
assert.equal(requests.length,1);assert.equal(requests[0].url,'/api/nodes/request-access');
assert.equal(requests[0].options.method,'POST');assert.equal(requests[0].options.credentials,'include');
assert.deepEqual(JSON.parse(requests[0].options.body),{{node_id:'computer-synthetic',connection_code:'12345678'}});
response(0,{json.dumps(data)},{status});await pending;flushMutations();
assert.equal(connectResult.textContent,{json.dumps(text)});assert.equal(refreshes,{refresh_count});
assert.equal(JSON.stringify(state),before);assert.equal(signedOut,0);assert.equal(location.href,'/nodes');
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_checklist_localization_accessibility_and_real_state(language):
    expected = ["GETTING STARTED", "Setup Checklist", "Connect your AI", "Connect your computer", "Set permissions", "Close"] if language == "en" else ["入门指南", "设置清单", "连接你的 AI", "连接电脑", "设置权限", "关闭"]
    label = "Getting Started" if language == "en" else "入门指南"
    run_computer_js(f"""
signIn();state.nodes=[{{node_id:'pending',pending:true,access_state:'pending'}}];
maybeStartOnboarding();flushMutations();const coach=document.getElementById('lucasCoach');
assert.ok(coach);assert.equal(coach.style.display,'block');assert.equal(coach.getAttribute('role'),'dialog');
assert.equal(coach.getAttribute('aria-modal'),'true');assert.equal(coach.getAttribute('aria-label'),{json.dumps(label)});
for(const text of {json.dumps(expected)})assert.ok(coach.textContent.includes(text),text);
let steps=coach.querySelectorAll('.coach-step');assert.equal(steps.length,3);
assert.deepEqual(steps.map(b=>b.classList.contains('done')),[false,false,false]);
state.aiClients=[{{client_id:'synthetic-ai'}}];state.nodes=offlineBindings(1);onboardingSync();flushMutations();
steps=coach.querySelectorAll('.coach-step');assert.deepEqual(steps.map(b=>b.classList.contains('done')),[true,true,true]);
steps[0].onclick();assert.equal(coach.style.display,'none');assert.equal(routes[0].id,'ai');
openGettingStarted();flushMutations();coach.querySelectorAll('.coach-step')[2].onclick();
assert.equal(routes[1].id,'nodes');assert.equal(requests.length,0);
assert.equal(state.nodes[0].online,false);assert.equal(state.nodes[0].authorized,true);
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_checklist_dismissal_hint_reopen_and_signed_out_guard(language):
    hint = "You can reopen setup guidance here anytime." if language == "en" else "你可以随时在这里重新打开设置指南。"
    button = "Got it" if language == "en" else "知道了"
    nav = "Help · Getting Started" if language == "en" else "帮助 · 入门指南"
    run_computer_js(f"""
maybeStartOnboarding();assert.equal(document.getElementById('lucasCoach'),null);
signIn();maybeStartOnboarding();flushMutations();document.getElementById('coachClose').onclick();runTimers(120);
assert.equal(document.getElementById('lucasCoach').style.display,'none');
const hint=document.getElementById('coachReopenHint');assert.ok(hint);
assert.ok(hint.textContent.includes({json.dumps(hint)}));assert.equal(hint.querySelector('button').textContent,{json.dumps(button)});
assert.equal(gettingStartedNav.textContent,{json.dumps(nav)});hint.querySelector('button').onclick();
assert.equal(document.getElementById('coachReopenHint'),null);maybeStartOnboarding();
assert.equal(document.getElementById('lucasCoach').style.display,'none');
openGettingStarted();flushMutations();assert.equal(document.getElementById('lucasCoach').style.display,'block');
state.user=null;auth.classList.remove('hidden');app.classList.add('hidden');onboardingSync();
assert.equal(document.getElementById('lucasCoach').style.display,'none');assert.equal(requests.length,0);
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_connection_modal_copy_and_code_metadata_are_preserved(language):
    paragraph = "Enter the Node ID and 8-digit Connection Code shown in Lucas Settings on the target computer. After the code is verified, that computer must still approve this Lucas account locally."
    if language != "en":
        paragraph = "输入目标电脑 Lucas 设置中显示的 Node ID 和 8 位连接码。连接码验证通过后，仍须由该电脑在本地批准此 Lucas 账号。"
    run_computer_js(f"""
assert.ok(connectModal.textContent.includes({json.dumps(paragraph)}));
assert.ok(connectModal.textContent.includes({'"Connection Code"' if language == 'en' else '"连接码"'}));
assert.equal(connectCode.getAttribute('maxlength'),'8');assert.equal(connectCode.getAttribute('inputmode'),'numeric');
assert.equal(connectCode.getAttribute('autocomplete'),'off');assert.equal(connectCode.placeholder,'12345678');
assert.equal(connectNodeId.getAttribute('autocomplete'),'off');assert.equal(connectNodeId.placeholder,'computer-xxxxxxxxxxxx');
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("paid", [False, True])
def test_beta_explanations_use_catalog_without_changing_limits_or_subscription_state(language, paid):
    intro = "Free during testing. 100,000 Operations/month, 3 Computers, 3 AI accounts. Plans and limits may change."
    footer = "Beta Notice: Plans, pricing, and limits may change during Beta."
    notice = "Lucas Beta is free during testing. An existing paid subscription is on record; review it separately to avoid future charges." if paid else "Lucas Beta is free during testing. Plans and limits may change."
    if language != "en":
        intro = "测试期间免费。每月 100,000 次操作、3 台电脑、3 个 AI 账号。套餐和限制可能调整。"
        footer = "测试提示：测试期间套餐、价格和限制可能调整。"
        notice = "Lucas 测试期间免费。系统中仍有付费订阅记录，请单独检查该订阅以避免后续扣费。" if paid else "Lucas 测试期间免费。套餐和限制可能调整。"
    run_computer_js(f"""
assert.ok(billing.textContent.includes({json.dumps(intro)}));assert.ok(billing.textContent.includes({json.dumps(footer)}));
const summary={{beta_free:true,existing_paid_subscription:{str(paid).lower()},plan:'free',plan_name:'Lucas Beta',requests_used:5,request_limit:100000,nodes_used:3,node_limit:3,nodes_connected:5,ai_accounts_used:1,ai_account_limit:3}};
signIn();const pending=loadBillingView();assert.equal(requests.length,1);assert.equal(requests[0].url,'/api/billing/summary');
response(0,summary);await pending;flushMutations();assert.equal(billingNotice.textContent,{json.dumps(notice)});
assert.deepEqual(state.billing,summary);assert.equal(billingPrice.textContent,'$0');
assert.equal(requests.length,1);assert.equal(location.href,'/nodes');
""".replace("billingNotice.textContent", "document.getElementById('billingNotice').textContent"), language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("node,status,mode,action", [
    ({"authorized": True, "online": True, "preset": "custom"}, ("Online", "在线"), ("Custom", "自定义"), ("View", "查看")),
    ({"authorized": True, "online": False}, ("Offline", "离线"), ("Ask for approval", "请求批准"), ("View", "查看")),
    ({"authorized": True, "online": True, "plan_limited": True, "preset": "full_access"}, ("Plan limit", "套餐限制"), ("Full Access", "完全访问权限"), ("Activate", "启用")),
    ({"pending": True}, ("Pending approval", "待批准"), ("Awaiting local approval", "等待本地批准"), None),
    ({"access_state": "unauthorized"}, ("Offline", "离线"), ("Not authorized", "未授权"), ("Reconnect", "重新连接")),
    ({"access_state": "unknown"}, ("Offline", "离线"), ("Authorization unavailable", "授权状态未知"), ("Reconnect", "重新连接")),
    ({"access_state": "authorized", "online": True, "preset": "auto_approve"}, ("Online", "在线"), ("Auto-approve safe actions", "自动批准安全操作"), ("View", "查看")),
])
def test_computer_status_permissions_and_actions_follow_server_state(language, node, status, mode, action):
    index = language != "en"
    node = {"node_id": "computer-synthetic", **node}
    expected_action = action[index] if action else None
    run_computer_js(f"""
const node={json.dumps(node)},before=JSON.stringify(node);
nodeTable.innerHTML='<table><tbody>'+nodeRowHtml(node)+'</tbody></table>';flushMutations();
assert.equal(nodeTable.querySelector('.badge').textContent,{json.dumps(status[index])});
assert.equal(nodeTable.querySelectorAll('td')[2].textContent,{json.dumps(mode[index])});
assert.equal(nodeTable.querySelector('button')?.textContent??null,{json.dumps(expected_action)});
assert.equal(JSON.stringify(node),before);assert.equal(requests.length,0);
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_connection_network_failure_does_not_grant_access_or_retry(language):
    run_computer_js("""
signIn();state.nodes=offlineBindings(3);state.billing={node_limit:3};const before=JSON.stringify(state);
openConnectModal();connectNodeId.value='computer-test';connectCode.value='12345678';
const pending=requestNodeAccess();requests[0].reject(new Error('Synthetic network failure'));
await pending;flushMutations();runTimers();
assert.equal(connectResult.textContent,'Synthetic network failure');assert.equal(visible('connectResult'),true);
assert.equal(requests.length,1);assert.equal(refreshes,0);assert.equal(JSON.stringify(state),before);
assert.equal(location.href,'/nodes');
""", language)
