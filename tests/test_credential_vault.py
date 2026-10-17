"""DPAPI contract tests: all native calls are faked, with synthetic values only."""
from __future__ import annotations

import base64
import ctypes
from types import SimpleNamespace

import pytest

from gpt_windows_connector import credential_vault as vault


class FakeFunction:
    def __init__(self, implementation):
        self.implementation = implementation
        self.argtypes = None
        self.restype = None

    def __call__(self, *arguments):
        return self.implementation(*arguments)


class FakeNative:
    """Never loads a DLL or calls DPAPI, including when run on Windows."""

    def __init__(self):
        self.loads = []
        self.calls = []
        self.freed = []
        self.buffers = []
        self.output = b"synthetic-output"
        self.output_size = None
        self.null_output = False
        self.output_address = None
        self.success = True
        self.exception = None
        self.last_error = 13
        self.crypt32 = SimpleNamespace(
            CryptProtectData=FakeFunction(self.protect),
            CryptUnprotectData=FakeFunction(self.unprotect),
        )
        self.kernel32 = SimpleNamespace(LocalFree=FakeFunction(self.free))

    def load(self, name, *, use_last_error):
        self.loads.append((name, use_last_error))
        return {"crypt32.dll": self.crypt32, "kernel32.dll": self.kernel32}[name]

    def protect(self, *arguments):
        return self.crypt("protect", arguments)

    def unprotect(self, *arguments):
        return self.crypt("unprotect", arguments)

    def crypt(self, operation, arguments):
        source = ctypes.cast(arguments[0], ctypes.POINTER(vault.DATA_BLOB)).contents
        self.calls.append((operation, ctypes.string_at(source.pbData, source.cbData), arguments))
        target = ctypes.cast(arguments[6], ctypes.POINTER(vault.DATA_BLOB)).contents
        target.cbData = len(self.output) if self.output_size is None else self.output_size
        if not self.null_output:
            buffer = ctypes.create_string_buffer(self.output)
            self.buffers.append(buffer)
            address = self.output_address or ctypes.addressof(buffer)
            target.pbData = ctypes.cast(ctypes.c_void_p(address), vault.BYTE_POINTER)
        if self.exception:
            raise self.exception
        return self.success

    def free(self, pointer):
        assert isinstance(pointer, ctypes.c_void_p)
        self.freed.append(pointer.value)
        self.last_error = 999  # Cleanup must not overwrite the reported DPAPI error.
        return None


@pytest.fixture(autouse=True)
def native(monkeypatch):
    fake = FakeNative()
    # Replace the module's sys reference, not the runner's platform globally.
    monkeypatch.setattr(vault, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(vault.ctypes, "WinDLL", fake.load, raising=False)
    monkeypatch.setattr(vault.ctypes, "get_last_error", lambda: fake.last_error, raising=False)
    monkeypatch.setattr(
        vault.ctypes, "WinError", lambda code: OSError(code, "synthetic native error"), raising=False
    )
    return fake


def invoke(operation):
    return getattr(vault, operation)(
        "synthetic-token" if operation == "protect_text" else "c3ludGhldGljLWNpcGhlcg=="
    )


def test_protect_encodes_utf8_and_returns_base64(native):
    assert vault.protect_text("synthetic-测试\0value") == base64.b64encode(native.output).decode("ascii")
    operation, data, arguments = native.calls[0]
    assert operation == "protect"
    assert data == "synthetic-测试\0value".encode("utf-8")
    assert arguments[1] == "Lucas account token"
    assert native.freed == [ctypes.addressof(native.buffers[0])]


def test_unprotect_decodes_base64_and_utf8(native):
    native.output = "synthetic-测试\0value".encode("utf-8")
    assert vault.unprotect_text("c3ludGhldGljLWNpcGhlcg==") == "synthetic-测试\0value"
    operation, data, arguments = native.calls[0]
    assert operation == "unprotect" and data == b"synthetic-cipher"
    assert arguments[1] is None  # Do not request a second allocated description.
    assert native.freed == [ctypes.addressof(native.buffers[0])]


@pytest.mark.parametrize("operation", ["protect_text", "unprotect_text"])
def test_native_signatures_and_user_scoped_noninteractive_flags(native, operation):
    invoke(operation)
    assert native.loads == [("crypt32.dll", True), ("kernel32.dll", True)]
    blob_pointer = ctypes.POINTER(vault.DATA_BLOB)
    common = [
        blob_pointer, ctypes.c_void_p, ctypes.POINTER(vault.CRYPTPROTECT_PROMPTSTRUCT),
        ctypes.c_uint32, blob_pointer,
    ]
    assert native.crypt32.CryptProtectData.argtypes == [blob_pointer, ctypes.c_wchar_p, *common]
    assert native.crypt32.CryptUnprotectData.argtypes == [
        blob_pointer, ctypes.POINTER(ctypes.c_wchar_p), *common
    ]
    assert native.crypt32.CryptProtectData.restype is ctypes.c_int32
    assert native.crypt32.CryptUnprotectData.restype is ctypes.c_int32
    assert native.kernel32.LocalFree.argtypes == [ctypes.c_void_p]
    assert native.kernel32.LocalFree.restype is ctypes.c_void_p
    assert native.calls[0][2][2:6] == (None, None, None, 0x01)


def test_data_blob_has_win32_dword_and_pointer_layout():
    assert ctypes.sizeof(vault.DATA_BLOB._fields_[0][1]) == 4
    assert vault.DATA_BLOB.pbData.offset == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(vault.DATA_BLOB) == 2 * ctypes.sizeof(ctypes.c_void_p)
    source, buffer = vault._blob(b"synthetic\0binary")
    assert source.cbData == 16
    assert ctypes.string_at(source.pbData, source.cbData) == b"synthetic\0binary"
    assert ctypes.cast(source.pbData, ctypes.c_void_p).value == ctypes.addressof(buffer)


@pytest.mark.parametrize("operation", ["protect_text", "unprotect_text"])
@pytest.mark.parametrize("allocated", [False, True])
def test_native_failure_preserves_error_and_frees_any_output(native, operation, allocated):
    native.success = False
    native.null_output = not allocated
    with pytest.raises(OSError) as error:
        invoke(operation)
    assert error.value.errno == 13
    assert native.freed == ([ctypes.addressof(native.buffers[0])] if allocated else [])


@pytest.mark.parametrize("operation", ["protect_text", "unprotect_text"])
def test_native_exception_frees_output(native, operation):
    native.exception = RuntimeError("synthetic native exception")
    with pytest.raises(RuntimeError, match="synthetic native exception"):
        invoke(operation)
    assert native.freed == [ctypes.addressof(native.buffers[0])]


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="x64 pointer regression")
def test_failure_cleanup_does_not_truncate_64_bit_pointer(native):
    native.success = False
    native.output_address = 0x123456789ABC
    with pytest.raises(OSError):
        vault.protect_text("synthetic-token")
    assert native.freed == [0x123456789ABC]


@pytest.mark.parametrize("operation", ["protect_text", "unprotect_text"])
@pytest.mark.parametrize("size,null_output", [(0, False), (0, True), (5, True)])
def test_empty_or_invalid_native_output_is_rejected_and_freed(native, operation, size, null_output):
    native.output_size = size
    native.null_output = null_output
    with pytest.raises(RuntimeError, match="empty or invalid result"):
        invoke(operation)
    assert native.freed == ([] if null_output else [ctypes.addressof(native.buffers[0])])


def test_invalid_decrypted_utf8_is_rejected_without_exposing_data(native):
    native.output = b"synthetic-sensitive-\xff"
    with pytest.raises(ValueError, match="invalid UTF-8 text") as error:
        vault.unprotect_text("c3ludGhldGljLWNpcGhlcg==")
    assert "sensitive" not in str(error.value)
    assert error.value.__suppress_context__
    assert native.freed == [ctypes.addressof(native.buffers[0])]


@pytest.mark.parametrize("operation", ["protect_text", "unprotect_text"])
@pytest.mark.parametrize("value", [None, b"synthetic", 123])
def test_non_text_is_rejected_before_native_calls(native, operation, value):
    with pytest.raises(TypeError, match="must be text"):
        getattr(vault, operation)(value)
    assert not native.loads


@pytest.mark.parametrize("operation", ["protect_text", "unprotect_text"])
def test_empty_text_is_rejected_before_native_calls(native, operation):
    with pytest.raises(ValueError, match="must not be empty"):
        getattr(vault, operation)("")
    assert not native.loads


@pytest.mark.parametrize("value", ["not base64!", "====", "YQ=", "YQ==\n", "YQ==garbage", "测试", " "])
def test_invalid_base64_is_rejected_before_native_calls(native, value):
    with pytest.raises(ValueError, match="valid base64"):
        vault.unprotect_text(value)
    assert not native.loads


def test_invalid_plaintext_utf8_is_rejected_before_native_calls(native):
    with pytest.raises(ValueError, match="valid UTF-8 text"):
        vault.protect_text("synthetic-\ud800")
    assert not native.loads


@pytest.mark.parametrize("operation", ["protect_text", "unprotect_text"])
def test_non_windows_fails_closed_without_native_calls(native, monkeypatch, operation):
    monkeypatch.setattr(vault, "sys", SimpleNamespace(platform="linux"))
    with pytest.raises(RuntimeError, match="requires Windows DPAPI"):
        invoke(operation)
    assert not native.loads
