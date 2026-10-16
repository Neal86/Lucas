"""Rendered web-route and viewport acceptance against disposable loopback data.

Run in the hosted Chromium job with RUN_LOGIN_E2E=1 and CHROME_BIN. Reuse the
existing isolated HTTP/SQLite/auth fixture and network-restricted CDP browser,
but mount the actual production web routes rather than a hand-written subset.
Email delivery alone is synthetic. No external identity/payment provider,
connected Node, device permissions, downloads, or deployment is exercised.

These checks establish rendered content, navigation, JavaScript error and
viewport contracts. They do not establish live provider/device acceptance or
replace the separately required deployed staging smoke gate.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from urllib.parse import urlsplit

import pytest
from starlette.routing import Mount, Route

from test_oauth_login_chromium import (
    EMAIL, PASSWORD, REGISTRATION_EMAIL, chromium, login_server, request_count,
    visible, wait_for,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)

VIEWPORTS = [pytest.param(1365, 900, False, id="desktop"),
             pytest.param(375, 812, True, id="mobile")]
LANGUAGES = ["en", "zh-CN"]
NODE_ID = "computer-browser-acceptance-offline"
NODE_NAME = "Synthetic offline acceptance computer"

# Every required page has a content assertion, including the final page after
# a legitimate authentication redirect. Keep expectations independent of HTML
# rendering functions so a blank/wrong page cannot pass by matching itself.
PUBLIC_PAGES = [
    ("/", "#landing h1", "Let AI Work for You", "让 AI 为你工作"),
    ("/features", "main h1", "Give your AI a secure way to use your computer.", None),
    ("/how-it-works", "main h1", "From AI request to computer action in three steps.", None),
    ("/security", "main h1", "Your computer stays behind your permission boundary.", None),
    ("/download", "main h1", "Connect your computer with Lucas Node.", None),
    ("/docs/computer-node", "#node-guide-title", "Connect a computer with Lucas Node", "使用 Lucas Node 连接电脑"),
    ("/pricing", "main h1", "Free during Beta", "测试期间免费"),
    ("/privacy", "main h1", "Privacy Policy", None),
    ("/terms", "main h1", "Terms of Service", None),
    ("/refunds", "main h1", "Refund & Cancellation Policy", None),
    ("/contact", "main h1", "Contact Lucas", None),
]
DASHBOARD_PAGES = [
    ("/dashboard", "dashboard", "Dashboard", "控制台"),
    ("/nodes", "nodes", "Computers", "电脑"),
    ("/ai-connections", "ai", "AI Connections", "AI 连接"),
    ("/task-runs", "tasks", "Task Runs", "任务记录"),
    ("/logs", "logs", "Activity Logs", "活动日志"),
    ("/account", "account", "Account & Security", "账号与安全"),
    ("/refer", "referral", "Refer & Earn", "Refer & Earn"),
    ("/billing", "billing", "Lucas Beta", "Lucas Beta"),
    ("/billing/success", "billing", "Lucas Beta", "Lucas Beta"),
    ("/billing/cancel", "billing", "Lucas Beta", "Lucas Beta"),
]
ADMIN_PAGES = [
    ("/admin", "dashboard", "Total users", "Total users"),
    ("/admin/users", "users", EMAIL, EMAIL),
    ("/admin/usage", "usage", "Success rate", "Success rate"),
    ("/admin/nodes", "nodes", "No nodes.", "No nodes."),
    ("/admin/operations", "operations", "No operations.", "No operations."),
    ("/admin/subscriptions", "subscriptions", EMAIL, EMAIL),
    ("/admin/system", "system", "healthy", "healthy"),
]


class PageResponses:
    """Observe actual HTTP statuses without changing a response or handler."""

    def __init__(self, app, records):
        self.app, self.records = app, records

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        async def observe(message):
            if message["type"] == "http.response.start":
                self.records.append({"path": scope["path"], "method": scope["method"],
                                     "status": message["status"]})
            await send(message)

        await self.app(scope, receive, observe)


@pytest.fixture
def acceptance_server(tmp_path, monkeypatch, request):
    # Resolve login_server only after isolating its import-time application
    # bootstrap. The imported shared fixture itself remains untouched.
    for key in ("HOME", "LOCALAPPDATA"):
        directory = tmp_path / key.lower()
        directory.mkdir()
        monkeypatch.setenv(key, str(directory))
    monkeypatch.setenv("GWC_DATA_DIR", str(tmp_path / "bootstrap"))
    server = request.getfixturevalue("login_server")
    assert urlsplit(server.base).scheme == "http"
    assert urlsplit(server.base).hostname == "127.0.0.1"

    from gpt_windows_connector import gateway, webapp
    from gpt_windows_connector.web_smoke_routes import WEB_SMOKE_ROUTES

    expected = {row[0] for row in PUBLIC_PAGES + DASHBOARD_PAGES + ADMIN_PAGES}
    assert expected == {path for path, _ in WEB_SMOKE_ROUTES}
    app = server.gate.app.app
    original = list(app.router.routes)
    production = [route for route in webapp.routes if isinstance(route, Route)]
    production_paths = {route.path for route in production}
    # Keep the fixture's isolated provider/auth handlers and authenticated
    # /auth/me fallback. Use real webapp/admin routes, never gateway globals.
    app.router.routes[:] = [route for route in original if isinstance(route, Route)
                           and route.path not in production_paths] + production + [
                               route for route in original if isinstance(route, Mount)]
    server.page_responses = []
    server.gate.app = PageResponses(server.gate.app, server.page_responses)
    with server.provider.db() as db:
        server.acceptance_user_id = db.execute(
            "SELECT id FROM users WHERE email=?", (EMAIL,),
        ).fetchone()[0]
        db.execute("UPDATE users SET role='user' WHERE id=?", (server.acceptance_user_id,))
        webapp._ensure_dashboard_metadata_schema(db)

    yield server

    # All permitted writes are to disposable local authentication state. Even
    # opening management UI must not accidentally dispatch a device/AI change.
    allowed_posts = {"/oauth/register", "/auth/login", "/auth/login/verify",
                     "/auth/register", "/auth/verify-email", "/api/logout"}
    assert all(r["method"] in {"GET", "HEAD"} or
               (r["method"] == "POST" and r["path"] in allowed_posts)
               for r in server.requests), server.requests
    assert gateway.registry.nodes == gateway.registry.pending_requests == {}
    assert not [r for r in server.requests if r["path"].startswith("/api/nodes/")]
    with server.provider.db() as db:
        for table in ("oauth_requests", "oauth_codes", "oauth_refresh_tokens", "task_steps"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def seed_management_rows(server):
    """Persist synthetic offline display rows; never simulate a live device."""
    from gpt_windows_connector import gateway

    gateway.bindings.upsert(server.acceptance_user_id, NODE_ID)
    with server.provider.db() as db:
        db.execute("INSERT INTO dashboard_user_nodes "
                   "(user_id,node_id,node_name,access_state,created_at,updated_at) "
                   "VALUES(?,?,?,'authorized',?,?)",
                   (server.acceptance_user_id, NODE_ID, NODE_NAME, time.time(), time.time()))
        db.execute("INSERT INTO oauth_client_users(client_id,user_id,authorized_at) VALUES(?,?,?)",
                   (server.client_id, server.acceptance_user_id, time.time()))


async def configure_browser(cdp, session, language, width, height, mobile):
    await cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": """
        Object.defineProperty(navigator,'language',{value:LANGUAGE});
        window.__acceptanceErrors=[];
        addEventListener('error',event=>{
          // A blocked optional analytics asset is a resource error, not a
          // JavaScript page exception. Do not suppress actual ErrorEvents.
          if(event instanceof ErrorEvent)__acceptanceErrors.push({kind:'error',
            message:event.message,file:event.filename,line:event.lineno});
        });
        addEventListener('unhandledrejection',event=>__acceptanceErrors.push({
          kind:'rejection',message:String(event.reason?.stack||event.reason)}));
    """.replace("LANGUAGE", json.dumps(language))}, session)
    await cdp.call("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile,
    }, session)


async def settled(cdp, session):
    await wait_for(cdp, session, "document.readyState==='complete'")
    await cdp.evaluate("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))", session)


async def navigate(cdp, session, server, path, selector, status=200, final_path=None):
    before = len(server.page_responses)
    marker = str(time.monotonic_ns())
    await cdp.evaluate("window.__acceptanceNavigationMarker=" + json.dumps(marker), session)
    await cdp.call("Page.navigate", {"url": server.base + path}, session)
    await wait_for(cdp, session, "window.__acceptanceNavigationMarker!==" + json.dumps(marker)
                   + "&&location.pathname===" + json.dumps(final_path or urlsplit(path).path)
                   + "&&" + visible(selector))
    await settled(cdp, session)
    responses = server.page_responses[before:]
    assert any(r == {"path": urlsplit(path).path, "method": "GET", "status": status}
               for r in responses), (path, responses)


async def text_content(cdp, session, selector):
    return await cdp.evaluate(
        f"document.querySelector({json.dumps(selector)}).textContent.trim()", session)


async def assert_page(cdp, session, width, selector):
    await settled(cdp, session)
    errors = await cdp.evaluate("window.__acceptanceErrors", session)
    assert errors == [], errors
    layout = await cdp.evaluate("""(() => {
      const root=document.documentElement,body=document.body,content=document.querySelector(SELECTOR);
      const r=content.getBoundingClientRect();
      return {url:location.href,title:document.title,text:body.innerText,
        innerWidth,viewport:root.clientWidth,width:Math.max(root.scrollWidth,body.scrollWidth),
        content:{left:r.left,right:r.right,width:r.width,height:r.height},
        brokenImages:[...document.images].filter(i=>i.getClientRects().length&&(!i.complete||!i.naturalWidth)).map(i=>i.src)};
    })()""".replace("SELECTOR", json.dumps(selector)), session)
    assert layout["title"].strip() and len(layout["text"].strip()) > 30, layout
    assert "async function api(" not in layout["text"], layout
    assert layout["innerWidth"] == width and 0 < layout["viewport"] <= width, layout
    assert layout["width"] <= layout["viewport"] + 1, layout
    rect = layout["content"]
    assert rect["width"] > 0 and rect["height"] > 0, layout
    assert rect["left"] >= -1 and rect["right"] <= layout["viewport"] + 1, layout
    assert not layout["brokenImages"], layout


async def click_control(cdp, session, selector):
    """Pointer hit-test the visible control; DOM .click() could hide clipping."""
    await wait_for(cdp, session, visible(selector))
    await cdp.evaluate("document.querySelector(" + json.dumps(selector) +
                       ").scrollIntoView({block:'center',inline:'nearest'});true", session)
    await settled(cdp, session)
    point = await cdp.evaluate("""(() => {
      const e=document.querySelector(SELECTOR),r=e.getBoundingClientRect();
      const x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);
      return {x,y,hit:hit===e||e.contains(hit),disabled:!!e.disabled,
        width:r.width,height:r.height,viewportWidth:innerWidth,viewportHeight:innerHeight};
    })()""".replace("SELECTOR", json.dumps(selector)), session)
    assert point["hit"] and not point["disabled"], (selector, point)
    assert point["width"] > 0 and point["height"] > 0, (selector, point)
    assert 0 <= point["x"] < point["viewportWidth"] and 0 <= point["y"] < point["viewportHeight"], point
    for kind in ("mousePressed", "mouseReleased"):
        await cdp.call("Input.dispatchMouseEvent", {
            "type": kind, "x": point["x"], "y": point["y"], "button": "left", "clickCount": 1,
        }, session)


async def fill(cdp, session, selector, value):
    await click_control(cdp, session, selector)
    await cdp.evaluate("document.querySelector(" + json.dumps(selector) + ").value='';true", session)
    await cdp.call("Input.insertText", {"text": value}, session)
    assert await cdp.evaluate("document.querySelector(" + json.dumps(selector) + ").value", session) == value


async def assert_named_controls(cdp, session, selectors):
    await cdp.call("Accessibility.enable", session=session)
    await cdp.call("DOM.enable", session=session)
    root = (await cdp.call("DOM.getDocument", session=session))["root"]["nodeId"]
    for selector in selectors:
        node = await cdp.call("DOM.querySelector", {"nodeId": root, "selector": selector}, session)
        assert node["nodeId"], selector
        tree = await cdp.call("Accessibility.getPartialAXTree", {
            "nodeId": node["nodeId"], "fetchRelatives": False,
        }, session)
        assert any(not n.get("ignored") and n.get("name", {}).get("value", "").strip()
                   for n in tree["nodes"]), (selector, tree)
        assert await cdp.evaluate("document.querySelector(" + json.dumps(selector) + ").tabIndex>=0", session), selector


async def dismiss_coach(cdp, session):
    # Dismiss only through the real control; don't replace onboarding behavior.
    if await cdp.evaluate(visible("#lucasCoach"), session):
        await click_control(cdp, session, "#coachClose")
    # The normal close schedules a hint. Hide that ancillary overlay via its
    # existing lifecycle hook before inspecting unrelated page controls.
    await cdp.evaluate("hideGettingStarted();stopRealtime();true", session)


async def sign_in(cdp, session, server, width):
    await navigate(cdp, session, server, "/dashboard", "#loginForm")
    await fill(cdp, session, "#loginEmail", EMAIL)
    await fill(cdp, session, "#loginPassword", PASSWORD)
    if await cdp.evaluate("loginRemember.checked", session):
        await click_control(cdp, session, "#loginRemember")
    await click_control(cdp, session, '#loginForm button[onclick="login()"]')
    await wait_for(cdp, session, visible("#loginVerifyForm"))
    assert server.deliveries[-1][0] == EMAIL
    await assert_page(cdp, session, width, ".auth-shell")
    await fill(cdp, session, "#loginVerifyCode", server.deliveries[-1][1])
    await click_control(cdp, session, '#loginVerifyForm button[onclick="verifyLogin()"]')
    await wait_for(cdp, session, visible("#app") + "&&Boolean(state.billing)")
    await wait_for(cdp, session, "(state.aiClients.length>0&&state.nodes.some(n=>n.authorized||n.access_state==='authorized'))||" + visible("#lucasCoach"))
    await dismiss_coach(cdp, session)
    assert await cdp.evaluate("state.user.email", session) == EMAIL


async def check_route_group(rows, check):
    """Report every independently navigable route failure in the same matrix."""
    failures = []
    for row in rows:
        try:
            await check(row)
        except (AssertionError, pytest.fail.Exception) as error:
            failures.append(f"{row[0]}: {error}")
    assert not failures, "\n\n".join(failures)


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("width,height,mobile", VIEWPORTS)
def test_public_routes_render_content_without_errors_or_horizontal_overflow(
    acceptance_server, tmp_path, language, width, height, mobile,
):
    server = acceptance_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await configure_browser(cdp, session, language, width, height, mobile)

            async def check(row):
                path, selector, english, chinese = row
                await navigate(cdp, session, server, path, selector)
                expected = chinese if language == "zh-CN" and chinese else english
                assert expected in await text_content(cdp, session, selector)
                # Legacy information/legal pages are currently English-only;
                # the localized landing, Pricing and guide must honor language.
                assert await cdp.evaluate("document.documentElement.lang", session) == (
                    language if chinese else "en")
                await assert_page(cdp, session, width, "main")
                if path == "/pricing":
                    assert await cdp.evaluate("document.querySelectorAll('main section.card').length", session) == 1
                    assert await text_content(cdp, session, "main .card h2") == "Lucas Beta"
                    assert (await text_content(cdp, session, ".price")).startswith("$0")
                    items = await cdp.evaluate("[...document.querySelectorAll('main .card li')].map(e=>e.textContent.trim())", session)
                    assert items == (["每月 100,000 次操作", "3 台电脑", "3 个 AI 账号", "多个并发任务", "完整 Lucas 执行功能", "无额外 Lucas Token 费用"] if language == "zh-CN" else [
                        "100,000 Operations per month", "3 Computers", "3 AI accounts", "Multiple concurrent tasks", "Full Lucas execution", "No additional Lucas token fees"])
                    assert await cdp.evaluate("document.querySelector('.cta').getAttribute('href')", session) == "/dashboard?signup=1"
                    assert await cdp.evaluate("document.querySelectorAll('main button,main select').length", session) == 0
                    assert not await cdp.evaluate("/Pro\\+?|Expansion Pack|\\$9\\.99|\\$19\\.99/.test(document.querySelector('main').innerText)", session)
                    await assert_named_controls(cdp, session, ['nav a[href="/dashboard"]', ".cta"])
                    await cdp.evaluate("scrollTo(0,500);true", session)
                    assert await cdp.evaluate("Math.abs(document.querySelector('nav').getBoundingClientRect().top)<=1", session)

            await check_route_group(PUBLIC_PAGES, check)
    asyncio.run(run())
    assert not server.deliveries


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("width,height,mobile", VIEWPORTS)
def test_landing_pricing_and_signup_navigation_stays_visible_and_operable(
    acceptance_server, tmp_path, language, width, height, mobile,
):
    server = acceptance_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await configure_browser(cdp, session, language, width, height, mobile)
            await navigate(cdp, session, server, "/", ".landing-signin")
            await assert_named_controls(cdp, session, [".landing-signin", ".hero-primary"])
            await cdp.evaluate("scrollTo(0,900);true", session)
            await settled(cdp, session)
            assert await cdp.evaluate("Math.abs(document.querySelector('.landing-nav').getBoundingClientRect().top)<=1", session)
            assert await cdp.evaluate(visible(".landing-signin"), session)
            if mobile:
                await assert_named_controls(cdp, session, [".mobile-menu summary"])
                await click_control(cdp, session, ".mobile-menu summary")
                assert await cdp.evaluate("document.querySelector('.mobile-menu').open", session)
                pricing = '.mobile-menu-panel a[href="/pricing"]'
                await assert_page(cdp, session, width, ".mobile-menu-panel")
            else:
                pricing = '.landing-links a[href="/pricing"]'
            assert await text_content(cdp, session, pricing) == ("价格" if language == "zh-CN" else "Pricing")
            await click_control(cdp, session, pricing)
            await wait_for(cdp, session, "location.pathname==='/pricing'&&" + visible(".cta"))
            await assert_page(cdp, session, width, "main")
            await click_control(cdp, session, ".cta")
            await wait_for(cdp, session, "location.pathname==='/dashboard'&&" + visible("#registerForm"))
            assert await cdp.evaluate("new URLSearchParams(location.search).get('signup')", session) == "1"
            await assert_page(cdp, session, width, ".auth-shell")
            await navigate(cdp, session, server, "/", ".landing-signin")
            await click_control(cdp, session, ".landing-signin")
            await wait_for(cdp, session, "location.pathname==='/dashboard'&&" + visible("#loginForm"))
            assert await text_content(cdp, session, '#loginForm button[onclick="login()"]') == ("登录" if language == "zh-CN" else "Sign in")
            await assert_page(cdp, session, width, ".auth-shell")
            await navigate(cdp, session, server, "/", ".hero-primary")
            await click_control(cdp, session, ".hero-primary")
            await wait_for(cdp, session, visible("#registerForm"))
            await assert_page(cdp, session, width, ".auth-shell")
    asyncio.run(run())
    assert not server.deliveries


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("width,height,mobile", VIEWPORTS)
def test_signed_out_deep_links_render_login_and_preserve_access_boundaries(
    acceptance_server, tmp_path, language, width, height, mobile,
):
    server = acceptance_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await configure_browser(cdp, session, language, width, height, mobile)

            async def check(row):
                path = row[0]
                redirect = path.startswith(("/admin", "/billing")) or path == "/refer"
                await navigate(cdp, session, server, path, "#loginForm",
                               status=302 if redirect else 200, final_path="/dashboard" if redirect else path)
                assert not await cdp.evaluate(visible("#app"), session)
                assert await cdp.evaluate("state.user", session) is None
                await assert_named_controls(cdp, session, ['#loginForm button[onclick="login()"]', '#loginForm button[onclick="showRegister(true)"]'])
                await assert_page(cdp, session, width, ".auth-shell")

            await check_route_group(DASHBOARD_PAGES + ADMIN_PAGES, check)
    asyncio.run(run())
    assert not server.deliveries
    assert not [r for r in server.requests if r["path"].startswith("/api/admin/")]


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("width,height,mobile", VIEWPORTS)
def test_registration_verification_and_return_to_login_fit_both_viewports(
    acceptance_server, tmp_path, language, width, height, mobile,
):
    server = acceptance_server

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await configure_browser(cdp, session, language, width, height, mobile)
            await navigate(cdp, session, server, "/dashboard?signup=1", "#registerForm")
            await assert_named_controls(cdp, session, ['#registerForm button[onclick="registerUser()"]', '#registerForm button[onclick="showRegister(false)"]'])
            # Switching modes must remain reachable before a challenge exists.
            await click_control(cdp, session, '#registerForm button[onclick="showRegister(false)"]')
            await wait_for(cdp, session, visible("#loginForm"))
            await assert_page(cdp, session, width, ".auth-shell")
            await click_control(cdp, session, '#loginForm button[onclick="showRegister(true)"]')
            for selector, value in (("#regName", "Synthetic Acceptance"), ("#regEmail", REGISTRATION_EMAIL), ("#regPassword", PASSWORD)):
                await fill(cdp, session, selector, value)
            await assert_page(cdp, session, width, ".auth-shell")
            await click_control(cdp, session, '#registerForm button[onclick="registerUser()"]')
            await wait_for(cdp, session, visible("#verifyForm"))
            assert server.responses[-1]["status"] == 202
            assert server.deliveries[-1][0] == REGISTRATION_EMAIL
            assert await text_content(cdp, session, "#verifyEmailLabel") == REGISTRATION_EMAIL
            assert await cdp.evaluate("resendVerificationBtn.disabled", session)
            assert await cdp.evaluate("({mode:verifyCode.inputMode,length:verifyCode.maxLength})", session) == {"mode": "numeric", "length": 6}
            await assert_page(cdp, session, width, ".auth-shell")
            await fill(cdp, session, "#verifyCode", server.deliveries[-1][1])
            await click_control(cdp, session, '#verifyForm button[onclick="verifyEmail()"]')
            await wait_for(cdp, session, visible("#lucasCoach"))
            assert await cdp.evaluate("state.user.email", session) == REGISTRATION_EMAIL
            await dismiss_coach(cdp, session)
            await assert_page(cdp, session, width, ".main")
            with server.provider.db() as db:
                assert db.execute("SELECT COUNT(*) FROM users WHERE email=?", (REGISTRATION_EMAIL,)).fetchone()[0] == 1
            # Logout uses the real handler; navigation then proves the cookie
            # was removed, rather than trusting only hidden application markup.
            await cdp.evaluate("logout().then(()=>true)", session)
            await navigate(cdp, session, server, "/dashboard", "#loginForm")
            await assert_page(cdp, session, width, ".auth-shell")
            assert await cdp.evaluate("fetch('/auth/me').then(r=>r.status)", session) == 401
            assert request_count(server, "/auth/register") == request_count(server, "/auth/verify-email") == 1
    asyncio.run(run())


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("width,height,mobile", VIEWPORTS)
def test_authenticated_dashboard_routes_show_real_account_data_and_history(
    acceptance_server, tmp_path, language, width, height, mobile,
):
    server = acceptance_server
    seed_management_rows(server)

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await configure_browser(cdp, session, language, width, height, mobile)
            await sign_in(cdp, session, server, width)

            async def check(row):
                path, view, english, chinese = row
                await navigate(cdp, session, server, path, "#" + view)
                await wait_for(cdp, session, "Boolean(state.billing)&&state.nodes.length===1&&state.aiClients.length===1")
                await dismiss_coach(cdp, session)
                expected = chinese if language == "zh-CN" else english
                assert await text_content(cdp, session, "#" + view + " h2") == expected
                assert await cdp.evaluate("[...document.querySelectorAll('.view')].filter(e=>e.getClientRects().length).map(e=>e.id)", session) == [view]
                assert await cdp.evaluate("state.user.email", session) == EMAIL
                assert not await cdp.evaluate(visible("#adminNav"), session)
                if view == "dashboard":
                    assert await cdp.evaluate("[metricPairedNodes.textContent,metricNodes.textContent,metricAiClients.textContent]", session) == ["1", "0", "1"]
                elif view == "nodes":
                    assert NODE_NAME in await text_content(cdp, session, "#nodeTable")
                    await assert_named_controls(cdp, session, ["#connectComputerBtn", "#nodeTable tbody button"])
                elif view == "ai":
                    assert "Synthetic Browser Client" in await text_content(cdp, session, "#aiClientTable")
                    await assert_named_controls(cdp, session, ["#addAiTopBtn", "#aiClientTable tbody .secondary", "#aiClientTable tbody .danger"])
                elif view == "tasks":
                    await wait_for(cdp, session, "document.querySelector('#taskRunSummary .metric')?.textContent==='0'")
                elif view == "logs":
                    await wait_for(cdp, session, "logTable.textContent.trim()!==''")
                elif view == "account":
                    assert await text_content(cdp, session, "#accountEmail") == EMAIL
                elif view == "referral":
                    await wait_for(cdp, session, "referralUrl.value!==''")
                    assert urlsplit(await cdp.evaluate("referralUrl.value", session)).netloc == urlsplit(server.base).netloc
                elif view == "billing":
                    await wait_for(cdp, session, "billingPrice.textContent==='$0'&&billingComputers.textContent==='1 / 3'&&billingAi.textContent==='1 / 3'")
                    assert await cdp.evaluate("state.billing.request_limit", session) == 100_000
                    assert await cdp.evaluate("document.querySelectorAll('#billing button,#billing select').length", session) == 0
                    assert not await cdp.evaluate(visible("#billingError"), session)
                await assert_page(cdp, session, width, ".main")

            await check_route_group(DASHBOARD_PAGES, check)
            await navigate(cdp, session, server, "/dashboard", "#dashboard")
            await dismiss_coach(cdp, session)
            await click_control(cdp, session, '.nav[data-view="nodes"]')
            await click_control(cdp, session, '.nav[data-view="ai"]')
            await cdp.evaluate("history.back();true", session)
            await wait_for(cdp, session, "location.pathname==='/nodes'&&" + visible("#nodes"))
            await cdp.evaluate("history.forward();true", session)
            await wait_for(cdp, session, "location.pathname==='/ai-connections'&&" + visible("#ai"))
            await assert_page(cdp, session, width, ".main")
            # A regular account also cannot render the administrative shell.
            await navigate(cdp, session, server, "/admin/users", "#dashboard", status=302, final_path="/dashboard")
            assert not await cdp.evaluate(visible("#adminNav"), session)
            await assert_page(cdp, session, width, ".main")
    asyncio.run(run())


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("width,height,mobile", VIEWPORTS)
def test_admin_deep_links_render_the_selected_tab_without_page_errors(
    acceptance_server, tmp_path, language, width, height, mobile,
):
    server = acceptance_server
    with server.provider.db() as db:
        db.execute("UPDATE users SET role='admin' WHERE id=?", (server.acceptance_user_id,))

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await configure_browser(cdp, session, language, width, height, mobile)
            await sign_in(cdp, session, server, width)

            async def check(row):
                path, tab, english, chinese = row
                await navigate(cdp, session, server, path, "#admin")
                await wait_for(cdp, session, "adminCurrentTab===" + json.dumps(tab) +
                               "&&!/Loading|加载/.test(adminContent.textContent)&&adminContent.textContent.trim()!==''")
                await dismiss_coach(cdp, session)
                assert not await cdp.evaluate("Boolean(adminContent.querySelector('.error'))", session)
                assert (chinese if language == "zh-CN" else english) in await text_content(cdp, session, "#adminContent")
                assert await cdp.evaluate(visible("#adminNav"), session)
                assert await cdp.evaluate("document.querySelectorAll('#adminTabs .primary').length", session) == 1
                await assert_named_controls(cdp, session, ["#adminTabs .primary"])
                await assert_page(cdp, session, width, ".main")

            await check_route_group(ADMIN_PAGES, check)
    asyncio.run(run())


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("width,height,mobile", VIEWPORTS)
def test_computer_and_ai_management_modals_fit_and_close_without_mutations(
    acceptance_server, tmp_path, language, width, height, mobile,
):
    server = acceptance_server
    seed_management_rows(server)

    async def modal(cdp, session, modal_id, english, chinese, controls):
        await wait_for(cdp, session, visible("#" + modal_id))
        assert await text_content(cdp, session, "#" + modal_id + " h3") == (chinese if language == "zh-CN" else english)
        await assert_page(cdp, session, width, "#" + modal_id + " .modal")
        box = await cdp.evaluate("""(() => {
          const e=document.querySelector(SELECTOR),r=e.getBoundingClientRect();
          return {top:r.top,bottom:r.bottom,height:innerHeight,width:e.clientWidth,scroll:e.scrollWidth};
        })()""".replace("SELECTOR", json.dumps("#" + modal_id + " .modal")), session)
        assert box["top"] >= -1 and box["bottom"] <= box["height"] + 1, box
        assert box["scroll"] <= box["width"] + 1, box
        close = f'#{modal_id} button[onclick="closeModal(\'{modal_id}\')"]'
        await assert_named_controls(cdp, session, [close, *controls])
        await click_control(cdp, session, close)
        await wait_for(cdp, session, "!" + visible("#" + modal_id))
        assert await cdp.evaluate(visible("#app"), session)

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await configure_browser(cdp, session, language, width, height, mobile)
            await sign_in(cdp, session, server, width)
            await click_control(cdp, session, '.nav[data-view="nodes"]')
            await click_control(cdp, session, "#connectComputerBtn")
            await modal(cdp, session, "connectModal", "Connect to a computer", "连接到电脑", ["#connectSubmit"])
            await click_control(cdp, session, "#connectComputerBtn")
            await cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27}, session)
            await cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27}, session)
            await wait_for(cdp, session, "!" + visible("#connectModal"))
            await click_control(cdp, session, "#nodeTable tbody button")
            assert await cdp.evaluate("manageNodeName.value", session) == NODE_NAME
            assert await text_content(cdp, session, "#manageNodeIdText") == NODE_ID
            await modal(cdp, session, "nodeModal", "Computer Node", "电脑节点", ["#manageNodeSave", "#manageNodeLogsRefresh"])
            assert await cdp.evaluate("location.pathname", session) == "/nodes"
            await click_control(cdp, session, '.nav[data-view="ai"]')
            await click_control(cdp, session, "#addAiTopBtn")
            await fill(cdp, session, "#aiClientType", "Synthetic AI")
            assert "Synthetic AI" in await text_content(cdp, session, "#aiHelp")
            await modal(cdp, session, "aiModal", "Add AI connection", "添加 AI 连接", ['#aiModal button[onclick="copyMcpUrl()"]'])
            await click_control(cdp, session, "#aiClientTable tbody .secondary")
            assert await cdp.evaluate("aiManageName.value", session) == "Synthetic Browser Client"
            await fill(cdp, session, "#aiManageName", "Unsaved synthetic edit")
            await fill(cdp, session, "#aiManageNote", "This disposable edit must not be saved by closing.")
            await modal(cdp, session, "aiManageModal", "Edit AI connection", "编辑 AI 连接", ["#aiManageSave"])
            await click_control(cdp, session, "#aiClientTable tbody .secondary")
            assert await cdp.evaluate("[aiManageName.value,aiManageNote.value]", session) == ["Synthetic Browser Client", ""]
            await modal(cdp, session, "aiManageModal", "Edit AI connection", "编辑 AI 连接", ["#aiManageSave"])
            assert await cdp.evaluate("location.pathname", session) == "/ai-connections"
            await assert_page(cdp, session, width, ".main")
    asyncio.run(run())
    with server.provider.db() as db:
        assert db.execute("SELECT COUNT(*) FROM dashboard_ai_metadata").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM dashboard_node_metadata").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM oauth_client_users").fetchone()[0] == 1
