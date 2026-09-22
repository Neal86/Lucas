from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse


class DesktopAuthApi:
    """Token login flow for the installed Lucas desktop app.

    Browser login keeps using HttpOnly cookies. The desktop app receives a bearer
    token only after password validation and the existing email verification
    challenge, then protects that token locally with Windows DPAPI.
    """

    def __init__(self, gateway, send_verification_email, email_verification_enabled) -> None:
        self.gateway = gateway
        self.send_verification_email = send_verification_email
        self.email_verification_enabled = email_verification_enabled

    def _ip(self, request: Request) -> str:
        return self.gateway._client_ip(request)

    def _token_response(self, user) -> JSONResponse:
        token = self.gateway.auth.issue_token(user)
        return JSONResponse({
            "access_token": token,
            "token_type": "bearer",
            "expires_in": self.gateway.settings.jwt_ttl_seconds,
            "user": user.__dict__,
        })

    async def login(self, request: Request):
        try:
            body = await request.json()
            email = str(body.get("email") or "").strip().lower()
            password = str(body.get("password") or "")
            ip_address = self._ip(request)
            if not self.gateway.registration_security.allow(f"desktop-login:{ip_address}:{email}", 10, 600):
                return JSONResponse({"error": "Too many login attempts. Try again later."}, status_code=429)
            user = self.gateway.auth.login(email, password)
            bypass = self.gateway.os.getenv("GWC_BYPASS_LOGIN_VERIFICATION", "").strip().lower() in {"1", "true", "yes", "on"}
            if bypass:
                self.gateway.auth.audit(user.id, "auth.desktop_login_staging_bypass")
                return self._token_response(user)
            if not self.email_verification_enabled():
                return JSONResponse({"error": "Email verification is required but email service is not configured"}, status_code=503)
            challenge_id, code = self.gateway.registration_security.start_login_verification(
                user.id, user.email, ip_address, False
            )
            self.send_verification_email(user.email, code)
            self.gateway.auth.audit(user.id, "auth.desktop_login_verification_sent")
            return JSONResponse(
                {"verification_required": True, "challenge_id": challenge_id, "email": user.email},
                status_code=202,
            )
        except PermissionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)

    async def verify(self, request: Request):
        try:
            body = await request.json()
            user_id, _remember, _trusted_token = self.gateway.registration_security.verify_login(
                str(body.get("challenge_id") or ""),
                str(body.get("code") or ""),
                self._ip(request),
            )
            user = self.gateway.auth.get_user(user_id)
            self.gateway.auth.audit(user.id, "auth.desktop_login_verified")
            return self._token_response(user)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except PermissionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

    async def resend(self, request: Request):
        try:
            body = await request.json()
            challenge_id = str(body.get("challenge_id") or "").strip()
            ip_address = self._ip(request)
            if not self.gateway.registration_security.allow(f"desktop-login-resend:{ip_address}:{challenge_id}", 6, 3600):
                return JSONResponse({"error": "Too many resend attempts. Try again later."}, status_code=429)
            user_id, email, code = self.gateway.registration_security.resend_login_verification(challenge_id, ip_address)
            self.send_verification_email(email, code)
            self.gateway.auth.audit(user_id, "auth.desktop_login_verification_resent")
            return JSONResponse({"ok": True, "email": email})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)
