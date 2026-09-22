from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from . import browser


@dataclass
class BrowserHandoff:
    token: str
    session_id: str
    page_index: int
    action_type: str
    message: str
    instructions: str
    url: str
    title: str
    created_at: float


_HANDOFFS: dict[str, BrowserHandoff] = {}
_MAX_HANDOFFS = 200


def classify_user_action(
    *,
    text: str = "",
    url: str = "",
    title: str = "",
    has_password: bool = False,
    has_otp: bool = False,
    has_captcha: bool = False,
) -> dict[str, Any] | None:
    haystack = " ".join([str(title or ""), str(url or ""), str(text or "")]).lower()

    if has_captcha or re.search(
        r"captcha|verify you are human|human verification|checking your browser|"
        r"人机验证|验证您是真人|安全验证|请完成验证",
        haystack,
    ):
        return {
            "action_type": "captcha",
            "message": "The site requires a human verification/CAPTCHA.",
            "instructions": "Complete the verification in the assigned browser, then tell the AI to continue.",
        }

    if has_otp or re.search(
        r"two[- ]factor|2fa|verification code|security code|authenticator code|"
        r"one[- ]time code|enter the code|短信验证码|验证码|两步验证|双重验证",
        haystack,
    ):
        return {
            "action_type": "2fa",
            "message": "The site requires a verification code or two-factor authentication.",
            "instructions": "Enter the verification code in the assigned browser, then tell the AI to continue.",
        }

    if re.search(
        r"passkey|security key|windows hello|use your phone to sign in|"
        r"通行密钥|安全密钥|windows hello",
        haystack,
    ):
        return {
            "action_type": "passkey",
            "message": "The site requires a passkey, security key, or device authentication.",
            "instructions": "Complete the device/passkey prompt, then tell the AI to continue.",
        }

    if re.search(
        r"verify your identity|identity verification|upload (?:your )?(?:id|identity)|"
        r"government[- ]issued id|business verification|upload business license|"
        r"身份验证|实名认证|上传证件|营业执照|企业认证",
        haystack,
    ):
        return {
            "action_type": "identity_verification",
            "message": "The site requires identity or business verification that needs user review.",
            "instructions": "Complete the identity/business verification in the browser, then tell the AI to continue.",
        }

    if has_password and re.search(r"/(?:login|signin|sign-in|auth)(?:[/?#]|$)|log in|sign in|登录|登入", haystack):
        return {
            "action_type": "login",
            "message": "The site is waiting for account login.",
            "instructions": "Log in in the assigned browser. Do not send passwords to the AI. Then tell the AI to continue.",
        }

    return None


def _prune() -> None:
    if len(_HANDOFFS) <= _MAX_HANDOFFS:
        return
    oldest = sorted(_HANDOFFS.values(), key=lambda item: item.created_at)
    for item in oldest[: len(_HANDOFFS) - _MAX_HANDOFFS]:
        _HANDOFFS.pop(item.token, None)


def _payload(item: BrowserHandoff) -> dict[str, Any]:
    return {
        "status": "requires_user_action",
        "requires_user_action": True,
        "action_type": item.action_type,
        "message": item.message,
        "instructions": item.instructions,
        "session_id": item.session_id,
        "page_index": item.page_index,
        "url": item.url,
        "title": item.title,
        "resume_token": item.token,
        "chat_message": (
            f"需要你的操作：{item.message} "
            "请直接在已保留的浏览器页面完成，完成后告诉我“好了，继续”。"
        ),
    }


async def request_user_action(
    session_id: str,
    page_index: int = 0,
    *,
    action_type: str = "manual",
    message: str = "This step requires user interaction.",
    instructions: str = "Complete the step in the assigned browser, then tell the AI to continue.",
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    token = uuid.uuid4().hex
    item = BrowserHandoff(
        token=token,
        session_id=session_id,
        page_index=int(page_index),
        action_type=str(action_type or "manual"),
        message=str(message or "This step requires user interaction."),
        instructions=str(instructions or "Complete the step in the assigned browser, then tell the AI to continue."),
        url=page.url,
        title=await page.title(),
        created_at=time.time(),
    )
    _HANDOFFS[token] = item
    _prune()
    return _payload(item)


async def check_user_action(
    session_id: str,
    page_index: int = 0,
    *,
    auto_create: bool = True,
    max_chars: int = 20000,
) -> dict[str, Any]:
    page = browser._page(session_id, page_index)
    try:
        text = (await page.locator("body").inner_text(timeout=4000))[: max(1000, min(int(max_chars or 20000), 50000))]
    except Exception:
        text = ""
    try:
        has_password = bool(await page.locator('input[type="password"]').count())
    except Exception:
        has_password = False
    try:
        has_otp = bool(await page.locator('input[autocomplete="one-time-code"]').count())
    except Exception:
        has_otp = False
    try:
        has_captcha = bool(
            await page.locator(
                'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare.com"], '
                '[data-sitekey], [class*="captcha" i], [id*="captcha" i]'
            ).count()
        )
    except Exception:
        has_captcha = False

    title = await page.title()
    detected = classify_user_action(
        text=text,
        url=page.url,
        title=title,
        has_password=has_password,
        has_otp=has_otp,
        has_captcha=has_captcha,
    )
    if not detected:
        return {
            "status": "ready",
            "requires_user_action": False,
            "session_id": session_id,
            "page_index": int(page_index),
            "url": page.url,
            "title": title,
        }
    if not auto_create:
        return {
            "status": "detected",
            "requires_user_action": True,
            "session_id": session_id,
            "page_index": int(page_index),
            "url": page.url,
            "title": title,
            **detected,
        }
    return await request_user_action(
        session_id,
        page_index,
        action_type=str(detected["action_type"]),
        message=str(detected["message"]),
        instructions=str(detected["instructions"]),
    )


async def resume(resume_token: str) -> dict[str, Any]:
    token = str(resume_token or "").strip()
    item = _HANDOFFS.pop(token, None)
    if item is None:
        raise KeyError("Unknown or already resumed browser handoff token")
    page = browser._page(item.session_id, item.page_index)
    return {
        "status": "resumed",
        "requires_user_action": False,
        "session_id": item.session_id,
        "page_index": item.page_index,
        "url": page.url,
        "title": await page.title(),
        "previous_action_type": item.action_type,
        "resume_token": token,
    }


def pending(session_id: str | None = None) -> list[dict[str, Any]]:
    items = sorted(_HANDOFFS.values(), key=lambda item: item.created_at)
    if session_id:
        items = [item for item in items if item.session_id == session_id]
    return [_payload(item) for item in items[-50:]]
