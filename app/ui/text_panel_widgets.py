#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整合的文字图层参数模块 - 专业UI设计
遵循现代设计原则，将所有参数整合到一个紧凑的界面中
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QSlider, QFrame,
                               QToolButton, QButtonGroup, QSizePolicy, QCheckBox,
                               QTextEdit, QLineEdit, QComboBox, QScrollArea, QDialog, QCompleter,
                               QGridLayout)
from PySide6.QtCore import Qt, Signal, QSize, QStringListModel, QRectF
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QIcon

import sys
import os
import json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.text_layer import TextLayer, TextAlign, FontStyle
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.property_panel_a2 import PropertyPanelA2



class A2Switch(QCheckBox):
    """A v2 switch control used for high-level enable/disable rows."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("role", "switch")
        self.setFixedSize(*PropertyPanelA2.SWITCH_SIZE)
        self.setFocusPolicy(Qt.StrongFocus)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        width, height = PropertyPanelA2.SWITCH_SIZE
        margin = PropertyPanelA2.SWITCH_TRACK_MARGIN
        knob_size = PropertyPanelA2.SWITCH_KNOB_SIZE
        track_rect = QRectF(
            margin,
            margin + 1,
            width - margin * 2,
            height - margin * 2 - 2,
        )

        if self.isEnabled():
            track_color = PropertyPanelA2.ACCENT if self.isChecked() else "#3A3C3F"
            knob_color = "#FFFFFF"
            border_color = PropertyPanelA2.ACCENT_HOVER if self.isChecked() else "#45484C"
        else:
            track_color = "#25272A"
            knob_color = "#8E95A3"
            border_color = "#2E3033"

        painter.setPen(QColor(border_color))
        painter.setBrush(QColor(track_color))
        painter.drawRoundedRect(track_rect, track_rect.height() / 2, track_rect.height() / 2)

        knob_y = (height - knob_size) / 2
        knob_x = width - knob_size - margin - 2 if self.isChecked() else margin + 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(knob_color))
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_size, knob_size))


class ToggleButton(QToolButton):
    """切换按钮 - 用于粗体、斜体等样式切换"""
    def __init__(self, text="", checkable=True):
        super().__init__()
        self.setText(text)
        self.setCheckable(checkable)
        self.setAutoRaise(False)
        self.setProperty("actionButton", True)
        self.setFixedSize(PropertyPanelA2.ICON_BUTTON_WIDTH, PropertyPanelA2.CONTROL_HEIGHT)


class AlignButtonGroup(QWidget):
    """对齐按钮组"""
    alignment_changed = Signal(TextAlign)

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(PropertyPanelA2.SEGMENT_GAP)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        # 左对齐
        self.left_btn = QToolButton()
        self.left_btn.setText("L")
        self.left_btn.setCheckable(True)
        self.left_btn.setChecked(True)
        self.apply_button_style(self.left_btn)

        # 居中对齐
        self.center_btn = QToolButton()
        self.center_btn.setText("C")
        self.center_btn.setCheckable(True)
        self.apply_button_style(self.center_btn)

        # 右对齐
        self.right_btn = QToolButton()
        self.right_btn.setText("R")
        self.right_btn.setCheckable(True)
        self.apply_button_style(self.right_btn)

        self.button_group.addButton(self.left_btn, 0)
        self.button_group.addButton(self.center_btn, 1)
        self.button_group.addButton(self.right_btn, 2)

        layout.addWidget(self.left_btn)
        layout.addWidget(self.center_btn)
        layout.addWidget(self.right_btn)

        # 连接信号
        self.left_btn.clicked.connect(lambda: self.alignment_changed.emit(TextAlign.LEFT))
        self.center_btn.clicked.connect(lambda: self.alignment_changed.emit(TextAlign.CENTER))
        self.right_btn.clicked.connect(lambda: self.alignment_changed.emit(TextAlign.RIGHT))

    def apply_button_style(self, button):
        button.setProperty("segmentButton", True)
        button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        button.setMinimumWidth(PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_alignment(self, align):
        if align == TextAlign.LEFT:
            self.left_btn.setChecked(True)
        elif align == TextAlign.CENTER:
            self.center_btn.setChecked(True)
        elif align == TextAlign.RIGHT:
            self.right_btn.setChecked(True)


class ColorIndicator(QPushButton):
    """颜色指示器 - 点击选择颜色，带下拉箭头"""
    color_changed = Signal(tuple)  # RGBA元组

    def __init__(self, color=(0, 0, 0, 255), size=24):
        super().__init__()
        self.current_color = color
        self._indicator_size = size
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.update_color_display()
        self.clicked.connect(self.choose_color)

    def update_color_display(self):
        r, g, b, a = self.current_color
        size = self._indicator_size
        css_size = max(0, size - 2)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba({r}, {g}, {b}, {a});
                border: 1px solid {PropertyPanelA2.BORDER_CONTROL};
                border-radius: 4px;
                min-width: {css_size}px;
                max-width: {css_size}px;
                min-height: {css_size}px;
                max-height: {css_size}px;
                padding: 0;
            }}
            QPushButton:hover {{
                border-color: {PropertyPanelA2.ACCENT_HOVER};
            }}
        """)
        self.setFixedSize(size, size)
        self.setText("")

    def choose_color(self):
        from app.ui.color_picker_dialog_a2 import get_color_a2
        # 使用当前颜色的RGB值和透明度创建QColor对象
        current_r, current_g, current_b, current_a = self.current_color
        initial_color = QColor(current_r, current_g, current_b, current_a)

        color = get_color_a2(
            initial_color,
            self,
            "选择颜色"
        )
        if color.isValid():
            # 保存新的颜色（包括透明度）
            self.current_color = (color.red(), color.green(), color.blue(), color.alpha())
            self.update_color_display()
            self.color_changed.emit(self.current_color)



