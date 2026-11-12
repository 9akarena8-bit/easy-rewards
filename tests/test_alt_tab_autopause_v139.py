"""Alt+Tab auto-suspension: no focus stealing, no inputs to other apps."""
from __future__ import annotations

import time

from backend import Backend
from core import Config, Engine


class FocusIO:
    def __init__(self):
        self.active = False
        self.found = True
        self.focus_attempts = 0
        self.actions = []

    def game_in_foreground(self):
        return self.active

    def game_window_found(self):
        return self.found

    def focus_game(self):
        self.focus_attempts += 1
        return self.active

    def foreground_title(self):
        return "Fortnite" if self.active else "Desktop"

    def foreground_process(self):
        return "FortniteClient-Win64-Shipping.exe" if self.active else "explorer.exe"

    def hold_key(self, key, duration, abort):
        if not abort():
            self.actions.append(key)


def make_engine(io, tmp_path, events):
    cfg = Config(auto_focus=True, afk_sequence_enabled=False,
                 afk_replay_auto_detect=False)
    return Engine(cfg, io, tmp_path, log=lambda key, **_: events.append(key))


def test_alt_tab_never_steals_focus_or_sends_keys(tmp_path):
    io, logs = FocusIO(), []
    e = make_engine(io, tmp_path, logs)
    e._tick()
    assert e.state == "waiting_window"
    assert e.wait_reason == "not_foreground"
    assert e._focus_suspended is True
    assert io.focus_attempts == 0
    assert io.actions == []
    first_epoch = e._screen_epoch
    # Repeated ticks must not spam notifications or change the epoch.
    for _ in range(8):
        e._tick()
    assert e._screen_epoch == first_epoch
    assert logs.count("log.focus_suspended") == 1
    assert io.focus_attempts == 0


def test_return_to_game_auto_resumes_after_grace_period(tmp_path):
    io, logs = FocusIO(), []
    e = make_engine(io, tmp_path, logs)
    e._tick()
    old_epoch = e._screen_epoch
    io.active = True
    e._tick()
    assert e._focus_suspended is False
    assert e._screen_epoch == old_epoch + 1
    assert logs.count("log.focus_resumed") == 1
    assert e._next_afk > time.monotonic()
    assert io.actions == []
    # After cooldown, running controls are allowed again with foreground.
    e._next_afk = 0.0
    e._tick()
    assert io.actions
    assert io.focus_attempts == 0


def test_absent_game_waits_without_launcher_focus_loop(tmp_path):
    io, logs = FocusIO(), []
    io.found = False
    e = make_engine(io, tmp_path, logs)
    for _ in range(5):
        e._tick()
    assert e.wait_reason == "not_found"
    assert e.state == "waiting_window"
    assert io.focus_attempts == 0
    assert not io.actions


def test_backend_exposes_focus_suspended_during_running_worker(tmp_path):
    io = FocusIO()
    b = Backend(tmp_path, io)
    # Avoid the game-launch hook; this is a pure FakeIO test.
    b.cfg.auto_launch_game = False
    b.start()
    try:
        deadline = time.monotonic() + 2
        while not b.engine._focus_suspended and time.monotonic() < deadline:
            time.sleep(.02)
        st = b.state()
        assert st["engine"]["running"]
        assert st["engine"]["focus_suspended"] is True
        b.pause()
        assert b.state()["engine"]["paused"] is True
        # Manual pause is distinct from auto-suspension.
        assert b.state()["engine"]["focus_suspended"] is False
        io.active = True
        b.pause()  # Resume is safe even after Alt+Tab.
        deadline = time.monotonic() + 2
        while b.engine._focus_suspended and time.monotonic() < deadline:
            time.sleep(.02)
        assert b.state()["engine"]["focus_suspended"] is False
    finally:
        b.stop()
        b.shutdown()
