from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .settings_constants import CONFIG_DIR

REGISTRY_FILE = CONFIG_DIR / "browser-profiles.json"
TASK_BINDINGS_FILE = CONFIG_DIR / "browser-task-bindings.json"

_LOCK = threading.RLock()


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _unique(values: list[object] | tuple[object, ...] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        key = _norm(text)
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else dict(default)
    except (OSError, json.JSONDecodeError):
        return dict(default)


def _default_registry() -> dict[str, Any]:
    return {"version": 1, "profiles": {}, "agent_policies": {}, "paired_bridges": {}}


def _default_bindings() -> dict[str, Any]:
    return {"version": 1, "bindings": {}, "handoffs": {}}


def _profile_key(record: dict[str, Any]) -> str:
    browser = _norm(record.get("browser_type") or "browser")
    profile_id = str(record.get("profile_id") or "").strip()
    installation_id = str(record.get("bridge_installation_id") or "").strip()
    name = _norm(record.get("profile_name") or record.get("name"))
    if profile_id:
        return f"{browser}:id:{profile_id}"
    if installation_id:
        return f"{browser}:bridge:{installation_id}"
    if name:
        return f"{browser}:name:{name}"
    return f"{browser}:lucas:{uuid.uuid4().hex}"


def sanitize_profile(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "profile_key",
        "browser_type",
        "profile_id",
        "profile_name",
        "aliases",
        "tags",
        "groups",
        "bridge_installation_id",
        "extension_id",
        "cdp_endpoint",
        "launcher",
        "enabled",
        "created_at",
        "updated_at",
        "last_seen",
        "notes",
    }
    return {key: value for key, value in dict(record or {}).items() if key in allowed}


class BrowserProfileRegistry:
    """Local source of truth for browser identity, aliases and agent/profile policy."""

    def __init__(
        self,
        registry_file: Path = REGISTRY_FILE,
        bindings_file: Path = TASK_BINDINGS_FILE,
    ) -> None:
        self.registry_file = registry_file
        self.bindings_file = bindings_file

    def _load(self) -> dict[str, Any]:
        data = _load_json(self.registry_file, _default_registry())
        data.setdefault("version", 1)
        data.setdefault("profiles", {})
        data.setdefault("agent_policies", {})
        data.setdefault("paired_bridges", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        _atomic_write(self.registry_file, data)

    def _load_bindings(self) -> dict[str, Any]:
        data = _load_json(self.bindings_file, _default_bindings())
        data.setdefault("version", 1)
        data.setdefault("bindings", {})
        data.setdefault("handoffs", {})
        return data

    def _save_bindings(self, data: dict[str, Any]) -> None:
        _atomic_write(self.bindings_file, data)

    def list_profiles(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        with _LOCK:
            records = []
            for key, raw in self._load().get("profiles", {}).items():
                if not isinstance(raw, dict):
                    continue
                record = {"profile_key": str(key), **raw}
                if not include_disabled and not bool(record.get("enabled", True)):
                    continue
                records.append(sanitize_profile(record))
            records.sort(
                key=lambda item: (
                    _norm(item.get("browser_type")),
                    _norm(item.get("profile_name")),
                    _norm(item.get("profile_id")),
                )
            )
            return records

    def get_profile(self, profile_key: str) -> dict[str, Any] | None:
        with _LOCK:
            raw = self._load().get("profiles", {}).get(str(profile_key))
            return sanitize_profile({"profile_key": str(profile_key), **raw}) if isinstance(raw, dict) else None

    def upsert_profile(self, record: dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            data = self._load()
            profiles = data.setdefault("profiles", {})
            incoming = dict(record or {})
            requested_key = str(incoming.pop("profile_key", "") or "").strip()
            key = requested_key or _profile_key(incoming)
            previous = profiles.get(key) if isinstance(profiles.get(key), dict) else {}
            now = time.time()
            merged = {
                **previous,
                "browser_type": str(incoming.get("browser_type") or previous.get("browser_type") or "browser").strip().lower(),
                "profile_id": str(incoming.get("profile_id") if incoming.get("profile_id") is not None else previous.get("profile_id") or "").strip() or None,
                "profile_name": str(incoming.get("profile_name") or incoming.get("name") or previous.get("profile_name") or "").strip() or None,
                "aliases": _unique(list(incoming.get("aliases") or previous.get("aliases") or [])),
                "tags": _unique(list(incoming.get("tags") or previous.get("tags") or [])),
                "groups": _unique(list(incoming.get("groups") or previous.get("groups") or [])),
                "bridge_installation_id": str(incoming.get("bridge_installation_id") or previous.get("bridge_installation_id") or "").strip() or None,
                "extension_id": str(incoming.get("extension_id") or previous.get("extension_id") or "").strip() or None,
                "cdp_endpoint": str(incoming.get("cdp_endpoint") or previous.get("cdp_endpoint") or "").strip() or None,
                "launcher": dict(incoming.get("launcher") or previous.get("launcher") or {}),
                "enabled": bool(incoming.get("enabled", previous.get("enabled", True))),
                "notes": str(incoming.get("notes") if incoming.get("notes") is not None else previous.get("notes") or "")[:1000],
                "created_at": float(previous.get("created_at") or now),
                "updated_at": now,
                "last_seen": float(incoming.get("last_seen") or previous.get("last_seen") or 0.0),
            }
            profiles[key] = merged
            installation_id = str(merged.get("bridge_installation_id") or "")
            if installation_id:
                data.setdefault("paired_bridges", {})[installation_id] = {
                    "profile_key": key,
                    "paired_at": float(
                        data.get("paired_bridges", {}).get(installation_id, {}).get("paired_at") or now
                    ),
                    "updated_at": now,
                }
            self._save(data)
            return sanitize_profile({"profile_key": key, **merged})

    def remove_profile(self, profile_key: str) -> bool:
        with _LOCK:
            data = self._load()
            profiles = data.setdefault("profiles", {})
            removed = profiles.pop(str(profile_key), None)
            if not isinstance(removed, dict):
                return False
            installation_id = str(removed.get("bridge_installation_id") or "")
            if installation_id:
                data.setdefault("paired_bridges", {}).pop(installation_id, None)
            self._save(data)
            bindings = self._load_bindings()
            changed = False
            for task_key, binding in list(bindings.get("bindings", {}).items()):
                if isinstance(binding, dict) and binding.get("profile_key") == profile_key:
                    bindings["bindings"].pop(task_key, None)
                    changed = True
            if changed:
                self._save_bindings(bindings)
            return True

    def profile_for_bridge(self, installation_id: str) -> dict[str, Any] | None:
        installation_id = str(installation_id or "").strip()
        if not installation_id:
            return None
        with _LOCK:
            data = self._load()
            paired = data.get("paired_bridges", {}).get(installation_id)
            if isinstance(paired, dict):
                profile_key = str(paired.get("profile_key") or "")
                raw = data.get("profiles", {}).get(profile_key)
                if isinstance(raw, dict):
                    return sanitize_profile({"profile_key": profile_key, **raw})
            for key, raw in data.get("profiles", {}).items():
                if isinstance(raw, dict) and str(raw.get("bridge_installation_id") or "") == installation_id:
                    return sanitize_profile({"profile_key": str(key), **raw})
        return None

    def resolve(
        self,
        *,
        profile_key: str | None = None,
        profile_id: str | int | None = None,
        profile_name: str | None = None,
        alias: str | None = None,
        tag: str | None = None,
        group: str | None = None,
        browser_type: str | None = None,
    ) -> dict[str, Any]:
        records = self.list_profiles()
        if profile_key:
            exact = [item for item in records if item.get("profile_key") == str(profile_key)]
            if exact:
                return {"resolved": True, "profile": exact[0], "candidates": exact}

        filters = {
            "profile_id": _norm(profile_id),
            "profile_name": _norm(profile_name),
            "alias": _norm(alias),
            "tag": _norm(tag),
            "group": _norm(group),
            "browser_type": _norm(browser_type),
        }
        candidates: list[tuple[int, dict[str, Any]]] = []
        for item in records:
            score = 0
            if filters["browser_type"] and _norm(item.get("browser_type")) != filters["browser_type"]:
                continue
            if filters["profile_id"]:
                if _norm(item.get("profile_id")) != filters["profile_id"]:
                    continue
                score += 100
            if filters["profile_name"]:
                name = _norm(item.get("profile_name"))
                if name == filters["profile_name"]:
                    score += 90
                elif filters["profile_name"] in name:
                    score += 45
                else:
                    continue
            if filters["alias"]:
                aliases = {_norm(value) for value in item.get("aliases") or []}
                if filters["alias"] not in aliases:
                    continue
                score += 95
            if filters["tag"]:
                tags = {_norm(value) for value in item.get("tags") or []}
                if filters["tag"] not in tags:
                    continue
                score += 40
            if filters["group"]:
                groups = {_norm(value) for value in item.get("groups") or []}
                if filters["group"] not in groups:
                    continue
                score += 40
            if not any(filters.values()):
                score = 1
            candidates.append((score, item))

        candidates.sort(key=lambda pair: (-pair[0], _norm(pair[1].get("profile_name"))))
        items = [item for _, item in candidates]
        if not items:
            return {"resolved": False, "reason": "No browser profile matched the selector.", "candidates": []}
        top_score = candidates[0][0]
        tied = [item for score, item in candidates if score == top_score]
        if len(tied) > 1 and any(filters[key] for key in ("profile_name", "tag", "group")) and not filters["profile_id"] and not filters["alias"]:
            return {
                "resolved": False,
                "ambiguous": True,
                "reason": "More than one browser profile matched. Use profile_id, alias, or profile_key.",
                "candidates": tied[:20],
            }
        return {"resolved": True, "profile": items[0], "candidates": items[:20]}

    def set_agent_policy(self, agent_key: str, policy: dict[str, Any]) -> dict[str, Any]:
        key = _norm(agent_key)
        if not key:
            raise ValueError("agent_key is required")
        with _LOCK:
            data = self._load()
            record = {
                "agent_key": str(agent_key).strip(),
                "allow_profiles": _unique(list(policy.get("allow_profiles") or [])),
                "allow_aliases": _unique(list(policy.get("allow_aliases") or [])),
                "allow_groups": _unique(list(policy.get("allow_groups") or [])),
                "allow_tags": _unique(list(policy.get("allow_tags") or [])),
                "deny_profiles": _unique(list(policy.get("deny_profiles") or [])),
                "deny_groups": _unique(list(policy.get("deny_groups") or [])),
                "deny_tags": _unique(list(policy.get("deny_tags") or [])),
                "default_profile": str(policy.get("default_profile") or "").strip() or None,
                "enabled": bool(policy.get("enabled", True)),
                "updated_at": time.time(),
            }
            data.setdefault("agent_policies", {})[key] = record
            self._save(data)
            return dict(record)

    def remove_agent_policy(self, agent_key: str) -> bool:
        key = _norm(agent_key)
        with _LOCK:
            data = self._load()
            removed = data.setdefault("agent_policies", {}).pop(key, None) is not None
            if removed:
                self._save(data)
            return removed

    def list_agent_policies(self) -> list[dict[str, Any]]:
        with _LOCK:
            values = [
                dict(value)
                for value in self._load().get("agent_policies", {}).values()
                if isinstance(value, dict)
            ]
        return sorted(values, key=lambda item: _norm(item.get("agent_key")))

    def get_agent_policy(self, keys: list[str]) -> dict[str, Any] | None:
        normalized = [_norm(key) for key in keys if _norm(key)]
        with _LOCK:
            policies = self._load().get("agent_policies", {})
            for key in normalized:
                value = policies.get(key)
                if isinstance(value, dict) and bool(value.get("enabled", True)):
                    return dict(value)
        return None

    def bind_task(
        self,
        task_key: str,
        profile_key: str,
        *,
        actor_key: str = "",
        transport: str = "",
        session_id: str = "",
        bridge_installation_id: str = "",
    ) -> dict[str, Any]:
        task_key = str(task_key or "").strip()
        if not task_key:
            raise ValueError("task_key is required")
        with _LOCK:
            data = self._load_bindings()
            now = time.time()
            binding = {
                "task_key": task_key,
                "profile_key": str(profile_key),
                "actor_key": str(actor_key or ""),
                "transport": str(transport or ""),
                "session_id": str(session_id or ""),
                "bridge_installation_id": str(bridge_installation_id or ""),
                "created_at": float(data.get("bindings", {}).get(task_key, {}).get("created_at") or now),
                "updated_at": now,
            }
            data.setdefault("bindings", {})[task_key] = binding
            self._save_bindings(data)
            return dict(binding)

    def task_binding(self, task_key: str, *, max_age_seconds: int = 7 * 24 * 3600) -> dict[str, Any] | None:
        task_key = str(task_key or "").strip()
        if not task_key:
            return None
        with _LOCK:
            data = self._load_bindings()
            binding = data.get("bindings", {}).get(task_key)
            if not isinstance(binding, dict):
                return None
            updated_at = float(binding.get("updated_at") or 0.0)
            if updated_at and time.time() - updated_at > max_age_seconds:
                data["bindings"].pop(task_key, None)
                self._save_bindings(data)
                return None
            return dict(binding)

    def release_task(self, task_key: str) -> bool:
        task_key = str(task_key or "").strip()
        with _LOCK:
            data = self._load_bindings()
            removed = data.setdefault("bindings", {}).pop(task_key, None) is not None
            if removed:
                self._save_bindings(data)
            return removed

    def create_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            data = self._load_bindings()
            token = uuid.uuid4().hex
            record = {
                "resume_token": token,
                "created_at": time.time(),
                **dict(payload or {}),
            }
            data.setdefault("handoffs", {})[token] = record
            self._save_bindings(data)
            return dict(record)

    def pop_handoff(self, token: str) -> dict[str, Any] | None:
        with _LOCK:
            data = self._load_bindings()
            value = data.setdefault("handoffs", {}).pop(str(token or ""), None)
            if value is not None:
                self._save_bindings(data)
            return dict(value) if isinstance(value, dict) else None

    def pending_handoffs(self) -> list[dict[str, Any]]:
        with _LOCK:
            values = [
                dict(value)
                for value in self._load_bindings().get("handoffs", {}).values()
                if isinstance(value, dict)
            ]
        return sorted(values, key=lambda item: float(item.get("created_at") or 0.0))


registry = BrowserProfileRegistry()
