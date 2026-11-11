"""Tests for new movement-only mode, popup deduplication and focus safety."""
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import Config, Engine, Template
from backend import Backend


class MockIO:
    def __init__(self):
        self.keys = []
        self.clicks = []
        self.focused = True

    def grab(self):
        return np.zeros((120, 180, 3), dtype=np.uint8)

    def hold_key(self, key, seconds, abort):
        self.keys.append((key, seconds))

    def click(self, x=None, y=None):
        self.clicks.append((x, y))

    def game_in_foreground(self):
        return self.focused

    def focus_game(self):
        pass


def test_afk_starts_without_templates():
    with tempfile.TemporaryDirectory() as tmp:
        io = MockIO()
        cfg = Config(scan_interval=0.03, afk_enabled=True, auto_focus=False, scales=[1.0])
        eng = Engine(cfg, io, Path(tmp), log=lambda *a, **kw: None)
        eng.start()
        assert eng.running, 'Anti-AFK should not require button images'
        eng._next_afk = 0.0
        time.sleep(0.18)
        eng.stop()
        assert len(io.keys) >= 1
        assert all(k in 'wasd' for k, _ in io.keys)
        assert not eng.running


def test_reward_counts_each_popup_once():
    with tempfile.TemporaryDirectory() as tmp:
        stats = []
        io = MockIO()
        eng = Engine(Config(threshold=.8), io, Path(tmp), log=lambda *a, **kw: None,
                     on_reward=lambda: stats.append('reward'))
        template = Template('reward_token', 'reward', np.ones((25, 25), np.uint8))
        seen = (.95, (12, 12), template)
        assert eng._scan_reward(seen, 100.0)
        assert eng._scan_reward(seen, 100.3)
        assert not eng._scan_reward(None, 100.5)
        assert eng._scan_reward(seen, 101.0)
        assert eng.rewards == 1 and stats == ['reward']
        eng._scan_reward(None, 102.0)
        eng._scan_reward(None, 103.6)
        eng._scan_reward(seen, 111.0)
        assert eng.rewards == 2 and len(stats) == 2


def test_no_click_after_focus_changes_during_grab():
    with tempfile.TemporaryDirectory() as tmp:
        io = MockIO()
        rng = np.random.default_rng(15)
        tpl = rng.integers(0, 255, (25, 33), dtype=np.uint8)
        gray = np.zeros((120, 180), dtype=np.uint8)
        gray[35:60, 40:73] = tpl
        io.grab = lambda: (setattr(io, 'focused', False) or cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
        eng = Engine(Config(require_foreground=True, auto_focus=False, afk_enabled=False, scales=[1.0]),
                     io, Path(tmp), log=lambda *a, **kw: None)
        eng.templates = [Template('start_play', 'start', tpl)]
        eng._tick()
        assert io.clicks == []
        assert eng.state == 'waiting_window'


def test_saved_reward_total_survives_restart():
    with tempfile.TemporaryDirectory() as tmp:
        backend = Backend(tmp, MockIO())
        backend.engine.on_reward()
        backend.engine.on_reward()
        assert backend.state()['reward']['total'] == 2
        restarted = Backend(tmp, MockIO())
        assert restarted.state()['reward']['total'] == 2


def test_no_templates_with_afk_disabled_reports_not_started():
    with tempfile.TemporaryDirectory() as tmp:
        eng = Engine(Config(afk_enabled=False), MockIO(), Path(tmp), log=lambda *a, **kw: None)
        eng.start()
        assert not eng.running
