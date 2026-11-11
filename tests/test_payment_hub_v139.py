"""v1.3.9 payment catalog: no billing, no forged activation, safe item planning."""
import json
from pathlib import Path

import pytest

import payment_hub
from backend import Backend


class OfflineIO:
    def game_in_foreground(self):
        return False

    def foreground_title(self):
        return "Desktop"

    def game_window_found(self):
        return False


def test_all_methods_and_popular_steam_games_are_listed():
    hub = payment_hub.catalog()
    assert hub["active"] is False and hub["automatic_activation"] is False
    assert hub["real_market_quotes"] is False and hub["checkout_ready"] is False
    assert {x["id"] for x in hub["methods"]} == {
        "stars", "card", "sbp", "qr", "bank_transfer", "steam_items"}
    assert {x["id"] for x in hub["games"]} == {
        "dota2", "rust", "tf2", "pubg", "dst", "naraka", "cs2"}
    assert next(x for x in hub["games"] if x["id"] == "cs2")["reversal_days"] == 7
    assert all(method["ready"] is False for method in hub["methods"])


def test_draft_is_local_only_and_does_not_activate_payment(tmp_path):
    b = Backend(tmp_path, OfflineIO())
    original = b.state()["subscription"]
    result = b.payment_interest_create("day", "steam_items", "rust")
    assert result["ok"] and result["status"] == "draft_only"
    assert result["payment_verified"] is False
    assert result["access_activated"] is False
    assert b.state()["subscription"] == original
    assert b.state()["payment_hub"]["active"] is False
    assert b.state()["payment_hub"]["drafts"][0]["id"] == result["id"]
    assert b.state()["payment_hub"]["drafts"][0]["status"] == "draft_only"
    assert (tmp_path / "payment_interest_drafts.json").is_file()


def test_invalid_options_cannot_create_payment(tmp_path):
    b = Backend(tmp_path, OfflineIO())
    for plan, method, game in [
        ("bad", "card", ""), ("day", "fraud", ""), ("day", "steam_items", ""),
        ("day", "card", "dota2"), ("day", "steam_items", "fortnite"),
    ]:
        assert b.payment_interest_create(plan, method, game)["ok"] is False
    assert not (tmp_path / "payment_interest_drafts.json").exists()


def test_preview_catalog_does_not_publish_user_secrets(tmp_path):
    b = Backend(tmp_path, OfflineIO())
    blob = json.dumps(b.state()["payment_hub"])
    for secret in ("shopId", "api_key", "steam_secret", "bot_token", "secret_key"):
        assert secret not in blob
    assert not hasattr(b, "grant_access")
    assert not hasattr(b, "payment_confirm")


def test_item_selector_finds_exact_and_minimum_overpayment():
    items = [
        {"appid": 570, "assetid": "dota-a", "net_kopeks": 30000, "tradable": True},
        {"appid": 252490, "assetid": "rust-b", "net_kopeks": 20000, "tradable": True},
        {"appid": 440, "assetid": "tf2-c", "net_kopeks": 22000, "tradable": True},
        {"appid": 252490, "assetid": "rust-untradable", "net_kopeks": 49900, "tradable": False},
    ]
    choice = payment_hub.pick_items(50000, items)
    assert choice["overpay_kopeks"] == 0
    assert set(choice["assetids"]) == {"dota-a", "rust-b"}
    assert choice["authorized_to_deliver"] is False
    assert payment_hub.pick_items(40000, items)["overpay_kopeks"] == 2000


def test_cs2_trade_protection_and_mixing_safety():
    items = [
        {"appid": 730, "assetid": "cs2-1", "net_kopeks": 32000, "tradable": True},
        {"appid": 570, "assetid": "dota-1", "net_kopeks": 18000, "tradable": True},
    ]
    assert payment_hub.pick_items(50000, items) is None
    result = payment_hub.pick_items(30000, items)
    assert result["assetids"] == ["cs2-1"]
    assert result["trade_protection_days"] == 7
    assert result["authorized_to_deliver"] is False


def test_quote_requires_trusted_integer_kopeks_and_unique_assets():
    with pytest.raises(ValueError):
        payment_hub.pick_items(5000, [{"appid": 570, "assetid": "1",
                                       "net_kopeks": 5000.1, "tradable": True}])
    with pytest.raises(ValueError):
        payment_hub.pick_items(5000, [{"appid": 570, "assetid": "1",
                                       "net_kopeks": 5000, "tradable": True}] * 2)
    with pytest.raises(ValueError):
        payment_hub.pick_items(True, [])


def test_web_ui_mentions_non_payable_drafts_and_no_real_checkout():
    root = Path(__file__).resolve().parents[1]
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'data-act="payment_draft"' in js
    assert 'payMethod === "steam_items"' in js
    assert 'api.payment_interest_create' in js
    assert 't("payments.not_live")' in js
    assert 't("payments.draft_warning")' in js
