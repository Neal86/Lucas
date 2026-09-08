from __future__ import annotations


def claim_referral_cookie(request, referral_service, user_id: str) -> None:
    code = str(request.cookies.get("lucas_ref") or "").strip()
    if code:
        referral_service.claim(user_id, code)
