"""
shadcn/ui 风格卡片组件。

结构：Card > CardHeader(CardTitle, CardDescription) + CardContent + CardFooter
视觉由全局 QSS 的 [role="card"] / [role="card-title"] / [role="card-desc"] 驱动。
"""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget
from PySide6.QtCore import Qt

from app.ui.theme import Theme


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            Theme.spacing("md"), Theme.spacing("md"),
            Theme.spacing("md"), Theme.spacing("md"))
        self._layout.setSpacing(Theme.spacing("sm"))

    def add_widget(self, w: QWidget):
        self._layout.addWidget(w)
        return w


class CardHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Theme.spacing("xs"))

    def add_widget(self, w: QWidget):
        self._layout.addWidget(w)
        return w


class CardTitle(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "card-title")


class CardDescription(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "card-desc")
        self.setWordWrap(True)


class CardContent(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Theme.spacing("sm"))

    def add_widget(self, w: QWidget):
        self._layout.addWidget(w)
        return w


class CardFooter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Theme.spacing("sm"))
        self._layout.addStretch(1)

    def add_widget(self, w: QWidget):
        self._layout.insertWidget(self._layout.count() - 1, w)
        return w
