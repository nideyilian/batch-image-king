#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批图王 · 全局 UI 设计令牌（Design Tokens）单一事实来源

所有颜色 / 字体 / 尺寸 / 间距 / 圆角 / 动效的取值都必须从这里引用，
禁止在业务文件里写死色值或像素。普通图层属性面板与文字图层属性面板
共用本模块生成的控件 QSS，从而保证两套界面视觉一致。
"""

from PySide6.QtGui import QColor  # noqa: F401  预留给需要 QColor 的调用方


class Tokens:
    # ---------------- 色彩 ----------------
    BG_PRIMARY = "#181818"        # 主背景 / 面板背景
    BG_SECONDARY = "#202123"      # 卡片 / 分组背景
    BG_TERTIARY = "#2A2B2E"       # 分组标题 / 表头
    BG_ELEVATED = "#111315"       # 输入框 / 下拉背景
    BG_CONTROL_ALT = "#242526"    # 按钮默认底
    BG_HOVER = "#303236"          # 控件 hover 底
    BORDER_PRIMARY = "#303033"    # 卡片 / 面板描边
    BORDER_SOFT = "#34383B"       # 次级描边 / 分割线
    BORDER_CONTROL = "#3A3A3D"    # 输入框 / 按钮描边
    TEXT_PRIMARY = "#F4F4F5"      # 主文本
    TEXT_MUTED = "#8E95A3"        # 次要 / 提示文本
    TEXT_DISABLED = "#606064"     # 禁用文本
    TEXT_SECONDARY = "#C7C7C9"    # 次级文本（hover 等）
    ACCENT = "#2F9CF4"            # 主强调（选中 / 激活）
    ACCENT_HOVER = "#55B2FF"      # 强调 hover
    ACCENT_PRESSED = "#1F7EC8"    # 强调 pressed
    SUCCESS = "#30D158"
    WARNING = "#FF8A3D"
    ERROR = "#FF453A"

    # ---------------- 字体（统一使用 px，禁止 pt） ----------------
    FONT_FAMILY = "Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif"
    FONT_SIZE_BASE = 13
    FONT_SIZE_SMALL = 11
    FONT_SIZE_TITLE = 13
    FONT_WEIGHT_REGULAR = 400
    FONT_WEIGHT_MEDIUM = 600
    FONT_WEIGHT_BOLD = 700

    # ---------------- 尺寸 / 间距 / 圆角 ----------------
    CONTROL_HEIGHT = 30           # 所有输入框 / 按钮 / 下拉统一高度
    CONTROL_RADIUS = 5
    CARD_RADIUS = 7
    HEADER_HEIGHT = 36            # 分组标题高度
    BODY_MARGINS = (10, 8, 10, 8)
    SUBPANEL_MARGINS = (8, 6, 8, 6)
    HEADER_MARGINS = (8, 4, 7, 4)
    GROUP_CONTENT_MARGINS = (8, 8, 8, 9)
    PANEL_MARGIN = 8
    ROW_GAP = 6
    SECTION_GAP = 8
    SEGMENT_GAP = 5
    LABEL_WIDTH = 58
    SECONDARY_LABEL_WIDTH = 40
    POSITION_LABEL_WIDTH = 22
    SPIN_WIDTH = 76
    COLOR_SWATCH_SIZE = 30
    ICON_BUTTON_WIDTH = 42
    COLLAPSE_BUTTON_SIZE = 18
    ACTION_BUTTON_WIDTH = 56
    ALIGN_BUTTON_MIN_WIDTH = 56
    FONT_BUTTON_MIN_WIDTH = 56
    FEATURE_TOGGLE_HEIGHT = 48
    BUTTON_RADIUS = 5
    INDICATOR_RADIUS = 4
    SUBPANEL_RADIUS = 6

    SECTION_TITLE_FONT_SIZE = 13
    FIELD_LABEL_FONT_SIZE = 12
    SUMMARY_FONT_SIZE = 11
    FEATURE_TITLE_FONT_SIZE = 15
    TEXT_AREA_HEIGHT = 96
    INDICATOR = 16                 # 复选 / 单选指示器边长

    # ---------------- 开关 ----------------
    SWITCH_W = 52
    SWITCH_H = 30
    SWITCH_TRACK_MARGIN = 3
    SWITCH_KNOB = 22

    # ---------------- 动效 ----------------
    MOTION_MS = 150

    # ------------------------------------------------------------------
    # QSS 生成器：两套属性面板共用，保证控件外观完全一致
    # ------------------------------------------------------------------
    @classmethod
    def control_qss(cls, selector):
        """通用控件样式（按钮 / 输入 / 下拉 / 分段 / 复选 / 滑块 / 开关）。"""
        return f"""
        {selector} {{
            background: {cls.BG_PRIMARY};
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FONT_SIZE_BASE}px;
            font-family: {cls.FONT_FAMILY};
        }}
        {selector} QLabel {{
            color: {cls.TEXT_PRIMARY};
            background: transparent;
            font-size: {cls.FONT_SIZE_BASE}px;
        }}
        {selector} QLabel[role="sectionTitle"] {{
            color: #FFFFFF;
            font-size: {cls.SECTION_TITLE_FONT_SIZE}px;
            font-weight: 700;
        }}
        {selector} QLabel[role="fieldLabel"], {selector} QLabel#fieldLabel {{
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: 700;
        }}
        {selector} QLabel[role="mutedLabel"], {selector} QLabel[role="summaryLabel"] {{
            color: {cls.TEXT_MUTED};
            font-size: {cls.SUMMARY_FONT_SIZE}px;
            font-weight: 700;
        }}
        {selector} QLabel[role="featureTitle"] {{
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FEATURE_TITLE_FONT_SIZE}px;
            font-weight: 700;
        }}
        {selector} QPushButton, {selector} QToolButton {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            background-color: {cls.BG_CONTROL_ALT};
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: 600;
            padding: 3px 8px;
        }}
        {selector} QAbstractButton[actionButton="true"] {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            background-color: {cls.BG_CONTROL_ALT};
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: 600;
            padding: 3px 8px;
        }}
        {selector} QPushButton:hover, {selector} QToolButton:hover {{
            background-color: {cls.BG_HOVER};
            border-color: {cls.ACCENT_HOVER};
        }}
        {selector} QPushButton:pressed, {selector} QToolButton:pressed {{
            background-color: {cls.ACCENT_PRESSED};
            border-color: {cls.ACCENT};
        }}
        {selector} QPushButton:disabled, {selector} QToolButton:disabled {{
            color: {cls.TEXT_DISABLED};
            background-color: #20252B;
            border-color: #252528;
        }}
        {selector} QPushButton[segmentButton="true"], {selector} QToolButton[segmentButton="true"] {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            padding: 3px 6px;
            background-color: {cls.BG_CONTROL_ALT};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: 600;
        }}
        {selector} QPushButton[segmentButton="true"]:checked, {selector} QToolButton[segmentButton="true"]:checked {{
            background-color: {cls.ACCENT};
            border-color: {cls.ACCENT_HOVER};
            color: #FFFFFF;
            font-weight: 700;
        }}
        {selector} QPushButton[compactValue="true"] {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            background-color: {cls.BG_ELEVATED};
            border-color: {cls.BORDER_SOFT};
            font-weight: 700;
        }}
        {selector} QLineEdit, {selector} QComboBox, {selector} QSpinBox, {selector} QDoubleSpinBox {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            background-color: {cls.BG_ELEVATED};
            color: #E9EEF3;
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            selection-background-color: #0E76D8;
            padding: 3px 6px;
        }}
        {selector} QTextEdit, {selector} QPlainTextEdit {{
            background-color: {cls.BG_ELEVATED};
            color: #E9EEF3;
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            selection-background-color: #0E76D8;
            padding: 3px 6px;
        }}
        {selector} QLineEdit:focus, {selector} QTextEdit:focus, {selector} QComboBox:focus,
        {selector} QSpinBox:focus, {selector} QDoubleSpinBox:focus {{
            border-color: {cls.ACCENT};
        }}
        {selector} QCheckBox, {selector} QRadioButton {{
            color: {cls.TEXT_PRIMARY};
            spacing: 6px;
            font-size: {cls.FONT_SIZE_BASE}px;
        }}
        {selector} QCheckBox[role="inlineCheck"] {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: 600;
        }}
        {selector} QCheckBox[role="switch"] {{
            min-width: {cls.SWITCH_W}px;
            max-width: {cls.SWITCH_W}px;
            min-height: {cls.SWITCH_H}px;
            max-height: {cls.SWITCH_H}px;
            background: transparent;
        }}
        {selector} QCheckBox::indicator {{
            width: {cls.INDICATOR}px;
            height: {cls.INDICATOR}px;
            border-radius: 4px;
            border: 1px solid #52555B;
            background: {cls.BG_ELEVATED};
        }}
        {selector} QRadioButton::indicator {{
            width: 15px;
            height: 15px;
            border-radius: 8px;
            border: 1px solid #52555B;
            background: {cls.BG_ELEVATED};
        }}
        {selector} QCheckBox::indicator:checked, {selector} QRadioButton::indicator:checked {{
            background: {cls.ACCENT};
            border-color: {cls.ACCENT_HOVER};
        }}
        {selector} QCheckBox[role="switch"]::indicator {{
            width: 0px;
            height: 0px;
            border: none;
            background: transparent;
        }}
        {selector} QSlider::groove:horizontal {{
            height: 4px;
            background: {cls.BORDER_CONTROL};
            border-radius: 2px;
        }}
        {selector} QSlider::sub-page:horizontal {{
            background: {cls.ACCENT};
            border-radius: 2px;
        }}
        {selector} QSlider::handle:horizontal {{
            background: {cls.ACCENT_HOVER};
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        """

    @classmethod
    def panel_qss(cls, selector):
        """控件样式 + 卡片/分组角色样式（文字图层面板使用）。"""
        return cls.control_qss(selector) + f"""
        {selector} QFrame[role="section"] {{
            background-color: {cls.BG_SECONDARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: {cls.CARD_RADIUS}px;
        }}
        {selector} QFrame[role="sectionHeader"] {{
            background-color: {cls.BG_TERTIARY};
            border: none;
            border-bottom: 1px solid {cls.BORDER_SOFT};
            border-top-left-radius: {cls.CARD_RADIUS}px;
            border-top-right-radius: {cls.CARD_RADIUS}px;
        }}
        {selector} QFrame[role="sectionBody"] {{
            background-color: transparent;
            border: none;
        }}
        {selector} QFrame[role="subPanel"] {{
            background-color: {cls.BG_ELEVATED};
            border: 1px solid {cls.BORDER_SOFT};
            border-radius: {cls.SUBPANEL_RADIUS}px;
        }}
        {selector} QFrame[role="parameterGrid"] {{
            background-color: transparent;
            border: none;
        }}
        {selector} QFrame[role="coreDivider"] {{
            background-color: {cls.BORDER_SOFT};
            border: none;
        }}
        """
