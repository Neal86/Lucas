from __future__ import annotations

import asyncio
import json
import logging
import time
from urllib.parse import urlencode

import websockets

from .config import NodeSettings
from .executor import Executor

log = logging.getLogger("gwc.node")


def _load_saved_token(settings: NodeSettings) -> str | None:
    if settings.node_token:
        return settings.node_token
    try:
        data = json.loads(settings.state_file.read_text(encoding="utf-8"))
        return data.get("node_token")
    except (OSError, json.JSONDecodeError):
        return None


def _save_token(settings: NodeSettings, token: str) -> None:
    tmp = settings.state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps({"node_id": settings.node_id, "node_token": token}, indent=2), encoding="utf-8")
    tmp.replace(settings.state_file)


async def _serve_connection(settings: NodeSettings, executor: Executor) -> None:
    query = urlencode({"node_id": settings.node_id})
    uri = settings.gateway_ws_url + ("&" if "?" in settings.gateway_ws_url else "?") + query
    token = _load_saved_token(settings)
    async with websockets.connect(uri, ping_interval=20, ping_timeout=20, max_size=32 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "type": "hello",
            "node_id": settings.node_id,
            "name": settings.node_name,
            "node_token": token,
            "pairing_code": settings.pairing_code,
        }))
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if not welcome.get("ok"):
            raise RuntimeError(welcome.get("error") or "Gateway rejected node")
        if welcome.get("node_token"):
            _save_token(settings, welcome["node_token"])
        log.info("Connected as %s (%s)", settings.node_name, settings.node_id)

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
            except asyncio.TimeoutError:
                await ws.send(json.dumps({"type": "heartbeat", "time": time.time()}))
                continue
            message = json.loads(raw)
            if message.get("type") != "request":
                continue
            request_id = message.get("id")
            try:
                result = await executor.call(message.get("method", ""), message.get("params") or {})
                response = {"type": "response", "id": request_id, "ok": True, "result": result}
            except Exception as exc:
                log.exception("Execution failed: %s", message.get("method"))
                response = {"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            await ws.send(json.dumps(response, ensure_ascii=False))


async def run_node() -> None:
    settings = NodeSettings.from_env()
    executor = Executor(settings.allowed_roots)
    delay = 1.0
    while True:
        try:
            await _serve_connection(settings, executor)
            delay = 1.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Disconnected: %s; retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run_node())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
