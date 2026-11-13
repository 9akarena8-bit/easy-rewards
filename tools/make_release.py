"""Builds a release: dist/EasyRewards-<version>.zip + dist/version.json

    python tools/make_release.py 1.0.1 "What changed"

Upload the whole dist/ folder (version.json, the zip and files/) to one https folder, e.g. GitHub Pages,
and put the address of version.json into the app's Updates tab. Installed apps then download only the
files that changed.
"""
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "_backup", "dist", "build", "__pycache__", ".git",
             ".pytest_cache", "node_modules", "saved", "saved-data", "saved_data",
             "fpt-owner-licensing", "design-approved", "handoff"}
SKIP_FILES = {"config.json", "crash.log", "installed_files.json", "tracker.json", "tracker.bad",
              "offline-license.json", "installation-id.txt", "payment_interest_drafts.json"}


def release_files(base: Path):
    """Prune local profiles and owner data before traversal, not just before zipping."""
    for directory, folders, names in os.walk(base, followlinks=False):
        folders[:] = sorted(name for name in folders
                            if name.lower() not in SKIP_DIRS
                            and not name.lower().startswith(("edge-", "owner-", "."))
                            and not (Path(directory) / name).is_symlink()
                            and not (Path(directory) == base and name == "EasyRewards"))
        for name in sorted(names):
            p = Path(directory) / name
            rel = p.relative_to(base)
            lower = name.lower()
            if (p.is_symlink() or lower in SKIP_FILES or lower.startswith((".env", "visual-"))
                    or p.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".key", ".pfx", ".p12", ".spec", ".log"}
                    or (p.suffix.lower() == ".pem" and rel.as_posix() != "assets/license-public.pem")
                    or (rel.parts[0] == "templates" and name != ".keep")):
                continue
            yield p, rel


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else (BASE / "VERSION").read_text().strip()
    notes = sys.argv[2] if len(sys.argv) > 2 else ""
    (BASE / "VERSION").write_text(version + "\n", encoding="utf-8")
    dist = BASE / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"EasyRewards-{version}.zip"
    files_dir = dist / "files"
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p, rel in release_files(BASE):
            z.write(p, Path("EasyRewards") / rel)
            (files_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, files_dir / rel)
            files[rel.as_posix()] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size}
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (dist / "version.json").write_text(
        json.dumps({"version": version, "zip": zip_path.name, "sha256": sha, "notes": notes,
                    "files_base": "files/", "files": files}, indent=2),
        encoding="utf-8")
    print(f"Built {zip_path.name}  sha256={sha}")


if __name__ == "__main__":
    main()
