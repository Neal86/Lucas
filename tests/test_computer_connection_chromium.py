"""Opt-in Chromium regressions for Connect computer response ownership.

The real composed dashboard, DOM, localization and API client run in Chromium.
One control uses the real loopback offline-node handler. The remaining cases
intercept only POST /api/nodes/request-access at the isolated fixture origin,
returning explicitly synthetic responses at the browser fetch boundary. They
establish frontend behavior, not device approval or backend acceptance.
No Node is connected, no permission is changed and no provider is contacted.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlsplit

import pytest

from test_oauth_login_chromium import (
    chromium, click, dashboard_login, login_server, request_count, visible,
    wait_for, wait_for_gate,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)

ACCESS_PATH = "/api/nodes/request-access"
CLOSE = '#connectModal button[onclick="closeModal(\'connectModal\')"]'
REFRESH_PATHS = ("/api/nodes", "/api/logs", "/api/ai-connections")


async def signed_in_dashboard(cdp, session, server, language):
    await cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source":
        "Object.defineProperty(navigator,'language',{value:" + json.dumps(language) + "});"}, session)
    await cdp.call("Page.navigate", {"url": server.base + "/dashboard"}, session)
    await wait_for(cdp, session, visible("#loginForm"))
    await dashboard_login(cdp, session)
    await cdp.evaluate("dashboardRequest.then(()=>true)", session)
    await wait_for(cdp, session, visible("#loginVerifyForm"))
    await cdp.evaluate(
        f"loginVerifyCode.value={json.dumps(server.deliveries[-1][1])};verifyLogin().then(()=>true)", session)
    await wait_for(cdp, session, visible("#app"))
    assert await cdp.evaluate("document.documentElement.lang", session) == language
    if await cdp.evaluate(visible("#lucasCoach"), session):
        await click(cdp, session, "#coachClose")
    await click(cdp, session, '.nav[data-view="nodes"]')


async def open_connect(cdp, session):
    await click(cdp, session, "#connectComputerBtn")
    await wait_for(cdp, session, visible("#connectModal"))
    assert await cdp.evaluate("""({id:connectNodeId.value,code:connectCode.value,
        result:connectResult.textContent,hidden:connectResult.classList.contains('hidden'),
        disabled:connectSubmit.disabled})""", session) == {
        "id": "", "code": "", "result": "", "hidden": True, "disabled": False,
    }


async def send_connect(cdp, session, node_id, promise, repeated=False):
    # Exercise both programmatic re-entry and actual button.click dispatch.
    await cdp.evaluate(f"""connectNodeId.value={json.dumps(node_id)};
        connectCode.value='12345678';window[{json.dumps(promise)}]=requestNodeAccess();
        {"connectSubmit.click();requestNodeAccess();connectSubmit.click();" if repeated else ""}
        true""", session)


async def completed(cdp, session, promise):
    await cdp.evaluate(f"window[{json.dumps(promise)}].then(()=>true)", session)


async def text_is(cdp, session, selector, expected):
    await wait_for(cdp, session,
                   f"document.querySelector({json.dumps(selector)})?.textContent.trim() === {json.dumps(expected)}")


def refresh_counts(server):
    return [request_count(server, path) for path in REFRESH_PATHS]


def assert_no_device_effects(server):
    from gpt_windows_connector import gateway

    assert gateway.registry.nodes == gateway.registry.pending_requests == {}
    with server.provider.db() as db:
        assert db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='node.access_request'").fetchone()[0] == 0
        for table in ("user_node_bindings", "dashboard_user_nodes", "dashboard_pending_node_access"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


async def intercept_synthetic_access(cdp, session, server):
    """A narrow browser-only transport fixture; production functions stay real."""
    assert urlsplit(server.base).scheme == "http"
    assert urlsplit(server.base).hostname == "127.0.0.1"
    await cdp.evaluate("""(() => {
        const origin=ORIGIN, nativeFetch=window.fetch.bind(window);
        if(location.origin!==origin)throw new Error('Wrong synthetic fixture origin');
        const requests=[],pending=[];
        window.__connectionTest={requests,
          respond(index,body,status=200){
            const request=pending[index];
            if(!request||request.done)throw new Error('Missing or settled synthetic response');
            request.done=true;
            request.resolve(new Response(JSON.stringify(body),{
              status,headers:{'Content-Type':'application/json'}}));
          },
          fail(index){
            const request=pending[index];
            if(!request||request.done)throw new Error('Missing or settled synthetic response');
            request.done=true;request.reject(new TypeError('Synthetic connection network error'));
          }};
        window.fetch=(input,options={})=>{
          const url=new URL(typeof input==='string'?input:input.url,location.href);
          const method=String(options.method||(typeof input==='object'&&input.method)||'GET').toUpperCase();
          if(url.origin===origin&&url.pathname==='/api/nodes/request-access'&&!url.search&&method==='POST'){
            const body=JSON.parse(options.body);
            if(!String(body.node_id).startsWith('computer-synthetic-')||body.connection_code!=='12345678')
              throw new Error('Unexpected non-synthetic connection payload');
            requests.push({url:url.href,method,body,credentials:options.credentials});
            return new Promise((resolve,reject)=>pending.push({resolve,reject,done:false}));
          }
          return nativeFetch(input,options);
        };
        return true;
    })()""".replace("ORIGIN", json.dumps(server.base)), session)


async def synthetic_count(cdp, session):
    return await cdp.evaluate("__connectionTest.requests.length", session)


async def respond(cdp, session, index, body=None, status=200):
    if status == "network":
        await cdp.evaluate(f"__connectionTest.fail({index});true", session)
    else:
        await cdp.evaluate(
            f"__connectionTest.respond({index},{json.dumps(body)},{status});true", session)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_connect_real_offline_response_is_single_flight_and_cannot_replace_reopened_modal(
    login_server, tmp_path, language,
):
    """Keep a real HTTP/backend control without introducing a live Node."""
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await signed_in_dashboard(cdp, session, server, language)
            await open_connect(cdp, session)
            server.gate.arm(ACCESS_PATH)
            await send_connect(cdp, session, "computer-offline-old", "connectOld", repeated=True)
            await wait_for_gate(server.gate)
            assert request_count(server, ACCESS_PATH) == 1
            assert await cdp.evaluate("connectSubmit.disabled", session)
            assert not await cdp.evaluate(f"document.querySelector({json.dumps(CLOSE)}).disabled", session)
            await click(cdp, session, CLOSE)
            await open_connect(cdp, session)
            await send_connect(cdp, session, "computer-offline-new", "connectNew", repeated=True)
            await completed(cdp, session, "connectNew")
            await text_is(cdp, session, "#connectResult", "Node is offline: computer-offline-new")
            assert request_count(server, ACCESS_PATH) == 2
            server.gate.release.set()
            await completed(cdp, session, "connectOld")
            assert await cdp.evaluate("connectResult.textContent", session) == "Node is offline: computer-offline-new"
            assert await cdp.evaluate("connectNodeId.value", session) == "computer-offline-new"
            assert not await cdp.evaluate("connectSubmit.disabled", session)
            assert await cdp.evaluate(visible("#app"), session)

    asyncio.run(run())
    assert_no_device_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_connect_synthetic_late_results_and_401_cannot_own_newer_request(
    login_server, tmp_path, language,
):
    server = login_server
    sending = "正在发送访问申请…" if language == "zh-CN" else "Sending access request…"
    approved = "访问已在目标电脑本地批准。" if language == "zh-CN" else "Access approved on the target computer."
    outcomes = [
        ({"pending": True}, 200), ({"authorized": True}, 200),
        ({"error": "Synthetic old connection error"}, 400),
        ({"error": "Synthetic obsolete session"}, 401), (None, "network"),
    ]

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await signed_in_dashboard(cdp, session, server, language)
            await intercept_synthetic_access(cdp, session, server)
            user_id = await cdp.evaluate("state.user.id", session)
            for finished_new in (False, True):
                for outcome_index, (body, status) in enumerate(outcomes):
                    first = await synthetic_count(cdp, session)
                    await open_connect(cdp, session)
                    await send_connect(cdp, session, f"computer-synthetic-old-{outcome_index}", "connectOld", repeated=True)
                    assert await synthetic_count(cdp, session) == first + 1
                    assert await cdp.evaluate("connectSubmit.disabled", session)
                    await click(cdp, session, CLOSE)
                    await open_connect(cdp, session)
                    new_id = f"computer-synthetic-new-{outcome_index}"
                    await send_connect(cdp, session, new_id, "connectNew", repeated=True)
                    assert await synthetic_count(cdp, session) == first + 2
                    if finished_new:
                        await respond(cdp, session, first + 1, {"authorized": True})
                        await completed(cdp, session, "connectNew")
                        await text_is(cdp, session, "#connectResult", approved)
                    before = refresh_counts(server)
                    await respond(cdp, session, first, body, status)
                    await completed(cdp, session, "connectOld")
                    await text_is(cdp, session, "#connectResult", approved if finished_new else sending)
                    assert await cdp.evaluate("connectSubmit.disabled", session) is (not finished_new)
                    assert await cdp.evaluate("connectNodeId.value", session) == new_id
                    assert await cdp.evaluate("state.user.id", session) == user_id
                    assert await cdp.evaluate(visible("#app"), session)
                    assert not await cdp.evaluate(visible("#auth"), session)
                    assert refresh_counts(server) == before
                    if not finished_new:
                        await respond(cdp, session, first + 1, {"authorized": True})
                        await completed(cdp, session, "connectNew")
                        await text_is(cdp, session, "#connectResult", approved)
                    await click(cdp, session, CLOSE)
            assert request_count(server, ACCESS_PATH) == 0

    asyncio.run(run())
    assert_no_device_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_connect_synthetic_current_results_preserve_validation_local_approval_and_retry(
    login_server, tmp_path, language,
):
    server = login_server
    zh = language == "zh-CN"
    outcomes = [
        ({"pending": True}, 200, "访问申请已发送，正在等待目标电脑本地批准。" if zh else
         "Access request sent. Waiting for local approval on the target computer.", True),
        ({"authorized": True}, 200, "访问已在目标电脑本地批准。" if zh else
         "Access approved on the target computer.", True),
        ({"error": "invalid connection code"}, 200, "连接码不正确。" if zh else "Connection Code is incorrect.", False),
        ({"authorized": False}, 200, "访问申请未被接受。" if zh else "Access request was not accepted.", False),
        ({"error": "Synthetic current connection error"}, 503, "Synthetic current connection error", False),
        (None, "network", "Synthetic connection network error", False),
    ]

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await signed_in_dashboard(cdp, session, server, language)
            await intercept_synthetic_access(cdp, session, server)
            await open_connect(cdp, session)
            await click(cdp, session, "#connectSubmit")
            await text_is(cdp, session, "#toast", "请输入 Node ID" if zh else "Node ID is required")
            await cdp.evaluate("connectNodeId.value='computer-synthetic-validation';connectCode.value='1234567';true", session)
            await click(cdp, session, "#connectSubmit")
            await text_is(cdp, session, "#toast", "请输入 8 位连接码" if zh else "Enter the 8-digit Connection Code")
            assert await synthetic_count(cdp, session) == 0
            assert not await cdp.evaluate(visible("#connectResult"), session)
            for index, (body, status, expected, refreshed) in enumerate(outcomes):
                before = refresh_counts(server)
                node_id = f"computer-synthetic-current-{index}"
                await send_connect(cdp, session, node_id, "connectCurrent", repeated=True)
                assert await synthetic_count(cdp, session) == index + 1
                assert await cdp.evaluate("connectSubmit.disabled", session)
                assert await cdp.evaluate(f"__connectionTest.requests[{index}]", session) == {
                    "url": server.base + ACCESS_PATH, "method": "POST", "credentials": "include",
                    "body": {"node_id": node_id, "connection_code": "12345678"},
                }
                await respond(cdp, session, index, body, status)
                await completed(cdp, session, "connectCurrent")
                await text_is(cdp, session, "#connectResult", expected)
                assert not await cdp.evaluate("connectSubmit.disabled", session)
                assert refresh_counts(server) == [count + int(refreshed) for count in before]
                assert await cdp.evaluate(visible("#app"), session)
            # A current 401 still opens authentication; only obsolete 401s are ignored.
            index = await synthetic_count(cdp, session)
            await send_connect(cdp, session, "computer-synthetic-expired", "connectCurrent")
            await respond(cdp, session, index, {"error": "Synthetic current expired session"}, 401)
            await completed(cdp, session, "connectCurrent")
            assert await cdp.evaluate("state.user", session) is None
            assert await cdp.evaluate(visible("#auth"), session)
            assert not await cdp.evaluate(visible("#app"), session)
            assert not await cdp.evaluate(visible("#connectModal"), session)
            assert request_count(server, ACCESS_PATH) == 0

    asyncio.run(run())
    assert_no_device_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_connect_synthetic_escape_navigation_and_auth_invalidate_pending_response(
    login_server, tmp_path, language,
):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await signed_in_dashboard(cdp, session, server, language)
            await intercept_synthetic_access(cdp, session, server)
            for index, transition in enumerate(("escape", "navigation", "auth")):
                await click(cdp, session, '.nav[data-view="nodes"]')
                await open_connect(cdp, session)
                await send_connect(cdp, session, f"computer-synthetic-{transition}", "connectOld")
                if transition == "escape":
                    await cdp.call("Input.dispatchKeyEvent", {
                        "type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
                    }, session)
                    await cdp.call("Input.dispatchKeyEvent", {
                        "type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
                    }, session)
                elif transition == "navigation":
                    await click(cdp, session, '.nav[data-view="dashboard"]')
                else:
                    await cdp.evaluate("showAuth();true", session)
                assert not await cdp.evaluate(visible("#connectModal"), session)
                snapshot = await cdp.evaluate("({result:connectResult.textContent,user:state.user?.id||null})", session)
                before = refresh_counts(server)
                await respond(cdp, session, index, {"error": "Synthetic obsolete session"}, 401)
                await completed(cdp, session, "connectOld")
                assert await cdp.evaluate("({result:connectResult.textContent,user:state.user?.id||null})", session) == snapshot
                assert not await cdp.evaluate(visible("#connectModal"), session)
                assert await cdp.evaluate(visible("#auth"), session) is (transition == "auth")
                assert refresh_counts(server) == before
            assert request_count(server, ACCESS_PATH) == 0

    asyncio.run(run())
    assert_no_device_effects(server)
