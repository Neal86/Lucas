from pathlib import Path

import pytest

from gpt_windows_connector import files


def test_file_read_write_patch_and_search(tmp_path: Path):
    files.write_text(tmp_path, "src/app.txt", "hello\nworld\n")
    assert files.read_text(tmp_path, "src/app.txt", 2, 2) == "world"
    result = files.patch_text(tmp_path, "src/app.txt", "world", "windows")
    assert result["matches"] == 1
    matches = files.search_text(tmp_path, "windows")
    assert matches[0]["path"].replace("\\", "/") == "src/app.txt"


def test_workspace_escape_is_blocked(tmp_path: Path):
    with pytest.raises(PermissionError):
        files.read_text(tmp_path, "../outside.txt")
