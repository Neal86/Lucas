from __future__ import annotations

import ast
import ctypes
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from gpt_windows_connector import settings_single_instance as guard
from gpt_windows_connector.update_ui import InAppUpdater


class Log:
    def __init__(self): self.errors = []
    def info(self, *args): pass
    def error(self, *args): self.errors.append(args)
    def exception(self, *args): self.errors.append(args)


class Call:
    def __init__(self, fn): self.fn = fn
    def __call__(self, *args): return self.fn(*args)


def fake_windows(monkeypatch, responses):
    state = {"error": 0, "time": 0.0, "closed": [], "calls": 0}
    def create(*args):
        assert args == (None, False, guard._MUTEX_NAME)
        handle, error = responses[min(state["calls"], len(responses) - 1)]
        state["calls"] += 1
        state["error"] = error
        return handle
    kernel = SimpleNamespace(CreateMutexW=Call(create), CloseHandle=Call(lambda handle: state["closed"].append(handle)))
    monkeypatch.setattr(guard, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda error: state.update(error=error), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: state["error"], raising=False)
    monkeypatch.setattr(guard, "time", SimpleNamespace(monotonic=lambda: state["time"], sleep=lambda seconds: state.update(time=state["time"] + seconds)))
    return state, kernel


def test_windows_handle_is_pointer_sized_and_retained(monkeypatch):
    handle = 2 ** 40 + 7
    state, kernel = fake_windows(monkeypatch, [(handle, 0)])
    assert guard.acquire_settings_mutex(Log()) == handle
    assert kernel.CreateMutexW.restype is ctypes.wintypes.HANDLE
    assert state["closed"] == []


def test_duplicate_settings_closes_only_its_new_handle(monkeypatch):
    state, _ = fake_windows(monkeypatch, [(91, 183)])
    assert guard.acquire_settings_mutex(Log()) is None
    assert state["closed"] == [91]
    assert state["calls"] == 1


def test_explicit_restart_waits_for_previous_process_then_acquires(monkeypatch):
    state, _ = fake_windows(monkeypatch, [(91, 183), (92, 183), (93, 0)])
    assert guard.acquire_settings_mutex(Log(), wait_seconds=5) == 93
    assert state["closed"] == [91, 92]


def test_restart_wait_is_bounded(monkeypatch):
    state, _ = fake_windows(monkeypatch, [(91, 183)])
    assert guard.acquire_settings_mutex(Log(), wait_seconds=500) is None
    assert 5 <= state["time"] < 5.2
    assert len(state["closed"]) == state["calls"]


def test_guard_api_failure_does_not_open_an_unguarded_window(monkeypatch):
    fake_windows(monkeypatch, [(0, 5)])
    log = Log()
    assert guard.acquire_settings_mutex(log) is None
    assert log.errors


def test_nonwindows_guard_is_a_noop(monkeypatch):
    monkeypatch.setattr(guard, "sys", SimpleNamespace(platform="linux"))
    assert guard.acquire_settings_mutex(Log()) is not None


def test_settings_guard_precedes_configuration_writes():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/gpt_windows_connector/node.py").read_text()
    main = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "main")
    body = ast.get_source_segment(source, main)
    assert body.index("guard_settings_startup(") < body.index("config = _load_config()")
    assert body.index("guard_settings_startup(") < body.index("_ensure_connection_code(config)")


@pytest.mark.parametrize("configure, wait, expected", [(False, False, None), (True, False, 0.0), (True, True, 5.0)])
def test_only_settings_restart_requests_a_wait(monkeypatch, configure, wait, expected):
    calls = []
    monkeypatch.setattr(guard, "acquire_settings_mutex", lambda log, **kwargs: calls.append(kwargs["wait_seconds"]) or object())
    assert guard.guard_settings_startup(SimpleNamespace(configure=configure, wait_for_settings=wait), Log()) is not None
    assert calls == ([] if expected is None else [expected])


def test_updater_restart_uses_bounded_handover(monkeypatch):
    obj = InAppUpdater.__new__(InAppUpdater)
    obj.state = {"return_page": "常规"}
    saved, spawned, scheduled = [], [], []
    obj.save_last_page = saved.append
    obj.root = SimpleNamespace(destroy=lambda: None, after=lambda delay, callback: scheduled.append((delay, callback)))
    monkeypatch.setattr("subprocess.Popen", lambda command, **kwargs: spawned.append((command, kwargs)))
    obj._restart_settings()
    assert saved == ["常规"]
    assert spawned[0][0][-2:] == ["--configure", "--wait-for-settings"]
    assert spawned[0][1]["env"]["LUCAS_SETTINGS_PAGE"] == "常规"
    assert scheduled[0][0] == 300


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows mutex contract")
def test_native_windows_duplicate_handle_and_release(monkeypatch):
    monkeypatch.setattr(guard, "_MUTEX_NAME", "Local\\LucasSettingsTest-" + uuid.uuid4().hex)
    log = Log()
    first = guard.acquire_settings_mutex(log)
    assert first is not None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    close = kernel.CloseHandle
    close.argtypes = [ctypes.wintypes.HANDLE]
    close.restype = ctypes.wintypes.BOOL
    try:
        assert guard.acquire_settings_mutex(log) is None
    finally:
        assert close(first)
    second = guard.acquire_settings_mutex(log)
    assert second is not None
    assert close(second)
    assert not log.errors
