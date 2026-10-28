"""截图真实经典界面（应用新令牌后的效果）。

不依赖人工操作：构造 MainWindow 后 render() 到 QPixmap。
offscreen 下 grab() 不可靠，必须用 render()。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "classic-applied.png"


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase, QFont, QPixmap
    from PySide6.QtCore import QCoreApplication

    app = QApplication.instance() or QApplication(sys.argv)
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    # 应用全局主题（含新令牌生成的 QSS）
    try:
        from app.ui.dark_theme import CursorDarkTheme
        CursorDarkTheme.apply_to_application(app)
        print("已应用全局主题")
    except Exception as e:
        print(f"应用主题失败（继续）: {e}")

    from app.main_window import MainWindow

    win = MainWindow()
    win.resize(1600, 960)
    win.show()
    for _ in range(25):
        QCoreApplication.processEvents()

    pm = QPixmap(win.size())
    pm.fill()
    win.render(pm)
    ok = pm.save(str(OUT), "PNG")
    print(f"已生成: {OUT}  ok={ok}  {pm.width()}x{pm.height()}")

    # 同时打印关键令牌实际生效值
    from app.ui.design_tokens import Tokens as T
    print("\n实际生效的关键令牌:")
    for k in ("BG_PRIMARY", "BG_SECONDARY", "BG_TERTIARY", "ACCENT",
              "TEXT_PRIMARY", "TEXT_MUTED", "FONT_FAMILY", "FONT_SIZE_BASE"):
        print(f"  {k:16} {getattr(T, k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
