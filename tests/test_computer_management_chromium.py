"""Opt-in real Chromium/DOM ownership checks with synthetic management responses.

Only exact fixture-origin synthetic computer name/log/activation and AI Delete
requests are intercepted. Real login/logout/verification and ordinary reads
remain native. No Node or OAuth grant/revocation is changed. Synthetic confirm
responses are recorded; these tests do not certify native permission dialogs.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import quote, urlsplit

import pytest

from test_ai_connection_editor_chromium import backend_snapshot, assert_backend_unchanged
from test_computer_connection_chromium import assert_no_device_effects, signed_in_dashboard
from test_oauth_login_chromium import PASSWORD, chromium, click, login_server, visible, wait_for
from test_session_lifecycle_chromium import second_login

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)

NODES = [
    {"node_id": "synthetic-management-a /?中文", "name": "Original A", "authorized": True,
     "online": False, "allowed_roots": ["SYNTHETIC_A_ROOT"], "last_seen": 1},
    {"node_id": "synthetic-management-b", "name": "Original B", "authorized": True,
     "online": False, "allowed_roots": ["SYNTHETIC_B_ROOT"], "last_seen": 1},
]
CLIENTS = [{"client_id": "synthetic-delete-a /?中文", "display_name": "Synthetic delete A"},
           {"client_id": "synthetic-delete-b", "display_name": "Synthetic delete B"}]

SYNTHETIC_TRANSPORT = r'''(() => {
const origin=FIXTURE_ORIGIN,nodes=NODE_IDS,clients=CLIENT_IDS,nativeFetch=window.fetch.bind(window),nativeConfirm=window.confirm.bind(window);
if(location.origin!==origin)throw new Error('Wrong management fixture origin');
const requests=[],pending=[],confirmations=[];
function take(index){const p=pending[index];if(!p||p.done||p.signal?.aborted)throw new Error('Missing, settled or cancelled management request');p.done=true;return p}
window.__managementTest={requests,confirmations,
 respond(index,body,status=200){take(index).resolve(new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}}))},
 fail(index){take(index).reject(new TypeError('Synthetic management network error'))},
 settled(){return pending.every(p=>p.done)}
};
window.confirm=message=>{
 if(String(message).startsWith('Delete AI connection Synthetic delete ')){
  confirmations.push(message);return true;
 }
 return nativeConfirm(message);
};
window.fetch=(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href),method=String(options.method||(typeof input==='object'&&input.method)||'GET').toUpperCase();
 const node=url.pathname.match(/^\/api\/nodes\/([^/]+)\/(name|logs|activate)$/);
 const client=url.pathname.match(/^\/api\/ai-connections\/([^/]+)$/);
 let synthetic=false;
 if(url.origin===origin&&node&&nodes.includes(decodeURIComponent(node[1]))){
  synthetic=(node[2]==='name'&&method==='PUT'&&!url.search)||(node[2]==='logs'&&method==='GET'&&url.search==='?limit=250')||(node[2]==='activate'&&method==='POST'&&!url.search);
 }
 if(url.origin===origin&&client&&clients.includes(decodeURIComponent(client[1]))&&method==='DELETE'&&!url.search)synthetic=true;
 if(!synthetic)return nativeFetch(input,options);
 const body=options.body===undefined?null:JSON.parse(options.body);
 if(node?.[2]==='name'&&(Object.keys(body).join(',')!=='name'||typeof body.name!=='string'))throw new Error('Unexpected rename payload');
 if(node?.[2]!=='name'&&body!==null)throw new Error('Unexpected management body');
 requests.push({path:url.pathname+url.search,method,body,credentials:options.credentials});
 return new Promise((resolve,reject)=>pending.push({resolve,reject,signal:options.signal,done:false}));
};return true;
})()'''


async def setup(cdp, session, server, language):
    assert urlsplit(server.base).hostname == "127.0.0.1"
    await signed_in_dashboard(cdp, session, server, language)
    await cdp.evaluate("stopRealtime();hideGettingStarted();true", session)
    source = SYNTHETIC_TRANSPORT.replace("FIXTURE_ORIGIN", json.dumps(server.base)).replace(
        "NODE_IDS", json.dumps([n["node_id"] for n in NODES])).replace(
        "CLIENT_IDS", json.dumps([c["client_id"] for c in CLIENTS]))
    await cdp.evaluate(source, session)
    await seed(cdp, session)


async def seed(cdp, session):
    await cdp.evaluate(f"state.nodes={json.dumps(NODES)};state.aiClients={json.dumps(CLIENTS)};renderNodes();renderAiClients();true", session)


async def open_node(cdp, session, index=0):
    await cdp.evaluate(f"openNodeModal(encodeURIComponent({json.dumps(NODES[index]['node_id'])}));true", session)
    await wait_for(cdp, session, visible("#nodeModal"))


async def begin(cdp, session, expression, name="managementPending", duplicate=False):
    await cdp.evaluate(f"window[{json.dumps(name)}]={expression};{expression+';' if duplicate else ''}true", session)


async def finish(cdp, session, name="managementPending"):
    await cdp.evaluate(f"window[{json.dumps(name)}].then(()=>true)", session)


async def respond(cdp, session, index, body=None, status=200):
    if status == "network":
        await cdp.evaluate(f"__managementTest.fail({index});true", session)
    else:
        await cdp.evaluate(f"__managementTest.respond({index},{json.dumps(body)},{status});true", session)


async def counts(cdp, session):
    return await cdp.evaluate("__managementTest.requests.length", session)


async def assert_settled(cdp, session):
    assert await cdp.evaluate("__managementTest.settled()", session)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_management_current_rename_payload_busy_failure_retry(login_server, tmp_path, language):
    server = login_server
    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup(cdp, session, server, language)
            before = backend_snapshot(server)
            await open_node(cdp, session)
            for index, (body, status) in enumerate([({"error": "Synthetic current error"}, 503),
                                                   (None, "network"), ({"display_name": "Renamed 中文"}, 200)]):
                await cdp.evaluate("manageNodeName.value='  Renamed 中文  ';manageNodeName.dispatchEvent(new Event('input',{bubbles:true}));true", session)
                await begin(cdp, session, "saveNodeName()", duplicate=True)
                await click(cdp, session, "#manageNodeSave")
                assert await counts(cdp, session) == index + 1
                assert await cdp.evaluate("manageNodeSave.disabled", session)
                assert await cdp.evaluate(f"__managementTest.requests[{index}]", session) == {
                    "path": "/api/nodes/" + quote(NODES[0]["node_id"], safe="~()*!.'-") + "/name",
                    "method": "PUT", "body": {"name": "Renamed 中文"}, "credentials": "include",
                }
                await respond(cdp, session, index, body, status)
                await finish(cdp, session)
                assert not await cdp.evaluate("manageNodeSave.disabled", session)
            assert await cdp.evaluate("state.nodes[0].display_name", session) == "Renamed 中文"
            assert await cdp.evaluate("state.nodes[1].display_name||null", session) is None
            await assert_settled(cdp, session)
            assert_backend_unchanged(server, before)
    asyncio.run(run())
    assert_no_device_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_management_old_rename_and_logs_cannot_replace_new_modal(login_server, tmp_path, language):
    server = login_server
    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup(cdp, session, server, language)
            await open_node(cdp, session)
            await cdp.evaluate("manageNodeName.value='OLD_NAME';true", session)
            await begin(cdp, session, "saveNodeName()", "oldName")
            await begin(cdp, session, "loadNodeLogs()", "oldLogs")
            await open_node(cdp, session, 1)
            await begin(cdp, session, "loadNodeLogs()", "freshLogs")
            await respond(cdp, session, 2, {"lines": ["CURRENT_B_LOG"]})
            await finish(cdp, session, "freshLogs")
            await respond(cdp, session, 0, {"display_name": "OLD_NAME"})
            await respond(cdp, session, 1, {"lines": ["OLD_A_LOG"]})
            await finish(cdp, session, "oldName"); await finish(cdp, session, "oldLogs")
            assert await cdp.evaluate("manageNodeName.value", session) == "Original B"
            assert await cdp.evaluate("manageNodeIdText.textContent", session) == NODES[1]["node_id"]
            assert await cdp.evaluate("manageLogs.textContent", session) == "CURRENT_B_LOG"
            assert await cdp.evaluate("state.nodes[1].display_name||null", session) is None
            assert await cdp.evaluate("state.nodes[0].display_name", session) == "OLD_NAME"
            await open_node(cdp, session)
            assert await cdp.evaluate("manageNodeName.value", session) == "OLD_NAME"
            await assert_settled(cdp, session)
    asyncio.run(run())
    assert_no_device_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_management_name_input_close_escape_and_navigation_retire_responses(login_server, tmp_path, language):
    server = login_server
    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup(cdp, session, server, language)
            for index, change in enumerate(["input", "close", "escape", "navigation"]):
                await open_node(cdp, session)
                await cdp.evaluate("manageNodeName.value='OLD';true", session)
                await begin(cdp, session, "saveNodeName()")
                if change == "input":
                    await cdp.evaluate("manageNodeName.value='NEW_DRAFT';manageNodeName.dispatchEvent(new Event('input',{bubbles:true}));true", session)
                elif change == "close":
                    await click(cdp, session, '#nodeModal button[onclick="closeModal(\'nodeModal\')"]')
                elif change == "escape":
                    await cdp.evaluate("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));true", session)
                else:
                    await cdp.evaluate("view('account',null);true", session)
                await respond(cdp, session, index, {"error": "Synthetic obsolete session"}, 401)
                await finish(cdp, session)
                assert await cdp.evaluate(visible("#app"), session)
                assert await cdp.evaluate("state.nodes[0].display_name||null", session) is None
                if change == "input":
                    assert await cdp.evaluate("manageNodeName.value", session) == "NEW_DRAFT"
                else:
                    assert not await cdp.evaluate(visible("#nodeModal"), session)
            await assert_settled(cdp, session)
    asyncio.run(run())
    assert_no_device_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_management_stale_401s_do_not_hide_real_replacement_login(login_server, tmp_path, language):
    server = login_server
    email = "management-second@example.test"
    second = server.provider.auth.register(email, PASSWORD)
    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup(cdp, session, server, language)
            before = backend_snapshot(server)
            await open_node(cdp, session)
            await begin(cdp, session, "loadNodeLogs()", "oldLogs")
            await begin(cdp, session, "deleteAiConnection(encodeURIComponent(" + json.dumps(CLIENTS[0]["client_id"]) + "))", "oldDelete")
            await cdp.evaluate("logout().then(()=>true)", session)
            assert not await cdp.evaluate(visible("#nodeModal"), session)
            assert await cdp.evaluate("manageRootsText.textContent", session) == ""
            await second_login(cdp, session, server, email)
            await seed(cdp, session)
            for index, name in [(0, "oldLogs"), (1, "oldDelete")]:
                await respond(cdp, session, index, {"error": "Synthetic old401"}, 401)
                await finish(cdp, session, name)
            assert await cdp.evaluate("state.user.id", session) == second.id
            assert await cdp.evaluate("state.aiClients.length", session) == 2
            assert await cdp.evaluate(visible("#app"), session)
            assert not await cdp.evaluate(visible("#nodeModal"), session)
            await assert_settled(cdp, session)
            assert_backend_unchanged(server, before)
    asyncio.run(run())
    assert_no_device_effects(server)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_management_ai_delete_duplicate_current_failure_retry_and_old_navigation(login_server, tmp_path, language):
    server = login_server
    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup(cdp, session, server, language)
            before = backend_snapshot(server)
            await click(cdp, session, '.nav[data-view="ai"]')
            expression = "deleteAiConnection(encodeURIComponent(" + json.dumps(CLIENTS[0]["client_id"]) + "))"
            await begin(cdp, session, expression, duplicate=True)
            assert await counts(cdp, session) == 1
            assert await cdp.evaluate("__managementTest.confirmations.length", session) == 1
            assert await cdp.evaluate("document.querySelector('#aiClientTable tbody tr button.danger').disabled", session)
            await respond(cdp, session, 0, {"error": "Synthetic current delete error"}, 503)
            await finish(cdp, session)
            assert await cdp.evaluate("state.aiClients.length", session) == 2
            await begin(cdp, session, expression, "oldDelete")
            await click(cdp, session, '.nav[data-view="account"]')
            await respond(cdp, session, 1, {"ok": True})
            await finish(cdp, session, "oldDelete")
            assert await cdp.evaluate("state.aiClients.length", session) == 1
            assert await cdp.evaluate("state.aiClients[0].client_id", session) == CLIENTS[1]["client_id"]
            await click(cdp, session, '.nav[data-view="ai"]')
            assert not await cdp.evaluate("aiClientTable.textContent.includes('Synthetic delete A')", session)
            expression = "deleteAiConnection(encodeURIComponent(" + json.dumps(CLIENTS[1]["client_id"]) + "))"
            await begin(cdp, session, expression, "currentDelete", duplicate=True)
            await respond(cdp, session, 2, {"ok": True})
            await finish(cdp, session, "currentDelete")
            assert await cdp.evaluate("state.aiClients.length", session) == 0
            await assert_settled(cdp, session)
            assert_backend_unchanged(server, before)
    asyncio.run(run())
    assert_no_device_effects(server)
