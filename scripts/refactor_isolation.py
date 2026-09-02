from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"


def read(name: str) -> str:
    return (PKG / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    path = PKG / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def node_range(source: str, *, kind: type[ast.AST], name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, kind) and getattr(node, "name", None) == name:
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            return start, end, "".join(lines[start:end])
    raise RuntimeError(f"Could not find {name}")


def assignment_range(source: str, target_name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == target_name for t in targets):
                start = node.lineno - 1
                end = node.end_lineno or node.lineno
                return start, end, "".join(lines[start:end])
    raise RuntimeError(f"Could not find assignment {target_name}")


def replace_range(source: str, start: int, end: int, replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    return "".join(lines[:start]) + replacement + "".join(lines[end:])


def extract_web_assets() -> None:
    source = read("webapp.py")
    if "from .web_assets import DASHBOARD_HTML" in source:
        return
    start, end, block = assignment_range(source, "DASHBOARD_HTML")
    write("web_assets.py", "from __future__ import annotations\n\n" + block)
    source = replace_range(source, start, end, "from .web_assets import DASHBOARD_HTML\n")
    write("webapp.py", source)


def extract_settings_constants() -> None:
    source = read("settings_ui.py")
    if "from .settings_constants import" in source:
        return
    start_marker = "SETTINGS_EN = {"
    end_marker = "def detect_security_preset"
    start = source.index(start_marker)
    end = source.index(end_marker)
    block = source[start:end]
    module = (
        "from __future__ import annotations\n\n"
        "import os\n"
        "from pathlib import Path\n\n"
        + block
    )
    write("settings_constants.py", module)
    names = [
        "SETTINGS_EN", "APP_NAME", "DEFAULT_GATEWAY", "CONFIG_DIR", "CONFIG_FILE",
        "STATE_FILE", "STATUS_FILE", "LOG_FILE", "TRAY_PID_FILE", "STATUS_STALE_SECONDS",
        "UI_STATE_FILE", "TASK_RUNS_FILE", "ACCESS_FILE", "LATEST_VERSION_URL", "INSTALLER_URL",
        "APPROVAL_DEFAULTS", "PRESETS", "PRESET_DESCRIPTIONS",
    ]
    imported = "from .settings_constants import (\n    " + ",\n    ".join(names) + ",\n)\n\n"
    source = source[:start] + imported + source[end:]
    write("settings_ui.py", source)


def extract_gateway_stores() -> None:
    source = read("gateway.py")
    if "from .gateway_stores import NodeAuthStore, UserNodeBindingStore" in source:
        return
    ranges = []
    blocks = []
    for name in ("NodeAuthStore", "UserNodeBindingStore"):
        start, end, block = node_range(source, kind=ast.ClassDef, name=name)
        ranges.append((start, end, name))
        blocks.append(block)
    module = (
        "from __future__ import annotations\n\n"
        "import json\nimport sqlite3\nimport time\nfrom pathlib import Path\n\n"
        + "\n\n".join(blocks)
    )
    write("gateway_stores.py", module)
    lines = source.splitlines(keepends=True)
    first = min(r[0] for r in ranges)
    for start, end, _ in sorted(ranges, reverse=True):
        lines[start:end] = []
    lines.insert(first, "from .gateway_stores import NodeAuthStore, UserNodeBindingStore\n\n")
    write("gateway.py", "".join(lines))


def extract_gateway_events() -> None:
    source = read("gateway.py")
    if "from .gateway_events import BrowserEventHub" in source:
        return
    start, end, block = node_range(source, kind=ast.ClassDef, name="BrowserEventHub")
    module = (
        "from __future__ import annotations\n\n"
        "import asyncio\nfrom starlette.websockets import WebSocket\n\n" + block
    )
    write("gateway_events.py", module)
    source = replace_range(source, start, end, "from .gateway_events import BrowserEventHub\n")
    write("gateway.py", source)


def extract_node_approval() -> None:
    source = read("node.py")
    if "from .node_approval import prompt_access_request as _prompt_access_request" in source:
        return
    start, end, block = node_range(source, kind=ast.AsyncFunctionDef, name="_prompt_access_request") if "async def _prompt_access_request" in source else node_range(source, kind=ast.FunctionDef, name="_prompt_access_request")
    block = block.replace("def _prompt_access_request", "def prompt_access_request", 1)
    module = "from __future__ import annotations\n\nfrom .i18n import tr\n\n" + block
    write("node_approval.py", module)
    source = replace_range(source, start, end, "from .node_approval import prompt_access_request as _prompt_access_request\n")
    write("node.py", source)


def write_architecture_docs_and_test() -> None:
    doc = '''# Lucas architecture boundaries\n\nThis repository intentionally keeps high-risk responsibilities isolated so a change in one area does not require editing unrelated code.\n\n## Stable boundaries\n\n- `webapp.py`: HTTP composition and route wiring only. Large HTML/CSS/JS payloads live in `web_assets.py`.\n- `gateway.py`: gateway orchestration only. Persistence lives in `gateway_stores.py`; browser event fan-out lives in `gateway_events.py`.\n- `node.py`: node lifecycle, protocol and dispatch. Local access-request UI lives in `node_approval.py`.\n- `settings_ui.py`: settings window composition. Shared constants and presets live in `settings_constants.py`. New settings pages should be added as separate modules instead of growing this file.\n- `tray.py`: tray orchestration. New Windows integration helpers should be added in dedicated modules rather than embedded into the tray class.\n\n## Change rule\n\nA feature change should touch only its owning module plus tests. Cross-boundary changes must be explicit and covered by regression tests. Do not move authentication, authorization, device identity, credential persistence, reconnect policy, UI rendering and installer behavior into the same module.\n\n## Non-regression areas\n\nThe following behavior is treated as protected: Node ID persistence; device credential persistence; local permission authority; allowed-folder enforcement; account-to-node authorization; OAuth/API contracts; WebSocket protocol; tray/node lifecycle; installer configuration preservation; dashboard node/AI metadata editing.\n'''
    (ROOT / "ARCHITECTURE.md").write_text(doc, encoding="utf-8")
    test = '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\nPKG = ROOT / "src" / "gpt_windows_connector"\n\n\ndef test_large_payloads_are_not_embedded_in_orchestrators():\n    webapp = (PKG / "webapp.py").read_text(encoding="utf-8")\n    gateway = (PKG / "gateway.py").read_text(encoding="utf-8")\n    node = (PKG / "node.py").read_text(encoding="utf-8")\n    settings = (PKG / "settings_ui.py").read_text(encoding="utf-8")\n    assert "DASHBOARD_HTML =" not in webapp\n    assert "class NodeAuthStore" not in gateway\n    assert "class UserNodeBindingStore" not in gateway\n    assert "class BrowserEventHub" not in gateway\n    assert "def _prompt_access_request" not in node\n    assert "SETTINGS_EN =" not in settings\n\n\ndef test_isolation_modules_exist():\n    required = {\n        "web_assets.py", "gateway_stores.py", "gateway_events.py",\n        "node_approval.py", "settings_constants.py",\n    }\n    assert required <= {p.name for p in PKG.iterdir() if p.is_file()}\n\n\ndef test_orchestrator_size_budgets_do_not_regress():\n    budgets = {\n        "webapp.py": 45000,\n        "gateway.py": 34000,\n        "node.py": 26000,\n        "settings_ui.py": 54000,\n        "tray.py": 22000,\n    }\n    failures = []\n    for name, budget in budgets.items():\n        size = (PKG / name).stat().st_size\n        if size > budget:\n            failures.append(f"{name}: {size} > {budget}")\n    assert not failures, "Architecture size budget exceeded: " + "; ".join(failures)\n'''
    (ROOT / "tests" / "test_architecture_boundaries.py").write_text(test, encoding="utf-8")


def main() -> None:
    extract_web_assets()
    extract_settings_constants()
    extract_gateway_stores()
    extract_gateway_events()
    extract_node_approval()
    write_architecture_docs_and_test()


if __name__ == "__main__":
    main()
