"""批图王自动更新核心逻辑（纯 Python，不依赖 Qt，便于单元测试）。

工作流程：
1. 通过 update/update.json 清单（默认从 GitHub 原始文件拉取）获取最新版本。
2. 与本地 app/version.py 中的版本比较，判断是否有新版本。
3. 下载新版可执行文件到当前程序同目录的 `批图王_new.exe`。
4. 以 `--apply-update` 方式启动一个临时实例等待主进程退出后完成替换并重启。

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

# 下载到程序目录时的新版本临时文件名
NEW_EXE_NAME = f"{APP_NAME}_new.exe"


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
    )


def check_for_update(
    manifest_url: str = "",
    current_version: str = "",
) -> Optional[UpdateInfo]:
    """检查是否有新版本；有则返回 UpdateInfo，无则返回 None。"""
    info = fetch_update_info(manifest_url)
    current = current_version or get_current_version()
    if current and is_newer(info.version, current):
        return info
    return None


def download_file(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """流式下载到目标路径（先写临时文件再原子替换）。返回目标路径。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".download")
    timeout = float(os.environ.get("BTPW_UPDATE_DOWNLOAD_TIMEOUT", "30"))
    with url_request.urlopen(url, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        with open(tmp, "wb") as handle:
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


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_path() -> Path:
    return Path(sys.executable).resolve()


def new_exe_path() -> Path:
    return exe_path().with_name(NEW_EXE_NAME)


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

    返回码：0=成功；1=非冻结环境跳过；2=新版文件缺失；3=替换失败。
    """
    if not is_frozen():
        return 1
    current = Path(current_exe or exe_path()).resolve()
    new = Path(new_exe).resolve()
    if not new.exists():
        return 2
    wait_for_process(wait_pid, timeout=timeout)
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
    if not new.exists():
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
