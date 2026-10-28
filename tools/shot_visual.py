"""视觉验收截图：改造后的主界面 + 两个侧栏面板。

用法：python tools/shot_visual.py
输出：docs/ui-review/visual-*.png
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

OUTDIR = os.path.join(ROOT, "docs", "ui-review")

from PySide6.QtCore import QPoint, QCoreApplication  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def grab(widget, name, height=None):
    h = height or widget.height()
    pm = QPixmap(widget.width(), h)
    pm.fill()
    widget.render(pm, QPoint(0, 0))
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

    from app.main_window import MainWindow
    from app.models.document import Document

    win = MainWindow()
    win.resize(1600, 1000)

    doc = Document(parent=win)
    doc.create_new(1080, 1080)
    win.create_new_tab(doc)

    # 造几个有代表性的图层，让面板有内容可看
    win.layer_controller.add_configured_text_layer(
        {"content": "双11狂欢", "font_size": 120, "color": "#FF2D55", "alignment": "center"}
    )
    win.layer_controller.add_configured_text_layer(
        {"content": "满300减50", "font_size": 64, "color": "#FFD60A", "alignment": "center"}
    )
    win.layer_controller.add_configured_text_layer(
        {"content": "仅限3天 · 手慢无", "font_size": 40, "color": "#64D2FF"}
    )

    win.show()
    for _ in range(30):
        QCoreApplication.processEvents()

    saved = [
        grab(win, "visual-main.png"),
        grab(win.properties_panel, "visual-properties.png"),
        grab(win.layer_panel, "visual-layers.png", height=min(win.layer_panel.height(), 320)),
    ]
    for path in saved:
        print("saved:", os.path.relpath(path, ROOT))

    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
