"""v1.4.0 beta: launcher dispatch, editable hotkeys and safe failure handling."""
from pathlib import Path
import time

from backend import AFK_HOTKEY_CHOICES, Backend
from core import Config

ROOT = Path(__file__).resolve().parents[1]


def until(predicate, seconds=2.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.01)
    return bool(predicate())


class FakeEpicIO:
    def __init__(self, *, found=False, launch_result=True):
        self.found = found
        self.launch_result = launch_result
        self.launch_count = 0
        self.focus_count = 0

    def game_window_found(self):
        return self.found

    def game_in_foreground(self):
        return False

    def foreground_title(self):
        return "Desktop"

    def foreground_process(self):
        return "explorer.exe"

    def launch_game(self):
        self.launch_count += 1
        return self.launch_result

    def focus_game(self):
        self.focus_count += 1
        return False


def test_start_launches_via_epic_only_when_game_absent(tmp_path):
    io = FakeEpicIO()
    b = Backend(tmp_path, io)
    try:
        result = b.start()
        assert result == {"ok": True, "reason": "start_queued"}
        assert until(lambda: b.engine.running)
        assert until(lambda: io.launch_count == 1)
        assert b.state()["cfg"]["afk_launch_game"] is True
    finally:
        b.stop()


def test_start_existing_game_does_not_launch_twice(tmp_path):
    io = FakeEpicIO(found=True)
    b = Backend(tmp_path, io)
    try:
        assert b.start()["ok"] is True
        assert io.launch_count == 0
        assert until(lambda: io.focus_count >= 1)
    finally:
        b.stop()


def test_missing_epic_responds_with_error_without_starting(tmp_path):
    io = FakeEpicIO(launch_result=False)
    b = Backend(tmp_path, io)
    result = b.start()
    assert result == {"ok": True, "reason": "start_queued"}
    assert until(lambda: io.launch_count == 1)
    assert b.engine.running
    assert until(lambda: b.state()["controls"]["start_error"] == "epic_launcher_unavailable")
    b.stop()


def test_autolaunch_can_be_disabled_and_saved(tmp_path):
    io = FakeEpicIO(launch_result=False)
    b = Backend(tmp_path, io)
    assert b.set_config({"afk_launch_game": False})["ok"] is True
    try:
        assert b.start()["ok"] is True
        assert io.launch_count == 0
    finally:
        b.stop()
    assert Config.load(tmp_path / "config.json").afk_launch_game is False


def test_shortcut_validation_prevents_collisions_and_reserved_keys(tmp_path):
    b = Backend(tmp_path, FakeEpicIO())
    assert b.set_config({"afk_start_hotkey": "f3"}) == {"ok": True, "rejected": []}
    assert b.cfg.afk_start_hotkey == "F3"
    assert b.set_config({"afk_stop_hotkey": "F3"}) == {"ok": False, "rejected": ["afk_stop_hotkey"]}
    assert b.set_config({"afk_start_hotkey": "F6"}) == {"ok": False, "rejected": ["afk_start_hotkey"]}
    assert b.set_config({"afk_start_hotkey": "F12"}) == {"ok": False, "rejected": ["afk_start_hotkey"]}
    assert b.set_config({"afk_stop_hotkey": "Enter"}) == {"ok": False, "rejected": ["afk_stop_hotkey"]}
    assert b.set_config({"afk_pause_hotkey": "f5"}) == {"ok": True, "rejected": []}
    assert b.cfg.afk_pause_hotkey == "F5"
    assert b.set_config({"afk_start_hotkey": "F5"}) == {"ok": False, "rejected": ["afk_start_hotkey"]}
    assert b.set_config({"afk_pause_hotkey": "F3"}) == {"ok": False, "rejected": ["afk_pause_hotkey"]}
    assert b.set_config({"afk_pause_hotkey": "F12"}) == {"ok": False, "rejected": ["afk_pause_hotkey"]}
    assert {"F1", "F5", "F7", "F8", "F11", "F12"} <= set(AFK_HOTKEY_CHOICES)
    assert all(k not in AFK_HOTKEY_CHOICES for k in ("F6", "F9", "F10"))
    assert Config.load(tmp_path / "config.json").afk_start_hotkey == "F3"


def test_malformed_config_never_overwrites_emergency_stop(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"afk_start_hotkey":"F12", "afk_stop_hotkey":"F12"}', encoding="utf-8")
    b = Backend(tmp_path, FakeEpicIO())
    assert b.cfg.afk_start_hotkey == "F7"
    assert b.cfg.afk_stop_hotkey == "F12"


def test_duplicated_config_hotkeys_repaired_before_polling(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"afk_start_hotkey":"F8", "afk_stop_hotkey":"F8"}', encoding="utf-8")
    b = Backend(tmp_path, FakeEpicIO())
    assert b.cfg.afk_start_hotkey == "F8"
    assert b.cfg.afk_stop_hotkey == "F12"


def test_beta_gui_contains_live_hotkeys_and_existing_controls():
    js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    shell = (ROOT / "webapp.py").read_text(encoding="utf-8")
    assert 'hotkeyPicker("afk_start_hotkey"' in js
    assert 'hotkeyPicker("afk_stop_hotkey"' in js
    assert 'hotkeyPicker("afk_pause_hotkey"' in js
    assert 'tog("afk_launch_game"' in js
    assert 'data-act="stop"' in js
    assert 'backend.cfg.afk_start_hotkey: backend.start' in shell
    assert 'backend.cfg.afk_stop_hotkey: backend.stop' in shell
    assert 'backend.cfg.afk_pause_hotkey: backend.pause' in shell
    assert 'HotkeyPoller(hotkey_bindings)' in shell
    assert 'data-act="afk_report"' in js
    assert 'if (a === "support_report" || a === "afk_report")' in js


def test_epic_capability_and_dispatch_status_do_not_claim_game_is_open(tmp_path):
    io = FakeEpicIO()
    io.epic_launcher_available = lambda: True
    backend = Backend(tmp_path, io)
    try:
        assert backend.state()["diagnostics"]["epic_launcher_available"] is True
        assert backend.start()["reason"] == "start_queued"
        assert until(lambda: backend.state()["controls"]["launch_status"] == "requested")
        assert backend.state()["diagnostics"]["game_active"] is False
        assert io.launch_count == 1
    finally:
        backend.stop()
    assert backend.state()["controls"]["launch_status"] == "idle"
