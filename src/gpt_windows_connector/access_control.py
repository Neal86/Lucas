from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


_DECISION_RANK = {"allow": 0, "ask": 1, "always_ask": 2, "block": 3}


def _stricter_decision(a: object, b: object, default: str = "ask") -> str:
    left = str(a or default).lower()
    right = str(b or default).lower()
    if left not in _DECISION_RANK:
        left = default
    if right not in _DECISION_RANK:
        right = default
    return left if _DECISION_RANK[left] >= _DECISION_RANK[right] else right


def intersect_security(node_security: dict[str, Any] | None, user_security: dict[str, Any] | None) -> dict[str, Any]:
    """Return effective security where a user can only narrow Node-wide permissions."""
    from .security import DEFAULT_SECURITY

    node = {**DEFAULT_SECURITY, **(node_security or {})}
    user = {**DEFAULT_SECURITY, **(user_security or {})}
    node_policy = {**DEFAULT_SECURITY["approval_policy"], **dict(node.get("approval_policy") or {})}
    user_policy = {**DEFAULT_SECURITY["approval_policy"], **dict(user.get("approval_policy") or {})}
    effective_policy = {
        key: _stricter_decision(node_policy.get(key), user_policy.get(key), DEFAULT_SECURITY["approval_policy"].get(key, "ask"))
        for key in set(node_policy) | set(user_policy)
    }

    node_domains = [str(v).strip().lower() for v in node.get("allowed_domains") or [] if str(v).strip()]
    user_domains = [str(v).strip().lower() for v in user.get("allowed_domains") or [] if str(v).strip()]
    if node_domains and user_domains:
        effective_domains = [v for v in user_domains if v in set(node_domains)]
    else:
        effective_domains = node_domains or user_domains

    return {
        **node,
        "approval_policy": effective_policy,
        "remember_approvals": bool(node.get("remember_approvals", True)) and bool(user.get("remember_approvals", True)),
        "network_external": _stricter_decision(node.get("network_external"), user.get("network_external")),
        "network_lan": _stricter_decision(node.get("network_lan"), user.get("network_lan")),
        "allowed_domains": effective_domains,
        "block_silent_network": bool(node.get("block_silent_network", True)) or bool(user.get("block_silent_network", True)),
        "show_rule_summary": bool(node.get("show_rule_summary", True)) or bool(user.get("show_rule_summary", True)),
        "rules_text": str(node.get("rules_text") or DEFAULT_SECURITY["rules_text"]),
    }

ACCESS_PRESETS = {"request_approval", "auto_approve", "full_access", "custom"}


def preset_security(preset: str) -> dict[str, Any]:
    from .security import DEFAULT_SECURITY

    base = {**DEFAULT_SECURITY, "approval_policy": dict(DEFAULT_SECURITY["approval_policy"])}
    if preset == "auto_approve":
        base["approval_policy"] = {k: "allow" for k in base["approval_policy"]}
        for key in ("browser_transfer", "git_push", "software_install", "registry_system", "high_risk", "service_control"):
            base["approval_policy"][key] = "always_ask"
        base["network_external"] = "allow"
        base["network_lan"] = "allow"
        base["block_silent_network"] = False
    elif preset == "full_access":
        base["approval_policy"] = {k: "allow" for k in base["approval_policy"]}
        base["network_external"] = "allow"
        base["network_lan"] = "allow"
        base["block_silent_network"] = False
    return base


def normalize_preset(value: str | None) -> str:
    value = str(value or "").strip()
    return value if value in ACCESS_PRESETS else "request_approval"


def clamp_roots(requested: list[str] | tuple[str, ...], node_roots: list[str] | tuple[str, ...]) -> list[str]:
    allowed = [Path(value).expanduser().resolve() for value in node_roots]
    result: list[str] = []
    for raw in requested:
        try:
            candidate = Path(raw).expanduser().resolve()
        except Exception:
            continue
        if any(candidate == root or root in candidate.parents for root in allowed):
            value = str(candidate)
            if value not in result:
                result.append(value)
    return result


class LocalAccessStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"version": 1, "users": {}}
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "users": {}}
        users = data.get("users")
        if not isinstance(users, dict):
            data["users"] = {}
        data.setdefault("version", 1)
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def list_users(self) -> list[dict[str, Any]]:
        users = self.load().get("users", {})
        out: list[dict[str, Any]] = []
        for user_id, record in users.items():
            if not isinstance(record, dict):
                continue
            out.append({"user_id": str(user_id), **record})
        return sorted(out, key=lambda item: str(item.get("name") or item.get("email") or item.get("user_id")).lower())

    def get(self, user_id: str) -> dict[str, Any] | None:
        record = self.load().get("users", {}).get(str(user_id))
        return dict(record) if isinstance(record, dict) else None

    def upsert(self, actor: dict[str, Any], preset: str, allowed_roots: list[str], *, security: dict[str, Any] | None = None, enabled: bool = True) -> dict[str, Any]:
        user_id = str(actor.get("user_id") or actor.get("id") or "").strip()
        if not user_id:
            raise ValueError("user_id is required")
        data = self.load()
        users = data.setdefault("users", {})
        previous = users.get(user_id) if isinstance(users.get(user_id), dict) else {}
        now = time.time()
        record = {
            "email": str(actor.get("email") or previous.get("email") or ""),
            "name": str(actor.get("name") or previous.get("name") or ""),
            "preset": normalize_preset(preset),
            "security": dict(security or preset_security(normalize_preset(preset))),
            "allowed_roots": list(dict.fromkeys(str(root) for root in allowed_roots if str(root).strip())),
            "enabled": bool(enabled),
            "approved_at": float(previous.get("approved_at") or now),
            "updated_at": now,
            "last_access": float(previous.get("last_access") or 0),
        }
        users[user_id] = record
        pending = data.setdefault("pending", {})
        if isinstance(pending, dict):
            pending.pop(user_id, None)
        self.save(data)
        return {"user_id": user_id, **record}

    def list_pending(self) -> list[dict[str, Any]]:
        pending = self.load().get("pending", {})
        if not isinstance(pending, dict):
            return []
        out: list[dict[str, Any]] = []
        for user_id, record in pending.items():
            if not isinstance(record, dict):
                continue
            out.append({"user_id": str(user_id), **record, "_pending": True})
        return sorted(out, key=lambda item: float(item.get("requested_at") or 0), reverse=True)

    def add_pending(self, actor: dict[str, Any]) -> dict[str, Any]:
        user_id = str(actor.get("user_id") or actor.get("id") or "").strip()
        if not user_id:
            raise ValueError("user_id is required")
        data = self.load()
        pending = data.setdefault("pending", {})
        now = time.time()
        previous = pending.get(user_id) if isinstance(pending.get(user_id), dict) else {}
        record = {
            "email": str(actor.get("email") or previous.get("email") or ""),
            "name": str(actor.get("name") or previous.get("name") or ""),
            "requested_at": float(previous.get("requested_at") or now),
            "updated_at": now,
        }
        pending[user_id] = record
        self.save(data)
        return {"user_id": user_id, **record, "_pending": True}

    def remove_pending(self, user_id: str) -> bool:
        data = self.load()
        pending = data.setdefault("pending", {})
        removed = pending.pop(str(user_id), None) is not None
        if removed:
            self.save(data)
        return removed

    def remove(self, user_id: str) -> bool:
        data = self.load()
        users = data.setdefault("users", {})
        removed = users.pop(str(user_id), None) is not None
        if removed:
            self.save(data)
        return removed

    def prune_root(self, removed_root: str) -> int:
        """Permanently remove a deleted Node root from every user's grants."""
        try:
            target = Path(removed_root).expanduser().resolve()
        except Exception:
            return 0
        data = self.load()
        users = data.setdefault("users", {})
        changed = 0
        for record in users.values():
            if not isinstance(record, dict):
                continue
            kept: list[str] = []
            removed = False
            for raw in record.get("allowed_roots") or []:
                try:
                    candidate = Path(str(raw)).expanduser().resolve()
                except Exception:
                    candidate = Path(str(raw))
                if candidate == target or target in candidate.parents:
                    removed = True
                    continue
                kept.append(str(raw))
            if removed:
                record["allowed_roots"] = kept
                record["updated_at"] = time.time()
                changed += 1
        if changed:
            self.save(data)
        return changed

    def touch(self, user_id: str) -> None:
        data = self.load()
        record = data.setdefault("users", {}).get(str(user_id))
        if not isinstance(record, dict):
            return
        record["last_access"] = time.time()
        self.save(data)

    def effective(self, user_id: str, node_roots: list[str] | tuple[str, ...]) -> dict[str, Any] | None:
        record = self.get(user_id)
        if not record or not bool(record.get("enabled", True)):
            return None
        roots = clamp_roots(list(record.get("allowed_roots") or []), list(node_roots))
        if not roots:
            return None
        preset = normalize_preset(record.get("preset") or ("full_access" if record.get("permission_level") == "admin" else "request_approval"))
        security = record.get("security") if isinstance(record.get("security"), dict) else preset_security(preset)
        clean = dict(record)
        clean.pop("permission_level", None)
        return {**clean, "user_id": str(user_id), "preset": preset, "security": dict(security), "allowed_roots": roots}
