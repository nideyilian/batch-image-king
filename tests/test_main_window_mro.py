"""主窗口 MRO 契约：mixin 必须排在 Qt 基类之前。

## 为什么需要这个测试

`MainWindow` 用多继承把功能拆到 5 个 mixin 里。曾经写成：

    class MainWindow(QMainWindow, MainWindowUi, MainWindowTabs, ...)

Python 的 MRO 里 `QMainWindow` 排在 mixin 前面，于是
`getattr(MainWindow, 'closeEvent')` 解析到的是 `QWidget.closeEvent`
（Qt 的空实现），**`MainWindowActions.closeEvent()` 从来没被执行过**。

后果（实测确认）：点窗口 X 直接退出，所有未保存文档静默丢弃，
一个提示都不弹。3 个 is_modified=True 的文档，弹窗次数 = 0。

Qt 的虚函数调用走 C++ 侧同名方法查找，谁在 MRO 前面就用谁。
这类 bug 不会报错、不会崩，只是"功能静默失效"，极难排查。

所以用测试锁住顺序，并用真实点击行为做二重保险。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.integration


def _app():
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    return app


def test_qt_base_class_is_last():
    """QMainWindow 必须排在所有 mixin 之后。"""
    from PySide6.QtWidgets import QMainWindow

    from app.main_window import MainWindow

    mro = MainWindow.__mro__
    qt_index = mro.index(QMainWindow)

    # 所有 app.main_window_* 的 mixin 都应该在 QMainWindow 之前
    for index, cls in enumerate(mro):
        if cls.__module__.startswith("app.main_window_"):
            assert index < qt_index, (
                f"{cls.__name__} 排在 {QMainWindow.__name__} 之后，"
                f"它里面的 Qt 虚函数（closeEvent / resizeEvent 等）会被静默遮蔽。"
                f"继承顺序必须是 (mixin..., QMainWindow)。"
            )


def test_close_event_resolves_to_project_code():
    """closeEvent 必须解析到项目自己的实现，而不是 Qt 基类。"""
    from app.main_window import MainWindow

    resolved = MainWindow.closeEvent.__qualname__
    assert not resolved.startswith(("QWidget.", "QMainWindow.")), (
        f"closeEvent 解析到了 {resolved} —— 关闭确认逻辑不会执行，"
        f"用户点 X 会静默丢失未保存内容。检查 MainWindow 的继承顺序。"
    )


def test_close_with_dirty_document_prompts_user():
    """有未保存改动时，关闭窗口必须先弹确认框。

    这是端到端保险：即使 MRO 测试通过，也要确认行为真的对。
    """
    from PySide6.QtWidgets import QMessageBox

    from app.main_window import MainWindow
    from app.models.document import Document

    app = _app()
    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)

    prompts = []
    original_exec = QMessageBox.exec
    original_clicked = QMessageBox.clickedButton

    def fake_exec(self):
        prompts.append(self.text())
        return 0

    def fake_clicked(self):
        # 选「取消」，不改动文档
        for b in self.buttons():
            if b.text() == "取消":
                return b
        return self.buttons()[0]

    QMessageBox.exec = fake_exec
    QMessageBox.clickedButton = fake_clicked

    win = None
    try:
        win = MainWindow()
        win.resize(1000, 700)
        doc = Document(parent=win)
        doc.create_new(400, 300)
        doc.is_modified = True
        win.create_new_tab(doc)
        win.show()
        app.processEvents()

        win.close()
        app.processEvents()

        assert prompts, (
            "关闭含未保存改动的窗口时没有任何提示 —— "
            "closeEvent 没被执行（很可能被 Qt 基类遮蔽了）"
        )
        assert "未保存" in prompts[0] or "保存" in prompts[0]
        # 点了取消，窗口应仍然打开
        assert win.isVisible(), "点了「取消」但窗口被关闭了"
    finally:
        QMessageBox.exec = original_exec
        QMessageBox.clickedButton = original_clicked
        if win is not None:
            win.deleteLater()
            app.processEvents()


def test_close_without_dirty_documents_closes_silently():
    """没有未保存改动时，关闭不应弹任何框（别烦用户）。"""
    from PySide6.QtWidgets import QMessageBox

    from app.main_window import MainWindow
    from app.models.document import Document

    app = _app()
    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)

    prompts = []
    original_exec = QMessageBox.exec
    QMessageBox.exec = lambda self: (prompts.append(self.text()), 0)[1]

    win = None
    try:
        win = MainWindow()
        win.resize(1000, 700)
        doc = Document(parent=win)
        doc.create_new(400, 300)
        doc.is_modified = False
        win.create_new_tab(doc)
        win.show()
        app.processEvents()

        win.close()
        app.processEvents()

        assert not prompts, f"干净文档关闭时不该弹框，实际弹了：{prompts}"
        assert not win.isVisible()
    finally:
        QMessageBox.exec = original_exec
        if win is not None:
            win.deleteLater()
            app.processEvents()
