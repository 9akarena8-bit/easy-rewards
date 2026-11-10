"""Updater tests using local file:// URLs (https is enforced in real use)."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import updater  # noqa: E402

updater.ALLOWED_SCHEMES = {"https", "file"}


def _make_install(tmp: Path, version="1.0.0") -> Path:
    base = tmp / "inst"
    base.mkdir()
    (base / "app.py").write_text("old")
    (base / "VERSION").write_text(version + "\n")
    (base / "config.json").write_text('{"keep": true}')
    (base / "templates" / "ru").mkdir(parents=True)
    (base / "templates" / "ru" / "start_play.png").write_bytes(b"mine")
    return base


def _release(tmp: Path, version="1.0.1", app_body="new", tamper=False, evil=False) -> str:
    dist = tmp / "dist"
    dist.mkdir(exist_ok=True)
    z = dist / f"EasyRewards-{version}.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("EasyRewards/app.py", app_body)
        zf.writestr("EasyRewards/VERSION", version + "\n")
        zf.writestr("EasyRewards/config.json", '{"overwritten": true}')
        zf.writestr("EasyRewards/templates/ru/start_play.png", "overwritten")
        if evil:
            zf.writestr("../escape.txt", "x")
    sha = hashlib.sha256(z.read_bytes()).hexdigest()
    if tamper:
        sha = "0" * 64
    (dist / "version.json").write_text(json.dumps({"version": version, "zip": z.name, "sha256": sha}))
    return (dist / "version.json").as_uri()


def test_versions():
    assert updater.is_newer("1.0.1", "1.0.0") and updater.is_newer("1.10.0", "1.9.9")
    assert not updater.is_newer("1.0.0", "1.0.0") and not updater.is_newer("0.9", "1.0.0")


def test_update_replaces_code_keeps_user_data_and_backs_up():
    tmp = Path(tempfile.mkdtemp())
    base, url = _make_install(tmp), _release(tmp)
    version, manifest = updater.check(base, url)
    assert manifest and version == "1.0.1"
    assert updater.install(base, manifest) == "1.0.1"
    assert (base / "app.py").read_text() == "new"
    assert updater.local_version(base) == "1.0.1"
    assert (base / "config.json").read_text() == '{"keep": true}'
    assert (base / "templates" / "ru" / "start_play.png").read_bytes() == b"mine"
    assert (base / "_backup" / "1.0.0" / "app.py").read_text() == "old"
    assert updater.check(base, url)[1] is None  # now up to date


def test_bad_checksum_is_rejected_and_nothing_changes():
    tmp = Path(tempfile.mkdtemp())
    base, url = _make_install(tmp), _release(tmp, tamper=True)
    _, manifest = updater.check(base, url)
    try:
        updater.install(base, manifest)
        raise AssertionError("should have failed")
    except ValueError as e:
        assert "checksum" in str(e)
    assert (base / "app.py").read_text() == "old"


def test_zip_slip_is_rejected():
    tmp = Path(tempfile.mkdtemp())
    base, url = _make_install(tmp), _release(tmp, evil=True)
    _, manifest = updater.check(base, url)
    try:
        updater.install(base, manifest)
        raise AssertionError("should have failed")
    except ValueError as e:
        assert "unsafe" in str(e)
    assert (base / "app.py").read_text() == "old" and not (tmp / "escape.txt").exists()


def test_http_is_refused():
    updater.ALLOWED_SCHEMES = {"https"}
    try:
        try:
            updater.fetch_manifest("http://example.com/version.json")
            raise AssertionError("should have failed")
        except ValueError:
            pass
    finally:
        updater.ALLOWED_SCHEMES = {"https", "file"}


def test_make_release_roundtrip():
    tmp = Path(tempfile.mkdtemp())
    work = tmp / "src"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".venv", "dist", "__pycache__", "_backup"))
    (work / "templates" / "ru" / "start_secret.png").write_bytes(b"personal")
    (work / "config.json").write_text("{}")
    subprocess.run([sys.executable, str(work / "tools" / "make_release.py"), "2.0.0", "notes"], check=True,
                   capture_output=True)
    z = work / "dist" / "EasyRewards-2.0.0.zip"
    names = zipfile.ZipFile(z).namelist()
    assert "EasyRewards/app.py" in names and "EasyRewards/updater.py" in names
    assert not any("config.json" in n or "start_secret" in n or "dist/" in n for n in names)
    m = json.loads((work / "dist" / "version.json").read_text())
    assert m["version"] == "2.0.0" and m["sha256"] == hashlib.sha256(z.read_bytes()).hexdigest()


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)


def test_delta_update_downloads_only_changed_files():
    tmp = Path(tempfile.mkdtemp())
    work = tmp / "src"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".venv", "dist", "__pycache__", "_backup", "config.json"))
    mk = [sys.executable, str(work / "tools" / "make_release.py")]
    subprocess.run(mk + ["1.0.0"], check=True, capture_output=True)
    base = tmp / "inst"  # simulate a user who installed 1.0.0 from the zip
    with zipfile.ZipFile(work / "dist" / "EasyRewards-1.0.0.zip") as z:
        z.extractall(tmp / "x")
    shutil.copytree(tmp / "x" / "EasyRewards", base)
    (base / "config.json").write_text('{"keep": true}')
    (base / "templates" / "ru").mkdir(parents=True, exist_ok=True)
    (base / "templates" / "ru" / "start_play.png").write_bytes(b"mine")
    updater._write_record(base, [p.relative_to(base).as_posix() for p in base.rglob("*")
                                 if p.is_file() and p.relative_to(base).parts[0] not in updater.PRESERVE])

    with open(work / "i18n.py", "a", encoding="utf-8") as f:
        f.write("\n# changed\n")
    (work / "newfile.txt").write_text("hello")
    (work / "tools" / "make_logo.py").unlink()
    shutil.rmtree(work / "dist")
    subprocess.run(mk + ["1.0.1"], check=True, capture_output=True)
    url = (work / "dist" / "version.json").as_uri()

    fetched = []
    real_open = updater._open
    updater._open = lambda u: (fetched.append(u), real_open(u))[1]
    try:
        _, manifest = updater.check(base, url)
        assert manifest and set(updater.plan_delta(base, manifest)) == {"VERSION", "i18n.py", "newfile.txt"}
        assert updater.install(base, manifest) == "1.0.1"
    finally:
        updater._open = real_open
    names = sorted(Path(u).name for u in fetched)
    assert names == sorted(["version.json", "VERSION", "i18n.py", "newfile.txt"]), names  # no zip, no unchanged files
    assert manifest["stats"]["downloaded_files"] == 3 and manifest["stats"]["unchanged_files"] > 5
    assert (base / "newfile.txt").read_text() == "hello" and not (base / "tools" / "make_logo.py").exists()
    assert (base / "_backup" / "1.0.0" / "i18n.py").exists() and (base / "_backup" / "1.0.0" / "tools" / "make_logo.py").exists()
    assert (base / "config.json").read_text() == '{"keep": true}'
    assert (base / "templates" / "ru" / "start_play.png").read_bytes() == b"mine"
    assert updater.check(base, url)[1] is None


def test_delta_rejects_tampered_file_and_changes_nothing():
    tmp = Path(tempfile.mkdtemp())
    base = tmp / "inst"
    base.mkdir()
    (base / "app.py").write_text("old")
    (base / "VERSION").write_text("1.0.0\n")
    rel = tmp / "rel"
    (rel / "files").mkdir(parents=True)
    (rel / "files" / "app.py").write_text("evil")
    manifest = {"version": "1.0.1", "zip": "x.zip", "sha256": "0" * 64, "files_base": "files/",
                "files": {"app.py": {"sha256": hashlib.sha256(b"good").hexdigest(), "size": 4}}}
    (rel / "version.json").write_text(json.dumps(manifest))
    _, m = updater.check(base, (rel / "version.json").as_uri())
    try:
        updater.install(base, m)
        raise AssertionError("should have failed")
    except ValueError as e:
        assert "checksum" in str(e)
    assert (base / "app.py").read_text() == "old"


def test_delta_rejects_path_traversal_in_manifest():
    tmp = Path(tempfile.mkdtemp())
    rel = tmp / "rel"
    rel.mkdir()
    (rel / "version.json").write_text(json.dumps({
        "version": "9", "zip": "x.zip", "sha256": "0" * 64,
        "files": {"../evil.py": {"sha256": "0" * 64, "size": 1}}}))
    try:
        updater.fetch_manifest((rel / "version.json").as_uri())
        raise AssertionError("should have failed")
    except ValueError as e:
        assert "unsafe" in str(e)
