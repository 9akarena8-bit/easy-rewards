"""Isolation tests: start/stop/start races must not lose a user restart.

These are synthetic Python/Windows-API-adapter tests, NOT evidence that a
protected game accepts keyboard/mouse input. No Fortnite account is involved.
"""
import threading
import time

from backend import Backend


class SafeFakeIO:
    def game_in_foreground(self):
        return False

    def game_window_found(self):
        return False

    def foreground_title(self):
        return "Desktop"

    def foreground_process(self):
        return "explorer.exe"


def eventually(condition, timeout=3.):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if condition():
            return True
        time.sleep(.01)
    return condition()


def hold_first_initialization(backend, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    seen = []
    first_lock = threading.Lock()
    actual = backend.engine.reload_templates

    def controlled_reload():
        with first_lock:
            seen.append(1)
            count = len(seen)
        if count == 1:
            entered.set()
            release.wait(3.)
        return actual()

    monkeypatch.setattr(backend.engine, "reload_templates", controlled_reload)
    return entered, release, seen


def test_stop_then_start_during_initialization_still_starts_latest_request(tmp_path, monkeypatch):
    backend = Backend(tmp_path, SafeFakeIO())
    entered, release, seen = hold_first_initialization(backend, monkeypatch)
    try:
        assert backend.start()["reason"] == "start_queued"
        assert entered.wait(1.5), "First startup was never entered"
        backend.stop()
        assert backend.start()["reason"] == "start_queued"
        release.set()
        assert eventually(lambda: backend.engine.running and
                          not backend.state()["controls"]["start_pending"]), (
            "Rapid Start → Stop → Start lost its final Start request")
        assert len(seen) >= 2
    finally:
        release.set()
        backend.stop()


def test_second_stop_cancels_a_pending_relaunch(tmp_path, monkeypatch):
    backend = Backend(tmp_path, SafeFakeIO())
    entered, release, seen = hold_first_initialization(backend, monkeypatch)
    try:
        backend.start()
        assert entered.wait(1.5)
        backend.stop()
        backend.start()
        backend.stop()
        release.set()
        assert eventually(lambda: not backend.state()["controls"]["start_pending"])
        time.sleep(.1)
        assert backend.engine.running is False
        assert len(seen) == 1, "Final Stop must cancel deferred restarts"
    finally:
        release.set()
        backend.stop()


def test_repeated_start_during_initialization_is_idempotent(tmp_path, monkeypatch):
    backend = Backend(tmp_path, SafeFakeIO())
    entered, release, seen = hold_first_initialization(backend, monkeypatch)
    try:
        backend.start()
        assert entered.wait(1.5)
        for _ in range(7):
            assert backend.start()["reason"] == "start_queued"
        release.set()
        assert eventually(lambda: backend.engine.running and
                          not backend.state()["controls"]["start_pending"])
        assert len(seen) == 1, "Repeated Start must not spawn duplicate workers"
    finally:
        release.set()
        backend.stop()
