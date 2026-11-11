"""Regression tests for the 1.3.5 UI stability and release integration."""
from __future__ import annotations

import json
from pathlib import Path

import release_updater
from backend import Backend

ROOT = Path(__file__).resolve().parents[1]


class IO:
    def game_in_foreground(self):
        return False
    def foreground_title(self):
        return "Desktop"


def test_ui_avoids_periodic_full_rebuild_and_preserves_scroll():
    js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    assert "runtime: undefined" in js
    assert "pointerIsDown" in js
    assert "if (!force && pointerIsDown) return;" in js
    assert "newScroll.scrollTop = oldScroll" in js
    assert "refreshLiveMetrics" in js
    gold = (ROOT / "ui" / "gold_ui.js").read_text(encoding="utf-8")
    assert "savedNavScroll" in gold
    assert "release_news" in gold
    assert 'data-act="stop"' in gold
    assert 'data-act="main"' in gold


def test_news_parses_only_valid_published_releases(monkeypatch):
    docs = [
        {"tag_name": "v1.3.5", "body": "Новый UI", "draft": False},
        {"tag_name": "v1.3.4", "body": "Fix", "prerelease": False},
        {"tag_name": "v1.3.7", "draft": True},
        {"tag_name": "beta", "body": "skip"},
    ]
    monkeypatch.setattr(release_updater, "_read_limited", lambda url, cap: json.dumps(docs).encode("utf-8"))
    result = release_updater.release_news()
    assert [r["version"] for r in result] == ["1.3.5", "1.3.4"]
    assert result[0]["notes"] == "Новый UI"


def test_backend_release_news_keeps_cache_on_network_error(monkeypatch, tmp_path):
    b = Backend(tmp_path, IO())
    b.release_mode = True
    monkeypatch.setattr(release_updater, "release_news", lambda: [{"version": "1.3.5", "title": "Test", "notes": "ready"}])
    assert b.refresh_release_news()[0]["version"] == "1.3.5"
    assert b.state()["release_news"][0]["notes"] == "ready"
    def fail():
        raise OSError("offline")
    monkeypatch.setattr(release_updater, "release_news", fail)
    assert b.refresh_release_news()[0]["version"] == "1.3.5"


def test_quiet_installer_only_launches_after_explicit_call(monkeypatch, tmp_path):
    install = tmp_path / "EasyRewards_Setup_1.3.5.exe"
    install.write_bytes(b"mock installer")
    launched = []
    monkeypatch.setattr(release_updater.subprocess, "Popen", lambda command, **kw: launched.append(command))
    assert not launched
    release_updater.launch_installer(install)
    assert len(launched) == 1
    assert "/VERYSILENT" in launched[0]
    assert "/LANG=russian" in launched[0]
    assert "/NORESTART" in launched[0]


def test_cleanup_only_removes_downloads_up_to_current_version(monkeypatch, tmp_path):
    monkeypatch.setattr(release_updater.tempfile, "gettempdir", lambda: str(tmp_path))
    folder = tmp_path / "EasyRewards-Updates"
    folder.mkdir()
    for name in ("EasyRewards_Setup_1.3.3.exe", "EasyRewards_Setup_1.3.5.exe",
                 "EasyRewards_Setup_1.3.6.exe", "randomfile.exe"):
        (folder / name).write_bytes(b"old")
    assert release_updater.cleanup_update_cache("1.3.5") == 2
    assert not (folder / "EasyRewards_Setup_1.3.5.exe").exists()
    assert (folder / "EasyRewards_Setup_1.3.6.exe").exists()
    assert (folder / "randomfile.exe").exists()


def test_installer_version_and_publish_scripts_consistent():
    version = (ROOT / "VERSION").read_text().strip()
    assert version == "1.3.5"
    assert f'#define AppVersion "{version}"' in (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert f"v{version}" in (ROOT / "TAG_RELEASE.bat").read_text(encoding="utf-8")
    assert "Flags: nowait" in (ROOT / "installer.iss").read_text(encoding="utf-8")
