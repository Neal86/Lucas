from pathlib import Path

import pytest

from gpt_windows_connector.executor import Executor


def test_workspace_browse_lists_only_allowed_directories(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    (root / "Project-A").mkdir()
    (root / "Project-B").mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")

    executor = Executor((root,))
    roots = executor.browse_workspaces()
    assert roots["roots"][0]["path"] == str(root.resolve())

    listing = executor.browse_workspaces(str(root))
    assert {item["name"] for item in listing["directories"]} == {"Project-A", "Project-B"}
    assert listing["parent"] is None


def test_workspace_browse_rejects_path_outside_allowed_root(tmp_path: Path):
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    executor = Executor((root,))
    with pytest.raises(PermissionError):
        executor.browse_workspaces(str(outside))
