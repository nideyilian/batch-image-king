from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
APP_NAME = "批图王"
GITHUB_REPO = "nideyilian/batch-image-king"
NSIS_EXE_CANDIDATES = [
    r"C:\Program Files (x86)\NSIS\makensis.exe",
    r"C:\Program Files\NSIS\makensis.exe",
]


def get_version() -> str:
    """从 app/version.py 读取版本号（唯一版本来源）。"""
    version = ""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from app.version import APP_VERSION
        version = str(APP_VERSION or "").strip()
    except Exception as e:
        print(f"Warning: 无法读取 app/version.py: {e}")
    if not re.match(r"^\d+\.\d+(\.\d+)*$", version):
        print("Error: app/version.py 中的 APP_VERSION 格式不合法，应为数字版本号（如 1.2.0）")
        sys.exit(1)
    return version


def _version_tuple(version: str) -> tuple:
    parts = [int(p) for p in version.split(".")]
    parts = (parts + [0, 0, 0, 0])[:4]
    return tuple(parts)


def write_version_info(target: Path, version: str) -> Path:
    """根据版本号生成 PyInstaller version 信息文件（写入 build 目录）。"""
    major, minor, patch, build_no = _version_tuple(version)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build_no}),
    prodvers=({major}, {minor}, {patch}, {build_no}),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'批图王'),
        StringStruct(u'FileDescription', u'批图王 - 专业图像批量合成工具'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'批图王'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2026 批图王'),
        StringStruct(u'OriginalFilename', u'批图王.exe'),
        StringStruct(u'ProductName', u'批图王'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def release_asset_url(version: str, filename: str) -> str:
    from urllib.parse import quote

    return (
        f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/"
        f"{quote(filename)}"
    )


def write_update_manifest(version: str) -> Path:
    """刷新 update/update.json，供客户端通过 raw.githubusercontent 检测更新。"""
    manifest_path = REPO_ROOT / "update" / "update.json"
    payload = {
        "version": version,
        "release_notes": f"批图王 v{version}\n请查看仓库更新日志了解本次更新内容。",
        "download_url": release_asset_url(version, f"{APP_NAME}.exe"),
        "installer_url": release_asset_url(version, f"{APP_NAME}-Setup.exe"),
        "required": False,
        "published_at": str(date.today()),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"更新清单已刷新: {manifest_path} (version={version})")
    print("注意: 请将该文件一并提交到 GitHub，并创建对应 v{0} Release".format(version))
    return manifest_path


def find_makensis() -> str:
    for candidate in NSIS_EXE_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return shutil.which("makensis") or ""


def build_installer(version: str) -> bool:
    """使用 NSIS 编译安装包，输出到 dist/批图王-Setup.exe。"""
    makensis = find_makensis()
    script = REPO_ROOT / "installer" / f"{APP_NAME}.nsi"
    if not makensis:
        print("Info: 未找到 NSIS（makensis.exe），跳过安装包构建")
        return False
    if not script.exists():
        print(f"Warning: 未找到安装脚本 {script}，跳过安装包构建")
        return False
    print(f"正在构建安装包 (NSIS)...")
    cmd = [makensis, f"/DAPP_VERSION={version}", f"/DAPP_NAME={APP_NAME}", str(script)]
    try:
        result = subprocess.run(cmd, cwd=str(script.parent), capture_output=True, text=True)
    except OSError as e:
        print(f"Warning: NSIS 编译失败: {e}")
        return False
    if result.returncode != 0:
        print(f"Warning: NSIS 编译失败:\n{result.stdout}\n{result.stderr}")
        return False
    setup_path = REPO_ROOT / "dist" / f"{APP_NAME}-Setup.exe"
    print(f"安装包生成: {setup_path}")
    return setup_path.exists()


def build():
    version = get_version()
    print(f"当前版本: v{version}")

    # 清理旧目录
    print("Cleaning up old build directories...")
    for directory in ("dist", "build"):
        if os.path.exists(directory):
            try:
                shutil.rmtree(directory)
            except Exception as e:
                print(f"Warning: Could not remove {directory} directory: {e}")

    # 确保 app/resources 存在
    if not os.path.exists('app/resources'):
        print("Error: app/resources not found!")
        return

    # 生成 PyInstaller 版本信息文件
    version_info_path = write_version_info(REPO_ROOT / "build" / "version_info_generated.txt", version)

    # PyInstaller 命令参数
    cmd = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--clean',
        '--windowed',
        '--onefile',
        f'--name={APP_NAME}',
        '--icon=app/resources/app_icon.ico',
        # 添加资源目录
        '--add-data=app/resources;app/resources',
        '--add-data=app/qml/Main.qml;app/qml',
        '--add-data=app/qml/components;app/qml/components',
        '--add-data=app/qml/icons;app/qml/icons',
        '--add-data=app/qml/assets;app/qml/assets',
        # 版本信息
        f'--version-file={version_info_path}',
        # 隐藏导入
        '--hidden-import=PySide6',
        '--hidden-import=PySide6.QtQml',
        '--hidden-import=PySide6.QtQuick',
        '--hidden-import=PySide6.QtQuickControls2',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=PIL',
        '--hidden-import=pyvips',
        '--hidden-import=app.workers.export_worker',
        '--hidden-import=cv2',
        '--hidden-import=numpy',
        '--hidden-import=scipy',
        '--hidden-import=psutil',
        # 排除不需要的模块以减小体积（可选）
        # '--exclude-module=matplotlib',
        # 入口文件
        'main.py'
    ]

    # 检查 presets
    if os.path.exists('presets'):
        cmd.insert(6, '--add-data=presets;presets')

    # 过滤 None 值
    cmd = [arg for arg in cmd if arg is not None]

    print("Executing command:", " ".join(cmd))

    try:
        subprocess.check_call(cmd)
        print("\n" + "="*50)
        print("打包成功！")
        print(f"输出目录: {os.path.abspath('dist')}")
        print(f"可执行文件: {os.path.abspath(f'dist/{APP_NAME}.exe')}")
        print("="*50)
    except subprocess.CalledProcessError as e:
        print(f"\n打包失败: {e}")
        sys.exit(1)

    # 生成自动更新清单（提交到仓库，供客户端检测）
    write_update_manifest(version)

    # 构建安装版
    build_installer(version)


if __name__ == "__main__":
    build()
