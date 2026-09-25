# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller hilmars_lostrommel.spec
# Onefile console exe. config/ is read next to the exe at runtime (see get_base_dir()),
# so it is copied into DISTPATH after the build instead of being bundled as datas.
import os
import shutil

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('readchar')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['hilmars_lostrommel.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', '_pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='hilmars_lostrommel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Refresh config/ next to the exe on every build so it never goes stale.
_config_dst = os.path.join(DISTPATH, 'config')
shutil.rmtree(_config_dst, ignore_errors=True)
shutil.copytree(os.path.join(SPECPATH, 'config'), _config_dst)
