"""Builds the whole GUI against a stub tkinter and drives language/theme/save paths.
Catches typos, wrong attribute names and bad signatures; it can NOT judge how it looks."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fake_tk  # noqa: E402

fake_tk.install()
import app_classic as app  # noqa: E402
from i18n import STRINGS  # noqa: E402


class FakeIO:
    def grab(self):
        import numpy as np
        return np.zeros((200, 300, 3), dtype="uint8")
    def click(self, x, y): pass
    def hold_key(self, *a): pass
    def game_in_foreground(self): return True
    def focus_game(self): pass


def test_gui_builds_and_switches():
    tmp = Path(tempfile.mkdtemp())
    app.CONFIG_PATH = tmp / "config.json"
    app.WinIO = FakeIO
    app.HotkeyPoller = None
    a = app.App()

    for lang in ("ru", "en", "uk"):
        a.set_ui_language(lang)
        assert a.cfg.ui_language == lang
    for theme in ("dark", "light"):
        a.set_theme(theme)
        assert a.c is app.PALETTES[theme]
    a.set_game_language("en")
    for page in a.pages:
        a.show(page)
    a._toggle_key("w")
    a.show("updates")
    a.v_url.set("")
    a.check_updates()
    a._handle_update_event(("available", {"version": "9.9.9", "zip": "x", "sha256": "0" * 64}, False))
    assert a.pending_update and a.btn_upd.key == "upd.install"
    a._handle_update_event(("error", "boom", False))
    a._handle_update_event(("done", "9.9.9", False))
    assert a.restart_requested
    a.restart_requested = False
    a.save_settings()
    a.test_now()
    a.engine.state = "in_match"
    a._tick()
    a._log("log.clicked", name="x", score="0.9", x=1, y=2)
    a._tick()
    assert (tmp / "config.json").exists()
    import json
    saved = json.loads((tmp / "config.json").read_text())
    assert saved["theme"] == "light" and saved["ui_language"] == "uk" and "w" not in saved["afk_keys"]


def test_every_ui_key_exists_in_all_languages():
    import re
    src = Path(app.__file__).read_text(encoding="utf-8")
    keys = set(re.findall(r'"((?:nav|home|btn|stat|log|state|settings|set|theme|afk|tpl|dlg|upd)\.[a-z_]+)"', src)) | {"hotkeys"}
    for k in keys:
        for lang in STRINGS:
            assert k in STRINGS[lang], (k, lang)


if __name__ == "__main__":
    test_gui_builds_and_switches()
    test_every_ui_key_exists_in_all_languages()
    print("gui smoke ok")
