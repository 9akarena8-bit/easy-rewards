"""v1.3.9 patch: live hotkey settings and launcher focus request."""
from pathlib import Path

from backend import Backend, Hooks
from core import Config


class FakeWindowIO:
    window_title = "Fortnite"

    def __init__(self, active=False, found=True):
        self.active = active
        self.found = found
        self.focus_calls = 0

    def game_in_foreground(self):
        return self.active

    def game_window_found(self):
        return self.found

    def foreground_title(self):
        return "Fortnite" if self.active else "Desktop"

    def foreground_process(self):
        return "FortniteClient-Win64-Shipping.exe" if self.active else "explorer.exe"

    def focus_game(self):
        self.focus_calls += 1
        return False


def test_hotkey_defaults_match_previous_shortcuts():
    cfg = Config()
    assert (cfg.hotkey_start, cfg.hotkey_stop, cfg.hotkey_pause) == ("F7", "F8", "F10")


def test_hotkey_change_persists_and_refreshes_live_bindings(tmp_path):
    io = FakeWindowIO()
    hooks = Hooks()
    seen = []
    hooks.hotkeys_changed = lambda: seen.append(1)
    backend = Backend(tmp_path, io, hooks)
    try:
        result = backend.set_config({"hotkey_start": "f4"})
        assert result == {"ok": True, "rejected": []}
        assert backend.cfg.hotkey_start == "F4"
        assert seen == [1]
        assert Config.load(tmp_path / "config.json").hotkey_start == "F4"
        assert backend.set_config({"hotkey_stop": "F4"}) == {
            "ok": False, "rejected": ["hotkey_stop"]}
        assert backend.set_config({"hotkey_pause": "F6"}) == {
            "ok": False, "rejected": ["hotkey_pause"]}
        assert backend.set_config({"hotkey_start": "F13"}) == {
            "ok": False, "rejected": ["hotkey_start"]}
        assert seen == [1]
    finally:
        backend.shutdown()


def test_launcher_requests_focus_only_if_verified_game_exists(tmp_path):
    io = FakeWindowIO(active=False, found=True)
    hooks = Hooks()
    focus_requests = []
    hooks.focus_on_start = lambda: focus_requests.append(True)
    backend = Backend(tmp_path, io, hooks)
    try:
        backend.start()
        assert backend.engine.running
        assert focus_requests == [True]
    finally:
        backend.stop()
        backend.shutdown()


def test_launcher_does_not_focus_when_fortnite_missing(tmp_path):
    io = FakeWindowIO(active=False, found=False)
    hooks = Hooks()
    requests = []
    hooks.focus_on_start = lambda: requests.append(True)
    backend = Backend(tmp_path, io, hooks)
    try:
        backend.start()
        assert requests == []
    finally:
        backend.stop()
        backend.shutdown()


def test_approved_skin_is_loaded_and_checkout_remains_demo():
    root = Path(__file__).resolve().parents[1]
    html = (root / "ui" / "index.html").read_text(encoding="utf-8")
    css = (root / "ui" / "approved_v2.css").read_text(encoding="utf-8")
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'href="approved_v2.css"' in html
    assert "pirate_seascape.svg" in css
    for key in ("hotkey_start", "hotkey_stop", "hotkey_pause"):
        assert f'hotkeySelect("{key}"' in js
    import payment_hub
    catalog = payment_hub.catalog()
    assert catalog["active"] is False
    assert catalog["automatic_activation"] is False

def test_corrupted_hotkeys_recover_safe_defaults(tmp_path):
    import json
    config = tmp_path / "config.json"
    for corrupted in (
        {"hotkey_start": "F7", "hotkey_stop": "F7", "hotkey_pause": "F10"},
        {"hotkey_start": "F6", "hotkey_stop": "F8", "hotkey_pause": "F10"},
        {"hotkey_start": None, "hotkey_stop": "F8", "hotkey_pause": "F10"},
        {"hotkey_start": "F18", "hotkey_stop": "F8", "hotkey_pause": "F10"},
    ):
        config.write_text(json.dumps(corrupted), encoding="utf-8")
        c = Config.load(config)
        assert (c.hotkey_start, c.hotkey_stop, c.hotkey_pause) == ("F7", "F8", "F10")
