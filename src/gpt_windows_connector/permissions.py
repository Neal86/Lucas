from __future__ import annotations

from dataclasses import dataclass


READ_METHODS = {
    "workspace.info", "workspace.browse",
    "files.list", "files.read", "files.search", "files.stat",
    "git.status", "git.diff", "git.log", "git.branch", "git.show",
    "process.poll", "process.list",
    "computer.info", "computer.processes", "computer.windows", "computer.screenshot", "computer.clipboard_get", "computer.ui_elements",
    "browser.discover", "browser.pages", "browser.inspect", "browser.screenshot",
}

ADMIN_ONLY = {"files.delete", "git.push"}


@dataclass(frozen=True)
class NodePolicy:
    level: str = "operate"

    def __post_init__(self) -> None:
        if self.level not in {"read", "operate", "admin"}:
            raise ValueError("Permission level must be read, operate, or admin")

    def authorize(self, method: str) -> None:
        if self.level == "admin":
            return
        if self.level == "read" and method not in READ_METHODS:
            raise PermissionError(f"Method requires operate/admin permission: {method}")
        if self.level == "operate" and method in ADMIN_ONLY:
            raise PermissionError(f"Method requires admin permission: {method}")
