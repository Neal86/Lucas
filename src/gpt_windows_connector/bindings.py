from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectBinding:
    project_id: str
    workspace: str
    node_id: str
    name: str | None = None


class BindingStore:
    """Persistent project -> Windows node + workspace bindings.

    This intentionally has no conversation binding layer. Every chat inside the
    same AI project is expected to resolve through the same project binding.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        default = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "gpt-windows-connector" / "projects.json"
        self.path = Path(path or os.environ.get("GWC_BINDINGS_FILE", default)).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write({"version": 1, "projects": {}})

    def _read(self) -> dict:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"version": 1, "projects": {}}
            data.setdefault("projects", {})
            return data

    def _write(self, data: dict) -> None:
        with self._lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def set(self, project_id: str, node_id: str, workspace: str, name: str | None = None) -> ProjectBinding:
        project_id = project_id.strip()
        node_id = node_id.strip()
        workspace = workspace.strip()
        if not project_id:
            raise ValueError("project_id is required")
        if not node_id:
            raise ValueError("node_id is required")
        if not workspace:
            raise ValueError("workspace is required")
        binding = ProjectBinding(project_id=project_id, node_id=node_id, workspace=workspace, name=name or None)
        data = self._read()
        data["projects"][project_id] = asdict(binding)
        self._write(data)
        return binding

    def get(self, project_id: str) -> ProjectBinding | None:
        raw = self._read().get("projects", {}).get(project_id)
        return ProjectBinding(**raw) if raw else None

    def remove(self, project_id: str) -> bool:
        data = self._read()
        existed = project_id in data.get("projects", {})
        if existed:
            del data["projects"][project_id]
            self._write(data)
        return existed

    def list(self) -> list[ProjectBinding]:
        return [ProjectBinding(**raw) for raw in self._read().get("projects", {}).values()]
