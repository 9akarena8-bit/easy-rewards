"""Check non-Windows source consistency before distributing Windows builds."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_hotkeys_have_vk_mappings():
    webapp = (ROOT / "webapp.py").read_text(encoding="utf-8")
    io_tree = ast.parse((ROOT / "winio.py").read_text(encoding="utf-8"))
    vk = next(node.value for node in io_tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "VK" for target in node.targets))
    mapped = ast.literal_eval(vk)
    for key in ("F6", "F7", "F8", "F9", "F10"):
        assert f'"{key}": ' in webapp
        assert key in mapped


def test_release_and_installer_versions_match():
    version = (ROOT / "VERSION").read_text().strip()
    assert version == "1.3.5"
    assert f'#define AppVersion "{version}"' in (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert f'git tag v{version}' in (ROOT / "TAG_RELEASE.bat").read_text(encoding="utf-8")
