#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable Dialog A2 styling tokens for modal windows.

收敛说明（P0）：
- 本模块所有颜色 / 字重常量现已改为从 ``app.ui.theme.Theme`` 读取，
  与全局 shadcn 设计令牌统一为**单一真源**，不再硬编码任何色值。
- 弹窗外观由 ``app.ui.theme.provider.build_global_stylesheet`` 中的
  ``[dialogA2="true"]`` 选择器统一承载（见 provider.py）。
- ``apply`` 只负责给对话框打上 ``dialogA2`` 属性标记，不再单独
  ``setStyleSheet``，从而消除与全局样式重叠的「第三套 QSS」，
  并让弹窗在暗/亮主题切换时自动跟随全局规范层。
"""

from app.ui.theme import Theme


class DialogA2:
    """Design tokens and helpers for dark, task-focused dialogs."""

    # ---- 布局 / 尺寸常量（非颜色，保持原值） ----
    OUTER_MARGIN = 20
    CONTENT_GAP = 12
    CARD_MARGIN = (14, 12, 14, 12)
    CARD_GAP = 10
    CARD_RADIUS = 6
    CONTROL_HEIGHT = 32
    BUTTON_HEIGHT = 34
    BUTTON_WIDTH = 80
    SMALL_BUTTON_WIDTH = 56
    FIELD_LABEL_WIDTH = 82
    SWATCH_SIZE = 28
    PREVIEW_SWATCH_SIZE = 68

    TITLE_FONT_SIZE = 16
    SECTION_TITLE_FONT_SIZE = 13
    FIELD_FONT_SIZE = 12
    HINT_FONT_SIZE = 11

    FONT_WEIGHT_BOLD = 700
    FONT_WEIGHT_MEDIUM = 600

    # ---- 颜色常量（统一从 Theme 读取，单一真源） ----
    PANEL_BG = Theme.color("background")
    CARD_BG = Theme.color("card")
    TITLE_BG = Theme.color("secondary")
    SUBPANEL_BG = Theme.color("background")
    CONTROL_BG = Theme.color("background")
    CONTROL_BG_ALT = Theme.color("secondary")
    CONTROL_BG_HOVER = Theme.color("hover")
    BORDER = Theme.color("border")
    BORDER_SOFT = Theme.color("border")
    BORDER_CONTROL = Theme.color("input")
    TEXT_PRIMARY = Theme.color("foreground")
    TEXT_MUTED = Theme.color("muted-foreground")
    TEXT_DISABLED = Theme.color("muted-foreground")
    ACCENT = Theme.color("primary")
    ACCENT_HOVER = Theme.color("primary-hover")
    ACCENT_PRESSED = Theme.color("primary-pressed")

    # 与 property_panel_a2 / design_tokens 对齐的语义别名（现统一取自 Theme）
    TEXT_INVERTED = Theme.color("primary-foreground")
    TEXT_INPUT = Theme.color("foreground")
    SELECTION_BG = Theme.color("primary")
    DISABLED_CTL_BG = Theme.color("secondary")
    BORDER_SUBTLE = Theme.color("border")
    BORDER_INDICATOR = Theme.color("input")
    BG_ELEVATED = Theme.color("popover")

    @classmethod
    def apply(cls, dialog):
        """给对话框打上 dialogA2 标记，外观交由全局 shadcn 规范层统一渲染。"""
        dialog.setProperty("dialogA2", True)

    @classmethod
    def stylesheet(cls):
        """兼容旧调用，返回全局主题生成的 DialogA2 规则。"""
        from app.ui.theme.provider import build_global_stylesheet
        return build_global_stylesheet()

    @classmethod
    def mark_primary(cls, button):
        button.setProperty("primaryButton", True)
        button.setFixedSize(cls.BUTTON_WIDTH, cls.BUTTON_HEIGHT)

    @classmethod
    def mark_secondary(cls, button):
        button.setProperty("secondaryButton", True)
        button.setFixedSize(cls.BUTTON_WIDTH, cls.BUTTON_HEIGHT)
