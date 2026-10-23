from functools import lru_cache

from starlette.responses import Response

from .browser_extension_archive import extension_archive


@lru_cache(maxsize=1)
def _package() -> bytes:
    return extension_archive()


async def download_browser_extension(_request):
    return Response(_package(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="Lucas-Browser-Bridge.zip"',
        "Cache-Control": "no-store",
    })
