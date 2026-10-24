import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import threading
import pytest
from gpt_windows_connector import gateway, shell, approval_dialog
from gpt_windows_connector.approval_queue import ApprovalQueue
from gpt_windows_connector.security import LocalSecurityPolicy
from gpt_windows_connector.execution_errors import RemoteExecutionError


def test_gateway_preserves_command_and_structures_runtime_errors(monkeypatch):
    monkeypatch.setattr(gateway, '_user', lambda: SimpleNamespace(id='test'))
    monkeypatch.setattr(gateway, '_actor', lambda *a, **k: {})
    monkeypatch.setattr(gateway, 'ensure_node_active', lambda *a: None)
    monkeypatch.setattr(gateway, 'ensure_request_capacity', lambda *a: None)
    for obj, names in [(gateway.auth, ['record_operation', 'audit']), (gateway.task_runs, ['record_operation'])]:
        for name in names:
            monkeypatch.setattr(obj, name, lambda *a, **k: None)
    command = 'python -m pip install --help'
    async def success(node, user, method, payload, **kwargs):
        assert payload['command'] == command
        return {'exit_code': 0, 'stdout': 'ok'}
    monkeypatch.setattr(gateway.registry, 'rpc', success)
    assert asyncio.run(gateway._node_rpc('test', 'C:\\test', 'shell.run', {'command': command}))['stdout'] == 'ok'
    for exc, code in [(TimeoutError('timeout'), 'RPC_TIMEOUT'), (RemoteExecutionError('denied', 'PERMISSION_DENIED'), 'PERMISSION_DENIED'), (RemoteExecutionError('expired', 'APPROVAL_TIMEOUT'), 'APPROVAL_TIMEOUT')]:
        async def failed(*a, **k):
            raise exc
        monkeypatch.setattr(gateway.registry, 'rpc', failed)
        result = asyncio.run(gateway._node_rpc('test', 'C:\\test', 'shell.run', {'command': command}))
        assert result['ok'] is False and result['error']['code'] == code


def test_queue_wait_expires_without_opening_another_dialog():
    queue = ApprovalQueue()
    entered, release = threading.Event(), threading.Event()
    def prompt():
        entered.set()
        release.wait(2)
        return True
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(queue.confirm, 'first', prompt)
        assert entered.wait(1)
        with pytest.raises(TimeoutError, match='APPROVAL_TIMEOUT'):
            queue.confirm('second', lambda: pytest.fail('concurrent dialog'), timeout=.02)
        release.set()
        assert first.result(1)
    assert not queue._pending and not queue._order
    assert queue.confirm('third', lambda: False) is False


def test_approval_helper_is_bounded_and_timeout_is_preserved(monkeypatch):
    def run(*args, **kwargs):
        assert kwargs['timeout'] == approval_dialog.APPROVAL_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired('approval', kwargs['timeout'])
    monkeypatch.setattr(approval_dialog.subprocess, 'run', run)
    with pytest.raises(TimeoutError, match='APPROVAL_TIMEOUT'):
        LocalSecurityPolicy({})._prompt('shell', 'shell.run', {}, 'test')


def test_duplicate_approval_key_ignores_transport_request_id():
    policy = LocalSecurityPolicy({})
    assert policy._approval_key('shell', 'shell.run', {'command': 'test', '_request_id': 'a'}, '') == policy._approval_key('shell', 'shell.run', {'command': 'test', '_request_id': 'b'}, '')


def test_worker_launch_failure_persists_and_never_reexecutes(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, 'JOB_ROOT', tmp_path / 'jobs')
    calls = []
    def fail(*a, **k):
        calls.append(1)
        raise OSError('worker launch failed')
    monkeypatch.setattr(shell.subprocess, 'Popen', fail)
    first = shell.run_powershell(tmp_path, 'echo ok', _request_id='fail')
    second = shell.run_powershell(tmp_path, 'echo ok', _request_id='fail')
    assert first['error'].startswith('WORKER_START_FAILED')
    assert second['recovered'] and calls == [1]
    assert (tmp_path / 'jobs/fail/result.json').exists()
