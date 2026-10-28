"""验证启动画面在真实启动流程中的表现。

检查三件事（都是当初改造的动机）：
1. 几何首帧是否在 2 秒内出现（用户不会看到长时间空白）
2. 构造期间画面是否真的在刷新（进度点在推进）
3. 主窗口是否正常显示、启动画面是否干净收起

用法：python tools/verify_splash.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    t0 = time.time()
    app = QApplication([])
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(path)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)

    from app.ui.splash_screen import SplashScreen

    # --- 1. 几何首帧 ---
    t = time.time()
    splash = SplashScreen()
    geom_ms = (time.time() - t) * 1000

    t = time.time()
    splash.show()
    splash._pulse_timer.start()
    app.processEvents()
    first_paint_ms = (time.time() - t) * 1000
    print(f"几何首帧可见耗时: {first_paint_ms:.0f}ms（构造 {geom_ms:.0f}ms）")

    # --- 2. 构造期间进度刷新 ---
    ticks = []
    original_advance = splash.advance

    def spy(progress, message="", detail=""):
        ticks.append((int((time.time() - t0) * 1000), progress, message))
        return original_advance(progress, message, detail)

    splash.advance = spy

    from app.main_window import MainWindow

    MainWindow.stage_hook = splash.advance
    t = time.time()
    window = MainWindow()
    build_ms = (time.time() - t) * 1000
    MainWindow.stage_hook = None
    print(f"主窗口构造完成: {build_ms:.0f}ms，期间进度点 {len(ticks)} 个")

    splash.advance(1.0)
    window.show()
    splash.finish_with(window)
    for _ in range(15):
        QCoreApplication.processEvents()

    # --- 3. 收尾状态 ---
    visible = window.isVisible()
    splash_gone = not splash.isVisible()
    print(f"主窗口可见: {visible}   启动画面已收起: {splash_gone}")

    progs = [p for _, p, _ in ticks]
    monotonic = all(b >= a for a, b in zip(progs, progs[1:]))
    print(f"进度单调递增: {monotonic}  序列: {progs}")

    ok = (
        first_paint_ms < 2000
        and visible
        and splash_gone
        and monotonic
        and len(ticks) >= 4
    )
    print("\nRESULT: {}".format("PASS" if ok else "FAIL"))
    window.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
