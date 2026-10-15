"""Actual extension modules in a deterministic Chrome/WebSocket boundary VM."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

RUNTIME = Path(__file__).with_name("extension_grant_lifecycle_runtime.cjs")
CASES = re.findall(r"^test\('([^']+)'", RUNTIME.read_text(encoding="utf-8"), flags=re.MULTILINE)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for extension runtime tests")
@pytest.mark.parametrize("case", CASES)
def test_extension_grant_lifecycle(case):
    env = {**os.environ, "NODE_NO_WARNINGS": "1"}
    result = subprocess.run(
        [shutil.which("node"), "--experimental-vm-modules", str(RUNTIME), case],
        text=True, capture_output=True, timeout=15, env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
