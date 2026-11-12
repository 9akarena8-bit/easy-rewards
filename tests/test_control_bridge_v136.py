"""v1.3.6 control-path regression checks.

These tests verify both sides of the GUI -> Python path. Actual WebView2 mouse
delivery must also be verified on Windows by the beta tester.
"""
from pathlib import Path

from backend import Backend

ROOT = Path(__file__).resolve().parents[1]


class FakeIO:
    def game_in_foreground(self):
        return False

    def game_window_found(self):
        return False

    def foreground_title(self):
        return "Easy Rewards"

    def foreground_process(self):
        return "EasyRewards.exe"


def test_backend_records_gui_and_hotkey_commands(tmp_path):
    b = Backend(tmp_path, FakeIO())
    assert b.state()["controls"]["sequence"] == 0
    b.stop()  # Also used for global F8.
    assert b.state()["controls"]["last"] == "stop"
    assert b.state()["controls"]["sequence"] == 1
    b.pause()  # Also used for global F10.
    assert b.state()["controls"]["last"] == "pause"
    assert b.state()["controls"]["sequence"] == 2
    result = b.focus_game_now()
    assert result["reason"] == "not_found"
    assert b.state()["controls"]["last"] == "focus"
    assert b.state()["controls"]["sequence"] == 3
    result = b.input_probe_delayed("invalid")
    assert result["reason"] == "invalid_target"
    assert b.state()["controls"]["last"] == "probe_invalid"


def test_mouse_controls_do_not_depend_on_click_bubbling():
    js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'document.addEventListener("pointerdown", ev =>' in js
    assert 'const CONTROL_ACTIONS = new Set(["start", "stop", "pause", "main", "focusgame", "ptest"])' in js
    assert "void runControlAction(btn.dataset.act" in js
    assert "lastPointerControl?.element === el" in js
    assert '"controls": {"last":' in (ROOT / "backend.py").read_text(encoding="utf-8")
    assert "ST.controls?.last" in js


def test_hotkey_callbacks_do_not_block_polling_thread():
    code = (ROOT / "winio.py").read_text(encoding="utf-8")
    assert 'threading.Thread(target=invoke, name=f"hotkey-{vk}"' in code
    shell = (ROOT / "webapp.py").read_text(encoding="utf-8")
    # F7/F8/F10 are defaults, but remapping uses the current config.
    for action in ("start", "stop", "pause"):
        assert f"backend.cfg.hotkey_{action}: backend.{action}" in shell
    for key in ("F6", "F9"):
        assert f'"{key}": ' in shell
