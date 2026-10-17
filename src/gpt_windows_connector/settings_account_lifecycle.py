"""Tk-thread delivery and cancellation for the isolated account settings page."""
from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
from typing import Any, Callable

from .local_account_state import AccountOperation, StaleAccountOperation


@dataclass
class _Completion:
    request_id: int
    operation: AccountOperation
    result: Any = None
    error: Exception | None = None


class AccountPageLifecycle:
    """Workers never call Tk (including after); the Tk thread polls a queue.

    Cancelling drops callbacks and prevents conditional local writes. A server
    mutation already dispatched may still finish; it is never presented as undone.
    """
    def __init__(self, widget, client, *, on_change: Callable[[], None],
                 on_busy: Callable[[bool], None], thread_factory=threading.Thread) -> None:
        self.widget = widget
        self.client = client
        self.on_change = on_change
        self.on_busy = on_busy
        self.thread_factory = thread_factory
        self.closed = False
        self._sequence = 0
        self._current: tuple[int, AccountOperation, Callable, Callable] | None = None
        self._results: queue.SimpleQueue[_Completion] = queue.SimpleQueue()
        self._after_id = None
        self._seen_generation = client.generation
        self._owned_challenge_generation = None
        widget.bind("<Destroy>", self._destroyed, add="+")
        self._schedule()

    @property
    def busy(self) -> bool:
        return self._current is not None

    def _alive(self) -> bool:
        if self.closed:
            return False
        try:
            return bool(self.widget.winfo_exists())
        except Exception:
            return False

    def _schedule(self) -> None:
        if not self._alive():
            self.close()
            return
        try:
            self._after_id = self.widget.after(40, self._poll)
        except Exception:
            self.close()

    def _destroyed(self, event) -> None:
        if event.widget is self.widget:
            self.close()

    def submit(self, work: Callable[[AccountOperation], Any], *, on_ok: Callable[[Any], None],
               on_error: Callable[[Exception], None], expected_generation: int | None = None) -> bool:
        if self.busy or not self._alive():
            return False
        operation = self.client.new_operation()
        # A stale displayed handler must never acquire ownership of newer work:
        # close/cancel would otherwise cancel the replacement challenge too.
        if expected_generation is not None and operation.generation != expected_generation:
            self.on_change()
            return False
        self._sequence += 1
        request_id = self._sequence
        self._current = request_id, operation, on_ok, on_error
        self.on_busy(True)

        def worker() -> None:
            if operation.cancelled.is_set():
                return
            try:
                result = work(operation)
                completion = _Completion(request_id, operation, result=result)
            except Exception as exc:
                completion = _Completion(request_id, operation, error=exc)
            self._results.put(completion)

        try:
            self.thread_factory(target=worker, daemon=True).start()
        except Exception as exc:
            self._current = None
            self.on_busy(False)
            on_error(exc)
            return False
        return True

    def _poll(self) -> None:
        self._after_id = None
        if not self._alive():
            self.close()
            return
        try:
            while not self._results.empty():
                completion = self._results.get()
                current = self._current
                if current is None or current[0] != completion.request_id:
                    continue
                self._current = None
                operation = completion.operation
                valid = (not operation.cancelled.is_set()
                         and operation.generation == self.client.generation)
                # Record ownership before any UI callback can destroy the page.
                if valid and completion.error is None and isinstance(completion.result, dict):
                    if completion.result.get("verification_required"):
                        self._owned_challenge_generation = operation.generation
                    elif completion.result.get("signed_in"):
                        self._owned_challenge_generation = None
                self.on_busy(False)
                if not self._alive():
                    self.close()
                    return
                valid = (valid and not operation.cancelled.is_set()
                         and operation.generation == self.client.generation)
                if not valid or isinstance(completion.error, StaleAccountOperation):
                    self.on_change()
                elif completion.error is not None:
                    current[3](completion.error)
                else:
                    current[2](completion.result)
                self._seen_generation = self.client.generation
            if self._seen_generation != self.client.generation:
                self._seen_generation = self.client.generation
                self.on_change()
        finally:
            self._schedule()

    def cancel(self) -> None:
        current, self._current = self._current, None
        if current is not None:
            current[1].cancel()
            self.client.cancel_pending_login(generation=current[1].generation)
        if self._owned_challenge_generation is not None:
            self.client.cancel_pending_login(generation=self._owned_challenge_generation)
            self._owned_challenge_generation = None
        if self._alive():
            self.on_busy(False)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.cancel()
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        # Discard queued references promptly; later worker completions remain inert.
        while not self._results.empty():
            self._results.get()
