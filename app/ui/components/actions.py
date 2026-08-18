"""操作类组件：图标按钮、按钮组、切换组与分段控件。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QToolButton, QVBoxLayout

from app.ui.components.button import Button
from app.ui.icon_manager import IconManager


class IconButton(Button):
    def __init__(self, icon_name, tool_tip, variant="ghost", icon_size=16, parent=None):
        icon = IconManager.get_icon(icon_name, icon_size)
        super().__init__("", variant=variant, size="icon", icon=icon, parent=parent)
        self.setToolTip(tool_tip)
        self.setAccessibleName(tool_tip)
        self.setProperty("role", "icon-button")


class ButtonGroup(QFrame):
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(parent)
        self.setProperty("role", "button-group")
        layout_class = QHBoxLayout if orientation == Qt.Horizontal else QVBoxLayout
        self._layout = layout_class(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def add_button(self, button, stretch=0):
        self._layout.addWidget(button, stretch)
        return button


class Toggle(QToolButton):
    def __init__(self, text="", icon=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setProperty("role", "toggle")
        self.setProperty("variant", "ghost")
        if icon is not None:
            self.setIcon(icon)
        if text:
            self.setAccessibleName(text.replace("&", ""))
        self.setCursor(Qt.PointingHandCursor)


class ToggleGroup(QFrame):
    currentChanged = Signal(str)

    def __init__(self, orientation=Qt.Horizontal, exclusive=True, parent=None):
        super().__init__(parent)
        self.setProperty("role", "toggle-group")
        self._buttons = QButtonGroup(self)
        self._buttons.setExclusive(exclusive)
        self._values = {}
        layout_class = QHBoxLayout if orientation == Qt.Horizontal else QVBoxLayout
        self._layout = layout_class(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def add_item(self, value, text, icon=None):
        button = Toggle(text, icon, self)
        self._buttons.addButton(button)
        self._values[button] = str(value)
        button.toggled.connect(lambda checked, b=button: self._emit_if_checked(b, checked))
        self._layout.addWidget(button)
        return button

    def _emit_if_checked(self, button, checked):
        if checked:
            self.currentChanged.emit(self._values[button])

    def current_value(self):
        checked = self._buttons.checkedButton()
        return self._values.get(checked, "")

    def set_current_value(self, value):
        expected = str(value)
        for button, item_value in self._values.items():
            if item_value == expected:
                button.setChecked(True)
                return True
        return False


class SegmentedControl(ToggleGroup):
    def __init__(self, items=None, parent=None):
        super().__init__(Qt.Horizontal, True, parent)
        self.setProperty("role", "segmented-control")
        for value, text in items or []:
            self.add_item(value, text)
        if self._buttons.buttons():
            self._buttons.buttons()[0].setChecked(True)


def tooltip(widget, text):
    widget.setToolTip(text)
    if not widget.accessibleName():
        widget.setAccessibleName(text)
    return widget
