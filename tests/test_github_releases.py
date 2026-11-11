"""Offline tests: release metadata, integrity, and integration with installed mode."""
import hashlib
import io
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_updater as r
from backend import Backend


class NoGame:
    def game_in_foreground(self):
        return False
    def foreground_title(self):
        return 'Desktop'


def fake_release(version, payload):
    filename = f'EasyRewards_Setup_{version}.exe'
    h = hashlib.sha256(payload).hexdigest()
    assets = [dict(name=filename, size=len(payload), browser_download_url=f'https://github.com/9akarena8-bit/easy-rewards/releases/download/v{version}/{filename}'),
              dict(name=filename+'.sha256', browser_download_url=f'https://github.com/9akarena8-bit/easy-rewards/releases/download/v{version}/{filename}.sha256')]
    return dict(tag_name='v'+version, assets=assets, draft=False, prerelease=False), h


def test_release_fetch_metadata_offline(monkeypatch):
    payload=b'installer content for test'
    release, digest = fake_release('1.2.5', payload)
    def read(url, limit):
        return json.dumps(release).encode() if url == r.RELEASE_API else (digest + '  EasyRewards_Setup_1.2.5.exe').encode()
    monkeypatch.setattr(r, '_read_limited', read)
    meta=r.latest_release('1.2.4')
    assert meta['version']=='1.2.5' and meta['sha256']==digest
    assert r.latest_release('1.2.5') is None


def test_tampered_checksum_is_rejected(monkeypatch, tmp_path):
    payload=b'executable'
    release, digest=fake_release('1.2.5',payload)
    monkeypatch.setattr(r,'_read_limited', lambda url, limit: json.dumps(release).encode() if url==r.RELEASE_API else (digest+'  EasyRewards_Setup_1.2.5.exe').encode())
    meta=r.latest_release('1.2.4')
    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    monkeypatch.setattr(r,'_urlopen',lambda u: Resp(b'different content!'))
    with pytest.raises(ValueError,match='verification failed'):
        r.download_installer(meta, tmp_path)
    assert not list(tmp_path.glob('*.exe'))


def test_release_install_requires_verification_and_click(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'latest_release',lambda v: dict(version='1.2.5',filename='EasyRewards_Setup_1.2.5.exe',url='https://github.com/9akarena8-bit/easy-rewards/releases/download/v1.2.5/EasyRewards_Setup_1.2.5.exe',sha256='a'*64,size=9))
    monkeypatch.setattr(r,'download_installer',lambda meta:tmp_path/'EasyRewards_Setup_1.2.5.exe')
    opened=[]
    monkeypatch.setattr(r,'launch_installer',lambda path:opened.append(path))
    backend=Backend(tmp_path, NoGame())
    backend.release_mode=True
    backend.version='1.2.4'
    assert backend.state()['release_mode'] is True
    assert backend.update_install()['status']=='error'  # no update selected
    assert backend.update_check()['status']=='available'
    assert not opened  # checking does NOT install
    assert backend.update_install()['status']=='installer_started'
    assert opened and opened[0].name=='EasyRewards_Setup_1.2.5.exe'


def test_bad_release_host_is_rejected():
    assert not r._is_official_asset_url('https://malicious.example.com/9akarena8-bit/easy-rewards/releases/download/v1.2.5/x.exe')
    assert not r._is_official_asset_url('http://github.com/9akarena8-bit/easy-rewards/releases/download/v1.2.5/x.exe')
