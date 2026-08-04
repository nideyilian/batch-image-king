"""
shadcn/ui 风格下拉选择（Select）。

直接基于 QComboBox，外观由全局 QSS 统一。提供 items / current 便捷接口。
"""
from PySide6.QtWidgets import QComboBox


class Select(QComboBox):
    def __init__(self, parent=None, items=None):
        super().__init__(parent)
        if items:
            self.addItems(items)

    def set_items(self, items):
        self.clear()
        self.addItems(items)

    @property
    def current(self) -> str:
        return self.currentText()
