from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


_GENERIC_TITLES = {"", "Lucas task", "operation"}

_READ_FILE_ACTIONS = {"files.list", "files.read", "files.search", "files.stat"}
_WRITE_FILE_ACTIONS = {"files.write", "files.patch", "files.mkdir", "files.move", "files.copy", "files.delete"}
_READ_GIT_ACTIONS = {"git.status", "git.diff", "git.log", "git.show"}
_WRITE_GIT_ACTIONS = {"git.branch", "git.branch_create", "git.branch_switch", "git.add", "git.commit", "git.pull", "git.push"}
_BROWSER_READ_ACTIONS = {
    "browser.discover", "browser.pages", "browser.resolve", "browser.observe", "browser.snapshot",
    "browser.inspect", "browser.screenshot", "browser.network", "browser.diagnostics",
    "browser.check_user_action", "browser.pending_user_actions",
}
_BROWSER_WRITE_ACTIONS = {
    "browser.new_page", "browser.navigate", "browser.semantic_click", "browser.semantic_type",
    "browser.click", "browser.type", "browser.select", "browser.upload", "browser.download",
    "browser.reload", "browser.back", "browser.forward", "browser.press", "browser.hover",
    "browser.scroll", "browser.close_page",
}
_DESKTOP_READ_ACTIONS = {
    "computer.info", "computer.processes", "computer.windows", "computer.screenshot",
    "computer.clipboard_get", "computer.ui_elements",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _legacy_title_candidates(action: str, target: str | None) -> set[str]:
    action = _clean(action)
    clean_target = _clean(target)
    candidates = {action}
    if not clean_target:
        return candidates

    candidates.add(f"{action} · {clean_target}")
    for path_type in (Path, PureWindowsPath, PurePosixPath):
        try:
            name = _clean(path_type(clean_target).name)
        except Exception:
            name = ""
        if name:
            candidates.add(f"{action} · {name}")
    return candidates


def _explicit_title_from_steps(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        details = step.get("details")
        if not isinstance(details, dict):
            continue
        title = _clean(details.get("task_title"))
        if title:
            return title[:180]
    return ""


def _looks_generated(stored_title: str, steps: list[dict[str, Any]]) -> bool:
    stored_title = _clean(stored_title)
    if stored_title in _GENERIC_TITLES:
        return True
    for step in steps:
        if stored_title in _legacy_title_candidates(
            _clean(step.get("action")),
            _clean(step.get("target")) or None,
        ):
            return True
    return False


def _shell_commands(steps: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    for step in steps:
        if _clean(step.get("action")) != "shell.run":
            continue
        details = step.get("details")
        if not isinstance(details, dict):
            continue
        raw = details.get("sub_operations")
        if isinstance(raw, list):
            commands.extend(_clean(value) for value in raw if _clean(value))
    return commands


def _shell_title(commands: list[str]) -> str:
    text = "\n".join(commands).lower()
    if not text:
        return "Run local command"

    has_test = any(marker in text for marker in (
        "pytest", "python -m pytest", "npm test", "npm run test", "pnpm test",
        "yarn test", "vitest", "jest", "unittest",
    ))
    has_write = any(marker in text for marker in (
        "set-content", "add-content", "new-item", "copy-item", "move-item", "remove-item",
        "mkdir ", " md ", "touch ", " cp ", " mv ", " rm ", "del ", "echo ",
    ))
    has_deploy = any(marker in text for marker in (
        "coolify", "docker compose up", "docker-compose up", "kubectl apply",
        "vercel", "railway up", "fly deploy", "npm run deploy", "pnpm deploy", "yarn deploy",
    ))
    has_logs = any(marker in text for marker in (
        "journalctl", "docker logs", "kubectl logs", "get-winevent", "eventlog",
        ".log", "tail ", "tail -", "get-content",
    )) and any(marker in text for marker in ("log", "journal", "event"))
    has_install = any(marker in text for marker in (
        "pip install", "pip3 install", "npm install", "npm ci", "pnpm install",
        "yarn install", "winget install", "choco install",
    ))
    has_build = any(marker in text for marker in (
        "npm run build", "pnpm build", "yarn build", "python -m build", "docker build",
    ))
    has_media = any(marker in text for marker in (
        "ffmpeg", "remotion", "hypit", "minimax", "grok-imagine-video", "imageio",
    ))
    has_git_write = any(marker in text for marker in (
        "git add", "git commit", "git push", "git pull", "git merge", "git rebase",
        "git checkout", "git switch", "git cherry-pick",
    ))
    has_git_read = any(marker in text for marker in (
        "git status", "git diff", "git log", "git show", "git branch",
    ))
    has_web = any(marker in text for marker in (
        "invoke-webrequest", "invoke-restmethod", "curl ", "curl.exe", "wget ",
    ))
    has_read = any(marker in text for marker in (
        "get-content", "get-childitem", "select-string", "resolve-path", "test-path",
        " rg ", "grep ", "findstr ", " dir ", " ls ",
    ))

    if has_deploy:
        return "Deploy application"
    if has_media:
        return "Process media files"
    if has_write and has_test:
        return "Update and test project"
    if has_test:
        return "Run project tests"
    if has_install:
        return "Install project dependencies"
    if has_build:
        return "Build project"
    if has_logs:
        return "Check application logs"
    if has_git_write:
        return "Update Git repository"
    if has_git_read:
        return "Review Git repository"
    if has_write:
        return "Update local files"
    if has_web:
        return "Call web service"
    if has_read:
        return "Inspect local files"
    if any(marker in text for marker in ("python ", "python.exe", "node ", "node.exe", "powershell ", "pwsh ")):
        return "Run project script"
    return "Run local command"


def _action_title(actions: set[str]) -> str:
    if actions & _BROWSER_WRITE_ACTIONS:
        return "Interact with website"
    if actions & _BROWSER_READ_ACTIONS or any(a.startswith("browser.") for a in actions):
        return "Inspect website"
    if actions & _WRITE_FILE_ACTIONS:
        return "Update local files"
    if actions & _READ_FILE_ACTIONS:
        return "Inspect local files"
    if actions & _WRITE_GIT_ACTIONS:
        return "Update Git repository"
    if actions & _READ_GIT_ACTIONS:
        return "Review Git repository"
    if any(a.startswith("process.") for a in actions):
        return "Manage local process"
    if any(a.startswith("computer.") and a not in _DESKTOP_READ_ACTIONS for a in actions):
        return "Use desktop"
    if actions & _DESKTOP_READ_ACTIONS:
        return "Inspect desktop"
    if "workspace.info" in actions:
        return "Inspect workspace"
    if actions:
        first = sorted(actions)[0]
        return first.replace(".", " ").replace("_", " ").strip().title()
    return "Lucas task"


def display_task_title(stored_title: str | None, steps: list[dict[str, Any]]) -> str:
    """Return a user-facing task title without exposing tool names or workspace paths.

    Explicit AI-provided task titles always win. Historical auto-generated titles are
    recognized from their action/target shape and replaced at read time, so existing
    records improve without a data migration.
    """
    stored = _clean(stored_title)

    explicit = _explicit_title_from_steps(steps)
    if explicit:
        return explicit

    if stored and not _looks_generated(stored, steps):
        return stored[:180]

    shell_title = _shell_title(_shell_commands(steps))
    if shell_title != "Run local command":
        return shell_title

    actions = {_clean(step.get("action")) for step in steps if _clean(step.get("action"))}
    if "shell.run" in actions:
        other_actions = {action for action in actions if action != "shell.run"}
        if other_actions:
            other_title = _action_title(other_actions)
            if other_title not in {"Lucas Task", "Inspect workspace"}:
                return other_title
        return shell_title

    return _action_title(actions)
