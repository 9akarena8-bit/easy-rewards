"""Opt-in launcher license verification: no payment acceptance and no spoofed access."""
from __future__ import annotations

import json

import backend
from backend import Backend


class FakeIO:
    def game_in_foreground(self):
        return False

    def game_window_found(self):
        return False

    def foreground_title(self):
        return "Desktop"

    def foreground_process(self):
        return "explorer.exe"


class FakeLicenseClient:
    def __init__(self, server):
        assert server == "https://license.example"
        self.stored = None

    def activate(self, key):
        self.stored = key
        return {"ok": True, "expires_at": 1999999999,
                "seconds_left": 700, "private_field": "DO_NOT_EXPOSE"}

    def check(self):
        if not self.stored:
            return {"ok": False, "error": "not_activated"}
        return {"ok": True, "expires_at": 1999999999, "seconds_left": 699}


def test_optional_key_verification_and_no_fake_paid_subscription(tmp_path, monkeypatch):
    monkeypatch.setenv("FPT_LICENSE_SERVER_URL", "https://license.example")
    monkeypatch.setattr(backend, "LicenseClient", FakeLicenseClient)
    b = Backend(tmp_path, FakeIO())
    result = b.license_activate("FPT-TEST")
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["enforcement_enabled"] is False
    assert result["seconds_left"] == 700
    assert b.license_check()["seconds_left"] == 699
    state = b.state()
    assert state["subscription"]["activation_enabled"] is False
    assert state["license_status"]["ok"] is True
    state_json = json.dumps(state)
    assert "FPT-TEST" not in state_json
    assert "DO_NOT_EXPOSE" not in state_json


def test_server_is_opt_in_and_unsafe_http_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("FPT_LICENSE_SERVER_URL", raising=False)
    b = Backend(tmp_path, FakeIO())
    assert b.license_check() == {"ok": False, "error": "server_not_configured"}
    assert b.state()["license_status"]["configured"] is False
    monkeypatch.setenv("FPT_LICENSE_SERVER_URL", "http://invalid.local")
    b2 = Backend(tmp_path, FakeIO())
    assert b2.license_client is None
    assert b2.state()["license_status"]["error"] == "invalid_https_server"


def test_bad_licence_input_does_not_call_server(tmp_path, monkeypatch):
    monkeypatch.setenv("FPT_LICENSE_SERVER_URL", "https://license.example")
    monkeypatch.setattr(backend, "LicenseClient", FakeLicenseClient)
    b = Backend(tmp_path, FakeIO())
    for bad in ("", " " * 8, "a" * 121, None):
        assert b.license_activate(bad)["ok"] is False
    assert b.license_client.stored is None


def test_checkout_page_is_still_demo_only():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'data-act="license_activate"' in js
    assert 'data-act="license_check"' in js
    assert 'data-act="payment_draft"' in js
    assert 't("payments.not_live")' in js
