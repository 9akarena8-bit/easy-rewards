# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('webview')

root = Path(SPECPATH)
ui_files = (
    'index.html', 'app.js', 'gold_ui.js', 'skinpay.js',
    'style.css', 'gold_ui.css', 'approved_v2.css', 'skinpay.css',
    'design-home-art.png', 'design-reference-home.jpg',
    'design-reference-settings.jpg', 'design-reference-support.jpg',
    'pirate-home.webp', 'pirate_token.png', 'logo.png', 'logo_gold.svg',
    'pirate_seascape.svg', 'hero_chest.svg',
)
asset_files = ('icon.ico', 'logo_44.png', 'logo_88.png', 'logo_256.png')
datas = [(str(root / 'ui' / name), 'ui') for name in ui_files]
datas += [(str(root / 'assets' / name), 'assets') for name in asset_files]
datas.append((str(root / 'VERSION'), '.'))
datas += [(str(root / 'locales' / f'{lang}.json'), 'locales')
          for lang in ('fr', 'pl', 'ar')]
datas += [(str(root / 'locales' / f'ui_{lang}.json'), 'locales')
          for lang in ('en', 'ru', 'uk', 'fr', 'pl', 'ar')]
public_key = root / 'assets' / 'license-public.pem'
if public_key.is_file():
    datas.append((str(public_key), 'assets'))


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['owner_access', 'merchant_service.owner_license', 'merchant_service.private_demo'],
    noarchive=False,
    optimize=0,
)
# The launcher captures screenshots with Pillow and uses OpenCV only for image
# matching/encoding. No runtime code opens video streams, so ship no FFmpeg DLL.
a.binaries = [item for item in a.binaries
              if "opencv_videoio_ffmpeg" not in str(item[0]).lower()]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EasyRewards',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EasyRewards',
)
