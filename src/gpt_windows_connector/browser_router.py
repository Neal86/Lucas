from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Any

from . import browser, browser_handoff, ixbrowser_bridge
from .browser_agent_policy import actor_keys, authorize_profile, default_selector, effective_policy
from .browser_bridge_server import bridge_server
from .browser_profile_registry import registry
from .config import resolve_in_workspace


BRIDGE_OPERATION_MAP = {
    "pages": "tabs.list",
    "new_page": "tab.open",
    "navigate": "tab.navigate",
    "inspect": "page.snapshot",
    "observe": "page.snapshot",
    "snapshot": "page.snapshot",
    "semantic_click": "page.click",
    "click": "page.click",
    "semantic_type": "page.type",
    "type": "page.type",
    "select": "page.select",
    "wait": "page.wait",
    "reload": "tab.reload",
    "back": "tab.back",
    "forward": "tab.forward",
    "press": "page.press",
    "hover": "page.hover",
    "scroll": "page.scroll",
    "upload": "page.upload",
    "network": "page.network",
    "close_page": "tab.close",
}


def _task_key(task_key: str | None, audit_context: dict[str, Any] | None) -> str:
    if str(task_key or "").strip():
        return str(task_key).strip()
    context = dict(audit_context or {})
    for key in ("task_title", "session_id", "audit_request_id", "gateway_request_id"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    return ""


def _actor_key(audit_context: dict[str, Any] | None, explicit_agent: str | None = None) -> str:
    keys = actor_keys(audit_context, explicit_agent)
    return keys[0] if keys else ""


def _selector(params: dict[str, Any], policy: dict[str, Any] | None) -> dict[str, Any]:
    selected = {
        "profile_key": params.get("profile_key"),
        "profile_id": params.get("profile_id"),
        "profile_name": params.get("profile_name"),
        "alias": params.get("alias"),
        "tag": params.get("tag"),
        "group": params.get("group"),
        "browser_type": params.get("browser_type"),
    }
    if not any(value not in (None, "") for value in selected.values()):
        selected.update(default_selector(policy))
    return selected


def list_profiles(audit_context: dict[str, Any] | None = None, *, agent: str | None = None) -> dict[str, Any]:
    policy = effective_policy(audit_context, explicit_agent=agent)
    profiles = []
    for item in registry.list_profiles():
        decision = authorize_profile(item, policy)
        profiles.append({**item, "allowed_for_agent": decision["allowed"], "policy_reason": decision["reason"]})
    return {
        "profiles": profiles,
        "agent_policy": policy,
        "bridge_clients": bridge_server.list_clients(),
    }


def resolve_profile(
    params: dict[str, Any],
    audit_context: dict[str, Any] | None,
) -> dict[str, Any]:
    policy = effective_policy(audit_context, explicit_agent=str(params.get("agent") or "") or None)
    selector = _selector(params, policy)
    result = registry.resolve(**selector)
    if not result.get("resolved"):
        return {**result, "selector": selector, "agent_policy": policy}
    profile = dict(result["profile"])
    decision = authorize_profile(profile, policy)
    if not decision["allowed"]:
        raise PermissionError(decision["reason"])
    return {
        **result,
        "selector": selector,
        "profile": profile,
        "agent_policy": policy,
        "policy_reason": decision["reason"],
    }


async def pair_bridge(params: dict[str, Any]) -> dict[str, Any]:
    return await bridge_server.pair(
        str(params.get("installation_id") or ""),
        pairing_code=str(params.get("pairing_code")) if params.get("pairing_code") is not None else None,
        browser_type=str(params.get("browser_type") or "ixbrowser"),
        profile_id=params.get("profile_id"),
        profile_name=str(params.get("profile_name") or "") or None,
        aliases=[str(v) for v in params.get("aliases") or []],
        tags=[str(v) for v in params.get("tags") or []],
        groups=[str(v) for v in params.get("groups") or []],
    )


def _bridge_for_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    installation_id = str(profile.get("bridge_installation_id") or "")
    if installation_id:
        for client in bridge_server.list_clients():
            if client.get("installation_id") == installation_id and client.get("paired"):
                return client
    profile_id = str(profile.get("profile_id") or "")
    profile_name = str(profile.get("profile_name") or "").lower()
    aliases = {str(v).lower() for v in profile.get("aliases") or []}
    for client in bridge_server.list_clients():
        if not client.get("paired"):
            continue
        cp = client.get("profile") or {}
        if str(cp.get("profile_key") or "") == str(profile.get("profile_key") or ""):
            return client
        if profile_id and str(client.get("profile_id") or "") == profile_id:
            return client
        if profile_name and str(client.get("profile_name") or "").lower() == profile_name:
            return client
        if aliases and str(client.get("alias") or "").lower() in aliases:
            return client
    return None


async def open_profile(
    params: dict[str, Any],
    audit_context: dict[str, Any] | None,
) -> dict[str, Any]:
    task_key = _task_key(str(params.get("task_key") or ""), audit_context)
    actor_key = _actor_key(audit_context, str(params.get("agent") or "") or None)

    if task_key and not any(params.get(k) not in (None, "") for k in ("profile_key", "profile_id", "profile_name", "alias", "tag", "group", "browser_type")):
        binding = registry.task_binding(task_key)
        if binding:
            profile = registry.get_profile(str(binding.get("profile_key") or ""))
            if profile:
                policy = effective_policy(audit_context, explicit_agent=str(params.get("agent") or "") or None)
                decision = authorize_profile(profile, policy)
                if not decision["allowed"]:
                    raise PermissionError(decision["reason"])
                return await _connect_profile(profile, task_key=task_key, actor_key=actor_key, reuse_binding=binding)

    resolved = resolve_profile(params, audit_context)
    if not resolved.get("resolved"):
        return resolved
    return await _connect_profile(
        dict(resolved["profile"]),
        task_key=task_key,
        actor_key=actor_key,
        reuse_binding=None,
    )


async def _connect_profile(
    profile: dict[str, Any],
    *,
    task_key: str,
    actor_key: str,
    reuse_binding: dict[str, Any] | None,
) -> dict[str, Any]:
    bridge = _bridge_for_profile(profile)
    if bridge:
        binding = registry.bind_task(
            task_key or ("profile:" + str(profile["profile_key"])),
            str(profile["profile_key"]),
            actor_key=actor_key,
            transport="bridge",
            bridge_installation_id=str(bridge["installation_id"]),
        )
        return {
            "status": "ready",
            "transport": "bridge",
            "profile": profile,
            "bridge": bridge,
            "binding": binding,
        }

    cdp_endpoint = str(profile.get("cdp_endpoint") or "").strip()
    if cdp_endpoint:
        result = await browser.ensure_cdp(
            endpoint=cdp_endpoint,
            browser_name=str(profile.get("browser_type") or "chrome"),
            profile=str(profile.get("profile_id") or profile.get("profile_name") or ""),
        )
        session_id = str(result.get("session_id") or "")
        binding = registry.bind_task(
            task_key or ("profile:" + str(profile["profile_key"])),
            str(profile["profile_key"]),
            actor_key=actor_key,
            transport="cdp",
            session_id=session_id,
        )
        return {
            "status": "ready",
            "transport": "cdp",
            "profile": profile,
            "session": result,
            "binding": binding,
        }

    if str(profile.get("browser_type") or "").lower() == "ixbrowser" and profile.get("profile_id"):
        status = ixbrowser_bridge.api_status()
        if status.get("available"):
            result = await ixbrowser_bridge.attach_profile(int(profile["profile_id"]))
            session_id = str(result.get("session_id") or "")
            binding = registry.bind_task(
                task_key or ("profile:" + str(profile["profile_key"])),
                str(profile["profile_key"]),
                actor_key=actor_key,
                transport="ixbrowser_api_cdp",
                session_id=session_id,
            )
            return {
                "status": "ready",
                "transport": "ixbrowser_api_cdp",
                "profile": profile,
                "session": result,
                "binding": binding,
            }

    handoff = registry.create_handoff({
        "kind": "open_profile",
        "profile_key": str(profile["profile_key"]),
        "task_key": task_key,
        "actor_key": actor_key,
    })
    profile_name = str(profile.get("profile_name") or profile.get("profile_id") or profile["profile_key"])
    return {
        "status": "requires_user_action",
        "requires_user_action": True,
        "action_type": "open_browser_profile",
        "profile": profile,
        "message": f"Browser profile {profile_name} is not currently connected.",
        "instructions": f"Open the {profile_name} profile. Lucas Browser Bridge will reconnect automatically.",
        "chat_message": f"需要你的操作：请打开浏览器 Profile「{profile_name}」。打开后告诉我“好了，继续”，Lucas 会恢复同一个任务。",
        "resume_token": handoff["resume_token"],
    }


async def resume_profile(
    resume_token: str,
    audit_context: dict[str, Any] | None,
) -> dict[str, Any]:
    handoff = registry.pop_handoff(str(resume_token or ""))
    if not handoff:
        raise KeyError("Unknown or already resumed browser profile handoff token")
    profile = registry.get_profile(str(handoff.get("profile_key") or ""))
    if not profile:
        raise KeyError("Browser profile no longer exists")
    policy = effective_policy(audit_context)
    decision = authorize_profile(profile, policy)
    if not decision["allowed"]:
        raise PermissionError(decision["reason"])
    result = await _connect_profile(
        profile,
        task_key=str(handoff.get("task_key") or ""),
        actor_key=str(handoff.get("actor_key") or ""),
        reuse_binding=None,
    )
    if result.get("requires_user_action"):
        return result
    return {"status": "resumed", "requires_user_action": False, **result}


def _binding_for_action(params: dict[str, Any], audit_context: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    task_key = _task_key(str(params.get("task_key") or ""), audit_context)
    binding = registry.task_binding(task_key) if task_key else None
    if not binding and params.get("profile_key"):
        profile = registry.get_profile(str(params.get("profile_key")))
        if profile:
            binding = {
                "task_key": task_key,
                "profile_key": profile["profile_key"],
                "transport": "",
                "session_id": "",
                "bridge_installation_id": "",
            }
    if not binding:
        raise RuntimeError("No browser profile is bound to this task. Call profile_open first.")
    profile = registry.get_profile(str(binding.get("profile_key") or ""))
    if not profile:
        raise KeyError("Bound browser profile no longer exists")
    policy = effective_policy(audit_context, explicit_agent=str(params.get("agent") or "") or None)
    decision = authorize_profile(profile, policy)
    if not decision["allowed"]:
        raise PermissionError(decision["reason"])
    return binding, profile


def _bridge_params(operation: str, operation_params: dict[str, Any]) -> dict[str, Any]:
    p = dict(operation_params or {})
    if "page_index" in p and "tab_id" not in p:
        # Bridge tabs use stable tab ids, not list positions. Keep explicit tab_id
        # authoritative; page_index is intentionally not converted silently.
        p.pop("page_index", None)
    if operation in {"semantic_click", "semantic_type"} and "target" not in p:
        p["target"] = p.get("selector")
    return p


async def profile_action(
    params: dict[str, Any],
    audit_context: dict[str, Any] | None,
    workspace: Path | None,
) -> Any:
    operation = str(params.get("operation") or "").strip()
    if not operation:
        raise ValueError("operation is required")
    operation_params = dict(params.get("operation_params") or {})
    binding, profile = _binding_for_action(params, audit_context)
    transport = str(binding.get("transport") or "")
    task_key = str(binding.get("task_key") or "")

    if transport == "bridge":
        installation_id = str(binding.get("bridge_installation_id") or profile.get("bridge_installation_id") or "")
        if not installation_id:
            raise RuntimeError("Bridge binding has no installation_id")
        action = BRIDGE_OPERATION_MAP.get(operation)
        if not action:
            raise ValueError(f"Operation {operation} is not supported by Browser Bridge")
        bridge_params = _bridge_params(operation, operation_params)
        if operation == "upload":
            if workspace is None:
                raise PermissionError("Browser upload requires a project workspace")
            encoded = []
            for raw in operation_params.get("paths") or []:
                path = resolve_in_workspace(workspace, str(raw))
                data = path.read_bytes()
                if len(data) > 25 * 1024 * 1024:
                    raise ValueError(f"Bridge upload file is larger than 25 MB: {path.name}")
                encoded.append({
                    "name": path.name,
                    "type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    "base64": base64.b64encode(data).decode("ascii"),
                })
            bridge_params["files"] = encoded
        result = await bridge_server.request(installation_id, action, bridge_params, timeout=float(operation_params.get("timeout", 30) or 30))
        if isinstance(result, dict) and result.get("blocker"):
            blocker = str(result.get("blocker"))
            handoff = registry.create_handoff({
                "kind": "bridge_blocker",
                "profile_key": profile["profile_key"],
                "task_key": task_key,
                "actor_key": _actor_key(audit_context, str(params.get("agent") or "") or None),
            })
            labels = {
                "captcha": "人机验证/CAPTCHA",
                "2fa": "验证码或双重验证",
                "passkey": "Passkey/设备验证",
                "login": "账号登录",
                "identity_verification": "身份或企业验证",
            }
            label = labels.get(blocker, blocker)
            return {
                "status": "requires_user_action",
                "requires_user_action": True,
                "action_type": blocker,
                "profile": profile,
                "page": result,
                "message": f"The page requires {label}.",
                "chat_message": f"需要你的操作：当前 Profile「{profile.get('profile_name') or profile.get('profile_id')}」需要完成{label}。完成后告诉我“好了，继续”。",
                "resume_token": handoff["resume_token"],
            }
        return {"transport": "bridge", "profile": profile, "result": result}

    session_id = str(binding.get("session_id") or "")
    if not session_id:
        reopened = await _connect_profile(
            profile,
            task_key=task_key,
            actor_key=_actor_key(audit_context, str(params.get("agent") or "") or None),
            reuse_binding=binding,
        )
        if reopened.get("requires_user_action"):
            return reopened
        session_id = str((reopened.get("session") or {}).get("session_id") or "")
        transport = str(reopened.get("transport") or transport)
    if not session_id:
        raise RuntimeError("Browser profile does not have a usable session")

    from . import browser_advanced, browser_diagnostics, browser_semantic

    handlers = {
        "pages": browser.pages,
        "new_page": browser.new_page,
        "navigate": browser.navigate,
        "inspect": browser.inspect,
        "observe": browser_semantic.observe,
        "snapshot": browser_advanced.aria_snapshot,
        "semantic_click": browser_semantic.semantic_click,
        "semantic_type": browser_semantic.semantic_type,
        "click": browser.click,
        "type": browser.type_text,
        "select": browser.select_option,
        "wait": browser_advanced.wait_for,
        "reload": browser_advanced.reload_page,
        "back": browser_advanced.go_back,
        "forward": browser_advanced.go_forward,
        "press": browser_advanced.press_key,
        "hover": browser_advanced.hover,
        "scroll": browser_advanced.scroll,
        "close_page": browser_advanced.close_page,
        "network": browser_advanced.network_summary,
        "diagnostics": browser_diagnostics.diagnostics,
        "screenshot": browser.screenshot,
    }
    if operation == "upload":
        if workspace is None:
            raise PermissionError("Browser upload requires a project workspace")
        operation_params["paths"] = [
            str(resolve_in_workspace(workspace, str(path)))
            for path in operation_params.get("paths") or []
        ]
        handler = browser.upload
    else:
        handler = handlers.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported browser profile operation: {operation}")
    result = await handler(session_id=session_id, **operation_params)
    return {"transport": transport or "cdp", "profile": profile, "result": result}


def release_task(task_key: str) -> dict[str, Any]:
    return {"released": registry.release_task(str(task_key or "")), "task_key": str(task_key or "")}
