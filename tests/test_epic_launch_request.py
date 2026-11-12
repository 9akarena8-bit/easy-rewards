"""Epic Games protocol launch is optional and never proves that the game is running."""
from pathlib import Path

from backend import Backend, Hooks


class WindowIO:
    def __init__(self, found=False):
        self.found = found

    def game_in_foreground(self):
        return False

    def game_window_found(self):
        return self.found

    def focus_game(self):
        return False


def test_start_requests_launcher_only_when_window_missing(tmp_path):
    hooks = Hooks()
    requests = []
    hooks.launch_game = lambda: requests.append("launch") or True
    io = WindowIO(found=False)
    b = Backend(tmp_path, io, hooks)
    try:
        b.start()
        assert requests == ["launch"]
        assert b.engine.focus_result == "launch_requested"
    finally:
        b.stop()
        b.shutdown()


def test_start_does_not_request_launcher_when_game_found(tmp_path):
    hooks = Hooks()
    requests = []
    hooks.launch_game = lambda: requests.append("launch") or True
    io = WindowIO(found=True)
    b = Backend(tmp_path, io, hooks)
    try:
        b.start()
        assert requests == []
    finally:
        b.stop()
        b.shutdown()


def test_epic_launcher_start_can_be_disabled(tmp_path):
    hooks = Hooks()
    requests = []
    hooks.launch_game = lambda: requests.append("launch") or True
    io = WindowIO(found=False)
    b = Backend(tmp_path, io, hooks)
    try:
        assert b.set_config({"auto_launch_game": False})["ok"]
        b.start()
        assert requests == []
    finally:
        b.stop()
        b.shutdown()


def test_uri_is_fixed_to_documented_epic_protocol():
    content = (Path(__file__).resolve().parents[1] / "winio.py").read_text(encoding="utf-8")
    assert "com.epicgames.launcher://apps/" in content
    assert "fn%3A4fe75bbc5a674f4f9b356b5c90567da5%3AFortnite" in content
    assert "?action=launch&silent=true" in content
    assert "winreg.OpenKey(" in content
    assert "os.startfile(EPIC_FORTNITE_URI)" in content
