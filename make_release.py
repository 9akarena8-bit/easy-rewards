"""Builds a release: dist/EasyRewards-<version>.zip + dist/version.json

    python tools/make_release.py 1.0.1 "What changed"

Upload the whole dist/ folder (version.json, the zip and files/) to one https folder, e.g. GitHub Pages,
and put the address of version.json into the app's Updates tab. Installed apps then download only the
files that changed.
"""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "_backup", "dist", "__pycache__", ".git"}
SKIP_FILES = {"config.json", "crash.log", "installed_files.json", "tracker.json", "tracker.bad"}


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
        for p in sorted(BASE.rglob("*")):
            rel = p.relative_to(BASE)
            if p.is_dir() or SKIP_DIRS & set(rel.parts) or p.name in SKIP_FILES:
                continue
            if rel.parts[0] == "templates" and p.name != ".keep":
                continue  # never ship personal templates
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
