"""
shadcn/ui 风格基础控件：复选、单选、滑块，以及统一的开关。

开关直接复用现有设计系统里的 PropertySwitch（A2Switch 的基类），
以保证「全程序开关视觉同源」（详见 docs/UI设计规范.md）。
"""
from PySide6.QtWidgets import QCheckBox, QRadioButton, QSlider
from PySide6.QtCore import Qt

from app.ui.property_widgets import PropertySwitch


class Checkbox(QCheckBox):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)


class RadioButton(QRadioButton):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)


class Slider(QSlider):
    def __init__(self, orientation: Qt.Orientation = Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)


# 全程序统一开关（已有 A2Switch 风格，禁止用原生 QCheckBox 当开关）
Switch = PropertySwitch
