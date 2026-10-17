"""Origin-bound desktop state and same-process request ownership.

Only protected token bytes belong in this store. HTTP is deliberately outside
its lock; commits are conditional on the session and latest request still owning
that work. This does not roll back a mutation already dispatched to the server.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any


class StaleAccountOperation(RuntimeError):
    """The local session changed, the view closed, or newer work superseded it."""


@dataclass
class AccountOperation:
    generation: int
    cancelled: threading.Event = field(default_factory=threading.Event, repr=False)
    login_started: bool = field(default=False, repr=False)

    def cancel(self) -> None:
        self.cancelled.set()


@dataclass(frozen=True)
class RequestOwner:
    generation: int
    kind: str
    sequence: int
    session_id: str
    user_id: str
    token_protected: str = field(repr=False)
    operation: AccountOperation = field(repr=False, compare=False)


class _SharedState:
    def __init__(self, lock: Any) -> None:
        self.lock = lock
        self.generation = 0
        self.sequence: dict[str, int] = {}
        self.pending: dict[str, Any] | None = None
        self.revoked_sessions: set[str] = set()
        self.session_id: str | None = None
        self.issued_at: float | None = None
        self.expires_at: float | None = None


_registry_lock = threading.Lock()
_registry: dict[str, _SharedState] = {}
_path_locks: dict[str, Any] = {}


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _path_lock(key: str) -> Any:
    # Never wait for a path lock while holding the registry mutex. Raw writes
    # need a lock, but must not initialize account-generation/lifetime metadata.
    with _registry_lock:
        lock = _path_locks.get(key)
        if lock is None:
            lock = _path_locks[key] = threading.RLock()
        return lock


def read_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def finite_number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _valid_lifetime(data: dict[str, Any]) -> bool:
    issued, expires = data.get("issued_at"), data.get("expires_at")
    return (finite_number(issued) and finite_number(expires) and 0 <= issued < expires)


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Private temp files, with same-process replacement serialized per path."""
    lock = _path_lock(_path_key(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        with lock:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class AccountState:
    def __init__(self, origin: str, state_path: Path) -> None:
        self.origin = origin
        self.path = Path(state_path)
        key = _path_key(self.path)
        lock = _path_lock(key)
        # Use the same reentrant lock as atomic_write, including initialization.
        # Registry lookup is complete before waiting for this path's lock.
        with lock, _registry_lock:
            shared = _registry.get(key)
            if shared is None:
                shared = _SharedState(lock)
                data = read_object(self.path)
                if _valid_lifetime(data):
                    shared.session_id = data.get("session_id")
                    shared.issued_at = data["issued_at"]
                    shared.expires_at = data["expires_at"]
                _registry[key] = shared
            self.shared = shared
        self.lock = self.shared.lock

    @property
    def generation(self) -> int:
        with self.lock:
            self._expire_if_due()
            return self.shared.generation

    def state(self) -> dict[str, Any]:
        self._expire_if_due()
        data = read_object(self.path)
        if data.get("version") != 1 or data.get("origin") != self.origin:
            return {}
        required = ("user_id", "session_id", "access_token_dpapi")
        if any(not isinstance(data.get(key), str) or not data[key] for key in required):
            return {}
        if (not _valid_lifetime(data) or not data["issued_at"] <= time.time() < data["expires_at"]
                or data["session_id"] in self.shared.revoked_sessions):
            return {}
        return data

    def operation(self) -> AccountOperation:
        return AccountOperation(self.generation)

    def check_operation(self, operation: AccountOperation) -> None:
        self._expire_if_due()
        if operation.cancelled.is_set() or operation.generation != self.shared.generation:
            raise StaleAccountOperation("Account operation was superseded or cancelled")

    def _expire_if_due(self) -> None:
        expires, issued = self.shared.expires_at, self.shared.issued_at
        if expires is not None and issued is not None and not issued <= time.time() < expires:
            if isinstance(self.shared.session_id, str):
                self.shared.revoked_sessions.add(self.shared.session_id)
            self.shared.session_id = self.shared.issued_at = self.shared.expires_at = None
            self._advance()

    def _advance(self) -> None:
        self.shared.generation += 1
        self.shared.sequence.clear()
        self.shared.pending = None

    def _delete_local(self) -> None:
        # Fail closed in this process even if filesystem removal reports an error.
        session = read_object(self.path).get("session_id")
        if isinstance(session, str):
            self.shared.revoked_sessions.add(session)
        self.shared.session_id = self.shared.issued_at = self.shared.expires_at = None
        self.path.unlink(missing_ok=True)

    def begin_login(self, operation: AccountOperation) -> None:
        with self.lock:
            self.check_operation(operation)
            if operation.login_started:
                raise StaleAccountOperation("This sign-in operation was already used")
            operation.login_started = True
            self._advance()
            operation.generation = self.shared.generation
            self._delete_local()
            self.shared.pending = {"origin": self.origin, "generation": operation.generation}

    def challenge(self, operation: AccountOperation, challenge_id: str, email: str) -> None:
        with self.lock:
            self.check_operation(operation)
            self.shared.pending = {"origin": self.origin, "generation": operation.generation,
                                   "challenge_id": challenge_id, "email": email}

    def check_challenge(self, challenge_id: str, operation: AccountOperation) -> dict[str, Any]:
        self.check_operation(operation)
        pending = self.shared.pending or {}
        if (not challenge_id or pending.get("origin") != self.origin
                or pending.get("generation") != operation.generation
                or pending.get("challenge_id") != challenge_id):
            raise StaleAccountOperation("Verification was cancelled or superseded; sign in again")
        return pending

    def cancel_login(self, generation: int | None = None) -> None:
        with self.lock:
            pending = self.shared.pending or {}
            if (pending.get("origin") == self.origin
                    and (generation is None or generation == self.shared.generation)):
                self._advance()

    def login_commit(self, operation: AccountOperation, data: dict[str, Any]) -> None:
        with self.lock:
            self.check_operation(operation)
            if not _valid_lifetime(data) or not data["issued_at"] <= time.time() < data["expires_at"]:
                raise PermissionError("Lucas account session expired; sign in again")
            atomic_write(self.path, data)
            self.shared.session_id = data["session_id"]
            self.shared.issued_at = data["issued_at"]
            self.shared.expires_at = data["expires_at"]
            self.shared.pending = None

    def request(self, kind: str, operation: AccountOperation | None = None) -> RequestOwner:
        with self.lock:
            operation = operation or self.operation()
            self.check_operation(operation)
            data = self.state()
            if not data:
                raise PermissionError("Sign in to Lucas first")
            sequence = self.shared.sequence.get(kind, 0) + 1
            self.shared.sequence[kind] = sequence
            return RequestOwner(operation.generation, kind, sequence, data["session_id"],
                                data["user_id"], data["access_token_dpapi"], operation)

    def check_owner(self, owner: RequestOwner, *, latest: bool = True) -> dict[str, Any]:
        self.check_operation(owner.operation)
        data = self.state()
        if (owner.generation != self.shared.generation or data.get("session_id") != owner.session_id
                or data.get("user_id") != owner.user_id
                or data.get("access_token_dpapi") != owner.token_protected
                or (latest and self.shared.sequence.get(owner.kind) != owner.sequence)):
            raise StaleAccountOperation("Account operation was superseded or cancelled")
        return data

    def logout(self, *, owner: RequestOwner | None = None, generation: int | None = None) -> bool:
        with self.lock:
            if owner is not None:
                try:
                    self.check_owner(owner)
                except StaleAccountOperation:
                    return False
            if generation is not None and generation != self.shared.generation:
                return False
            # A client pointing at another origin cannot delete its replacement.
            raw = read_object(self.path)
            if raw.get("origin") not in (None, self.origin):
                return False
            self._advance()
            self._delete_local()
            return True

