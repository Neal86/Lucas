import pytest

from gpt_windows_connector.permissions import NodePolicy


def test_read_policy_blocks_mutation():
    NodePolicy("read").authorize("files.read")
    with pytest.raises(PermissionError):
        NodePolicy("read").authorize("files.write")


def test_operate_policy_blocks_admin_actions():
    NodePolicy("operate").authorize("shell.run")
    with pytest.raises(PermissionError):
        NodePolicy("operate").authorize("git.push")


def test_admin_policy_allows_everything():
    NodePolicy("admin").authorize("files.delete")
    NodePolicy("admin").authorize("git.push")
