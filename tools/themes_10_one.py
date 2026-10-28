"""单方案主界面渲染（排查用）。

先确认一个方案能正确渲染，再批量出 10 格。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from themes_10 import THEMES  # noqa: E402
from themes_10_main_ui import build_ui, qss  # noqa: E402

OUT = ROOT / "_main_ui_one.png"


def main(key="01"):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase, QPixmap
    from PySide6.QtCore import QCoreApplication

    app = QApplication.instance() or QApplication(sys.argv)
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)

    t = next(x for x in THEMES if x["key"] == key)

    root = build_ui(t)
    root.setStyleSheet(qss(t))
    root.resize(1000, 640)
    root.show()
    for _ in range(20):
        QCoreApplication.processEvents()

    print(f"root size = {root.width()}x{root.height()}")
    print(f"root sizeHint = {root.sizeHint().width()}x{root.sizeHint().height()}")

    pm = QPixmap(root.size())
    pm.fill()
    root.render(pm)
    ok = pm.save(str(OUT), "PNG")
    print(f"已生成: {OUT} ok={ok} {pm.width()}x{pm.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "01"))
