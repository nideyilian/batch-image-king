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
        # 历史调用方（layer_item / layer_panel_base 等 20 处）沿用 'primary'
        # 命名；语义等价于 'accent'，指向同一批 Tokens，保持单一事实来源。
        'primary': {
            'main': "ACCENT",
            'light': "ACCENT_HOVER",
            'dark': "ACCENT_PRESSED",
            'contrast': "TEXT_INVERTED",
        },
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
        # 历史调用方（layer_item 的悬停/按下/选中态）沿用 'interactive' 命名
        'interactive': {
            'hover': "OVERLAY_HOVER",
            'active': "OVERLAY_PRESSED",
            'selected': "BG_SELECTED",
            'focus': "ACCENT_HOVER",
        },
    }

    # 字体族 + 字号梯级角色表。
    # 早期版本 FONTS 兼作「族名映射」和「角色 → 字号」两用，token 改造时
    # 退化成了只有 UI/MONO 的族名表，导致 vh.FONTS['body'] 直接 KeyError、
    # layer_item 构造失败、图层面板渲染 0 项。此处显式拆成两张表。
    FONT_FAMILIES = {
        'UI': "Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI, sans-serif",
        'MONO': "Cascadia Code, Consolas, Menlo, monospace",
    }

    # 角色 → {size(px), weight}。字号严格对齐 docs/UI设计规范.md §3.2：
    # base 13px / small 11px，不新增 12px 之外的档位。
    FONTS = {
        'title': {'size': 16, 'weight': 700},
        'subtitle': {'size': 14, 'weight': 600},
        'body': {'size': 13, 'weight': 400},
        'button': {'size': 13, 'weight': 600},
        'small': {'size': 11, 'weight': 400},
        'tiny': {'size': 10, 'weight': 400},
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
        cls._cache["ready"] = True

    @classmethod
    def get_spacing(cls, key):
        cls._ensure()
        return cls.SPACING.get(key, 8)

    @classmethod
    def get_font(cls, role='body', size=None, weight=None):
        """按角色返回 QFont。

        role 命中 FONTS 角色表时，取该角色的字号与字重；显式传入 size/weight
        则以入参覆盖。role 也能传 'UI'/'MONO' 直接取字体族。
        """
        cls._ensure()
        spec = cls.FONTS.get(role)
        if isinstance(spec, dict):
            family = cls.FONT_FAMILIES['UI']
            point_size = spec['size'] if size is None else size
            font_weight = spec['weight'] if weight is None else weight
        else:
            family = spec or cls.FONT_FAMILIES['UI']
            point_size = 13 if size is None else size
            font_weight = 400 if weight is None else weight
        font = QFont(family)
        # 规范统一用 px（docs/UI设计规范.md §3.2）；setPixelSize 避免 DPI 下 pt 换算漂移。
        font.setPixelSize(int(point_size))
        font.setWeight(QFont.Weight(int(font_weight)))
        return font

    @classmethod
    def get_color(cls, group, key, fallback='#888888'):
        """返回 QSS 可直接拼接的颜色**字符串**。

        必须返回 str：全部 108 处调用都是 f-string 拼进样式表，
        返回 QColor 会被 str() 成 'PySide6.QtGui.QColor.fromRgbF(...)'，
        导致整段 QSS 声明失效（静默降级为默认样式）。
        """
        cls._ensure()
        token_name = cls.COLORS.get(group, {}).get(key)
        if not token_name:
            return fallback
        value = cls._tokens.get(token_name, fallback)
        # Tokens 里的 rgba(...) 不是 QColor 的合法输入，但 QSS 原生支持，
        # 因此先做有效性探测：无效则原样透传给 QSS。
        if isinstance(value, str) and not QColor(value).isValid():
            return value
        return value if isinstance(value, str) else fallback

    @classmethod
    def get_radius(cls, key='md'):
        cls._ensure()
        return cls.RADIUS.get(key, 6)
