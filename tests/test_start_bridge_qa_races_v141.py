"""QA-only regression probes for the v1.4.1 nonblocking start bridge.

These tests are marked xfail because the referenced beta branch is not yet
correct. They document risks without changing the running engine or UI.
Remove the xfail markers once an implementation fix is reviewed.
"""
import threading
import time

import pytest

from backend import Backend


def until(predicate, seconds=1.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class PassiveIO:
    def game_in_foreground(self):
        return False

    def game_window_found(self):
        return False

    def foreground_title(self):
        return "Launcher"

    def foreground_process(self):
        return "EasyRewards.exe"


class PausedStartEngine:
    """Block engine initialization without any actual game input."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.start_calls = 0
        self.running = False
        self.paused = False

    def start(self):
        self.start_calls += 1
        self.entered.set()
        self.release.wait(2)
        self.running = True
        return True

    def stop(self):
        self.running = False


@pytest.mark.xfail(
    reason="v1.4.1: Stop invalidates generation but leaves start_pending set; immediate Start may be lost",
    strict=False,
)
def test_start_stop_start_during_slow_initialization_is_not_lost(tmp_path):
    backend = Backend(tmp_path, PassiveIO())
    engine = PausedStartEngine()
    backend.engine = engine
    try:
        assert backend.start()["reason"] == "start_queued"
        assert engine.entered.wait(1), "first launch never reached the engine"
        backend.stop()
        assert backend.start()["reason"] == "start_queued"

        engine.release.set()
        assert until(lambda: not backend._start_pending)
        # The user pressed Start a second time. At least one NEW worker should
        # start after Stop, instead of reporting queued and silently dropping it.
        assert engine.start_calls >= 2
        assert engine.running
    finally:
        engine.release.set()
        backend.stop()


class SlowDiscoveryIO(PassiveIO):
    def game_window_found(self):
        time.sleep(0.8)
        return False


@pytest.mark.xfail(
    reason="v1.4.1: state() performs blocking Windows discovery on the pywebview API thread",
    strict=False,
)
def test_state_poll_does_not_wait_for_slow_fortnite_discovery(tmp_path):
    backend = Backend(tmp_path, SlowDiscoveryIO())
    start = time.monotonic()
    backend.state()
    duration = time.monotonic() - start
    assert duration < 0.3, (
        f"state polling blocked UI for {duration:.2f}s; "
        "cache window status or refresh diagnostics in a background worker"
    )
