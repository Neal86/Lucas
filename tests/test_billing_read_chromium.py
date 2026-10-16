"""Opt-in Chromium regressions for account-owned Billing/quota reads.

The real loopback dashboard, login handlers, API client, localization and DOM
run unchanged. A one-shot fixture-origin gate finishes native HTTP and JSON
parsing, then holds delivery of that real summary payload to the API client.
Explicitly synthetic quota/error cases intercept only GET /api/billing/summary
and GET /api/nodes at that origin; all other requests retain native transport.
No Node, payment, subscription mutation or external provider is contacted.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlsplit

import pytest

from test_computer_connection_chromium import signed_in_dashboard
from test_oauth_login_chromium import (
    EMAIL, PASSWORD, chromium, click, login_server, request_count, visible,
    wait_for,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)

SUMMARY = "/api/billing/summary"
NODES = "/api/nodes"
BILLING_NAV = '.nav[data-view="billing"]'
BETA_NOTICE = "Lucas Beta is free during testing. Plans and limits may change."
OLD_NOTICE = (
    "Lucas Beta is free during testing. An existing paid subscription is on record; "
    "review it separately to avoid future charges."
)


def synthetic_summary(used, **extra):
    """Explicit transport data, never a production quota or entitlement change."""
    return {
        "plan": "free", "plan_name": "Lucas Beta", "beta_free": True,
        "billing_configured": False, "existing_paid_subscription": False,
        "billing_interval": "month", "billing_total": 0, "expansion_quantity": 0,
        "renewal_at": None, "requests_used": used, "requests_pending": 2,
        "requests_unconfirmed": 1, "request_remaining": 100000 - used - 3,
        "request_limit": 100000, "period_end": 1793491200,
        "nodes_used": 1, "nodes_connected": 1, "node_limit": 3,
        "ai_accounts_used": 2, "ai_account_limit": 3, **extra,
    }


async def ready_billing(cdp, session, server, language):
    await signed_in_dashboard(cdp, session, server, language)
    # Stop only the existing reconnect timer, not any dispatched request.
    await cdp.evaluate("stopRealtime();true", session)
    await click(cdp, session, BILLING_NAV)
    await wait_for(cdp, session, "performance.getEntriesByType('resource').some("
                   "r=>new URL(r.name).pathname==='/api/billing/summary')")
    await cdp.evaluate("loadBillingView().then(()=>true)", session)
    assert await cdp.evaluate(visible("#billing"), session)


async def complete(cdp, session, name):
    await cdp.evaluate(f"window[{json.dumps(name)}].then(()=>true)", session)


async def text_is(cdp, session, element_id, expected):
    await wait_for(cdp, session,
                   f"document.getElementById({json.dumps(element_id)}).textContent.trim()"
                   f"===wt({json.dumps(expected)})")


async def assert_snapshot(cdp, session, snapshot, language):
    assert await cdp.evaluate("state.billing", session) == snapshot
    expected = {
        "completed": snapshot["requests_used"], "pending": snapshot["requests_pending"],
        "unconfirmed": snapshot["requests_unconfirmed"],
        "remaining": snapshot["request_remaining"], "limit": snapshot["request_limit"],
    }
    await wait_for(cdp, session, "['billingRequests','metricRequests'].every(id=>"
                   "Object.entries(" + json.dumps(expected) + ").every(([key,value])=>"
                   "document.querySelector('#'+id+' [data-operation-count=\"'+key+'\"]')"
                   "?.textContent===Number(value).toLocaleString()))")
    for element_id in ("billingRequests", "metricRequests"):
        label = "已完成操作" if language == "zh-CN" else "Completed Operations"
        assert label in await cdp.evaluate(
            f"document.getElementById({json.dumps(element_id)}).textContent", session)
    if snapshot["plan"] == "free":
        await text_is(cdp, session, "billingPlan", "Lucas Beta")
        await text_is(cdp, session, "billingPrice", "$0")
        await text_is(cdp, session, "billingAi", f"{snapshot['ai_accounts_used']} / 3")
        await text_is(cdp, session, "billingComputers", f"{snapshot['nodes_used']} / 3")
        await text_is(cdp, session, "billingNotice",
                      OLD_NOTICE if snapshot["existing_paid_subscription"] else BETA_NOTICE)
        await text_is(cdp, session, "billingRenew", "")
    assert await cdp.evaluate("document.documentElement.lang", session) == language


async def assert_cleared(cdp, session):
    assert await cdp.evaluate("state.billing", session) is None
    for element_id in ("billingPlan", "billingPrice", "billingAi", "billingComputers"):
        await text_is(cdp, session, element_id, "—")
    for element_id in ("billingRenew", "billingNotice", "billingError"):
        await text_is(cdp, session, element_id, "")
    assert await cdp.evaluate("document.getElementById('billingNotice').classList.contains('hidden')&&"
                              "document.getElementById('billingError').classList.contains('hidden')", session)
    assert await cdp.evaluate("document.querySelector('#billingRequestsBar i').style.width", session) == "0%"
    for element_id in ("billingRequests", "metricRequests"):
        assert await cdp.evaluate(
            f"document.querySelector('#{element_id} [data-operation-count=completed]').textContent",
            session) == "—"


async def hold_next_real_summary_payload(cdp, session, server):
    """Hold parsed real JSON, leaving native HTTP free to serve the next GET."""
    assert urlsplit(server.base).scheme == "http"
    assert urlsplit(server.base).hostname == "127.0.0.1"
    await cdp.evaluate(REAL_SUMMARY_PAYLOAD_GATE.replace("FIXTURE_ORIGIN", json.dumps(server.base)), session)


REAL_SUMMARY_PAYLOAD_GATE = r"""(() => {
  const origin=FIXTURE_ORIGIN,nativeFetch=window.fetch.bind(window);
  if(location.origin!==origin)throw new Error('Wrong real Billing fixture origin');
  let armed=true,deliver;
  const gate=window.__billingPayloadGate={
    ready:false,released:false,jsonRequested:0,payload:null,error:null,
    release(){
      if(!gate.ready||gate.released)throw new Error('Missing or released real Billing payload');
      gate.released=true;deliver();
    }
  };
  window.fetch=async(input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    const method=String(options.method||(typeof input==='object'&&input.method)||'GET').toUpperCase();
    if(!armed||url.origin!==origin||url.pathname!=='/api/billing/summary'||url.search||method!=='GET')
      return nativeFetch(input,options);
    armed=false;
    try{
      const response=await nativeFetch(input,options);
      // Complete the actual network body before allowing a second same-URL GET.
      // Only delivery to api().json() waits; no payload/status/header is invented.
      const payload=await response.json();
      gate.payload=payload;
      const delivery=new Promise(resolve=>{deliver=()=>resolve(payload)});
      Object.defineProperty(response,'json',{value:()=>{
        gate.jsonRequested++;return delivery;
      }});
      gate.ready=true;
      return response;
    }catch(error){gate.error=String(error);throw error}
  };
  return true;
})()"""


async def intercept_synthetic_reads(cdp, session, server):
    """Fixture-origin GET shim; do not replace application/API/auth functions."""
    assert urlsplit(server.base).scheme == "http"
    assert urlsplit(server.base).hostname == "127.0.0.1"
    await cdp.evaluate(SYNTHETIC_READ_SHIM.replace("FIXTURE_ORIGIN", json.dumps(server.base)), session)


SYNTHETIC_READ_SHIM = r"""(() => {
  const origin=FIXTURE_ORIGIN,nativeFetch=window.fetch.bind(window),pending=[];
  if(location.origin!==origin)throw new Error('Wrong synthetic Billing fixture origin');
  window.__billingReads={requests:[],
    respond(index,body,status=200){
      const request=pending[index];
      if(!request||request.done)throw new Error('Missing or settled synthetic Billing read');
      request.done=true;
      request.resolve(new Response(JSON.stringify(body),{
        status,headers:{'Content-Type':'application/json'}}));
    },
    fail(index){
      const request=pending[index];
      if(!request||request.done)throw new Error('Missing or settled synthetic Billing read');
      request.done=true;request.reject(new TypeError('Synthetic Billing network error'));
    },
    allSettled(){return pending.every(request=>request.done)}
  };
  window.fetch=(input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    const method=String(options.method||(typeof input==='object'&&input.method)||'GET').toUpperCase();
    if(url.origin===origin&&!url.search&&method==='GET'&&
       ['/api/billing/summary','/api/nodes'].includes(url.pathname)){
      if(options.signal)throw new Error('Billing reads must not cancel dispatched work');
      __billingReads.requests.push({path:url.pathname,method,credentials:options.credentials});
      return new Promise((resolve,reject)=>pending.push({resolve,reject,done:false}));
    }
    return nativeFetch(input,options);
  };
  return true;
})()"""


async def begin(cdp, session, name, operation="loadBillingView()", path=SUMMARY):
    index = await cdp.evaluate("__billingReads.requests.length", session)
    await cdp.evaluate(f"window[{json.dumps(name)}]={operation};true", session)
    assert await cdp.evaluate("__billingReads.requests.length", session) == index + 1
    assert await cdp.evaluate(f"__billingReads.requests[{index}]", session) == {
        "path": path, "method": "GET", "credentials": "include",
    }
    return index


async def respond(cdp, session, index, body=None, status=200):
    if status == "network":
        await cdp.evaluate(f"__billingReads.fail({index});true", session)
    else:
        await cdp.evaluate(
            f"__billingReads.respond({index},{json.dumps(body)},{status});true", session)


async def billing_snapshot(cdp, session, snapshot):
    index = await begin(cdp, session, "billingCurrent")
    await respond(cdp, session, index, snapshot)
    await complete(cdp, session, "billingCurrent")


async def assert_all_reads_settled(cdp, session):
    assert await cdp.evaluate("__billingReads.allSettled()", session)


def assert_no_operational_effects(server):
    from gpt_windows_connector import gateway

    assert gateway.registry.nodes == gateway.registry.pending_requests == {}
    assert not [request for request in server.requests if
                request["path"].startswith("/api/billing/") and request["path"] != SUMMARY]
    assert not [request for request in server.requests if
                request["path"].startswith("/api/nodes/")]
    assert all(request["method"] == "GET" for request in server.requests
               if request["path"] in (SUMMARY, NODES))
    with server.provider.db() as db:
        assert db.execute("SELECT COUNT(*) FROM billing_events").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM task_steps").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM user_node_bindings").fetchone()[0] == 0


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_billing_real_held_summary_cannot_restore_old_subscription_warning(login_server, tmp_path, language):
    """Real HTTP/JSON payloads, with only the first parsed-payload delivery held."""
    server = login_server

    async def run():
        from gpt_windows_connector import gateway

        async with chromium(tmp_path) as (cdp, session):
            await ready_billing(cdp, session, server, language)
            user_id = await cdp.evaluate("state.user.id", session)
            # An inert subscription reference in the disposable SQLite fixture.
            with server.provider.db() as db:
                db.execute("UPDATE subscriptions SET stripe_subscription_id=? WHERE user_id=?",
                           ("sub_synthetic_read_history", user_id))
            await cdp.evaluate("loadBillingView().then(()=>true)", session)
            await text_is(cdp, session, "billingNotice", OLD_NOTICE)
            before = request_count(server, SUMMARY)
            await hold_next_real_summary_payload(cdp, session, server)
            await cdp.evaluate("window.billingOld=loadBillingView();true", session)
            await wait_for(cdp, session, "__billingPayloadGate.error||"
                           "(__billingPayloadGate.ready&&__billingPayloadGate.jsonRequested===1)")
            assert await cdp.evaluate("__billingPayloadGate.error", session) is None
            captured = await cdp.evaluate("__billingPayloadGate.payload", session)
            assert captured == gateway.billing.summary(user_id)
            assert captured["existing_paid_subscription"] is True
            assert request_count(server, SUMMARY) == before + 1
            # Change only this local fixture between two real summary reads.
            with server.provider.db() as db:
                db.execute("UPDATE subscriptions SET stripe_subscription_id=NULL WHERE user_id=?", (user_id,))
            await cdp.evaluate("loadBillingView().then(()=>true)", session)
            current = gateway.billing.summary(user_id)
            await assert_snapshot(cdp, session, current, language)
            assert not await cdp.evaluate("__billingPayloadGate.released", session)
            await cdp.evaluate("__billingPayloadGate.release();true", session)
            await complete(cdp, session, "billingOld")
            await assert_snapshot(cdp, session, current, language)
            assert request_count(server, SUMMARY) == before + 2
            assert await cdp.evaluate("document.querySelectorAll("
                                      "'#billingChoosePro,#billingChooseProPlus,#billingExpansionQty').length",
                                      session) == 0
            with server.provider.db() as db:
                assert db.execute("SELECT stripe_subscription_id FROM subscriptions WHERE user_id=?",
                                  (user_id,)).fetchone()[0] is None

    asyncio.run(run())
    assert_no_operational_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_billing_synthetic_order_errors_and_explicit_ui_retry(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready_billing(cdp, session, server, language)
            await intercept_synthetic_reads(cdp, session, server)
            baseline, old, fresh = (synthetic_summary(n) for n in (11, 22, 33))
            user_id = await cdp.evaluate("state.user.id", session)
            for newer_finishes_first in (False, True):
                await billing_snapshot(cdp, session, baseline)
                first = await begin(cdp, session, "billingOld")
                second = await begin(cdp, session, "billingNew")
                if newer_finishes_first:
                    await respond(cdp, session, second, fresh)
                    await complete(cdp, session, "billingNew")
                await respond(cdp, session, first, old)
                await complete(cdp, session, "billingOld")
                await assert_snapshot(cdp, session, fresh if newer_finishes_first else baseline, language)
                if not newer_finishes_first:
                    await respond(cdp, session, second, fresh)
                    await complete(cdp, session, "billingNew")
                await assert_snapshot(cdp, session, fresh, language)
            for status in (401, 503, "network"):
                first = await begin(cdp, session, "billingOld")
                await billing_snapshot(cdp, session, fresh)
                await respond(cdp, session, first, {"error": "Synthetic obsolete Billing error"}, status)
                await complete(cdp, session, "billingOld")
                await assert_snapshot(cdp, session, fresh, language)
                await text_is(cdp, session, "billingError", "")
                assert await cdp.evaluate("state.user.id", session) == user_id
                assert await cdp.evaluate(visible("#app"), session)
            for status in (503, "network"):
                first = await begin(cdp, session, "billingFailure")
                await respond(cdp, session, first, {"error": "Synthetic current Billing error"}, status)
                await complete(cdp, session, "billingFailure")
                await text_is(cdp, session, "billingError", "Synthetic Billing network error"
                              if status == "network" else "Synthetic current Billing error")
                assert await cdp.evaluate(visible("#billingError"), session)
                await assert_snapshot(cdp, session, fresh, language)
                # Retry by leaving and reopening Billing through its actual nav.
                await click(cdp, session, '.nav[data-view="nodes"]')
                index = await cdp.evaluate("__billingReads.requests.length", session)
                await click(cdp, session, BILLING_NAV)
                assert await cdp.evaluate("__billingReads.requests.length", session) == index + 1
                await respond(cdp, session, index, baseline)
                await wait_for(cdp, session, "state.billing?.requests_used===11")
                await assert_snapshot(cdp, session, baseline, language)
                assert not await cdp.evaluate(visible("#billingError"), session)
                await billing_snapshot(cdp, session, fresh)
            await assert_all_reads_settled(cdp, session)

    asyncio.run(run())
    assert_no_operational_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_billing_synthetic_dashboard_overlap_has_one_quota_owner(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready_billing(cdp, session, server, language)
            await intercept_synthetic_reads(cdp, session, server)
            baseline, old, fresh = (synthetic_summary(n) for n in (41, 52, 63))
            for dashboard_is_newer in (False, True):
                for newer_finishes_first in (False, True):
                    await billing_snapshot(cdp, session, baseline)
                    first = await begin(cdp, session, "olderRead",
                                        "loadBillingView()" if dashboard_is_newer else "refresh()",
                                        SUMMARY if dashboard_is_newer else NODES)
                    second = await begin(cdp, session, "newerRead",
                                         "refresh()" if dashboard_is_newer else "loadBillingView()",
                                         NODES if dashboard_is_newer else SUMMARY)
                    marker = "computer-synthetic-dashboard-snapshot"
                    row = {"node_id": marker, "display_name": marker, "online": False, "authorized": False}
                    old_body = old if dashboard_is_newer else {"nodes": [row], "billing": old}
                    fresh_body = {"nodes": [row], "billing": fresh} if dashboard_is_newer else fresh
                    if newer_finishes_first:
                        await respond(cdp, session, second, fresh_body)
                        await complete(cdp, session, "newerRead")
                    await respond(cdp, session, first, old_body)
                    await complete(cdp, session, "olderRead")
                    await assert_snapshot(cdp, session, fresh if newer_finishes_first else baseline, language)
                    if not newer_finishes_first:
                        await respond(cdp, session, second, fresh_body)
                        await complete(cdp, session, "newerRead")
                    await assert_snapshot(cdp, session, fresh, language)
                    # An older dashboard may still own its unrelated computer rows.
                    assert await cdp.evaluate("state.nodes[0].node_id", session) == marker
                    assert marker in await cdp.evaluate("nodeTable.textContent", session)
            await assert_all_reads_settled(cdp, session)

    asyncio.run(run())
    assert_no_operational_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_billing_synthetic_stale_401_cannot_restore_previous_account(login_server, tmp_path, language):
    server = login_server
    second_email = "billing-second-browser@example.test"
    second_user = server.provider.auth.register(second_email, PASSWORD)

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await ready_billing(cdp, session, server, language)
            assert await cdp.evaluate("state.user.email", session) == EMAIL
            await intercept_synthetic_reads(cdp, session, server)
            legacy = synthetic_summary(77, beta_free=False, plan="pro_plus", plan_name="Pro+",
                                       expansion_quantity=2, billing_interval="year",
                                       billing_total=499.97, renewal_at=1793491200)
            await billing_snapshot(cdp, session, legacy)
            await text_is(cdp, session, "billingPlan", "Pro+ + 2 Packs")
            await text_is(cdp, session, "billingPrice", "$499.97/yr")
            assert await cdp.evaluate("billingRenew.textContent.startsWith('Renews ')", session)
            assert await cdp.evaluate("Boolean(document.getElementById('billingNotice').textContent)", session)
            failed = await begin(cdp, session, "oldError")
            await respond(cdp, session, failed, {"error": "Synthetic previous account error"}, 503)
            await complete(cdp, session, "oldError")
            assert await cdp.evaluate(visible("#billingError"), session)
            old = await begin(cdp, session, "oldAccountRead")
            # Real logout and a second real login; neither POST is intercepted.
            await click(cdp, session, '.nav[data-view="nodes"]')
            await click(cdp, session, 'button[onclick="logout()"]')
            await wait_for(cdp, session, visible("#loginForm"))
            await assert_cleared(cdp, session)
            before = await cdp.evaluate("__billingReads.requests.length", session)
            await cdp.evaluate("loadBillingView().then(()=>true)", session)
            assert await cdp.evaluate("__billingReads.requests.length", session) == before
            await cdp.evaluate(f"loginEmail.value={json.dumps(second_email)};"
                               f"loginPassword.value={json.dumps(PASSWORD)};"
                               "loginRemember.checked=false;login().then(()=>true)", session)
            await wait_for(cdp, session, visible("#loginVerifyForm"))
            assert server.deliveries[-1][0] == second_email
            await cdp.evaluate(f"loginVerifyCode.value={json.dumps(server.deliveries[-1][1])};"
                               "window.secondLogin=verifyLogin();true", session)
            await wait_for(cdp, session, f"__billingReads.requests.length==={before + 1}")
            assert await cdp.evaluate("state.user.id", session) == second_user.id
            await assert_cleared(cdp, session)  # New account's dashboard read is still held.
            fresh = synthetic_summary(88, ai_accounts_used=0, nodes_used=0, nodes_connected=0)
            await respond(cdp, session, before, {"nodes": [], "billing": fresh})
            await complete(cdp, session, "secondLogin")
            await cdp.evaluate("stopRealtime();true", session)
            await assert_snapshot(cdp, session, fresh, language)
            await respond(cdp, session, old, {"error": "Synthetic old account 401"}, 401)
            await complete(cdp, session, "oldAccountRead")
            assert await cdp.evaluate("state.user.id", session) == second_user.id
            assert await cdp.evaluate(visible("#app"), session)
            assert not await cdp.evaluate(visible("#auth"), session)
            await assert_snapshot(cdp, session, fresh, language)
            await text_is(cdp, session, "billingError", "")
            # A current 401 must still open auth and clear all account data.
            current = await begin(cdp, session, "current401")
            await respond(cdp, session, current, {"error": "Synthetic current session expired"}, 401)
            await complete(cdp, session, "current401")
            assert await cdp.evaluate(visible("#loginForm"), session)
            await assert_cleared(cdp, session)
            await assert_all_reads_settled(cdp, session)
            assert request_count(server, "/api/logout") == 1
            assert request_count(server, "/auth/login/verify") == 2

    asyncio.run(run())
    assert_no_operational_effects(server)
