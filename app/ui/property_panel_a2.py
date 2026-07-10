#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable property-panel styling tokens for right-side property panels.

本模块仅作为 design_tokens.Tokens 的兼容外观层：所有取值来自 Tokens，
保证文字图层属性面板与普通图层属性面板使用同一套设计令牌。
"""

from app.ui.design_tokens import Tokens


class PropertyPanelA2:
    """兼容层：重新暴露 Tokens 取值，供既有代码（integrated_text_panel 等）引用。"""

    # 尺寸 / 间距 / 圆角
    PANEL_MARGIN = Tokens.PANEL_MARGIN
    CARD_GAP = Tokens.ROW_GAP
    CARD_RADIUS = Tokens.CARD_RADIUS
    HEADER_HEIGHT = Tokens.HEADER_HEIGHT
    BODY_MARGINS = Tokens.BODY_MARGINS
    SUBPANEL_MARGINS = Tokens.SUBPANEL_MARGINS
    ROW_GAP = Tokens.ROW_GAP
    SECTION_GAP = Tokens.SECTION_GAP
    SEGMENT_GAP = Tokens.SEGMENT_GAP
    CONTROL_HEIGHT = Tokens.CONTROL_HEIGHT
    TEXT_AREA_HEIGHT = Tokens.TEXT_AREA_HEIGHT
    LABEL_WIDTH = Tokens.LABEL_WIDTH
    SECONDARY_LABEL_WIDTH = Tokens.SECONDARY_LABEL_WIDTH
    POSITION_LABEL_WIDTH = Tokens.POSITION_LABEL_WIDTH
    SPIN_WIDTH = Tokens.SPIN_WIDTH
    COLOR_SWATCH_SIZE = Tokens.COLOR_SWATCH_SIZE
    ICON_BUTTON_WIDTH = Tokens.ICON_BUTTON_WIDTH
    ACTION_BUTTON_WIDTH = Tokens.ACTION_BUTTON_WIDTH
    ALIGN_BUTTON_MIN_WIDTH = Tokens.ALIGN_BUTTON_MIN_WIDTH
    FONT_BUTTON_MIN_WIDTH = Tokens.FONT_BUTTON_MIN_WIDTH
    FEATURE_TOGGLE_HEIGHT = Tokens.FEATURE_TOGGLE_HEIGHT
    SWITCH_SIZE = (Tokens.SWITCH_W, Tokens.SWITCH_H)
    SWITCH_TRACK_MARGIN = Tokens.SWITCH_TRACK_MARGIN
    SWITCH_KNOB_SIZE = Tokens.SWITCH_KNOB
    BUTTON_RADIUS = Tokens.BUTTON_RADIUS
    SUBPANEL_RADIUS = Tokens.SUBPANEL_RADIUS

    SECTION_TITLE_FONT_SIZE = Tokens.SECTION_TITLE_FONT_SIZE
    FIELD_LABEL_FONT_SIZE = Tokens.FIELD_LABEL_FONT_SIZE
    SUMMARY_FONT_SIZE = Tokens.SUMMARY_FONT_SIZE
    FEATURE_TITLE_FONT_SIZE = Tokens.FEATURE_TITLE_FONT_SIZE

    # 颜色
    PANEL_BG = Tokens.BG_PRIMARY
    CARD_BG = Tokens.BG_SECONDARY
    HEADER_BG = Tokens.BG_TERTIARY
    CONTROL_BG = Tokens.BG_ELEVATED
    CONTROL_BG_ALT = Tokens.BG_CONTROL_ALT
    CONTROL_BG_HOVER = Tokens.BG_HOVER
    BORDER = Tokens.BORDER_PRIMARY
    BORDER_SOFT = Tokens.BORDER_SOFT
    BORDER_CONTROL = Tokens.BORDER_CONTROL
    TEXT_PRIMARY = Tokens.TEXT_PRIMARY
    TEXT_MUTED = Tokens.TEXT_MUTED
    TEXT_DISABLED = Tokens.TEXT_DISABLED
    ACCENT = Tokens.ACCENT
    ACCENT_HOVER = Tokens.ACCENT_HOVER
    ACCENT_PRESSED = Tokens.ACCENT_PRESSED

    @classmethod
    def stylesheet(cls, root_selector="#IntegratedTextPanel"):
        """返回统一控件 + 卡片样式（来自 Tokens）。"""
        return Tokens.panel_qss(root_selector)
