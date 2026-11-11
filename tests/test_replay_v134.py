"""v1.3.4: yellow Replay detection, click discipline and focus recovery."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from core import Config, Engine
from replay_detect import yellow_replay_button
from backend import Backend


def frame(with_replay: bool = True, top: int = 5, other_buttons: bool = True):
    image = np.full((1080, 1920, 3), (103, 45, 25), np.uint8)
    if other_buttons:
        # Test against yellow buttons that must never be clicked.
        cv2.rectangle(image, (1340, 246), (1820, 304), (10, 255, 250), -1)   # spirit
        cv2.rectangle(image, (145, 846), (575, 890), (10, 255, 250), -1)    # pass
        cv2.rectangle(image, (1340, 370), (1820, 430), (240, 204, 202), -1)  # team
        cv2.rectangle(image, (1340, 453), (1820, 510), (240, 204, 202), -1)  # lobby
    cv2.putText(image, f'TOP #{top}', (820, 55), cv2.FONT_HERSHEY_SIMPLEX,
                1.4, (240, 240, 240), 4)
    if with_replay:
        cv2.rectangle(image, (1340, 521), (1819, 608), (25, 255, 250), -1)
        cv2.putText(image, 'PLAY AGAIN', (1430, 576), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (18, 17, 33), 4, cv2.LINE_AA)
    return image


class ReplayIO:
    def __init__(self, image):
        self.image = image
        self.clicks = []
        self.movements = []
        self.active = True
        self.found = True
        self.focus_calls = 0
        self.window_title = 'Fortnite'

    def grab(self):
        return self.image.copy()

    def game_in_foreground(self):
        return self.active

    def game_window_found(self):
        return self.found

    def focus_game(self):
        self.focus_calls += 1
        return self.active

    def hold_key(self, key, seconds, abort):
        if not abort():
            self.movements.append(key)

    def click(self, x, y):
        self.clicks.append((x, y))


def engine(io, tmp_path):
    return Engine(Config(auto_focus=False, afk_enabled=True, afk_sequence_enabled=False,
                         afk_replay_auto_detect=True, scales=[1.0]), io, tmp_path,
                  log=lambda *a, **kw: None)


def test_detector_ignores_top_number_and_uses_only_right_yellow_button():
    for top in (1, 5, 21, 99):
        found = yellow_replay_button(frame(top=top))
        assert found is not None
        confidence, (x, y) = found
        assert confidence > .75
        assert 1340 <= x <= 1820 and 521 <= y <= 608
    assert yellow_replay_button(frame(with_replay=False)) is None


def test_replay_detector_rejects_yellow_button_without_results_screen_context():
    image = frame(other_buttons=False)
    assert yellow_replay_button(image) is None


def test_detector_rejects_uniform_yellow_block_without_dark_letters():
    image = frame(with_replay=False, other_buttons=False)
    cv2.rectangle(image, (1340, 521), (1819, 608), (25, 255, 250), -1)
    assert yellow_replay_button(image) is None


def test_replay_requires_three_frames_then_stops_movement_until_loading_finishes(tmp_path):
    io = ReplayIO(frame(top=5))
    eng = engine(io, tmp_path)
    eng._next_afk = 0.0
    eng._tick()
    assert eng.state == 'await_replay' and not io.clicks and not io.movements
    eng._tick()
    assert not io.clicks
    io.image = frame(top=73)  # placement number changed; detection remains stable
    eng._tick()
    assert len(io.clicks) == 1 and eng.replay_count == 1
    assert eng.replay_source == 'yellow'
    assert eng._replay_pending and eng.state == 'loading'
    assert eng.games == 1 and not eng._in_match
    assert not io.movements
    io.image = frame(with_replay=False)
    eng._tick()
    assert eng._replay_pending and not io.movements
    eng._replay_clicked_at -= 8.0
    eng._tick()
    assert not eng._replay_pending and eng._in_match
    assert eng.replay_status == 'resumed'
    eng._next_afk = time.monotonic() - 1
    eng._tick()
    assert io.movements


def test_replay_retry_cap_prevents_unbounded_clicks(tmp_path):
    io = ReplayIO(frame())
    eng = engine(io, tmp_path)
    for _ in range(3):
        eng._tick()
    assert len(io.clicks) == 1
    for _ in range(5):
        eng._replay_last_attempt -= 7.0
        eng._tick()
    assert len(io.clicks) == 3
    assert eng.state == 'await_replay'
    assert eng.replay_status == 'unresponsive'
    assert eng.wait_reason == 'replay_unresponsive'
    assert not io.movements


def test_replay_never_clicks_when_fortnite_is_not_foreground(tmp_path):
    io = ReplayIO(frame())
    io.active = False
    eng = engine(io, tmp_path)
    for _ in range(5):
        eng._tick()
    assert io.clicks == [] and eng.state == 'waiting_window'
    assert eng.wait_reason == 'not_foreground'


def test_false_positive_single_frame_does_not_freeze_movement(tmp_path):
    io = ReplayIO(frame())
    eng = engine(io, tmp_path)
    eng._tick()
    assert eng.state == 'await_replay'
    io.image = frame(with_replay=False)
    for _ in range(4):
        eng._tick()
    assert not eng._awaiting_replay and not io.clicks
    assert eng.replay_status == 'idle'


def test_focus_attempt_is_throttled(tmp_path):
    io = ReplayIO(frame())
    io.active = False
    eng = Engine(Config(auto_focus=True), io, tmp_path, log=lambda *a, **kw: None)
    for _ in range(5):
        eng._tick()
    assert io.focus_calls == 1
    assert eng.focus_result == 'denied'


def test_replay_switch_persists_through_backend_config(tmp_path):
    io = ReplayIO(frame())
    backend = Backend(tmp_path, io)
    assert backend.set_config({'afk_replay_auto_detect': False})['ok']
    assert Backend(tmp_path, io).cfg.afk_replay_auto_detect is False
    s = backend.state()
    assert s['engine']['replay_status'] == 'idle'
    assert s['engine']['replay_count'] == 0


def test_quick_f7_after_f8_is_queued_until_previous_worker_exits(tmp_path):
    import threading

    class SlowIO(ReplayIO):
        def __init__(self):
            super().__init__(frame(with_replay=False))
            self.entered = threading.Event()
            self.release = threading.Event()

        def grab(self):
            self.entered.set()
            self.release.wait(timeout=5)
            return self.image.copy()

    io = SlowIO()
    eng = Engine(Config(afk_enabled=True, auto_focus=False, scan_interval=.02), io,
                 tmp_path, log=lambda *a, **kw: None)
    try:
        eng.start()
        assert io.entered.wait(2)
        first_thread = eng._thread
        eng.stop()
        assert eng.state == 'stopped'
        assert not eng.running
        eng.start()  # F7 immediately after F8 starts a fresh control loop.
        assert eng._thread is not first_thread
        assert eng.running
        io.release.set()
    finally:
        eng.stop()
        if eng._thread is not None:
            eng._thread.join(timeout=2)


def test_no_templates_with_autodetect_still_runs_movement_and_reports_afk_only(tmp_path):
    io = ReplayIO(frame(with_replay=False))
    eng = engine(io, tmp_path)
    eng._next_afk = 0.0
    eng._tick()
    assert eng.state == 'afk_only'
    assert eng.input_count == 1
    assert io.movements
