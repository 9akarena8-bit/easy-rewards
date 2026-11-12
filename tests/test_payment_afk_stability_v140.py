"""Safety regressions for persisted AFK settings and payment draft inputs."""
import json

import pytest

from core import Config
from payment_hub import LocalInterestDrafts


def test_config_load_recovers_from_non_object_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('["not", "a", "config"]', encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.afk_enabled is True
    assert cfg.afk_interval == 6.0


def test_config_load_rejects_corrupt_afk_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "afk_interval": -50,
        "afk_enabled": "false",
        "afk_hold": 1e100,
        "afk_keys": ["w"],
        "afk_pause_min": 9,
        "afk_pause_max": 1,
        "scales": [0, "bad"],
        "threshold": True,
        "ui_language": "unknown",
        "auto_focus": False,
    }), encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.afk_interval == 6.0
    assert cfg.afk_enabled is True
    assert cfg.afk_hold == 3.0
    assert cfg.afk_keys == "wasd"
    assert (cfg.afk_pause_min, cfg.afk_pause_max) == (0.5, 2.0)
    assert cfg.scales == [1.0, 0.9, 1.1]
    assert cfg.threshold == 0.80
    assert cfg.ui_language == "ru"
    assert cfg.auto_focus is False


def test_config_save_is_atomic_and_roundtrips(tmp_path):
    path = tmp_path / "nested" / "config.json"
    cfg = Config(afk_interval=7.5, afk_enabled=False)
    cfg.save(path)
    assert Config.load(path).afk_interval == 7.5
    assert Config.load(path).afk_enabled is False
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("plan, method, game", [
    ([], "card", ""),
    ("day", {}, ""),
    ({"day": True}, "card", ""),
    ("day", "steam_items", []),
    ("day", "card", None),
])
def test_payment_drafts_reject_unhashable_or_wrong_types(tmp_path, plan, method, game):
    drafts = LocalInterestDrafts(tmp_path / "drafts.json")
    result = drafts.create(plan, method, game)
    assert result["ok"] is False
    assert not drafts.path.exists()
