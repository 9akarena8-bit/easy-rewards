"""Offline regressions for the Windows release-installer cache (integration PR #37).

These tests intentionally never launch an executable, contact GitHub, or change
the Anti-AFK engine. They complement tests/test_github_releases.py.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

import release_updater as releases


def _meta(version: str, payload: bytes) -> dict:
    name = f"EasyRewards_Setup_{version}.exe"
    return {
        "version": version,
        "filename": name,
        "url": (
            "https://github.com/9akarena8-bit/easy-rewards/"
            f"releases/download/v{version}/{name}"
        ),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }


def test_interrupted_download_never_promotes_partial_installer(monkeypatch, tmp_path):
    payload = b"real EXE" * 40000
    meta = _meta("1.4.3", payload)
    cached = tmp_path / meta["filename"]
    cached.write_bytes(b"old unverified cache")
    pending = tmp_path / (meta["filename"] + ".download")

    class BrokenResponse(io.BytesIO):
        def __init__(self):
            super().__init__(payload)
            self.reads = 0

        def read(self, n=-1):
            self.reads += 1
            if self.reads > 1:
                raise ConnectionResetError("simulated network interruption")
            return super().read(n)

    monkeypatch.setattr(releases, "_urlopen", lambda url: BrokenResponse())
    with pytest.raises(ConnectionResetError, match="interruption"):
        releases.download_installer(meta, tmp_path)

    assert cached.read_bytes() == b"old unverified cache"
    assert not pending.exists()
    assert not releases.verify_installer(meta, cached)


def test_same_size_checksum_mismatch_does_not_replace_cache(monkeypatch, tmp_path):
    expected = b"trusted executable content"
    meta = _meta("1.4.3", expected)
    cached = tmp_path / meta["filename"]
    cached.write_bytes(b"old bad cache")
    pending = tmp_path / (meta["filename"] + ".download")
    tampered = b"!" * len(expected)
    monkeypatch.setattr(releases, "_urlopen", lambda url: io.BytesIO(tampered))

    with pytest.raises(ValueError, match="verification failed"):
        releases.download_installer(meta, tmp_path)

    assert cached.read_bytes() == b"old bad cache"
    assert not pending.exists()
    assert not releases.verify_installer(meta, cached)


def test_verified_cache_is_reused_without_network_access(monkeypatch, tmp_path):
    payload = b"already verified release"
    meta = _meta("1.4.3", payload)
    cached = tmp_path / meta["filename"]
    cached.write_bytes(payload)

    def unexpected_network(url):
        raise AssertionError("verified cache should not be downloaded again")

    monkeypatch.setattr(releases, "_urlopen", unexpected_network)
    assert releases.download_installer(meta, tmp_path) == cached
    assert cached.read_bytes() == payload


def test_corrupt_cache_is_replaced_only_after_verified_download(monkeypatch, tmp_path):
    payload = b"actual trusted release content"
    meta = _meta("1.4.3", payload)
    cached = tmp_path / meta["filename"]
    cached.write_bytes(b"?" * len(payload))
    monkeypatch.setattr(releases, "_urlopen", lambda url: io.BytesIO(payload))

    assert releases.download_installer(meta, tmp_path) == cached
    assert cached.read_bytes() == payload
    assert releases.verify_installer(meta, cached)
    assert not (tmp_path / (meta["filename"] + ".download")).exists()


def test_cache_cleanup_keeps_future_update_and_unrelated_files(monkeypatch, tmp_path):
    monkeypatch.setattr(releases.tempfile, "gettempdir", lambda: str(tmp_path))
    cache = tmp_path / "EasyRewards-Updates"
    cache.mkdir()
    old = cache / "EasyRewards_Setup_1.4.1.exe"
    current = cache / "EasyRewards_Setup_1.4.2.exe.download"
    future = cache / "EasyRewards_Setup_1.4.3.exe"
    unrelated = cache / "tester-notes.txt"
    for p in (old, current, future, unrelated):
        p.write_bytes(b"x")

    assert releases.cleanup_update_cache("1.4.2") == 2
    assert not old.exists() and not current.exists()
    assert future.exists() and unrelated.exists()
