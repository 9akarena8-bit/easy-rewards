"""GitHub Releases-based installer updater for the Windows application.

Only this project's official, public GitHub release installer is accepted.
The companion SHA-256 asset detects corruption before an installer is launched.
No silent execution, token, third-party mirror, or arbitrary remote command.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from updater import is_newer

REPOSITORY = "9akarena8-bit/easy-rewards"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
SETUP_PREFIX = "EasyRewards_Setup_"
MAX_SETUP_BYTES = 450 * 1024 * 1024
TIMEOUT_SECONDS = 25


def _urlopen(url: str):
    # Both /releases/latest and /releases?per_page=N return JSON. Sending
    # application/octet-stream to the release feed causes HTTP 415.
    parsed = urlparse(url)
    is_release_api = (parsed.scheme == "https"
                      and parsed.hostname == "api.github.com"
                      and parsed.path.startswith(f"/repos/{REPOSITORY}/releases"))
    headers = {
        "User-Agent": "EasyRewards-ReleaseUpdater/1.3.6",
        "Accept": "application/vnd.github+json" if is_release_api else "application/octet-stream",
    }
    if is_release_api:
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return urlopen(Request(url, headers=headers), timeout=TIMEOUT_SECONDS)


def _read_limited(url: str, limit: int) -> bytes:
    with _urlopen(url) as response:
        chunk = response.read(limit + 1)
    if len(chunk) > limit:
        raise ValueError("GitHub response is too large")
    return chunk


def _is_official_asset_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname == "github.com"
            and parsed.path.startswith(f"/{REPOSITORY}/releases/download/"))


def _read_sha256(data: bytes, filename: str) -> str:
    text = data.decode("utf-8-sig").strip()
    # GitHub Actions creates: "<hash>  <installer filename>".
    match = re.fullmatch(r"([a-fA-F0-9]{64})(?:\s+\*?(.+))?", text)
    if not match:
        raise ValueError("Invalid SHA-256 checksum in release")
    if match.group(2) and Path(match.group(2)).name != filename:
        raise ValueError("SHA-256 checksum belongs to another file")
    return match.group(1).lower()


def latest_release(current_version: str) -> dict | None:
    """Return safe metadata for a newer official release, or None if up-to-date."""
    raw = json.loads(_read_limited(RELEASE_API, 1_000_000).decode("utf-8"))
    if raw.get("draft") or raw.get("prerelease"):
        return None
    tag = str(raw.get("tag_name") or "").removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", tag):
        raise ValueError("Unsupported GitHub release version")
    if not is_newer(tag, current_version):
        return None
    filename = f"{SETUP_PREFIX}{tag}.exe"
    assets = {asset.get("name"): asset for asset in raw.get("assets", []) if isinstance(asset, dict)}
    setup = assets.get(filename)
    checksum = assets.get(filename + ".sha256")
    if not setup or not checksum:
        raise ValueError("Release does not include the installer and its checksum")
    setup_url = setup.get("browser_download_url", "")
    checksum_url = checksum.get("browser_download_url", "")
    if not _is_official_asset_url(setup_url) or not _is_official_asset_url(checksum_url):
        raise ValueError("Untrusted GitHub release asset address")
    size = int(setup.get("size") or 0)
    if size < 1 or size > MAX_SETUP_BYTES:
        raise ValueError("Unexpected installer size")
    expected_hash = _read_sha256(_read_limited(checksum_url, 256), filename)
    return {"version": tag, "url": setup_url, "filename": filename,
            "sha256": expected_hash, "size": size,
            "notes": str(raw.get("body") or "")[:1200]}


def verify_installer(meta: dict, path: Path) -> bool:
    """Validate the exact downloaded artifact against the release manifest."""
    try:
        p = Path(path)
        if p.name != meta["filename"] or p.stat().st_size != int(meta["size"]):
            return False
        digest = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == meta["sha256"]
    except (OSError, KeyError, TypeError, ValueError):
        return False


def download_installer(meta: dict, directory: Path | None = None) -> Path:
    """Download and verify the EXE before it can be launched."""
    version = str(meta["version"])
    expected_name = f"{SETUP_PREFIX}{version}.exe"
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid installer version")
    if meta.get("filename") != expected_name or not _is_official_asset_url(meta.get("url", "")):
        raise ValueError("Invalid installer metadata")
    if not re.fullmatch(r"[a-f0-9]{64}", str(meta.get("sha256", ""))):
        raise ValueError("Invalid installer checksum")
    size_expected = int(meta.get("size") or 0)
    if size_expected < 1 or size_expected > MAX_SETUP_BYTES:
        raise ValueError("Invalid installer size")
    folder = (Path(directory) if directory is not None else Path(tempfile.gettempdir()) / "EasyRewards-Updates")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / expected_name
    pending = folder / (expected_name + ".download")
    if verify_installer(meta, target):
        return target
    digest = hashlib.sha256()
    total = 0
    try:
        with _urlopen(meta["url"]) as src, pending.open("wb") as out:
            while True:
                block = src.read(128 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_SETUP_BYTES:
                    raise ValueError("Installer exceeds maximum size")
                digest.update(block)
                out.write(block)
        if total != size_expected or digest.hexdigest() != meta["sha256"]:
            raise ValueError("Installer size or SHA-256 verification failed")
        pending.replace(target)
        return target
    finally:
        pending.unlink(missing_ok=True)


def release_news(limit: int = 7) -> list[dict]:
    """Fetch recent published GitHub release notes, including beta patches.

    No HTML or executable code from the release is trusted. The UI escapes text.
    """
    url = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page={min(max(1,limit),10)}"
    data = json.loads(_read_limited(url, 1_000_000).decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Invalid release feed")
    items = []
    for rel in data:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        version = str(rel.get("tag_name") or "").removeprefix("v")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            continue
        notes = str(rel.get("body") or "").strip()
        # GitHub auto-generated notes can include verbose markdown and links.
        # Show the latest excerpt; no marketing claims about new features.
        items.append({"version": version,
                      "title": f"Fortnite Pirate Token v{version}" + (" Beta" if rel.get("prerelease") else ""),
                      "published_at": str(rel.get("published_at") or ""),
                      "prerelease": bool(rel.get("prerelease")),
                      "notes": notes[:12000] or "Опубликована новая версия Fortnite Pirate Token."})
    return items


def cleanup_update_cache(current_version: str) -> int:
    """Remove obsolete verified setup downloads after launching an updated version.

    Never delete a newer installer that may still be waiting to install.
    """
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(current_version)):
        return 0
    folder = Path(tempfile.gettempdir()) / "EasyRewards-Updates"
    if not folder.is_dir():
        return 0
    removed = 0
    from updater import is_newer
    for p in folder.iterdir():
        match = re.fullmatch(r"EasyRewards_Setup_(\d+\.\d+\.\d+)\.exe(?:\.download)?", p.name)
        if match and p.is_file() and not is_newer(match.group(1), current_version):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass  # Installer still executing or locked; next launch can retry.
    return removed


def launch_installer(path: Path, language: str = "ru") -> None:
    """Install the *already verified* release after explicit user confirmation.

    Inno Setup quiet mode reuses its AppId and install directory, does not
    prompt for a language on every update and never erases the user data dir.
    Full installer is still downloaded; delta patching needs a future format.
    """
    path = Path(path).resolve()
    if not path.is_file() or not re.fullmatch(r"EasyRewards_Setup_\d+\.\d+\.\d+\.exe", path.name):
        raise ValueError("Not a downloaded Easy Rewards installer")
    lang = "russian" if language == "ru" else "english"
    command = [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
               "/CLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", f"/LANG={lang}"]
    subprocess.Popen(command, close_fds=True)
