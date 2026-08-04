"""
shadcn/ui 风格标签页容器。

标签页外观由全局 QSS 的 QTabWidget / QTabBar 规则驱动（见 dark_theme + provider）。
本组件提供统一的 Tab 添加辅助。
"""
from PySide6.QtWidgets import QTabWidget, QWidget


class Tabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    def add_tab(self, widget: QWidget, title: str) -> int:
        return self.addTab(widget, title)
