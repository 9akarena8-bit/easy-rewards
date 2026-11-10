"""Headless tests: fake screen + fake IO, no Windows needed.  Run: python -m pytest  (or python tests/test_core.py)"""
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import Config, Engine, best_match  # noqa: E402


def make_button(w=160, h=48, seed=1):
    rng = np.random.default_rng(seed)
    img = rng.integers(60, 200, (h, w, 3), dtype=np.uint8)
    cv2.putText(img, "PLAY", (20, 33), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return img


def make_screen(button=None, pos=(700, 500), size=(1080, 1920)):
    rng = np.random.default_rng(99)
    scr = rng.integers(0, 40, (*size, 3), dtype=np.uint8)
    if button is not None:
        h, w = button.shape[:2]
        scr[pos[1]:pos[1] + h, pos[0]:pos[0] + w] = button
    return scr


class FakeIO:
    def __init__(self, screens):
        self.screens, self.i = screens, 0
        self.clicks, self.keys = [], []

    def grab(self):
        s = self.screens[min(self.i, len(self.screens) - 1)]
        return s

    def click(self, x, y):
        self.clicks.append((x, y))
        self.i += 1  # after a click the screen changes

    def hold_key(self, key, seconds, abort):
        self.keys.append((key, seconds))

    def game_in_foreground(self):
        return True

    def focus_game(self):
        pass


def _setup(tmp, role="start"):
    btn = make_button()
    d = Path(tmp) / "ru"
    d.mkdir()
    cv2.imencode(".png", btn)[1].tofile(str(d / f"{role}_play.png"))
    return btn


def test_best_match_finds_position():
    btn = make_button()
    scr = make_screen(btn, (700, 500))
    score, (cx, cy) = best_match(cv2.cvtColor(scr, cv2.COLOR_BGR2GRAY),
                                 cv2.cvtColor(btn, cv2.COLOR_BGR2GRAY), [1.0])
    assert score > 0.99
    assert abs(cx - (700 + 80)) <= 1 and abs(cy - (500 + 24)) <= 1


def test_no_false_positive_on_empty_screen():
    btn = make_button()
    score, _ = best_match(cv2.cvtColor(make_screen(), cv2.COLOR_BGR2GRAY),
                          cv2.cvtColor(btn, cv2.COLOR_BGR2GRAY), [1.0])
    assert score < 0.5


def test_engine_clicks_counts_and_antiafk():
    with tempfile.TemporaryDirectory() as tmp:
        btn = _setup(tmp)
        io = FakeIO([make_screen(btn), make_screen()])  # button, then in-match
        cfg = Config(scan_interval=0.05, click_delay=0.1, afk_interval=1.0, afk_hold=1.0,
                     scales=[1.0], auto_focus=False)
        logs = []
        eng = Engine(cfg, io, Path(tmp), log=lambda *a, **k: logs.append(a))
        eng.start()
        time.sleep(0.6)
        assert len(io.clicks) == 1 and eng.games == 1
        assert abs(io.clicks[0][0] - 780) <= 3 and abs(io.clicks[0][1] - 524) <= 3
        assert eng.state == "in_match"
        time.sleep(1.8)  # anti-AFK interval is randomised 0.7-1.3s -> >=1 press
        eng.stop()
        assert io.keys and all(k in "wasd" for k, _ in io.keys)
        assert eng.runtime > 1.0


def test_result_button_counts_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        start, result = make_button(seed=1), make_button(seed=7)
        d = Path(tmp) / "ru"
        d.mkdir()
        cv2.imencode(".png", start)[1].tofile(str(d / "start_play.png"))
        cv2.imencode(".png", result)[1].tofile(str(d / "result_continue.png"))
        io = FakeIO([make_screen(start), make_screen(), make_screen(result)])
        cfg = Config(scan_interval=0.05, click_delay=0.1, scales=[1.0], auto_focus=False, afk_enabled=False)
        eng = Engine(cfg, io, Path(tmp), log=lambda *a, **k: None)
        eng.start()
        time.sleep(0.2)
        io.i = 2  # jump to result screen
        time.sleep(0.5)
        eng.stop()
        assert eng.games == 1 and eng.cycles == 1


def test_pause_stops_clicking():
    with tempfile.TemporaryDirectory() as tmp:
        btn = _setup(tmp)

        class Sticky(FakeIO):
            def click(self, x, y):
                self.clicks.append((x, y))  # screen does not change

        io = Sticky([make_screen(btn)])
        cfg = Config(scan_interval=0.05, click_delay=0.1, scales=[1.0], auto_focus=False, afk_enabled=False)
        eng = Engine(cfg, io, Path(tmp), log=lambda *a, **k: None)
        eng.start()
        time.sleep(0.5)
        eng.toggle_pause()
        time.sleep(0.3)  # let a scan that was already in flight finish
        n = len(io.clicks)
        time.sleep(0.5)
        assert len(io.clicks) == n
        eng.stop()


def test_translations_complete():
    from i18n import STRINGS, tr
    en = set(STRINGS["en"])
    for lang in ("ru", "uk"):
        assert set(STRINGS[lang]) == en, (lang, en ^ set(STRINGS[lang]))
    assert tr("uk", "log.clicked", name="x", score="0.9", x=1, y=2).startswith("Клік")
    assert tr("xx", "btn.start") == "Start"      # unknown language falls back to English



if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
