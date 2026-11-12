"""Validate global hotkey wiring without importing Windows-only WinIO."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_windows_hotkeys_are_mapped_and_live_configurable():
    shell = (ROOT / "webapp.py").read_text(encoding="utf-8")
    io = (ROOT / "winio.py").read_text(encoding="utf-8")
    tree = ast.parse(io)
    assignment = next(n.value for n in tree.body
                      if isinstance(n, ast.Assign) and
                      any(isinstance(t, ast.Name) and t.id == "VK" for t in n.targets))
    assert isinstance(assignment, ast.DictComp)
    assert '{f"F{i}": 0x6F + i for i in range(1, 13)}' in io
    for key in ("F6", "F9", "F10"):
        assert f'"{key}": ' in shell
    assert "backend.cfg.afk_start_hotkey: backend.start" in shell
    assert "backend.cfg.afk_stop_hotkey: backend.stop" in shell
    assert '"F12": backend.stop' in shell
    assert "self.bindings() if callable(self.bindings)" in io


def test_release_and_installer_versions_match():
    version = (ROOT / "VERSION").read_text().strip()
    assert version == "1.4.0"
    assert f'#define AppVersion "{version}"' in (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert f'git tag v{version}' in (ROOT / "TAG_RELEASE.bat").read_text(encoding="utf-8")
