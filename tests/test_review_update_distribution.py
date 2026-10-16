"""No updater network/process effects are needed to verify review isolation."""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import ast
import io
import json
import tomllib
import zipfile

import pytest

from gpt_windows_connector import update_distribution as policy
from gpt_windows_connector import settings_helpers
from gpt_windows_connector.browser_extension_setup import extension_zip
from gpt_windows_connector.update_ui import InAppUpdater

ROOT = Path(__file__).resolve().parents[1]


class Value:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class Button:
    def configure(self, **kwargs):
        self.state = kwargs["state"]


def updater(monkeypatch):
    obj = InAppUpdater.__new__(InAppUpdater)
    obj.installer_url = policy.STABLE_INSTALLER_URL
    obj.version_status = Value()
    obj.T = lambda zh, en: en
    obj.check_update_button = Button()
    obj.update_button = Button()
    obj.root = SimpleNamespace(after=lambda delay, callback: callback())
    obj.tk = SimpleNamespace(TclError=RuntimeError)
    def forbidden(*args, **kwargs):
        pytest.fail("A blocked review build attempted an update effect")
    obj.fetch_latest_version = forbidden
    obj._show_update_page = forbidden
    obj.before_update = forbidden
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    return obj


@pytest.mark.parametrize("channel", ["review", "", "unknown", "Stable", None])
def test_review_and_unknown_channels_never_update(monkeypatch, channel):
    monkeypatch.setattr(policy, "UPDATE_CHANNEL", channel)
    obj = updater(monkeypatch)
    obj.run_update()
    obj._check_update_worker()
    assert settings_helpers._fetch_latest_version() is None
    assert obj.check_update_button.state == obj.update_button.state == "disabled"
    assert "main installer will not be downloaded or run" in obj.version_status.value


def test_stable_contract_rejects_a_different_installer(monkeypatch):
    monkeypatch.setattr(policy, "UPDATE_CHANNEL", "stable")
    obj = updater(monkeypatch)
    obj.installer_url = "https://example.invalid/install.ps1"
    obj.run_update()
    obj._check_update_worker()
    assert obj.update_button.state == "disabled"


def test_stable_contract_rejects_a_different_version_source(monkeypatch):
    monkeypatch.setattr(policy, "UPDATE_CHANNEL", "stable")
    monkeypatch.setattr(settings_helpers, "LATEST_VERSION_URL", "https://example.invalid/version")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("Unexpected source fetched"))
    assert settings_helpers._fetch_latest_version() is None


def test_stable_contract_retains_existing_version_parser_without_network(monkeypatch):
    monkeypatch.setattr(policy, "UPDATE_CHANNEL", "stable")
    seen = []
    class Response(io.BytesIO):
        pass
    def fetch(request, timeout):
        seen.append(request.full_url)
        return Response(b'[project]\nversion = "1.7.69"\n')
    monkeypatch.setattr("urllib.request.urlopen", fetch)
    assert settings_helpers._fetch_latest_version() == "1.7.69"
    assert seen[0].startswith(policy.STABLE_VERSION_URL + "?t=")


def test_review_marker_and_existing_version_are_not_a_release():
    assert policy.UPDATE_CHANNEL == "review"
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["version"] == "1.7.55"
    # Legacy module-version disagreement is recorded as a release gate, not
    # silently changed by this source-only batch.
    source = (ROOT / "src/gpt_windows_connector/__init__.py").read_text()
    values = [n.value.value for n in ast.parse(source).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)]
    assert values == ["1.2.0"]
    assert metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"] == {
        "extensions/lucas-browser": "gpt_windows_connector/assets/lucas-browser"
    }


def test_download_zip_matches_all_review_extension_assets():
    expected = {"manifest.json", "background.js", "grant_lifecycle.js", "page_actions.js", "popup.html", "popup.js", "popup.css"}
    with zipfile.ZipFile(io.BytesIO(extension_zip())) as archive:
        assert set(archive.namelist()) == {"Lucas-Browser/" + name for name in expected}
        for name in expected:
            assert archive.read("Lucas-Browser/" + name) == (ROOT / "extensions/lucas-browser" / name).read_bytes()
        manifest = json.loads(archive.read("Lucas-Browser/manifest.json"))
        assert manifest["version"] == "2.1.0"
        assert "host_permissions" not in manifest


def test_localized_review_warning_and_description():
    from gpt_windows_connector.settings_constants import SETTINGS_EN
    assert "测试版本" in policy.review_update_message(lambda zh, en: zh)
    assert "review build" in policy.review_update_message(lambda zh, en: en)
    assert any("review builds never automatically switch" in value for value in SETTINGS_EN.values())


def test_closed_settings_window_does_not_schedule_or_start_update_effects(monkeypatch):
    obj = updater(monkeypatch)
    def closed(*args):
        raise obj.tk.TclError("window closed")
    obj.root.after = closed
    obj._check_update_worker()


def test_new_settings_modules_participate_in_restart_detection():
    assert {"settings_single_instance.py", "update_distribution.py"} <= set(InAppUpdater.SETTINGS_RUNTIME_FILES)
    obj = InAppUpdater.__new__(InAppUpdater)
    hashes = obj._settings_hashes()
    assert all(hashes[name] for name in InAppUpdater.SETTINGS_RUNTIME_FILES)
    assert not obj._settings_changed(hashes)
    for name in ["settings_single_instance.py", "update_distribution.py"]:
        before = {**hashes, name: "different-before-update"}
        assert obj._settings_changed(before)
