"""
shadcn/ui 风格对话框与抽屉（Sheet）容器。

- Dialog：标准模态对话框基类，提供统一的底部按钮行（确定/取消等）。
- Sheet ：侧边抽屉容器（role="sheet"），用于右侧属性/设置面板。
"""
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QWidget
from PySide6.QtCore import Qt

from app.ui.components.button import Button
from app.ui.components.card import CardFooter


class Dialog(QDialog):
    def __init__(self, parent=None, title: str = ""):
        super().__init__(parent)
        if title:
            self.setWindowTitle(title)
        self.setMinimumWidth(420)

    def button_row(self, buttons) -> QWidget:
        """buttons: 可迭代的 QPushButton；自动右对齐并加间距。"""
        footer = CardFooter()
        for b in buttons:
            footer.add_widget(b)
        return footer


class Sheet(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "sheet")
