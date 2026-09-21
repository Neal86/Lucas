from __future__ import annotations

HTML_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def html_no_cache_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(HTML_NO_CACHE_HEADERS)
    if extra:
        headers.update(extra)
    return headers
