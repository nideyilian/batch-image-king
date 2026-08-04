#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批图王 · 全局 UI 设计令牌（Design Tokens）单一事实来源

所有颜色 / 字体 / 尺寸 / 间距 / 圆角 / 动效的取值都必须从这里引用，
禁止在业务文件里写死色值或像素。普通图层属性面板与文字图层属性面板
共用本模块生成的控件 QSS，从而保证两套界面视觉一致。

阶段 1 改造说明（2026-08-04）：
- 本模块现为唯一事实来源；`dark_theme.CursorDarkTheme` 与 `visual_hierarchy.VisualHierarchy`
  均已改为从这里取值，不再各自维护重复的十六进制字面量。
- 共享基础值（BG_SECONDARY / BG_TERTIARY / BG_ELEVATED / TEXT_MUTED）已对齐到全局主题，
  消除令牌系统与全局主题长期存在的颜色漂移。
- 新增 Foundation 补充令牌（画布 / 标题栏 / 反转文本 / 覆盖层 / 指示器等）与 Semantic 语义别名层。
"""

from PySide6.QtGui import QColor  # noqa: F401  预留给需要 QColor 的调用方


class Tokens:
    # ===================== Foundation · 基础灰阶 =====================
    BG_PRIMARY = "#181818"        # 应用主背景 / 面板背景
    BG_SECONDARY = "#1F1F1F"      # 侧栏 / 停靠区 / 卡片背景（已对齐全局主题）
    BG_TERTIARY = "#2A2A2A"       # 普通控件背景（已对齐全局主题）
    BG_ELEVATED = "#2F2F2F"       # 输入框 / 下拉 / 弹层背景（已对齐全局主题）
    BG_CONTROL_ALT = "#242526"    # 按钮默认底
    BG_HOVER = "#303236"          # 控件 hover 底
    BG_CANVAS = "#151515"         # 中央画布工作区背景
    BG_TITLEBAR = "#202024"       # 菜单栏 / 工具栏背景
    BG_SELECTED = "#242B33"       # 列表选中底

    # ===================== Foundation · 蓝色 =====================
    ACCENT = "#2F9CF4"            # 主强调（选中 / 激活）
    ACCENT_HOVER = "#55B2FF"      # 强调 hover
    ACCENT_PRESSED = "#1F7EC8"    # 强调 pressed

    # ===================== Foundation · 红 / 黄 / 绿 =====================
    SUCCESS = "#30D158"
    WARNING = "#FF8A3D"
    ERROR = "#FF453A"
    INFO = "#38A5FF"

    # ===================== Foundation · 边框 =====================
    BORDER_PRIMARY = "#303033"    # 卡片 / 面板描边
    BORDER_SOFT = "#34383B"       # 次级描边 / 分割线
    BORDER_CONTROL = "#3A3A3D"    # 输入框 / 按钮描边
    BORDER_SUBTLE = "#252528"     # 弱分割线 / 禁用描边
    BORDER_FOCUS = "#2F9CF4"      # 焦点边框
    BORDER_INDICATOR = "#52555B"  # 复选 / 单选指示器描边

    # ===================== Foundation · 字体与文本 =====================
    TEXT_PRIMARY = "#F4F4F5"      # 主文本
    TEXT_SECONDARY = "#C7C7C9"    # 次级文本（hover 等）
    TEXT_MUTED = "#8E8E93"        # 次要 / 提示文本（已对齐全局主题）
    TEXT_DISABLED = "#606064"     # 禁用文本
    TEXT_INVERTED = "#FFFFFF"     # 反转文本（主操作按钮文字等）
    TEXT_INPUT = "#E9EEF3"        # 输入框内文本

    # ===================== Foundation · 交互覆盖层 =====================
    OVERLAY_HOVER = "rgba(255, 255, 255, 0.07)"
    OVERLAY_PRESSED = "rgba(255, 255, 255, 0.11)"
    SELECTION_BG = "#0E76D8"      # 文本选择背景
    DISABLED_CTL_BG = "#20252B"   # 禁用按钮底

    # ===================== 字体（统一使用 px，禁止 pt） =====================
    FONT_FAMILY = "Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif"
    FONT_SIZE_BASE = 13
    FONT_SIZE_SMALL = 11
    FONT_SIZE_TITLE = 13
    FONT_WEIGHT_REGULAR = 400
    FONT_WEIGHT_MEDIUM = 600
    FONT_WEIGHT_BOLD = 700

    # ===================== 尺寸 / 间距 / 圆角 =====================
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

    # ===================== 开关 =====================
    SWITCH_W = 52
    SWITCH_H = 30
    SWITCH_TRACK_MARGIN = 3
    SWITCH_KNOB = 22

    # ===================== 动效 =====================
    MOTION_MS = 150

    # ===================== Semantic · 语义别名层 =====================
    # 业务代码优先使用语义键，而非具体灰阶，便于后续统一调整层级。
    SEMANTIC = {
        "surface.app": BG_PRIMARY,
        "surface.panel": BG_SECONDARY,
        "surface.control": BG_CONTROL_ALT,
        "surface.elevated": BG_ELEVATED,
        "surface.canvas": BG_CANVAS,
        "surface.titlebar": BG_TITLEBAR,
        "text.primary": TEXT_PRIMARY,
        "text.secondary": TEXT_SECONDARY,
        "text.muted": TEXT_MUTED,
        "text.disabled": TEXT_DISABLED,
        "border.default": BORDER_PRIMARY,
        "border.soft": BORDER_SOFT,
        "border.focus": BORDER_FOCUS,
        "action.primary": ACCENT,
        "action.primary.hover": ACCENT_HOVER,
        "action.primary.pressed": ACCENT_PRESSED,
        "status.success": SUCCESS,
        "status.warning": WARNING,
        "status.error": ERROR,
        "status.info": INFO,
    }

    @classmethod
    def semantic(cls, key: str) -> str:
        """按语义键取色，未知键回退到主文本色。"""
        return cls.SEMANTIC.get(key, cls.TEXT_PRIMARY)

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
            color: {cls.TEXT_INVERTED};
            font-size: {cls.SECTION_TITLE_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QLabel[role="fieldLabel"], {selector} QLabel#fieldLabel {{
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QLabel[role="mutedLabel"], {selector} QLabel[role="summaryLabel"] {{
            color: {cls.TEXT_MUTED};
            font-size: {cls.SUMMARY_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QLabel[role="featureTitle"] {{
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FEATURE_TITLE_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QPushButton, {selector} QToolButton {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            background-color: {cls.BG_CONTROL_ALT};
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
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
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
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
            background-color: {cls.DISABLED_CTL_BG};
            border-color: {cls.BORDER_SUBTLE};
        }}
        {selector} QPushButton[segmentButton="true"], {selector} QToolButton[segmentButton="true"] {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            padding: 3px 6px;
            background-color: {cls.BG_CONTROL_ALT};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
        }}
        {selector} QPushButton[segmentButton="true"]:checked, {selector} QToolButton[segmentButton="true"]:checked {{
            background-color: {cls.ACCENT};
            border-color: {cls.ACCENT_HOVER};
            color: {cls.TEXT_INVERTED};
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QPushButton[compactValue="true"] {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            background-color: {cls.BG_ELEVATED};
            border-color: {cls.BORDER_SOFT};
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QLineEdit, {selector} QComboBox, {selector} QSpinBox, {selector} QDoubleSpinBox {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            background-color: {cls.BG_ELEVATED};
            color: {cls.TEXT_INPUT};
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            selection-background-color: {cls.SELECTION_BG};
            padding: 3px 6px;
        }}
        {selector} QTextEdit, {selector} QPlainTextEdit {{
            background-color: {cls.BG_ELEVATED};
            color: {cls.TEXT_INPUT};
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            selection-background-color: {cls.SELECTION_BG};
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
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
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
            border: 1px solid {cls.BORDER_INDICATOR};
            background: {cls.BG_ELEVATED};
        }}
        {selector} QRadioButton::indicator {{
            width: 15px;
            height: 15px;
            border-radius: 8px;
            border: 1px solid {cls.BORDER_INDICATOR};
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
        {selector} QPushButton[variant="primary"], {selector} QToolButton[variant="primary"] {{
            background-color: {cls.ACCENT};
            border: 1px solid {cls.ACCENT};
            color: {cls.TEXT_INVERTED};
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QPushButton[variant="primary"]:hover, {selector} QToolButton[variant="primary"]:hover {{
            background-color: {cls.ACCENT_HOVER};
            border-color: {cls.ACCENT_HOVER};
        }}
        {selector} QPushButton[variant="primary"]:pressed, {selector} QToolButton[variant="primary"]:pressed {{
            background-color: {cls.ACCENT_PRESSED};
            border-color: {cls.ACCENT_PRESSED};
        }}
        {selector} QPushButton[variant="secondary"], {selector} QToolButton[variant="secondary"] {{
            background-color: {cls.BG_TERTIARY};
            border: 1px solid {cls.BORDER_CONTROL};
            color: {cls.TEXT_PRIMARY};
        }}
        {selector} QPushButton[variant="secondary"]:hover, {selector} QToolButton[variant="secondary"]:hover {{
            background-color: {cls.BG_HOVER};
            border-color: {cls.BORDER_FOCUS};
        }}
        {selector} QPushButton[variant="ghost"], {selector} QToolButton[variant="ghost"] {{
            background: transparent;
            border: 1px solid {cls.BORDER_CONTROL};
            color: {cls.TEXT_SECONDARY};
        }}
        {selector} QPushButton[variant="ghost"]:hover, {selector} QToolButton[variant="ghost"]:hover {{
            background-color: {cls.BG_HOVER};
            border-color: {cls.BORDER_FOCUS};
            color: {cls.TEXT_PRIMARY};
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
        {selector} QFrame[role="previewCard"] {{
            background-color: {cls.BG_SECONDARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: {cls.SUBPANEL_RADIUS}px;
            padding: 8px;
        }}
        {selector} QLabel[role="previewTitle"] {{
            color: {cls.TEXT_INVERTED};
            font-weight: {cls.FONT_WEIGHT_BOLD};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
        }}
        {selector} QLabel[role="previewArea"] {{
            background-color: {cls.BG_ELEVATED};
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.CONTROL_RADIUS}px;
            padding: 12px;
            color: {cls.TEXT_INVERTED};
            font-size: 18px;
        }}
        """
