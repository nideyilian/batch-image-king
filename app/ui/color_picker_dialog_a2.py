#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dialog A2 color picker used instead of the native QColorDialog."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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


class _ColorSwatchButton(QPushButton):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setProperty("color", self._color)
        self.setFixedSize(DialogA2.SWATCH_SIZE, DialogA2.SWATCH_SIZE)
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
                border-radius: 4px;
                min-width: {DialogA2.SWATCH_SIZE - width * 2}px;
                max-width: {DialogA2.SWATCH_SIZE - width * 2}px;
                min-height: {DialogA2.SWATCH_SIZE - width * 2}px;
                max-height: {DialogA2.SWATCH_SIZE - width * 2}px;
                padding: 0;
            }}
        """)


class ColorPickerDialogA2(QDialog):
    """Compact dark color picker with preset swatches and RGB/HEX inputs."""

    BASIC_COLORS = [
        "#000000", "#ff0000", "#00a000", "#c76d00", "#00c000", "#b8b800", "#00ff00", "#8cff00",
        "#0000a8", "#b000a8", "#006a88", "#b05a80", "#00a88a", "#b8b88d", "#00f0a0", "#92f080",
        "#0000ff", "#a000ff", "#006cff", "#a060ff", "#00b8e8", "#a6a6ff", "#00eeee", "#b4ffff",
        "#6e0000", "#ff1010", "#505000", "#ff5a00", "#4f9b00", "#ffaa00", "#55e600", "#ffff00",
        "#6a0088", "#ff0077", "#555588", "#ff5a92", "#58a88a", "#ffa27e", "#42e67a", "#fff68a",
        "#5500ff", "#ff00dd", "#5555ff", "#ee55ee", "#4aa8ee", "#ee90ee", "#55eeee", "#ffffff",
    ]

    def __init__(self, initial_color=None, parent=None, title="选择颜色", show_alpha=True):
        super().__init__(parent)
        self._syncing = False
        self._show_alpha = show_alpha
        self._selected_color = QColor(initial_color) if initial_color is not None else QColor(255, 255, 255, 255)
        if not self._selected_color.isValid():
            self._selected_color = QColor(255, 255, 255, 255)

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 430)
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

        self._selected_color = next_color
        self._syncing = True
        try:
            self.red_spin.setValue(next_color.red())
            self.green_spin.setValue(next_color.green())
            self.blue_spin.setValue(next_color.blue())
            self.alpha_spin.setValue(next_color.alpha())
            self.hex_edit.setText(next_color.name())
            self._update_preview()
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

        swatch_card = self._make_card()
        swatch_layout = QVBoxLayout(swatch_card)
        swatch_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        swatch_layout.setSpacing(DialogA2.CARD_GAP)
        swatch_title = QLabel("基础颜色")
        swatch_title.setProperty("role", "sectionTitle")
        swatch_layout.addWidget(swatch_title)

        swatch_grid = QGridLayout()
        swatch_grid.setHorizontalSpacing(7)
        swatch_grid.setVerticalSpacing(7)
        self.swatch_buttons = []
        for index, color in enumerate(self.BASIC_COLORS):
            button = _ColorSwatchButton(color, self)
            button.clicked.connect(lambda checked=False, chosen=QColor(color): self._choose_swatch(chosen))
            row, col = divmod(index, 8)
            swatch_grid.addWidget(button, row, col)
            self.swatch_buttons.append(button)
        swatch_layout.addLayout(swatch_grid)
        swatch_layout.addStretch()
        body.addWidget(swatch_card, 0)

        detail_card = self._make_card()
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        detail_layout.setSpacing(DialogA2.CARD_GAP)
        detail_title = QLabel("当前颜色")
        detail_title.setProperty("role", "sectionTitle")
        detail_layout.addWidget(detail_title)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(DialogA2.CONTENT_GAP)
        self.preview_swatch = QFrame()
        self.preview_swatch.setFixedSize(DialogA2.PREVIEW_SWATCH_SIZE, DialogA2.PREVIEW_SWATCH_SIZE)
        self.preview_swatch.setProperty("role", "dialogSubPanel")
        preview_row.addWidget(self.preview_swatch)
        preview_text = QLabel("使用 RGB / HEX 精确输入，支持透明度。")
        preview_text.setWordWrap(True)
        preview_text.setProperty("role", "hint")
        preview_row.addWidget(preview_text, 1)
        detail_layout.addLayout(preview_row)

        spin_grid = QGridLayout()
        spin_grid.setHorizontalSpacing(DialogA2.CONTENT_GAP)
        spin_grid.setVerticalSpacing(8)
        self.red_spin = self._make_spin()
        self.green_spin = self._make_spin()
        self.blue_spin = self._make_spin()
        self.alpha_spin = self._make_spin()
        for row, (label, spin) in enumerate((
            ("R", self.red_spin),
            ("G", self.green_spin),
            ("B", self.blue_spin),
            ("A", self.alpha_spin),
        )):
            spin_grid.addWidget(self._field_label(label), row, 0)
            spin_grid.addWidget(spin, row, 1)
        detail_layout.addLayout(spin_grid)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(DialogA2.CONTENT_GAP)
        hex_row.addWidget(self._field_label("HEX"))
        self.hex_edit = QLineEdit()
        self.hex_edit.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        self.hex_edit.editingFinished.connect(self.apply_hex_color)
        hex_row.addWidget(self.hex_edit, 1)
        detail_layout.addLayout(hex_row)

        body.addWidget(detail_card, 1)

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

        for spin in (self.red_spin, self.green_spin, self.blue_spin, self.alpha_spin):
            spin.valueChanged.connect(self._on_spin_changed)
        if not self._show_alpha:
            self.alpha_spin.setEnabled(False)

    def _make_card(self):
        frame = QFrame()
        frame.setProperty("role", "dialogCard")
        return frame

    def _field_label(self, text):
        label = QLabel(text)
        label.setProperty("role", "fieldLabel")
        label.setFixedWidth(34)
        return label

    def _make_spin(self):
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return spin

    def _choose_swatch(self, color):
        next_color = QColor(color)
        next_color.setAlpha(self.alpha_spin.value())
        self.set_selected_color(next_color)

    def _on_spin_changed(self):
        if self._syncing:
            return
        self.set_selected_color(QColor(
            self.red_spin.value(),
            self.green_spin.value(),
            self.blue_spin.value(),
            self.alpha_spin.value(),
        ))

    def _update_preview(self):
        color = self._selected_color
        self.preview_swatch.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});
                border: 1px solid {DialogA2.BORDER_CONTROL};
                border-radius: 6px;
            }}
        """)

    def _update_swatch_selection(self):
        selected_name = self._selected_color.name()
        for button in self.swatch_buttons:
            button.set_selected(button.property("color").name() == selected_name)


def get_color_a2(initial_color, parent=None, title="选择颜色", show_alpha=True):
    dialog = ColorPickerDialogA2(initial_color, parent=parent, title=title, show_alpha=show_alpha)
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected_color()
    return QColor()
