"""Opt-in OAuth and dashboard regressions using Chromium, HTTP and SQLite.

Run with RUN_LOGIN_E2E=1 and CHROME_BIN pointing to a Chromium binary.
Only delivery of synthetic verification emails is replaced; login, challenge
validation, OAuth consent, cookies and code redemption use production handlers.
The browser has a fresh temporary profile and can reach only the loopback app.
Computer onboarding uses synthetic offline SQLite records, never a live Node.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Mount, Route
from websockets.asyncio.client import connect

from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.oauth import OAuthProvider
from gpt_windows_connector.registration_security import RegistrationSecurity
from test_extension_chromium import CDP


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)

EMAIL = "oauth-browser@example.test"
PASSWORD = "synthetic-oauth-browser-password"
STATE = "preserved browser state /+&=?"
VERIFIER = "synthetic-browser-pkce-verifier-with-at-least-forty-three-characters"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


class LoginResponses:
    """Observe real responses without changing the application behavior."""

    def __init__(self, app, records):
        self.app, self.records = app, records

    async def __call__(self, scope, receive, send):
        record = {"path": scope.get("path"), "status": None, "headers": []}
        body = bytearray()

        async def observe(message):
            if message["type"] == "http.response.start":
                record.update(status=message["status"], headers=message.get("headers", []))
            elif message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, observe)
        if str(record["path"]).startswith("/auth/login"):
            record["json"] = json.loads(body)
            self.records.append(record)


class ResponseGate:
    """Hold one real HTTP response at a deterministic boundary for UI races."""

    def __init__(self, app):
        self.app = app
        self.path = None
        self.ready = threading.Event()
        self.release = threading.Event()

    def arm(self, path):
        assert self.path is None
        self.ready.clear()
        self.release.clear()
        self.path = path

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != self.path:
            return await self.app(scope, receive, send)
        self.path = None
        messages = []

        async def collect(message):
            messages.append(message)

        await self.app(scope, receive, collect)
        self.ready.set()
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        for message in messages:
            await send(message)


@dataclass
class LoginServer:
    base: str
    redirect_uri: str
    client_id: str
    provider: OAuthProvider
    deliveries: list
    responses: list
    gate: ResponseGate

    def authorization_url(self):
        return self.base + "/oauth/authorize?" + urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": STATE,
            "scope": "lucas offline_access",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
        })

    def counts(self):
        with self.provider.db() as db:
            return {name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                    for name in ("oauth_requests", "oauth_codes", "oauth_client_users", "oauth_refresh_tokens")}


@pytest.fixture
def login_server(tmp_path, monkeypatch):
    # Importing gateway initializes stores, so isolate its bootstrap as well.
    monkeypatch.setenv("GWC_DATA_DIR", str(tmp_path / "bootstrap"))
    monkeypatch.setenv("GWC_JWT_SECRET", "synthetic-browser-test-secret-" * 2)
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    monkeypatch.delenv("GWC_BYPASS_LOGIN_VERIFICATION", raising=False)
    monkeypatch.setenv("GWC_SMTP_HOST", "unused.example.test")
    monkeypatch.setenv("GWC_SMTP_FROM", "lucas@example.test")
    from gpt_windows_connector import gateway, login_policy, server as dashboard_server
    from gpt_windows_connector.billing import BillingService

    deliveries, responses = [], []
    monkeypatch.setattr(login_policy, "send_verification_email",
                        lambda email, code: deliveries.append((email, code)))
    path = tmp_path / "oauth-login.db"
    auth = AuthStore(path, "synthetic-oauth-login-signing-secret-" * 2)
    auth.register(EMAIL, PASSWORD)
    security = RegistrationSecurity(path)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        provider = OAuthProvider(path, auth, base)
        monkeypatch.setattr(gateway, "db_path", path)
        monkeypatch.setattr(gateway, "auth", auth)
        monkeypatch.setattr(gateway, "oauth", provider)
        monkeypatch.setattr(gateway, "billing", BillingService(path, base))
        monkeypatch.setattr(gateway, "auth_store", gateway.NodeAuthStore(path))
        bindings = gateway.UserNodeBindingStore(path)
        monkeypatch.setattr(gateway, "bindings", bindings)
        monkeypatch.setattr(gateway, "registry", gateway.NodeRegistry(bindings))
        monkeypatch.setattr(gateway, "registration_security", security)
        monkeypatch.setattr(gateway, "settings", replace(gateway.settings, public_base_url=base))

        async def callback(_request):
            return HTMLResponse("<!doctype html><title>Local OAuth callback</title><h1>Callback received</h1>")

        # Bind the isolated provider explicitly, not the module's global routes.
        app = Starlette(routes=[
            Route("/auth/login", gateway.auth_login, methods=["POST"]),
            Route("/auth/login/verify", gateway.auth_login_verify, methods=["POST"]),
            Route("/auth/login/resend", gateway.auth_login_resend, methods=["POST"]),
            Route("/oauth/register", provider.register, methods=["POST"]),
            Route("/oauth/authorize", provider.authorize),
            Route("/oauth/authorize/resume", provider.authorize_resume),
            Route("/oauth/authorize/cancel", provider.authorize_cancel, methods=["POST"]),
            Route("/oauth/authorize/decision", provider.authorize_decision, methods=["POST"]),
            Route("/oauth/token", provider.token, methods=["POST"]),
            Route("/client/callback", callback),
            Route("/dashboard", dashboard_server.webapp.dashboard),
            Route("/api/logout", dashboard_server.webapp.api_logout, methods=["POST"]),
            Route("/api/nodes", dashboard_server.webapp.api_nodes),
            Route("/api/nodes/request-access", dashboard_server.webapp.api_request_node_access, methods=["POST"]),
            Route("/api/nodes/{node_id}/activate", dashboard_server.webapp.api_activate_node, methods=["POST"]),
            Route("/api/billing/summary", dashboard_server.webapp.api_billing_summary),
            Route("/api/logs", dashboard_server.webapp.api_logs),
            Route("/api/ai-connections", dashboard_server.webapp.api_ai_connections),
            Mount("/", app=gateway.AuthMiddleware(Starlette(routes=[
                Route("/auth/me", gateway.auth_me),
            ]))),
        ])
        gate = ResponseGate(LoginResponses(app, responses))
        server = uvicorn.Server(uvicorn.Config(
            gate, log_level="error", access_log=False, lifespan="off",
        ))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started, "Local OAuth HTTP server failed to start"
            redirect_uri = base + "/client/callback?registered=preserved"
            with httpx.Client(trust_env=False) as http:
                registered = http.post(base + "/oauth/register", json={
                    "client_name": "Synthetic Browser Client", "redirect_uris": [redirect_uri],
                })
            assert registered.status_code == 201, registered.text
            yield LoginServer(base, redirect_uri, registered.json()["client_id"], provider, deliveries, responses, gate)
        finally:
            gate.release.set()
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "Local OAuth HTTP server did not stop"


@asynccontextmanager
async def chromium(tmp_path):
    profile = tmp_path / "chromium-profile"
    error_log = tmp_path / "chromium-stderr.log"
    with error_log.open("wb") as stderr:
        process = subprocess.Popen([
            os.environ["CHROME_BIN"], "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
            "--remote-debugging-port=0", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
            "--disable-component-update", "--disable-sync", "--metrics-recording-only",
            "--disable-features=AutofillServerCommunication,OptimizationHints,MediaRouter",
            "--password-store=basic",
            "--proxy-server=http://127.0.0.1:9",
            "--proxy-bypass-list=localhost;127.0.0.1;[::1]",
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=stderr)
        try:
            active_port = profile / "DevToolsActivePort"
            for _ in range(150):
                if process.poll() is not None:
                    pytest.fail("Chromium failed to start: " + error_log.read_text(errors="replace")[-6000:])
                if active_port.exists():
                    break
                await asyncio.sleep(0.1)
            assert active_port.exists(), "Chromium did not expose its debugging endpoint"
            port = active_port.read_text().splitlines()[0]
            async with httpx.AsyncClient(trust_env=False) as http:
                version = (await http.get(f"http://127.0.0.1:{port}/json/version")).json()
            async with connect(version["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024) as ws:
                cdp = CDP(ws)
                target = (await cdp.call("Target.createTarget", {"url": "about:blank"}))["targetId"]
                session = (await cdp.call("Target.attachToTarget", {
                    "targetId": target, "flatten": True,
                }))["sessionId"]
                for domain in ("Page", "Runtime", "Network"):
                    await cdp.call(domain + ".enable", session=session)
                # Dashboard tracking/Turnstile assets must never leave loopback.
                await cdp.call("Network.setBlockedURLs", {"urls": ["https://*", "wss://*"]}, session)
                yield cdp, session
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


async def wait_for(cdp, session, expression):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            result = await cdp.evaluate(expression, session)
            if result:
                return result
        except AssertionError as exc:
            if not any(message in str(exc) for message in (
                "Execution context was destroyed", "Cannot find context with specified id",
            )):
                raise
        await asyncio.sleep(0.05)
    pytest.fail(f"Browser condition timed out: {expression}\n" + str(
        await cdp.evaluate("({url: location.href, text: document.body?.innerText})", session)))


def visible(selector):
    return f"Boolean(document.querySelector({json.dumps(selector)})?.getClientRects().length)"


async def click(cdp, session, selector):
    await cdp.evaluate(f"document.querySelector({json.dumps(selector)}).click(); true", session)


async def submit_login(cdp, session, password=PASSWORD):
    await cdp.evaluate(f"""(() => {{
        document.querySelector('#email').value = {json.dumps(EMAIL)};
        document.querySelector('#password').value = {json.dumps(password)};
        document.querySelector('#remember').checked = false;
        document.querySelector('#loginForm').requestSubmit();
        return true;
    }})()""", session)


async def submit_code(cdp, session, code):
    await cdp.evaluate(f"""(() => {{
        document.querySelector('#code').value = {json.dumps(code)};
        document.querySelector('#verifyForm').requestSubmit();
        return true;
    }})()""", session)


async def assert_signed_out(cdp, session, server):
    cookies = (await cdp.call("Network.getCookies", {"urls": [server.base]}, session))["cookies"]
    assert not any(cookie["name"] == "gwc_access_token" for cookie in cookies)
    counts = server.counts()
    assert counts["oauth_requests"] == 1
    assert counts["oauth_codes"] == counts["oauth_client_users"] == counts["oauth_refresh_tokens"] == 0


def test_oauth_email_verification_then_consent_issues_one_use_code(login_server, tmp_path):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await cdp.call("Page.navigate", {"url": server.authorization_url()}, session)
            await wait_for(cdp, session, visible("#loginForm"))
            rid = await cdp.evaluate("document.querySelector('#cancelForm [name=request_id]').value", session)
            await submit_login(cdp, session, password="synthetic-wrong-password")
            await wait_for(cdp, session, "document.querySelector('#loginError')?.textContent.trim()")
            assert server.responses[-1]["status"] == 401
            assert not server.deliveries
            await assert_signed_out(cdp, session, server)

            await submit_login(cdp, session)
            await wait_for(cdp, session, visible("#verifyForm"))
            challenge = server.responses[-1]
            assert challenge["path"] == "/auth/login" and challenge["status"] == 202
            assert challenge["json"]["verification_required"] is True
            assert challenge["json"]["email"] == EMAIL
            assert "access_token" not in challenge["json"]
            assert not any(name.lower() == b"set-cookie" for name, _ in challenge["headers"])
            assert len(server.deliveries) == 1 and server.deliveries[0][0] == EMAIL
            assert await cdp.evaluate("document.querySelector('#resendBtn').disabled", session)
            await assert_signed_out(cdp, session, server)

            code = server.deliveries[-1][1]
            wrong_code = "000000" if code != "000000" else "111111"
            await submit_code(cdp, session, wrong_code)
            await wait_for(cdp, session, "document.querySelector('#loginError')?.textContent.trim()")
            assert server.responses[-1]["path"] == "/auth/login/verify"
            assert server.responses[-1]["status"] == 400
            assert "access_token" not in server.responses[-1]["json"]
            assert await cdp.evaluate(visible("#verifyForm"), session)
            await assert_signed_out(cdp, session, server)

            await submit_code(cdp, session, code)
            await wait_for(cdp, session, visible('form[action="/oauth/authorize/decision"]'))
            resume = urlsplit(await cdp.evaluate("location.href", session))
            assert resume.path == "/oauth/authorize/resume"
            assert parse_qs(resume.query) == {"request_id": [rid]}
            assert server.responses[-1]["status"] == 200
            cookies = (await cdp.call("Network.getCookies", {"urls": [server.base]}, session))["cookies"]
            access = next(cookie for cookie in cookies if cookie["name"] == "gwc_access_token")
            assert access["httpOnly"] and access["sameSite"] == "Lax"
            assert server.provider.auth.verify_token(access["value"]).email == EMAIL
            assert server.counts()["oauth_codes"] == 0  # Consent is still required.
            await click(cdp, session, 'button[name="decision"][value="allow"]')
            await wait_for(cdp, session, "location.pathname === '/client/callback'")
            redirected = urlsplit(await cdp.evaluate("location.href", session))
            registered = urlsplit(server.redirect_uri)
            assert (redirected.scheme, redirected.netloc, redirected.path) == (
                registered.scheme, registered.netloc, registered.path)
            query = parse_qs(redirected.query)
            assert query["state"] == [STATE] and query["registered"] == ["preserved"]
            assert set(query) == {"state", "registered", "code"}
            assert server.counts() == {
                "oauth_requests": 0, "oauth_codes": 1, "oauth_client_users": 1, "oauth_refresh_tokens": 0,
            }
            form = {"grant_type": "authorization_code", "client_id": server.client_id,
                    "redirect_uri": server.redirect_uri, "code": query["code"][0], "code_verifier": VERIFIER}
            async with httpx.AsyncClient(trust_env=False) as http:
                token = await http.post(server.base + "/oauth/token", data=form)
                assert token.status_code == 200, token.text
                assert server.provider.auth.verify_token(token.json()["access_token"]).client_id == server.client_id
                replay = await http.post(server.base + "/oauth/token", data=form)
                assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
            assert server.counts()["oauth_codes"] == 0

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_dashboard_computer_onboarding_at_capacity_and_beta_limits(login_server, tmp_path, language):
    """Exercise real UI/API state with offline fixtures and no Node operations."""
    from gpt_windows_connector import gateway, webapp
    from gpt_windows_connector.entitlements import ensure_node_active

    server = login_server
    with server.provider.db() as db:
        user_id = db.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()[0]
        webapp._ensure_dashboard_metadata_schema(db)

    def seed_computer(node_id, authorized=True):
        # These are isolated account fixtures, not simulated device approvals.
        if authorized:
            gateway.bindings.upsert(user_id, node_id)
        with server.provider.db() as db:
            db.execute(
                "INSERT INTO dashboard_user_nodes "
                "(user_id,node_id,node_name,access_state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (user_id, node_id, "Synthetic offline computer", "authorized" if authorized else "unauthorized",
                 time.time(), time.time()),
            )

    for index in range(1, 4):
        seed_computer(f"computer-browser-offline-{index}")
    reconnect_id = "computer-browser-reconnect"
    seed_computer(reconnect_id, authorized=False)
    assert gateway.registry.nodes == {}  # api_nodes cannot dispatch access.check.

    zh = language == "zh-CN"
    expected = {
        "coach_label": "入门指南" if zh else "Getting Started",
        "checklist": "设置清单" if zh else "Setup Checklist",
        "steps": ["连接你的 AI", "连接电脑", "设置权限"] if zh else [
            "Connect your AI", "Connect your computer", "Set permissions"],
        "close": "关闭" if zh else "Close",
        "help": "帮助 · 入门指南" if zh else "Help · Getting Started",
        "hint": "你可以随时在这里重新打开设置指南。" if zh else "You can reopen setup guidance here anytime.",
        "got_it": "知道了" if zh else "Got it",
        "connect_help": "输入目标电脑 Lucas 设置中显示的 Node ID 和 8 位连接码。连接码验证通过后，仍须由该电脑在本地批准此 Lucas 账号。" if zh else
                        "Enter the Node ID and 8-digit Connection Code shown in Lucas Settings on the target computer. After the code is verified, that computer must still approve this Lucas account locally.",
        "beta": "测试期间免费。每月 100,000 次操作、3 台电脑、3 个 AI 账号。套餐和限制可能调整。" if zh else
                "Free during testing. 100,000 Operations/month, 3 Computers, 3 AI accounts. Plans and limits may change.",
        "beta_footer": "测试提示：测试期间套餐、价格和限制可能调整。" if zh else
                       "Beta Notice: Plans, pricing, and limits may change during Beta.",
        "beta_notice": "Lucas 测试期间免费。套餐和限制可能调整。" if zh else
                       "Lucas Beta is free during testing. Plans and limits may change.",
    }

    async def text_is(cdp, session, selector, text):
        await wait_for(cdp, session,
                       f"document.querySelector({json.dumps(selector)})?.textContent.trim() === {json.dumps(text)}")

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source":
                "Object.defineProperty(navigator,'language',{value:" + json.dumps(language) + "});"}, session)
            await cdp.call("Page.navigate", {"url": server.base + "/dashboard"}, session)
            await wait_for(cdp, session, visible("#loginForm"))
            await dashboard_login(cdp, session)
            await cdp.evaluate("dashboardRequest.then(()=>true)", session)
            await wait_for(cdp, session, visible("#loginVerifyForm"))
            assert len(server.deliveries) == 1 and server.deliveries[0][0] == EMAIL
            await cdp.evaluate(
                f"loginVerifyCode.value={json.dumps(server.deliveries[-1][1])};verifyLogin().then(()=>true)", session)
            await wait_for(cdp, session, visible("#lucasCoach"))
            assert [r["status"] for r in server.responses] == [202, 200]
            assert await cdp.evaluate("document.documentElement.lang", session) == language

            # The dynamic checklist reflects persisted authorization, not online status.
            await text_is(cdp, session, "#lucasCoach h3", expected["checklist"])
            assert await cdp.evaluate("document.querySelector('#lucasCoach').getAttribute('aria-label')", session) == expected["coach_label"]
            assert await cdp.evaluate("[...document.querySelectorAll('#lucasCoach .coach-step')].map(b=>b.lastElementChild.textContent)", session) == expected["steps"]
            assert await cdp.evaluate("[...document.querySelectorAll('#lucasCoach .coach-step')].map(b=>b.classList.contains('done'))", session) == [False, True, True]
            await text_is(cdp, session, "#coachClose", expected["close"])
            await text_is(cdp, session, "#gettingStartedNav", expected["help"])
            await click(cdp, session, "#coachClose")
            await wait_for(cdp, session, visible("#coachReopenHint"))
            await text_is(cdp, session, "#coachReopenHint button", expected["got_it"])
            assert await cdp.evaluate("document.querySelector('#coachReopenHint').firstChild.textContent", session) == expected["hint"]
            assert not await cdp.evaluate(visible("#lucasCoach"), session)
            await click(cdp, session, "#coachReopenHint button")
            await click(cdp, session, "#gettingStartedNav")
            await text_is(cdp, session, "#lucasCoach h3", expected["checklist"])
            await click(cdp, session, '#lucasCoach .coach-step[data-target="ai"]')
            await wait_for(cdp, session, "location.pathname === '/ai-connections'")
            assert await cdp.evaluate(visible("#ai"), session)
            assert not await cdp.evaluate(visible("#lucasCoach"), session)
            await click(cdp, session, "#gettingStartedNav")
            await click(cdp, session, '#lucasCoach .coach-step[data-target="nodes"]')
            await wait_for(cdp, session, "location.pathname === '/nodes'")
            assert await cdp.evaluate(visible("#nodes"), session)
            assert await cdp.evaluate("({paired:metricPairedNodes.textContent,online:metricNodes.textContent})", session) == {"paired": "3", "online": "0"}
            assert await cdp.evaluate("({limit:state.billing.node_limit,active:state.billing.nodes_used,connected:state.billing.nodes_connected})", session) == {"limit": 3, "active": 3, "connected": 3}

            # Three authorized bindings must not block opening the connect dialog.
            await click(cdp, session, "#connectComputerBtn")
            await wait_for(cdp, session, visible("#connectModal"))
            assert await cdp.evaluate("({id:connectNodeId.value,code:connectCode.value,inputmode:connectCode.inputMode,maxlength:connectCode.maxLength})", session) == {"id": "", "code": "", "inputmode": "numeric", "maxlength": 8}
            await text_is(cdp, session, "#connectModal p", expected["connect_help"])
            assert await cdp.evaluate("[...document.querySelectorAll('#connectModal label')].map(e=>e.textContent)", session) == ["Node ID", "连接码" if zh else "Connection Code"]
            await click(cdp, session, '#connectModal button[onclick="requestNodeAccess()"]')
            await text_is(cdp, session, "#toast", "请输入 Node ID" if zh else "Node ID is required")
            await cdp.evaluate(f"connectNodeId.value={json.dumps(reconnect_id)};connectCode.value='1234567';true", session)
            await click(cdp, session, '#connectModal button[onclick="requestNodeAccess()"]')
            await text_is(cdp, session, "#toast", "请输入 8 位连接码" if zh else "Enter the 8-digit Connection Code")
            assert not await cdp.evaluate(visible("#connectResult"), session)

            # A real request against an offline fixture fails before any Node RPC.
            await cdp.evaluate(f"connectNodeId.value={json.dumps(reconnect_id)};connectCode.value='12345678';true", session)
            await click(cdp, session, '#connectModal button[onclick="requestNodeAccess()"]')
            await text_is(cdp, session, "#connectResult", "Node is offline: " + reconnect_id)
            await click(cdp, session, '#connectModal button[onclick="closeModal(\'connectModal\')"]')
            await click(cdp, session, "#connectComputerBtn")
            await wait_for(cdp, session, visible("#connectModal"))
            assert await cdp.evaluate("({id:connectNodeId.value,code:connectCode.value,result:connectResult.textContent,hidden:connectResult.classList.contains('hidden')})", session) == {"id": "", "code": "", "result": "", "hidden": True}
            await click(cdp, session, '#connectModal button[onclick="closeModal(\'connectModal\')"]')
            reconnect = f'#nodeTable tr[data-node-key="{reconnect_id}"] button'
            await click(cdp, session, reconnect)
            await wait_for(cdp, session, visible("#connectModal"))
            assert await cdp.evaluate("({id:connectNodeId.value,code:connectCode.value})", session) == {"id": reconnect_id, "code": ""}
            await click(cdp, session, '#connectModal button[onclick="closeModal(\'connectModal\')"]')
            assert await cdp.evaluate("location.pathname", session) == "/nodes"

            # Extra offline bindings remain permitted; activation still replaces one slot.
            seed_computer("computer-browser-offline-4")
            await cdp.evaluate("refresh().then(()=>true)", session)
            inactive = await cdp.evaluate("state.nodes.find(n=>n.plan_limited).node_id", session)
            with pytest.raises(PermissionError, match="inactive for your plan"):
                ensure_node_active(server.provider.auth.db_path, user_id, inactive)
            await click(cdp, session, f'#nodeTable tr[data-node-key="{inactive}"] button')
            await wait_for(cdp, session,
                           f"state.nodes.find(n=>n.node_id==={json.dumps(inactive)})?.active === true")
            assert await cdp.evaluate("({active:state.nodes.filter(n=>n.active).length,limited:state.nodes.filter(n=>n.plan_limited).length,connected:state.billing.nodes_connected,limit:state.billing.node_limit})", session) == {"active": 3, "limited": 1, "connected": 4, "limit": 3}
            ensure_node_active(server.provider.auth.db_path, user_id, inactive)
            demoted = await cdp.evaluate("state.nodes.find(n=>n.plan_limited).node_id", session)
            with pytest.raises(PermissionError, match="inactive for your plan"):
                ensure_node_active(server.provider.auth.db_path, user_id, demoted)
            await click(cdp, session, "#connectComputerBtn")
            await wait_for(cdp, session, visible("#connectModal"))
            await click(cdp, session, '#connectModal button[onclick="closeModal(\'connectModal\')"]')

            await click(cdp, session, '.nav[data-view="billing"]')
            await wait_for(cdp, session, visible("#billingNotice"))
            await text_is(cdp, session, "#billing .top p", expected["beta"])
            await text_is(cdp, session, "#billing > p", expected["beta_footer"])
            await text_is(cdp, session, "#billingNotice", expected["beta_notice"])
            assert not await cdp.evaluate(visible("#billingError"), session)
            assert await cdp.evaluate("({beta:state.billing.beta_free,operations:state.billing.request_limit,computers:state.billing.node_limit,ai:state.billing.ai_account_limit})", session) == {"beta": True, "operations": 100000, "computers": 3, "ai": 3}
            assert await cdp.evaluate("document.querySelectorAll('#billingCardPro,#billingCardExpansion,#billingManage').length", session) == 0

    asyncio.run(run())
    assert gateway.registry.nodes == gateway.registry.pending_requests == {}
    with server.provider.db() as db:
        assert db.execute("SELECT COUNT(*) FROM user_active_nodes WHERE user_id=?", (user_id,)).fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='node.activate' AND user_id=?", (user_id,)).fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='node.access_request' AND user_id=?", (user_id,)).fetchone()[0] == 0


@pytest.mark.parametrize("after_password", [False, True], ids=["initial-login", "pending-code"])
def test_cancel_oauth_before_authentication_never_grants_access(login_server, tmp_path, after_password):
    server = login_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await cdp.call("Page.navigate", {"url": server.authorization_url()}, session)
            await wait_for(cdp, session, visible("#loginForm"))
            if after_password:
                await submit_login(cdp, session)
                await wait_for(cdp, session, visible("#verifyForm"))
                old_challenge = server.responses[-1]["json"]["challenge_id"]
                await click(cdp, session, "#backBtn")
                await wait_for(cdp, session, visible("#loginForm"))
                assert not await cdp.evaluate(visible("#verifyForm"), session)
                await assert_signed_out(cdp, session, server)
                await submit_login(cdp, session)
                await wait_for(cdp, session, visible("#verifyForm"))
                assert server.responses[-1]["json"]["challenge_id"] != old_challenge
                assert len(server.deliveries) == 2
            await assert_signed_out(cdp, session, server)
            await click(cdp, session, "#cancelForm button")
            await wait_for(cdp, session, "location.pathname === '/client/callback'")
            redirected = urlsplit(await cdp.evaluate("location.href", session))
            registered = urlsplit(server.redirect_uri)
            assert (redirected.scheme, redirected.netloc, redirected.path) == (
                registered.scheme, registered.netloc, registered.path)
            assert parse_qs(redirected.query) == {
                "registered": ["preserved"], "state": [STATE], "error": ["access_denied"],
            }
            assert server.counts() == {
                "oauth_requests": 0, "oauth_codes": 0, "oauth_client_users": 0, "oauth_refresh_tokens": 0,
            }
            cookies = (await cdp.call("Network.getCookies", {"urls": [server.base]}, session))["cookies"]
            assert not any(cookie["name"] == "gwc_access_token" for cookie in cookies)

    asyncio.run(run())


async def wait_for_gate(gate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if gate.ready.is_set():
            return
        await asyncio.sleep(0.02)
    pytest.fail("The isolated server did not prepare the held login response")


async def dashboard_login(cdp, session, repeat=False):
    await cdp.evaluate(f"""(() => {{
        loginEmail.value = {json.dumps(EMAIL)};
        loginPassword.value = {json.dumps(PASSWORD)};
        loginRemember.checked = false;
        window.dashboardRequest = login();
        {'login(); login();' if repeat else ''}
        return true;
    }})()""", session)


async def assert_dashboard_mode(cdp, session, mode):
    for name in ("loginForm", "loginVerifyForm", "registerForm", "verifyForm"):
        assert await cdp.evaluate(visible("#" + name), session) is (name == mode), name


async def assert_dashboard_reset(cdp, session):
    assert await cdp.evaluate("""({challenge:pendingLoginChallenge,code:loginVerifyCode.value,
        email:loginVerifyEmailLabel.textContent,timer:loginResendCooldownTimer,
        cooldown:loginResendCooldownUntil,busy:loginResendBusy,
        submitDisabled:document.querySelector('#loginForm button[onclick="login()"]').disabled,
        verifyDisabled:document.querySelector('#loginVerifyForm button[onclick="verifyLogin()"]').disabled,
        error:document.getElementById('authError').textContent})""", session) == {
        "challenge": "", "code": "", "email": "", "timer": None, "cooldown": 0,
        "busy": False, "submitDisabled": False, "verifyDisabled": False, "error": "",
    }


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_dashboard_modes_back_stale_responses_and_repeated_submits(login_server, tmp_path, language):
    """Real rendered dashboard, real auth handlers/SQLite, synthetic mail only."""
    server = login_server

    async def signed_out(cdp, session):
        cookies = (await cdp.call("Network.getCookies", {"urls": [server.base]}, session))["cookies"]
        assert not any(cookie["name"] == "gwc_access_token" for cookie in cookies)
        assert server.counts() == {
            "oauth_requests": 0, "oauth_codes": 0, "oauth_client_users": 0, "oauth_refresh_tokens": 0,
        }

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source":
                "Object.defineProperty(navigator,'language',{value:" + json.dumps(language) + "});"}, session)
            await cdp.call("Page.navigate", {"url": server.base + "/dashboard?signup=1"}, session)
            await wait_for(cdp, session, visible("#registerForm"))
            await assert_dashboard_mode(cdp, session, "registerForm")
            signup_title = await cdp.evaluate("authTitle.textContent", session)
            assert signup_title == "Start using Lucas for free"
            await click(cdp, session, '#registerForm button[onclick="showRegister(false)"]')
            await assert_dashboard_mode(cdp, session, "loginForm")
            assert await cdp.evaluate("document.querySelector('#loginForm .primary').textContent", session) == (
                "登录" if language == "zh-CN" else "Sign in")

            # A late password response cannot resurrect verification over signup.
            server.gate.arm("/auth/login")
            await dashboard_login(cdp, session, repeat=True)
            await wait_for_gate(server.gate)
            assert len(server.responses) == len(server.deliveries) == 1
            assert await cdp.evaluate("document.querySelector('#loginForm .primary').disabled", session)
            await click(cdp, session, '#loginForm button[onclick="showRegister(true)"]')
            server.gate.release.set()
            await cdp.evaluate("dashboardRequest.then(()=>true)", session)
            await assert_dashboard_mode(cdp, session, "registerForm")
            await assert_dashboard_reset(cdp, session)
            assert await cdp.evaluate("authTitle.textContent", session) == signup_title
            await signed_out(cdp, session)

            # Back clears a completed challenge, including the code and timer.
            await click(cdp, session, '#registerForm button[onclick="showRegister(false)"]')
            await dashboard_login(cdp, session)
            await cdp.evaluate("dashboardRequest.then(()=>true)", session)
            await assert_dashboard_mode(cdp, session, "loginVerifyForm")
            old_challenge = await cdp.evaluate("pendingLoginChallenge", session)
            assert await cdp.evaluate("loginResendBtn.disabled", session)
            assert ("重新发送" if language == "zh-CN" else "Resend") in await cdp.evaluate("loginResendBtn.textContent", session)
            await cdp.evaluate("loginVerifyCode.value='123456'; true", session)
            await click(cdp, session, '#loginVerifyForm button[onclick="cancelLoginVerification()"]')
            await assert_dashboard_mode(cdp, session, "loginForm")
            await assert_dashboard_reset(cdp, session)

            # A real resend response arriving after another mode change is inert.
            await dashboard_login(cdp, session)
            await cdp.evaluate("dashboardRequest.then(()=>true)", session)
            assert await cdp.evaluate("pendingLoginChallenge", session) != old_challenge
            server.gate.arm("/auth/login/resend")
            await cdp.evaluate("""loginResendCooldownUntil=0;renderLoginResendButton();
                window.dashboardRequest=resendLoginVerification();resendLoginVerification();verifyLogin();true""", session)
            await wait_for_gate(server.gate)
            assert [r["path"] for r in server.responses].count("/auth/login/resend") == 1
            assert not any(r["path"] == "/auth/login/verify" for r in server.responses)
            if language == "en":
                await cdp.evaluate("showRegister(true); true", session)
                expected_mode = "registerForm"
            else:
                await click(cdp, session, '#loginVerifyForm button[onclick="cancelLoginVerification()"]')
                expected_mode = "loginForm"
            server.gate.release.set()
            await cdp.evaluate("dashboardRequest.then(()=>true)", session)
            await assert_dashboard_mode(cdp, session, expected_mode)
            await assert_dashboard_reset(cdp, session)
            await signed_out(cdp, session)

            # Wrong codes remain retryable; a duplicate valid verify sends once.
            await cdp.evaluate("showRegister(false); true", session)
            await dashboard_login(cdp, session)
            await cdp.evaluate("dashboardRequest.then(()=>true)", session)
            code = server.deliveries[-1][1]
            wrong = "000000" if code != "000000" else "111111"
            await cdp.evaluate(f"loginVerifyCode.value={json.dumps(wrong)};verifyLogin().then(()=>true)", session)
            await assert_dashboard_mode(cdp, session, "loginVerifyForm")
            assert server.responses[-1]["status"] == 400
            assert await cdp.evaluate("document.getElementById('authError').textContent", session) == (
                "验证码错误" if language == "zh-CN" else "Invalid verification code")
            await signed_out(cdp, session)
            server.gate.arm("/auth/login/verify")
            before = len(server.responses)
            await cdp.evaluate(f"""loginVerifyCode.value={json.dumps(code)};
                window.dashboardRequest=verifyLogin();verifyLogin();resendLoginVerification();true""", session)
            await wait_for_gate(server.gate)
            assert len(server.responses) == before + 1
            assert server.responses[-1]["status"] == 200
            assert await cdp.evaluate("document.querySelector('#loginVerifyForm .primary').disabled", session)
            await signed_out(cdp, session)  # Cookie is still in the held response.
            server.gate.release.set()
            await cdp.evaluate("dashboardRequest.then(()=>true)", session)
            await wait_for(cdp, session, visible("#app"))
            assert not await cdp.evaluate(visible("#auth"), session)
            await assert_dashboard_reset(cdp, session)
            cookies = (await cdp.call("Network.getCookies", {"urls": [server.base]}, session))["cookies"]
            token = next(cookie for cookie in cookies if cookie["name"] == "gwc_access_token")
            assert token["httpOnly"] and token["sameSite"] == "Lax"
            assert server.provider.auth.verify_token(token["value"]).email == EMAIL
            assert await cdp.evaluate("localStorage.getItem('lucas_login_email')", session) is None

    asyncio.run(run())
