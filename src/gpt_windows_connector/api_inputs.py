"""Small shared HTTP input boundary for JSON object request bodies."""
from __future__ import annotations

from typing import Any

from starlette.requests import Request


async def read_json_object(request: Request) -> dict[str, Any]:
    """Reject malformed or non-object JSON without coercing valid empty objects."""
    body = await request.json()
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    return body
