"""No-network tests for optional Discord alerts and secret handling."""
import json
import time

import discord_notifications as dn
from backend import Backend


VALID = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz_123456789"


class IO:
    def game_in_foreground(self):
        return False

    def game_window_found(self):
        return False

    def foreground_title(self):
        return "Desktop"


def test_webhook_hosts_and_paths_strictly_allowlisted():
    assert dn.valid_webhook(VALID)
    assert not dn.valid_webhook(VALID.replace("discord.com", "discord.com.evil.test"))
    assert not dn.valid_webhook(VALID.replace("https://", "http://"))
    assert not dn.valid_webhook("https://discord.com/api/webhooks/notanid/secret")
    assert not dn.valid_webhook(VALID + "?wait=true")
    assert not dn.valid_webhook(VALID + "#anchor")
    assert not dn.valid_webhook(VALID.replace("discord.com", "discord.gg"))


def test_disabled_by_default_and_never_expose_webhook(tmp_path):
    b = Backend(tmp_path, IO())
    assert b.state()["discord_notifications"]["enabled"] is False
    assert not b.discord_test()["ok"]
    result = b.discord_configure(VALID, enabled=False)
    assert result["ok"] and result["configured"]
    assert VALID not in json.dumps(b.state())
    report = b.create_support_report()
    assert report["ok"]
    assert VALID not in report["text"]
    assert VALID not in report["path"]


def test_enabled_events_nonblocking_and_test_message(monkeypatch, tmp_path):
    messages = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, n):
            return b""

    def fake_urlopen(request, timeout):
        assert timeout <= 8
        assert request.full_url == VALID
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["allowed_mentions"] == {"parse": []}
        messages.append(payload["content"])
        return Response()

    monkeypatch.setattr(dn, "urlopen", fake_urlopen)
    b = Backend(tmp_path, IO())
    assert b.discord_configure(VALID, enabled=True)["ok"]
    b.log("log.started")
    b.log("log.replay_clicked", source="yellow", attempt=1)
    b.log("log.error", err="do not send sensitive log details")
    assert b.discord_test()["ok"]
    b.discord._pending.join()
    assert len(messages) == 4
    assert any("Play Again" in msg for msg in messages)
    assert all("sensitive" not in msg for msg in messages)
    assert b.state()["discord_notifications"]["last_sent"] != ""
    assert VALID not in json.dumps(b.state())
    assert b.discord_clear()["ok"]
    assert b.state()["discord_notifications"]["configured"] is False
    assert not b.discord.notify("log.stopped")


def test_invalid_or_missing_webhook_never_enables(tmp_path):
    d = dn.DiscordNotifications(tmp_path / "notifications.json")
    assert not d.configure("https://example.com/hello", True)["ok"]
    assert not d.configure("", True)["ok"]
    assert d.configure(VALID, True)["ok"]
    assert d.status()["configured"]
    d2 = dn.DiscordNotifications(tmp_path / "notifications.json")
    assert d2.status()["enabled"]
    assert d2.clear()["ok"]
    assert not (tmp_path / "notifications.json").exists()


def test_configure_failure_preserves_existing_secret_and_status(tmp_path, monkeypatch):
    path = tmp_path / "discord.json"
    d = dn.DiscordNotifications(path)
    assert d.configure(VALID, enabled=False)["ok"]
    saved = path.read_bytes()
    before = d.status()

    def fail_replace(*args, **kwargs):
        raise PermissionError("simulated file lock")

    monkeypatch.setattr(dn.os, "replace", fail_replace)
    new_url = VALID.replace("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert d.configure(new_url, enabled=True)["ok"] is False
    assert d.status() == before
    assert path.read_bytes() == saved
    assert not list(tmp_path.glob("*.tmp"))


def test_clear_failure_preserves_persisted_state(tmp_path, monkeypatch):
    from pathlib import Path
    path = tmp_path / "discord.json"
    d = dn.DiscordNotifications(path)
    assert d.configure(VALID, enabled=False)["ok"]
    original = Path.unlink

    def deny(self, *args, **kwargs):
        if self == path:
            raise PermissionError("locked")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny)
    assert d.clear()["ok"] is False
    assert d.status()["configured"]
    assert path.exists()


def test_support_report_removes_webhook_from_unexpected_error(tmp_path):
    import support_report
    b = Backend(tmp_path, IO())
    b.log("log.error", err="network " + VALID + "?wait=true")
    result = b.create_support_report()
    assert result["ok"]
    assert VALID not in result["text"]
    assert "DISCORD_WEBHOOK_REDACTED" in result["text"]
    assert VALID not in support_report.clean(VALID)
