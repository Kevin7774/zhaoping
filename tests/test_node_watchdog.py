import threading
import time

import pytest

import app.core.orchestrator as orchestrator
from app.core.orchestrator import TaskCancelled, _run_step_handler_guarded


class _StubStore:
    def __init__(self) -> None:
        self.cancelled = threading.Event()

    def is_cancelled(self, task_id: str) -> bool:
        return self.cancelled.is_set()


def test_guarded_handler_returns_result() -> None:
    store = _StubStore()

    result = _run_step_handler_guarded(
        lambda ctx: {"ok": ctx["value"]},
        {"value": 42},
        store=store,
        task_id="task_watchdog_ok",
        label="单元测试节点",
    )

    assert result == {"ok": 42}


def test_guarded_handler_raises_when_cancelled_mid_run() -> None:
    store = _StubStore()
    release = threading.Event()

    def blocking_handler(ctx):
        release.wait(timeout=30)
        return {"ok": True}

    def cancel_soon():
        time.sleep(0.3)
        store.cancelled.set()

    threading.Thread(target=cancel_soon, daemon=True).start()
    started = time.monotonic()
    try:
        with pytest.raises(TaskCancelled):
            _run_step_handler_guarded(
                blocking_handler,
                {},
                store=store,
                task_id="task_watchdog_cancel",
                label="阻塞节点",
            )
        assert time.monotonic() - started < 10
    finally:
        release.set()


def test_guarded_handler_times_out_hung_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "_NODE_HANDLER_TIMEOUT_SECONDS", 1.5)
    store = _StubStore()
    release = threading.Event()

    def hung_handler(ctx):
        release.wait(timeout=30)
        return {"ok": True}

    try:
        with pytest.raises(TimeoutError, match="阻塞节点"):
            _run_step_handler_guarded(
                hung_handler,
                {},
                store=store,
                task_id="task_watchdog_timeout",
                label="阻塞节点",
            )
    finally:
        release.set()


def test_guarded_handler_propagates_handler_exception() -> None:
    store = _StubStore()

    def failing_handler(ctx):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        _run_step_handler_guarded(
            failing_handler,
            {},
            store=store,
            task_id="task_watchdog_error",
            label="异常节点",
        )
