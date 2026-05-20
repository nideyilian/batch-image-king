#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视觉层级管理器
统一管理应用程序的视觉层级，包括字体、颜色、间距等设计规范
"""

from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt
from app.ui.dark_theme import CursorDarkTheme


class VisualHierarchy:
    """视觉层级管理器"""

    # 字体层级定义
    FONTS = {
        'title': {'size': 16, 'weight': QFont.Bold},        # 标题
        'subtitle': {'size': 13, 'weight': QFont.DemiBold}, # 副标题
        'body': {'size': 10, 'weight': QFont.Normal},       # 正文
        'small': {'size': 9, 'weight': QFont.Normal},       # 小字
        'tiny': {'size': 8, 'weight': QFont.Normal},        # 极小字
        'button': {'size': 10, 'weight': QFont.Medium},     # 按钮
        'input': {'size': 10, 'weight': QFont.Normal},      # 输入框
    }

    # 颜色层级定义
    COLORS = {
        'primary': {
            'main': CursorDarkTheme.ACCENT_PRIMARY,
            'light': CursorDarkTheme.ACCENT_HOVER,
            'dark': CursorDarkTheme.ACCENT_PRESSED,
            'contrast': CursorDarkTheme.TEXT_INVERTED,
        },
        'text': {
            'primary': CursorDarkTheme.TEXT_PRIMARY,
            'secondary': CursorDarkTheme.TEXT_SECONDARY,
            'disabled': CursorDarkTheme.TEXT_DISABLED,
            'hint': CursorDarkTheme.TEXT_MUTED,
        },
        'background': {
            'primary': CursorDarkTheme.BACKGROUND_PRIMARY,
            'secondary': CursorDarkTheme.BACKGROUND_SECONDARY,
            'surface': CursorDarkTheme.BACKGROUND_TERTIARY,
            'panel': CursorDarkTheme.BACKGROUND_ELEVATED,
        },
        'border': {
            'primary': CursorDarkTheme.BORDER_PRIMARY,
            'secondary': CursorDarkTheme.BORDER_SUBTLE,
            'focus': CursorDarkTheme.BORDER_FOCUS,
            'divider': CursorDarkTheme.BORDER_PRIMARY,
        },
        'state': {
            'success': CursorDarkTheme.SUCCESS,
            'warning': CursorDarkTheme.WARNING,
            'error': CursorDarkTheme.ERROR,
            'info': CursorDarkTheme.INFO,
        },
        'interactive': {
            'hover': CursorDarkTheme.HOVER_OVERLAY,
            'active': CursorDarkTheme.PRESSED_OVERLAY,
            'selected': CursorDarkTheme.SELECTED_BG,
            'focus': 'rgba(47, 156, 244, 0.28)',
        }
    }

    # 间距层级定义
    SPACING = {
        'xs': 2,        # 极小间距
        'sm': 4,        # 小间距
        'md': 8,        # 中等间距
        'lg': 12,       # 大间距
        'xl': 16,       # 极大间距
        'xxl': 24,      # 超大间距
    }

    # 圆角定义
    RADIUS = {
        'sm': 2,        # 小圆角
        'md': 4,        # 中等圆角
        'lg': 6,        # 大圆角
        'xl': 8,        # 极大圆角
    }

    # 阴影定义
    SHADOWS = {
        'light': 'rgba(0, 0, 0, 0.1)',     # 浅阴影
        'medium': 'rgba(0, 0, 0, 0.2)',    # 中等阴影
        'dark': 'rgba(0, 0, 0, 0.3)',      # 深阴影
    }

    @classmethod
    def get_font(cls, level: str, family: str = "Microsoft YaHei") -> QFont:
        """获取指定层级的字体

        Args:
            level: 字体层级 (title, subtitle, body, small, tiny, button, input)
            family: 字体族名称

        Returns:
            QFont对象
        """
        if level not in cls.FONTS:
            level = 'body'  # 默认层级

        font_config = cls.FONTS[level]
        font = QFont(family, font_config['size'])
        font.setWeight(font_config['weight'])

        return font

    @classmethod
    def get_color(cls, category: str, variant: str = 'main') -> str:
        """获取指定类别的颜色

        Args:
            category: 颜色类别 (primary, text, background, border, state, interactive)
            variant: 颜色变体 (main, light, dark, contrast等)

        Returns:
            颜色字符串
        """
        if category not in cls.COLORS:
            return cls.COLORS['text']['primary']  # 默认颜色

        color_group = cls.COLORS[category]

        if variant in color_group:
            return color_group[variant]
        elif 'main' in color_group:
            return color_group['main']
        else:
            return list(color_group.values())[0]

    @classmethod
    def get_spacing(cls, size: str) -> int:
        """获取指定大小的间距

        Args:
            size: 间距大小 (xs, sm, md, lg, xl, xxl)

        Returns:
            间距像素值
        """
        return cls.SPACING.get(size, cls.SPACING['md'])

    @classmethod
    def get_radius(cls, size: str) -> int:
        """获取指定大小的圆角

        Args:
            size: 圆角大小 (sm, md, lg, xl)

        Returns:
            圆角像素值
        """
        return cls.RADIUS.get(size, cls.RADIUS['md'])

    @classmethod
    def create_button_style(cls, state: str = 'normal', variant: str = 'primary') -> str:
        """创建按钮样式

        Args:
            state: 状态 (normal, hover, pressed, disabled)
            variant: 变体 (primary, secondary, danger)

        Returns:
            CSS样式字符串
        """
        if variant == 'primary':
            if state == 'normal':
                bg_color = cls.get_color('background', 'secondary')
                border_color = cls.get_color('border', 'primary')
                text_color = cls.get_color('text', 'primary')
            elif state == 'hover':
                bg_color = cls.get_color('background', 'surface')
                border_color = cls.get_color('border', 'focus')
                text_color = cls.get_color('text', 'primary')
            elif state == 'pressed':
                bg_color = cls.get_color('primary', 'main')
                border_color = cls.get_color('primary', 'dark')
                text_color = cls.get_color('primary', 'contrast')
            else:  # disabled
                bg_color = cls.get_color('background', 'primary')
                border_color = cls.get_color('border', 'secondary')
                text_color = cls.get_color('text', 'disabled')
        elif variant == 'secondary':
            if state == 'normal':
                bg_color = 'transparent'
                border_color = cls.get_color('border', 'secondary')
                text_color = cls.get_color('text', 'secondary')
            elif state == 'hover':
                bg_color = cls.get_color('interactive', 'hover')
                border_color = cls.get_color('border', 'primary')
                text_color = cls.get_color('text', 'primary')
            elif state == 'pressed':
                bg_color = cls.get_color('interactive', 'active')
                border_color = cls.get_color('border', 'focus')
                text_color = cls.get_color('text', 'primary')
            else:  # disabled
                bg_color = 'transparent'
                border_color = cls.get_color('border', 'secondary')
                text_color = cls.get_color('text', 'disabled')
        else:  # danger
            if state == 'normal':
                bg_color = 'transparent'
                border_color = cls.get_color('state', 'error')
                text_color = cls.get_color('state', 'error')
            elif state == 'hover':
                bg_color = cls.get_color('state', 'error')
                border_color = cls.get_color('state', 'error')
                text_color = cls.get_color('primary', 'contrast')
            elif state == 'pressed':
                bg_color = '#D32F2F'  # 更深的红色
                border_color = '#D32F2F'
                text_color = cls.get_color('primary', 'contrast')
            else:  # disabled
                bg_color = 'transparent'
                border_color = cls.get_color('border', 'secondary')
                text_color = cls.get_color('text', 'disabled')

        return f"""
            background-color: {bg_color};
            border: 1px solid {border_color};
            color: {text_color};
            border-radius: {cls.get_radius('md')}px;
            padding: {cls.get_spacing('sm')}px {cls.get_spacing('md')}px;
        """

    @classmethod
    def create_panel_style(cls, level: int = 1) -> str:
        """创建面板样式

        Args:
            level: 面板层级 (1=主面板, 2=次面板, 3=内容面板)

        Returns:
            CSS样式字符串
        """
        if level == 1:
            bg_color = cls.get_color('background', 'primary')
            border_color = cls.get_color('border', 'secondary')
        elif level == 2:
            bg_color = cls.get_color('background', 'secondary')
            border_color = cls.get_color('border', 'primary')
        else:  # level 3
            bg_color = cls.get_color('background', 'surface')
            border_color = cls.get_color('border', 'primary')

        return f"""
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: {cls.get_radius('lg')}px;
            padding: {cls.get_spacing('md')}px;
        """

    @classmethod
    def create_input_style(cls, state: str = 'normal') -> str:
        """创建输入框样式

        Args:
            state: 状态 (normal, focus, error, disabled)

        Returns:
            CSS样式字符串
        """
        bg_color = cls.get_color('background', 'surface')
        text_color = cls.get_color('text', 'primary')

        if state == 'normal':
            border_color = cls.get_color('border', 'secondary')
        elif state == 'focus':
            border_color = cls.get_color('border', 'focus')
        elif state == 'error':
            border_color = cls.get_color('state', 'error')
        else:  # disabled
            bg_color = cls.get_color('background', 'primary')
            border_color = cls.get_color('border', 'secondary')
            text_color = cls.get_color('text', 'disabled')

        return f"""
            background-color: {bg_color};
            border: 1px solid {border_color};
            color: {text_color};
            border-radius: {cls.get_radius('sm')}px;
            padding: {cls.get_spacing('sm')}px {cls.get_spacing('md')}px;
            selection-background-color: {cls.get_color('primary', 'light')};
        """

    @classmethod
    def create_divider_style(cls, orientation: str = 'horizontal') -> str:
        """创建分割线样式

        Args:
            orientation: 方向 (horizontal, vertical)

        Returns:
            CSS样式字符串
        """
        if orientation == 'horizontal':
            return f"""
                border-top: 1px solid {cls.get_color('border', 'divider')};
                margin: {cls.get_spacing('md')}px 0;
            """
        else:  # vertical
            return f"""
                border-left: 1px solid {cls.get_color('border', 'divider')};
                margin: 0 {cls.get_spacing('md')}px;
            """
