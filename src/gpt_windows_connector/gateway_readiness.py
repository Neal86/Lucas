from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def readiness_checks(db_path: Path, settings, billing, email_verification_enabled) -> dict[str, bool]:
    db_ok = True
    try:
        with sqlite3.connect(db_path, timeout=3) as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False
    return {
        "database": db_ok,
        "jwt_secret": bool(settings.jwt_secret),
        "super_admin_configured": bool(os.getenv("GWC_SUPER_ADMIN_EMAIL", "").strip()),
        "email_verification": bool(email_verification_enabled()),
        "google_oauth": bool(settings.google_client_id and settings.google_client_secret),
        "turnstile": bool(os.getenv("GWC_TURNSTILE_SECRET_KEY", "").strip()),
        "stripe_checkout": bool(billing.checkout_configured),
        "stripe_annual": bool(billing.annual_checkout_configured),
        "stripe_webhook": bool(billing.webhook_configured),
    }


def critical_ready(checks: dict[str, bool]) -> bool:
    return bool(checks.get("database") and checks.get("jwt_secret") and checks.get("super_admin_configured"))
