"""Regression: state() must not block pywebview on slow Win32 enumeration."""
import threading
import time

from backend import Backend


class GateIO:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.found = True

    def game_window_found(self):
        self.calls += 1
        self.entered.set()
        self.release.wait(5)
        return self.found

    def game_in_foreground(self):
        return False

    def foreground_title(self):
        return "Launcher"

    def foreground_process(self):
        return "explorer.exe"


def wait_for(check, seconds=1):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if check():
            return True
        time.sleep(.01)
    return bool(check())


def test_state_returns_promptly_with_blocked_window_lookup(tmp_path):
    io = GateIO()
    b = Backend(tmp_path, io)
    try:
        started = time.monotonic()
        status = b.state()
        assert time.monotonic() - started < .3
        assert status["diagnostics"]["game_lookup_pending"]
        assert io.entered.wait(1)
        for _ in range(5):
            started = time.monotonic()
            assert b.state()["diagnostics"]["game_lookup_pending"]
            assert time.monotonic() - started < .3
        assert io.calls == 1, "Repeated polling must not start more stuck lookup workers"
        io.release.set()
        assert wait_for(lambda: b.state()["diagnostics"]["game_found"])
        assert not b.state()["diagnostics"]["game_lookup_pending"]
    finally:
        io.release.set()


def test_window_lookup_error_does_not_crash_state(tmp_path):
    class FailingIO(GateIO):
        def game_window_found(self):
            raise OSError("fake Windows lookup failure")

    io = FailingIO()
    b = Backend(tmp_path, io)
    b.state()
    assert wait_for(lambda: b.state()["diagnostics"]["game_lookup_known"])
    result = b.state()["diagnostics"]
    assert result["game_found"] is False
    assert result["game_lookup_error"] == "OSError"
