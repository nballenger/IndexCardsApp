# -*- mode: python ; coding: utf-8 -*-
#
# Builds the macOS IndexCards.app bundle. Checked in (unlike build/ and
# dist/, which are gitignored output directories) so a release build is
# reproducible via `uv run pyinstaller IndexCards.spec` rather than having
# to reconstruct the CLI flags this was originally generated from. Rerun
# `uv run pyinstaller IndexCards.spec` after changing this file or bumping
# the version in pyproject.toml; regenerate the icon itself via
# resources/icons/generate_app_icon.py + resources/icons/build_icns.sh.

import tomllib

with open("pyproject.toml", "rb") as f:
    _version = tomllib.load(f)["project"]["version"]

a = Analysis(
    ['src/indexcards/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IndexCards',
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
    icon=['resources/icons/AppIcon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IndexCards',
)
app = BUNDLE(
    coll,
    name='IndexCards.app',
    icon='resources/icons/AppIcon.icns',
    bundle_identifier='com.nballenger.indexcards',
    info_plist={
        'CFBundleShortVersionString': _version,
        'CFBundleVersion': _version,
        'NSHumanReadableCopyright': 'Nick Ballenger',
    },
)
