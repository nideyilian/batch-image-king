#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批图王 · 统一属性面板组件库

所有属性面板（普通图层 / 文字图层 / 异形图层等）必须从这里取件，
禁止在业务代码里自绘或写死样式。控件样式统一引用 design_tokens。

═══════════════════════════════════════════════════════════════════════
表单三件套（2026-10-28 新增，属性面板栅格的唯一实现）
═══════════════════════════════════════════════════════════════════════

`field_label()` / `blank_field_label()` / `property_form()`

为什么要有这三件：属性面板曾被说「乱」，查下来不是审美问题，是**没有栅格**。
同一个面板里标签列宽实测出现 58 / 84 / 640 三种，右边缘落在 70 / 84 / 96
三个 x 坐标。原因是每个文件都自己 new 一个 QFormLayout、自己定间距、
自己 addRow("文字:", ...) —— 四套表单实现各写各的。

规则只有一条，全部收敛到这三个函数：
  · 字段标签固定 `Layout.LABEL_WIDTH`(72) 宽、右对齐、冒号连成一条竖线
  · 行距 8 / 列距 12、整行不折行、字段列可伸展
  · 整行控件（按钮、说明）用 `blank_field_label()` 占住标签列，不许从最左边起排
  · 行内子标签用 `field_label(..., inline=True)`，不参与栅格
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter

from app.ui.design_spec import Layout as _Layout
from app.ui.design_spec import Space as _Space
from app.ui.design_tokens import Tokens

#: 字段标签列宽（单一真源在 design_spec.Layout）
LABEL_WIDTH = _Layout.LABEL_WIDTH


def field_label(text, width=None, inline=False):
    """属性面板字段标签。

    Args:
        text: 文字。是否带冒号由调用点决定。
        width: 覆盖列宽（嵌套子标签用较窄的值，例如 X/Y/W/H 用 22）。
        inline: True = 行内子标签（如「描边粗细: [20] 对齐 [内描边]」的后半段），
            按内容自适应宽度，不占主标签列。
    """
    label = QLabel(text)
    label.setWordWrap(False)

    if inline:
        label.setObjectName("fieldLabelInline")
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return label

    # 宽度不是栅格值 → 嵌套子标签，语义上不占主列
    if width is not None and width != LABEL_WIDTH:
        label.setObjectName("fieldLabelInline")
        label.setFixedWidth(width)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return label

    label.setObjectName("fieldLabel")
    label.setFixedWidth(LABEL_WIDTH)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    return label


def blank_field_label():
    """占位标签列，让整行控件（按钮/说明文字）落在字段列上。

    `form.addRow("", w)` 里的空字符串会被 QFormLayout 当成宽度 0 的标签，
    字段列因此左移 —— 这就是「随机选择」「当前图像」跑到分区最左边的来源。
    """
    spacer = QWidget()
    spacer.setFixedWidth(LABEL_WIDTH)
    return spacer


def property_form(parent=None):
    """属性面板统一表单布局。

    · 列距 12 / 行距 8（design_spec.Space MD / SM）
    · 标签右对齐、字段列可伸展、**整行不折行**
      （默认 WrapLongRows 在面板变窄时会把标签和字段拆成两行，
        同一面板里有的拆有的不拆，行高忽高忽低）
    """
    form = QFormLayout(parent)
    form.setHorizontalSpacing(_Space.MD)    # 12
    form.setVerticalSpacing(_Space.SM)      # 8
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.DontWrapRows)
    return form


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


def switch_row(label_text, switch=None, role="featureTitle"):
    """统一「左标题 + 右侧开关」行布局。

    返回 (QHBoxLayout, PropertySwitch)。

    Args:
        role: 标签的 QSS 角色。
            - `featureTitle`（默认，15px bold）：用于**真正的功能分组标题**，
              例如"智能裁剪"。这是历史默认值，保持不动。
            - `fieldLabel`（12px medium）：用于属性面板里**普通字段开关**，
              例如"启用描边"—— 它和"混合模式:"是同一层级，不该比区块标题还大。
              2026-10-28 实测：属性面板里"启用描边"是 15px，比"基本属性"(14px)
              这类区块标题还大，视觉上完全失衡。
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    label = QLabel(label_text)
    label.setProperty("role", role)
    if role == "fieldLabel":
        # 与 _label() 的输出保持一致：标签比内容小一档、不抢视觉重量，
        # 并且**必须落在同一条标签列栅格上**（固定 72、右对齐）。
        # 原来只设了 objectName 没设宽度，实测这一行标签右边缘在 60，
        # 而同一个"外观"分区里其他字段在 84 —— 又是一条错位的竖线。
        label.setObjectName("fieldLabel")
        label.setFixedWidth(_Layout.LABEL_WIDTH)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if switch is None:
        switch = PropertySwitch()
    row.addWidget(label)
    row.addStretch(1)
    row.addWidget(switch)
    return row, switch
