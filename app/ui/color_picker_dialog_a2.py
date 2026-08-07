#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Photoshop 风格的统一颜色选择器。"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.dialog_a2 import DialogA2


class _SaturationValueField(QWidget):
    """二维饱和度 / 明度色域。"""

    value_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self._saturation = 0
        self._value = 0
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)

    def set_hsv(self, hue, saturation, value):
        self._hue = max(0, min(359, int(hue)))
        self._saturation = max(0, min(255, int(saturation)))
        self._value = max(0, min(255, int(value)))
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        saturation_gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        saturation_gradient.setColorAt(0.0, QColor(Qt.white))
        saturation_gradient.setColorAt(1.0, QColor.fromHsv(self._hue, 255, 255))
        painter.fillRect(rect, saturation_gradient)

        value_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        value_gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        value_gradient.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, value_gradient)

        painter.setPen(QPen(QColor(DialogA2.BORDER_CONTROL), 1))
        painter.drawRect(rect)

        x = rect.left() + (self._saturation / 255.0) * rect.width()
        y = rect.top() + (1.0 - self._value / 255.0) * rect.height()
        painter.setPen(QPen(Qt.black, 3))
        painter.drawEllipse(QPointF(x, y), 6, 6)
        painter.setPen(QPen(Qt.white, 1))
        painter.drawEllipse(QPointF(x, y), 5, 5)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._update_from_position(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._update_from_position(event.position())

    def _update_from_position(self, position):
        width = max(1, self.width() - 2)
        height = max(1, self.height() - 2)
        x = max(0.0, min(float(width), position.x() - 1.0))
        y = max(0.0, min(float(height), position.y() - 1.0))
        self._saturation = round((x / width) * 255)
        self._value = round((1.0 - y / height) * 255)
        self.update()
        self.value_changed.emit(self._saturation, self._value)


class _HueStrip(QWidget):
    """垂直色相选择条。"""

    hue_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self.setFixedWidth(30)
        self.setMinimumHeight(320)
        self.setCursor(Qt.PointingHandCursor)

    def set_hue(self, hue):
        self._hue = max(0, min(359, int(hue)))
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        rect = QRectF(self.rect()).adjusted(4, 1, -5, -1)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        for index in range(7):
            position = index / 6.0
            gradient.setColorAt(position, QColor.fromHsv(round(position * 359), 255, 255))
        painter.fillRect(rect, gradient)
        painter.setPen(QPen(QColor(DialogA2.BORDER_CONTROL), 1))
        painter.drawRect(rect)

        y = rect.top() + (self._hue / 359.0) * rect.height()
        painter.setPen(QPen(Qt.white, 2))
        painter.drawLine(0, round(y), 4, round(y))
        painter.drawLine(self.width() - 5, round(y), self.width() - 1, round(y))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._update_from_position(event.position().y())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._update_from_position(event.position().y())

    def _update_from_position(self, y):
        height = max(1, self.height() - 2)
        clamped = max(0.0, min(float(height), y - 1.0))
        self._hue = round((clamped / height) * 359)
        self.update()
        self.hue_changed.emit(self._hue)


class _ColorPreview(QFrame):
    """带透明棋盘格的颜色预览。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(Qt.transparent)
        self.setFixedSize(DialogA2.PREVIEW_SWATCH_SIZE, DialogA2.PREVIEW_SWATCH_SIZE)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        cell = 8
        light = QColor(205, 205, 205)
        dark = QColor(145, 145, 145)
        for y in range(0, self.height(), cell):
            for x in range(0, self.width(), cell):
                painter.fillRect(x, y, cell, cell, light if ((x // cell) + (y // cell)) % 2 == 0 else dark)
        painter.fillRect(self.rect(), self._color)
        painter.setPen(QPen(QColor(DialogA2.BORDER_CONTROL), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


class _ColorSwatchButton(QPushButton):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setProperty("color", self._color)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._refresh_style(False)

    def set_selected(self, selected):
        self._refresh_style(selected)

    def _refresh_style(self, selected):
        border = DialogA2.ACCENT_HOVER if selected else DialogA2.BORDER_CONTROL
        width = 2 if selected else 1
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._color.name()};
                border: {width}px solid {border};
                border-radius: 3px;
                padding: 0;
            }}
        """)


class ColorPickerDialogA2(QDialog):
    """统一的专业取色器，支持 HSV、RGB、HEX 和透明度。"""

    BASIC_COLORS = [
        "#000000", "#404040", "#808080", "#bfbfbf", "#ffffff", "#7f0000", "#ff0000", "#ff7f7f",
        "#7f3f00", "#ff7f00", "#ffbf7f", "#7f7f00", "#ffff00", "#ffff7f", "#007f00", "#00ff00",
        "#7fff7f", "#007f7f", "#00ffff", "#7fffff", "#00007f", "#0000ff", "#7f7fff", "#3f007f",
        "#7f00ff", "#bf7fff", "#7f007f", "#ff00ff", "#ff7fff", "#7f003f", "#ff007f", "#ff7fbf",
    ]

    def __init__(self, initial_color=None, parent=None, title="选择颜色", show_alpha=True):
        super().__init__(parent)
        self._syncing = False
        self._show_alpha = show_alpha
        self._initial_color = QColor(initial_color) if initial_color is not None else QColor(255, 255, 255, 255)
        if not self._initial_color.isValid():
            self._initial_color = QColor(255, 255, 255, 255)
        if not show_alpha:
            self._initial_color.setAlpha(255)
        self._selected_color = QColor(self._initial_color)
        self._hue = max(0, self._selected_color.hsvHue())

        self.setWindowTitle(f"取色器（{title}）")
        self.setModal(True)
        self.resize(780, 540)
        self.setMinimumSize(700, 500)
        DialogA2.apply(self)
        self._setup_ui(title)
        self.set_selected_color(self._selected_color)

    def selected_color(self):
        return QColor(self._selected_color)

    def set_selected_color(self, color):
        if not color.isValid():
            return
        next_color = QColor(color)
        if not self._show_alpha:
            next_color.setAlpha(255)
        next_hue = next_color.hsvHue()
        if next_hue >= 0:
            self._hue = next_hue

        self._selected_color = next_color
        self._syncing = True
        try:
            self.red_spin.setValue(next_color.red())
            self.green_spin.setValue(next_color.green())
            self.blue_spin.setValue(next_color.blue())
            self.alpha_spin.setValue(next_color.alpha())
            self.hue_spin.setValue(self._hue)
            self.saturation_spin.setValue(round(next_color.hsvSaturation() * 100 / 255))
            self.value_spin.setValue(round(next_color.value() * 100 / 255))
            self.hex_edit.setText(next_color.name())
            self.color_field.set_hsv(self._hue, next_color.hsvSaturation(), next_color.value())
            self.hue_strip.set_hue(self._hue)
            self.new_preview.set_color(next_color)
            self.preview_swatch = self.new_preview
            self._update_swatch_selection()
        finally:
            self._syncing = False

    def apply_hex_color(self):
        text = self.hex_edit.text().strip()
        if not text.startswith("#"):
            text = f"#{text}"
        color = QColor(text)
        if color.isValid():
            color.setAlpha(self.alpha_spin.value())
            self.set_selected_color(color)
        else:
            self.hex_edit.setText(self._selected_color.name())

    def _setup_ui(self, title):
        root = QVBoxLayout(self)
        root.setContentsMargins(DialogA2.OUTER_MARGIN, DialogA2.OUTER_MARGIN, DialogA2.OUTER_MARGIN, DialogA2.OUTER_MARGIN)
        root.setSpacing(DialogA2.CONTENT_GAP)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "dialogTitle")
        root.addWidget(self.title_label)

        body = QHBoxLayout()
        body.setSpacing(DialogA2.CONTENT_GAP)
        root.addLayout(body, 1)

        field_card = self._make_card()
        field_layout = QHBoxLayout(field_card)
        field_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        field_layout.setSpacing(10)
        self.color_field = _SaturationValueField(self)
        self.hue_strip = _HueStrip(self)
        field_layout.addWidget(self.color_field, 1)
        field_layout.addWidget(self.hue_strip)
        body.addWidget(field_card, 3)

        detail_card = self._make_card()
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        detail_layout.setSpacing(DialogA2.CARD_GAP)

        preview_layout = QGridLayout()
        preview_layout.setHorizontalSpacing(10)
        preview_layout.setVerticalSpacing(4)
        self.new_preview = _ColorPreview(self)
        self.current_preview = _ColorPreview(self)
        self.current_preview.set_color(self._initial_color)
        preview_layout.addWidget(QLabel("新的"), 0, 0, Qt.AlignHCenter)
        preview_layout.addWidget(QLabel("当前"), 0, 1, Qt.AlignHCenter)
        preview_layout.addWidget(self.new_preview, 1, 0)
        preview_layout.addWidget(self.current_preview, 1, 1)
        detail_layout.addLayout(preview_layout)

        hsv_grid = QGridLayout()
        hsv_grid.setHorizontalSpacing(8)
        hsv_grid.setVerticalSpacing(6)
        self.hue_spin = self._make_spin(0, 359, "°")
        self.saturation_spin = self._make_spin(0, 100, "%")
        self.value_spin = self._make_spin(0, 100, "%")
        self.red_spin = self._make_spin(0, 255)
        self.green_spin = self._make_spin(0, 255)
        self.blue_spin = self._make_spin(0, 255)
        self.alpha_spin = self._make_spin(0, 255)

        fields = (
            ("H", self.hue_spin, 0, 0), ("S", self.saturation_spin, 1, 0), ("B", self.value_spin, 2, 0),
            ("R", self.red_spin, 0, 2), ("G", self.green_spin, 1, 2), ("B", self.blue_spin, 2, 2),
            ("A", self.alpha_spin, 3, 2),
        )
        for label, spin, row, column in fields:
            hsv_grid.addWidget(self._field_label(label), row, column)
            hsv_grid.addWidget(spin, row, column + 1)
        detail_layout.addLayout(hsv_grid)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(8)
        hex_row.addWidget(self._field_label("#"))
        self.hex_edit = QLineEdit()
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        self.hex_edit.editingFinished.connect(self.apply_hex_color)
        hex_row.addWidget(self.hex_edit, 1)
        detail_layout.addLayout(hex_row)

        palette_label = QLabel("常用颜色")
        palette_label.setProperty("role", "sectionTitle")
        detail_layout.addWidget(palette_label)
        swatch_grid = QGridLayout()
        swatch_grid.setHorizontalSpacing(5)
        swatch_grid.setVerticalSpacing(5)
        self.swatch_buttons = []
        for index, color in enumerate(self.BASIC_COLORS):
            button = _ColorSwatchButton(color, self)
            button.clicked.connect(lambda checked=False, chosen=QColor(color): self._choose_swatch(chosen))
            row, col = divmod(index, 8)
            swatch_grid.addWidget(button, row, col)
            self.swatch_buttons.append(button)
        detail_layout.addLayout(swatch_grid)
        detail_layout.addStretch()
        body.addWidget(detail_card, 2)

        footer = QFrame()
        footer.setProperty("role", "dialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        DialogA2.mark_primary(self.ok_button)
        DialogA2.mark_secondary(self.cancel_button)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.ok_button)
        footer_layout.addWidget(self.cancel_button)
        root.addWidget(footer)

        self.color_field.value_changed.connect(self._on_field_changed)
        self.hue_strip.hue_changed.connect(self._on_hue_changed)
        for spin in (self.hue_spin, self.saturation_spin, self.value_spin):
            spin.valueChanged.connect(self._on_hsv_spin_changed)
        for spin in (self.red_spin, self.green_spin, self.blue_spin, self.alpha_spin):
            spin.valueChanged.connect(self._on_rgb_spin_changed)
        if not self._show_alpha:
            self.alpha_spin.setVisible(False)

    def _make_card(self):
        frame = QFrame()
        frame.setProperty("role", "dialogCard")
        return frame

    def _field_label(self, text):
        label = QLabel(text)
        label.setProperty("role", "fieldLabel")
        label.setFixedWidth(18)
        return label

    def _make_spin(self, minimum, maximum, suffix=""):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(suffix)
        spin.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        spin.setMinimumWidth(72)
        spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return spin

    def _choose_swatch(self, color):
        next_color = QColor(color)
        next_color.setAlpha(self.alpha_spin.value())
        self.set_selected_color(next_color)

    def _on_field_changed(self, saturation, value):
        color = QColor.fromHsv(self._hue, saturation, value, self.alpha_spin.value())
        self.set_selected_color(color)

    def _on_hue_changed(self, hue):
        self._hue = hue
        color = QColor.fromHsv(
            hue,
            round(self.saturation_spin.value() * 255 / 100),
            round(self.value_spin.value() * 255 / 100),
            self.alpha_spin.value(),
        )
        self.set_selected_color(color)

    def _on_hsv_spin_changed(self):
        if self._syncing:
            return
        self._hue = self.hue_spin.value()
        color = QColor.fromHsv(
            self._hue,
            round(self.saturation_spin.value() * 255 / 100),
            round(self.value_spin.value() * 255 / 100),
            self.alpha_spin.value(),
        )
        self.set_selected_color(color)

    def _on_rgb_spin_changed(self):
        if self._syncing:
            return
        self.set_selected_color(QColor(
            self.red_spin.value(),
            self.green_spin.value(),
            self.blue_spin.value(),
            self.alpha_spin.value(),
        ))

    def _update_swatch_selection(self):
        selected_name = self._selected_color.name()
        for button in self.swatch_buttons:
            button.set_selected(button.property("color").name() == selected_name)


def get_color_a2(initial_color, parent=None, title="选择颜色", show_alpha=True):
    dialog = ColorPickerDialogA2(initial_color, parent=parent, title=title, show_alpha=show_alpha)
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected_color()
    return QColor()
