"""Desktop account login composition; integration synchronization is excluded."""
from starlette.routing import Route
from .desktop_auth import DesktopAuthApi

DESKTOP_AUTH_PATHS = {"/auth/desktop/login", "/auth/desktop/login/verify", "/auth/desktop/login/resend"}


def desktop_account_routes(gateway):
    desktop = DesktopAuthApi(gateway)
    return [
        Route("/auth/desktop/login", desktop.login, methods=["POST"]),
        Route("/auth/desktop/login/verify", desktop.verify, methods=["POST"]),
        Route("/auth/desktop/login/resend", desktop.resend, methods=["POST"]),
    ]
