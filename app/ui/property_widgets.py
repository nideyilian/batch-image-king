#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批图王 · 统一属性面板组件库

所有属性面板（普通图层 / 文字图层 / 异形图层等）必须从这里取件，
禁止在业务代码里自绘或写死样式。控件样式统一引用 design_tokens。
"""

from PySide6.QtWidgets import QCheckBox, QLabel, QHBoxLayout
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter

from app.ui.design_tokens import Tokens
from app.ui.collapsible_group import CollapsibleGroupBox


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


class PropertySection(CollapsibleGroupBox):
    """统一的可折叠分组（令牌驱动的 CollapsibleGroupBox 别名）。

    后续新增属性面板请直接使用本类，保持分组外观一致。
    """
    pass


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
