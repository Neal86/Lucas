from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from . import gateway, webapp


def _embedded_logo(filename: str) -> str:
    """Return an exact bundled PNG as a data URI; never transform the artwork."""
    try:
        payload = (webapp.BRAND_ASSET_DIR / filename).read_text(encoding="utf-8").strip()
    except OSError:
        payload = ""
    return f"data:image/png;base64,{payload}" if payload else ""


# Exactly two horizontal brand sources are used on the web UI.
# Light surfaces use the user's blue original; dark surfaces use the user's white original.
BLUE_LOGO_SRC = _embedded_logo("lucas-logo-auth-blue.png.b64")
WHITE_LOGO_SRC = _embedded_logo("lucas-logo-white.png.b64")


html = webapp.DASHBOARD_HTML

# Keep the landing navigation text as bright as the adjacent action text.
html = html.replace(
    '.landing-links a,.landing-footer{color:#8e98ae}',
    '.landing-links a{color:#dfe4f3}.landing-footer{color:#8e98ae}',
)

# Replace every horizontal brand surface directly with one of the two embedded originals.
if WHITE_LOGO_SRC:
    html = html.replace(
        '<nav class="landing-nav"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        f'<nav class="landing-nav"><div class="landing-logo"><img src="{WHITE_LOGO_SRC}" alt="Lucas" /></div>',
    )
    html = html.replace(
        '<footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        f'<footer class="landing-footer"><div class="landing-logo"><img src="{WHITE_LOGO_SRC}" alt="Lucas" /></div>',
    )
    html = html.replace(
        '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        f'<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="{WHITE_LOGO_SRC}" alt="Lucas" /></div>',
    )

if BLUE_LOGO_SRC:
    html = html.replace(
        '<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        f'<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="{BLUE_LOGO_SRC}" alt="Lucas" /></div>',
    )

# One sizing block only. No filter, invert, opacity tricks, asset routes, or cache-version chains.
html = html.replace(
    '</head>',
    '<style>'
    '.auth-card .brand{height:140px;display:flex;align-items:center;justify-content:center;margin:0 0 18px}'
    '.auth-card .brand img{display:block;width:300px;max-width:92%;max-height:120px;height:auto;object-fit:contain;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important}'
    '.side .logo{height:96px!important;min-height:96px!important;padding:10px 14px!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;overflow:hidden!important}'
    '.side .logo img{display:block!important;width:205px!important;max-width:205px!important;max-height:76px!important;height:auto!important;object-fit:contain!important;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important;margin:0!important}'
    '.landing-logo img{display:block!important;height:52px!important;width:auto!important;max-width:220px!important;object-fit:contain!important;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important}'
    '</style></head>',
)

webapp.DASHBOARD_HTML = html


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
    uvicorn.run(app, host=gateway.settings.host, port=gateway.settings.port, log_level="info")


if __name__ == "__main__":
    main()
