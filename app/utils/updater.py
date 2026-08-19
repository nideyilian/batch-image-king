"""批图王自动更新核心逻辑（纯 Python，不依赖 Qt，便于单元测试）。

工作流程：
1. 通过 update/update.json 清单获取最新版本。清单源按顺序回退：
   显式指定 > 环境变量覆盖 > GitHub 官方 raw > jsDelivr CDN 备用镜像。
2. 与本地 app/version.py 中的版本比较，判断是否有新版本。
3. 下载新版可执行文件到当前程序同目录的 `批图王_new.exe`。下载地址按顺序回退：
   官方 GitHub Release > 多个国内 GitHub 加速代理；清单带 sha256 时逐源校验完整性。
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
    地址（防止代理源返回损坏或被篡改的文件）。
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
            for leftover in (dest, dest.with_name(dest.name + ".download")):
                try:
                    if leftover.exists():
                        leftover.unlink()
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
