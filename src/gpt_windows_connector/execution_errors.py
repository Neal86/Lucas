"""Stable execution error codes shared by Node and Gateway."""
from __future__ import annotations


def execution_error_code(exc: Exception) -> str:
    if getattr(exc, "code", None):
        return str(exc.code)
    if "APPROVAL_TIMEOUT" in str(exc):
        return "APPROVAL_TIMEOUT"
    if isinstance(exc, TimeoutError):
        return "RPC_TIMEOUT"
    if isinstance(exc, PermissionError):
        return "PERMISSION_DENIED"
    if isinstance(exc, ConnectionError):
        return "NODE_DISCONNECTED"
    return "NODE_EXECUTION_FAILED"


class RemoteExecutionError(RuntimeError):
    def __init__(self, message: str, code: str = "NODE_EXECUTION_FAILED") -> None:
        super().__init__(message)
        self.code = code
