"""One password-login policy for the dashboard, standalone gateway and OAuth UI.

Rate buckets remain process-local, as before. Deployments needing a global
limit must apply one at the trusted ingress or use a shared rate store.
"""
from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import JSONResponse

from .registration_security import email_verification_enabled, send_verification_email


def _set_access_cookie(response: JSONResponse, user, auth, settings) -> JSONResponse:
    token = auth.issue_token(user)
    response.set_cookie(
        "gwc_access_token",
        token,
        httponly=True,
        secure=settings.public_base_url.startswith("https://"),
        samesite="lax",
        max_age=settings.jwt_ttl_seconds,
    )
    return response


async def login(request: Request, auth, security, settings, client_ip):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        email = str(body.get("email") or "").strip().lower()
        password = str(body.get("password") or "")
        remember = bool(body.get("remember"))
        ip_address = client_ip(request)
        if not security.allow(f"login:{ip_address}:{email}", 10, 600):
            return JSONResponse({"error": "Too many login attempts. Try again later."}, status_code=429)
        user = auth.login(email, password)
        bypass_login_verification = os.getenv("GWC_BYPASS_LOGIN_VERIFICATION", "").strip().lower() in {"1", "true", "yes", "on"}
        if bypass_login_verification:
            auth.audit(user.id, "auth.login_staging_bypass")
            return _set_access_cookie(JSONResponse({"access_token": "cookie", "token_type": "bearer", "user": user.__dict__}), user, auth, settings)
        trusted_cookie = request.cookies.get("gwc_trusted_login_device", "")
        if remember and security.is_trusted_login(user.id, trusted_cookie, ip_address):
            auth.audit(user.id, "auth.login_trusted_device", details={"ip_changed": False})
            return _set_access_cookie(JSONResponse({"access_token": "cookie", "token_type": "bearer", "user": user.__dict__}), user, auth, settings)
        if not email_verification_enabled():
            return JSONResponse({"error": "Email verification is required but email service is not configured"}, status_code=503)
        challenge_id, code = security.start_login_verification(user.id, user.email, ip_address, remember)
        send_verification_email(user.email, code)
        auth.audit(user.id, "auth.login_verification_sent", details={"remember_device": remember})
        return JSONResponse({"verification_required": True, "challenge_id": challenge_id, "email": user.email}, status_code=202)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


async def resend(request: Request, auth, security, settings, client_ip):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        challenge_id = str(body.get("challenge_id") or "").strip()
        ip_address = client_ip(request)
        if not security.allow(f"login-resend:{ip_address}:{challenge_id}", 6, 3600):
            return JSONResponse({"error": "Too many resend attempts. Try again later."}, status_code=429)
        user_id, email, code = security.resend_login_verification(challenge_id, ip_address)
        send_verification_email(email, code)
        auth.audit(user_id, "auth.login_verification_resent")
        return JSONResponse({"ok": True, "email": email})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


async def verify(request: Request, auth, security, settings, client_ip):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        ip_address = client_ip(request)
        user_id, remember, trusted_token = security.verify_login(str(body.get("challenge_id") or ""), str(body.get("code") or ""), ip_address)
        user = auth.get_user(user_id)
        auth.audit(user.id, "auth.login_verified", details={"remember_device": remember})
        response = _set_access_cookie(JSONResponse({"access_token": "cookie", "token_type": "bearer", "user": user.__dict__}), user, auth, settings)
        if remember and trusted_token:
            response.set_cookie(
                "gwc_trusted_login_device",
                trusted_token,
                httponly=True,
                secure=settings.public_base_url.startswith("https://"),
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
            )
        else:
            response.delete_cookie("gwc_trusted_login_device")
        return response
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)

