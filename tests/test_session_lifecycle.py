"""Actual dashboard lifecycle with synthetic HTTP, DOM, sockets and timers."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from gpt_windows_connector import server
from test_dashboard_response_ownership import DASHBOARD_CASES, DashboardIds


def run_session_cases(tmp_path, cases, label):
    html = server.webapp._dashboard_html()
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    runtime = next(s for s in scripts if "const state=" in s)
    assert runtime.endswith("\nboot();\n")
    runtime = next(s for s in scripts if "const WEB_LANG=" in s) + "\n" + runtime[:-len("boot();\n")]
    markup = DashboardIds(); markup.feed(html)
    fixture = DASHBOARD_CASES.split("for(const language of ['en','zh-CN']){")[0]
    fixture = fixture.replace("'/api/logout'].includes(url)", "'/api/logout','/api/referrals/summary'].includes(url)")
    fixture = fixture.replace("const requests=[],elements=", "let clock=1000,timerId=0;const timeouts=new Map(),intervals=new Map();class FixtureDate extends Date{static now(){return clock}};const requests=[],elements=")
    fixture = fixture.replace("const ctx={console,URLSearchParams,Date,", "const ctx={console,URLSearchParams,Date:FixtureDate,")
    fixture = fixture.replace("setTimeout(){return 1},clearTimeout(){},setInterval(){return 1},clearInterval(){},", "setTimeout(callback,delay){const id=++timerId;timeouts.set(id,{callback,delay});return id},clearTimeout(id){timeouts.delete(id)},setInterval(callback,delay){const id=++timerId;intervals.set(id,{callback,delay});return id},clearInterval(id){intervals.delete(id)},")
    fixture = fixture.replace("close(){this.readyState=3}send(){}", "sent=[];closed=[];close(...args){this.closed.push(args);this.readyState=3}send(data){this.sent.push(data)}")
    fixture = fixture.replace("return {ctx,requests,", "return {ctx,timeouts,intervals,advance(ms){clock+=ms},requests,")
    script = tmp_path / (label + ".mjs")
    script.write_text("const runtime=" + json.dumps(runtime) + ";\nconst markup=" + json.dumps(markup.elements) + ";\n" + fixture + SHARED_CASES + cases, encoding="utf-8")
    node = shutil.which("node"); assert node, "Node.js is required for lifecycle regressions"
    result = subprocess.run([node, "--test", str(script)], capture_output=True, text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fail 0" in result.stdout


SHARED_CASES = r'''
const lifecycleTest=(name,body)=>test(name,{timeout:1500},body);
function account(f,id='user-b'){f.call("showAuth();state.user="+JSON.stringify({id,email:'b@example.test',role:'user'})+";showApp()")}
function currentMe(id='user-a',role='user'){return {user:{id,email:'a@example.test',name:'Current account',role,provider:'email'}}}
async function finishBoot(f,p,index=0,id='user-a',role='user'){f.respond(index,currentMe(id,role));await settle();reply(f,index+1,'CURRENT');await p}
function socketCallbacks(socket){return {open:socket.onopen,message:socket.onmessage,close:socket.onclose,error:socket.onerror}}
'''


def test_session_boot_logout_and_account_presentation(tmp_path):
    run_session_cases(tmp_path, SESSION_CASES, "session-lifecycle")


SESSION_CASES = r'''
for(const language of ['en','zh-CN']){
 lifecycleTest(language+': current bootstrap retains account identity and normal follow-up reads',async()=>{const f=fixture(language),p=f.call('boot()');await finishBoot(f,p);assert.equal(f.call('state.user.id'),'user-a');assert.equal(f.ctx.userName.textContent,'Current account');assert.equal(f.ctx.accountProvider.textContent,'email');assert.equal(f.sockets.length,1);assert.equal(f.requests.length,4)});
 for(const oldOutcome of [200,401,503,'network'])lifecycleTest(language+': older bootstrap cannot replace or sign out newer bootstrap '+oldOutcome,async()=>{const f=fixture(language),old=f.call('boot()'),fresh=f.call('boot()');await finishBoot(f,fresh,1,'user-b');if(oldOutcome==='network')f.requests[0].reject(new Error('OLD'));else f.respond(0,oldOutcome===200?currentMe('old-account'):{error:'OLD'},oldOutcome);await settle();if(f.requests.length>5)reply(f,5,'OLD');await old;assert.equal(f.call('state.user.id'),'user-b');assert.equal(f.requests.length,5);assert.equal(f.sockets.length,1)});
 lifecycleTest(language+': old bootstrap delayed JSON cannot replace current owner',async()=>{const f=fixture(language),old=f.call('boot()');let deliver;f.requests[0].resolve({status:200,ok:true,json:()=>new Promise(r=>deliver=r)});await settle();const fresh=f.call('boot()');await finishBoot(f,fresh,1,'user-b');deliver(currentMe('OLD'));await settle();if(f.requests.length>5)reply(f,5,'OLD');await old;assert.equal(f.call('state.user.id'),'user-b')});
 lifecycleTest(language+': auth reset invalidates pending bootstrap without extra reads',async()=>{const f=fixture(language),old=f.call('boot()');f.call('showAuth()');f.respond(0,currentMe('OLD'));await old;assert.equal(f.call('state.user'),null);assert.equal(f.requests.length,1);assert.equal(f.sockets.length,0)});
 lifecycleTest(language+': obsolete caller does not claim a new bootstrap',async()=>{const f=fixture(language),current=f.call('boot()'),obsolete=f.call('boot(()=>false)'),count=f.requests.length;if(count>1)f.respond(1,currentMe());await obsolete;f.respond(0,currentMe());await settle();reply(f,count,'CURRENT');await current;assert.equal(f.call('state.user.id'),'user-a');assert.equal(count,1);assert.equal(f.requests.length,4)});
 for(const role of ['user','admin','super_admin'])lifecycleTest(language+': current role controls admin navigation '+role,async()=>{const f=fixture(language);f.ctx.adminNav.classList.remove('hidden');const p=f.call('boot()');await finishBoot(f,p,0,'user-b',role);assert.equal(f.ctx.adminNav.classList.contains('hidden'),role==='user')});
 lifecycleTest(language+': reset clears identity text and admin navigation without erasing drafts',()=>{const f=fixture(language);for(const id of ['userName','userEmail','accountName','accountEmail','accountProvider'])f.elements.get(id).textContent='OLD';for(const id of ['aiManageName','aiManageNote','connectNodeId','connectCode','taskRunDays','logAction','logTarget'])f.elements.get(id).value='DRAFT';f.stored.set('unrelated','keep');f.call('showAuth()');for(const id of ['userName','userEmail','accountName','accountEmail','accountProvider'])assert.equal(f.elements.get(id).textContent,'');for(const id of ['aiManageName','aiManageNote','connectNodeId','connectCode','taskRunDays','logAction','logTarget'])assert.equal(f.elements.get(id).value,'DRAFT');assert.equal(f.stored.get('unrelated'),'keep');assert.ok(f.ctx.adminNav.classList.contains('hidden'))});
 for(const outcome of [200,401,503,'network'])lifecycleTest(language+': dispatched old logout response cannot hide replacement account '+outcome,async()=>{const f=fixture(language),old=f.call('logout()');assert.equal(f.requests[0].url,'/api/logout');assert.equal(f.requests[0].options.method,'POST');assert.equal(f.requests[0].options.body,undefined);account(f);if(outcome==='network')f.requests[0].reject(new Error('OLD'));else f.respond(0,{error:'OLD'},outcome);await old;assert.equal(f.call('state.user.id'),'user-b');assert.equal(f.requests.length,1)});
 for(const outcome of [200,503,'network'])lifecycleTest(language+': current logout keeps established signout after response '+outcome,async()=>{const f=fixture(language),p=f.call('logout()');if(outcome==='network')f.requests[0].reject(new Error('CURRENT'));else f.respond(0,{},outcome);await p;assert.equal(f.call('state.user'),null);assert.equal(f.ctx.auth.classList.contains('hidden'),false)});
 lifecycleTest(language+': current logout remains current through same-account bootstrap object replacement',async()=>{const f=fixture(language),logout=f.call('logout()'),boot=f.call('boot()');await finishBoot(f,boot,1);f.respond(0,{ok:true});await logout;assert.equal(f.call('state.user'),null)});
 lifecycleTest(language+': current bootstrap HTTP failure retains authentication fallback',async()=>{const f=fixture(language),p=f.call('boot()');f.respond(0,{error:'CURRENT'},503);await p;assert.equal(f.call('state.user'),null);assert.equal(f.requests.length,1)});
}
'''
