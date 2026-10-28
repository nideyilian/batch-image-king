"""真实启动截图：在启动画面上屏后抓一张，确认视觉与文字层都正确。

用法：python tools/shot_splash.py
输出：docs/ui-review/splash-*.png
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

OUTDIR = os.path.join(ROOT, "docs", "ui-review")

from PySide6.QtGui import QFont, QFontDatabase, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def grab(widget, name: str) -> str:
    pm = QPixmap(widget.width(), widget.height())
    pm.fill()
    widget.render(pm)
    path = os.path.join(OUTDIR, name)
    pm.save(path, "PNG")
    return path


def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)
    app = QApplication([])
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)

    from app.ui.splash_screen import SplashScreen

    splash = SplashScreen()
    splash.begin()

    # begin() 内部已补完文字层，这里两个阶段各截一张
    for progress, tag in ((0.08, "start"), (0.55, "mid"), (1.0, "done")):
        splash.advance(progress)
        path = grab(splash, f"splash-{tag}.png")
        print("saved:", os.path.relpath(path, ROOT))

    splash.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
