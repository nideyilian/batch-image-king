#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批图王 · 统一属性面板组件库

所有属性面板（普通图层 / 文字图层 / 异形图层等）必须从这里取件，
禁止在业务代码里自绘或写死样式。控件样式统一引用 design_tokens。
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter

from app.ui.design_tokens import Tokens


class PropertySwitch(QCheckBox):
    """统一开关控件（自绘，普通图层与文字图层共用同一实现）。

    作为 QCheckBox 的子类，原本连接 .toggled / .setChecked / .blockSignals /
    .isChecked 的代码无需改动即可直接使用。
    """

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("role", "switch")
        self.setFixedSize(Tokens.SWITCH_W, Tokens.SWITCH_H)
        self.setFocusPolicy(Qt.StrongFocus)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        width, height = Tokens.SWITCH_W, Tokens.SWITCH_H
        margin = Tokens.SWITCH_TRACK_MARGIN
        knob_size = Tokens.SWITCH_KNOB
        track_rect = QRectF(
            margin,
            margin + 1,
            width - margin * 2,
            height - margin * 2 - 2,
        )

        if self.isEnabled():
            track_color = Tokens.ACCENT if self.isChecked() else Tokens.BORDER_CONTROL
            knob_color = Tokens.TEXT_INVERTED
            border_color = Tokens.ACCENT_HOVER if self.isChecked() else Tokens.BORDER_SOFT
        else:
            track_color = Tokens.BG_SELECTED
            knob_color = Tokens.TEXT_MUTED
            border_color = Tokens.BORDER_SUBTLE

        painter.setPen(QColor(border_color))
        painter.setBrush(QColor(track_color))
        painter.drawRoundedRect(track_rect, track_rect.height() / 2, track_rect.height() / 2)

        knob_y = (height - knob_size) / 2
        knob_x = width - knob_size - margin - 2 if self.isChecked() else margin + 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(knob_color))
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_size, knob_size))


class PropertySection(QFrame):
    """属性侧边栏的扁平分区。

    分区没有独立卡片背景、圆角或阴影，仅通过标题、细分隔线与间距建立层级。
    ``collapsed`` 参数仅为兼容旧调用保留，顶层分区始终完整展示。
    """

    def __init__(self, title="", collapsed=False, parent=None):
        super().__init__(parent)
        self.collapsed = False
        self.content_widget = None
        self.setProperty("role", "propertySection")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.title_frame = QFrame(self)
        self.title_frame.setProperty("role", "propertySectionHeader")
        self.title_frame.setFixedHeight(
            Tokens.SIDEBAR_TITLE_LINE_HEIGHT + Tokens.SIDEBAR_SECTION_PADDING_TOP
        )
        title_layout = QHBoxLayout(self.title_frame)
        title_layout.setContentsMargins(0, Tokens.SIDEBAR_SECTION_PADDING_TOP, 0, 0)
        title_layout.setSpacing(0)

        self.title_label = QLabel(title, self.title_frame)
        self.title_label.setProperty("role", "propertySectionTitle")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch(1)
        self.main_layout.addWidget(self.title_frame)

        self.content_container = QFrame(self)
        self.content_container.setProperty("role", "propertySectionBody")
        self.container_layout = QVBoxLayout(self.content_container)
        self.container_layout.setContentsMargins(
            0,
            Tokens.ROW_GAP,
            0,
            Tokens.SIDEBAR_SECTION_PADDING_BOTTOM,
        )
        self.container_layout.setSpacing(Tokens.ROW_GAP)
        self.main_layout.addWidget(self.content_container)

    def set_content_widget(self, widget):
        if self.content_widget is not None:
            self.container_layout.removeWidget(self.content_widget)
        self.content_widget = widget
        if widget is not None:
            self.container_layout.addWidget(widget)

    def add_content_layout(self, layout):
        self.container_layout.addLayout(layout)

    def set_collapsed(self, collapsed):
        self.collapsed = False
        self.content_container.setVisible(True)

    def is_collapsed(self):
        return False


def switch_row(label_text, switch=None):
    """统一「左标题 + 右侧开关」行布局。

    返回 (QHBoxLayout, PropertySwitch)。标题使用 featureTitle 角色，
    与普通图层/文字图层面板的分组标题风格一致。
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    label = QLabel(label_text)
    label.setProperty("role", "featureTitle")
    if switch is None:
        switch = PropertySwitch()
    row.addWidget(label)
    row.addStretch(1)
    row.addWidget(switch)
    return row, switch
