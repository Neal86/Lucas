from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger("lucas.meta_capi")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


class MetaConversionsAPI:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.pixel_id = os.getenv("META_PIXEL_ID", "").strip()
        self.access_token = os.getenv("META_CAPI_ACCESS_TOKEN", "").strip()
        self.test_event_code = os.getenv("META_TEST_EVENT_CODE", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.pixel_id and self.access_token)

    def _payload(
        self,
        event_name: str,
        *,
        event_id: str,
        email: str = "",
        user_id: str = "",
        source_url: str = "",
        client_ip: str = "",
        user_agent: str = "",
        fbp: str = "",
        fbc: str = "",
        custom_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_data: dict[str, Any] = {}
        if email:
            user_data["em"] = [_sha256(email)]
        if user_id:
            user_data["external_id"] = [_sha256(user_id)]
        if client_ip and client_ip != "unknown":
            user_data["client_ip_address"] = client_ip
        if user_agent:
            user_data["client_user_agent"] = user_agent
        if fbp:
            user_data["fbp"] = fbp
        if fbc:
            user_data["fbc"] = fbc
        event: dict[str, Any] = {
            "event_name": event_name,
            "event_time": int(time.time()),
            "event_id": event_id,
            "action_source": "website",
            "event_source_url": source_url or self.base_url,
            "user_data": user_data,
        }
        if custom_data:
            event["custom_data"] = custom_data
        payload: dict[str, Any] = {"data": [event]}
        if self.test_event_code:
            payload["test_event_code"] = self.test_event_code
        return payload

    def _endpoint(self) -> str:
        return f"https://graph.facebook.com/{self.pixel_id}/events"

    def send(self, event_name: str, **kwargs: Any) -> bool:
        if not self.enabled:
            return False
        try:
            response = httpx.post(
                self._endpoint(),
                params={"access_token": self.access_token},
                json=self._payload(event_name, **kwargs),
                timeout=8.0,
            )
            response.raise_for_status()
            return True
        except Exception as exc:
            log.warning("Meta CAPI event failed event=%s error=%s", event_name, exc)
            return False

    async def send_async(self, event_name: str, **kwargs: Any) -> bool:
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    self._endpoint(),
                    params={"access_token": self.access_token},
                    json=self._payload(event_name, **kwargs),
                )
                response.raise_for_status()
            return True
        except Exception as exc:
            log.warning("Meta CAPI event failed event=%s error=%s", event_name, exc)
            return False
