from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import gateway, webapp


# Brand assets are intentionally split by surface so light/dark UI never share
# a logo that needs different source artwork.
BRAND_ASSETS = {
    "lucas-logo-home-square-white.png": "lucas-logo-home-square-white.png",
    "lucas-logo-horizontal-blue.png": "lucas-logo-horizontal-blue.png",
    "lucas-logo-horizontal-white.png": "lucas-logo-horizontal-white.png",
}

# The auth-page blue logo is stored as base64 text so the exact user-supplied
# artwork can be embedded directly without another image-processing step.
try:
    AUTH_LOGO_B64 = (webapp.BRAND_ASSET_DIR / "lucas-logo-auth-blue.png.b64").read_text(encoding="utf-8").strip()
    AUTH_LOGO_SRC = f"data:image/png;base64,{AUTH_LOGO_B64}" if AUTH_LOGO_B64 else "/assets/lucas-logo-horizontal-blue.png"
except OSError:
    AUTH_LOGO_SRC = "/assets/lucas-logo-horizontal-blue.png"


# Apply surface-specific artwork directly to the existing single-page UI.
webapp.DASHBOARD_HTML = (
    webapp.DASHBOARD_HTML
    .replace("filter:brightness(0) invert(1)!important", "filter:none!important")
    .replace("filter:brightness(0) invert(1)", "filter:none")
    .replace(
        '.landing-links a,.landing-footer{color:#8e98ae}',
        '.landing-links a{color:#dfe4f3}.landing-footer{color:#8e98ae}',
    )
    .replace(
        '.logo{height:64px;min-height:64px;padding:4px 10px 14px;',
        '.logo{height:104px;min-height:104px;padding:10px 10px 12px;',
    )
    .replace(
        '.logo img{display:block;width:184px;height:auto;background:transparent;border-radius:0;padding:0;filter:none!important}',
        '.logo img{display:block;width:230px;max-width:100%;height:auto;background:transparent;border-radius:0;padding:0;filter:brightness(0) invert(1)!important;opacity:1}',
    )
    .replace(
        '.landing-logo img{display:block;height:44px;width:auto;background:transparent;border-radius:0;padding:0;filter:none}',
        '.landing-logo img{display:block;height:54px;width:auto;background:transparent;border-radius:0;padding:0;filter:brightness(0) invert(1);opacity:1}',
    )
    .replace(
        '<link rel="icon" type="image/png" href="/assets/lucas-logo-square.png" />',
        '<link rel="icon" type="image/png" href="/assets/lucas-logo-home-square-white.png?v=brand-auth-final-20260831" />',
    )
    .replace(
        '<nav class="landing-nav"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        '<nav class="landing-nav"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal-white.png?v=brand-auth-final-20260831" alt="Lucas" /></div>',
    )
    .replace(
        '<div class="core-ring"><img src="/assets/lucas-logo-square.png" alt="Lucas" /></div>',
        '<div class="core-ring"><img src="/assets/lucas-logo-home-square-white.png?v=brand-auth-final-20260831" alt="Lucas" /></div>',
    )
    .replace(
        '<footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        '<footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal-white.png?v=brand-auth-final-20260831" alt="Lucas" /></div>',
    )
    .replace(
        '<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        f'<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="{AUTH_LOGO_SRC}" alt="Lucas" /></div>',
    )
    .replace(
        '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal-white.png?v=brand-auth-final-20260831" alt="Lucas" /></div>',
    )
    .replace(
        '</head>',
        '<style>.auth-card .brand{height:150px;display:flex;align-items:center;justify-content:center;margin:0 0 18px}.auth-card .brand img{display:block;width:310px;max-width:92%;height:auto;object-fit:contain;filter:none!important;opacity:1}</style></head>',
    )
)


async def split_brand_asset(request):
    name = str(request.path_params.get("name") or "")
    filename = BRAND_ASSETS.get(name)
    if not filename:
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(
        webapp.BRAND_ASSET_DIR / filename,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


for _asset_name in BRAND_ASSETS:
    _asset_path = f"/assets/{_asset_name}"
    if not any(getattr(r, "path", None) == _asset_path for r in webapp.routes):
        webapp.routes.insert(0, Route(_asset_path, split_brand_asset, methods=["GET"]))


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
