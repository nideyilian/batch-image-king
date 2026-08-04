"""
shadcn/ui 规范设计令牌（Design Tokens）

令牌命名与语义严格对齐 https://ui.shadcn.com 的默认（zinc 中性 + 蓝色 primary）规范：
    background / foreground / card / popover / primary / secondary /
    muted / accent / destructive / border / input / ring / radius

暗色主题色值直接复用 app/ui/design_tokens.py（现有画布与控件的运行期真值），
亮色主题为标准的 shadcn zinc 亮色规范。两套主题通过 ``Theme.mode`` 切换。

用法：
    from app.ui.theme import Theme
    Theme.color("primary")                 # -> "#2F9CF4"
    Theme.qc("primary", 0.9)               # -> QColor(带透明度)
    Theme.spacing("md")                    # -> 12
    Theme.radius("lg")                     # -> 8
"""
from PySide6.QtGui import QColor

# 现有运行期真值（画布/控件已在使用）——暗色主题以此为准，避免双份真值漂移。
try:
    from app.ui.design_tokens import Tokens as _T
except Exception:  # pragma: no cover - 允许独立导入用于文档生成
    class _T:  # 兜底（仅当 design_tokens 缺失时）
        BG_PRIMARY = "#181818"; BG_SECONDARY = "#1F1F1F"; BG_TERTIARY = "#2A2A2A"
        BG_ELEVATED = "#151515"; BG_HOVER = "#303236"; BG_SELECTED = "#242B33"
        BG_CONTROL_ALT = "#242526"; BORDER_PRIMARY = "#303033"; BORDER_SOFT = "#34383B"
        BORDER_CONTROL = "#3A3A3D"; TEXT_PRIMARY = "#F4F4F5"; TEXT_SECONDARY = "#C7C7C9"
        TEXT_MUTED = "#8E8E93"; TEXT_DISABLED = "#606064"; TEXT_INVERTED = "#FFFFFF"
        ACCENT = "#2F9CF4"; ACCENT_HOVER = "#55B2FF"; ACCENT_PRESSED = "#1F7EC8"
        SUCCESS = "#30D158"; WARNING = "#FF8A3D"; ERROR = "#FF453A"
        FONT_FAMILY = "Segoe UI, -apple-system, sans-serif"
        FONT_SIZE_BASE = 13; FONT_SIZE_SMALL = 11; FONT_SIZE_TITLE = 13
        FONT_WEIGHT_REGULAR = 400; FONT_WEIGHT_MEDIUM = 600; FONT_WEIGHT_BOLD = 700
        CONTROL_HEIGHT = 30; CONTROL_RADIUS = 5; CARD_RADIUS = 7
        SECTION_GAP = 8; ROW_GAP = 6; PANEL_MARGIN = 8; LABEL_WIDTH = 58
        SWITCH_W = 52; SWITCH_H = 30; INDICATOR = 16; CHECK_SIZE = 16; MOTION_MS = 150


# ---------------------------------------------------------------------------
# 主题调色板（shadcn/ui 语义令牌）
# ---------------------------------------------------------------------------
_THEMES = {
    # 暗色：直接复用 design_tokens，与现有画布/控件视觉同源
    "dark": {
        "background":          _T.BG_PRIMARY,        # 主背景 / 面板
        "foreground":          _T.TEXT_PRIMARY,      # 主文本
        "card":                _T.BG_SECONDARY,      # 卡片 / 分组
        "card-foreground":     _T.TEXT_PRIMARY,
        "popover":             _T.BG_ELEVATED,       # 弹层 / 下拉
        "popover-foreground":  _T.TEXT_PRIMARY,
        "primary":             _T.ACCENT,            # 品牌主色（蓝）
        "primary-foreground":  _T.TEXT_INVERTED,
        "secondary":           _T.BG_TERTIARY,       # 次级面
        "secondary-foreground":_T.TEXT_PRIMARY,
        "muted":               _T.BG_TERTIARY,       # 弱化面
        "muted-foreground":    _T.TEXT_MUTED,        # 次要文本
        "accent":              _T.BG_SELECTED,       # hover / 选中面
        "accent-foreground":   _T.TEXT_PRIMARY,
        "destructive":         _T.ERROR,             # 破坏性操作
        "destructive-foreground": _T.TEXT_INVERTED,
        "border":              _T.BORDER_PRIMARY,    # 卡片 / 面板描边
        "input":               _T.BORDER_CONTROL,    # 输入框 / 按钮描边
        "ring":                _T.ACCENT,            # 焦点环
        "primary-hover":       _T.ACCENT_HOVER,
        "primary-pressed":     _T.ACCENT_PRESSED,
        "hover":               _T.BG_HOVER,          # 次级/ghost hover 面
        "success":             _T.SUCCESS,
        "warning":             _T.WARNING,
        "info":                _T.ACCENT_HOVER,
        "radius":              f"{_T.CONTROL_RADIUS}px",
    },
    # 亮色：标准 shadcn zinc 亮色规范（primary 沿用品牌蓝）
    "light": {
        "background":          "#FFFFFF",
        "foreground":          "#09090B",
        "card":                "#FFFFFF",
        "card-foreground":     "#09090B",
        "popover":             "#FFFFFF",
        "popover-foreground":  "#09090B",
        "primary":             _T.ACCENT,
        "primary-foreground":  _T.TEXT_INVERTED,
        "secondary":           "#F4F4F5",
        "secondary-foreground":"#09090B",
        "muted":               "#F4F4F5",
        "muted-foreground":    "#71717A",
        "accent":              "#F4F4F5",
        "accent-foreground":   "#09090B",
        "destructive":         "#EF4444",
        "destructive-foreground": "#FAFAFA",
        "border":              "#E4E4E7",
        "input":               "#E4E4E7",
        "ring":                _T.ACCENT,
        "primary-hover":       "#1F7EC8",
        "primary-pressed":     "#176BB0",
        "hover":               "#E4E4E7",
        "success":             "#16A34A",
        "warning":             "#EA580C",
        "info":                _T.ACCENT_HOVER,
        "radius":              f"{_T.CONTROL_RADIUS}px",
    },
}

# shadcn 默认图表配色（用于统计/预览/批量导出报告等可视化）
_CHART_COLORS = [
    _T.ACCENT,      # blue
    _T.SUCCESS,     # green
    _T.WARNING,     # orange
    _T.ERROR,       # red
    "#8E8E93",      # gray
    _T.ACCENT_HOVER,
    "#A855F7",      # purple
    "#EAB308",      # yellow
]

# 间距（px）— shadcn/Tailwind 4px 基数
_SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "2xl": 24, "3xl": 32}

# 圆角（px）
_RADIUS = {"sm": 4, "md": 6, "lg": 8, "xl": 12}

# 字体
_TYPOGRAPHY = {
    "family": _T.FONT_FAMILY,
    "size": {
        "xs": 10,
        "sm": _T.FONT_SIZE_SMALL,    # 11
        "base": _T.FONT_SIZE_BASE,   # 13
        "md": _T.FONT_SIZE_BASE,
        "lg": 15,
        "xl": 18,
        "title": _T.FONT_SIZE_TITLE,
        "2xl": 22,
    },
    "weight": {
        "regular": _T.FONT_WEIGHT_REGULAR,
        "medium": _T.FONT_WEIGHT_MEDIUM,
        "bold": _T.FONT_WEIGHT_BOLD,
    },
}

# 控件高度（px）— shadcn 控件尺寸规范
_LAYOUT = {
    "control_height": _T.CONTROL_HEIGHT,       # 30
    "control_height_sm": 30,
    "control_height_lg": 36,
    "icon_button": 36,
    "switch_w": _T.SWITCH_W,
    "switch_h": _T.SWITCH_H,
    "indicator": _T.INDICATOR,
    "label_width": _T.LABEL_WIDTH,
    "motion_ms": _T.MOTION_MS,
    "section_gap": _T.SECTION_GAP,
    "row_gap": _T.ROW_GAP,
    "panel_margin": _T.PANEL_MARGIN,
}


def hsl_to_qcolor(h: float, s: float, l: float, a: float = 1.0) -> QColor:
    """由 HSL 分量构造 QColor（shadcn 令牌以 HSL 通道定义，便于做透明度叠加）。"""
    c = QColor()
    c.setHslF(((h % 360) / 360.0), max(0.0, min(1.0, s / 100.0)),
              max(0.0, min(1.0, l / 100.0)), max(0.0, min(1.0, a)))
    return c


class Theme:
    """全局主题访问器。所有颜色/尺寸都必须经由此处获取，禁止在业务代码写死色值。"""

    _mode = "dark"
    _on_change = []

    # ---- 模式 ----
    @classmethod
    def mode(cls) -> str:
        return cls._mode

    @classmethod
    def set_mode(cls, mode: str) -> None:
        if mode not in _THEMES:
            mode = "dark"
        if mode != cls._mode:
            cls._mode = mode
            for cb in cls._on_change:
                try:
                    cb(mode)
                except Exception:
                    pass

    @classmethod
    def toggle_mode(cls) -> str:
        cls.set_mode("light" if cls._mode == "dark" else "dark")
        return cls._mode

    @classmethod
    def on_change(cls, cb):
        cls._on_change.append(cb)

    # ---- 颜色 ----
    @classmethod
    def colors(cls) -> dict:
        return _THEMES[cls._mode]

    @classmethod
    def color(cls, name: str, default: str = "#000000") -> str:
        return cls.colors().get(name, default)

    @classmethod
    def qc(cls, name: str, alpha: float = 1.0) -> QColor:
        """返回带透明度的 QColor（用于代码侧绘制，如画布/图表）。"""
        hex_color = cls.color(name)
        c = QColor(hex_color)
        if alpha < 1.0:
            c.setAlphaF(alpha)
        return c

    # ---- 间距 / 圆角 / 字体 / 布局 ----
    @classmethod
    def spacing(cls, key: str) -> int:
        return _SPACING.get(key, 12)

    @classmethod
    def radius(cls, key: str) -> int:
        return _RADIUS.get(key, 6)

    @classmethod
    def font(cls, key: str) -> str:
        return _TYPOGRAPHY["family"]

    @classmethod
    def font_size(cls, key: str) -> int:
        return _TYPOGRAPHY["size"].get(key, 13)

    @classmethod
    def font_weight(cls, key: str) -> int:
        return _TYPOGRAPHY["weight"].get(key, 400)

    @classmethod
    def layout(cls, key: str):
        return _LAYOUT.get(key)

    @classmethod
    def chart_color(cls, index: int) -> str:
        return _CHART_COLORS[index % len(_CHART_COLORS)]


# 便捷导出（供 provider / 组件库直接引用）
spacing = lambda k="md": Theme.spacing(k)          # noqa: E731
radius = lambda k="md": Theme.radius(k)            # noqa: E731
typography = _TYPOGRAPHY
chart_colors = _CHART_COLORS
layout_scale = _LAYOUT
