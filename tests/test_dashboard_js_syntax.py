import re
import shutil
import subprocess

import pytest

from gpt_windows_connector.web_assets import DASHBOARD_HTML


def test_dashboard_inline_javascript_has_valid_syntax():
    """Catch syntax errors that would leave the dashboard completely blank."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for dashboard JavaScript syntax smoke test")

    scripts = re.findall(
        r"<script(?:\\s[^>]*)?>(.*?)</script>",
        DASHBOARD_HTML,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert scripts, "Dashboard should contain inline JavaScript"

    result = subprocess.run(
        [node, "--check", "-"],
        input="\n".join(scripts),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
