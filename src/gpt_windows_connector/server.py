from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import gateway, webapp


# Brand assets are intentionally split by surface so light/dark UI never share
# a logo that needs CSS inversion or opacity tricks.
BRAND_ASSETS = {
    "lucas-logo-home-square-white.png": "lucas-logo-home-square-white.png",
    "lucas-logo-horizontal-blue.png": "lucas-logo-horizontal-blue.png",
    "lucas-logo-horizontal-white.png": "lucas-logo-horizontal-white.png",
}


# Apply the surface-specific artwork directly to the existing single-page UI.
# Keep these replacements narrowly scoped to branding/presentation only.
webapp.DASHBOARD_HTML = (
    webapp.DASHBOARD_HTML
    .replace("filter:brightness(0) invert(1)!important", "filter:none!important")
    .replace("filter:brightness(0) invert(1)", "filter:none")
    .replace(
        '.landing-links a,.landing-footer{color:#8e98ae}',
        '.landing-links a{color:#dfe4f3}.landing-footer{color:#8e98ae}',
    )
    .replace(
        '<link rel="icon" type="image/png" href="/assets/lucas-logo-square.png" />',
        '<link rel="icon" type="image/png" href="/assets/lucas-logo-home-square-white.png?v=brand-split-20260830" />',
    )
    .replace(
        '<nav class="landing-nav"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        '<nav class="landing-nav"><div class="landing-logo"><img src="/assets/lucas-logo-home-square-white.png?v=brand-split-20260830" alt="Lucas" /></div>',
    )
    .replace(
        '<div class="core-ring"><img src="/assets/lucas-logo-square.png" alt="Lucas" /></div>',
        '<div class="core-ring"><img src="/assets/lucas-logo-home-square-white.png?v=brand-split-20260830" alt="Lucas" /></div>',
    )
    .replace(
        '<footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        '<footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal-white.png?v=brand-split-20260830" alt="Lucas" /></div>',
    )
    .replace(
        '<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        '<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="/assets/lucas-logo-horizontal-blue.png?v=brand-split-20260830" alt="Lucas" /></div>',
    )
    .replace(
        '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>',
        '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal-white.png?v=brand-split-20260830" alt="Lucas" /></div>',
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


# Serve only the three explicitly separated brand resources without widening
# the legacy webapp asset route.
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
