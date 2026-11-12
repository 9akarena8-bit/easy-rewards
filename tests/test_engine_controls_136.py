"""Regression: Stop/Pause must not depend on ImageGrab/OpenCV finishing."""
import threading
import time

import numpy as np

from backend import Backend
from core import Config, Engine


class BlockingIO:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.presses = []

    def game_in_foreground(self):
        return True

    def game_window_found(self):
        return True

    def foreground_title(self):
        return "Fortnite"

    def foreground_process(self):
        return "FortniteClient-Win64-Shipping.exe"

    def grab(self):
        self.entered.set()
        self.release.wait(5)
        return np.zeros((150, 250, 3), dtype=np.uint8)

    def hold_key(self, key, seconds, abort):
        if not abort():
            self.presses.append(key)

    def focus_game(self):
        return True


def wait_until(pred, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(.015)
    return bool(pred())


def test_stop_completes_when_capture_hangs(tmp_path):
    io = BlockingIO()
    engine = Engine(Config(afk_enabled=True, afk_replay_auto_detect=True, scan_interval=.1),
                    io, tmp_path, log=lambda *args, **kwargs: None)
    try:
        engine.start()
        assert io.entered.wait(2)
        start = time.monotonic()
        engine.stop()
        assert time.monotonic() - start < .9
        assert wait_until(lambda: not engine.running, 1.5)
        assert engine.state == "stopped"
        assert engine._stop.is_set()
    finally:
        io.release.set()


def test_pause_and_stop_work_during_blocked_capture(tmp_path):
    io = BlockingIO()
    engine = Engine(Config(afk_enabled=True, afk_replay_auto_detect=True, scan_interval=.1),
                    io, tmp_path, log=lambda *args, **kwargs: None)
    try:
        engine.start()
        assert io.entered.wait(2)
        start = time.monotonic()
        engine.toggle_pause()
        assert time.monotonic() - start < .25
        assert engine.paused
        assert engine.state == "paused"
        engine.stop()
        assert wait_until(lambda: not engine.running, 1.5)
        assert engine.state == "stopped"
        assert not engine.paused and not engine.pause_reason
    finally:
        io.release.set()


def test_backend_recovers_from_stopping_and_can_restart(tmp_path):
    io = BlockingIO()
    backend = Backend(tmp_path, io)
    backend.cfg.afk_enabled = True
    backend.cfg.afk_replay_auto_detect = True
    try:
        backend.start()
        assert io.entered.wait(2)
        backend.stop()
        assert wait_until(lambda: not backend.engine.running, 1.5)
        assert backend.state()["engine"]["running"] is False
        assert backend.state()["engine"]["state"] == "stopped"
        io.release.set()
        time.sleep(.03)
        backend.start()
        assert wait_until(lambda: backend.engine.running, 1)
        backend.stop()
        assert wait_until(lambda: not backend.engine.running, 1.5)
    finally:
        io.release.set()


def test_focus_game_reports_real_windows_result(tmp_path):
    io = BlockingIO()
    backend = Backend(tmp_path, io)
    assert backend.focus_game_now() == {"ok": True, "reason": "focused"}
    io.game_in_foreground = lambda: False
    io.focus_game = lambda: False
    assert backend.focus_game_now() == {"ok": False, "reason": "denied"}

def test_backend_state_never_reports_stopping_when_worker_is_gone(tmp_path):
    io = BlockingIO()
    backend = Backend(tmp_path, io)
    backend.engine.state = "stopping"
    assert backend.engine.running is False
    state = backend.state()["engine"]
    assert state["running"] is False
    assert state["state"] == "stopped"
