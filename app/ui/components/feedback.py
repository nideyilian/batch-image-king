"""
shadcn/ui 风格反馈类组件：徽章、警示条、分割线、进度条。
视觉由全局 QSS 的 [role="badge"]/[role="alert"]/[role="separator"]/[role="progress"] 驱动。
"""
from PySide6.QtWidgets import (
    QLabel, QFrame, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt, Signal


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


class Toast(QFrame):
    dismissed = Signal()
    VARIANTS = ("default", "success", "warning", "destructive", "info")

    def __init__(self, message="", variant="default", parent=None, closable=True):
        super().__init__(parent)
        self.setProperty("role", "toast")
        self.setProperty("variant", variant if variant in self.VARIANTS else "default")
        self._message = QLabel(message, self)
        self._message.setProperty("role", "toast-message")
        self._message.setWordWrap(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 8, 9)
        layout.setSpacing(8)
        layout.addWidget(self._message, 1)
        self.close_button = QPushButton("x", self)
        self.close_button.setProperty("variant", "ghost")
        self.close_button.setProperty("uiSize", "icon")
        self.close_button.setAccessibleName("关闭通知")
        self.close_button.clicked.connect(self.dismiss)
        self.close_button.setVisible(closable)
        layout.addWidget(self.close_button)

    def message(self):
        return self._message.text()

    def set_message(self, message):
        self._message.setText(message)

    def dismiss(self):
        self.hide()
        self.dismissed.emit()


class Spinner(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "spinner")
        self.setRange(0, 0)
        self.setTextVisible(False)
        self.setFixedHeight(4)


class Skeleton(QFrame):
    def __init__(self, parent=None, width=0, height=16):
        super().__init__(parent)
        self.setProperty("role", "skeleton")
        if width:
            self.setFixedWidth(width)
        self.setFixedHeight(height)


class EmptyState(QFrame):
    def __init__(self, title="", description="", action_text="", parent=None):
        super().__init__(parent)
        self.setProperty("role", "empty-state")
        self.title_label = QLabel(title, self)
        self.title_label.setProperty("role", "empty-title")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.description_label = QLabel(description, self)
        self.description_label.setProperty("role", "muted")
        self.description_label.setAlignment(Qt.AlignCenter)
        self.description_label.setWordWrap(True)
        self.action_button = QPushButton(action_text, self)
        self.action_button.setProperty("variant", "default")
        self.action_button.setVisible(bool(action_text))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addWidget(self.action_button, 0, Qt.AlignCenter)
        layout.addStretch(1)
