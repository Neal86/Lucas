from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

PERMISSION_RANK = {"read": 0, "operate": 1, "admin": 2}


def clamp_permission(requested: str, maximum: str) -> str:
    requested = requested if requested in PERMISSION_RANK else "read"
    maximum = maximum if maximum in PERMISSION_RANK else "operate"
    return min((requested, maximum), key=lambda value: PERMISSION_RANK[value])


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

    def upsert(self, actor: dict[str, Any], permission_level: str, allowed_roots: list[str], *, enabled: bool = True) -> dict[str, Any]:
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
            "permission_level": permission_level if permission_level in PERMISSION_RANK else "read",
            "allowed_roots": list(dict.fromkeys(str(root) for root in allowed_roots if str(root).strip())),
            "enabled": bool(enabled),
            "approved_at": float(previous.get("approved_at") or now),
            "updated_at": now,
            "last_access": float(previous.get("last_access") or 0),
        }
        users[user_id] = record
        self.save(data)
        return {"user_id": user_id, **record}

    def remove(self, user_id: str) -> bool:
        data = self.load()
        users = data.setdefault("users", {})
        removed = users.pop(str(user_id), None) is not None
        if removed:
            self.save(data)
        return removed

    def touch(self, user_id: str) -> None:
        data = self.load()
        record = data.setdefault("users", {}).get(str(user_id))
        if not isinstance(record, dict):
            return
        record["last_access"] = time.time()
        self.save(data)

    def effective(self, user_id: str, node_permission: str, node_roots: list[str] | tuple[str, ...]) -> dict[str, Any] | None:
        record = self.get(user_id)
        if not record or not bool(record.get("enabled", True)):
            return None
        roots = clamp_roots(list(record.get("allowed_roots") or []), list(node_roots))
        if not roots:
            return None
        return {
            **record,
            "user_id": str(user_id),
            "permission_level": clamp_permission(str(record.get("permission_level") or "read"), node_permission),
            "allowed_roots": roots,
        }
