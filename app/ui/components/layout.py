"""布局组件：滚动区、可调整分栏、侧栏、比例容器和手风琴。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
)

from app.ui.theme import Theme


class ScrollArea(QScrollArea):
    def __init__(self, content=None, parent=None):
        super().__init__(parent)
        self.setProperty("role", "scroll-area")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        if content is not None:
            self.setWidget(content)


class Resizable(QSplitter):
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setProperty("role", "resizable")
        self.setChildrenCollapsible(False)


class Sidebar(QFrame):
    def __init__(self, parent=None, width=260):
        super().__init__(parent)
        self.setProperty("role", "sidebar")
        self.setMinimumWidth(width)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)


class AspectRatio(QFrame):
    def __init__(self, ratio=1.0, parent=None):
        super().__init__(parent)
        self.setProperty("role", "aspect-ratio")
        self._ratio = max(float(ratio), 0.01)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return round(width / self._ratio)

    def ratio(self):
        return self._ratio

    def set_ratio(self, ratio):
        self._ratio = max(float(ratio), 0.01)
        self.updateGeometry()


class AccordionItem(QFrame):
    expandedChanged = Signal(bool)

    def __init__(self, title, content, expanded=False, parent=None):
        super().__init__(parent)
        self.setProperty("role", "accordion-item")
        self.trigger = QToolButton(self)
        self.trigger.setText(title)
        self.trigger.setCheckable(True)
        self.trigger.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.trigger.setProperty("role", "accordion-trigger")
        self.trigger.setCursor(Qt.PointingHandCursor)
        self.content = content
        self.content.setProperty("role", "accordion-content")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.trigger)
        layout.addWidget(content)
        self.trigger.toggled.connect(self._set_content_visible)
        self.set_expanded(expanded)

    def _set_content_visible(self, expanded):
        self.content.setVisible(expanded)
        self.setProperty("expanded", expanded)
        self.expandedChanged.emit(expanded)

    def is_expanded(self):
        return self.trigger.isChecked()

    def set_expanded(self, expanded):
        expanded = bool(expanded)
        self.trigger.setChecked(expanded)
        self._set_content_visible(expanded)


class Accordion(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "accordion")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Theme.spacing("xs"))
        self._layout.addStretch(1)
        self._items = []

    def add_item(self, title, content, expanded=False):
        item = AccordionItem(title, content, expanded, self)
        self._layout.insertWidget(self._layout.count() - 1, item)
        self._items.append(item)
        return item

    def items(self):
        return tuple(self._items)
