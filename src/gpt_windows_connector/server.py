from __future__ import annotations

import contextlib

import uvicorn
from starlette.applications import Starlette

from . import gateway, webapp


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with gateway.mcp.session_manager.run():
        yield


app = Starlette(routes=webapp.routes, lifespan=lifespan)


def main() -> None:
    uvicorn.run(app, host=gateway.settings.host, port=gateway.settings.port, log_level="info")


if __name__ == "__main__":
    main()
