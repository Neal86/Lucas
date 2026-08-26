from pathlib import Path

import pytest

from gpt_windows_connector.path_guard import validate_command_paths, validate_launch_target


ROOT = Path(r"C:\Users\mrwan")
WORKSPACE = Path(r"C:\Users\mrwan\project")
ROOTS = (ROOT,)


def test_allows_absolute_path_inside_allowed_folder():
    validate_command_paths(WORKSPACE, ROOTS, r'Get-Content "C:\Users\mrwan\project\README.md"')


def test_blocks_absolute_path_on_other_drive():
    with pytest.raises(PermissionError, match="PATH_OUTSIDE_ALLOWED_FOLDERS"):
        validate_command_paths(WORKSPACE, ROOTS, r'Get-Content "G:\secret\data.txt"')


def test_blocks_drive_switch():
    with pytest.raises(PermissionError, match="PATH_OUTSIDE_ALLOWED_FOLDERS"):
        validate_command_paths(WORKSPACE, ROOTS, "G:")


def test_blocks_unc_path():
    with pytest.raises(PermissionError, match="PATH_OUTSIDE_ALLOWED_FOLDERS"):
        validate_command_paths(WORKSPACE, ROOTS, r'Get-Content \\server\share\secret.txt')


def test_blocks_parent_traversal():
    with pytest.raises(PermissionError, match="PATH_OUTSIDE_ALLOWED_FOLDERS"):
        validate_command_paths(WORKSPACE, ROOTS, r'Get-Content ..\..\secret.txt')


def test_operate_cannot_launch_nested_shell():
    with pytest.raises(PermissionError, match="SHELL_LAUNCH_BLOCKED"):
        validate_launch_target(WORKSPACE, ROOTS, "powershell.exe", "-Command Get-ChildItem", "operate")


def test_admin_can_launch_shell_when_paths_are_allowed():
    validate_launch_target(WORKSPACE, ROOTS, "powershell.exe", r'-Command Get-Content C:\Users\mrwan\project\README.md', "admin")
