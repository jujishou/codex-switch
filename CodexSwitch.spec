# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — macOS .app bundle (onedir 模式,启动秒开)

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SRC = os.path.join(os.path.abspath(SPECPATH), 'src')
ICON = os.path.join(os.path.abspath(SPECPATH), 'assets', 'CodexSwitch.icns')

# customtkinter 自带主题 json + 字体,必须 collect-all
ctk_datas = collect_data_files('customtkinter')
ctk_hidden = collect_submodules('customtkinter')

a = Analysis(
    [os.path.join(SRC, 'gui_ctk.py')],
    pathex=[SRC],
    binaries=[],
    datas=ctk_datas,
    hiddenimports=['tomlkit', 'adapter', 'core', 'darkdetect'] + ctk_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# onedir 模式:EXE 不内嵌 binary/data,运行时直接读文件夹 → 秒开
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CodexSwitch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 把所有 binary + data 收到一个目录
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CodexSwitch',
)

app = BUNDLE(
    coll,
    name='CodexSwitch.app',
    icon=ICON,
    bundle_identifier='com.aliang.codexswitch',
    info_plist={
        'CFBundleName': 'CodexSwitch',
        'CFBundleDisplayName': 'CodexSwitch',
        'CFBundleShortVersionString': '1.1.0',
        'CFBundleVersion': '1.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        'LSUIElement': False,
        'NSHumanReadableCopyright': '跟着阿亮学AI — Local-only adapter for Codex.',
    },
)
