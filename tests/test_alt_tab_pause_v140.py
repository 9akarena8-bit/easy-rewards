"""Regression tests for Alt+Tab focus-lost pause/resume lifecycle."""
from __future__ import annotations

import threading
import time

from backend import Backend
from core import Config, Engine


def wait_for(fn, seconds=2.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(.012)
    return bool(fn())


class FakeGameIO:
    def __init__(self, active=True):
        self.active = active
        self.focus_attempts = 0
        self.action_calls = []
        self.hold_started = threading.Event()
        self.hold_released = threading.Event()
        self.found = True

    def game_in_foreground(self):
        return self.active

    def game_window_found(self):
        return self.found

    def foreground_title(self):
        return "Fortnite" if self.active else "Other application"

    def foreground_process(self):
        return "FortniteClient-Win64-Shipping.exe" if self.active else "explorer.exe"

    def focus_game(self):
        self.focus_attempts += 1
        # Deliberately not stealing focus.
        return False

    def hold_key(self, key, seconds, should_abort):
        self.hold_started.set()
        start = time.monotonic()
        try:
            while time.monotonic() - start < seconds:
                if should_abort():
                    break
                self.action_calls.append(key)
                time.sleep(.02)
        finally:
            self.hold_released.set()


def short_config(**overrides):
    values = dict(
        auto_focus=True,
        afk_enabled=True,
        afk_sequence_enabled=False,
        afk_replay_auto_detect=False,
        afk_interval=120,
        scan_interval=.03,
    )
    values.update(overrides)
    return Config(**values)


def test_alt_tab_latches_pause_and_waits_for_manual_f10(tmp_path):
    io = FakeGameIO()
    engine = Engine(short_config(), io, tmp_path)
    try:
        engine.start()
        assert wait_for(lambda: engine._ever_foreground and engine.state == "afk_only")
        io.active = False
        assert wait_for(lambda: engine.paused)
        assert engine.pause_reason == "focus_lost"
        assert engine.state == "paused"
        assert engine.wait_reason == "focus_lost"
        assert io.focus_attempts == 0
        assert engine.toggle_pause() is False  # refused outside Fortnite
        io.active = True
        time.sleep(.15)
        assert engine.paused  # returning to game does NOT silently resume
        assert engine.toggle_pause() is True
        assert wait_for(lambda: not engine.paused)
        assert engine.pause_reason == ""
        assert engine.wait_reason == ""
        assert wait_for(lambda: engine.state == "afk_only")
    finally:
        engine.stop()
    assert not engine.running


def test_start_hotkey_can_resume_paused_engine_in_fortnite(tmp_path):
    io = FakeGameIO()
    backend = Backend(tmp_path, io)
    backend.cfg = backend.engine.cfg = short_config()
    try:
        assert backend.start()["ok"] is True
        assert wait_for(lambda: backend.engine._ever_foreground)
        io.active = False
        assert wait_for(lambda: backend.engine.paused)
        assert backend.start() == {"ok": False, "reason": "return_to_game"}
        assert backend.pause() == {"ok": False, "reason": "return_to_game"}
        io.active = True
        assert backend.start() == {"ok": True, "reason": "resumed"}
        assert wait_for(lambda: not backend.engine.paused)
    finally:
        backend.stop()


def test_alt_tab_during_input_aborts_and_releases_held_key(tmp_path):
    io = FakeGameIO()
    engine = Engine(short_config(afk_hold=2.0, afk_interval=1.0), io, tmp_path)
    try:
        engine.start()
        assert io.hold_started.wait(2.5)
        io.active = False
        assert io.hold_released.wait(.8)
        assert wait_for(lambda: engine.paused)
        seen = len(io.action_calls)
        time.sleep(.12)
        assert len(io.action_calls) == seen
        assert engine.pause_reason == "focus_lost"
    finally:
        engine.stop()


def test_disabling_latched_pause_never_sends_input_to_another_window(tmp_path):
    io = FakeGameIO()
    engine = Engine(short_config(afk_pause_on_alt_tab=False), io, tmp_path)
    try:
        engine.start()
        assert wait_for(lambda: engine.state == "afk_only")
        io.active = False
        assert wait_for(lambda: engine.state == "waiting_window")
        assert not engine.paused
        assert io.focus_attempts == 0
        io.active = True
        assert wait_for(lambda: engine.state == "afk_only")
    finally:
        engine.stop()


def test_manual_pause_keeps_manual_reason_and_f12_stop_works(tmp_path):
    io = FakeGameIO()
    b = Backend(tmp_path, io)
    b.cfg = b.engine.cfg = short_config()
    try:
        b.start()
        assert wait_for(lambda: b.engine.running)
        assert b.pause() == {"ok": True, "reason": "paused"}
        assert b.engine.pause_reason == "manual"
        io.active = False
        time.sleep(.12)
        assert b.engine.pause_reason == "manual"
        b.stop()
        assert wait_for(lambda: not b.engine.running)
        assert b.state()["engine"]["running"] is False
    finally:
        b.stop()


def test_start_after_stop_recreates_worker_without_stale_focus_pause(tmp_path):
    io = FakeGameIO()
    engine = Engine(short_config(), io, tmp_path)
    try:
        engine.start()
        assert wait_for(lambda: engine.state == "afk_only")
        io.active = False
        assert wait_for(lambda: engine.paused)
        engine.stop()
        assert wait_for(lambda: not engine.running)
        io.active = True
        engine.start()
        assert wait_for(lambda: engine.running and not engine.paused)
        assert engine.pause_reason == ""
        assert engine._ever_foreground is True
    finally:
        engine.stop()


def test_alt_tab_detected_while_idle_even_with_long_scan_interval(tmp_path):
    io = FakeGameIO()
    engine = Engine(short_config(scan_interval=4.0), io, tmp_path)
    try:
        engine.start()
        assert wait_for(lambda: engine._ever_foreground and engine.state == "afk_only")
        io.active = False
        assert wait_for(lambda: engine.paused, seconds=.8)
        assert engine.pause_reason == "focus_lost"
        assert io.focus_attempts == 0
    finally:
        engine.stop()
