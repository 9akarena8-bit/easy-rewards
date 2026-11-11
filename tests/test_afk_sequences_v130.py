"""v1.3 tests: sequence variations, screen wait latch, config and safe abort."""
import random
import tempfile
from pathlib import Path

import cv2
import numpy as np

from core import Config, Engine, Template
from backend import Backend


class IO:
    def __init__(self):
        self.events = []
        self.focused = True
        self.image = np.zeros((140, 220, 3), np.uint8)

    def game_in_foreground(self):
        return self.focused

    def focus_game(self):
        pass

    def foreground_title(self):
        return 'Fortnite'

    def hold_keys(self, keys, seconds, abort):
        if not abort():
            self.events.append(('keys', tuple(keys), seconds))

    def press_key(self, key):
        self.events.append(('press', key))

    def hold_mouse(self, button, seconds, abort):
        if not abort():
            self.events.append(('mouse', button, seconds))

    def aim_and_fire(self, seconds, abort):
        if not abort():
            self.events.append(('aim', seconds))

    def move_mouse_relative(self, dx, dy, seconds, abort):
        if not abort():
            self.events.append(('camera', dx, dy, seconds))

    def grab(self):
        return self.image.copy()

    def click(self, x=None, y=None):
        self.events.append(('click', x, y))


def test_weighted_sequence_includes_all_requested_movement_modes():
    io = IO()
    cfg = Config(afk_sequence_enabled=True, afk_pause_min=.5, afk_pause_max=2.,
                 afk_pickaxe_enabled=True, afk_grenade_enabled=True, afk_weapon_enabled=True)
    eng = Engine(cfg, io, Path('.'), log=lambda *a, **kw: None)
    random.seed(3212)
    for _ in range(1000):
        eng._smart_afk_action(lambda: False)
    assert eng.input_count == 1000
    combos = {e[1] for e in io.events if e[0] == 'keys'}
    assert ('w', 'shift', 'ctrl', 'space') in combos
    assert ('w', 'shift', 'space') in combos
    assert ('w', 'shift', 'ctrl') in combos
    assert ('w', 'shift') in combos
    assert ('w', 'a') in combos and ('s', 'd') in combos
    assert ('ctrl',) in combos
    assert ('space',) in combos
    assert any(e[0] == 'camera' for e in io.events)
    assert any(e[0] == 'mouse' and e[1] == 'left' for e in io.events)
    assert any(e[0] == 'aim' for e in io.events)
    assert set(e[1] for e in io.events if e[0] == 'press' and str(e[1]) in '123456') == set('123456')
    assert .5 <= eng._afk_wait() <= 2.


def test_disabled_optional_weapons_and_inventory_are_not_triggered():
    io=IO()
    cfg=Config(afk_weapon_enabled=False, afk_pickaxe_enabled=False, afk_grenade_enabled=False)
    eng=Engine(cfg, io, Path('.'), log=lambda *a, **kw: None)
    random.seed(998)
    for _ in range(100):
        eng._smart_afk_action(lambda: False)
    assert all(e[0] not in ('mouse', 'aim') for e in io.events)
    assert not any(e[0] == 'press' and e[1] == 'y' for e in io.events)
    assert eng.last_input_error == ''


def test_abort_does_not_send_input_or_count_an_action():
    io=IO()
    eng=Engine(Config(),io,Path('.'),log=lambda *a,**kw: None)
    eng._smart_afk_action(lambda: True)
    assert not io.events and eng.input_count == 0


def test_death_template_latches_until_replay_appears():
    io=IO()
    rng=np.random.default_rng(555)
    dead=rng.integers(0,255,(24,32),dtype=np.uint8)
    replay=rng.integers(0,255,(21,38),dtype=np.uint8)
    cfg=Config(threshold=.82, afk_enabled=True, auto_focus=False, scales=[1.0])
    eng=Engine(cfg, io, Path('.'), log=lambda *a, **kw: None)
    eng.templates=[Template('death_overlay', 'death', dead), Template('replay_button', 'replay', replay)]
    gray=np.zeros((140,220),dtype=np.uint8)
    gray[10:34,12:44]=dead
    io.image=cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    eng._tick()
    assert eng.state=='await_replay' and eng._awaiting_replay
    assert not io.events
    io.image=np.zeros_like(io.image)
    eng._tick()
    assert eng.state=='await_replay'
    assert not io.events
    gray=np.zeros((140,220),dtype=np.uint8)
    gray[60:81,80:118]=replay
    io.image=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    eng._tick()
    assert any(e[0]=='click' for e in io.events)
    assert not eng._awaiting_replay
    assert eng.games==1


def test_configuration_validation_and_persistence():
    with tempfile.TemporaryDirectory() as d:
        backend=Backend(d,IO())
        res=backend.set_config({'afk_pause_min': 1.4, 'afk_pause_max': 2.2,
                                'afk_camera_pixels_360': 1700, 'afk_slide_enabled':False})
        assert res['ok']
        again=Backend(d,IO())
        assert again.cfg.afk_pause_min==1.4
        assert again.cfg.afk_camera_pixels_360==1700
        assert again.cfg.afk_slide_enabled is False
        assert again.set_config({'afk_camera_pixels_360':'bad'})['rejected']==['afk_camera_pixels_360']
