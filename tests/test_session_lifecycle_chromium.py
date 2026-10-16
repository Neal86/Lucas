"""Opt-in Chromium account lifecycle batch using disposable loopback accounts.

Real login/logout/referral/auth-me handlers and cookies run unchanged. The
one-shot gate finishes native HTTP/JSON, then delays only parsed delivery.
Explicit synthetic tests cover one stale referral 401, browser event callbacks
and hint timers; they do not establish server event/device authorization.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlsplit

import pytest

from test_billing_read_chromium import REAL_SUMMARY_PAYLOAD_GATE
from test_computer_connection_chromium import signed_in_dashboard
from test_oauth_login_chromium import (
    EMAIL, PASSWORD, chromium, click, login_server, request_count, visible, wait_for,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)


async def ready(cdp, session, server, language):
    await signed_in_dashboard(cdp, session, server, language)
    await cdp.evaluate("stopRealtime();hideGettingStarted();true", session)


async def gate_payload(cdp, session, server, path, method="GET"):
    assert (path, method) in {("/auth/me", "GET"), ("/api/referrals/summary", "GET"), ("/api/logout", "POST")}
    assert urlsplit(server.base).hostname == "127.0.0.1"
    script = REAL_SUMMARY_PAYLOAD_GATE.replace("FIXTURE_ORIGIN", json.dumps(server.base))
    assert script.count("'/api/billing/summary'") == script.count("method!=='GET'") == 1
    script = script.replace("'/api/billing/summary'", json.dumps(path)).replace("method!=='GET'", "method!==" + json.dumps(method))
    script = script.replace("__billingPayloadGate", "__sessionPayloadGate")
    await cdp.evaluate(script, session)


async def payload_ready(cdp, session):
    await wait_for(cdp, session, "__sessionPayloadGate.error||(__sessionPayloadGate.ready&&__sessionPayloadGate.jsonRequested===1)")
    assert await cdp.evaluate("__sessionPayloadGate.error", session) is None
    return await cdp.evaluate("__sessionPayloadGate.payload", session)


async def finish(cdp, session, name):
    await cdp.evaluate(f"window[{json.dumps(name)}].then(()=>true)", session)


async def second_login(cdp, session, server, email):
    await cdp.evaluate(f"loginEmail.value={json.dumps(email)};loginPassword.value={json.dumps(PASSWORD)};loginRemember.checked=false;login().then(()=>true)", session)
    await wait_for(cdp, session, visible("#loginVerifyForm"))
    assert server.deliveries[-1][0] == email
    await cdp.evaluate(f"loginVerifyCode.value={json.dumps(server.deliveries[-1][1])};verifyLogin().then(()=>true)", session)
    await wait_for(cdp, session, visible("#app"))
    await cdp.evaluate("stopRealtime();hideGettingStarted();true", session)
    assert await cdp.evaluate("state.user.email", session) == email


def assert_no_device_or_reward_effects(server):
    from gpt_windows_connector import gateway
    assert gateway.registry.nodes == gateway.registry.pending_requests == {}
    with server.provider.db() as db:
        for table in ("referrals", "billing_events", "task_steps", "user_node_bindings"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert not [r for r in server.requests if r["path"].startswith("/api/nodes/")]


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_real_referral_payload_cannot_restore_previous_account_link(login_server, tmp_path, language):
    server = login_server
    email = "session-referral-second@example.test"
    second = server.provider.auth.register(email, PASSWORD)

    async def run():
        from gpt_windows_connector import gateway
        async with chromium(tmp_path) as (cdp, session):
            await ready(cdp, session, server, language)
            first_id = await cdp.evaluate("state.user.id", session)
            await click(cdp, session, '.nav[data-view="referral"]')
            await wait_for(cdp, session, "referralUrl.value!==''")
            await gate_payload(cdp, session, server, "/api/referrals/summary")
            await cdp.evaluate("window.oldReferral=loadReferralView();true", session)
            old = await payload_ready(cdp, session)
            assert old == gateway.billing.referrals.summary(first_id)
            await click(cdp, session, '.nav[data-view="nodes"]')
            await cdp.evaluate("logout().then(()=>true)", session)
            assert await cdp.evaluate("referralUrl.value", session) == ""
            await second_login(cdp, session, server, email)
            await cdp.evaluate("loadReferralView().then(()=>true)", session)
            fresh = gateway.billing.referrals.summary(second.id)
            assert old["code"] != fresh["code"]
            await cdp.evaluate("__sessionPayloadGate.release();true", session)
            await finish(cdp, session, "oldReferral")
            assert await cdp.evaluate("referralUrl.value", session) == fresh["url"]
            assert await cdp.evaluate("referralCode.textContent", session) == fresh["code"]
            assert await cdp.evaluate("state.user.id", session) == second.id
            assert await cdp.evaluate(visible("#app"), session)
            assert request_count(server, "/api/logout") == 1
    asyncio.run(run())
    assert_no_device_or_reward_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_real_bootstrap_payload_order_keeps_current_role(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready(cdp, session, server, language)
            user_id = await cdp.evaluate("state.user.id", session)
            with server.provider.db() as db:
                db.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
            await gate_payload(cdp, session, server, "/auth/me")
            await cdp.evaluate("window.oldBoot=boot();true", session)
            old = await payload_ready(cdp, session)
            assert old["user"]["role"] == "admin"
            with server.provider.db() as db:
                db.execute("UPDATE users SET role='user' WHERE id=?", (user_id,))
            await cdp.evaluate("boot().then(()=>true)", session)
            assert await cdp.evaluate("state.user.role", session) == "user"
            assert not await cdp.evaluate(visible("#adminNav"), session)
            await cdp.evaluate("__sessionPayloadGate.release();true", session)
            await finish(cdp, session, "oldBoot")
            assert await cdp.evaluate("state.user.role", session) == "user"
            assert not await cdp.evaluate(visible("#adminNav"), session)
            assert await cdp.evaluate("accountEmail.textContent", session) == EMAIL
    asyncio.run(run())
    assert_no_device_or_reward_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_real_logout_effect_precedes_new_login_and_stale_ui_completion(login_server, tmp_path, language):
    server = login_server
    email = "session-logout-second@example.test"
    second = server.provider.auth.register(email, PASSWORD)

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready(cdp, session, server, language)
            await gate_payload(cdp, session, server, "/api/logout", "POST")
            await cdp.evaluate("window.oldLogout=logout();true", session)
            assert await payload_ready(cdp, session) == {"ok": True}
            # The original response already removed the real cookie. No claim of undoing it.
            assert await cdp.evaluate("fetch('/auth/me',{credentials:'include'}).then(r=>r.status)", session) == 401
            await cdp.evaluate("showAuth();true", session)
            await second_login(cdp, session, server, email)
            await cdp.evaluate("__sessionPayloadGate.release();true", session)
            await finish(cdp, session, "oldLogout")
            assert await cdp.evaluate("state.user.id", session) == second.id
            assert await cdp.evaluate(visible("#app"), session)
            assert await cdp.evaluate("fetch('/auth/me',{credentials:'include'}).then(r=>r.json()).then(d=>d.user.id)", session) == second.id
            assert request_count(server, "/api/logout") == 1
    asyncio.run(run())
    assert_no_device_or_reward_effects(server)


SYNTHETIC_REFERRAL_401 = r'''(() => {
const origin=FIXTURE_ORIGIN,nativeFetch=window.fetch.bind(window);let armed=true;
if(location.origin!==origin)throw new Error('Wrong session fixture origin');
window.__staleReferral={ready:false,release:null};
window.fetch=(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href),method=String(options.method||(typeof input==='object'&&input.method)||'GET').toUpperCase();
 if(!armed||url.origin!==origin||url.pathname!=='/api/referrals/summary'||url.search||method!=='GET')return nativeFetch(input,options);
 armed=false;__staleReferral.ready=true;
 return new Promise(resolve=>{__staleReferral.release=()=>{resolve(new Response(JSON.stringify({error:'Synthetic stale referral session'}),{status:401,headers:{'Content-Type':'application/json'}}));__staleReferral.release=null}});
};return true;
})()'''


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_synthetic_old_referral_401_does_not_hide_real_new_login(login_server, tmp_path, language):
    server = login_server
    email = "session-401-second@example.test"
    second = server.provider.auth.register(email, PASSWORD)

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready(cdp, session, server, language)
            await cdp.evaluate(SYNTHETIC_REFERRAL_401.replace("FIXTURE_ORIGIN", json.dumps(server.base)), session)
            await cdp.evaluate("window.oldReferral401=loadReferralView();true", session)
            assert await cdp.evaluate("__staleReferral.ready", session)
            await cdp.evaluate("logout().then(()=>true)", session)
            await second_login(cdp, session, server, email)
            await cdp.evaluate("loadReferralView().then(()=>true)", session)
            fresh = await cdp.evaluate("referralUrl.value", session)
            await cdp.evaluate("__staleReferral.release();true", session)
            await finish(cdp, session, "oldReferral401")
            assert await cdp.evaluate("state.user.id", session) == second.id
            assert await cdp.evaluate("referralUrl.value", session) == fresh
            assert await cdp.evaluate("referralError.textContent", session) == ""
            assert await cdp.evaluate(visible("#app"), session)
    asyncio.run(run())
    assert_no_device_or_reward_effects(server)


SYNTHETIC_EVENT_SOCKET = r'''(() => {
const expected=EXPECTED_SOCKET,Native=window.WebSocket;
window.__sessionSockets=[];
window.WebSocket=class {
 static OPEN=1;static CONNECTING=0;readyState=0;sent=[];closed=[];
 constructor(url,...args){if(url!==expected)return new Native(url,...args);__sessionSockets.push(this)}
 close(...args){this.closed.push(args);this.readyState=3}
 send(data){this.sent.push(data)}
};return true;
})()'''


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_synthetic_retired_socket_callbacks_cannot_restore_computer_rows(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready(cdp, session, server, language)
            expected = server.base.replace("http://", "ws://") + "/ws/events"
            await cdp.evaluate(SYNTHETIC_EVENT_SOCKET.replace("EXPECTED_SOCKET", json.dumps(expected)), session)
            await cdp.evaluate("startRealtime();window.oldSocket=__sessionSockets[0];oldSocket.readyState=1;oldSocket.onopen();window.oldCallbacks={open:oldSocket.onopen,message:oldSocket.onmessage,close:oldSocket.onclose};true", session)
            await cdp.evaluate("showAuth();state.user={id:'synthetic-ui-only',email:'synthetic-ui-only@example.test',role:'user'};showApp();startRealtime();window.freshSocket=__sessionSockets[1];freshSocket.readyState=1;freshSocket.onopen();window.currentHeartbeat=eventHeartbeatTimer;true", session)
            await cdp.evaluate("oldCallbacks.open();oldCallbacks.message({data:JSON.stringify({type:'node.upsert',node:{node_id:'OLD_EVENT_ROW',authorized:true,online:true}})});oldCallbacks.close();true", session)
            assert await cdp.evaluate("state.nodes.length", session) == 0
            assert not await cdp.evaluate("nodeTable.textContent.includes('OLD_EVENT_ROW')", session)
            assert await cdp.evaluate("eventSocket===freshSocket&&eventHeartbeatTimer===currentHeartbeat", session)
            await cdp.evaluate("freshSocket.onmessage({data:JSON.stringify({type:'node.upsert',node:{node_id:'CURRENT_EVENT_ROW',authorized:true,online:true}})});true", session)
            await wait_for(cdp, session, "nodeTable.textContent.includes('CURRENT_EVENT_ROW')")
            assert await cdp.evaluate("state.nodes[0].node_id", session) == "CURRENT_EVENT_ROW"
            await cdp.evaluate("stopRealtime();true", session)
    asyncio.run(run())
    assert_no_device_or_reward_effects(server)


HINT_TIMERS = r'''(() => {
const timeout=window.setTimeout.bind(window),clear=window.clearTimeout.bind(window);let sequence=0;
window.__hintTimers=[];
window.setTimeout=(callback,delay,...args)=>{
 if(delay!==120&&delay!==9000)return timeout(callback,delay,...args);
 const item={id:--sequence,callback:()=>callback(...args),delay,cancelled:false};__hintTimers.push(item);return item.id;
};
window.clearTimeout=id=>{const item=__hintTimers.find(t=>t.id===id);if(item)item.cancelled=true;else clear(id)};
return true;
})()'''


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_synthetic_hint_timers_keep_current_localized_checklist_owner(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready(cdp, session, server, language)
            await cdp.evaluate(HINT_TIMERS, session)
            await cdp.evaluate("localStorage.removeItem('lucas-setup-checklist-hint-v1:'+state.user.email);openGettingStarted();document.getElementById('coachClose').click();window.oldShow=__hintTimers.at(-1);openGettingStarted();oldShow.callback();true", session)
            assert not await cdp.evaluate("Boolean(document.getElementById('coachReopenHint'))", session)
            assert await cdp.evaluate(visible("#lucasCoach"), session)
            await cdp.evaluate("finishOnboarding();__hintTimers.at(-1).callback();window.oldDismiss=__hintTimers.at(-1);true", session)
            await wait_for(cdp, session, visible("#coachReopenHint"))
            await cdp.evaluate("showAuth();state.user={id:'synthetic-hint-only',email:'synthetic-hint-only@example.test',role:'user'};showApp();openGettingStarted();finishOnboarding();window.newShow=__hintTimers.at(-1);oldShow.callback();true", session)
            assert await cdp.evaluate("localStorage.getItem('lucas-setup-checklist-hint-v1:synthetic-hint-only@example.test')", session) is None
            await cdp.evaluate("newShow.callback();oldDismiss.callback();true", session)
            await wait_for(cdp, session, visible("#coachReopenHint"))
            expected = "知道了" if language == "zh-CN" else "Got it"
            await wait_for(cdp, session, "document.querySelector('#coachReopenHint button').textContent===" + json.dumps(expected))
            await cdp.evaluate("__hintTimers.at(-1).callback();true", session)
            assert not await cdp.evaluate("Boolean(document.getElementById('coachReopenHint'))", session)
            assert await cdp.evaluate("localStorage.getItem('lucas-setup-checklist-hint-v1:synthetic-hint-only@example.test')", session) == "1"
    asyncio.run(run())
    assert_no_device_or_reward_effects(server)
