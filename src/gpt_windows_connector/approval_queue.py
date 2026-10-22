"""One FIFO approval queue shared by all executors in this Node process."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class _Request:
    done: threading.Event = field(default_factory=threading.Event)
    allowed: bool = False


class ApprovalQueue:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending: dict[str, _Request] = {}
        self._order: deque[str] = deque()

    def confirm(self, key: str, prompt: Callable[[], bool]) -> bool:
        with self._condition:
            request = self._pending.get(key)
            owner = request is None
            if owner:
                request = _Request()
                self._pending[key] = request
                self._order.append(key)
        assert request is not None
        if not owner:
            request.done.wait()
            return request.allowed
        try:
            with self._condition:
                self._condition.wait_for(lambda: self._order[0] == key)
            request.allowed = bool(prompt())
        except Exception:
            request.allowed = False
        finally:
            with self._condition:
                self._order.popleft()
                del self._pending[key]
                request.done.set()
                self._condition.notify_all()
        return request.allowed


NODE_APPROVAL_QUEUE = ApprovalQueue()
