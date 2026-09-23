from __future__ import annotations

import re
from typing import Any

from .browser_profile_registry import BrowserProfileRegistry, registry as default_registry


LEGACY_EVA_CLIENT_ID = "lucas_RadfVO6VaiwUY5bEzzq6piO9NApZRJLb"


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def actor_keys(audit_context: dict[str, Any] | None, explicit_agent: str | None = None) -> list[str]:
    context = dict(audit_context or {})
    values = [
        explicit_agent,
        context.get("client_id"),
        context.get("client_name"),
        context.get("source"),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = _norm(text)
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def effective_policy(
    audit_context: dict[str, Any] | None,
    *,
    explicit_agent: str | None = None,
    registry: BrowserProfileRegistry = default_registry,
) -> dict[str, Any] | None:
    keys = actor_keys(audit_context, explicit_agent)
    configured = registry.get_agent_policy(keys)
    if configured:
        return configured

    context = dict(audit_context or {})
    if str(context.get("client_id") or "").strip() == LEGACY_EVA_CLIENT_ID:
        # Preserve the old Eva isolation guarantee until the user replaces it
        # with an explicit local browser-profile rule in Lucas Settings.
        return {
            "agent_key": "Eva",
            "allow_profiles": [],
            "allow_aliases": ["eva"],
            "allow_groups": [],
            "allow_tags": [],
            "deny_profiles": [],
            "deny_groups": [],
            "deny_tags": [],
            "default_profile": "eva",
            "enabled": True,
            "legacy": True,
        }
    return None


def _contains(values: list[object] | tuple[object, ...] | None, candidate: object) -> bool:
    wanted = _norm(candidate)
    return bool(wanted) and wanted in {_norm(value) for value in values or []}


def authorize_profile(profile: dict[str, Any], policy: dict[str, Any] | None) -> dict[str, Any]:
    if policy is None:
        return {"allowed": True, "reason": "No browser profile restriction is configured for this agent."}

    profile_key = str(profile.get("profile_key") or "")
    aliases = list(profile.get("aliases") or [])
    groups = list(profile.get("groups") or [])
    tags = list(profile.get("tags") or [])

    if _contains(policy.get("deny_profiles"), profile_key):
        return {"allowed": False, "reason": f"Profile {profile_key} is explicitly denied for this agent."}
    if any(_contains(policy.get("deny_groups"), group) for group in groups):
        return {"allowed": False, "reason": "This profile belongs to a denied browser group."}
    if any(_contains(policy.get("deny_tags"), tag) for tag in tags):
        return {"allowed": False, "reason": "This profile has a denied browser tag."}

    positive_rules = any(
        policy.get(key)
        for key in ("allow_profiles", "allow_aliases", "allow_groups", "allow_tags")
    )
    if not positive_rules:
        return {"allowed": True, "reason": "No positive allow-list is configured."}

    if _contains(policy.get("allow_profiles"), profile_key):
        return {"allowed": True, "reason": "Profile is explicitly allowed."}
    if any(_contains(policy.get("allow_aliases"), alias) for alias in aliases):
        return {"allowed": True, "reason": "Profile alias is allowed."}
    if any(_contains(policy.get("allow_groups"), group) for group in groups):
        return {"allowed": True, "reason": "Profile group is allowed."}
    if any(_contains(policy.get("allow_tags"), tag) for tag in tags):
        return {"allowed": True, "reason": "Profile tag is allowed."}

    profile_name = str(profile.get("profile_name") or profile_key or "browser profile")
    return {
        "allowed": False,
        "reason": f"{profile_name} is outside this agent's local browser-profile allow-list.",
    }


def default_selector(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not policy:
        return {}
    default_profile = str(policy.get("default_profile") or "").strip()
    if not default_profile:
        return {}
    return {"alias": default_profile}
