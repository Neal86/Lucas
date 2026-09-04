from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import gateway, webapp
from .registration_security import email_verification_enabled, send_verification_email


WHITE_LOGO_URL = "/assets/lucas-logo-horizontal-white.png?v=exact-f0e1b4a6"
BLUE_LOGO_URL = "/assets/lucas-logo-horizontal-blue.png?v=source-20260901b"
html = webapp.DASHBOARD_HTML

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
    '<div id="loginVerifyForm" class="hidden"><p class="muted">We sent a 6-digit login verification code to <b id="loginVerifyEmailLabel"></b>.</p><div class="field"><label>Verification code</label><input id="loginVerifyCode" class="input" inputmode="numeric" maxlength="6" autocomplete="one-time-code"></div><button class="btn primary" style="width:100%" onclick="verifyLogin()">Verify and sign in</button><button class="btn secondary" style="width:100%;margin-top:10px" onclick="cancelLoginVerification()">Back to sign in</button></div><div id="registerForm" class="hidden">',
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
    '.password-wrap{position:relative}.password-wrap .input{padding-right:46px}.password-eye{position:absolute;right:7px;top:50%;transform:translateY(-50%);width:34px;height:34px;border:0;background:transparent;cursor:pointer;border-radius:7px;font-size:17px;line-height:1}.password-eye:hover{background:#f2f4f7}.remember-row{display:flex;align-items:center;gap:8px;margin:2px 0 14px;color:#475467;cursor:pointer}.remember-row input{width:16px;height:16px}'
    '</style></head>',
)

# Preserve real login errors instead of converting every 401 into "Please sign in".
html = html.replace(
    "if(r.status===401){showAuth();throw new Error('Please sign in')}if(!r.ok)throw new Error(d.error||('Request failed: '+r.status));return d",
    "if(r.status===401&&url!='/auth/login'){showAuth()}if(!r.ok)throw new Error(d.error||('Request failed: '+r.status));return d",
)
html = html.replace("let pendingVerificationEmail='';", "let pendingVerificationEmail='',pendingLoginChallenge='';")
html = html.replace(
    "function showRegister(v){authError('');document.getElementById('verifyForm').classList.add('hidden');document.getElementById('loginForm').classList.toggle('hidden',v);document.getElementById('registerForm').classList.toggle('hidden',!v)}",
    "function showRegister(v){authError('');document.getElementById('verifyForm').classList.add('hidden');document.getElementById('loginVerifyForm').classList.add('hidden');document.getElementById('loginForm').classList.toggle('hidden',v);document.getElementById('registerForm').classList.toggle('hidden',!v)}",
)
html = html.replace(
    "async function login(){try{await api('/auth/login',{method:'POST',body:JSON.stringify({email:loginEmail.value,password:loginPassword.value})});await boot()}catch(e){authError(e.message)}}",
    """async function rememberCredential(){try{if(loginRemember.checked){localStorage.setItem('lucas_login_email',loginEmail.value.trim());if(window.PasswordCredential&&navigator.credentials){await navigator.credentials.store(new PasswordCredential({id:loginEmail.value.trim(),password:loginPassword.value,name:loginEmail.value.trim()}))}}else{localStorage.removeItem('lucas_login_email')}}catch{}}
async function login(){authError('');try{const d=await api('/auth/login',{method:'POST',body:JSON.stringify({email:loginEmail.value,password:loginPassword.value,remember:!!loginRemember.checked})});if(d.verification_required){pendingLoginChallenge=d.challenge_id;loginVerifyEmailLabel.textContent=d.email||loginEmail.value;loginForm.classList.add('hidden');registerForm.classList.add('hidden');loginVerifyForm.classList.remove('hidden');setTimeout(()=>loginVerifyCode.focus(),50);return}await rememberCredential();await boot()}catch(e){authError(e.message)}}
async function verifyLogin(){authError('');try{await api('/auth/login/verify',{method:'POST',body:JSON.stringify({challenge_id:pendingLoginChallenge,code:loginVerifyCode.value})});await rememberCredential();pendingLoginChallenge='';loginVerifyCode.value='';await boot()}catch(e){authError(e.message)}}
function cancelLoginVerification(){pendingLoginChallenge='';loginVerifyCode.value='';authError('');loginVerifyForm.classList.add('hidden');loginForm.classList.remove('hidden')}
function togglePassword(id,button){const input=document.getElementById(id),show=input.type==='password';input.type=show?'text':'password';button.textContent=show?'🙈':'👁';button.setAttribute('aria-label',show?'Hide password':'Show password');button.title=show?'Hide password':'Show password'}""",
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


def _login_ip(request: Request) -> str:
    return gateway._client_ip(request)


def _set_access_cookie(response: JSONResponse, user) -> JSONResponse:
    token = gateway.auth.issue_token(user)
    response.set_cookie(
        "gwc_access_token",
        token,
        httponly=True,
        secure=gateway.settings.public_base_url.startswith("https://"),
        samesite="lax",
        max_age=gateway.settings.jwt_ttl_seconds,
    )
    return response


async def secure_auth_login(request: Request):
    try:
        body = await request.json()
        email = str(body.get("email") or "").strip().lower()
        password = str(body.get("password") or "")
        remember = bool(body.get("remember"))
        ip_address = _login_ip(request)
        if not gateway.registration_security.allow(f"login:{ip_address}:{email}", 10, 600):
            return JSONResponse({"error": "Too many login attempts. Try again later."}, status_code=429)
        user = gateway.auth.login(email, password)
        trusted_cookie = request.cookies.get("gwc_trusted_login_device", "")
        if remember and gateway.registration_security.is_trusted_login(user.id, trusted_cookie, ip_address):
            gateway.auth.audit(user.id, "auth.login_trusted_device", details={"ip_changed": False})
            return _set_access_cookie(JSONResponse({"access_token": "cookie", "token_type": "bearer", "user": user.__dict__}), user)
        if not email_verification_enabled():
            return JSONResponse({"error": "Email verification is required but email service is not configured"}, status_code=503)
        challenge_id, code = gateway.registration_security.start_login_verification(user.id, user.email, ip_address, remember)
        send_verification_email(user.email, code)
        gateway.auth.audit(user.id, "auth.login_verification_sent", details={"remember_device": remember})
        return JSONResponse({"verification_required": True, "challenge_id": challenge_id, "email": user.email}, status_code=202)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


async def secure_auth_login_verify(request: Request):
    try:
        body = await request.json()
        ip_address = _login_ip(request)
        user_id, remember, trusted_token = gateway.registration_security.verify_login(str(body.get("challenge_id") or ""), str(body.get("code") or ""), ip_address)
        user = gateway.auth.get_user(user_id)
        gateway.auth.audit(user.id, "auth.login_verified", details={"remember_device": remember})
        response = _set_access_cookie(JSONResponse({"access_token": "cookie", "token_type": "bearer", "user": user.__dict__}), user)
        if remember and trusted_token:
            response.set_cookie(
                "gwc_trusted_login_device",
                trusted_token,
                httponly=True,
                secure=gateway.settings.public_base_url.startswith("https://"),
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
            )
        else:
            response.delete_cookie("gwc_trusted_login_device")
        return response
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)


for path, handler, methods in (
    ("/auth/login", secure_auth_login, ["POST"]),
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
        if scope["type"] == "http" and path.startswith("/api/") and path != "/api/logout":
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
