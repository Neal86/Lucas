"""Execute the rendered dashboard auth runtime against controlled DOM/HTTP state.

These tests can also run with PYTHONPATH pointing to an older source tree to
prove that the actual rendered mode-switch/async regressions fail before fixes.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from gpt_windows_connector import server


def run_dashboard_js(body: str, language: str = "en", *, real_boot=False, real_refresh=False):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for rendered dashboard auth regressions")
    html = server.webapp._dashboard_html()
    # Include the real API, mode-switch and registration functions, as well as
    # all login declarations/functions. Do not reimplement the function at issue.
    runtime = html[html.index("async function api("):html.index("async function logout(")]
    if real_boot:
        runtime += html[html.index("async function boot("):html.index("async function refresh(")]
    if real_refresh:
        runtime += html[html.index("async function refresh("):html.index("function updateNodeMetrics(")]
    i18n = html[html.index("const WEB_ZH="):html.index("function localizeWeb(")]
    ids = re.findall(r'\bid="([^"]+)"', html)
    script = r'''
const assert = require('node:assert/strict');
const elements = new Map();
function element(id) {
  const classes = new Set(['hidden']);
  const e = {id, value:'', textContent:'', disabled:false, checked:false, type:'password',
    focus(){ focused.push(id) }, setAttribute(){},
    classList:{add(x){classes.add(x)}, remove(x){classes.delete(x)},
      contains(x){return classes.has(x)}, toggle(x,v){if(v===undefined)v=!classes.has(x);v?classes.add(x):classes.delete(x)}}};
  elements.set(id,e);globalThis[id]=e;return e;
}
''' + "\n".join(f"element({json.dumps(id)});" for id in ids) + r'''
const focused=[],requests=[],intervals=new Map(),timeouts=[];
const submitButton=element('testLoginSubmit'),verifyButton=element('testLoginVerify');
const registerButton=element('testRegisterSubmit'),registrationVerifyButton=element('testRegistrationVerify'),turnstileInput=element('testTurnstileResponse');
const document={getElementById:id=>elements.get(id)||null,
  querySelector:selector=>selector.includes('loginForm')?submitButton:selector.includes('loginVerifyForm')?verifyButton:selector.includes('registerForm')?registerButton:selector.includes('verifyForm')?registrationVerifyButton:selector==='[name="cf-turnstile-response"]'?turnstileInput:null};
const window=globalThis,location={search:''},state={user:null},stopRealtime=()=>{};
const stored=new Map(),localStorage={setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)};
const navigator={};
let bootCount=0;
async function boot(){bootCount++}
let routes=0,realtime=0,onboarding=0;
async function refresh(){}
function routeFromLocation(){routes++}
function startRealtime(){realtime++}
function maybeStartOnboarding(){onboarding++}
function setInterval(f){const id=intervals.size+1;intervals.set(id,f);return id}
function clearInterval(id){intervals.delete(id)}
function setTimeout(f){timeouts.push(f);return timeouts.length}
function fetch(url,options){return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))}
function response(index,data,status=200){requests[index].resolve({status,ok:status>=200&&status<300,json:async()=>data})}
async function settle(){for(let i=0;i<12;i++)await Promise.resolve()}
function visible(id){return !elements.get(id).classList.contains('hidden')}
function assertMode(mode){for(const id of ['loginForm','loginVerifyForm','registerForm','verifyForm'])assert.equal(visible(id),id===mode,id)}
function expireCooldown(){loginResendCooldownUntil=0;renderLoginResendButton()}
function assertReset(){
  assert.equal(pendingLoginChallenge,'');assert.equal(loginVerifyCode.value,'');
  assert.equal(loginVerifyEmailLabel.textContent,'');
  assert.equal(loginResendCooldownTimer,null);assert.equal(loginResendCooldownUntil,0);
  assert.equal(loginResendBusy,false);assert.equal(intervals.size,0);
  assert.equal(submitButton.disabled,false);assert.equal(verifyButton.disabled,false);
}
async function beginChallenge(id='challenge-one'){
  const index=requests.length,p=login();response(index,{verification_required:true,challenge_id:id,email:'synthetic@example.test'},202);await p;
  assertMode('loginVerifyForm');return id;
}
''' + f"const WEB_LANG={json.dumps(language)};\n" + i18n + runtime + r'''
(async()=>{
loginEmail.value='synthetic@example.test';loginPassword.value='synthetic-password';loginRemember.checked=false;
showAuth();
''' + body + r'''
console.log('dashboard-auth-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    if real_boot:
        script = script.replace("async function boot(){bootCount++}\n", "")
    if real_refresh:
        script = script.replace("async function refresh(){}\n", "")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'dashboard-auth-complete' in result.stdout, 'Runtime did not finish; an unexpected duplicate request may still be pending'


@pytest.mark.parametrize("register", [True, False], ids=["signup", "signin"])
def test_mode_switch_clears_pending_login_and_preserves_signup_copy(register):
    run_dashboard_js("""
await beginChallenge();loginVerifyCode.value='123456';
showRegister(%s);assertMode(%s);assertReset();
assert.equal(authTitle.textContent,%s);
assert.equal(authGuideTitle.textContent,%s);
assert.equal(document.getElementById('authError').textContent,'');
""" % (str(register).lower(), json.dumps("registerForm" if register else "loginForm"),
           json.dumps("Start using Lucas for free" if register else "Welcome back"),
           json.dumps("From account to action in minutes." if register else "Your AI and computers, ready when you are.")))


def test_back_clears_state_and_next_login_has_fresh_challenge():
    run_dashboard_js("""
await beginChallenge();loginVerifyCode.value='123456';cancelLoginVerification();
assertMode('loginForm');assertReset();
await beginChallenge('fresh-challenge');assert.equal(pendingLoginChallenge,'fresh-challenge');
assert.equal(loginVerifyCode.value,'');assert.equal(intervals.size,1);
""")


@pytest.mark.parametrize("status", [202, 401, 503])
def test_login_response_after_switch_cannot_change_mode_or_show_error(status):
    run_dashboard_js(f"""
const pending=login();showRegister(true);
response(0,{{verification_required:true,challenge_id:'stale',email:'stale@example.test',error:'stale error'}},{status});
await pending;assertMode('registerForm');assertReset();
assert.equal(document.getElementById('authError').textContent,'');assert.equal(bootCount,0);assert.equal(stored.size,0);
timeouts.forEach(f=>f());assert.deepEqual(focused,[]);
""")


def test_late_password_success_cannot_boot_or_remember_credentials():
    run_dashboard_js("""
loginRemember.checked=true;const pending=login();showRegister(true);response(0,{});
await pending;assertMode('registerForm');assertReset();assert.equal(bootCount,0);assert.equal(stored.size,0);
""")


def test_older_login_cannot_unlock_a_new_inflight_submission():
    run_dashboard_js("""
const old=login();showRegister(true);showRegister(false);const fresh=login();
response(0,{error:'old failure'},503);await old;
await login();assert.equal(requests.length,2);assert.equal(submitButton.disabled,true);assert.equal(document.getElementById('authError').textContent,'');
response(1,{verification_required:true,challenge_id:'fresh',email:'synthetic@example.test'},202);await fresh;
assert.equal(pendingLoginChallenge,'fresh');assertMode('loginVerifyForm');
""")


@pytest.mark.parametrize("action", ["showRegister(true)", "cancelLoginVerification()"])
@pytest.mark.parametrize("status", [200, 401, 503])
def test_stale_resend_cannot_restart_cooldown_or_show_error(action, status):
    run_dashboard_js(f"""
await beginChallenge();expireCooldown();const pending=resendLoginVerification();
{action};response(1,{{error:'stale resend error'}},{status});await pending;
assertMode({'"registerForm"' if action.startswith('showRegister') else '"loginForm"'});assertReset();
assert.equal(document.getElementById('authError').textContent,'');assert.equal(document.getElementById('toast').textContent,'');
""")


@pytest.mark.parametrize("status", [200, 401, 400])
def test_stale_verify_cannot_boot_or_overwrite_new_mode(status):
    run_dashboard_js(f"""
await beginChallenge();loginVerifyCode.value='123456';loginRemember.checked=true;
const pending=verifyLogin();showRegister(true);response(1,{{error:'stale verify error'}},{status});await pending;
assertMode('registerForm');assertReset();assert.equal(document.getElementById('authError').textContent,'');
assert.equal(bootCount,0);assert.equal(stored.size,0);
""")


def test_repeated_login_verify_resend_and_cross_actions_send_once():
    run_dashboard_js("""
const loginPending=login();await login();assert.equal(requests.length,1);assert.equal(submitButton.disabled,true);
response(0,{verification_required:true,challenge_id:'one',email:'synthetic@example.test'},202);await loginPending;
await login();assert.equal(requests.length,1);
expireCooldown();const resendPending=resendLoginVerification();await resendLoginVerification();await verifyLogin();
assert.equal(requests.length,2);response(1,{});await resendPending;
assert.equal(loginResendBusy,false);assert.equal(loginResendBtn.disabled,true);
expireCooldown();loginVerifyCode.value='123456';const verifyPending=verifyLogin();await verifyLogin();await resendLoginVerification();
assert.equal(requests.length,3);assert.equal(verifyButton.disabled,true);response(2,{});await verifyPending;
assert.equal(bootCount,1);assertReset();
await verifyLogin();await resendLoginVerification();assert.equal(requests.length,3);
""")


@pytest.mark.parametrize("language", ["en", "zh"])
def test_current_errors_remain_retryable_and_resend_keeps_localized_labels(language):
    run_dashboard_js("""
const first=login();response(0,{error:'Invalid email or password'},401);await first;
assertMode('loginForm');assert.equal(submitButton.disabled,false);
assert.equal(document.getElementById('authError').textContent,WEB_LANG==='zh'?'邮箱或密码错误':'Invalid email or password');
await beginChallenge();assert.match(loginResendBtn.textContent,WEB_LANG==='zh'?/重新发送/:/Resend/);
loginVerifyCode.value='111111';const bad=verifyLogin();response(2,{error:'Invalid verification code'},400);await bad;
assertMode('loginVerifyForm');assert.equal(verifyButton.disabled,false);
assert.equal(document.getElementById('authError').textContent,WEB_LANG==='zh'?'验证码错误':'Invalid verification code');
expireCooldown();const retry=resendLoginVerification();response(3,{error:'Try later'},429);await retry;
assert.equal(loginResendBusy,false);assert.equal(loginResendBtn.disabled,false);assert.equal(document.getElementById('authError').textContent,'Try later');
""", language)


@pytest.mark.parametrize("switch_mode", [False, True], ids=["stay-signin", "new-attempt"])
def test_password_success_stays_locked_until_dashboard_boot_completes(switch_mode):
    run_dashboard_js("""
let finishBoot;boot=()=>new Promise(resolve=>{bootCount++;finishBoot=resolve});
const first=login();response(0,{});await settle();
await login();assert.equal(requests.length,1);assert.equal(submitButton.disabled,true);
""" + ("""
showRegister(true);showRegister(false);const next=login();assert.equal(requests.length,2);
finishBoot();await first;assert.equal(submitButton.disabled,true);
response(1,{verification_required:true,challenge_id:'next',email:'synthetic@example.test'},202);await next;
assertMode('loginVerifyForm');assert.equal(pendingLoginChallenge,'next');
""" if switch_mode else """
finishBoot();await first;assert.equal(submitButton.disabled,false);assert.equal(bootCount,1);
"""))


@pytest.mark.parametrize("status", [200, 401, 503])
def test_actual_boot_ignores_auth_me_after_newer_auth_mode(status):
    run_dashboard_js(f"""
const pending=login();response(0,{{}});await settle();assert.equal(requests[1].url,'/auth/me');
showRegister(true);response(1,{{user:{{email:'synthetic@example.test',role:'user',provider:'email'}},error:'late me error'}},{status});
await pending;assertMode('registerForm');assertReset();assert.equal(state.user,null);
assert.equal(visible('app'),false);assert.equal(visible('auth'),true);
assert.equal(routes,0);assert.equal(realtime,0);assert.equal(onboarding,0);
""", real_boot=True)


@pytest.mark.parametrize("status", [200, 401, 503])
def test_actual_boot_refresh_cannot_mutate_a_new_auth_mode(status):
    run_dashboard_js(f"""
const pending=login();response(0,{{}});await settle();
response(1,{{user:{{email:'synthetic@example.test',role:'user',provider:'email'}}}});await settle();
assert.equal(requests.length,5);assert.equal(visible('app'),true);
location.search='?signup=1';showAuth();
response(2,{{nodes:[],error:'late refresh error'}},{status});response(3,{{logs:[]}});response(4,{{clients:[]}});
await pending;assertMode('registerForm');assertReset();assert.equal(state.user,null);
assert.equal(state.nodes,undefined);assert.equal(visible('app'),false);assert.equal(visible('auth'),true);
assert.equal(routes,0);assert.equal(realtime,0);assert.equal(onboarding,0);
assert.equal(document.getElementById('toast').textContent,'');
""", real_boot=True, real_refresh=True)


def test_actual_boot_current_login_still_opens_dashboard():
    run_dashboard_js("""
const pending=login();response(0,{});await settle();
response(1,{user:{email:'synthetic@example.test',role:'user',provider:'email'}});await pending;
assert.equal(visible('app'),true);assert.equal(visible('auth'),false);assertReset();
assert.equal(routes,1);assert.equal(realtime,1);assert.equal(onboarding,1);
""", real_boot=True)


def test_unrelated_api_unauthorized_response_retains_auth_navigation():
    run_dashboard_js("""
await beginChallenge();location.search='?signup=1';
const pending=api('/api/nodes');response(1,{error:'authentication_required'},401);
await assert.rejects(pending,/authentication_required/);assertMode('registerForm');assertReset();
assert.equal(state.user,null);assert.equal(visible('app'),false);assert.equal(visible('auth'),true);
""")


@pytest.mark.parametrize("status", [200, 401])
def test_initial_page_boot_cannot_override_later_signup_choice(status):
    run_dashboard_js(f"""
const pending=boot();showRegister(true);
response(0,{{user:{{email:'synthetic@example.test',role:'user',provider:'email'}},error:'late initial auth'}},{status});
await pending;assertMode('registerForm');assertReset();assert.equal(state.user,null);
assert.equal(visible('app'),false);assert.equal(visible('auth'),true);
assert.equal(routes,0);assert.equal(realtime,0);
""", real_boot=True)


def test_current_auth_failure_returns_to_login():
    run_dashboard_js("""
const pending=boot();response(0,{error:'authentication_required'},401);await pending;
assertMode('loginForm');assertReset();assert.equal(state.user,null);
assert.equal(visible('app'),false);assert.equal(visible('auth'),true);
""", real_boot=True)


def test_current_refresh_failure_keeps_authenticated_dashboard():
    run_dashboard_js("""
const pending=boot();response(0,{user:{email:'synthetic@example.test',role:'user',provider:'email'}});await settle();
response(1,{error:'temporary nodes failure'},503);response(2,{logs:[]});response(3,{clients:[]});await pending;
assert.equal(visible('app'),true);assert.equal(visible('auth'),false);
assert.equal(state.user.email,'synthetic@example.test');
assert.match(document.getElementById('toast').textContent,/Some dashboard data failed/);
assert.equal(routes,1);assert.equal(realtime,1);assert.equal(onboarding,1);
""", real_boot=True, real_refresh=True)
