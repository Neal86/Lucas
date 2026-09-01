from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import gateway, webapp


WHITE_LOGO_PATH = "/assets/lucas-logo-horizontal-white.png"
BLUE_LOGO_PATH = "/assets/lucas-logo-horizontal-blue.png"
WHITE_LOGO_URL = f"{WHITE_LOGO_PATH}?v=brand-20260901"
BLUE_LOGO_URL = f"{BLUE_LOGO_PATH}?v=brand-20260901"


html = webapp.DASHBOARD_HTML

# Public navigation text should match the bright adjacent action text.
html = html.replace(
    '.landing-links a,.landing-footer{color:#8e98ae}',
    '.landing-links a{color:#dfe4f3}.landing-footer{color:#8e98ae}',
)

# Use real PNG files directly on every surface. No base64, filters, recoloring,
# generated artwork, or fallback chains.
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

# Size only; never transform the logo artwork.
html = html.replace(
    '</head>',
    '<style>'
    '.auth-card .brand{height:140px;display:flex;align-items:center;justify-content:center;margin:0 0 18px}'
    '.auth-card .brand img{display:block;width:300px;max-width:92%;max-height:120px;height:auto;object-fit:contain;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important}'
    '.side .logo{height:96px!important;min-height:96px!important;padding:10px 14px!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;overflow:hidden!important}'
    '.side .logo img{display:block!important;width:205px!important;max-width:205px!important;max-height:76px!important;height:auto!important;object-fit:contain!important;object-position:left center!important;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important;margin:0!important}'
    '.landing-logo img{display:block!important;height:52px!important;width:auto!important;max-width:220px!important;object-fit:contain!important;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important}'
    '</style></head>',
)

webapp.DASHBOARD_HTML = html


async def brand_logo_asset(request):
    name = str(request.path_params.get("name") or "")
    if name == "white":
        filename = "lucas-logo-horizontal-white.png"
    elif name == "blue":
        filename = "lucas-logo-horizontal-blue.png"
    else:
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(
        webapp.BRAND_ASSET_DIR / filename,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate"},
    )


for path, name in ((WHITE_LOGO_PATH, "white"), (BLUE_LOGO_PATH, "blue")):
    if not any(getattr(r, "path", None) == path for r in webapp.routes):
        webapp.routes.insert(0, Route(path, brand_logo_asset, methods=["GET"], name=f"brand-logo-{name}"))


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
