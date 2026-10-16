"""Exercise registration mode and async guards in the actual rendered runtime.

DOM and HTTP are controlled; no email, device or browser actions are performed.
"""
import pytest
from test_dashboard_auth_modes import run_dashboard_js as _run_dashboard_js


def run_dashboard_js(body, language="en", **kwargs):
    _run_dashboard_js(HELPERS + body, language, **kwargs)


HELPERS = r'''
function assertRegistrationReset(){
  assert.equal(pendingVerificationEmail,'');assert.equal(pendingRegistrationMetaEventId,'');
  assert.equal(verifyCode.value,'');assert.equal(verifyEmailLabel.textContent,'');
  assert.equal(resendCooldownTimer,null);assert.equal(resendCooldownUntil,0);
  assert.equal(registrationBusy,false);assert.equal(registrationVerifyBusy,false);assert.equal(resendVerificationBusy,false);
  assert.equal(registerButton.disabled,false);assert.equal(registrationVerifyButton.disabled,false);assert.equal(resendVerificationBtn.disabled,true);
  assert.equal(resendVerificationBtn.classList.contains('disabled-btn'),true);
}
async function beginRegistration(email='synthetic@example.test'){
  showRegister(true);regEmail.value=email;const index=requests.length,p=registerUser();
  response(index,{verification_required:true,email},202);await p;assertMode('verifyForm');
  return JSON.parse(requests[index].options.body).meta_event_id;
}
function expireRegistrationCooldown(){resendCooldownUntil=0;renderResendVerificationButton()}
function mockDashboardRender(){
  globalThis.renderNodes=()=>{};globalThis.renderRecent=()=>{};globalThis.renderAiClients=()=>{};
  globalThis.updateNodeMetrics=()=>{};globalThis.renderOperationUsage=()=>{};
}
'''

BEGIN = """
showRegister(true);regEmail.value='old@example.test';
const registration=registerUser();
response(0,{verification_required:true,email:'old@example.test'},202);await registration;
"""


def test_duplicate_registration_sends_once():
    run_dashboard_js("""
showRegister(true);const a=registerUser(),b=registerUser();
assert.equal(requests.length,1);
response(0,{error:'synthetic failure'},400);await Promise.all([a,b]);
""")


def test_duplicate_email_verification_sends_once():
    run_dashboard_js(BEGIN + """
verifyCode.value='123456';const a=verifyEmail(),b=verifyEmail();
assert.equal(requests.length,2);
response(1,{error:'synthetic failure'},400);await Promise.all([a,b]);
""")


@pytest.mark.parametrize('first,second', [('verifyEmail','resendVerification'), ('resendVerification','verifyEmail')])
def test_verification_and_resend_are_mutually_exclusive(first, second):
    run_dashboard_js(BEGIN + f"""
resendCooldownUntil=0;verifyCode.value='123456';const a={first}(),b={second}();
assert.equal(requests.length,2);
response(1,{{error:'synthetic failure'}},400);await Promise.all([a,b]);
""")


def test_late_registration_challenge_does_not_reopen_verification():
    run_dashboard_js("""
showRegister(true);const p=registerUser();showRegister(false);
response(0,{verification_required:true,email:'old@example.test'},202);await p;
assertMode('loginForm');assert.equal(pendingVerificationEmail,'');assert.equal(intervals.size,0);
""")


def test_late_direct_registration_success_cannot_start_actual_boot():
    run_dashboard_js("""
const tracked=[];window.lucasMetaTrack=(...args)=>tracked.push(args);
showRegister(true);const p=registerUser();showRegister(false);
response(0,{user:{email:'old@example.test'}},201);await settle();
assert.equal(requests.length,1);await p;assertMode('loginForm');
assert.equal(visible('app'),false);assert.equal(state.user,null);assert.equal(tracked.length,0);
""", real_boot=True)


def test_late_verification_success_cannot_start_actual_boot():
    run_dashboard_js(BEGIN + """
const tracked=[];window.lucasMetaTrack=(...args)=>tracked.push(args);
verifyCode.value='123456';const p=verifyEmail();showRegister(false);
response(1,{});await settle();assert.equal(requests.length,2);await p;
assertMode('loginForm');assert.equal(visible('app'),false);assert.equal(state.user,null);assert.equal(tracked.length,0);
""", real_boot=True)


@pytest.mark.parametrize('status', [400,503])
def test_late_registration_error_cannot_change_error_or_reset_turnstile(status):
    run_dashboard_js(f"""
let resets=0;window.turnstile={{reset(){{resets++}}}};
showRegister(true);const p=registerUser();showRegister(false);
response(0,{{error:'old registration failure'}},{status});await p;
assertMode('loginForm');assert.equal(document.getElementById('authError').textContent,'');assert.equal(resets,0);
""")


def test_late_resend_success_cannot_restart_cooldown_or_toast():
    run_dashboard_js(BEGIN + """
resendCooldownUntil=0;const p=resendVerification();showRegister(false);response(1,{});await p;
assertMode('loginForm');assert.equal(document.getElementById('toast').textContent,'');
assert.equal(pendingVerificationEmail,'');assert.equal(intervals.size,0);assert.equal(resendCooldownUntil,0);
""")


@pytest.mark.parametrize('status', [400,503])
def test_late_resend_error_cannot_change_current_error(status):
    run_dashboard_js(BEGIN + f"""
resendCooldownUntil=0;const p=resendVerification();showRegister(false);
response(1,{{error:'old resend failure'}},{status});await p;
assertMode('loginForm');assert.equal(document.getElementById('authError').textContent,'');
""")


def test_mode_reset_clears_registration_target_code_metadata_and_cooldown():
    run_dashboard_js(BEGIN + """
verifyCode.value='123456';showRegister(false);
assert.equal(verifyCode.value,'');assert.equal(pendingVerificationEmail,'');assert.equal(verifyEmailLabel.textContent,'');
assert.equal(pendingRegistrationMetaEventId,'');assert.equal(intervals.size,0);assert.equal(resendCooldownUntil,0);
""")


def test_late_registration_401_cannot_cancel_new_login_challenge():
    # The handlers currently return 400/429/503 errors, not 401. This is a
    # robustness guard for API navigation behavior, not a normal-handler claim.
    run_dashboard_js("""
showRegister(true);const r=registerUser();showRegister(false);
const l=login();response(1,{verification_required:true,challenge_id:'fresh',email:'fresh@example.test'},202);await l;
response(0,{error:'stale unauthorized'},401);await r;
assertMode('loginVerifyForm');assert.equal(pendingLoginChallenge,'fresh');assert.equal(document.getElementById('authError').textContent,'');
""")


def test_old_registration_cannot_replace_new_target_or_metadata():
    run_dashboard_js("""
showRegister(true);regEmail.value='old@example.test';const old=registerUser();
showRegister(false);showRegister(true);regEmail.value='new@example.test';const fresh=registerUser();
const freshMeta=JSON.parse(requests[1].options.body).meta_event_id;
response(1,{verification_required:true,email:'new@example.test'},202);await fresh;
response(0,{verification_required:true,email:'old@example.test'},202);await old;
assert.equal(pendingVerificationEmail,'new@example.test');assert.equal(pendingRegistrationMetaEventId,freshMeta);
""")


def test_current_resend_duplicate_remains_blocked_control():
    run_dashboard_js(BEGIN + """
resendCooldownUntil=0;const p=resendVerification();await resendVerification();assert.equal(requests.length,2);
response(1,{});await p;
""")


@pytest.mark.parametrize('register_mode', [False, True], ids=['signin', 'signup'])
@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail', 'resendVerification'])
def test_mode_switch_clears_all_registration_state_during_pending_action(register_mode, action):
    begin = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();expireRegistrationCooldown();"
    run_dashboard_js(begin + f"""
const index=requests.length,p={action}();verifyCode.value='123456';showRegister({str(register_mode).lower()});
assertMode({'"registerForm"' if register_mode else '"loginForm"'});assertRegistrationReset();assert.equal(intervals.size,0);
response(index,{{error:'late error'}},503);await p;assertRegistrationReset();assert.equal(intervals.size,0);
assert.equal(document.getElementById('authError').textContent,'');
""")


def test_hidden_or_targetless_registration_actions_do_not_send_requests():
    run_dashboard_js("""
await registerUser();await verifyEmail();await resendVerification();assert.equal(requests.length,0);
showRegister(true);await verifyEmail();await resendVerification();assert.equal(requests.length,0);
auth.classList.add('hidden');await registerUser();assert.equal(requests.length,0);auth.classList.remove('hidden');
await beginRegistration();expireRegistrationCooldown();auth.classList.add('hidden');
await registerUser();await verifyEmail();await resendVerification();assert.equal(requests.length,1);
""")


def test_registration_payload_and_metadata_are_snapshotted_without_changing_backend_rules():
    run_dashboard_js("""
showRegister(true);regName.value=' Synthetic Name ';regEmail.value='Mixed.Case@example.test';
regPassword.value=' Exact password 123! ';regWebsite.value='honeypot-value';turnstileInput.value='synthetic-turnstile-token';
const p=registerUser(),payload=JSON.parse(requests[0].options.body),metaId=payload.meta_event_id;
assert.equal(requests[0].url,'/auth/register');assert.equal(requests[0].options.method,'POST');
assert.equal(requests[0].options.credentials,'include');
assert.deepEqual(payload,{name:' Synthetic Name ',email:'Mixed.Case@example.test',password:' Exact password 123! ',website:'honeypot-value',turnstile_token:'synthetic-turnstile-token',meta_event_id:metaId});
regEmail.value='edited@example.test';regPassword.value='changed';turnstileInput.value='changed';
verifyCode.value='stale-code';response(0,{verification_required:true,email:'mixed.case@example.test'},202);await p;
assert.equal(pendingVerificationEmail,'mixed.case@example.test');assert.equal(verifyEmailLabel.textContent,'mixed.case@example.test');
assert.equal(pendingRegistrationMetaEventId,metaId);assert.equal(verifyCode.value,'');assert.equal(registrationBusy,false);
verifyCode.value='123456';const v=verifyEmail();verifyCode.value='654321';
assert.deepEqual(JSON.parse(requests[1].options.body),{email:'mixed.case@example.test',code:'123456',meta_event_id:metaId});
response(1,{error:'Invalid verification code'},400);await v;
expireRegistrationCooldown();const r=resendVerification();assert.deepEqual(JSON.parse(requests[2].options.body),{email:'mixed.case@example.test'});
response(2,{});await r;assert.equal(pendingRegistrationMetaEventId,metaId);
""")


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_current_errors_are_localized_retryable_and_turnstile_resets_only_registration(language):
    run_dashboard_js("""
let resets=0;window.turnstile={reset(){resets++}};showRegister(true);
const first=registerUser(),firstMeta=JSON.parse(requests[0].options.body).meta_event_id;
response(0,{error:'Email is already registered'},400);await first;
assertMode('registerForm');assert.equal(registerButton.disabled,false);assert.equal(registrationBusy,false);assert.equal(resets,1);
assert.equal(document.getElementById('authError').textContent,WEB_LANG==='zh'?'该邮箱已注册':'Email is already registered');
const retry=registerUser();assert.equal(document.getElementById('authError').textContent,'');
const metaId=JSON.parse(requests[1].options.body).meta_event_id;assert.notEqual(metaId,firstMeta);
response(1,{verification_required:true,email:'synthetic@example.test'},202);await retry;
assertMode('verifyForm');assert.equal(pendingRegistrationMetaEventId,metaId);
verifyCode.value='111111';const bad=verifyEmail();response(2,{error:'Invalid verification code'},400);await bad;
assert.equal(registrationVerifyButton.disabled,false);assert.equal(registrationVerifyBusy,false);assert.equal(resets,1);
assert.equal(document.getElementById('authError').textContent,WEB_LANG==='zh'?'验证码错误':'Invalid verification code');
expireRegistrationCooldown();const resend=resendVerification();
assert.equal(document.getElementById('authError').textContent,'');assert.equal(registrationVerifyButton.disabled,true);
assert.equal(resendVerificationBtn.textContent,WEB_LANG==='zh'?'发送中…':'Sending…');
response(3,{error:'Try later'},429);await resend;
assert.equal(resendVerificationBusy,false);assert.equal(resendVerificationBtn.disabled,false);assert.equal(registrationVerifyButton.disabled,false);
assert.equal(document.getElementById('authError').textContent,'Try later');assert.equal(resets,1);
const verify=verifyEmail();assert.equal(document.getElementById('authError').textContent,'');response(4,{});await verify;
assert.equal(bootCount,1);assertRegistrationReset();assert.equal(intervals.size,0);
""", language)


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_registration_resend_preserves_localized_sixty_second_cooldown(language):
    run_dashboard_js("""
let now=1000000;Date.now=()=>now;await beginRegistration();
assert.equal(resendCooldownUntil,now+60000);assert.equal(intervals.size,1);assert.equal(resendVerificationBtn.disabled,true);
assert.equal(resendVerificationBtn.textContent,WEB_LANG==='zh'?'重新发送 (60秒)':'Resend code (60s)');
await resendVerification();assert.equal(requests.length,1);
now+=59999;[...intervals.values()].forEach(f=>f());assert.equal(resendVerificationBtn.disabled,true);
assert.equal(resendVerificationBtn.textContent,WEB_LANG==='zh'?'重新发送 (1秒)':'Resend code (1s)');
now++;[...intervals.values()].forEach(f=>f());assert.equal(resendVerificationBtn.disabled,false);
assert.equal(resendCooldownTimer,null);assert.equal(intervals.size,0);
const pending=resendVerification();await resendVerification();await verifyEmail();assert.equal(requests.length,2);
assert.equal(registrationVerifyButton.disabled,true);response(1,{});await pending;
assert.equal(document.getElementById('toast').textContent,WEB_LANG==='zh'?'验证码已重新发送':'Verification code resent');
assert.equal(resendCooldownUntil,now+60000);assert.equal(intervals.size,1);assert.equal(resendVerificationBtn.disabled,true);
assert.equal(registrationVerifyButton.disabled,false);showRegister(false);assertRegistrationReset();assert.equal(intervals.size,0);
""", language)


@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail', 'resendVerification'])
@pytest.mark.parametrize('status', [200, 400, 503])
def test_stale_finally_cannot_unlock_a_new_registration_operation(action, status):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();expireRegistrationCooldown();"
    busy = {'registerUser':'registrationBusy', 'verifyEmail':'registrationVerifyBusy', 'resendVerification':'resendVerificationBusy'}[action]
    button = {'registerUser':'registerButton', 'verifyEmail':'registrationVerifyButton', 'resendVerification':'resendVerificationBtn'}[action]
    run_dashboard_js(setup + f"""
const oldIndex=requests.length,old={action}();showRegister(false);
{setup}
const freshIndex=requests.length,fresh={action}(),freshMeta=pendingRegistrationMetaEventId;
response(oldIndex,{{error:'old error'}},{status});await old;
assert.equal({busy},true);assert.equal({button}.disabled,true);assert.equal(pendingRegistrationMetaEventId,freshMeta);
const count=requests.length;await {action}();assert.equal(requests.length,count);
assert.equal(document.getElementById('authError').textContent,'');assert.equal(document.getElementById('toast').textContent,'');
response(freshIndex,{{error:'current error'}},400);await fresh;assert.equal({busy},false);
assert.equal(document.getElementById('authError').textContent,'current error');
""")


@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail'])
@pytest.mark.parametrize('switch_mode', [False, True], ids=['current', 'newer-attempt'])
def test_registration_success_stays_locked_through_boot_and_stale_finally(action, switch_mode):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();expireRegistrationCooldown();"
    busy = 'registrationBusy' if action == 'registerUser' else 'registrationVerifyBusy'
    button = 'registerButton' if action == 'registerUser' else 'registrationVerifyButton'
    run_dashboard_js(setup + f"""
let finishBoot;boot=()=>new Promise(resolve=>{{bootCount++;finishBoot=resolve}});
const oldIndex=requests.length,old={action}();response(oldIndex,{{}});await settle();
const count=requests.length;await {action}();await resendVerification();assert.equal(requests.length,count);
assert.equal({busy},true);assert.equal({button}.disabled,true);
""" + (f"""
showRegister(false);{setup}
const freshIndex=requests.length,fresh={action}(),freshMeta=pendingRegistrationMetaEventId;
finishBoot();await old;assert.equal({busy},true);assert.equal({button}.disabled,true);assert.equal(pendingRegistrationMetaEventId,freshMeta);
response(freshIndex,{{error:'fresh error'}},400);await fresh;assert.equal({busy},false);
""" if switch_mode else """
finishBoot();await old;assert.equal(bootCount,1);assertRegistrationReset();assert.equal(intervals.size,0);
"""))


@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail'])
@pytest.mark.parametrize('status', [200, 401, 503])
def test_registration_actual_boot_ignores_stale_auth_me(action, status):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();"
    run_dashboard_js(setup + f"""
const index=requests.length,pending={action}();response(index,{{}});await settle();assert.equal(requests[index+1].url,'/auth/me');
showRegister(false);response(index+1,{{user:{{email:'old@example.test',role:'user',provider:'email'}},error:'late me error'}},{status});await pending;
assertMode('loginForm');assertRegistrationReset();assert.equal(state.user,null);assert.equal(visible('app'),false);assert.equal(visible('auth'),true);
assert.equal(routes,0);assert.equal(realtime,0);assert.equal(onboarding,0);assert.equal(document.getElementById('authError').textContent,'');
""", real_boot=True)


@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail'])
@pytest.mark.parametrize('status', [200, 401, 503])
def test_registration_actual_boot_refresh_cannot_mutate_a_new_auth_mode(action, status):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();"
    run_dashboard_js(setup + f"""
const index=requests.length,pending={action}();response(index,{{}});await settle();
response(index+1,{{user:{{email:'old@example.test',role:'user',provider:'email'}}}});await settle();
assert.equal(requests.length,index+5);assert.equal(visible('app'),true);
showAuth();response(index+2,{{nodes:[],error:'late refresh error'}},{status});response(index+3,{{logs:[]}});response(index+4,{{clients:[]}});await pending;
assertMode('loginForm');assertRegistrationReset();assert.equal(state.user,null);assert.deepEqual(state.nodes,[]);assert.deepEqual(state.aiClients,[]);assert.equal(state.billing,null);
assert.equal(visible('app'),false);assert.equal(visible('auth'),true);assert.equal(routes,0);assert.equal(realtime,0);assert.equal(onboarding,0);
assert.equal(document.getElementById('toast').textContent,'');assert.equal(document.getElementById('authError').textContent,'');
""", real_boot=True, real_refresh=True)


@pytest.mark.parametrize('action,status', [('registerUser','completed'), ('verifyEmail','verified')])
def test_current_registration_completes_actual_boot_refresh_and_tracks_once(action, status):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();"
    busy = 'registrationBusy' if action == 'registerUser' else 'registrationVerifyBusy'
    run_dashboard_js(setup + f"""
mockDashboardRender();const tracked=[];window.lucasMetaTrack=(...args)=>tracked.push(args);
const index=requests.length,pending={action}(),metaId=pendingRegistrationMetaEventId;response(index,{{}});await settle();
assert.equal({busy},true);response(index+1,{{user:{{email:'current@example.test',role:'user',provider:'email'}}}});await settle();
assert.equal({busy},true);assert.equal(visible('app'),true);assert.equal(visible('auth'),false);
const count=requests.length;await registerUser();await verifyEmail();await resendVerification();assert.equal(requests.length,count);
response(index+2,{{nodes:[]}});response(index+3,{{logs:[]}});response(index+4,{{clients:[]}});await pending;
assertRegistrationReset();assert.equal(intervals.size,0);assert.equal(state.user.email,'current@example.test');assert.deepEqual(state.nodes,[]);
assert.equal(routes,1);assert.equal(realtime,1);assert.equal(onboarding,1);
assert.deepEqual(tracked,[['CompleteRegistration',{{content_name:'Email Registration',status:'{status}'}},metaId]]);
await registerUser();await verifyEmail();await resendVerification();assert.equal(requests.length,count);
""", real_boot=True, real_refresh=True)


def test_obsolete_cooldown_callback_cannot_clear_or_render_a_new_timer():
    run_dashboard_js("""
await beginRegistration('old@example.test');const oldTick=[...intervals.values()][0];
showRegister(false);await beginRegistration('fresh@example.test');const freshTimer=resendCooldownTimer;
resendCooldownUntil=0;resendVerificationBtn.textContent='current button';oldTick();
assert.equal(resendVerificationBtn.textContent,'current button');assert.equal(resendCooldownTimer,freshTimer);assert.equal(intervals.size,1);
""")


@pytest.mark.parametrize('action', ['verifyEmail', 'resendVerification'])
@pytest.mark.parametrize('status', [200, 400, 401, 503])
def test_obsolete_verification_request_cannot_cancel_new_login_challenge(action, status):
    run_dashboard_js(f"""
await beginRegistration();expireRegistrationCooldown();const old={action}();showRegister(false);
await beginChallenge('fresh-login');response(1,{{error:'old verification error'}},{status});await old;
assertMode('loginVerifyForm');assert.equal(pendingLoginChallenge,'fresh-login');assertRegistrationReset();
assert.equal(document.getElementById('authError').textContent,'');assert.equal(document.getElementById('toast').textContent,'');assert.equal(bootCount,0);
""")


@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail', 'resendVerification'])
def test_current_network_failure_unlocks_the_same_action_for_retry(action):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();expireRegistrationCooldown();"
    busy = {'registerUser':'registrationBusy', 'verifyEmail':'registrationVerifyBusy', 'resendVerification':'resendVerificationBusy'}[action]
    run_dashboard_js(setup + f"""
const index=requests.length,first={action}();requests[index].reject(new Error('Network unavailable'));await first;
assert.equal({busy},false);assert.equal(document.getElementById('authError').textContent,'Network unavailable');
const retry={action}();assert.equal(requests.length,index+2);assert.equal({busy},true);
assert.equal(document.getElementById('authError').textContent,'');response(index+1,{{error:'Current retry error'}},400);await retry;
assert.equal({busy},false);assert.equal(document.getElementById('authError').textContent,'Current retry error');
""")


@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail'])
def test_current_registration_auth_me_failure_resets_to_signin(action):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();"
    run_dashboard_js(setup + f"""
const index=requests.length,pending={action}();response(index,{{}});await settle();
response(index+1,{{error:'authentication_required'}},401);await pending;
assertMode('loginForm');assertRegistrationReset();assert.equal(state.user,null);assert.equal(visible('app'),false);assert.equal(visible('auth'),true);
assert.equal(routes,0);assert.equal(realtime,0);assert.equal(onboarding,0);
""", real_boot=True)


@pytest.mark.parametrize('action', ['registerUser', 'verifyEmail'])
def test_current_registration_refresh_failure_keeps_dashboard_and_releases_lock(action):
    setup = "showRegister(true);" if action == 'registerUser' else "await beginRegistration();"
    run_dashboard_js(setup + f"""
const index=requests.length,pending={action}();response(index,{{}});await settle();
response(index+1,{{user:{{email:'current@example.test',role:'user',provider:'email'}}}});await settle();
response(index+2,{{error:'temporary nodes error'}},503);response(index+3,{{logs:[]}});response(index+4,{{clients:[]}});await pending;
assertRegistrationReset();assert.equal(state.user.email,'current@example.test');assert.equal(visible('app'),true);assert.equal(visible('auth'),false);
assert.equal(routes,1);assert.equal(realtime,1);assert.equal(onboarding,1);assert.match(document.getElementById('toast').textContent,/Some dashboard data failed/);
""", real_boot=True, real_refresh=True)
