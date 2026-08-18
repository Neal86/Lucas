from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    workspace: Path

    @classmethod
    def from_env(cls) -> "Settings":
        raw = os.environ.get("GWC_WORKSPACE", "").strip()
        if not raw:
            raise RuntimeError("GWC_WORKSPACE is required and must point to an existing workspace directory")
        workspace = Path(raw).expanduser().resolve()
        if not workspace.exists() or not workspace.is_dir():
            raise RuntimeError(f"GWC_WORKSPACE does not exist or is not a directory: {workspace}")
        return cls(workspace=workspace)


def resolve_in_workspace(workspace: Path, relative: str | Path = ".") -> Path:
    candidate = (workspace / relative).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise PermissionError(f"Path escapes workspace: {relative}") from exc
    return candidate
