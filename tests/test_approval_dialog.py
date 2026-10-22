from types import SimpleNamespace

import pytest

from gpt_windows_connector import approval_dialog


@pytest.mark.parametrize(('returncode', 'output', 'expected'), [(0, 'allow\n', True), (0, 'deny\n', False), (1, 'allow\n', False), (0, '', False)])
def test_helper_results_fail_closed(monkeypatch, returncode, output, expected):
    def run(args, **kwargs):
        assert args[-1] == 'gpt_windows_connector.approval_dialog'
        assert kwargs['encoding'] == 'utf-8'
        return SimpleNamespace(returncode=returncode, stdout=output)
    monkeypatch.setattr(approval_dialog.subprocess, 'run', run)
    assert approval_dialog.confirm_operation('安全确认', '是否允许') is expected
