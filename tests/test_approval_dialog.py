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


def test_tray_pythonw_uses_console_python_with_hidden_window(monkeypatch):
    monkeypatch.setattr(approval_dialog.sys, 'executable', '/venv/Scripts/pythonw.exe')
    def run(args, **kwargs):
        assert args[0] == str(__import__('pathlib').Path('/venv/Scripts/python.exe'))
        assert 'creationflags' in kwargs
        return SimpleNamespace(returncode=0, stdout='allow')
    monkeypatch.setattr(approval_dialog.subprocess, 'run', run)
    assert approval_dialog.confirm_operation('title', 'text') is True


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='native Windows UI')
def test_native_windows_close_no_yes(monkeypatch):
    ns = {'_show_dialog': approval_dialog._show_dialog}
    import ctypes
    import tkinter as tk
    from ctypes import wintypes
    
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.GetSystemMenu.restype = wintypes.HMENU
    user32.GetMenuState.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
    user32.GetMenuState.restype = wintypes.UINT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    original_tk = tk.Tk
    errors = []
    
    def buttons(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Button):
                yield child
            yield from buttons(child)
    
    for action, expected in [('close', False), ('no', False), ('yes', True)]:
        def factory(action=action):
            root = original_tk()
            def drive():
                try:
                    hwnd = user32.GetAncestor(root.winfo_id(), 2)
                    state = user32.GetMenuState(user32.GetSystemMenu(hwnd, False), 0xF060, 0)
                    assert state != 0xFFFFFFFF and state & 3 == 0, ('X disabled', state)
                    if action == 'close':
                        assert user32.PostMessageW(hwnd, 0x0010, 0, 0)
                    else:
                        target = next(b for b in buttons(root) if b.cget('text').startswith('Yes' if action == 'yes' else 'No'))
                        target.invoke()
                except Exception as exc:
                    errors.append(repr(exc))
                    root.destroy()
            root.after(300, drive)
            root.after(5000, root.destroy)
            return root
        tk.Tk = factory
        result = ns['_show_dialog']('Lucas staging approval test', 'Automatic UI verification: ' + action)
        assert result is expected, (action, result)
        assert not errors, errors
        print('PASS native Windows dialog', action, 'result=', result, 'X=enabled')
    tk.Tk = original_tk
