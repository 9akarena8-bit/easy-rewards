"""Self-updater.

The app downloads a small manifest (version.json) from an address you control:

    {"version": "1.0.1", "zip": "EasyRewards-1.0.1.zip", "sha256": "<hex>", "notes": "..."}

If the version is newer, the zip is downloaded, its SHA-256 is verified, and the program files are
replaced. Your config.json and templates/ are never touched, and every replaced file is copied to
_backup/<old version>/ first.  Only https:// addresses are accepted.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urljoin, urlparse

PRESERVE = {"config.json", "templates", ".venv", "_backup", "crash.log", "__pycache__", "dist",
            "installed_files.json", "tracker.json"}
TIMEOUT = 20
MAX_ZIP = 100 * 1024 * 1024
ALLOWED_SCHEMES = {"https"}  # tests add "file"


def local_version(base: Path) -> str:
    try:
        return (Path(base) / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _parse(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) or (0,)


def is_newer(remote: str, local: str) -> bool:
    return _parse(remote) > _parse(local)


def _open(url: str):
    if urlparse(url).scheme not in ALLOWED_SCHEMES:
        raise ValueError("update address must start with https://")
    req = urllib.request.Request(url, headers={"User-Agent": "EasyRewards-updater"})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def fetch_manifest(url: str) -> dict:
    with _open(url) as r:
        data = json.loads(r.read(1_000_000).decode("utf-8"))
    for key in ("version", "zip", "sha256"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValueError(f"manifest is missing '{key}'")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", data["sha256"]):
        raise ValueError("manifest sha256 is not valid")
    data["zip"] = urljoin(url, data["zip"])
    data["base"] = url
    files = data.get("files")
    if files is not None:  # delta mode: {"relative/path": {"sha256": ..., "size": ...}}
        if not isinstance(files, dict) or not files:
            raise ValueError("manifest 'files' is not valid")
        for rel, meta in files.items():
            _safe_rel(rel)
            if not isinstance(meta, dict) or not re.fullmatch(r"[0-9a-fA-F]{64}", str(meta.get("sha256", ""))):
                raise ValueError(f"manifest checksum for {rel} is not valid")
    return data


def check(base: Path, url: str) -> tuple[str, dict | None]:
    """Return (remote_version, manifest) - manifest is None when already up to date."""
    manifest = fetch_manifest(url)
    if is_newer(manifest["version"], local_version(base)):
        return manifest["version"], manifest
    return manifest["version"], None


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if dest != target and dest not in target.parents:
            raise ValueError("unsafe path in update package")
    zf.extractall(dest)


def _safe_rel(rel: str) -> PurePosixPath:
    p = PurePosixPath(rel)
    if p.is_absolute() or not p.parts or ".." in p.parts or "\\" in rel or ":" in rel:
        raise ValueError(f"unsafe path in manifest: {rel}")
    return p


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _record_path(base: Path) -> Path:
    return Path(base) / "installed_files.json"


def _read_record(base: Path) -> list[str]:
    try:
        return list(json.loads(_record_path(base).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def _write_record(base: Path, rels) -> None:
    _record_path(base).write_text(json.dumps(sorted(rels)), encoding="utf-8")


def _backup(base: Path, rel: PurePosixPath, backup: Path) -> None:
    src = Path(base, *rel.parts)
    if src.exists():
        dst = Path(backup, *rel.parts)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def plan_delta(base: Path, manifest: dict) -> list[str]:
    """Files that are missing or different on disk (what a delta update would download)."""
    todo = []
    for rel, meta in manifest["files"].items():
        parts = _safe_rel(rel).parts
        if parts[0] in PRESERVE:
            continue
        dest = Path(base, *parts)
        if not dest.is_file() or _sha_file(dest) != meta["sha256"].lower():
            todo.append(rel)
    return todo


def install_delta(base: Path, manifest: dict) -> str:
    """Download only the files that changed, verify each one, then swap them in."""
    base = Path(base)
    todo = plan_delta(base, manifest)
    tmp = Path(tempfile.mkdtemp(prefix="easy_rewards_delta_"))
    downloaded = 0
    try:
        root_url = urljoin(manifest["base"], manifest.get("files_base", "files/"))
        for rel in todo:
            p = _safe_rel(rel)
            target = tmp.joinpath(*p.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, total = hashlib.sha256(), 0
            with _open(urljoin(root_url, quote(p.as_posix()))) as r, open(target, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ZIP:
                        raise ValueError("file is too large")
                    digest.update(chunk)
                    f.write(chunk)
            if digest.hexdigest() != manifest["files"][rel]["sha256"].lower():
                raise ValueError(f"checksum mismatch for {rel} - update rejected")
            downloaded += total

        backup = base / "_backup" / local_version(base)
        for rel in todo:  # everything verified - now apply
            p = _safe_rel(rel)
            _backup(base, p, backup)
            dest = Path(base, *p.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp.joinpath(*p.parts), dest)

        new = {r for r in manifest["files"] if _safe_rel(r).parts[0] not in PRESERVE}
        for rel in _read_record(base):  # files that existed in the old release but not in the new one
            if rel not in new and _safe_rel(rel).parts[0] not in PRESERVE:
                _backup(base, _safe_rel(rel), backup)
                Path(base, *_safe_rel(rel).parts).unlink(missing_ok=True)
        _write_record(base, new)
        manifest["stats"] = {"downloaded_files": len(todo), "downloaded_bytes": downloaded,
                             "unchanged_files": len(new) - len(todo)}
        return manifest["version"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def install(base: Path, manifest: dict) -> str:
    """Download, verify and apply an update. Returns the installed version.

    Uses the per-file (delta) manifest when the release has one, otherwise the full zip."""
    if manifest.get("files"):
        return install_delta(base, manifest)
    base = Path(base)
    tmp = Path(tempfile.mkdtemp(prefix="easy_rewards_update_"))
    try:
        zpath = tmp / "update.zip"
        digest, total = hashlib.sha256(), 0
        with _open(manifest["zip"]) as r, open(zpath, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ZIP:
                    raise ValueError("update package is too large")
                digest.update(chunk)
                f.write(chunk)
        if digest.hexdigest().lower() != manifest["sha256"].lower():
            raise ValueError("checksum mismatch - update rejected")

        extracted = tmp / "x"
        with zipfile.ZipFile(zpath) as zf:
            _safe_extract(zf, extracted)
        root = extracted
        entries = list(extracted.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]
        if not (root / "app.py").exists():
            raise ValueError("package does not look like Easy Rewards")

        backup = base / "_backup" / local_version(base)
        for item in root.iterdir():
            if item.name in PRESERVE:
                continue
            dest = base / item.name
            if dest.exists():
                bdest = backup / item.name
                bdest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_dir():
                    shutil.copytree(dest, bdest, dirs_exist_ok=True)
                else:
                    shutil.copy2(dest, bdest)
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        _write_record(base, [p.relative_to(root).as_posix() for p in root.rglob("*")
                             if p.is_file() and p.relative_to(root).parts[0] not in PRESERVE])
        version_file = root / "VERSION"
        return version_file.read_text(encoding="utf-8").strip() if version_file.exists() else manifest["version"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
