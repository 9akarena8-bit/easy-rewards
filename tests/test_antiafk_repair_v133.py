"""v1.3.3 regressions: visibility, probe diagnostics, shutdown lifecycle."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from backend import Backend
from core import Config, Engine, best_match
from i18n import STRINGS


class FakeInput:
    def __init__(self, *, game_active=True, found=True, process="FortniteClient-Win64-Shipping.exe"):
        self.game_active = game_active
        self.found = found
        self.process = process
        self.actions = []
        self.window_title = "Fortnite"

    def game_in_foreground(self):
        return self.game_active

    def game_window_found(self):
        return self.found

    def foreground_title(self):
        return "Fortnite" if self.game_active else "Notepad"

    def foreground_process(self):
        return self.process

    def hold_keys(self, keys, duration, abort):
        if not abort():
            self.actions.append(("hold", tuple(keys)))

    def hold_key(self, key, duration, abort):
        if not abort():
            self.actions.append(("hold", (key,)))

    def press_key(self, key):
        self.actions.append(("press", key))

    def focus_game(self):
        pass


def test_probe_rejects_non_active_fortnite_without_sending_anything(tmp_path):
    io = FakeInput(game_active=False)
    eng = Engine(Config(), io, tmp_path)
    result = eng.input_probe()
    assert result["status"] == "waiting_window"
    assert not io.actions


def test_probe_fortnite_sends_only_short_w(tmp_path):
    io = FakeInput(game_active=True)
    eng = Engine(Config(), io, tmp_path)
    result = eng.input_probe()
    assert result["status"] == "sent"
    assert io.actions == [("hold", ("w",))]
    assert "may" not in result["detail"]  # never pretend this proves game movement


def test_notepad_probe_only_when_notepad_in_foreground(tmp_path):
    io = FakeInput(game_active=False, process="notepad.exe")
    eng = Engine(Config(), io, tmp_path)
    assert eng.input_probe("notepad")["status"] == "sent"
    assert io.actions == [("press", "w")]
    io.process = "explorer.exe"
    assert eng.input_probe("notepad")["status"] == "waiting_window"
    assert io.actions == [("press", "w")]


def test_packaged_probe_requires_a_license_for_both_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    io = FakeInput(process="notepad.exe")
    engine = Engine(Config(), io, tmp_path)
    assert engine.input_probe()["status"] == "subscription_required"
    assert engine.input_probe("notepad")["status"] == "subscription_required"
    assert not io.actions


def test_packaged_probe_allows_active_license_and_blocks_after_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    io = FakeInput()
    active = True
    engine = Engine(Config(), io, tmp_path, probe_allowed=lambda: active)
    assert engine.input_probe()["status"] == "sent"
    active = False
    assert engine.input_probe()["status"] == "subscription_required"
    assert io.actions == [("hold", ("w",))]


def test_probe_rechecks_license_before_pressing_a_key(tmp_path):
    class ExpiringInput(FakeInput):
        def game_in_foreground(self):
            nonlocal active
            active = False
            return True

    active = True
    io = ExpiringInput()
    engine = Engine(Config(), io, tmp_path, probe_allowed=lambda: active)
    assert engine.input_probe()["status"] == "subscription_required"
    assert not io.actions


def test_probe_prevents_parallel_running_worker(tmp_path):
    io = FakeInput()
    eng = Engine(Config(), io, tmp_path)
    eng._thread = threading.Thread(target=lambda: time.sleep(0.6), daemon=True)
    eng._thread.start()
    assert eng.input_probe()["status"] == "busy"
    assert not io.actions
    eng.stop()


def test_waiting_status_distinguishes_absent_and_background_window(tmp_path):
    io = FakeInput(game_active=False, found=False)
    eng = Engine(Config(auto_focus=False), io, tmp_path)
    eng._tick()
    assert (eng.state, eng.wait_reason) == ("waiting_window", "not_found")
    io.found = True
    eng._tick()
    assert (eng.state, eng.wait_reason) == ("waiting_window", "not_foreground")


def test_stop_doesnt_block_ui_during_slow_capture(tmp_path):
    class SlowCapture(FakeInput):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()

        def grab(self):
            self.entered.set()
            self.release.wait(5)
            return np.zeros((80, 100, 3), dtype=np.uint8)

    io = SlowCapture()
    tpl = np.random.default_rng(12).integers(0, 255, (16, 20), dtype=np.uint8)
    folder = tmp_path / "ru"
    folder.mkdir()
    cv2.imencode(".png", tpl)[1].tofile(str(folder / "wait_test.png"))
    eng = Engine(Config(auto_focus=False, scan_interval=0.01), io, tmp_path)
    try:
        eng.start()
        assert io.entered.wait(timeout=2)
        start = time.monotonic()
        eng.stop()
        assert time.monotonic() - start < 0.9
        assert eng.state == "stopped"
        # Screen processing runs in a daemon analysis worker and cannot block Stop.
        assert not eng.running
    finally:
        io.release.set()
    eng._thread.join(timeout=2)
    assert not eng.running
    assert eng.state == "stopped"


def test_best_match_respects_abort_before_expensive_scales():
    frame = np.ones((80, 80), dtype=np.uint8)
    tpl = np.ones((10, 10), dtype=np.uint8)
    score, _ = best_match(frame, tpl, [0.5, 1.0, 1.1], lambda: True)
    assert score == -1


def test_backend_exposes_why_no_input_and_probe_status(tmp_path):
    io = FakeInput(game_active=False, found=False)
    backend = Backend(tmp_path, io)
    backend.engine._tick()
    state = backend.state()
    assert state["engine"]["wait_reason"] == "not_found"
    assert state["diagnostics"]["game_found"] is False
    assert state["diagnostics"]["foreground_process"] == io.process
    assert state["engine"]["probe_status"] == "idle"
    assert backend.input_probe_delayed("foobar") == {"ok": False, "reason": "invalid_target"}


def test_i18n_v133_is_complete():
    assert set(STRINGS['ru']) == set(STRINGS['en']) == set(STRINGS['uk'])
    for lang in ('ru', 'en', 'uk'):
        assert STRINGS[lang]['afk.probe_notepad']
        assert STRINGS[lang]['state.stopping']
