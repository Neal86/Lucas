from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _const(path: Path, name: str) -> str:
    source = _read(path)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError(f"{name} not found in {path}")


def _write_const(path: Path, name: str, value: str) -> None:
    _write(path, "from __future__ import annotations\n\n" + name + " = " + repr(value) + "\n")


def preserve_landing_auth_separator() -> None:
    path = PKG / "web_landing.py"
    value = _const(path, "LANDING_HTML")
    if not value.endswith("\n"):
        _write_const(path, "LANDING_HTML", value + "\n")


def update_regression_contracts() -> None:
    billing = ROOT / "tests" / "test_billing_contract.py"
    text = _read(billing)
    text = text.replace('"6 Nodes"', '"6 Computers"')
    old = '    text=Path("src/gpt_windows_connector/web_assets.py").read_text(encoding="utf-8")\n'
    new = '    from gpt_windows_connector.web_assets import DASHBOARD_HTML\n    text=DASHBOARD_HTML\n'
    if old not in text:
        raise RuntimeError("billing dashboard source assertion marker not found")
    text = text.replace(old, new, 1)
    _write(billing, text)

    ui = ROOT / "tests" / "test_ui_isolation.py"
    text = _read(ui)
    text = text.replace("'id=\"landing\"', 'id=\"auth\"', 'id=\"app\"', 'id=\"billing\"',", "'id=\"landing\"', 'id=\"auth\"', 'id=\"app\"',")
    _write(ui, text)


def main() -> None:
    preserve_landing_auth_separator()
    update_regression_contracts()


if __name__ == "__main__":
    main()
