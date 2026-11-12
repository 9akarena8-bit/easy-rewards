"""Regression: support report v1.4.0 had start received but no engine logs."""
import threading
import time
from backend import Backend


class SlowWindowIO:
    def __init__(self):
        self.wait = threading.Event()
        self.lookup_started = threading.Event()

    def game_in_foreground(self):
        return False

    def game_window_found(self):
        self.lookup_started.set()
        self.wait.wait(4.0)
        return True

    def focus_game(self):
        return False

    def foreground_title(self):
        return "Launcher"

    def foreground_process(self):
        return "EasyRewards.exe"


def wait_for(condition, seconds=2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(.01)
    return condition()


def test_start_not_blocked_by_windows_game_discovery(tmp_path):
    io = SlowWindowIO()
    backend = Backend(tmp_path, io)
    try:
        began = time.monotonic()
        response = backend.start()
        assert time.monotonic() - began < .5
        assert response == {"ok": True, "reason": "start_queued"}
        assert wait_for(lambda: backend.engine.running)
        assert io.lookup_started.wait(1)
        assert backend.state()["controls"]["start_phase"] in ("waiting_for_fortnite", "engine_running")
        assert backend.state()["controls"]["start_pending"] is False
        assert backend._log, "Engine should log start before hanging game lookup"
    finally:
        backend.stop()
        io.wait.set()


def test_stop_cancels_queued_engine_start(tmp_path, monkeypatch):
    io = SlowWindowIO()
    io.wait.set()
    backend = Backend(tmp_path, io)
    entered = threading.Event()
    release = threading.Event()
    def slow_templates():
        entered.set()
        release.wait(2)
        return 0
    monkeypatch.setattr(backend.engine, "reload_templates", slow_templates)
    try:
        assert backend.start()["reason"] == "start_queued"
        assert entered.wait(1)
        backend.stop()
        release.set()
        assert wait_for(lambda: not backend.state()["controls"]["start_pending"])
        assert not backend.engine.running
    finally:
        release.set()
        backend.stop()


def test_start_diagnostic_is_in_support_report(tmp_path):
    backend = Backend(tmp_path, SlowWindowIO())
    from support_report import report_text
    state = backend.state()
    report = report_text("1.4.0", backend.engine, state["diagnostics"], state["controls"], state["log"])
    assert "Start pending:" in report
    assert "Start phase:" in report
    assert "Start error:" in report
