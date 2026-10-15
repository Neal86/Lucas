from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import gateway, webapp


WHITE_LOGO_URL = "/assets/lucas-logo-horizontal-white.png?v=exact-f0e1b4a6"
BLUE_LOGO_URL = "/assets/lucas-logo-horizontal-blue.png?v=source-20260901b"
# Remove the public component before logo replacements can change its identity.
html = webapp.DASHBOARD_HTML.replace(webapp.LANDING_HTML, "", 1)

html = html.replace(
    '.landing-links a,.landing-footer{color:#8e98ae}',
    '.landing-links a{color:#dfe4f3}.landing-footer{color:#8e98ae}',
)

html = html.replace(
    '<nav class="landing-nav"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
    f'<nav class="landing-nav"><div class="landing-logo"><img src="{WHITE_LOGO_URL}" alt="Lucas" /></div>',
)
html = html.replace(
    '<footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
    f'<footer class="landing-footer"><div class="landing-logo"><img src="{WHITE_LOGO_URL}" alt="Lucas" /></div>',
)
html = html.replace(
    '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
    f'<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="{WHITE_LOGO_URL}" alt="Lucas" /></div>',
)
html = html.replace(
    '<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
    f'<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="{BLUE_LOGO_URL}" alt="Lucas" /></div>',
)

# Login UI: password visibility, remembered-device choice, and email verification.
html = html.replace(
    '<input id="loginPassword" class="input" type="password" autocomplete="current-password">',
    '<div class="password-wrap"><input id="loginPassword" class="input" type="password" autocomplete="current-password"><button class="password-eye" type="button" onclick="togglePassword(\'loginPassword\',this)" aria-label="Show password" title="Show password">👁</button></div>',
)
html = html.replace(
    '<input id="regPassword" class="input" type="password" placeholder="At least 10 characters">',
    '<div class="password-wrap"><input id="regPassword" class="input" type="password" autocomplete="new-password" placeholder="At least 10 characters"><button class="password-eye" type="button" onclick="togglePassword(\'regPassword\',this)" aria-label="Show password" title="Show password">👁</button></div>',
)
html = html.replace(
    '<button class="btn primary" style="width:100%" onclick="login()">Sign in</button>',
    '<label class="remember-row"><input id="loginRemember" type="checkbox" checked> <span>Remember password</span></label><button class="btn primary" style="width:100%" onclick="login()">Sign in</button>',
)
html = html.replace(
    '<div id="registerForm" class="hidden">',
    '<div id="loginVerifyForm" class="hidden"><p class="muted">We sent a 6-digit login verification code to <b id="loginVerifyEmailLabel"></b>.</p><div class="field"><label>Verification code</label><div class="login-code-wrap"><input id="loginVerifyCode" class="input" inputmode="numeric" maxlength="6" autocomplete="one-time-code"><button id="loginResendBtn" class="login-code-resend" type="button" onclick="resendLoginVerification()">Resend</button></div></div><button class="btn primary" style="width:100%" onclick="verifyLogin()">Verify and sign in</button><button class="btn secondary" style="width:100%;margin-top:10px" onclick="cancelLoginVerification()">Back to sign in</button></div><div id="registerForm" class="hidden">',
    1,
)

# The display boxes have both width and height; object-fit:contain preserves the
# source aspect ratio. Do not combine fixed width with max-height because that
# can squash tall source canvases into a horizontal line.
html = html.replace(
    '</head>',
    '<style>'
    '.auth-card .brand{height:140px;display:flex;align-items:center;justify-content:center;margin:0 0 18px}'
    '.auth-card .brand img{display:block;width:300px!important;height:120px!important;object-fit:contain!important;object-position:center!important;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important}'
    '.side .logo{height:96px!important;min-height:96px!important;padding:10px 14px!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;overflow:hidden!important}'
    '.side .logo img{display:block!important;width:205px!important;height:76px!important;object-fit:contain!important;object-position:left center!important;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important;margin:0!important}'
    '.landing-logo img{display:block!important;width:220px!important;height:52px!important;object-fit:contain!important;object-position:left center!important;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important}'
    '.password-wrap{position:relative}.password-wrap .input{padding-right:46px}.password-eye{position:absolute;right:7px;top:50%;transform:translateY(-50%);width:34px;height:34px;border:0;background:transparent;cursor:pointer;border-radius:7px;font-size:17px;line-height:1}.password-eye:hover{background:#f2f4f7}.remember-row{display:flex;align-items:center;gap:8px;margin:2px 0 14px;color:#475467;cursor:pointer}.remember-row input{width:16px;height:16px}.login-code-wrap{position:relative}.login-code-wrap .input{padding-right:132px}.login-code-resend{position:absolute;right:10px;top:50%;transform:translateY(-50%);border:0;background:transparent;color:var(--accent);font-weight:700;padding:7px 8px;cursor:pointer;white-space:nowrap}.login-code-resend:hover:not(:disabled){text-decoration:underline}.login-code-resend:disabled{color:#98a2b3;cursor:not-allowed;text-decoration:none}'
    '</style></head>',
)

html = html.replace(
    "function authError(t){const e=document.getElementById('authError');e.textContent=t;e.classList.toggle('hidden',!t)}",
    """function authError(t){const M={'Invalid email or password':'邮箱或密码错误','Account is disabled':'账号已禁用','Email is already registered':'该邮箱已注册','Email verification is required but email service is not configured':'登录需要邮箱验证码，但邮件服务尚未配置','Invalid verification code':'验证码错误','Verification code expired':'验证码已过期','Too many verification attempts':'验证码错误次数过多','Login verification session expired':'登录验证已过期，请重新登录','Login network changed. Please sign in again.':'登录网络已变化，请重新登录','Too many login attempts. Try again later.':'登录尝试过多，请稍后再试'};const e=document.getElementById('authError');e.textContent=WEB_LANG==='zh'?(M[t]||t):t;e.classList.toggle('hidden',!t)}""",
)
html = html.replace(
    "boot();\n</script>",
    """try{const saved=localStorage.getItem('lucas_login_email');if(saved){loginEmail.value=saved;loginRemember.checked=true}}catch{}
boot();
</script>""",
)

webapp.DASHBOARD_HTML = html


async def white_logo_asset(request):
    return FileResponse(
        webapp.BRAND_ASSET_DIR / "lucas-logo-horizontal-white.png",
        media_type="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


async def blue_logo_asset(request):
    return FileResponse(
        webapp.BRAND_ASSET_DIR / "lucas-logo-horizontal-blue.png",
        media_type="image/png",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


# Keep the composite server's route names, but never fork authentication policy.
secure_auth_login = gateway.auth_login
secure_auth_login_resend = gateway.auth_login_resend
secure_auth_login_verify = gateway.auth_login_verify


for path, handler, methods in (
    ("/auth/login", secure_auth_login, ["POST"]),
    ("/auth/login/resend", secure_auth_login_resend, ["POST"]),
    ("/auth/login/verify", secure_auth_login_verify, ["POST"]),
    ("/assets/lucas-logo-horizontal-white.png", white_logo_asset, ["GET"]),
    ("/assets/lucas-logo-horizontal-blue.png", blue_logo_asset, ["GET"]),
):
    webapp.routes[:] = [r for r in webapp.routes if getattr(r, "path", None) != path]
    webapp.routes.insert(0, Route(path, handler, methods=methods))


class DashboardAuthMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        # Stripe must be able to reach the signed webhook without a Lucas login.
        # The webhook authenticates itself with Stripe-Signature instead.
        public_api_paths = {"/api/logout", "/api/billing/webhook"}
        if scope["type"] == "http" and path.startswith("/api/") and path not in public_api_paths:
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            token = ""
            authorization = headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                token = authorization[7:].strip()
            if not token:
                cookie = headers.get("cookie", "")
                for part in cookie.split(";"):
                    name, sep, value = part.strip().partition("=")
                    if sep and name == "gwc_access_token":
                        token = value
                        break
            try:
                gateway.auth.verify_token(token)
            except Exception:
                await JSONResponse({"error": "authentication_required"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with gateway.mcp.session_manager.run():
        yield


starlette_app = Starlette(routes=webapp.routes, lifespan=lifespan)
app = DashboardAuthMiddleware(starlette_app)


def main() -> None:
    uvicorn.run(
        app,
        host=gateway.settings.host,
        port=gateway.settings.port,
        log_level="info",
        ws_ping_interval=30.0,
        ws_ping_timeout=60.0,
    )


if __name__ == "__main__":
    main()
