# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller hilmars_lostrommel.spec
# Onefile console exe. config/ is read next to the exe at runtime (see get_base_dir()),
# so config.ini is copied next to the exe after the build instead of being bundled as datas.
import os
import shutil
import sys

from PyInstaller.utils.hooks import collect_all

# Put the version into the exe name (e.g. hilmars_lostrommel_v1.2.1.exe);
# core/version.py stays the single source of truth.
sys.path.insert(0, SPECPATH)
from core.version import __version__

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
    name=f'hilmars_lostrommel_v{__version__}',
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

# Ship everything in a versioned folder: dist/hilmars_lostrommel_v<version>/
# holds the exe and config/config.ini. The folder is rebuilt on every build so
# neither the exe nor the config ever goes stale. Only config.ini is shipped;
# the template and local variants (config_backup.ini, ...) stay in the repo.
# The exe is moved aside first: without the .exe suffix (non-Windows builds)
# it has the same path as the folder that is about to be created.
_release_dir = os.path.join(DISTPATH, f'hilmars_lostrommel_v{__version__}')
_exe_file = os.path.basename(exe.name)
_staged_exe = exe.name + '.staged'
os.replace(exe.name, _staged_exe)
shutil.rmtree(_release_dir, ignore_errors=True)
os.makedirs(os.path.join(_release_dir, 'config'))
os.replace(_staged_exe, os.path.join(_release_dir, _exe_file))
shutil.copy2(
    os.path.join(SPECPATH, 'config', 'config.ini'),
    os.path.join(_release_dir, 'config', 'config.ini'),
)
