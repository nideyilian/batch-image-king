"""
shadcn/ui 风格反馈类组件：徽章、警示条、分割线、进度条。
视觉由全局 QSS 的 [role="badge"]/[role="alert"]/[role="separator"]/[role="progress"] 驱动。
"""
from PySide6.QtWidgets import QLabel, QFrame, QProgressBar, QVBoxLayout, QWidget
from PySide6.QtCore import Qt


class Badge(QLabel):
    VARIANTS = ("default", "primary", "destructive", "success", "warning", "outline")

    def __init__(self, text: str = "", variant: str = "default", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "badge")
        self.set_variant(variant)

    def set_variant(self, variant: str):
        self.setProperty("variant", variant if variant in self.VARIANTS else "default")
        self.style().polish(self)


class Alert(QFrame):
    VARIANTS = ("default", "destructive", "success", "warning", "info")

    def __init__(self, title: str = "", description: str = "", variant: str = "default",
                 parent=None):
        super().__init__(parent)
        self.setProperty("role", "alert")
        self.set_variant(variant)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._title = QLabel(title)
        self._title.setProperty("role", "alert-title")
        self._desc = QLabel(description)
        self._desc.setProperty("role", "alert-desc")
        self._desc.setWordWrap(True)
        if title:
            self._layout.addWidget(self._title)
        if description:
            self._layout.addWidget(self._desc)

    def set_variant(self, variant: str):
        self.setProperty("variant", variant if variant in self.VARIANTS else "default")
        self.style().polish(self)

    def set_title(self, text: str):
        self._title.setText(text)

    def set_description(self, text: str):
        self._desc.setText(text)


class Separator(QFrame):
    def __init__(self, orientation: Qt.Orientation = Qt.Horizontal, parent=None):
        super().__init__(parent)
        self.setProperty("role", "separator")
        if orientation == Qt.Vertical:
            self.setProperty("orientation", "vertical")
            self.setFrameShape(QFrame.VLine)
        else:
            self.setFrameShape(QFrame.HLine)


class ProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "progress")
        self.setTextVisible(False)

    def set_progress(self, value: int, maximum: int = 100):
        self.setMaximum(maximum)
        self.setValue(value)
