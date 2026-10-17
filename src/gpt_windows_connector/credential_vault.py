"""Protect desktop account tokens with the current Windows user's DPAPI key."""
from __future__ import annotations

import base64
import binascii
import ctypes
import sys


# Win32 DWORD/BOOL are always 32 bits, even when a test host's C long is 64 bits.
DWORD = ctypes.c_uint32
BOOL = ctypes.c_int32
BYTE_POINTER = ctypes.POINTER(ctypes.c_ubyte)
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", DWORD), ("pbData", BYTE_POINTER)]


class CRYPTPROTECT_PROMPTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("cbSize", DWORD),
        ("dwPromptFlags", DWORD),
        ("hwndApp", ctypes.c_void_p),
        ("szPrompt", ctypes.c_wchar_p),
    ]


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Credential persistence requires Windows DPAPI")


def _native_api():
    crypt32 = ctypes.WinDLL("crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    blob_pointer = ctypes.POINTER(DATA_BLOB)
    common_arguments = [
        blob_pointer,
        ctypes.c_void_p,
        ctypes.POINTER(CRYPTPROTECT_PROMPTSTRUCT),
        DWORD,
        blob_pointer,
    ]
    crypt32.CryptProtectData.argtypes = [blob_pointer, ctypes.c_wchar_p, *common_arguments]
    crypt32.CryptProtectData.restype = BOOL
    crypt32.CryptUnprotectData.argtypes = [
        blob_pointer, ctypes.POINTER(ctypes.c_wchar_p), *common_arguments
    ]
    crypt32.CryptUnprotectData.restype = BOOL
    # HLOCAL is pointer-sized. The default ctypes int result truncates it on x64.
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _blob(data: bytes) -> tuple[DATA_BLOB, object]:
    if len(data) > 0xFFFFFFFF:
        raise ValueError("Credential data exceeds the Windows DPAPI size limit")
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, BYTE_POINTER)), buffer


def _crypt(data: bytes, *, protect: bool) -> bytes:
    crypt32, kernel32 = _native_api()
    source, keepalive = _blob(data)
    target = DATA_BLOB()
    operation = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    try:
        if not operation(
            ctypes.byref(source),
            "Lucas account token" if protect else None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(target),
        ):
            # Capture the native error before cleanup can replace last-error.
            raise ctypes.WinError(ctypes.get_last_error())
        if not target.pbData or not target.cbData:
            raise RuntimeError("Windows DPAPI returned an empty or invalid result")
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        # Native failure may still allocate output. Never free the input buffer,
        # which belongs to ctypes and is retained by keepalive through this call.
        if target.pbData:
            kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))


def _require_text(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError("Credential value must be text")
    if not value:
        raise ValueError("Credential value must not be empty")


def protect_text(value: str) -> str:
    _require_windows()
    _require_text(value)
    try:
        data = value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Credential value must be valid UTF-8 text") from None
    return base64.b64encode(_crypt(data, protect=True)).decode("ascii")


def unprotect_text(value: str) -> str:
    _require_windows()
    _require_text(value)
    try:
        data = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error):
        raise ValueError("Protected credential must be valid base64") from None
    if not data:
        raise ValueError("Protected credential must not be empty")
    try:
        return _crypt(data, protect=False).decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Windows DPAPI returned invalid UTF-8 text") from None
