"""Settings from the approved-v2 beta survive; writes are atomic."""
import json
import threading

from backend import Backend
from core import Config


class IO:
    def game_in_foreground(self):
        return False
    def game_window_found(self):
        return False
    def foreground_title(self):
        return "Desktop"


def test_load_migrates_hotkey_field_names_from_v2(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "hotkey_start": "F1", "hotkey_stop": "F2",
        "hotkey_pause": "F3", "auto_launch_game": False,
        "afk_pause_on_alt_tab": True,
    }), encoding="utf-8")
    loaded = Config.load(path)
    assert (loaded.afk_start_hotkey, loaded.afk_stop_hotkey, loaded.afk_pause_hotkey) == ("F1", "F2", "F3")
    assert loaded.afk_launch_game is False
    b = Backend(tmp_path, IO())
    assert b.cfg.afk_start_hotkey == "F1"
    assert b.cfg.afk_stop_hotkey == "F2"
    assert b.cfg.afk_pause_hotkey == "F3"


def test_new_field_names_take_precedence_over_legacy(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "hotkey_start": "F1", "afk_start_hotkey": "F4",
    }), encoding="utf-8")
    assert Config.load(path).afk_start_hotkey == "F4"


def test_non_dict_json_loads_defaults_without_crash(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")
    assert Config.load(path).afk_start_hotkey == "F7"


def test_atomic_config_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.afk_start_hotkey = "F3"
    cfg.save(path)
    assert Config.load(path).afk_start_hotkey == "F3"
    assert not list(tmp_path.glob(".cfg-*.tmp"))


def test_rapid_backend_settings_updates_preserve_valid_json(tmp_path):
    b = Backend(tmp_path, IO())
    workers = [threading.Thread(target=lambda i=i: b.set_config({"afk_hold": .5 + (i % 9) * .1}))
               for i in range(18)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(3)
        assert not worker.is_alive()
    settings = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert isinstance(settings, dict)
    assert .5 <= settings["afk_hold"] <= 1.3
    assert not list(tmp_path.glob(".cfg-*.tmp"))


def test_theme_and_language_are_saved_and_failed_write_does_not_change_state(tmp_path, monkeypatch):
    backend = Backend(tmp_path, IO())
    assert backend.set_config({"theme": "light", "ui_language": "uk"})["ok"]
    assert Backend(tmp_path, IO()).cfg.theme == "light"
    assert Backend(tmp_path, IO()).cfg.ui_language == "uk"

    def fail_save(self, path):
        raise PermissionError(path)

    monkeypatch.setattr(Config, "save", fail_save)
    assert backend.set_config({"theme": "dark", "ui_language": "en"}) == {
        "ok": False, "rejected": [], "error": "save_failed",
    }
    assert backend.state()["cfg"]["theme"] == "light"
    assert backend.state()["cfg"]["ui_language"] == "uk"
    assert backend.set_config({"afk_launch_game": "false"})["rejected"] == ["afk_launch_game"]
