# -*- mode: python ; coding: utf-8 -*-

# 该 spec 是唯一打包入口（build.py 通过 PyInstaller 调用本文件）。
# 模式由环境变量控制：
#   BTK_BUILD_MODE=onefile  → 便携版单文件（exe 内嵌全部二进制）
#   BTK_BUILD_MODE=onedir   → 安装版目录（默认，启动无需解压）
import os

# 排除清单与 build.py 共用同一份（见 build_excludes.py 里的用途说明）
from build_excludes import EXCLUDES, _strip_binaries, dedupe

BUILD_MODE = os.environ.get("BTK_BUILD_MODE", "onedir")
ONEFILE = BUILD_MODE == "onefile"


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('presets', 'presets'),
        ('app/resources', 'app/resources'),
        ('app/qml/Main.qml', 'app/qml'),
        ('app/qml/components', 'app/qml/components'),
        ('app/qml/icons', 'app/qml/icons'),
        ('app/qml/assets', 'app/qml/assets'),
    ],
    hiddenimports=[
        'PySide6',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickControls2',
        'PySide6.QtWidgets',
        'PIL',
        'pyvips',
        'app.workers.export_worker',
        'cv2',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=dedupe(EXCLUDES),
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# 剔除用不到的 Qt 原生库与 cv2 视频解码器。
# spec 没有 `--exclude-binary` 的等价参数，只能在 Analysis 之后过滤；过滤
# 规则集中在 build_excludes._strip_binaries，与命令行路径共用同一份。
a.binaries = _strip_binaries(a.binaries)

# onefile 模式下把 binaries/datas 塞进 exe；onedir 模式交给 COLLECT
_extra = (a.binaries + a.datas) if ONEFILE else []

exe = EXE(
    pyz,
    a.scripts,
    _extra,
    [],
    name='批图王',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['app\\resources\\app_icon.ico'],
    exclude_binaries=not ONEFILE,
)

if ONEFILE:
    # 单文件模式不需要 COLLECT
    pass
else:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='批图王',
    )
