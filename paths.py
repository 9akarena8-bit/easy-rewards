"""Separate packaged assets from writable user data."""
from pathlib import Path
import os
import sys


def resources() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def data() -> Path:
    if getattr(sys, "frozen", False):
        folder = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "EasyRewards"
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    return resources()
