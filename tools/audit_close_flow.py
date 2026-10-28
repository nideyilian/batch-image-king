"""关闭流程体检：把经典版的关闭确认流实际跑一遍，看它到底哪里不对。

不起真对话框（会阻塞），用打桩替换 QMessageBox.exec / clickedButton
模拟用户点击「保存 / 不保存 / 取消」，检查：
1. 多标签 + 每个都有未保存改动时，点「取消」是否真能取消
2. 点「不保存」是否真的全部丢弃
3. 关闭单个标签时是否存在索引错乱
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


class State:
    plan: list[str] = []
    prompts: list[dict] = []


def make_window():
    from app.main_window import MainWindow
    from app.models.document import Document

    win = MainWindow()
    win.resize(1200, 800)
    for _ in range(3):
        doc = Document(parent=win)
        doc.create_new(400, 300)
        doc.is_modified = True
        win.create_new_tab(doc)
    win.show()
    QApplication.processEvents()
    return win


def install_stubs():
    def fake_exec(self):
        State.prompts.append(
            {
                "title": self.windowTitle(),
                "text": self.text(),
                "buttons": [b.text() for b in self.buttons()],
            }
        )
        return 0

    def fake_clicked(self):
        want = State.plan.pop(0) if State.plan else "取消"
        for b in self.buttons():
            if b.text() == want:
                return b
        return self.buttons()[0]

    QMessageBox.exec = fake_exec
    QMessageBox.clickedButton = fake_clicked


def reset(plan):
    State.plan = list(plan)
    State.prompts = []


def main() -> int:
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)

    install_stubs()

    # ---------- 场景 1：多文档全脏，点「取消」 ----------
    print("=== 场景1：3 个脏文档，点「取消」 ===")
    win = make_window()
    reset(["取消"])
    win.close()
    app.processEvents()
    print(f"  弹框次数: {len(State.prompts)}")
    for p in State.prompts:
        print(f"    标题={p['title']!r} 按钮={p['buttons']}")
    print(f"  窗口仍可见: {win.isVisible()}   (期望 True)")
    print(f"  标签数: {win.tab_widget.count()}   (期望 3)")
    still_modified = [
        win.document_manager.get_document(i).is_modified
        for i in range(win.document_manager.get_document_count())
    ]
    print(f"  各文档 is_modified: {still_modified}   (期望全 True)")
    win.deleteLater()
    app.processEvents()

    # ---------- 场景 2：多文档全脏，点「不保存」 ----------
    print("\n=== 场景2：3 个脏文档，点「不保存」 ===")
    win2 = make_window()
    reset(["不保存"])
    win2.close()
    app.processEvents()
    print(f"  弹框次数: {len(State.prompts)}   (期望 1 次就够)")
    print(f"  窗口仍可见: {win2.isVisible()}   (期望 False)")
    win2.deleteLater()
    app.processEvents()

    # ---------- 场景 3：关单个标签（中间那个） ----------
    print("\n=== 场景3：关闭中间标签（索引1），点「不保存」 ===")
    win3 = make_window()
    names_before = [win3.tab_widget.tabText(i) for i in range(win3.tab_widget.count())]
    reset(["不保存"])
    win3.close_tab(1)
    app.processEvents()
    names_after = [win3.tab_widget.tabText(i) for i in range(win3.tab_widget.count())]
    print(f"  关闭前: {names_before}")
    print(f"  关闭后: {names_after}   (期望少一个，其余顺序不变)")
    print(f"  弹框次数: {len(State.prompts)}")
    win3.deleteLater()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
