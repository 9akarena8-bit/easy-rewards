"""Regression for the v1.4.1 Start / Stop / Start generation race.

Only a fake injected IO is used. No keyboard events, Fortnite, or payments.
"""
import threading
import time

from backend import Backend


class FakeGameIO:
    def game_in_foreground(self):
        return False

    def game_window_found(self):
        return True

    def focus_game(self):
        return False

    def foreground_title(self):
        return "Desktop"

    def foreground_process(self):
        return "explorer.exe"


def wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.01)
    return bool(predicate())


def test_stop_then_start_during_blocked_template_loading_is_not_lost(tmp_path, monkeypatch):
    """An obsolete worker must not clear the new Start's pending flag."""
    backend = Backend(tmp_path, FakeGameIO())
    first_entered, second_entered = threading.Event(), threading.Event()
    first_release, second_release = threading.Event(), threading.Event()
    calls = []
    guard = threading.Lock()

    def slow_templates():
        with guard:
            calls.append(len(calls) + 1)
            call = calls[-1]
        if call == 1:
            first_entered.set()
            assert first_release.wait(5), "first worker was not released"
        if call == 2:
            second_entered.set()
            assert second_release.wait(5), "second worker was not released"
        return 0

    monkeypatch.setattr(backend.engine, "reload_templates", slow_templates)
    try:
        started = time.monotonic()
        assert backend.start() == {"ok": True, "reason": "start_queued"}
        assert time.monotonic() - started < .5
        assert first_entered.wait(2)

        backend.stop()
        assert backend.state()["controls"]["start_phase"] == "cancelled"
        assert backend.start() == {"ok": True, "reason": "start_queued"}
        assert backend.state()["controls"]["start_pending"] is True

        # Old worker is still blocked; new initialization cannot overlap it.
        assert not second_entered.wait(.1)
        first_release.set()
        assert second_entered.wait(2)
        # Old worker has finished, but the *new* request must remain pending.
        assert backend.state()["controls"]["start_pending"] is True
        assert not backend.engine.running

        second_release.set()
        assert wait_until(lambda: backend.engine.running)
        assert wait_until(lambda: backend.state()["controls"]["start_pending"] is False)
        assert calls == [1, 2]
        assert backend.state()["controls"]["start_phase"] in (
            "waiting_for_fortnite", "engine_running")
    finally:
        first_release.set()
        second_release.set()
        backend.stop()
        assert wait_until(lambda: not backend.engine.running)


def test_stop_before_pending_worker_begins_cannot_resurrect_engine(tmp_path, monkeypatch):
    backend = Backend(tmp_path, FakeGameIO())
    first_entered = threading.Event()
    release = threading.Event()

    def slow_templates():
        first_entered.set()
        assert release.wait(5)
        return 0

    monkeypatch.setattr(backend.engine, "reload_templates", slow_templates)
    try:
        backend.start()
        assert first_entered.wait(2)
        backend.stop()
        release.set()
        assert wait_until(lambda: not backend._start_pending)
        # The invalidated worker will not leave the engine running.
        assert wait_until(lambda: backend.engine.state == "stopped")
        assert not backend.engine.running
    finally:
        release.set()
        backend.stop()
