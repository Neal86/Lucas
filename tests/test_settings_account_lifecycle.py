"""Account-only UI regressions without Tk, threads, network, or real state.

The production lifecycle and page builder run unchanged. Deterministic worker
steps allow close/cancel/replacement to interleave with work without timing races.
"""
from collections import deque
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest

from gpt_windows_connector.local_account import LocalAccountClient
from gpt_windows_connector.local_account_state import AccountOperation, StaleAccountOperation
from gpt_windows_connector.settings_account_lifecycle import AccountPageLifecycle
from gpt_windows_connector import settings_account_ui


class FakeTk:
    def __init__(self):
        self.context = "main"
        self.widgets = []
        self.forbidden_calls = []

    def check_main(self, action):
        if self.context != "main":
            self.forbidden_calls.append(action)
            raise AssertionError(f"Tk called from worker: {action}")

    @contextmanager
    def as_context(self, context):
        previous, self.context = self.context, context
        try:
            yield
        finally:
            self.context = previous

    def interrupt_on_main(self, callback):
        """Model the main event loop running while a worker awaits a response."""
        with self.as_context("main"):
            callback()

    def _widget(self, kind, parent=None, **options):
        self.check_main(f"create {kind}")
        widget = FakeWidget(self, kind, parent, options)
        self.widgets.append(widget)
        return widget

    def Frame(self, parent=None, **options):
        return self._widget("Frame", parent, **options)

    def Label(self, parent=None, **options):
        return self._widget("Label", parent, **options)

    def Entry(self, parent=None, **options):
        return self._widget("Entry", parent, **options)

    def Button(self, parent=None, **options):
        return self._widget("Button", parent, **options)

    def StringVar(self, *, value):
        self.check_main("StringVar")
        return FakeVariable(self, value)


class FakeVariable:
    def __init__(self, tk, value):
        self.tk, self.value = tk, value

    def get(self):
        self.tk.check_main("variable.get")
        return self.value

    def set(self, value):
        self.tk.check_main("variable.set")
        self.value = value


class FakeWidget:
    def __init__(self, tk, kind, parent, options):
        self.tk, self.kind, self.parent, self.options = tk, kind, parent, options
        self.children = []
        self.packed = False
        self.destroyed = False
        self.bindings = {}
        self.afters = {}
        self.after_cancelled = []
        self._after_sequence = 0
        if parent is not None:
            parent.children.append(self)

    def pack(self, **options):
        self.tk.check_main("pack")
        self.packed = True
        self.pack_options = options

    def pack_forget(self):
        self.tk.check_main("pack_forget")
        self.packed = False

    def configure(self, **options):
        self.tk.check_main("configure")
        self.options.update(options)

    def bind(self, event, callback, *, add):
        self.tk.check_main("bind")
        assert add == "+"
        self.bindings.setdefault(event, []).append(callback)

    def winfo_exists(self):
        self.tk.check_main("winfo_exists")
        return not self.destroyed

    def after(self, delay, callback):
        self.tk.check_main("after")
        assert delay > 0
        assert not self.destroyed
        self._after_sequence += 1
        after_id = f"after-{self._after_sequence}"
        self.afters[after_id] = callback
        return after_id

    def after_cancel(self, after_id):
        self.tk.check_main("after_cancel")
        self.after_cancelled.append(after_id)
        self.afters.pop(after_id, None)

    def poll_once(self):
        self.tk.check_main("event loop")
        assert len(self.afters) == 1
        after_id, callback = next(iter(self.afters.items()))
        del self.afters[after_id]
        callback()

    def emit_destroy(self, widget=None):
        self.tk.check_main("destroy")
        target = widget or self
        if target is self:
            self.destroyed = True
        for callback in self.bindings.get("<Destroy>", []):
            callback(SimpleNamespace(widget=target))

    def invoke(self):
        self.tk.check_main("invoke")
        if self.options.get("state", "normal") != "disabled":
            return self.options["command"]()


class FakeQueue:
    def __init__(self, tk):
        self.tk, self.items, self.put_contexts = tk, deque(), []

    def put(self, item):
        self.put_contexts.append(self.tk.context)
        self.items.append(item)

    def empty(self):
        return not self.items

    def get(self):
        return self.items.popleft()


class FakeThreads:
    def __init__(self, tk):
        self.tk, self.jobs = tk, []
        self.fail_start = None

    def __call__(self, *, target, daemon):
        assert daemon is True

        def start():
            if self.fail_start:
                raise self.fail_start
            self.jobs.append(target)

        return SimpleNamespace(start=start)

    def run_next(self):
        target = self.jobs.pop(0)
        with self.tk.as_context("worker"):
            target()


class SyntheticAccount:
    """An in-memory account with the production operation/generation contract."""
    def __init__(self):
        self.generation = 0
        self.signed_in = False
        self.name = "Test Person"
        self.email = "person@example.invalid"
        self.user_id = "synthetic-user"
        self.pending = None
        self.operations = []
        self.cancelled_generations = []
        self.calls = []
        self.login_count = 0
        self.require_verification = True
        self.login_error = None
        self.verify_error = None
        self.during_login = None
        self.during_verify = None

    def new_operation(self):
        operation = AccountOperation(self.generation)
        self.operations.append(operation)
        return operation

    def check(self, operation):
        if operation.cancelled.is_set() or operation.generation != self.generation:
            raise StaleAccountOperation("Synthetic operation cancelled or superseded")

    def status(self):
        return {"signed_in": self.signed_in, "name": self.name if self.signed_in else "",
                "email": self.email if self.signed_in else "", "user_id": self.user_id if self.signed_in else "",
                "generation": self.generation}

    def cancel_pending_login(self, *, generation):
        self.cancelled_generations.append(generation)
        if self.pending is not None and generation == self.generation:
            self.pending = None
            self.generation += 1

    def logout(self, *, generation):
        self.calls.append(("logout", generation))
        if generation == self.generation:
            self.generation += 1
            self.signed_in = False
            self.pending = None

    def login(self, email, password, *, operation):
        self.check(operation)
        self.calls.append(("login", email, password))
        self.login_count += 1
        self.generation += 1
        operation.generation = self.generation
        self.signed_in = False
        challenge = f"synthetic-challenge-{self.login_count}"
        self.pending = challenge
        if self.during_login:
            self.during_login()
        self.check(operation)
        if self.login_error:
            raise self.login_error
        if self.require_verification:
            return {"verification_required": True, "challenge_id": challenge,
                    "email": email, "generation": self.generation}
        self.pending = None
        self.signed_in = True
        return self.status()

    def verify_login(self, challenge, code, *, operation):
        self.check(operation)
        assert challenge == self.pending
        self.calls.append(("verify", challenge, code))
        if self.during_verify:
            self.during_verify()
        self.check(operation)
        if self.verify_error:
            raise self.verify_error
        self.pending = None
        self.signed_in = True
        return self.status()

    def resend_login(self, challenge, *, operation):
        self.check(operation)
        assert challenge == self.pending
        self.calls.append(("resend", challenge))
        return {"sent": True}


@pytest.fixture
def lifecycle_case():
    tk = FakeTk()
    widget, client, events = tk.Frame(), SyntheticAccount(), []
    threads = FakeThreads(tk)

    def record(kind, value=None):
        tk.check_main(f"callback {kind}")
        events.append((kind, value))

    lifecycle = AccountPageLifecycle(widget, client, thread_factory=threads,
                                     on_change=lambda: record("change"),
                                     on_busy=lambda busy: record("busy", busy))
    lifecycle._results = FakeQueue(tk)
    case = SimpleNamespace(tk=tk, widget=widget, client=client, events=events,
                           lifecycle=lifecycle, threads=threads,
                           ok=lambda result: record("ok", result),
                           error=lambda error: record("error", error))
    yield case
    lifecycle.close()
    assert tk.forbidden_calls == []


def submit(case, work):
    return case.lifecycle.submit(work, on_ok=case.ok, on_error=case.error)


@pytest.mark.parametrize("fails", [False, True])
def test_worker_delivers_only_through_main_thread_queue_poll(lifecycle_case, fails):
    c = lifecycle_case
    problem = ValueError("synthetic failure")

    def work(operation):
        assert c.tk.context == "worker"
        if fails:
            raise problem
        return "complete"

    assert submit(c, work)
    assert c.events == [("busy", True)]
    c.threads.run_next()
    assert c.lifecycle.busy
    assert c.events == [("busy", True)]
    assert c.lifecycle._results.put_contexts == ["worker"]
    c.widget.poll_once()
    assert not c.lifecycle.busy
    assert c.events == [("busy", True), ("busy", False),
                        ("error", problem) if fails else ("ok", "complete")]
    assert len(c.widget.afters) == 1


def test_duplicate_submit_does_not_create_another_operation_or_worker(lifecycle_case):
    c = lifecycle_case
    assert submit(c, lambda operation: "first")
    assert not submit(c, lambda operation: pytest.fail("duplicate work executed"))
    assert len(c.client.operations) == len(c.threads.jobs) == 1
    c.threads.run_next()
    c.widget.poll_once()
    assert ("ok", "first") in c.events


@pytest.mark.parametrize("action", ["cancel", "close", "destroy"])
def test_cancelled_queued_work_never_starts(lifecycle_case, action):
    c = lifecycle_case
    assert submit(c, lambda operation: pytest.fail("cancelled work executed"))
    operation = c.client.operations[-1]
    if action == "destroy":
        c.widget.emit_destroy()
    else:
        getattr(c.lifecycle, action)()
    assert operation.cancelled.is_set()
    assert not c.lifecycle.busy
    c.threads.run_next()
    assert c.lifecycle._results.empty()
    assert not any(kind in {"ok", "error"} for kind, _ in c.events)
    if action != "cancel":
        assert c.lifecycle.closed
        assert not c.widget.afters
        assert not submit(c, lambda operation: None)


def test_close_discards_completion_before_poll(lifecycle_case):
    c = lifecycle_case
    submit(c, lambda operation: "finished before close")
    c.threads.run_next()
    assert not c.lifecycle._results.empty()
    c.lifecycle.close()
    c.lifecycle.close()
    assert c.lifecycle._results.empty()
    assert c.events == [("busy", True)]
    assert len(c.widget.after_cancelled) == 1


@pytest.mark.parametrize("action", ["close", "destroy"])
def test_close_during_worker_makes_late_completion_inert(lifecycle_case, action):
    c = lifecycle_case

    def work(operation):
        close = c.lifecycle.close if action == "close" else c.widget.emit_destroy
        c.tk.interrupt_on_main(close)
        assert operation.cancelled.is_set()
        return "late result"

    submit(c, work)
    c.threads.run_next()
    assert c.lifecycle.closed
    assert not c.lifecycle.busy
    assert not c.widget.afters
    c.lifecycle._poll()  # Even an event already dispatched before close is inert.
    assert c.events == [("busy", True)]


def test_child_destroy_does_not_close_page(lifecycle_case):
    c = lifecycle_case
    c.widget.emit_destroy(c.tk.Frame(c.widget))
    assert not c.lifecycle.closed
    assert submit(c, lambda operation: "still open")
    c.threads.run_next()
    c.widget.poll_once()
    assert ("ok", "still open") in c.events


@pytest.mark.parametrize("fails", [False, True])
def test_stale_generation_suppresses_result_and_error(lifecycle_case, fails):
    c = lifecycle_case

    def work(operation):
        if fails:
            raise PermissionError("old account error")
        return "old account result"

    submit(c, work)
    c.threads.run_next()
    c.client.generation += 1
    c.widget.poll_once()
    assert c.events == [("busy", True), ("busy", False), ("change", None)]
    assert not c.lifecycle.busy


def test_stale_operation_error_refreshes_without_showing_error(lifecycle_case):
    c = lifecycle_case

    def work(operation):
        raise StaleAccountOperation("another request owns this response")

    submit(c, work)
    c.threads.run_next()
    c.widget.poll_once()
    assert c.events[-1] == ("change", None)
    assert not any(kind == "error" for kind, _ in c.events)


def test_old_completion_cannot_clear_new_request_busy_or_callbacks(lifecycle_case):
    c = lifecycle_case

    def replace():
        c.lifecycle.cancel()
        assert submit(c, lambda operation: "new result")

    def old_work(operation):
        c.tk.interrupt_on_main(replace)
        return "old result"

    submit(c, old_work)
    c.threads.run_next()
    events_before_poll = list(c.events)
    c.widget.poll_once()
    assert c.lifecycle.busy
    assert c.events == events_before_poll
    c.threads.run_next()
    c.widget.poll_once()
    assert not c.lifecycle.busy
    assert [event for event in c.events if event[0] == "ok"] == [("ok", "new result")]


def test_external_generation_change_refreshes_once_when_idle(lifecycle_case):
    c = lifecycle_case
    c.client.generation += 1
    c.widget.poll_once()
    c.widget.poll_once()
    assert c.events == [("change", None)]


def test_worker_start_failure_returns_false_and_recovers(lifecycle_case):
    c = lifecycle_case
    problem = RuntimeError("synthetic thread start failure")
    c.threads.fail_start = problem
    assert not submit(c, lambda operation: None)
    assert not c.lifecycle.busy
    assert c.events == [("busy", True), ("busy", False), ("error", problem)]
    c.threads.fail_start = None
    assert submit(c, lambda operation: "retry")
    c.threads.run_next()
    c.widget.poll_once()
    assert c.events[-1] == ("ok", "retry")


@pytest.mark.parametrize("action", ["close", "destroy"])
@pytest.mark.parametrize("fails", [False, True])
def test_close_in_completion_busy_callback_suppresses_delivery(lifecycle_case, action, fails):
    c = lifecycle_case
    original_on_busy = c.lifecycle.on_busy

    def on_busy(busy):
        original_on_busy(busy)
        if not busy:
            close = c.lifecycle.close if action == "close" else c.widget.emit_destroy
            close()

    def work(operation):
        if fails:
            raise ValueError("synthetic completion error")
        return "synthetic completion"

    c.lifecycle.on_busy = on_busy
    submit(c, work)
    c.threads.run_next()
    c.widget.poll_once()
    assert c.lifecycle.closed
    assert c.events == [("busy", True), ("busy", False)]
    assert not c.widget.afters


def test_close_in_completion_busy_callback_cancels_new_verification_challenge(lifecycle_case):
    c = lifecycle_case

    def on_busy(busy):
        if not busy:
            c.lifecycle.close()

    c.lifecycle.on_busy = on_busy
    submit(c, lambda operation: c.client.login("person@example.invalid", "synthetic-password", operation=operation))
    c.threads.run_next()
    assert c.client.pending is not None
    c.widget.poll_once()
    assert c.lifecycle.closed
    assert c.client.pending is None
    assert not any(kind in {"ok", "error"} for kind, _ in c.events)


def test_destroyed_widget_rejects_submit_and_poll_closes_lifecycle(lifecycle_case):
    c = lifecycle_case
    c.widget.destroyed = True
    assert not submit(c, lambda operation: pytest.fail("destroyed page ran work"))
    c.widget.poll_once()
    assert c.lifecycle.closed
    assert not c.threads.jobs
    assert c.events == []


COLORS = {name: name for name in ("window", "card", "line", "text", "muted", "blue",
                                "white", "control", "blue_dark", "control_hover", "red", "orange")}


@pytest.fixture
def make_page(monkeypatch):
    pages = []

    def build(*, scrolled=False, client=None):
        tk, client = FakeTk(), client or SyntheticAccount()
        threads = FakeThreads(tk)
        parent = tk.Frame()
        supplied_wrapper = tk.Frame(parent) if scrolled else None
        supplied_body = tk.Frame(supplied_wrapper) if scrolled else None

        def lifecycle_factory(*args, **kwargs):
            lifecycle = AccountPageLifecycle(*args, thread_factory=threads, **kwargs)
            lifecycle._results = FakeQueue(tk)
            return lifecycle

        monkeypatch.setattr(settings_account_ui, "AccountPageLifecycle", lifecycle_factory)
        kwargs = {"scroll_page": lambda: (supplied_wrapper, supplied_body)} if scrolled else {}
        wrapper = settings_account_ui.build_account_page(
            tk=tk, parent=parent, colors=COLORS, font="Synthetic font", client=client,
            translate=lambda chinese, english: english, **kwargs)
        entries = [widget for widget in tk.widgets if widget.kind == "Entry"]
        assert len(entries) == 3
        email, password, code = entries
        status = next(widget for widget in tk.widgets
                      if widget.kind == "Label" and "textvariable" in widget.options)
        buttons = [widget for widget in tk.widgets if widget.kind == "Button"]

        def button(text, index=0):
            return [widget for widget in buttons if widget.options["text"] == text][index]

        page = SimpleNamespace(tk=tk, client=client, threads=threads, wrapper=wrapper,
                               lifecycle=wrapper._lucas_account_lifecycle, email=email,
                               password=password, code=code, form=email.parent, verify_form=code.parent,
                               status=status, button=button, supplied_wrapper=supplied_wrapper,
                               supplied_body=supplied_body)
        pages.append(page)
        return page

    yield build
    for page in pages:
        page.lifecycle.close()
        assert page.tk.forbidden_calls == []


def value(entry):
    return entry.options["textvariable"]


def status_text(page):
    return value(page.status).get()


def start_login(page):
    value(page.email).set(" person@example.invalid ")
    value(page.password).set("synthetic-password")
    page.button("Sign in").invoke()


def finish_work(page):
    page.threads.run_next()
    page.wrapper.poll_once()


def await_verification(page):
    start_login(page)
    finish_work(page)
    assert status_text(page) == "Email verification required."
    assert page.verify_form.packed and not page.form.packed


def test_signed_out_controls_are_explicit_and_login_form_visible(make_page):
    page = make_page()
    assert status_text(page) == "Not signed in. Sign in to your Lucas account."
    assert page.form.packed and not page.verify_form.packed
    assert page.button("Sign in").options["state"] == "normal"
    for text in ("Sign out", "Verify and sign in", "Resend", "Cancel"):
        assert page.button(text).options["state"] == "disabled"
    assert page.code.options["state"] == "disabled"
    assert page.password.options["show"] == "*"
    assert page.client.calls == []


def test_login_snapshots_inputs_clears_password_and_blocks_duplicate(make_page):
    page = make_page()
    page.client.require_verification = False
    start_login(page)
    assert status_text(page) == "Working…"
    assert value(page.password).get() == ""
    assert page.button("Cancel").options["state"] == "normal"
    for control in (page.email, page.password, page.button("Sign in")):
        assert control.options["state"] == "disabled"
    page.button("Sign in").invoke()
    assert len(page.threads.jobs) == 1
    value(page.email).set("changed@example.invalid")
    finish_work(page)
    assert page.client.calls == [("login", "person@example.invalid", "synthetic-password")]
    assert status_text(page) == "Saved account session: Test Person"
    assert not page.form.packed and not page.verify_form.packed
    assert page.button("Sign out").options["state"] == "normal"


@pytest.mark.parametrize("email,password", [("", ""), (" ", "synthetic-password"), ("a@example.invalid", "")])
def test_empty_login_fields_do_not_start_worker(make_page, email, password):
    page = make_page()
    value(page.email).set(email)
    value(page.password).set(password)
    page.button("Sign in").invoke()
    assert status_text(page) == "Enter your email and password."
    assert page.status.options["fg"] == COLORS["red"]
    assert not page.threads.jobs


def test_worker_start_error_is_not_overwritten_by_working_status(make_page):
    page = make_page()
    page.threads.fail_start = RuntimeError("synthetic thread start failure")
    start_login(page)
    assert status_text(page) == "synthetic thread start failure"
    assert page.status.options["fg"] == COLORS["red"]
    assert not page.lifecycle.busy
    assert page.button("Sign in").options["state"] == "normal"


def test_login_error_returns_to_enabled_signed_out_form(make_page):
    page = make_page()
    page.client.login_error = PermissionError("Synthetic sign-in rejected")
    start_login(page)
    finish_work(page)
    assert status_text(page) == "Synthetic sign-in rejected"
    assert page.form.packed and not page.verify_form.packed
    assert page.button("Sign in").options["state"] == "normal"
    assert page.button("Sign out").options["state"] == "disabled"


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", "１２３４５６", "١٢٣٤٥٦"])
def test_verification_requires_six_ascii_digits_without_starting_work(make_page, code):
    page = make_page()
    await_verification(page)
    value(page.code).set(code)
    page.button("Verify and sign in").invoke()
    assert status_text(page) == "Enter the 6-digit verification code."
    assert not page.threads.jobs
    assert page.verify_form.packed
    assert page.button("Verify and sign in").options["state"] == "normal"


def test_verification_retry_resend_cancel_and_repeated_login_flow(make_page):
    page = make_page()
    await_verification(page)
    first_challenge = page.client.pending
    page.client.verify_error = PermissionError("Synthetic code rejected")
    value(page.code).set("123456")
    page.button("Verify and sign in").invoke()
    assert value(page.code).get() == ""
    assert page.button("Resend").options["state"] == "disabled"
    finish_work(page)
    assert status_text(page) == "Synthetic code rejected"
    assert page.client.pending == first_challenge
    for _ in range(2):
        page.button("Resend").invoke()
        finish_work(page)
        assert page.client.pending == first_challenge
        assert status_text(page) == "Email verification required."
    value(page.code).set("654321")
    page.button("Cancel", 1).invoke()
    assert page.client.pending is None
    assert value(page.code).get() == ""
    assert page.form.packed and not page.verify_form.packed
    assert page.button("Verify and sign in").options["state"] == "disabled"
    await_verification(page)
    second_challenge = page.client.pending
    assert second_challenge != first_challenge
    page.client.verify_error = None
    value(page.code).set(" 123456 ")
    page.button("Verify and sign in").invoke()
    finish_work(page)
    assert page.client.calls[-1] == ("verify", second_challenge, "123456")
    assert status_text(page) == "Saved account session: Test Person"
    assert not page.verify_form.packed
    assert page.client.pending is None
    page.button("Sign out").invoke()
    assert status_text(page) == "Not signed in. Sign in to your Lucas account."
    assert page.button("Sign out").options["state"] == "disabled"
    assert page.form.packed


@pytest.mark.parametrize("action", ["close", "destroy"])
def test_closing_waiting_verification_cancels_owned_challenge(make_page, action):
    page = make_page()
    await_verification(page)
    generation = page.client.generation
    if action == "close":
        page.lifecycle.close()
    else:
        page.wrapper.emit_destroy()
    assert page.client.pending is None
    assert page.client.generation == generation + 1
    assert generation in page.client.cancelled_generations
    assert not page.wrapper.afters


def test_closing_old_page_does_not_cancel_replacement_challenge(make_page):
    page = make_page()
    await_verification(page)
    owned_generation = page.client.generation
    page.client.generation += 1
    page.client.pending = "another-page-challenge"
    page.lifecycle.close()
    assert page.client.pending == "another-page-challenge"
    assert page.client.cancelled_generations[-1] == owned_generation


def test_cancelling_old_verification_page_preserves_replacement_challenge(make_page):
    page = make_page()
    await_verification(page)
    owned_generation = page.client.generation
    page.client.generation += 1
    page.client.pending = "another-page-challenge"
    page.button("Cancel", 1).invoke()
    assert page.client.pending == "another-page-challenge"
    assert page.client.cancelled_generations[-1] == owned_generation
    assert page.form.packed and not page.verify_form.packed


@pytest.fixture
def real_challenge_client(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/auth/desktop/login"
        return httpx.Response(200, json={
            "verification_required": True,
            "challenge_id": f"synthetic-challenge-{len(requests)}",
            "email": "person@example.invalid",
        })

    client = LocalAccountClient("https://accounts.example.invalid", tmp_path / "account.json",
                                transport=httpx.MockTransport(handler))
    return client, requests


@pytest.mark.parametrize("action", ["Verify and sign in", "Resend"])
@pytest.mark.parametrize("cleanup", ["close", "cancel", "destroy"])
def test_stale_challenge_submit_then_cleanup_preserves_replacement(
        make_page, real_challenge_client, action, cleanup):
    client, requests = real_challenge_client
    page = make_page(client=client)
    await_verification(page)
    value(page.code).set("123456")
    replacement = client.login("replacement@example.invalid", "synthetic-password")
    generation = client.generation
    # Do not poll: the rendered verification handler still belongs to gen 1.
    page.button(action).invoke()
    if cleanup == "close":
        page.lifecycle.close()
    elif cleanup == "destroy":
        page.wrapper.emit_destroy()
    else:
        page.button("Cancel", 1).invoke()
    assert client.generation == generation
    assert client._state.shared.pending["challenge_id"] == replacement["challenge_id"]
    assert not page.threads.jobs
    assert not page.lifecycle.busy
    assert len(requests) == 2
    assert not client.state_path.exists()


def test_stale_sign_in_handler_cannot_claim_replacement_challenge(make_page, real_challenge_client):
    client, requests = real_challenge_client
    page = make_page(client=client)
    replacement = client.login("replacement@example.invalid", "synthetic-password")
    generation = client.generation
    start_login(page)
    page.lifecycle.close()
    assert client.generation == generation
    assert client._state.shared.pending["challenge_id"] == replacement["challenge_id"]
    assert not page.threads.jobs
    assert len(requests) == 1


def test_submit_compares_captured_operation_generation_before_claiming_work(lifecycle_case):
    c = lifecycle_case
    captured_generation = c.client.generation
    new_operation = c.client.new_operation

    def replacement_before_capture():
        c.client.generation += 1
        c.client.pending = "replacement-challenge"
        return new_operation()

    c.client.new_operation = replacement_before_capture
    assert not c.lifecycle.submit(lambda operation: pytest.fail("stale work dispatched"),
                                  on_ok=c.ok, on_error=c.error,
                                  expected_generation=captured_generation)
    assert c.events == [("change", None)]
    assert not c.lifecycle.busy and not c.threads.jobs
    c.lifecycle.close()
    assert c.client.pending == "replacement-challenge"
    assert not c.client.cancelled_generations


def test_sign_out_from_stale_page_cannot_logout_replacement_account(make_page):
    client = SyntheticAccount()
    client.signed_in = True
    page = make_page(client=client)
    displayed_generation = client.generation
    assert status_text(page) == "Saved account session: Test Person"
    client.generation += 1
    client.name = "Replacement Person"
    page.button("Sign out").invoke()
    assert client.calls[-1] == ("logout", displayed_generation)
    assert client.signed_in
    assert status_text(page) == "Saved account session: Replacement Person"


def test_external_generation_change_clears_verification_form_and_code(make_page):
    page = make_page()
    await_verification(page)
    value(page.code).set("123456")
    page.client.generation += 1
    page.client.pending = None
    page.wrapper.poll_once()
    assert value(page.code).get() == ""
    assert page.form.packed and not page.verify_form.packed
    assert page.button("Verify and sign in").options["state"] == "disabled"
    assert page.button("Resend").options["state"] == "disabled"


def test_cancel_login_before_worker_start_allows_clean_retry(make_page):
    page = make_page()
    start_login(page)
    page.button("Cancel").invoke()
    page.threads.run_next()
    assert page.client.calls == []
    assert not page.lifecycle.busy
    assert page.button("Sign in").options["state"] == "normal"
    await_verification(page)
    assert page.client.login_count == 1


@pytest.mark.parametrize("flow", ["login", "verify"])
def test_close_during_account_worker_prevents_late_sign_in(make_page, flow):
    page = make_page()
    close_during_work = lambda: page.tk.interrupt_on_main(page.wrapper.emit_destroy)
    if flow == "login":
        page.client.require_verification = False
        page.client.during_login = close_during_work
        start_login(page)
    else:
        await_verification(page)
        page.client.during_verify = close_during_work
        value(page.code).set("123456")
        page.button("Verify and sign in").invoke()
    page.threads.run_next()
    assert page.lifecycle.closed
    assert not page.client.signed_in
    assert page.client.pending is None
    assert not page.wrapper.afters


@pytest.mark.parametrize("name,email,expected", [
    ("Test Person", "person@example.invalid", "Test Person"),
    ("", "person@example.invalid", "person@example.invalid"),
    ("", "", "synthetic-user"),
])
def test_signed_in_status_identity_fallback(make_page, name, email, expected):
    client = SyntheticAccount()
    client.signed_in, client.name, client.email = True, name, email
    page = make_page(client=client)
    assert status_text(page) == f"Saved account session: {expected}"
    assert not page.form.packed and not page.verify_form.packed


@pytest.mark.parametrize("scrolled", [False, True])
def test_page_supports_optional_shared_scroll_wrapper(make_page, scrolled):
    page = make_page(scrolled=scrolled)
    assert page.wrapper._lucas_account_lifecycle is page.lifecycle
    assert len(page.wrapper.afters) == 1
    if scrolled:
        assert page.wrapper is page.supplied_wrapper
        assert page.status.parent.parent.parent is page.supplied_body
    else:
        assert page.wrapper.children[0].packed
        assert page.wrapper.children[0].pack_options == {"fill": "both", "expand": True}
    await_verification(page)
