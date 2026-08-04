"""
shadcn/ui 风格输入控件与标签。

所有 QLineEdit / QSpinBox / QDoubleSpinBox / QComboBox 已由全局 QSS 统一外观，
本模块提供语义化的 Label 与「标签 + 控件」行布局辅助。
"""
from PySide6.QtWidgets import QLineEdit, QLabel, QWidget, QHBoxLayout, QFormLayout
from PySide6.QtCore import Qt

from app.ui.theme import Theme


class Input(QLineEdit):
    def __init__(self, parent=None, placeholder: str = ""):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)


class Label(QLabel):
    def __init__(self, text: str = "", parent=None, muted: bool = False):
        super().__init__(text, parent)
        self.setProperty("role", "muted" if muted else "label")


def field(label_text: str, control: QWidget, label_width: int = None,
          control_stretch: int = 1) -> QWidget:
    """构造一行「标签 + 控件」布局（标签固定宽、右对齐、加粗）。"""
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(Theme.spacing("sm"))
    lbl = Label(label_text)
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lw = label_width or Theme.layout("label_width")
    lbl.setFixedWidth(lw)
    h.addWidget(lbl)
    h.addWidget(control, control_stretch)
    return row


def form_layout() -> QFormLayout:
    """返回统一间距的表单布局，用于属性/设置面板。"""
    fl = QFormLayout()
    fl.setContentsMargins(0, 0, 0, 0)
    fl.setVerticalSpacing(Theme.spacing("sm"))
    fl.setHorizontalSpacing(Theme.spacing("sm"))
    fl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return fl
