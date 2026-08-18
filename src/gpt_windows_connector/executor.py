from __future__ import annotations

import asyncio
from pathlib import Path

from . import browser, computer, files, git_tools, processes, shell
from .config import resolve_in_workspace, validate_workspace
from .permissions import NodePolicy


class Executor:
    def __init__(self, allowed_roots: tuple[Path, ...], permission_level: str = "operate") -> None:
        self.allowed_roots = tuple(root.resolve() for root in allowed_roots)
        self.policy = NodePolicy(permission_level)

    def workspace(self, raw: str) -> Path:
        return validate_workspace(self.allowed_roots, raw)

    def browse_workspaces(self, path: str | None = None) -> dict:
        if not path:
            roots = []
            for root in self.allowed_roots:
                if root.exists() and root.is_dir():
                    roots.append({"name": root.name or root.anchor or str(root), "path": str(root)})
            return {"path": None, "parent": None, "roots": roots, "directories": []}

        current = validate_workspace(self.allowed_roots, path)
        directories: list[dict] = []
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            raise PermissionError(f"Unable to browse folder: {current}") from exc
        for child in children:
            try:
                if child.is_dir() and not child.is_symlink():
                    directories.append({"name": child.name, "path": str(child.resolve())})
            except OSError:
                continue

        parent = None
        candidate_parent = current.parent
        if candidate_parent != current:
            for root in self.allowed_roots:
                try:
                    candidate_parent.relative_to(root)
                    parent = str(candidate_parent)
                    break
                except ValueError:
                    continue
        return {
            "path": str(current),
            "parent": parent,
            "roots": [],
            "directories": directories[:1000],
        }

    async def call(self, method: str, params: dict) -> object:
        self.policy.authorize(method)
        p = dict(params or {})
        workspace = self.workspace(p.pop("workspace")) if "workspace" in p else None
        sync = {
            "workspace.info": lambda: {"path": str(workspace), "name": workspace.name},
            "workspace.browse": lambda: self.browse_workspaces(**p),
            "files.list": lambda: files.list_files(workspace, **p),
            "files.read": lambda: files.read_text(workspace, **p),
            "files.write": lambda: files.write_text(workspace, **p),
            "files.patch": lambda: files.patch_text(workspace, **p),
            "files.search": lambda: files.search_text(workspace, **p),
            "files.stat": lambda: files.stat_path(workspace, **p),
            "files.mkdir": lambda: files.make_dir(workspace, **p),
            "files.move": lambda: files.move_path(workspace, **p),
            "files.copy": lambda: files.copy_path(workspace, **p),
            "files.delete": lambda: files.delete_path(workspace, **p),
            "shell.run": lambda: shell.run_powershell(workspace, **p),
            "process.start": lambda: processes.start_process(workspace, **p),
            "process.poll": lambda: processes.poll_process(workspace=workspace, **p),
            "process.stop": lambda: processes.stop_process(workspace=workspace, **p),
            "process.list": lambda: processes.list_managed_processes(workspace=workspace),
            "git.status": lambda: git_tools.status(workspace),
            "git.diff": lambda: git_tools.diff(workspace, **p),
            "git.log": lambda: git_tools.log(workspace, **p),
            "git.branch": lambda: git_tools.branch(workspace),
            "git.branch_create": lambda: git_tools.branch_create(workspace, **p),
            "git.branch_switch": lambda: git_tools.branch_switch(workspace, **p),
            "git.add": lambda: git_tools.add(workspace, **p),
            "git.commit": lambda: git_tools.commit(workspace, **p),
            "git.pull": lambda: git_tools.pull(workspace, **p),
            "git.push": lambda: git_tools.push(workspace, **p),
            "git.show": lambda: git_tools.show(workspace, **p),
            "browser.discover": lambda: browser.discover_browsers(),
            "computer.info": lambda: computer.system_info(),
            "computer.processes": lambda: computer.list_processes(**p),
            "computer.launch": lambda: computer.launch_app(**p),
            "computer.windows": lambda: computer.list_windows(),
            "computer.activate": lambda: computer.activate_window(**p),
            "computer.screenshot": lambda: computer.screenshot(),
            "computer.click": lambda: computer.click(**p),
            "computer.move": lambda: computer.move(**p),
            "computer.drag": lambda: computer.drag(**p),
            "computer.type": lambda: computer.type_text(**p),
            "computer.hotkey": lambda: computer.hotkey(**p),
            "computer.press": lambda: computer.press(**p),
            "computer.scroll": lambda: computer.scroll(**p),
            "computer.clipboard_get": lambda: computer.clipboard_get(),
            "computer.clipboard_set": lambda: computer.clipboard_set(**p),
            "computer.ui_elements": lambda: computer.ui_elements(**p),
            "computer.ui_click": lambda: computer.ui_click(**p),
            "computer.ui_set_text": lambda: computer.ui_set_text(**p),
        }
        if method in sync:
            return await asyncio.to_thread(sync[method])

        if method == "browser.upload":
            if workspace is None:
                raise PermissionError("browser.upload requires a project workspace")
            paths = p.get("paths") or []
            p["paths"] = [str(resolve_in_workspace(workspace, path)) for path in paths]
        elif method == "browser.download":
            if workspace is None:
                raise PermissionError("browser.download requires a project workspace")
            p["save_path"] = str(resolve_in_workspace(workspace, p["save_path"]))

        async_methods = {
            "browser.connect_cdp": browser.connect_cdp,
            "browser.launch_persistent": browser.launch_persistent,
            "browser.pages": browser.pages,
            "browser.new_page": browser.new_page,
            "browser.navigate": browser.navigate,
            "browser.inspect": browser.inspect,
            "browser.click": browser.click,
            "browser.type": browser.type_text,
            "browser.select": browser.select_option,
            "browser.upload": browser.upload,
            "browser.download": browser.download,
            "browser.screenshot": browser.screenshot,
            "browser.close": browser.close,
        }
        func = async_methods.get(method)
        if func:
            return await func(**p)
        raise KeyError(f"Unknown method: {method}")
