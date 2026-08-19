"""批图王安装版自动更新工具（独立单文件 exe，随安装版一起分发）。

为什么需要独立工具：安装版是 PyInstaller onedir 布局，主程序运行时会占用
``_internal`` 目录中的 DLL 等文件锁，无法在进程内替换整个安装目录。本工具
是 onefile 单文件程序，运行时自解压到系统临时目录，不占用安装目录任何文件，
因此可以在主程序完全退出后安全地执行安装包替换。

用法（由主程序自动调用，也可手动执行）：
    updater_tool.exe --apply-installer <setup.exe> [--install-dir <目录>] \\
        [--wait-pid <主进程PID>] [--wait-timeout <秒>] [--no-relaunch]

流程：
1. 等待主进程退出（--wait-pid，超时 --wait-timeout，默认 120 秒）。
2. 静默运行安装包：``setup.exe /S /D=<安装目录>``（/D 必须放在最后）。
3. 安装成功且未指定 --no-relaunch 时，重启安装目录中的主程序。

退出码：0=成功；1=参数错误；2=安装包缺失；3=等待主进程超时；4=安装失败。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "批图王"
APP_EXE = f"{APP_NAME}.exe"
_UNINSTALL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\批图王"
)
_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
)


def default_install_dir() -> str:
    """读取注册表中的安装目录；读取失败时回退到 NSIS 默认安装位置。"""
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as key:
                value, _ = winreg.QueryValueEx(key, "InstallLocation")
                if value:
                    return str(value).strip()
        except OSError:
            pass
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            return str(Path(base) / "Programs" / APP_NAME)
    return ""


def wait_for_pid(pid: int, timeout: float = 120.0) -> bool:
    """等待指定进程退出；超时返回 False。"""
    if pid <= 0:
        return True
    if os.name == "nt":
        return _wait_for_pid_win32(pid, timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.5)
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


def _wait_for_pid_win32(pid: int, timeout: float) -> bool:
    """win32 实现：OpenProcess + GetExitCodeProcess 轮询。"""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return True  # 无法打开通常意味着进程已不存在
    try:
        code = wintypes.DWORD()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            if code.value != STILL_ACTIVE:
                return True
            time.sleep(0.5)
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value != STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def run_installer(setup_exe: Path, install_dir: str = "", timeout: float = 600.0) -> int:
    """静默运行安装包，返回其退出码；启动失败或超时返回 -1。"""
    cmd = [str(setup_exe), "/S"]
    if install_dir:
        cmd.append(f"/D={install_dir}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(Path(setup_exe).parent),
            creationflags=_CREATE_NO_WINDOW,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1
    return result.returncode


def apply_installer(
    setup_exe,
    install_dir: str = "",
    wait_pid: int = 0,
    relaunch: bool = True,
    wait_timeout: float = 120.0,
) -> int:
    """安装版更新主流程；返回码见模块文档。"""
    setup = Path(setup_exe)
    if not setup.is_file():
        return 2
    if wait_pid > 0 and not wait_for_pid(wait_pid, timeout=wait_timeout):
        return 3
    code = run_installer(setup, install_dir=install_dir)
    if code != 0:
        return 4
    if relaunch:
        target = Path(install_dir) / APP_EXE if install_dir else Path()
        if target.is_file():
            try:
                subprocess.Popen(
                    [str(target)],
                    cwd=str(target.parent),
                    creationflags=_CREATE_NO_WINDOW,
                )
            except OSError:
                pass
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="updater_tool",
        description="批图王安装版自动更新工具",
    )
    parser.add_argument("--apply-installer", metavar="SETUP_EXE", default="")
    parser.add_argument("--install-dir", default="")
    parser.add_argument("--wait-pid", type=int, default=0)
    parser.add_argument("--wait-timeout", type=float, default=120.0)
    parser.add_argument("--no-relaunch", action="store_true")
    args = parser.parse_args(argv)

    if not args.apply_installer:
        parser.print_usage(sys.stderr)
        return 1
    install_dir = args.install_dir or default_install_dir()
    return apply_installer(
        args.apply_installer,
        install_dir=install_dir,
        wait_pid=args.wait_pid,
        relaunch=not args.no_relaunch,
        wait_timeout=args.wait_timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
