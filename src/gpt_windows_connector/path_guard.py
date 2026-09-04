from __future__ import annotations

import ntpath
import re
from pathlib import Path

_WINDOWS_ABSOLUTE = re.compile(r"(?i)(?<![A-Za-z0-9_])([A-Za-z]:[\\/][^\r\n\t\"'`;|&<>]*)")
_UNC = re.compile(r"(?<![\\])((?:\\\\|//)[^\r\n\t\"'`;|&<>]+)")
_DRIVE_SWITCH = re.compile(r"(?i)(?:^|[;&|]\s*|\s)([A-Za-z]:)(?=\s*(?:$|[;&|]))")
_PARENT = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
_URL = re.compile(r"(?i)\b(?:https?|wss?|ftp)://[^\s\"'`;|&<>]+")

def _windows_norm(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(value.strip().strip("\"'")))

def _is_under(candidate: str, root: str) -> bool:
    candidate_n = _windows_norm(candidate)
    root_n = _windows_norm(root)
    try:
        return ntpath.commonpath([candidate_n, root_n]) == root_n
    except ValueError:
        return False

def _allowed_strings(allowed_roots: tuple[Path, ...]) -> tuple[str, ...]:
    return tuple(str(root) for root in allowed_roots)

def validate_command_paths(workspace: Path, allowed_roots: tuple[Path, ...], command: str) -> None:
    text = str(command or "")
    # Network URLs are not Windows filesystem paths. Remove them before scanning
    # so https://host/path is never interpreted as a //host/path UNC path.
    path_text = _URL.sub("", text)
    roots = _allowed_strings(allowed_roots)
    for match in _WINDOWS_ABSOLUTE.finditer(path_text):
        candidate = match.group(1).strip()
        if candidate and not any(_is_under(candidate, root) for root in roots):
            raise PermissionError(f"PATH_OUTSIDE_ALLOWED_FOLDERS: {candidate}")
    for match in _UNC.finditer(path_text):
        candidate = match.group(1).strip()
        # A real UNC path has at least a server and share component. Tokens such
        # as \\LucasPet.exe are not complete UNC paths and must not be treated
        # as filesystem escapes.
        unc_body = candidate.lstrip("\\/")
        if not re.search(r"[\\/]", unc_body):
            continue
        if candidate and not any(_is_under(candidate, root) for root in roots):
            raise PermissionError(f"PATH_OUTSIDE_ALLOWED_FOLDERS: {candidate}")
    for match in _DRIVE_SWITCH.finditer(path_text):
        drive = match.group(1).casefold()
        if not any(ntpath.splitdrive(_windows_norm(root))[0].casefold() == drive for root in roots):
            raise PermissionError(f"PATH_OUTSIDE_ALLOWED_FOLDERS: {drive}")
    if _PARENT.search(path_text):
        raise PermissionError("PATH_OUTSIDE_ALLOWED_FOLDERS: parent traversal is not allowed in shell/process commands")

def validate_launch_target(workspace: Path, allowed_roots: tuple[Path, ...], target: str, arguments: str = "") -> None:
    validate_command_paths(workspace, allowed_roots, f"{target} {arguments}")
    base = ntpath.basename(str(target)).lower()
    if base in {"powershell.exe", "powershell", "pwsh.exe", "pwsh", "cmd.exe", "cmd", "wsl.exe", "wsl", "bash.exe", "bash"}:
        raise PermissionError(f"SHELL_LAUNCH_BLOCKED: {target}; use shell.run inside an Allowed Folder instead")
