"""Desktop account HTTP client with origin-bound, protected session storage."""
from __future__ import annotations

import ipaddress
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
import uuid

import httpx

from .credential_vault import protect_text, unprotect_text
from .local_account_state import AccountOperation, AccountState, RequestOwner, StaleAccountOperation, finite_number


def normalize_account_origin(value: str) -> str:
    """Accept an origin or the configured node WebSocket URL, never credentials."""
    if not isinstance(value, str) or any(ord(c) < 33 for c in value.strip()) or "\\" in value:
        raise ValueError("Invalid Lucas account server URL")
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
        host, port = parsed.hostname, parsed.port
        if (scheme not in {"https", "http"} or not host or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or "?" in raw or "#" in raw or parsed.path not in {"", "/", "/ws/node", "/ws/node/"}):
            raise ValueError
        if "%" in host:
            raise ValueError
        if ":" in host:
            host = str(ipaddress.IPv6Address(host))
            hostname = f"[{host}]"
        else:
            host = host.encode("idna").decode("ascii").lower()
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                raise ValueError
            hostname = host
        if scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError
        if port is not None and port != (443 if scheme == "https" else 80):
            hostname += f":{port}"
        return f"{scheme}://{hostname}"
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Lucas account URL must be a credential-free HTTPS origin (HTTP is local-only)") from exc


class LocalAccountClient:
    """DPAPI-protected, origin/account-bound desktop authentication.

    All clients sharing a state path coordinate in this process. Cancellation
    prevents stale local commits, not effects of already-dispatched HTTP writes.
    """
    def __init__(self, base_url: str, state_path: Path, *,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._base_url = normalize_account_origin(base_url)
        self.state_path = Path(state_path)
        self._state = AccountState(self._base_url, self.state_path)
        self._transport = transport

    @property
    def base_url(self) -> str:
        return self._base_url

    _normalize_base_url = staticmethod(normalize_account_origin)

    @property
    def generation(self) -> int:
        return self._state.generation

    def new_operation(self) -> AccountOperation:
        return self._state.operation()

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(timeout=timeout, transport=self._transport, follow_redirects=False, trust_env=False)

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except (ValueError, UnicodeError) as exc:
            raise ValueError("Lucas returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise ValueError("Lucas returned an invalid response")
        return payload

    @staticmethod
    def _error(response: httpx.Response, fallback: str) -> str:
        try:
            message = LocalAccountClient._payload(response).get("error")
            return message[:400] if isinstance(message, str) and message else fallback
        except ValueError:
            return fallback

    def _check_response(self, response: httpx.Response, fallback: str,
                        owner: RequestOwner | None = None) -> None:
        if owner is not None:
            with self._state.lock:
                self._state.check_owner(owner)
        if response.status_code == 401 and owner is not None:
            self._state.logout(owner=owner)
            raise PermissionError("Lucas account session expired")
        if not 200 <= response.status_code < 300:
            raise PermissionError(self._error(response, fallback))

    @staticmethod
    def _text(payload: dict[str, Any], key: str, default: str = "") -> str:
        value = payload.get(key, default)
        return value if isinstance(value, str) else default

    def status(self) -> dict[str, Any]:
        with self._state.lock:
            data = self._state.state()
            signed_in = False
            if data:
                try:
                    signed_in = bool(unprotect_text(data["access_token_dpapi"])) and bool(self._state.state())
                except Exception:
                    pass
            if not signed_in:
                return {"signed_in": False, "email": "", "name": "", "user_id": "",
                        "generation": self.generation, "expires_at": None}
            return {"signed_in": True, "email": self._text(data, "email"),
                    "name": self._text(data, "name"), "user_id": data["user_id"],
                    "generation": self.generation, "expires_at": data["expires_at"]}

    def _store_login_payload(self, payload: dict[str, Any], operation: AccountOperation,
                             started_at: float, fallback_email: str = "") -> dict[str, Any]:
        token = self._text(payload, "access_token")
        user = payload.get("user")
        if (not token or token == "cookie" or len(token) > 16384 or "\r" in token or "\n" in token
                or not isinstance(user, dict) or not self._text(user, "id").strip()):
            raise PermissionError("Lucas did not return a valid desktop account token and user")
        ttl = payload.get("expires_in")
        if (not finite_number(ttl) or ttl <= 0 or not finite_number(started_at + ttl)):
            raise ValueError("Lucas returned an invalid session lifetime")
        expires_at = started_at + ttl
        if not started_at <= time.time() < expires_at:
            raise PermissionError("Lucas account session expired; sign in again")
        protected = protect_text(token)
        if not isinstance(protected, str) or not protected or protected == token:
            raise RuntimeError("Credential protection failed")
        state = {"version": 1, "origin": self.base_url, "session_id": uuid.uuid4().hex,
                 "access_token_dpapi": protected, "user_id": user["id"],
                 "email": self._text(user, "email", fallback_email), "name": self._text(user, "name"),
                 "provider": self._text(user, "provider"), "issued_at": started_at, "expires_at": expires_at}
        self._state.login_commit(operation, state)
        with self._state.lock:
            self._state.check_operation(operation)
            return self.status()

    def login(self, email: str, password: str, timeout: float = 20.0, *,
              operation: AccountOperation | None = None) -> dict[str, Any]:
        email = str(email or "").strip()
        if not email or not isinstance(password, str) or not password:
            raise ValueError("Enter your email and password")
        operation = operation or self.new_operation()
        self._state.begin_login(operation)
        started_at = time.time()
        with self._client(timeout) as client:
            response = client.post(self.base_url + "/auth/desktop/login", json={"email": email, "password": password})
        with self._state.lock:
            self._state.check_operation(operation)
            self._check_response(response, "Sign in failed")
            payload = self._payload(response)
            if "verification_required" in payload and type(payload["verification_required"]) is not bool:
                raise ValueError("Lucas returned an invalid verification response")
            if payload.get("verification_required") is True:
                challenge = self._text(payload, "challenge_id").strip()
                if not challenge:
                    raise ValueError("Lucas returned an invalid verification challenge")
                challenge_email = self._text(payload, "email", email)
                self._state.challenge(operation, challenge, challenge_email)
                return {"verification_required": True, "challenge_id": challenge,
                        "email": challenge_email, "generation": operation.generation}
            return self._store_login_payload(payload, operation, started_at, email)

    def verify_login(self, challenge_id: str, code: str, timeout: float = 20.0, *,
                     operation: AccountOperation | None = None) -> dict[str, Any]:
        operation = operation or self.new_operation()
        challenge_id, code = str(challenge_id or "").strip(), str(code or "").strip()
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("Enter the 6-digit verification code")
        with self._state.lock:
            pending = self._state.check_challenge(challenge_id, operation)
            email = str(pending.get("email") or "")
            sequence = self._state.shared.sequence.get("verify", 0) + 1
            self._state.shared.sequence["verify"] = sequence
        started_at = time.time()
        with self._client(timeout) as client:
            response = client.post(self.base_url + "/auth/desktop/login/verify", json={"challenge_id": challenge_id, "code": code})
        with self._state.lock:
            self._state.check_challenge(challenge_id, operation)
            if sequence != self._state.shared.sequence.get("verify"):
                raise StaleAccountOperation("Verification was superseded")
            self._check_response(response, "Verification failed")
            return self._store_login_payload(self._payload(response), operation, started_at, email)

    def resend_login(self, challenge_id: str, timeout: float = 20.0, *,
                     operation: AccountOperation | None = None) -> dict[str, Any]:
        operation = operation or self.new_operation()
        challenge_id = str(challenge_id or "").strip()
        with self._state.lock:
            self._state.check_challenge(challenge_id, operation)
        with self._client(timeout) as client:
            response = client.post(self.base_url + "/auth/desktop/login/resend", json={"challenge_id": challenge_id})
        with self._state.lock:
            self._state.check_challenge(challenge_id, operation)
            self._check_response(response, "Could not resend verification code")
            return self._payload(response)

    def cancel_pending_login(self, *, generation: int | None = None) -> None:
        self._state.cancel_login(generation)

    def logout(self, *, generation: int | None = None) -> None:
        self._state.logout(generation=generation)

    def _request(self, method: str, path: str, timeout: float, kind: str, operation: AccountOperation | None,
                 **kwargs: Any) -> tuple[httpx.Response, RequestOwner]:
        owner = self._state.request(kind, operation)
        with self._state.lock:
            self._state.check_owner(owner)
            try:
                token = unprotect_text(owner.token_protected)
            except Exception as exc:
                raise PermissionError("Could not unlock the Lucas session; sign in again") from exc
            if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
                raise PermissionError("Could not unlock the Lucas session; sign in again")
        with self._client(timeout) as client:
            response = client.request(method, self.base_url + path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        self._check_response(response, "Lucas account request failed", owner)
        return response, owner

    def me(self, timeout: float = 15.0, *, operation: AccountOperation | None = None) -> dict[str, Any]:
        response, owner = self._request("GET", "/auth/me", timeout, "me", operation)
        user = self._payload(response).get("user")
        if not isinstance(user, dict) or self._text(user, "id") != owner.user_id:
            raise ValueError("Lucas returned an invalid account response")
        with self._state.lock:
            self._state.check_owner(owner)
            return user

