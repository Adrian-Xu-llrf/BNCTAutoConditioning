# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for RFQ Auto Conditioning System
# 打包命令: pyinstaller RFQAutoCon.spec

from PyInstaller.utils.hooks import collect_all

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
    name='RFQAutoCon',
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
