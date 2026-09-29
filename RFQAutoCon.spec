# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for RFQ Auto Conditioning System
# 打包命令: pyinstaller RFQAutoCon.spec

from PyInstaller.utils.hooks import collect_all
import os
import re

# 从 rfq/__init__.py 读取版本号（不 import，避免拉起 epics 依赖）
# 版本号改这里：rfq/__init__.py 的 __version__
with open(os.path.join(SPECPATH, 'rfq', '__init__.py'), encoding='utf-8') as _f:
    __version__ = re.search(r"__version__\s*=\s*'([^']+)'", _f.read()).group(1)
print(f"[spec] RFQAutoCon version = {__version__}")

# 收集 pyepics 所有依赖（包含动态库）
epics_datas, epics_binaries, epics_hiddenimports = collect_all('epics')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=epics_binaries,
    datas=epics_datas,
    hiddenimports=epics_hiddenimports + [
        'rfq',
        'rfq.core',
        'rfq.core.config',
        'rfq.core.controller',
        'rfq.core.params',
        'rfq.core.pv_keys',
        'rfq.core.rf_manager',
        'rfq.core.state',
        'rfq.controllers',
        'rfq.controllers.fault',
        'rfq.controllers.power',
        'rfq.controllers.pulse',
        'rfq.controllers.vacuum',
        'rfq.utils',
        'rfq.utils.pv_manager',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'PIL',
        'IPython',
        'jupyter',
        'pytest',
    ],
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
    name=f'RFQAutoCon_v{__version__}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # 保留控制台窗口（命令行程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
