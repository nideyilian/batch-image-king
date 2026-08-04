"""
app/ui/theme — 批图王 shadcn/ui 设计令牌与主题系统

本包是「单一事实来源（Single Source of Truth）」的规范化承载：
- tokens.py    : shadcn/ui 语义令牌（background / foreground / primary / ...）、间距、圆角、字体、图表色、暗/亮双主题
- provider.py  : 由令牌生成全局 QSS，供所有界面继承，并提供 shadcn 按钮变体与尺寸

设计语言对齐 https://ui.shadcn.com 的默认（zinc 中性 + 蓝色 primary）规范，
暗色主题色值直接复用 app/ui/design_tokens.py，保证与现有画布/控件视觉同源。
"""

from app.ui.theme.tokens import (
    Theme,
    layout_scale,
    radius,
    spacing,
    typography,
    chart_colors,
    hsl_to_qcolor,
)
from app.ui.theme.provider import apply_theme, build_global_stylesheet, get_palette
from app.ui.theme.polisher import install_semantic_polisher, polish_widget_tree

__all__ = [
    "Theme",
    "layout_scale",
    "radius",
    "spacing",
    "typography",
    "chart_colors",
    "hsl_to_qcolor",
    "apply_theme",
    "build_global_stylesheet",
    "get_palette",
    "install_semantic_polisher",
    "polish_widget_tree",
]
