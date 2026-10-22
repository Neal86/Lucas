from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from gpt_windows_connector.approval_queue import ApprovalQueue
from gpt_windows_connector.access_control import preset_security, resolve_effective_security
from gpt_windows_connector.security import LocalSecurityPolicy


def wait_pending(queue, count):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with queue._condition:
            if len(queue._order) == count:
                return
        threading.Event().wait(0.005)
    pytest.fail('request did not reach approval queue')


def test_fifo_across_independent_policy_objects(monkeypatch):
    queue = ApprovalQueue()
    monkeypatch.setattr('gpt_windows_connector.security.NODE_APPROVAL_QUEUE', queue)
    entered, release = threading.Event(), threading.Event()
    order = []

    def prompt(self, category, method, params, summary, context):
        order.append(params['command'])
        if len(order) == 1:
            entered.set()
            assert release.wait(2)
        return True

    monkeypatch.setattr(LocalSecurityPolicy, '_prompt', prompt)
    policies = [LocalSecurityPolicy({}) for _ in range(3)]
    with ThreadPoolExecutor(3) as pool:
        first = pool.submit(policies[0].authorize, 'shell.run', {'command': 'bcdedit /set first 1'})
        assert entered.wait(2)
        second = pool.submit(policies[1].authorize, 'shell.run', {'command': 'bcdedit /set second 1'})
        wait_pending(queue, 2)
        third = pool.submit(policies[2].authorize, 'shell.run', {'command': 'bcdedit /set third 1'})
        wait_pending(queue, 3)
        assert len(order) == 1
        release.set()
        for future in (first, second, third):
            future.result(2)
    assert order == ['bcdedit /set first 1', 'bcdedit /set second 1', 'bcdedit /set third 1']


@pytest.mark.parametrize('allow', [True, False])
def test_pending_duplicates_share_allow_or_denial_and_later_request_reprompts(allow):
    queue = ApprovalQueue()
    entered, release, joined = threading.Event(), threading.Event(), threading.Event()
    count = []

    def prompt():
        count.append(1)
        entered.set()
        assert release.wait(2)
        return allow

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(queue.confirm, 'same-request', prompt)
        assert entered.wait(2)
        # Observe the duplicate waiting on the same event before releasing owner.
        original_wait = queue._pending['same-request'].done.wait
        def waiting(timeout=None):
            joined.set()
            return original_wait(timeout)
        queue._pending['same-request'].done.wait = waiting
        second = pool.submit(queue.confirm, 'same-request', prompt)
        assert joined.wait(2)
        release.set()
        assert first.result(2) is allow
        assert second.result(2) is allow
    assert count == [1]
    assert queue.confirm('same-request', prompt) is allow
    assert count == [1, 1]


def test_prompt_failure_denies_and_releases_queue():
    queue = ApprovalQueue()
    def broken():
        raise RuntimeError('UI unavailable')
    assert queue.confirm('broken', broken) is False
    assert queue.confirm('next', lambda: True) is True


def full_policy():
    security = resolve_effective_security({'foreground_confirmation': False}, preset_security('full_access'), 'full_access')
    return LocalSecurityPolicy({'security': security})


@pytest.mark.parametrize(('method', 'params'), [
    ('shell.run', {'command': 'Get-Process | Format-Table'}),
    ('shell.run', {'command': 'python -m pip install yt-dlp'}),
    ('shell.run', {'command': 'npm install'}),
    ('shell.run', {'command': 'winget install Python.Python.3.12'}),
    ('shell.run', {'command': 'git clone https://example.com/repo.git'}),
    ('files.write', {'path': r'C:\work\example.txt'}),
    ('files.delete', {'path': r'C:\work\example.txt'}),
    ('git.push', {}), ('browser.navigate', {'url': 'https://example.com'}),
    ('computer.click', {'x': 10, 'y': 10}),
])
def test_full_access_routine_actions_never_prompt(monkeypatch, method, params):
    def unexpected(*args):
        pytest.fail('routine action prompted')
    monkeypatch.setattr(LocalSecurityPolicy, '_prompt', unexpected)
    full_policy().authorize(method, params)


@pytest.mark.parametrize(('method', 'params'), [
    ('shell.run', {'command': 'format C: /Q'}),
    ('process.start', {'command': 'format C: /Q'}),
    ('shell.run', {'command': 'pip install requests; bcdedit /set testsigning on'}),
    ('shell.run', {'command': r'Remove-Item -Recurse -Force C:\Windows'}),
    ('files.delete', {'path': r'C:\Windows\System32'}),
    ('shell.run', {'command': 'reg add HKLM\\Software\\Test'}),
])
def test_true_danger_requires_confirmation_even_with_allow_config(monkeypatch, method, params):
    prompts = []
    def deny(*args):
        prompts.append(1)
        return False
    monkeypatch.setattr(LocalSecurityPolicy, '_prompt', deny)
    policy = full_policy()
    policy.security['approval_policy']['high_risk'] = 'allow'
    with pytest.raises(PermissionError):
        policy.authorize(method, params)
    assert prompts == [1]


def test_full_access_preserves_foreground_toggle_and_explicit_block(monkeypatch):
    monkeypatch.setattr(LocalSecurityPolicy, '_prompt', lambda *args: False)
    policy = full_policy()
    policy.security['foreground_confirmation'] = True
    with pytest.raises(PermissionError):
        policy.authorize('computer.click', {})
    policy.security['foreground_confirmation'] = False
    policy.security['approval_policy']['desktop_control'] = 'block'
    with pytest.raises(PermissionError, match='Blocked'):
        policy.authorize('computer.click', {})


def test_approval_keys_include_full_command_and_target():
    policy = full_policy()
    assert policy._approval_key('shell', 'shell.run', {'command': 'x' * 250 + 'a'}, '') != policy._approval_key('shell', 'shell.run', {'command': 'x' * 250 + 'b'}, '')
    assert policy._approval_key('file_delete', 'files.delete', {'path': 'a'}, '') != policy._approval_key('file_delete', 'files.delete', {'path': 'b'}, '')
