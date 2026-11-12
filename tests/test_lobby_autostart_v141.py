"""Offline regressions for lobby-button templates and match verification.

No Fortnite connection, injection, payments or anti-cheat bypass involved.
"""
import time

import cv2
import numpy as np

from backend import Backend
from core import Config, Engine, Template, load_templates, template_role


class LobbyIO:
    def __init__(self):
        self.active = True
        self.image = np.zeros((500, 820, 3), dtype=np.uint8)
        self.clicks = []
        self.movements = []

    def game_in_foreground(self):
        return self.active

    def game_window_found(self):
        return True

    def grab(self):
        return self.image.copy()

    def click(self, x, y):
        self.clicks.append((x, y))

    def hold_key(self, key, seconds, should_abort):
        if not should_abort():
            self.movements.append(key)


def make_engine(tmp_path):
    io = LobbyIO()
    rng = np.random.default_rng(20261112)
    play = rng.integers(0, 255, (46, 105), dtype=np.uint8)
    ready = rng.integers(0, 255, (43, 115), dtype=np.uint8)
    hud = rng.integers(0, 255, (36, 82), dtype=np.uint8)
    cfg = Config(auto_focus=False, afk_enabled=True, lobby_autostart_enabled=True,
                 afk_replay_auto_detect=False, afk_sequence_enabled=False,
                 afk_interval=1, scales=[1.0], threshold=.88)
    eng = Engine(cfg, io, tmp_path, log=lambda *a, **kw: None)
    templates = {
        "lobby_play": Template("lobby_play_button", "lobby_play", play),
        "lobby_ready": Template("lobby_ready_button", "lobby_ready", ready),
        "match_hud": Template("match_hud_health", "match_hud", hud),
    }
    eng.templates = list(templates.values())

    def frame(*roles):
        result = np.full((500, 820), 17, dtype=np.uint8)
        for role in roles:
            if role == "match_hud":
                x, y = 40, 38
            elif role == "lobby_ready":
                x, y = 610, 390
            else:
                x, y = 615, 305
            tile = templates[role].gray
            result[y:y+tile.shape[0], x:x+tile.shape[1]] = tile
        io.image = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    return eng, io, frame


def test_template_roles_parse_multiword_names_and_load(tmp_path):
    assert template_role("lobby_play_button") == "lobby_play"
    assert template_role("lobby_ready_button") == "lobby_ready"
    assert template_role("match_hud_health") == "match_hud"
    assert template_role("start_button") == "start"
    assert template_role("unrelated_x") == ""
    directory = tmp_path / "ru"
    directory.mkdir()
    rng = np.random.default_rng(24)
    image = rng.integers(0, 255, (40, 120), dtype=np.uint8)
    cv2.imwrite(str(directory / "lobby_play_button.png"), image)
    loaded = load_templates(tmp_path, "ru")
    assert len(loaded) == 1 and loaded[0].role == "lobby_play"


def test_lobby_requires_two_stable_frames_and_never_afks_in_menu(tmp_path):
    eng, io, frame = make_engine(tmp_path)
    frame("lobby_play")
    eng._next_afk = 0
    eng._tick()
    assert eng.state == "lobby_button"
    assert not io.clicks and not io.movements
    eng._tick()
    assert len(io.clicks) == 1
    assert eng.lobby_clicks == 1
    assert not io.movements
    eng._tick()
    assert len(io.clicks) == 1


def test_lobby_step_priority_and_hud_confirmation(tmp_path):
    eng, io, frame = make_engine(tmp_path)
    frame("lobby_play", "lobby_ready")
    eng._tick()
    eng._tick()
    assert eng.lobby_last_button == "lobby_ready"
    assert len(io.clicks) == 1
    frame()
    eng._next_afk = 0
    eng._tick()
    assert not io.movements
    frame("match_hud")
    eng._tick()
    assert not eng._in_match and not io.movements
    eng._tick()
    assert eng._in_match and eng.lobby_state == "in_match"
    assert eng.games == 1
    eng._next_afk = time.monotonic() - 1
    eng._tick()
    assert io.movements, "AFK is allowed only after the HUD is verified"
    assert eng.games == 1


def test_hud_flicker_does_not_duplicate_match_count(tmp_path):
    eng, io, frame = make_engine(tmp_path)
    frame("match_hud")
    eng._tick()
    eng._tick()
    assert eng.games == 1
    frame()
    eng._tick()
    assert eng.games == 1
    frame("match_hud")
    eng._tick()
    eng._tick()
    assert eng.games == 1


def test_missing_hud_template_suspends_actions_after_lobby(tmp_path):
    eng, io, frame = make_engine(tmp_path)
    eng.templates = [t for t in eng.templates if t.role != "match_hud"]
    frame("lobby_play")
    eng._tick()
    eng._tick()
    frame()
    eng._next_afk = 0
    for _ in range(4):
        eng._tick()
    assert eng.lobby_state == "waiting_for_hud"
    assert not io.movements


def test_lobby_retry_is_bounded_and_needs_foreground(tmp_path):
    eng, io, frame = make_engine(tmp_path)
    frame("lobby_play")
    eng._tick()
    eng._tick()
    assert len(io.clicks) == 1
    eng._lobby_last_click_at -= 9
    eng._last_click -= 9
    eng._tick()
    assert len(io.clicks) == 2
    eng._lobby_last_click_at -= 9
    eng._last_click -= 9
    eng._tick()
    assert len(io.clicks) == 2
    assert eng.state == "lobby_attention"


def test_lobby_alt_tab_blocks_click(tmp_path):
    eng, io, frame = make_engine(tmp_path)
    frame("lobby_play")
    eng._tick()
    io.active = False
    eng._tick()
    assert eng.paused
    assert eng.pause_reason == "focus_lost"
    assert io.clicks == []


def test_uniform_lobby_capture_rejected_and_switch_persists(tmp_path):
    io = LobbyIO()
    backend = Backend(tmp_path, io)
    backend._shot = np.full((120, 250, 3), 100, dtype=np.uint8)
    assert backend.save_template("lobby_play", "flat", 0, 0, 1, 1)["error"] == "low_detail_template"
    assert backend.set_config({"lobby_autostart_enabled": False})["ok"]
    assert Backend(tmp_path, io).cfg.lobby_autostart_enabled is False

def test_alt_tab_resets_stale_lobby_candidates(tmp_path):
    eng, io, frame = make_engine(tmp_path)
    frame("lobby_play")
    eng._tick()
    assert eng._lobby_candidate_hits == 1
    io.active = False
    eng._tick()
    assert eng._lobby_candidate_hits == 0
    assert not io.clicks
