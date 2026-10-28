"""两处缺口的端到端验证：关闭确认流 + 快速建文字层。

跑真实窗口，输出可核对的事实（不依赖断言，便于人工复核）。
用法：python tools/verify_gaps.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


def setup_app():
    app = QApplication.instance() or QApplication([])
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)
    return app


def section(title):
    print("\n" + "=" * 58)
    print(title)
    print("=" * 58)


def main() -> int:
    app = setup_app()
    from app.main_window import MainWindow
    from app.models.document import Document

    # ---------------- 缺口 1：关闭确认流 ----------------
    section("缺口 1：关闭确认流")
    from app.main_window_actions import MainWindowActions

    resolved = MainWindow.closeEvent.__qualname__
    print(f"closeEvent 解析到: {resolved}")
    print(f"是否为项目实现: {'是' if resolved.startswith('MainWindowActions') else '否 <-- 有问题'}")

    state = {"plan": [], "prompts": []}
    orig_exec, orig_clicked = QMessageBox.exec, QMessageBox.clickedButton

    def fake_exec(self):
        state["prompts"].append(
            {"text": self.text(), "buttons": [b.text() for b in self.buttons()]}
        )
        return 0

    def fake_clicked(self):
        want = state["plan"].pop(0) if state["plan"] else "取消"
        for b in self.buttons():
            if b.text() == want:
                return b
        return self.buttons()[0]

    QMessageBox.exec = fake_exec
    QMessageBox.clickedButton = fake_clicked

    def make_win(dirty_count=3):
        win = MainWindow()
        win.resize(1000, 700)
        for _ in range(dirty_count):
            doc = Document(parent=win)
            doc.create_new(400, 300)
            doc.is_modified = True
            win.create_new_tab(doc)
        win.show()
        app.processEvents()
        return win

    for plan, label, expect_visible in (
        (["取消"], "3 个脏文档 → 点「取消」", True),
        (["不保存"], "3 个脏文档 → 点「不保存」", False),
    ):
        win = make_win(3)
        state["plan"] = list(plan)
        state["prompts"] = []
        win.close()
        app.processEvents()
        p = state["prompts"]
        print(f"\n{label}")
        print(f"  弹框次数: {len(p)}")
        if p:
            print(f"  提示文案: {p[0]['text'].replace(chr(10), ' ')[:60]}")
            print(f"  按钮: {p[0]['buttons']}")
        print(f"  窗口仍打开: {win.isVisible()}  (期望 {expect_visible})")
        win.deleteLater()
        app.processEvents()

    QMessageBox.exec = orig_exec
    QMessageBox.clickedButton = orig_clicked

    # ---------------- 缺口 2：快速建文字层 ----------------
    section("缺口 2：快速建文字层")

    win = MainWindow()
    win.resize(1100, 800)
    doc = Document(parent=win)
    doc.create_new(1080, 1080)
    win.create_new_tab(doc)
    win.show()
    app.processEvents()

    print("方式 A：快捷键 T")
    before = len(doc.layers)
    win.setFocus()
    app.processEvents()
    QTest.keyClick(win, Qt.Key_T)
    app.processEvents()
    print(f"  图层数 {before} → {len(doc.layers)}")
    if doc.layers:
        layer = doc.layers[0]
        print(f"  名称={layer.name!r} 字号={layer.font_size}px 尺寸={layer.width}x{layer.height}")
        print(f"  自动适配={layer.auto_fit_text_box}")

    print("\n方式 B：带配置建层（非绑定多行）")
    layer2 = win.layer_controller.add_configured_text_layer(
        {
            "content": "秋季大促\n满300减50\n仅限3天",
            "font_size": 72,
            "color": "#FFD60A",
            "alignment": "center",
            "binding_enabled": False,
        }
    )
    if layer2:
        print(f"  名称={layer2.name!r} 尺寸={layer2.width}x{layer2.height}")
        print(f"  内容行数={len(str(layer2.current_text).splitlines())}")

    print("\n方式 C：对话框入口仍可用")
    from PySide6.QtGui import QAction

    acts = [a.text() for a in win.findChildren(QAction) if "文字" in (a.text() or "")]
    print(f"  菜单/工具栏里的文字层入口: {acts}")

    print("\n渲染检查")
    img = doc.render_composition()
    if img:
        import numpy as np

        arr = np.array(img.convert("RGB"))
        yellow = (
            (arr[:, :, 0] > 180) & (arr[:, :, 1] > 150) & (arr[:, :, 2] < 120)
        ).sum()
        white = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 200) & (arr[:, :, 2] > 200)
        print(f"  画布尺寸={img.size}  黄色像素={yellow}  白色像素={white.sum()}")

    win.deleteLater()
    app.processEvents()

    section("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
