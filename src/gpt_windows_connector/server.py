from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import gateway, webapp


# Keep the dark landing/dashboard surfaces on the white transparent logo.
# Use a separate blue Lucas logo only inside the light authentication card.
webapp.DASHBOARD_HTML = (
    webapp.DASHBOARD_HTML
    .replace("filter:brightness(0) invert(1)!important", "filter:none!important")
    .replace("filter:brightness(0) invert(1)", "filter:none")
    .replace(
        "/assets/lucas-logo-horizontal.png",
        "/assets/lucas-logo-horizontal.png?v=direct-white-20260829",
    )
    .replace(
        "/assets/lucas-logo-square.png",
        "/assets/lucas-logo-square.png?v=direct-white-20260829",
    )
    .replace(
        '<div class="brand"><img src="/assets/lucas-logo-horizontal.png?v=direct-white-20260829" alt="Lucas" /></div>',
        '<div class="brand"><img src="/assets/lucas-logo-horizontal-blue.png?v=auth-blue-20260830" alt="Lucas" /></div>',
    )
)


async def auth_blue_logo(_: object):
    return FileResponse(
        webapp.BRAND_ASSET_DIR / "lucas-logo-horizontal-blue.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# The auth-only logo route is intentionally separate so webapp.py does not need
# to widen the general brand-asset allowlist.
if not any(getattr(r, "path", None) == "/assets/lucas-logo-horizontal-blue.png" for r in webapp.routes):
    webapp.routes.insert(0, Route("/assets/lucas-logo-horizontal-blue.png", auth_blue_logo, methods=["GET"]))


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
