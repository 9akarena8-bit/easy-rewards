"""Offline tests for background download, click-to-install and disabled billing."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import release_updater
import subscription_preview
from backend import Backend


class NoGame:
    def game_in_foreground(self):
        return False

    def foreground_title(self):
        return "Desktop"


def meta_for(payload):
    return {
        "version": "1.3.9",
        "filename": "EasyRewards_Setup_1.3.9.exe",
        "url": "https://github.com/9akarena8-bit/easy-rewards/releases/download/v1.3.9/EasyRewards_Setup_1.3.9.exe",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
        "notes": "Test release",
    }


def test_subscriptions_are_read_only_and_disabled(tmp_path):
    snapshot = subscription_preview.snapshot()
    assert snapshot["enabled"] is False
    assert snapshot["payments_enabled"] is False
    assert snapshot["activation_enabled"] is False
    assert snapshot["remaining_seconds"] is None
    assert snapshot["payment_methods"] == ["card", "sbp"]
    assert [p["id"] for p in snapshot["plans"]] == ["demo", "day", "three_days", "week"]
    assert [p["hours"] for p in snapshot["plans"]] == [None, 24, 72, 168]
    assert Backend(tmp_path, NoGame()).state()["subscription"] == snapshot


def test_cached_installer_verification_and_tampering(tmp_path):
    payload = b"test installer bytes"
    meta = meta_for(payload)
    path = tmp_path / meta["filename"]
    path.write_bytes(payload)
    assert release_updater.verify_installer(meta, path)
    path.write_bytes(b"modified installer")
    assert not release_updater.verify_installer(meta, path)
    path.unlink()
    assert not release_updater.verify_installer(meta, path)


def test_background_prepare_never_launches_installer(monkeypatch, tmp_path):
    payload = b"test build"
    meta = meta_for(payload)
    installer = tmp_path / meta["filename"]
    installer.write_bytes(payload)
    launched = []
    downloaded = []
    monkeypatch.setattr(release_updater, "latest_release", lambda v: meta)
    monkeypatch.setattr(release_updater, "download_installer", lambda metadata: downloaded.append(metadata) or installer)
    monkeypatch.setattr(release_updater, "launch_installer", lambda p: launched.append(p))
    backend = Backend(tmp_path, NoGame())
    backend.release_mode = True
    backend.version = "1.3.2"
    assert backend.update_check()["status"] == "available"
    assert backend.update_prepare()["status"] == "ready"
    assert not launched
    assert len(downloaded) == 1
    assert backend.update_check()["status"] == "ready"
    # Already verified; background work does not download twice.
    assert backend.update_prepare()["status"] == "ready"
    assert len(downloaded) == 1
    assert backend.update_install()["status"] == "installer_started"
    assert launched == [installer]


def test_update_requires_stopping_running_engine(monkeypatch, tmp_path):
    meta = meta_for(b"test")
    monkeypatch.setattr(release_updater, "latest_release", lambda v: meta)
    backend = Backend(tmp_path, NoGame())
    backend.release_mode = True
    backend.version = "1.3.2"
    assert backend.update_check()["status"] == "available"
    # Do not allow installing while a running session cannot be stopped.
    monkeypatch.setattr(type(backend.engine), "running", property(lambda self: True))
    monkeypatch.setattr(backend.engine, "stop", lambda: None)
    res = backend.update_install()
    assert res["status"] == "error" and "Stop" in res["error"]
