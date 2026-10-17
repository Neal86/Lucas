"""Desktop response adapter over the shared password/challenge policy."""
from . import login_policy


class DesktopAuthApi:
    def __init__(self, gateway):
        self.gateway = gateway

    async def _call(self, method, request):
        gw = self.gateway
        response = await method(request, gw.auth, gw.registration_security, gw.settings,
                                gw._client_ip, desktop=True)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    async def login(self, request):
        return await self._call(login_policy.login, request)

    async def verify(self, request):
        return await self._call(login_policy.verify, request)

    async def resend(self, request):
        return await self._call(login_policy.resend, request)
