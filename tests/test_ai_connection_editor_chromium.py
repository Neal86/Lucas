"""Opt-in Chromium regressions for AI metadata editor response ownership.

The composed dashboard, DOM, localization, login and read APIs remain real.
Only PUTs for explicitly synthetic AI client IDs at the isolated loopback
fixture origin are held by a browser fetch shim. Synthetic clients exist only
in page state; no OAuth consent, token, permission or real client is changed.
The inherited login fixture registers one disposable OAuth client; every test
checks that its OAuth records and all AI metadata remain unchanged.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import quote, urlsplit

import pytest

from test_computer_connection_chromium import signed_in_dashboard
from test_oauth_login_chromium import (
    chromium, click, login_server, request_count, visible, wait_for, wait_for_gate,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)

CLOSE = '#aiManageModal button[onclick="closeModal(\'aiManageModal\')"]'
REFRESH_PATHS = ("/api/nodes", "/api/logs", "/api/ai-connections")
CLIENTS = [
    {"client_id": "synthetic-ai-a /?+%中文", "client_name": "Synthetic AI A",
     "display_name": "Original A", "note": "Original note A", "created_at": 1},
    {"client_id": "synthetic-ai-b", "client_name": "Synthetic AI B",
     "display_name": "Original B", "note": "Original note B", "created_at": 2},
]
LATE_OUTCOMES = [
    ({"ok": True}, 200),
    ({"error": "Synthetic old AI metadata error"}, 400),
    ({"error": "Synthetic old AI session"}, 401),
    (None, "network"),
]


def backend_snapshot(server):
    """Do not seed ownership, tokens or AI metadata to exercise this UI race."""
    with server.provider.db() as db:
        return {
            name: [tuple(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY rowid")]
            for name in (
                "oauth_clients", "oauth_client_users", "oauth_requests", "oauth_codes",
                "oauth_refresh_tokens", "oauth_revocations", "dashboard_ai_metadata",
            )
        }


def assert_backend_unchanged(server, before):
    assert backend_snapshot(server) == before
    assert not [request for request in server.requests
                if request["path"].startswith("/api/ai-connections/")]
    with server.provider.db() as db:
        assert db.execute("SELECT COUNT(*) FROM audit_logs WHERE action IN "
                          "('oauth.connection_update','oauth.disconnect')").fetchone()[0] == 0


def refresh_counts(server):
    return [request_count(server, path) for path in REFRESH_PATHS]


async def setup_editor(cdp, session, server, language):
    await signed_in_dashboard(cdp, session, server, language)
    await click(cdp, session, '.nav[data-view="ai"]')
    await intercept_synthetic_updates(cdp, session, server)
    await seed_clients(cdp, session)


async def seed_clients(cdp, session):
    # Keep real GET /api/ai-connections unmodified; only the page's disposable
    # presentation state contains the synthetic editable rows.
    await cdp.evaluate(f"state.aiClients={json.dumps(CLIENTS)};renderAiClients();true", session)


async def open_editor(cdp, session, index=0):
    await click(cdp, session, f"#aiClientTable tbody tr:nth-child({index + 1}) button")
    await wait_for(cdp, session, visible("#aiManageModal"))
    assert await cdp.evaluate("""({name:aiManageName.value,note:aiManageNote.value,
        disabled:aiManageSave.disabled,busy:aiManageSave.getAttribute('aria-busy')})""", session) == {
        "name": CLIENTS[index]["display_name"], "note": CLIENTS[index]["note"],
        "disabled": False, "busy": "false",
    }


async def set_fields(cdp, session, name, note, dispatch=True):
    await cdp.evaluate(f"""aiManageName.value={json.dumps(name)};
        aiManageNote.value={json.dumps(note)};
        {"aiManageName.dispatchEvent(new Event('input',{bubbles:true}));aiManageNote.dispatchEvent(new Event('input',{bubbles:true}));" if dispatch else ""}
        true""", session)


async def save(cdp, session, promise="aiSave", repeated=True):
    # Invoke both the production function and the actual disabled-button path.
    await cdp.evaluate(f"""window[{json.dumps(promise)}]=saveAiConnection();
        {"aiManageSave.click();saveAiConnection();aiManageSave.click();" if repeated else ""}
        true""", session)


async def completed(cdp, session, promise="aiSave"):
    await cdp.evaluate(f"window[{json.dumps(promise)}].then(()=>true)", session)


async def synthetic_count(cdp, session):
    return await cdp.evaluate("__aiEditorTest.requests.length", session)


async def respond(cdp, session, index, body=None, status=200):
    if status == "network":
        await cdp.evaluate(f"__aiEditorTest.fail({index});true", session)
    else:
        await cdp.evaluate(f"__aiEditorTest.respond({index},{json.dumps(body)},{status});true", session)


async def editor_snapshot(cdp, session):
    # Toast visibility expires on a timer, but its text must not be overwritten.
    return await cdp.evaluate("""({name:aiManageName.value,note:aiManageNote.value,
        disabled:aiManageSave.disabled,busy:aiManageSave.getAttribute('aria-busy'),
        modal:!aiManageModal.classList.contains('hidden'),toast:document.getElementById('toast').textContent,
        user:state.user?.id||null,clients:state.aiClients,path:location.pathname,
        app:!document.getElementById('app').classList.contains('hidden'),
        auth:!document.getElementById('auth').classList.contains('hidden')})""", session)


async def text_is(cdp, session, selector, expected):
    await wait_for(cdp, session,
                   f"document.querySelector({json.dumps(selector)})?.textContent.trim() === {json.dumps(expected)}")


async def intercept_synthetic_updates(cdp, session, server):
    """A transport boundary only; never replace the product API or editor."""
    assert urlsplit(server.base).scheme == "http"
    assert urlsplit(server.base).hostname == "127.0.0.1"
    await cdp.evaluate("""(() => {
        const origin=ORIGIN,nativeFetch=window.fetch.bind(window),requests=[],pending=[];
        if(location.origin!==origin)throw new Error('Wrong synthetic fixture origin');
        const take=index=>{
          const request=pending[index];
          if(!request||request.done)throw new Error('Missing or settled synthetic AI response');
          if(request.signal?.aborted)throw new Error('Dispatched metadata PUT was cancelled');
          request.done=true;return request;
        };
        window.__aiEditorTest={requests,
          respond(index,body,status=200){
            take(index).resolve(new Response(JSON.stringify(body),{
              status,headers:{'Content-Type':'application/json'}}));
          },
          fail(index){take(index).reject(new TypeError('Synthetic AI metadata network error'))}
        };
        window.fetch=(input,options={})=>{
          const url=new URL(typeof input==='string'?input:input.url,location.href);
          const method=String(options.method||(typeof input==='object'&&input.method)||'GET').toUpperCase();
          if(url.origin===origin&&url.pathname.startsWith('/api/ai-connections/synthetic-')&&!url.search&&method==='PUT'){
            const body=JSON.parse(options.body);
            if(Object.keys(body).sort().join(',')!=='display_name,note'||
               typeof body.display_name!=='string'||typeof body.note!=='string')
              throw new Error('Unexpected synthetic AI metadata payload');
            requests.push({url:url.href,method,body,credentials:options.credentials});
            return new Promise((resolve,reject)=>pending.push({resolve,reject,signal:options.signal,done:false}));
          }
          return nativeFetch(input,options);
        };
        return true;
    })()""".replace("ORIGIN", json.dumps(server.base)), session)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_ai_editor_current_payload_single_flight_errors_and_retry(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup_editor(cdp, session, server, language)
            before = backend_snapshot(server)
            await open_editor(cdp, session)
            await text_is(cdp, session, "#aiManageSave", "保存" if language == "zh-CN" else "Save")
            await text_is(cdp, session, CLOSE, "关闭" if language == "zh-CN" else "Close")
            name, note = "  Assistant 中文  ", " \nSynthetic note / & + 中文\n  "
            await set_fields(cdp, session, name, note)
            outcomes = [
                ({"error": "Synthetic current metadata error"}, 400, "Synthetic current metadata error"),
                ({}, 503, "Request failed: 503"),
                (None, "network", "Synthetic AI metadata network error"),
                ({"ok": True}, 200, "AI connection saved"),
            ]
            for index, (body, status, message) in enumerate(outcomes):
                counts = refresh_counts(server)
                await save(cdp, session)
                assert await synthetic_count(cdp, session) == index + 1
                assert await cdp.evaluate("aiManageSave.disabled", session)
                assert await cdp.evaluate("aiManageSave.getAttribute('aria-busy')", session) == "true"
                assert not await cdp.evaluate(f"document.querySelector({json.dumps(CLOSE)}).disabled", session)
                assert await cdp.evaluate(f"__aiEditorTest.requests[{index}]", session) == {
                    "url": server.base + "/api/ai-connections/" + quote(CLIENTS[0]["client_id"], safe="~()*!.'-"),
                    "method": "PUT", "credentials": "include",
                    "body": {"display_name": name.strip(), "note": note.strip()},
                }
                await respond(cdp, session, index, body, status)
                await completed(cdp, session)
                await text_is(cdp, session, "#toast", message)
                assert not await cdp.evaluate("aiManageSave.disabled", session)
                assert await cdp.evaluate("aiManageSave.getAttribute('aria-busy')", session) == "false"
                succeeded = status == 200
                assert await cdp.evaluate(visible("#aiManageModal"), session) is (not succeeded)
                assert refresh_counts(server) == [count + int(succeeded) for count in counts]
                assert await cdp.evaluate("aiManageName.value", session) == name
                assert await cdp.evaluate("aiManageNote.value", session) == note
                assert await cdp.evaluate(visible("#app"), session)
            # Success's hidden editor cannot dispatch another metadata update.
            await save(cdp, session)
            await completed(cdp, session)
            assert await synthetic_count(cdp, session) == len(outcomes)
            assert_backend_unchanged(server, before)

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_ai_editor_late_results_cannot_close_or_change_newer_editor(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup_editor(cdp, session, server, language)
            before = backend_snapshot(server)
            for same_client in (False, True):
                for newer_result in ("pending", "error", "success"):
                    for body, status in LATE_OUTCOMES:
                        await seed_clients(cdp, session)
                        await open_editor(cdp, session)
                        first = await synthetic_count(cdp, session)
                        await set_fields(cdp, session, "Old unsaved name", "Old unsaved note")
                        await save(cdp, session, "oldAiSave")
                        assert await synthetic_count(cdp, session) == first + 1
                        await click(cdp, session, CLOSE)
                        await open_editor(cdp, session, 0 if same_client else 1)
                        await set_fields(cdp, session, "New editor name", "New editor note")
                        await save(cdp, session, "newAiSave")
                        assert await synthetic_count(cdp, session) == first + 2
                        if newer_result != "pending":
                            if newer_result == "success":
                                await respond(cdp, session, first + 1, {"ok": True})
                                expected = "AI connection saved"
                            else:
                                await respond(cdp, session, first + 1, {"error": "New editor retryable error"}, 409)
                                expected = "New editor retryable error"
                            await completed(cdp, session, "newAiSave")
                            await text_is(cdp, session, "#toast", expected)
                        snapshot, counts = await editor_snapshot(cdp, session), refresh_counts(server)
                        await respond(cdp, session, first, body, status)
                        await completed(cdp, session, "oldAiSave")
                        assert await editor_snapshot(cdp, session) == snapshot
                        assert refresh_counts(server) == counts
                        assert await synthetic_count(cdp, session) == first + 2
                        if newer_result == "pending":
                            await respond(cdp, session, first + 1, {"error": "New editor retryable error"}, 409)
                            await completed(cdp, session, "newAiSave")
                            await text_is(cdp, session, "#toast", "New editor retryable error")
                        await click(cdp, session, CLOSE)
            assert_backend_unchanged(server, before)

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_ai_editor_input_changes_suppress_old_feedback_and_allow_explicit_retry(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup_editor(cdp, session, server, language)
            before = backend_snapshot(server)
            for edit in ("name", "note", "reverted", "without_input_event"):
                for body, status in (({"ok": True}, 200), ({"error": "Obsolete input session"}, 401)):
                    await open_editor(cdp, session)
                    first = await synthetic_count(cdp, session)
                    await save(cdp, session, "oldAiSave")
                    if edit == "name":
                        name, note = "New field name", CLIENTS[0]["note"]
                    else:
                        name, note = CLIENTS[0]["display_name"], "New field note"
                    await set_fields(cdp, session, name, note, dispatch=edit != "without_input_event")
                    if edit == "reverted":
                        name, note = CLIENTS[0]["display_name"], CLIENTS[0]["note"]
                        await set_fields(cdp, session, name, note)
                    await save(cdp, session, "duplicateAiSave")
                    await completed(cdp, session, "duplicateAiSave")
                    assert await synthetic_count(cdp, session) == first + 1
                    assert await cdp.evaluate("aiManageSave.disabled", session)
                    snapshot, counts = await editor_snapshot(cdp, session), refresh_counts(server)
                    await respond(cdp, session, first, body, status)
                    await completed(cdp, session, "oldAiSave")
                    snapshot.update(disabled=False, busy="false")
                    assert await editor_snapshot(cdp, session) == snapshot
                    assert refresh_counts(server) == counts
                    await save(cdp, session, "newAiSave")
                    assert await synthetic_count(cdp, session) == first + 2
                    assert await cdp.evaluate(f"__aiEditorTest.requests[{first + 1}].body", session) == {
                        "display_name": name, "note": note,
                    }
                    await respond(cdp, session, first + 1, {"error": "Current explicit retry"}, 400)
                    await completed(cdp, session, "newAiSave")
                    await text_is(cdp, session, "#toast", "Current explicit retry")
                    await click(cdp, session, CLOSE)
            assert_backend_unchanged(server, before)

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_ai_editor_close_escape_navigation_history_and_auth_invalidate_response(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup_editor(cdp, session, server, language)
            before = backend_snapshot(server)
            for index, transition in enumerate(("close", "escape", "navigation", "history", "auth")):
                await click(cdp, session, '.nav[data-view="nodes"]')
                await click(cdp, session, '.nav[data-view="ai"]')
                await open_editor(cdp, session)
                await save(cdp, session, "oldAiSave")
                if transition == "close":
                    await click(cdp, session, CLOSE)
                elif transition == "escape":
                    for event_type in ("keyDown", "keyUp"):
                        await cdp.call("Input.dispatchKeyEvent", {
                            "type": event_type, "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
                        }, session)
                elif transition == "navigation":
                    await click(cdp, session, '.nav[data-view="dashboard"]')
                elif transition == "history":
                    await cdp.evaluate("history.back();true", session)
                    await wait_for(cdp, session, "location.pathname==='/nodes' && aiManageModal.classList.contains('hidden')")
                else:
                    await cdp.evaluate("showAuth();true", session)
                assert not await cdp.evaluate(visible("#aiManageModal"), session)
                assert not await cdp.evaluate("aiManageSave.disabled", session)
                await save(cdp, session, "hiddenAiSave")
                await completed(cdp, session, "hiddenAiSave")
                assert await synthetic_count(cdp, session) == index + 1
                snapshot, counts = await editor_snapshot(cdp, session), refresh_counts(server)
                await respond(cdp, session, index, {"error": "Obsolete dismissed editor session"}, 401)
                await completed(cdp, session, "oldAiSave")
                assert await editor_snapshot(cdp, session) == snapshot
                assert refresh_counts(server) == counts
                assert await cdp.evaluate(visible("#auth"), session) is (transition == "auth")
            assert_backend_unchanged(server, before)

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_ai_editor_old_account_results_cannot_change_new_account_editor(login_server, tmp_path, language):
    server = login_server
    second_email, second_password = "ai-editor-second@example.test", "synthetic-ai-editor-password"
    server.provider.auth.register(second_email, second_password)

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup_editor(cdp, session, server, language)
            before = backend_snapshot(server)
            first_user = await cdp.evaluate("state.user.id", session)
            for index in range(len(LATE_OUTCOMES)):
                await open_editor(cdp, session)
                await save(cdp, session, f"oldAccountSave{index}")
                await click(cdp, session, CLOSE)
            await cdp.evaluate("showAuth();true", session)
            await wait_for(cdp, session, visible("#loginForm"))
            await cdp.evaluate(f"""loginEmail.value={json.dumps(second_email)};
                loginPassword.value={json.dumps(second_password)};loginRemember.checked=false;
                login().then(()=>true)""", session)
            await wait_for(cdp, session, visible("#loginVerifyForm"))
            assert server.deliveries[-1][0] == second_email
            await cdp.evaluate(f"loginVerifyCode.value={json.dumps(server.deliveries[-1][1])};verifyLogin().then(()=>true)", session)
            await wait_for(cdp, session, visible("#app"))
            assert await cdp.evaluate("state.user.email", session) == second_email
            assert await cdp.evaluate("state.user.id", session) != first_user
            if await cdp.evaluate(visible("#lucasCoach"), session):
                await click(cdp, session, "#coachClose")
            await click(cdp, session, '.nav[data-view="ai"]')
            await seed_clients(cdp, session)
            await open_editor(cdp, session, 1)
            await set_fields(cdp, session, "Second account name", "Second account note")
            await save(cdp, session, "newAccountSave")
            snapshot, counts = await editor_snapshot(cdp, session), refresh_counts(server)
            for index, (body, status) in enumerate(LATE_OUTCOMES):
                await respond(cdp, session, index, body, status)
                await completed(cdp, session, f"oldAccountSave{index}")
                assert await editor_snapshot(cdp, session) == snapshot
                assert refresh_counts(server) == counts
                assert await synthetic_count(cdp, session) == len(LATE_OUTCOMES) + 1
            await respond(cdp, session, len(LATE_OUTCOMES), {"error": "Second account current error"}, 409)
            await completed(cdp, session, "newAccountSave")
            await text_is(cdp, session, "#toast", "Second account current error")
            assert not await cdp.evaluate("aiManageSave.disabled", session)
            assert_backend_unchanged(server, before)

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_ai_editor_reopened_during_success_refresh_keeps_new_ui(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup_editor(cdp, session, server, language)
            before = backend_snapshot(server)
            await open_editor(cdp, session)
            await set_fields(cdp, session, "Committed synthetic name", "Committed synthetic note")
            await save(cdp, session, "oldAiSave")
            counts = refresh_counts(server)
            server.gate.arm("/api/ai-connections")
            await respond(cdp, session, 0, {"ok": True})
            await wait_for_gate(server.gate)
            assert not await cdp.evaluate(visible("#aiManageModal"), session)
            assert refresh_counts(server) == [count + 1 for count in counts]
            await open_editor(cdp, session, 1)
            await set_fields(cdp, session, "Newer editor name", "Newer editor note")
            await save(cdp, session, "newAiSave")
            snapshot = await editor_snapshot(cdp, session)
            server.gate.release.set()
            await completed(cdp, session, "oldAiSave")
            assert await editor_snapshot(cdp, session) == snapshot
            assert await synthetic_count(cdp, session) == 2
            await respond(cdp, session, 1, {"error": "Current editor after old refresh"}, 400)
            await completed(cdp, session, "newAiSave")
            await text_is(cdp, session, "#toast", "Current editor after old refresh")
            assert not await cdp.evaluate("aiManageSave.disabled", session)
            assert_backend_unchanged(server, before)

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_ai_editor_current_401_still_requires_authentication(login_server, tmp_path, language):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await setup_editor(cdp, session, server, language)
            before = backend_snapshot(server)
            await open_editor(cdp, session)
            counts = refresh_counts(server)
            await save(cdp, session)
            await respond(cdp, session, 0, {"error": "Synthetic current expired session"}, 401)
            await completed(cdp, session)
            assert await cdp.evaluate("state.user", session) is None
            assert await cdp.evaluate(visible("#auth"), session)
            assert not await cdp.evaluate(visible("#app"), session)
            assert not await cdp.evaluate(visible("#aiManageModal"), session)
            assert not await cdp.evaluate("aiManageSave.disabled", session)
            assert refresh_counts(server) == counts
            assert await synthetic_count(cdp, session) == 1
            assert_backend_unchanged(server, before)

    asyncio.run(run())
