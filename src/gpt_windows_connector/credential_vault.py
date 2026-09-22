from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[DATA_BLOB, object]:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _bytes(blob: DATA_BLOB) -> bytes:
    if not blob.pbData or not blob.cbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect_text(value: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Credential persistence requires Windows DPAPI")
    source, keepalive = _blob(value.encode("utf-8"))
    target = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(source), "Lucas account token", None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return base64.b64encode(_bytes(target)).decode("ascii")
    finally:
        kernel32.LocalFree(target.pbData)


def unprotect_text(value: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Credential persistence requires Windows DPAPI")
    source, keepalive = _blob(base64.b64decode(value.encode("ascii")))
    target = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return _bytes(target).decode("utf-8")
    finally:
        kernel32.LocalFree(target.pbData)
