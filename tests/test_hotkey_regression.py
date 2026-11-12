"""Source consistency checks for dynamically remappable Windows hotkeys."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_hotkeys_have_vk_mappings():
    webapp = (ROOT / "webapp.py").read_text(encoding="utf-8")
    io_source = (ROOT / "winio.py").read_text(encoding="utf-8")
    tree = ast.parse(io_source)
    vk = next(node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "VK" for target in node.targets))
    assert isinstance(vk, (ast.Dict, ast.DictComp))
    assert 'range(1, 13)' in io_source
    assert "def set_bindings(" in io_source
    assert '"F6": backend.engine.input_probe' in webapp
    assert '"F9": backend.hotkey_count' in webapp
    for action in ("start", "stop", "pause"):
        assert f"backend.cfg.hotkey_{action}: backend.{action}" in webapp


def test_release_and_installer_versions_match():
    version = (ROOT / "VERSION").read_text().strip()
    assert version == "1.3.9"
    assert f'#define AppVersion "{version}"' in (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert f'git tag v{version}' in (ROOT / "TAG_RELEASE.bat").read_text(encoding="utf-8")
