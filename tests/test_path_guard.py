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


def test_allows_https_url_in_command():
    validate_command_paths(
        WORKSPACE,
        ROOTS,
        r'Invoke-WebRequest https://github.com/Neal86/nicerp/archive/refs/heads/develop.zip -OutFile "C:\Users\mrwan\project\develop.zip"',
    )


def test_allows_network_urls_in_command():
    validate_command_paths(WORKSPACE, ROOTS, r'curl wss://lucasmcp.com/ws/node')
    validate_command_paths(WORKSPACE, ROOTS, r'curl http://example.com/file.zip')


def test_does_not_treat_incomplete_unc_token_as_path():
    validate_command_paths(WORKSPACE, ROOTS, r'echo \\LucasPet.exe')


def test_blocks_parent_traversal():
    with pytest.raises(PermissionError, match="PATH_OUTSIDE_ALLOWED_FOLDERS"):
        validate_command_paths(WORKSPACE, ROOTS, r'Get-Content ..\..\secret.txt')


def test_computer_launch_cannot_nest_a_shell():
    with pytest.raises(PermissionError, match="SHELL_LAUNCH_BLOCKED"):
        validate_launch_target(WORKSPACE, ROOTS, "powershell.exe", "-Command Get-ChildItem")


def test_normal_launch_target_inside_allowed_path_is_allowed():
    validate_launch_target(WORKSPACE, ROOTS, r"C:\Users\mrwan\project\tool.exe", "--help")
