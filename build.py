from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent
APP_NAME = "批图王"
GITHUB_REPO = "nideyilian/batch-image-king"
# 注意：GitHub Release 资产名不接受非 ASCII 字符，上传时统一使用 ASCII 文件名
RELEASE_EXE_NAME = "batch-image-king.exe"
RELEASE_SETUP_NAME = "batch-image-king-setup.exe"
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


def _sha256_hex(path: Path) -> str:
    """计算文件 SHA-256（分块读取，避免大文件占用过多内存）。"""
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_updater_tool(workpath: Path) -> Path:
    """构建安装版专用的独立更新工具（updater_tool.exe，onefile）。

    该工具运行时自解压到系统临时目录，不占用安装目录文件锁，因此可以安全地
    在主程序退出后静默执行安装包替换。输出到 dist/批图王/，随 NSIS 一起分发。
    """
    dist = REPO_ROOT / "dist" / APP_NAME
    workpath.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        f"--distpath={dist}",
        f"--workpath={workpath}",
        f"--specpath={workpath / 'spec'}",
        "--name=updater_tool",
        str(REPO_ROOT / "updater_tool.py"),
    ]
    print("Executing updater tool build command:", " ".join(cmd))
    subprocess.check_call(cmd)
    tool = dist / "updater_tool.exe"
    print(f"更新工具生成: {tool}")
    return tool


def write_update_manifest(version: str) -> Path:
    """刷新 update/update.json，供客户端通过 raw.githubusercontent 检测更新。"""
    manifest_path = REPO_ROOT / "update" / "update.json"

    # 本地自用包不该改线上清单：清单里写的是 download_url，一改就等于
    # 把全体用户的更新指向一个并不存在（或未签名）的版本。
    # 设 BTPW_SKIP_UPDATE_MANIFEST=1 可完全跳过本步骤。
    if os.environ.get("BTPW_SKIP_UPDATE_MANIFEST") == "1":
        print("已跳过更新清单生成（BTPW_SKIP_UPDATE_MANIFEST=1），update.json 保持不变")
        return manifest_path

    payload = {
        "version": version,
        "release_notes": f"批图王 v{version}\n请查看仓库更新日志了解本次更新内容。",
        "download_url": release_asset_url(version, RELEASE_EXE_NAME),
        "installer_url": release_asset_url(version, RELEASE_SETUP_NAME),
        "required": False,
        "published_at": str(date.today()),
    }
    # 便携版存在时写入 SHA-256，客户端下载后逐源校验，防止代理源返回损坏文件
    portable_exe = REPO_ROOT / "dist" / f"{APP_NAME}.exe"
    if portable_exe.exists():
        payload["sha256"] = _sha256_hex(portable_exe)
        print(f"已写入便携版 SHA-256: {payload['sha256']}")
    # 安装包存在时写入 SHA-256，安装版用户走静默安装包更新时同样逐源校验
    setup_exe = REPO_ROOT / "dist" / f"{APP_NAME}-Setup.exe"
    if setup_exe.exists():
        payload["installer_sha256"] = _sha256_hex(setup_exe)
        print(f"已写入安装包 SHA-256: {payload['installer_sha256']}")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # 自动签名（2026-11-02 加入）。
    #
    # 为什么放在这里：本函数每次发版都会**重写** update.json，而签名是对
    # 内容算的 —— 重写必然让旧签名失效。如果靠人工记得"打包完再签一次"，
    # 迟早会漏；漏签的后果不是报错，而是所有已升级客户端**静默拒绝更新**
    # （用户只看到"已是最新版本"），排查起来非常隐蔽。
    #
    # 私钥查找顺序：
    #   1) 环境变量 BTPW_SIGNING_KEY 指向的文件
    #   2) 签名工具约定的默认路径（当前工作目录下的 update_private_key.txt）
    # 找不到就不签，并打醒目提示（不静默跳过）。
    payload = _sign_manifest_payload(payload)

    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"更新清单已刷新: {manifest_path} (version={version})")
    print("注意: 请将该文件一并提交到 GitHub，并创建对应 v{0} Release".format(version))
    return manifest_path


def _find_signing_key() -> Optional[Path]:
    """定位私钥文件；找不到返回 None。"""
    env_key = os.environ.get("BTPW_SIGNING_KEY", "").strip()
    candidates = []
    if env_key:
        candidates.append(Path(env_key).expanduser())
    candidates.append(Path.cwd() / "update_private_key.txt")
    # 项目内也找一下（虽然 .gitignore 已屏蔽，但本地开发可能放这里）
    candidates.append(REPO_ROOT / "update_private_key.txt")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _sign_manifest_payload(payload: dict) -> dict:
    """给清单加 Ed25519 签名；无密钥时原样返回并提示。"""
    signing_key = _find_signing_key()
    if signing_key is None:
        # 用 [错误] 前缀：build.py 顶层把 print 换成了 safe_print，
        # 而 safe_print 只放行带"错误/失败"等关键词的消息。
        # 这条警告若被静音，使用者会以为签名成功、实际发出去的是未签名清单。
        print()
        print("[错误] 未找到签名私钥，update.json 将不带签名")
        print("[错误] 后果：已升级到「强制验签」版本的客户端会拒绝这次更新")
        print("   处理：设置环境变量 BTPW_SIGNING_KEY 指向私钥，或把私钥放到当前目录")
        print("   生成密钥：python tools/sign_update_manifest.py --gen-key")
        print()
        return payload

    try:
        import base64

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from app.utils.updater_signature import SIGNATURE_ALGORITHM, canonical_payload

        raw = base64.b64decode(signing_key.read_text(encoding="utf-8").strip(), validate=True)
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
        payload["signature"] = base64.b64encode(
            private_key.sign(canonical_payload(payload))
        ).decode()
        payload["signature_algorithm"] = SIGNATURE_ALGORITHM
        print(f"更新清单已签名: {payload['signature'][:24]}...")
    except Exception as error:  # noqa: BLE001 - 打包流程不应因签名失败整体中断
        print(f"[错误] 清单签名失败（本次发布将不带有效签名）: {error}")
        print("[错误] 已升级客户端会拒绝此清单，请修复后重新打包")
    return payload


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
        # NSIS 在中文 Windows 上按 ANSI/GBK 输出，用默认 UTF-8 解码会在读线程里
        # 抛 UnicodeDecodeError（不影响产物，但会污染构建日志）。errors=replace
        # 保证任何代码页下都能读全输出，失败时还能看到真实报错。
        result = subprocess.run(
            cmd,
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )
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
    write_version_info(REPO_ROOT / "build" / "version_info_generated.txt", version)

    def pyinstaller_command(*, distpath: str, workpath: str) -> list[str]:
        """构造 PyInstaller 命令 —— 统一走 ``批图王.spec``。

        为什么不再用一长串命令行参数：PyInstaller **没有** ``--exclude-binary``
        开关，纯命令行无法剔除被 Qt hook 整批收集的原生 DLL
        （``Qt6WebEngineCore.dll`` 单个 79.8MB）。只有在 spec 的 Analysis 之后
        过滤 ``a.binaries`` 才拦得住，因此资源和排除逻辑全部收敛到 spec。

        模式通过环境变量 ``BTK_BUILD_MODE`` 传给 spec（spec 内部据此决定
        单文件还是目录结构），这里不再需要 ``--onefile`` / ``--onedir``。
        """
        return [
            sys.executable,
            '-m',
            'PyInstaller',
            '--noconfirm',
            '--clean',
            f'--distpath={distpath}',
            f'--workpath={workpath}',
            str(REPO_ROOT / '批图王.spec'),
        ]

    def run_build(mode: str, distpath: str, workpath: str) -> None:
        """以指定模式执行一次打包（模式经环境变量传给 spec）。"""
        cmd = pyinstaller_command(distpath=distpath, workpath=workpath)
        print(f"Executing {mode} build:", " ".join(cmd))
        env = dict(os.environ)
        env['BTK_BUILD_MODE'] = mode
        subprocess.check_call(cmd, env=env)

    # 安装版优先：目录内直接加载 DLL/Python 模块，不再启动时解压。
    # onedir 的应用目录由 PyInstaller 按 ``distpath/<name>`` 生成，
    # 直接放在 dist 下，NSIS 可把该目录内容复制到安装根目录，避免额外一层目录。
    install_dist = str(REPO_ROOT / 'dist')
    install_work = str(REPO_ROOT / 'build' / 'installer')
    try:
        run_build('onedir', install_dist, install_work)
        # 便携版仍保留 onefile，供更新清单和免安装分发使用。
        run_build(
            'onefile',
            str(REPO_ROOT / 'dist'),
            str(REPO_ROOT / 'build' / 'portable'),
        )
        print("\n" + "="*50)
        print("打包成功！")
        print(f"安装版目录: {os.path.abspath(f'dist/{APP_NAME}')}")
        print(f"便携版文件: {os.path.abspath(f'dist/{APP_NAME}.exe')}")
        print("="*50)
    except subprocess.CalledProcessError as e:
        print(f"\n打包失败: {e}")
        sys.exit(1)

    # 构建安装版专用的独立更新工具（放进 dist/批图王/，随 NSIS 一起分发）
    try:
        build_updater_tool(REPO_ROOT / "build" / "updater_tool")
    except subprocess.CalledProcessError as e:
        print(f"\n更新工具打包失败: {e}")
        sys.exit(1)

    # 构建安装版（NSIS 会连同 updater_tool.exe 一起打包）
    build_installer(version)

    # 生成自动更新清单（含便携版与安装包 SHA-256），提交到仓库供客户端检测
    write_update_manifest(version)


if __name__ == "__main__":
    build()
