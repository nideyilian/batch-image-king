# -*- mode: python ; coding: utf-8 -*-


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
        'scipy',
    ],
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
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='批图王',
)
