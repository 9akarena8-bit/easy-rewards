"""Ordered slide input and stop-safety regression checks."""
import sys

import pytest

import core
from core import Config, Engine


class FakeSequenceIO:
    def __init__(self):
        self.commands = []

    def hold_keys(self, keys, seconds, abort):
        self.commands.append(("legacy_hold", tuple(keys)))

    def slide_sequence(self, seconds, jump, abort):
        self.commands.append(("slide", bool(jump)))


@pytest.mark.parametrize("selected,jump", [("slide", False), ("slide_jump", True)])
def test_core_routes_slide_to_ordered_io(monkeypatch, tmp_path, selected, jump):
    io = FakeSequenceIO()
    engine = Engine(Config(), io, tmp_path)
    monkeypatch.setattr(core.random, "choices", lambda values, weights, k: [selected])
    engine._smart_afk_action(lambda: False)
    assert io.commands == [("slide", jump)]
    assert engine.input_count == 1


@pytest.mark.skipif(sys.platform != "win32", reason="WinIO only exists on Windows")
def test_slide_taps_ctrl_then_jumps_and_releases_every_key(monkeypatch):
    import winio
    events = []
    monkeypatch.setattr(winio, "_key", lambda scan, up: events.append((scan, up)))
    winio.WinIO().slide_sequence(.9, True, lambda: False)
    names = {code: key for key, code in winio.SCANCODES.items()}
    observed = [(names[k], "up" if up else "down") for k, up in events]
    assert observed == [
        ("w", "down"), ("shift", "down"), ("ctrl", "down"),
        ("ctrl", "up"), ("space", "down"), ("space", "up"),
        ("shift", "up"), ("w", "up")]


@pytest.mark.skipif(sys.platform != "win32", reason="WinIO only exists on Windows")
def test_slide_stop_before_ctrl_releases_w_and_shift(monkeypatch):
    import winio
    events = []
    monkeypatch.setattr(winio, "_key", lambda scan, up: events.append((scan, up)))
    scans = winio.SCANCODES
    def abort():
        return len(events) >= 2
    winio.WinIO().slide_sequence(2.0, False, abort)
    assert events == [
        (scans["w"], False), (scans["shift"], False),
        (scans["shift"], True), (scans["w"], True)]
