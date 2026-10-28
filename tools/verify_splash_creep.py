"""验证：长时间阻塞期间，进度条是否真的在"蠕动"（而不是钉死不动）。

背景：主窗口构造里 `self.statusBar()` 一步占 79.5% 耗时（约 4 秒），
这段不可能产生中间进度点。若画面完全静止，用户会以为卡死。
本脚本模拟"两段真实进度之间隔 3 秒"，检查画面是否仍在变化。
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtGui import QFont, QFontDatabase, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def frame_signature(splash) -> bytes:
    """把当前画面转成字节，用于判断画面是否变化。"""
    pm = QPixmap(splash.width(), splash.height())
    pm.fill()
    splash.render(pm)
    img = pm.toImage()
    return bytes(img.constBits())


def main() -> int:
    app = QApplication([])
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(path)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)

    from app.splash_screen import SplashScreen

    splash = SplashScreen()
    splash.begin()
    splash.advance(0.12)

    start_progress = splash._progress
    signatures = set()

    # 模拟 2 秒的"阻塞期"：只有心跳定时器在跑，没有新的 advance
    deadline = time.time() + 2.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
        signatures.add(hash(frame_signature(splash)))

    end_progress = splash._progress
    grew = end_progress > start_progress
    varied = len(signatures) > 3

    print(f"阻塞期起点进度: {start_progress:.3f}")
    print(f"阻塞期终点进度: {end_progress:.3f}  前进 {end_progress - start_progress:.3f}")
    print(f"画面不同帧数: {len(signatures)}")
    print(f"进度在蠕动: {grew}   画面在变化: {varied}")

    ok = grew and varied and end_progress <= 0.12 + 0.09
    print("\nRESULT: {}".format("PASS" if ok else "FAIL"))
    splash.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
