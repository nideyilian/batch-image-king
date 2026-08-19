"""批图王自动更新核心逻辑（纯 Python，不依赖 Qt，便于单元测试）。

工作流程：
1. 通过 update/update.json 清单获取最新版本。清单源按顺序回退：
   显式指定 > 环境变量覆盖 > GitHub 官方 raw > jsDelivr CDN 备用镜像。
2. 与本地 app/version.py 中的版本比较，判断是否有新版本。
3. 按安装形态选择更新目标（update_download_target）：
   - 安装版（onedir，目录内有 updater_tool.exe）：下载新版安装包，
     由 updater_tool.exe 在主程序退出后静默执行 /S 安装，保持 onedir 布局；
   - 便携版（onefile）或无法走安装包流程：下载便携版 exe 原地替换。
   下载地址按顺序回退（官方 GitHub Release > 国内加速代理），
   清单带 sha256 时逐源校验完整性，支持断点续传。
4. 以 `--apply-update` 方式启动临时实例等待主进程退出后完成替换并重启。

环境变量：
- BTPW_UPDATE_URL：覆盖清单地址（测试时可用 file:// 指向本地 JSON）。
- BTPW_UPDATE_TIMEOUT：清单请求超时（秒）。
- BTPW_UPDATE_DOWNLOAD_TIMEOUT：下载连接/读取超时（秒）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib import request as url_request

APP_NAME = "批图王"

DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/nideyilian/batch-image-king/main/update/update.json"
)

# 更新清单备用源：官方 raw 源不可达时依次尝试。
# jsDelivr CDN 在国内可达性较好，但对 GitHub 文件缓存最长约 12 小时，
# 新版本发布后可能稍晚才可见（作为兜底可接受）。
MANIFEST_MIRRORS = [
    "https://cdn.jsdelivr.net/gh/nideyilian/batch-image-king@main/update/update.json",
]

# GitHub Release 下载加速代理前缀：逐个拼在官方下载地址前面作为备用源。
# 这些公益代理可能随时失效，可按需增删；客户端始终先尝试官方地址，
# 只有官方源失败（超时/被墙/限流）时才回退到代理。
GITHUB_PROXY_PREFIXES = [
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://ghproxy.net/",
    "https://gh.ddlc.top/",
    "https://github.moeyy.xyz/",
]

# 下载到程序目录时的新版本临时文件名
NEW_EXE_NAME = f"{APP_NAME}_new.exe"
# 安装版更新时下载到程序目录的安装包临时文件名
NEW_SETUP_NAME = f"{APP_NAME}-Setup_new.exe"
# 安装版自带的独立更新工具（随 onedir 一起分发）
UPDATER_TOOL_NAME = "updater_tool.exe"


@dataclass
class UpdateInfo:
    """从清单解析出的更新信息。"""

    version: str = ""
    release_notes: str = ""
    download_url: str = ""
    installer_url: str = ""
    required: bool = False
    published_at: str = ""
    manifest_url: str = ""
    sha256: str = ""
    installer_sha256: str = ""


def get_current_version() -> str:
    """读取本地版本（app/version.py，随程序一起打包）。"""
    try:
        from app.version import APP_VERSION

        return str(APP_VERSION or "").strip()
    except Exception:
        return ""


def get_manifest_url() -> str:
    return os.environ.get("BTPW_UPDATE_URL", DEFAULT_MANIFEST_URL)


def normalize_version(text: str) -> tuple:
    """把版本号规整为可比较的数字元组，如 '1.2.3' -> (1, 2, 3)。"""
    if not text:
        return (0,)
    parts = [int(part) for part in re.findall(r"\d+", str(text))][:4]
    return tuple(parts) if parts else (0,)


def is_newer(latest: str, current: str) -> bool:
    return normalize_version(latest) > normalize_version(current)


def fetch_update_info(manifest_url: str = "") -> UpdateInfo:
    """拉取并解析更新清单。网络/JSON 异常会向上抛出，由调用方处理。"""
    url = manifest_url or get_manifest_url()
    timeout = float(os.environ.get("BTPW_UPDATE_TIMEOUT", "15"))
    with url_request.urlopen(url, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    return UpdateInfo(
        version=str(payload.get("version", "") or "").strip(),
        release_notes=str(payload.get("release_notes", "") or ""),
        download_url=str(payload.get("download_url", "") or "").strip(),
        installer_url=str(payload.get("installer_url", "") or "").strip(),
        required=bool(payload.get("required", False)),
        published_at=str(payload.get("published_at", "") or ""),
        manifest_url=url,
        sha256=str(payload.get("sha256", "") or "").strip(),
        installer_sha256=str(payload.get("installer_sha256", "") or "").strip(),
    )


def _manifest_url_candidates(manifest_url: str = "") -> list[str]:
    """构造清单候选源列表（去重保序）：

    显式指定 > BTPW_UPDATE_URL 环境变量覆盖 > GitHub 官方 raw > 备用镜像。
    """
    candidates: list[str] = []

    def add(url: str) -> None:
        url = (url or "").strip()
        if url and url not in candidates:
            candidates.append(url)

    add(manifest_url)
    add(os.environ.get("BTPW_UPDATE_URL", ""))
    add(DEFAULT_MANIFEST_URL)
    for mirror in MANIFEST_MIRRORS:
        add(mirror)
    return candidates


def check_for_update(
    manifest_url: str = "",
    current_version: str = "",
) -> Optional[UpdateInfo]:
    """检查是否有新版本；有则返回 UpdateInfo，无则返回 None。

    按候选源顺序依次尝试（官方 > 备用镜像），任一源成功即返回结果；
    全部失败时抛出 RuntimeError，错误信息提示可手动下载。
    """
    candidates = _manifest_url_candidates(manifest_url)
    last_error: Optional[Exception] = None
    for url in candidates:
        try:
            info = fetch_update_info(url)
        except Exception as error:  # noqa: BLE001 - 单源失败继续尝试下一个
            last_error = error
            continue
        current = current_version or get_current_version()
        if current and is_newer(info.version, current):
            return info
        return None
    if last_error is not None:
        raise RuntimeError(
            f"检查更新失败：已尝试 {len(candidates)} 个更新源均不可达"
            f"（{last_error}）。请检查网络后重试，或打开“下载页”手动获取最新版。"
        ) from last_error
    return None


def download_file(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """流式下载到目标路径（先写临时文件再原子替换）。返回目标路径。

    支持断点续传：临时文件（*.download）已存在时带 Range 头续传；
    服务器不支持 Range（返回 200）时自动从头重新下载。中途失败会保留
    已下载的部分，下次调用从断点继续。
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".download")
    timeout = float(os.environ.get("BTPW_UPDATE_DOWNLOAD_TIMEOUT", "30"))
    existing = tmp.stat().st_size if tmp.exists() else 0
    headers = {}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
    req = url_request.Request(url, headers=headers)
    with url_request.urlopen(req, timeout=timeout) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status == 206:
            # 服务器支持续传：追加到已有部分之后
            mode = "ab"
            received = existing
            total = existing + int(response.headers.get("Content-Length") or 0)
        else:
            # 服务器不支持 Range：从头重新下载
            mode = "wb"
            received = 0
            total = int(response.headers.get("Content-Length") or 0)
        with open(tmp, mode) as handle:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                handle.write(chunk)
                received += len(chunk)
                if progress_cb:
                    progress_cb(received, total)
    if tmp.exists():
        tmp.replace(dest)
    if progress_cb:
        progress_cb(received, total)
    return dest


class UpdateIntegrityError(RuntimeError):
    """下载文件完整性校验失败（SHA-256 不匹配）。"""


def expand_download_urls(url: str) -> list[str]:
    """把官方下载地址扩展为「官方 + 加速代理」候选列表。非 GitHub 地址原样返回。"""
    candidates = [url]
    if url and url.startswith("https://github.com/"):
        for prefix in GITHUB_PROXY_PREFIXES:
            candidates.append(prefix + url)
    return candidates


def _sha256_hex(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_update(
    urls,
    dest: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    sha256: str = "",
) -> Path:
    """按候选顺序下载，首个成功的地址即返回；全部失败抛出最后一次异常。

    若提供了 sha256，下载完成后逐源校验哈希，不匹配则清理文件并尝试下一个
    地址（防止代理源返回损坏或被篡改的文件）。中途失败保留部分下载文件
    （*.download），供下一个地址或下次更新续传。
    """
    dest = Path(dest)
    last_error: Optional[Exception] = None
    for url in urls:
        try:
            download_file(url, dest, progress_cb)
            if sha256:
                actual = _sha256_hex(dest)
                if actual.lower() != sha256.lower():
                    raise UpdateIntegrityError(
                        f"文件校验失败：SHA-256 不匹配（来源：{url}）"
                    )
            return dest
        except Exception as error:  # noqa: BLE001 - 单源失败继续尝试下一个
            last_error = error
            # 完整下载但校验失败的产物需要清理；未完成的临时文件保留以便续传
            try:
                if dest.exists():
                    dest.unlink()
            except OSError:
                pass
    if last_error is not None:
        raise last_error
    raise RuntimeError("没有可用的下载地址")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_path() -> Path:
    return Path(sys.executable).resolve()


def new_exe_path() -> Path:
    return exe_path().with_name(NEW_EXE_NAME)


def new_setup_path() -> Path:
    """安装版更新时下载安装包的目标路径（程序目录内）。"""
    return exe_path().with_name(NEW_SETUP_NAME)


def updater_tool_path() -> Path:
    """安装版自带的独立更新工具路径（exe 同目录）。"""
    return exe_path().with_name(UPDATER_TOOL_NAME)


def is_onedir_install(exe: Optional[Path] = None) -> bool:
    """判断当前安装形态：onedir（安装版）在 exe 旁存在 _internal 目录。"""
    exe = Path(exe or exe_path()).resolve()
    return (exe.parent / "_internal").is_dir()


def installed_dir() -> str:
    """读取安装版注册表中的安装目录（HKCU 卸载项）；便携版或读取失败返回空串。"""
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
            return str(value or "").strip()
    except OSError:
        return ""


def read_exe_version(path) -> str:
    """读取 Windows PE 文件的版本资源（FileVersion），如 '1.2.3'。

    用于识别程序目录中已存在的新版 exe（手动导入兜底）。
    非 Windows、无版本资源或读取失败时返回空串。
    """
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        path = str(path)
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if size <= 0:
            return ""
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buffer):
            return ""
        value = wintypes.LPVOID()
        length = wintypes.UINT()
        sub_block = "\\StringFileInfo\\040904B0\\FileVersion"
        ok = ctypes.windll.version.VerQueryValueW(
            buffer, sub_block, ctypes.byref(value), ctypes.byref(length)
        )
        if not ok or not length.value:
            return ""
        raw = ctypes.wstring_at(value, length.value // 2)
        return str(raw).split("\x00", 1)[0].strip()
    except Exception:  # noqa: BLE001 - 读不出版本资源按无版本处理
        return ""


def find_local_update(current_version: str = "") -> Optional[Path]:
    """检测程序目录中是否已存在更新版 exe（手动导入兜底）。

    若 `批图王_new.exe` 存在且其 PE 版本资源高于当前版本，返回该文件路径；
    否则返回 None。
    """
    candidate = new_exe_path()
    if not candidate.is_file():
        return None
    current = current_version or get_current_version()
    candidate_version = read_exe_version(candidate)
    if not current or not candidate_version:
        return None
    if is_newer(candidate_version, current):
        return candidate
    return None


@dataclass
class DownloadTarget:
    """本次更新要下载的目标。"""

    kind: str  # "installer"（安装版安装包）或 "portable"（便携版 exe）
    url: str
    sha256: str
    dest: Path


def update_download_target(info: UpdateInfo) -> DownloadTarget:
    """根据当前安装形态选择更新下载目标。

    - 安装版（exe 旁有 _internal 且目录内有 updater_tool.exe）：下载安装包，
      由 updater_tool 静默安装，保持 onedir 布局与快捷方式/注册表一致；
    - 便携版或无法走安装包流程（旧版本无 updater_tool）：下载便携版 exe，
      原地替换。
    """
    if (
        is_onedir_install()
        and info.installer_url
        and updater_tool_path().is_file()
    ):
        return DownloadTarget(
            kind="installer",
            url=info.installer_url,
            sha256=info.installer_sha256,
            dest=new_setup_path(),
        )
    return DownloadTarget(
        kind="portable",
        url=info.download_url,
        sha256=info.sha256,
        dest=new_exe_path(),
    )


def wait_for_process(pid: int, timeout: float = 30.0) -> bool:
    """等待指定进程退出。超时返回 False。"""
    if pid <= 0:
        return True
    try:
        import psutil

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                process = psutil.Process(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return True
            if not process.is_running():
                return True
            time.sleep(0.5)
        try:
            process = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True
        return not process.is_running()
    except ImportError:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _pid_alive(pid):
                return True
            time.sleep(0.5)
        return not _pid_alive(pid)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def apply_update(
    new_exe: Path,
    current_exe: Optional[Path] = None,
    wait_pid: int = 0,
    relaunch: bool = True,
    timeout: float = 30.0,
) -> int:
    """在 `--apply-update` 模式下执行替换。

    返回码：0=成功；1=非冻结环境跳过；2=新版文件缺失；3=替换失败；
    4=等待主进程退出超时。
    """
    if not is_frozen():
        return 1
    current = Path(current_exe or exe_path()).resolve()
    if not str(new_exe):
        return 2
    new = Path(new_exe).resolve()
    if not new.is_file():
        return 2
    if not wait_for_process(wait_pid, timeout=timeout):
        return 4
    backup = current.with_name(current.name + ".bak")
    try:
        if backup.exists():
            backup.unlink()
        os.replace(current, backup)
        os.replace(new, current)
    except OSError:
        try:
            if not current.exists() and backup.exists():
                os.replace(backup, current)
        except OSError:
            pass
        return 3
    if relaunch:
        try:
            subprocess.Popen([str(current)], cwd=str(current.parent))
        except OSError:
            pass
    return 0


def spawn_apply_update(
    wait_pid: int,
    new_exe: Path,
    current_exe: Optional[Path] = None,
) -> bool:
    """从主进程启动自升级实例；成功返回 True，主进程应随后退出。"""
    if not is_frozen():
        return False
    current = Path(current_exe or exe_path()).resolve()
    new = Path(new_exe).resolve()
    if not new.is_file():
        return False
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        subprocess.Popen(
            [str(current), "--apply-update", str(new), "--wait-pid", str(int(wait_pid))],
            cwd=str(current.parent),
            creationflags=flags,
            close_fds=True,
        )
        return True
    except OSError:
        return False


def spawn_installer_update(
    setup_exe: Path,
    install_dir: str = "",
    wait_pid: int = 0,
    relaunch: bool = True,
) -> bool:
    """从主进程启动安装版更新工具（updater_tool.exe）；成功返回 True。

    updater_tool 是独立单文件程序，运行时自解压到临时目录、不占用安装目录
    文件锁，可安全地在主进程退出后静默执行安装包替换。
    """
    tool = updater_tool_path()
    if not tool.is_file() or not Path(setup_exe).is_file():
        return False
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    cmd = [
        str(tool),
        "--apply-installer",
        str(Path(setup_exe).resolve()),
        "--wait-pid",
        str(int(wait_pid)),
    ]
    if install_dir:
        cmd.append("--install-dir")
        cmd.append(install_dir)
    if not relaunch:
        cmd.append("--no-relaunch")
    try:
        subprocess.Popen(cmd, cwd=str(tool.parent), creationflags=flags, close_fds=True)
        return True
    except OSError:
        return False


def parse_apply_update_args(argv) -> tuple:
    """解析 `--apply-update <new> --wait-pid <pid>` 参数，返回 (new_exe, pid, relaunch)。"""
    new_exe = ""
    wait_pid = 0
    relaunch = True
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--apply-update" and index + 1 < len(argv):
            new_exe = argv[index + 1]
            index += 1
        elif arg == "--wait-pid" and index + 1 < len(argv):
            try:
                wait_pid = int(argv[index + 1])
            except ValueError:
                wait_pid = 0
            index += 1
        elif arg == "--no-relaunch":
            relaunch = False
        index += 1
    return new_exe, wait_pid, relaunch
