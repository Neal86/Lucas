from __future__ import annotations

import importlib
from pathlib import Path

import gpt_windows_connector.eva_browser_policy as policy


EVA_ENV_KEYS = (
    "LUCAS_EVA_CLIENT_ID",
    "LUCAS_EVA_BROWSER_ENDPOINT",
    "LUCAS_EVA_BROWSER_PROFILE",
    "LUCAS_EVA_BROWSER_EXECUTABLE",
    "LUCAS_EVA_NODE_ID",
    "LUCAS_EVA_BROWSER_USER_DATA_DIR",
    "LUCAS_EVA_ALI_NODE_ID",
    "LUCAS_EVA_ALI_BROWSER_ENDPOINT",
    "LUCAS_EVA_ALI_BROWSER_PROFILE",
    "LUCAS_EVA_ALI_BROWSER_EXECUTABLE",
    "LUCAS_EVA_ALI_BROWSER_USER_DATA_DIR",
    "LUCAS_EVA_HOME_NODE_ID",
    "LUCAS_EVA_HOME_BROWSER_ENDPOINT",
    "LUCAS_EVA_HOME_BROWSER_PROFILE",
    "LUCAS_EVA_HOME_BROWSER_EXECUTABLE",
    "LUCAS_EVA_HOME_BROWSER_USER_DATA_DIR",
)


def _default_policy(monkeypatch):
    for key in EVA_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return importlib.reload(policy)


def test_eva_targets_include_ali_and_home(monkeypatch):
    module = _default_policy(monkeypatch)
    by_label = {target.label: target for target in module.configured_targets()}

    assert by_label["ALI"].node_id == "ali-bc0358dd0a5d"
    assert by_label["Home"].node_id == "N20630"
    assert by_label["ALI"].profile == "eva"
    assert by_label["Home"].profile == "eva"
    assert by_label["ALI"].endpoint == "http://127.0.0.1:9222"
    assert by_label["Home"].endpoint == "http://127.0.0.1:9222"
    assert by_label["Home"].user_data_dir == r"C:\Users\Administrator\.lucas\browser-profiles\eva"


def test_eva_target_is_scoped_to_eva_client_and_exact_node(monkeypatch):
    module = _default_policy(monkeypatch)

    home = module.resolve_eva_browser_target("N20630", module.EVA_CLIENT_ID)
    assert home is not None
    assert home.label == "Home"
    assert module.resolve_eva_browser_target("N20630", "someone-else") is None
    assert module.resolve_eva_browser_target("unknown-node", module.EVA_CLIENT_ID) is None


def test_home_target_can_be_overridden_without_changing_ali(monkeypatch):
    module = _default_policy(monkeypatch)
    monkeypatch.setenv("LUCAS_EVA_HOME_NODE_ID", "HOME-OVERRIDE")
    monkeypatch.setenv("LUCAS_EVA_HOME_BROWSER_USER_DATA_DIR", r"D:\EvaHome")
    module = importlib.reload(module)
    by_label = {target.label: target for target in module.configured_targets()}

    assert by_label["Home"].node_id == "HOME-OVERRIDE"
    assert by_label["Home"].user_data_dir == r"D:\EvaHome"
    assert by_label["ALI"].node_id == "ali-bc0358dd0a5d"


def test_gateway_uses_shared_eva_browser_policy():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "gpt_windows_connector"
        / "gateway.py"
    ).read_text(encoding="utf-8")

    assert "resolve_eva_browser_target" in source
    assert "target = _eva_browser_target(node_id)" in source
    assert '"user_data_dir": target.user_data_dir' in source
    assert '"profile": target.profile' in source
    assert "When the user says Home, use node N20630" in source
    assert "Eva on either Home or ALI" in source
