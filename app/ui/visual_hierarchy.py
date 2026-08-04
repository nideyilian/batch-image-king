#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VisualHierarchy — 兼容适配层（阶段 1 改造，2026-08-04）

历史上 VisualHierarchy 直接引用 CursorDarkTheme 的十六进制常量，造成第三套颜色定义。
现改为从 `app.ui.design_tokens.Tokens`（唯一事实来源）读取颜色，自身只保留：
- 布局令牌（FONT / SPACING / RADIUS / SHADOWS），这些属于视觉层级而非颜色；
- 按语义归类的颜色索引 COLORS；
- 对外方法 get_spacing / get_font / get_color / get_radius。

调用方（如 status_indicators）无需修改。
"""

from PySide6.QtGui import QColor, QFont


class VisualHierarchy:
    # 颜色全部取自 Tokens，仅做语义归类
    COLORS = {
        'accent': {
            'main': "ACCENT",
            'light': "ACCENT_HOVER",
            'dark': "ACCENT_PRESSED",
            'contrast': "TEXT_INVERTED",
        },
        'text': {
            'primary': "TEXT_PRIMARY",
            'secondary': "TEXT_SECONDARY",
            'disabled': "TEXT_DISABLED",
            'hint': "TEXT_MUTED",
        },
        'background': {
            'primary': "BG_PRIMARY",
            'secondary': "BG_SECONDARY",
            'surface': "BG_TERTIARY",
            'panel': "BG_ELEVATED",
        },
        'border': {
            'primary': "BORDER_PRIMARY",
            'secondary': "BORDER_SOFT",
            'focus': "BORDER_FOCUS",
            'divider': "BORDER_PRIMARY",
        },
        'status': {
            'success': "SUCCESS",
            'warning': "WARNING",
            'error': "ERROR",
            'info': "INFO",
        },
        # 兼容旧调用方（ToastMessage 等）使用的 'state' 语义组
        'state': {
            'success': "SUCCESS",
            'warning': "WARNING",
            'error': "ERROR",
            'info': "INFO",
        },
        'overlay': {
            'hover': "OVERLAY_HOVER",
            'active': "OVERLAY_PRESSED",
            'selected': "BG_SELECTED",
        },
    }

    FONTS = {
        'UI': "Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI, sans-serif",
        'MONO': "Cascadia Code, Consolas, Menlo, monospace",
    }

    SPACING = {
        'xs': 4,
        'sm': 8,
        'md': 12,
        'lg': 16,
        'xl': 24,
    }

    RADIUS = {
        'sm': 4,
        'md': 6,
        'lg': 8,
    }

    SHADOWS = {
        'none': "none",
        'sm': "0 1px 2px rgba(0,0,0,0.4)",
        'md': "0 2px 8px rgba(0,0,0,0.5)",
    }

    _cache = {}

    @classmethod
    def _ensure(cls):
        if cls._cache:
            return
        from app.ui.design_tokens import Tokens
        cls._tokens = {k: v for k, v in vars(Tokens).items() if not k.startswith("_") and k.isupper()}

    @classmethod
    def get_spacing(cls, group, key):
        cls._ensure()
        return cls.SPACING.get(key, 8)

    @classmethod
    def get_font(cls, role='UI', size=13, weight=400):
        cls._ensure()
        return QFont(cls.FONTS.get(role, cls.FONTS['UI']), size, weight)

    @classmethod
    def get_color(cls, group, key, fallback='#888888'):
        cls._ensure()
        token_name = cls.COLORS.get(group, {}).get(key)
        if not token_name:
            return QColor(fallback)
        value = cls._tokens.get(token_name, fallback)
        try:
            return QColor(value)
        except Exception:
            return QColor(fallback)

    @classmethod
    def get_radius(cls, key='md'):
        cls._ensure()
        return cls.RADIUS.get(key, 6)
