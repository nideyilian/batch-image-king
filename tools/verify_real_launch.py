"""真实启动 main.py 的端到端验证（QML 工作台）。

用真实参数跑 main.main()，3 秒后自动退出，检查：
- 是否打印「启动完成」（日志走 stderr，print 走 stdout）
- 退出码是否为 0
- 是否抛异常

2026-10-28：经典界面下线后，这里不再包装 MainWindow.stage_hook。
注意 main() 现在有自己的退出清理（线程池 / 缓存 / 崩溃会话收尾），
所以「退出码 0」比过去更有意义 —— 它同时证明清理流程没抛异常。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INNER = r'''
import sys
sys.argv = ["main.py"]
sys.path.insert(0, ".")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

_orig_exec = QApplication.exec


def _exec_with_timeout(self=None):
    def _auto_quit():
        app = QApplication.instance()
        if app is not None:
            app.quit()

    QTimer.singleShot(3000, _auto_quit)
    return _orig_exec()


QApplication.exec = staticmethod(_exec_with_timeout)
QApplication.exec_ = staticmethod(_exec_with_timeout)

import main as entry

rc = entry.main()
print("EXITCODE:", rc)
'''


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "-u", "-c", INNER],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ROOT,
        timeout=180,
    )
    out = proc.stdout or ""
    err = proc.stderr or ""

    ok_start = "启动完成" in err or "启动完成" in out
    has_traceback = "Traceback (most recent call last)" in err
    exit_match = re.search(r"EXITCODE:\s*(-?\d+)", out)
    exit_code = int(exit_match.group(1)) if exit_match else None

    dur_match = re.search(r"启动完成，总耗时:\s*([\d.]+)", err + out)

    print("=== 结果 ===")
    print(f"启动完成日志: {'有' if ok_start else '无'}")
    if dur_match:
        print(f"总耗时: {dur_match.group(1)} 秒")
    print(f"退出码: {exit_code}")
    print(f"异常: {'有 Traceback' if has_traceback else '无'}")

    if has_traceback:
        idx = err.find("Traceback")
        print("--- traceback ---")
        print(err[idx : idx + 900])

    ok = ok_start and exit_code == 0 and not has_traceback
    print("\nRESULT: {}".format("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
