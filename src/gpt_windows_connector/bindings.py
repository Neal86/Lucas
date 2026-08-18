from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

BindingScope = Literal["project", "conversation"]


@dataclass(frozen=True)
class WorkspaceBinding:
    scope: BindingScope
    scope_id: str
    workspace: str
    node_id: str | None = None


class BindingStore:
    """Persistent project/conversation -> workspace binding store.

    Conversation bindings override project bindings. The store is intentionally
    independent from any specific AI vendor; callers provide stable project and
    conversation IDs from their client/session context.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        default = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "gpt-windows-connector" / "bindings.json"
        self.path = Path(path or os.environ.get("GWC_BINDINGS_FILE", default)).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write({"version": 1, "project": {}, "conversation": {}})

    def _read(self) -> dict:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"version": 1, "project": {}, "conversation": {}}
            data.setdefault("project", {})
            data.setdefault("conversation", {})
            return data

    def _write(self, data: dict) -> None:
        with self._lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    @staticmethod
    def _validate_workspace(workspace: str | Path) -> Path:
        resolved = Path(workspace).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(f"Workspace does not exist or is not a directory: {resolved}")
        return resolved

    def set(self, scope: BindingScope, scope_id: str, workspace: str | Path, node_id: str | None = None) -> WorkspaceBinding:
        if scope not in ("project", "conversation"):
            raise ValueError("scope must be 'project' or 'conversation'")
        scope_id = scope_id.strip()
        if not scope_id:
            raise ValueError("scope_id is required")
        resolved = self._validate_workspace(workspace)
        binding = WorkspaceBinding(scope=scope, scope_id=scope_id, workspace=str(resolved), node_id=node_id or None)
        data = self._read()
        data[scope][scope_id] = asdict(binding)
        self._write(data)
        return binding

    def get(self, scope: BindingScope, scope_id: str) -> WorkspaceBinding | None:
        data = self._read()
        raw = data.get(scope, {}).get(scope_id)
        return WorkspaceBinding(**raw) if raw else None

    def remove(self, scope: BindingScope, scope_id: str) -> bool:
        data = self._read()
        existed = scope_id in data.get(scope, {})
        if existed:
            del data[scope][scope_id]
            self._write(data)
        return existed

    def list(self, scope: BindingScope | None = None) -> list[WorkspaceBinding]:
        data = self._read()
        scopes = (scope,) if scope else ("project", "conversation")
        result: list[WorkspaceBinding] = []
        for current_scope in scopes:
            for raw in data.get(current_scope, {}).values():
                result.append(WorkspaceBinding(**raw))
        return result

    def resolve(self, project_id: str | None = None, conversation_id: str | None = None) -> WorkspaceBinding | None:
        """Resolve the active binding with conversation > project precedence."""
        if conversation_id:
            binding = self.get("conversation", conversation_id)
            if binding:
                return binding
        if project_id:
            return self.get("project", project_id)
        return None
