"""启动耗时分段测量：找出 7.9 秒花在哪。"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MARKS = []


def mark(label, t0):
    d = (time.time() - t0) * 1000
    MARKS.append((label, d))
    return time.time()


def main():
    t = time.time()

    from PySide6.QtWidgets import QApplication
    t = mark("import PySide6", t)

    app = QApplication(sys.argv)
    t = mark("QApplication()", t)

    from PySide6.QtGui import QFontDatabase, QFont

    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    t = mark("加载字体", t)

    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)
    t = mark("应用主题(生成QSS)", t)

    from app.main_window import MainWindow

    t = mark("import MainWindow", t)

    win = MainWindow()
    t = mark("MainWindow() 构造", t)

    win.resize(1600, 1000)
    win.show()
    t = mark("show()", t)

    from PySide6.QtCore import QCoreApplication

    for _ in range(20):
        QCoreApplication.processEvents()
    t = mark("20 轮事件循环", t)

    total = sum(d for _, d in MARKS)
    print(f"{'阶段':28} {'耗时(ms)':>10} {'占比':>7}")
    print("-" * 50)
    for label, d in MARKS:
        print(f"{label:28} {d:10.0f} {d / total * 100:6.1f}%")
    print("-" * 50)
    print(f"{'合计':28} {total:10.0f}")

    # cProfile 细化 MainWindow 构造
    import cProfile
    import io
    import pstats

    pr = cProfile.Profile()
    pr.enable()
    win2 = MainWindow()
    pr.disable()
    buf = io.StringIO()
    ps = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    ps.print_stats(18)
    print("\n=== MainWindow 构造热点 ===")
    for line in buf.getvalue().splitlines():
        s = line.strip()
        if s and ("app/" in s or "PySide6" in s or "cumulative" in s):
            print(line[:150])


if __name__ == "__main__":
    main()
