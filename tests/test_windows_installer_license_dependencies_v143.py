"""Static regressions for Windows installer dependency and version contracts.

These checks do not replace an actual Windows PyInstaller/Inno Setup run.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_build_installs_optional_offline_license_deps_before_pyinstaller():
    script = (ROOT / "BUILD_INSTALLER.bat").read_text(encoding="utf-8")
    guard = 'if exist "merchant_service\\requirements-offline.txt" ('
    install = '-r "merchant_service\\requirements-offline.txt"'
    build = 'echo [1/2] Building Windows executable...'

    assert guard in script, "clean builds must install offline license dependencies"
    assert script.index(guard) < script.index(install) < script.index(build)
    conditional = script.split(guard, 1)[1].split("\n)", 1)[0]
    assert "if errorlevel 1 goto error" in conditional


def test_ready_message_uses_inno_setup_version():
    batch = (ROOT / "BUILD_INSTALLER.bat").read_text(encoding="utf-8")
    installer = (ROOT / "installer.iss").read_text(encoding="utf-8")
    version = re.search(r'^#define AppVersion "([^"]+)"$', installer, flags=re.MULTILINE)
    assert version is not None
    assert f"EasyRewards_Setup_{version.group(1)}.exe" in batch
