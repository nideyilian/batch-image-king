"""表单类组件：组合输入、可验证字段和选择控件。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QStandardItem
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
)

from app.ui.components.input import Label
from app.ui.components.select import Select
from app.ui.theme import Theme


class Textarea(QTextEdit):
    def __init__(self, parent=None, placeholder=""):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)


class NumberInput(QDoubleSpinBox):
    def __init__(self, parent=None, minimum=0, maximum=100, value=0,
                 decimals=0, suffix="", step=1):
        super().__init__(parent)
        self.setDecimals(decimals)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.setSuffix(suffix)
        self.setValue(value)


class ComboBox(Select):
    def __init__(self, parent=None, items=None, placeholder=""):
        super().__init__(parent, items)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        if self.lineEdit() is not None:
            self.lineEdit().setReadOnly(True)
            self.lineEdit().setPlaceholderText(placeholder)


class MultiSelect(QComboBox):
    selectedValuesChanged = Signal(list)

    def __init__(self, parent=None, items=None, placeholder="选择..."):
        super().__init__(parent)
        self._placeholder = placeholder
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.view().pressed.connect(self._toggle_index)
        for value, text in items or []:
            self.add_option(value, text)
        self._update_text()

    def add_option(self, value, text):
        item = QStandardItem(str(text))
        item.setData(str(value), Qt.UserRole)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)
        self.model().appendRow(item)

    def _toggle_index(self, index):
        item = self.model().itemFromIndex(index)
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self._update_text()
        self.selectedValuesChanged.emit(self.selected_values())

    def selected_values(self):
        return [
            self.model().item(row).data(Qt.UserRole)
            for row in range(self.model().rowCount())
            if self.model().item(row).checkState() == Qt.Checked
        ]

    def set_selected_values(self, values):
        wanted = {str(value) for value in values}
        for row in range(self.model().rowCount()):
            item = self.model().item(row)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in wanted else Qt.Unchecked)
        self._update_text()
        self.selectedValuesChanged.emit(self.selected_values())

    def _update_text(self):
        labels = [
            self.model().item(row).text()
            for row in range(self.model().rowCount())
            if self.model().item(row).checkState() == Qt.Checked
        ]
        self.lineEdit().setText(", ".join(labels) if labels else self._placeholder)


class RadioGroup(QFrame):
    valueChanged = Signal(str)

    def __init__(self, parent=None, options=None, orientation=Qt.Horizontal):
        super().__init__(parent)
        self.setProperty("role", "radio-group")
        self._group = QButtonGroup(self)
        self._values = {}
        layout_class = QHBoxLayout if orientation == Qt.Horizontal else QVBoxLayout
        self._layout = layout_class(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Theme.spacing("sm"))
        for value, text in options or []:
            self.add_option(value, text)

    def add_option(self, value, text):
        button = QRadioButton(text, self)
        self._group.addButton(button)
        self._values[button] = str(value)
        button.toggled.connect(lambda checked, b=button: checked and self.valueChanged.emit(self._values[b]))
        self._layout.addWidget(button)
        return button

    def value(self):
        return self._values.get(self._group.checkedButton(), "")

    def set_value(self, value):
        expected = str(value)
        for button, option_value in self._values.items():
            if option_value == expected:
                button.setChecked(True)
                return True
        return False


class Field(QFrame):
    def __init__(self, label, control, hint="", parent=None):
        super().__init__(parent)
        self.setProperty("role", "field")
        self.control = control
        self.label = Label(label, self)
        self.hint = QLabel(hint, self)
        self.hint.setProperty("role", "muted")
        self.error = QLabel("", self)
        self.error.setProperty("role", "field-error")
        self.error.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Theme.spacing("xs"))
        layout.addWidget(self.label)
        layout.addWidget(control)
        layout.addWidget(self.hint)
        layout.addWidget(self.error)

    def set_error(self, text):
        self.error.setText(text)
        self.error.setVisible(bool(text))
        self.hint.setVisible(bool(self.hint.text()) and not text)
        self.control.setProperty("invalid", bool(text))
        self.control.style().unpolish(self.control)
        self.control.style().polish(self.control)

    def error_text(self):
        return self.error.text()


class InputGroup(QFrame):
    def __init__(self, control, prefix="", suffix="", parent=None):
        super().__init__(parent)
        self.setProperty("role", "input-group")
        self.control = control
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Theme.spacing("sm"), 0, Theme.spacing("sm"), 0)
        layout.setSpacing(Theme.spacing("xs"))
        if prefix:
            prefix_label = QLabel(prefix, self)
            prefix_label.setProperty("role", "muted")
            layout.addWidget(prefix_label)
        layout.addWidget(control, 1)
        if suffix:
            suffix_label = QLabel(suffix, self)
            suffix_label.setProperty("role", "muted")
            layout.addWidget(suffix_label)
        self.setFocusProxy(control)


class ColorSwatch(QPushButton):
    colorChanged = Signal(QColor)

    def __init__(self, color="#000000", parent=None):
        super().__init__(parent)
        self.setProperty("role", "color-swatch")
        self.setAccessibleName("选择颜色")
        self.setFixedSize(36, 30)
        self._color = QColor()
        self.set_color(color)

    def color(self):
        return QColor(self._color)

    def set_color(self, color):
        candidate = QColor(color)
        if not candidate.isValid():
            raise ValueError("invalid color: %s" % color)
        if candidate != self._color:
            self._color = candidate
            self.setStyleSheet("background-color: %s;" % candidate.name(QColor.HexArgb))
            self.setToolTip(candidate.name(QColor.HexArgb))
            self.colorChanged.emit(QColor(candidate))
