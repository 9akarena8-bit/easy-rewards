"""Regression checks for F7-to-input flow and installed-data placement."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from core import Config, Engine
from backend import Backend
import paths


class GameIO:
    window_title = 'Fortnite'

    def __init__(self, active=True):
        self.active = active
        self.actions = []

    def grab(self):
        raise AssertionError('No templates means no screenshot is needed')

    def hold_key(self, key, seconds, abort):
        if not abort():
            self.actions.append(key)

    def game_in_foreground(self):
        return self.active

    def foreground_title(self):
        return 'Fortnite test client' if self.active else 'Easy Rewards'

    def focus_game(self):
        pass


def test_no_templates_sends_key_without_grabbing_screen():
    with tempfile.TemporaryDirectory() as directory:
        io = GameIO()
        engine = Engine(Config(afk_enabled=True, auto_focus=False), io, Path(directory),
                        log=lambda *a, **k: None)
        engine._next_afk = 0
        engine._tick()
        assert engine.state == 'afk_only'
        assert engine.input_count == 1 and io.actions
        assert engine.last_input in 'WASD'


def test_not_in_game_prevents_input_and_reports_state():
    with tempfile.TemporaryDirectory() as directory:
        io = GameIO(active=False)
        engine = Engine(Config(afk_enabled=True, auto_focus=False), io, Path(directory),
                        log=lambda *a, **k: None)
        engine._next_afk = 0
        engine._tick()
        assert engine.state == 'waiting_window'
        assert engine.input_count == 0
        assert not io.actions


def test_frontend_sees_diagnostics():
    with tempfile.TemporaryDirectory() as directory:
        data = Backend(directory, GameIO(active=False)).state()
        assert data['diagnostics']['game_active'] is False
        assert data['diagnostics']['foreground_title'] == 'Easy Rewards'
        assert data['diagnostics']['game_title'] == 'Fortnite'
        assert data['engine']['input_count'] == 0


def test_packaged_userdata_does_not_modify_resource_dir(monkeypatch, tmp_path):
    bundled = tmp_path / 'bundled'
    bundled.mkdir()
    user = tmp_path / 'user'
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(bundled), raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(user))
    assert paths.resources() == bundled
    assert paths.data() == user / 'EasyRewards'
    assert paths.data().is_dir()
