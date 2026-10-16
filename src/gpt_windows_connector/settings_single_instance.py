"""Process-lifetime Windows Settings window guard, separate from Node execution."""
from __future__ import annotations

import argparse
import sys
import time

_MUTEX_NAME = "Local\\LucasSettingsSingleInstance"


def parse_settings_args(parser):
    parser.add_argument("--wait-for-settings", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def guard_settings_startup(args, log) -> object | None:
    if not args.configure:
        return object()
    handle = acquire_settings_mutex(log, wait_seconds=5.0 if args.wait_for_settings else 0.0)
    if handle is None:
        log.info("Lucas Settings is already open or its single-instance guard is unavailable; exiting")
    return handle


def acquire_settings_mutex(log, *, wait_seconds: float = 0.0) -> object | None:
    """Hold the handle until process exit; wait only for an updater handover.

    No local configuration, account grants or execution policy is read or changed.
    A failed guard closes the duplicate path rather than opening extra windows.
    """
    if sys.platform != "win32":
        return object()
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateMutexW
        create.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        create.restype = wintypes.HANDLE
        close = kernel32.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
        deadline = time.monotonic() + min(5.0, max(0.0, wait_seconds))
        while True:
            ctypes.set_last_error(0)
            handle = create(None, False, _MUTEX_NAME)
            error = ctypes.get_last_error()
            if not handle:
                log.error("Could not acquire Lucas Settings single-instance guard: %s", error)
                return None
            if error != 183:  # ERROR_ALREADY_EXISTS
                return handle
            close(handle)
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.1)
    except Exception:
        log.exception("Could not acquire Lucas Settings single-instance guard")
        return None
