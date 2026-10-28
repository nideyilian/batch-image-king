"""
shadcn/ui 规范设计令牌（Design Tokens）

令牌命名与语义严格对齐 https://ui.shadcn.com 的默认（zinc 中性 + 蓝色 primary）规范：
    background / foreground / card / popover / primary / secondary /
    muted / accent / destructive / border / input / ring / radius

暗色主题色值直接复用 app/ui/design_tokens.py（现有画布与控件的运行期真值）。
主题通过可扩展皮肤注册表管理；``Theme.mode`` 作为历史兼容别名保留。

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
# P1 收敛（2026-10-27）：暗色主题真值改指向 tokens_v2
#
# 历史问题：本文件与 design_tokens.py 各维护一份色值，导致同一产品出现三套主色
# （design_tokens 的 #2F9CF4、文字编辑器里的 Ant Design #1677FF/#4096FF、
# 以及本文件的映射值）。现在唯一事实来源是 app/ui/tokens_v2.py。
# `_T` 仅保留给亮色主题与历史调用方兜底。
from app.ui.tokens_v2 import Color as _C
from app.ui.tokens_v2 import Radius as _R

_THEMES = {
    # 暗色：唯一事实来源 = app/ui/tokens_v2（方向 01 墨黑极简）
    "dark": {
        "background":          _C.surface_base,
        "foreground":          _C.text_primary,
        "card":                _C.surface_1,
        "card-foreground":     _C.text_primary,
        "popover":             _C.surface_4,
        "popover-foreground":  _C.text_primary,
        "primary":             _C.accent,
        "primary-foreground":  _C.text_on_accent,
        "secondary":           _C.surface_2,
        "secondary-foreground": _C.text_primary,
        "muted":               _C.surface_2,
        "muted-foreground":    _C.text_muted,
        "accent":              _C.surface_selected,
        "accent-foreground":   _C.text_primary,
        "destructive":         _C.danger,
        "destructive-foreground": _C.text_on_accent,
        # 边框：01 方向是零边框设计，默认取最低一档（近乎不可见），
        # 真正的层次由 surface 亮度差承担。
        "border":              _C.border_subtle,
        "input":               _C.surface_3,
        "ring":                _C.border_focus,
        "primary-hover":       _C.accent_hover,
        "primary-pressed":     _C.accent_active,
        "hover":               _C.surface_hover,
        "success":             _C.success,
        "warning":             _C.warning,
        "info":                _C.info,
        "radius":              f"{_R.md}px",
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

# QML 工作台固定使用的生产控制台配色。保留为独立令牌，供仍需保留的
# QWidget 工具面板接入，避免同一窗口同时出现旧版蓝色与当前生产绿。
_CONSOLE_COLORS = {
    "panel": "#151a1c",
    "raised": "#1a2022",
    "control": "#20272a",
    "hover": "#293235",
    "border": "#2b3437",
    "border_strong": "#3b474a",
    "text_primary": "#f3f6f5",
    "text_secondary": "#aab5b1",
    "text_muted": "#84918c",
    "accent": "#3bd5aa",
    "accent_hover": "#67e6c1",
    "accent_pressed": "#28b88f",
    "accent_foreground": "#06271f",
}

_REQUIRED_SEMANTIC_COLORS = frozenset({
    "background", "foreground", "card", "card-foreground", "popover",
    "popover-foreground", "primary", "primary-foreground", "secondary",
    "secondary-foreground", "muted", "muted-foreground", "accent",
    "accent-foreground", "destructive", "destructive-foreground", "border",
    "input", "ring", "primary-hover", "primary-pressed", "hover", "success",
    "warning", "info",
})

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
    """全局主题访问器和皮肤注册表。"""

    DEFAULT_SKIN = "dark"
    _skin = DEFAULT_SKIN
    _on_change = []

    # ---- 皮肤 / 历史 mode 兼容层 ----
    @classmethod
    def skin(cls) -> str:
        return cls._skin

    @classmethod
    def available_skins(cls):
        return tuple(_THEMES.keys())

    @classmethod
    def register_skin(cls, name: str, colors: dict, overwrite: bool = False) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("skin name cannot be empty")
        if normalized in _THEMES and not overwrite:
            raise ValueError("skin already registered: %s" % normalized)
        missing = sorted(_REQUIRED_SEMANTIC_COLORS.difference(colors))
        if missing:
            raise ValueError("missing semantic colors: %s" % ", ".join(missing))
        _THEMES[normalized] = dict(colors)

    @classmethod
    def unregister_skin(cls, name: str, missing_ok: bool = False) -> None:
        if name == cls.DEFAULT_SKIN:
            raise ValueError("the default skin cannot be unregistered")
        if name not in _THEMES:
            if missing_ok:
                return
            raise KeyError("unknown skin: %s" % name)
        if cls._skin == name:
            cls.set_skin(cls.DEFAULT_SKIN)
        del _THEMES[name]

    @classmethod
    def set_skin(cls, name: str) -> None:
        if name not in _THEMES:
            raise KeyError("unknown skin: %s" % name)
        if name != cls._skin:
            cls._skin = name
            for cb in tuple(cls._on_change):
                try:
                    cb(name)
                except Exception:
                    pass

    @classmethod
    def mode(cls) -> str:
        return cls.skin()

    @classmethod
    def set_mode(cls, mode: str) -> None:
        """历史兼容入口；未知模式维持原有回退到暗色的行为。"""
        if mode not in _THEMES:
            mode = cls.DEFAULT_SKIN
        cls.set_skin(mode)

    @classmethod
    def toggle_mode(cls) -> str:
        cls.set_mode("light" if cls._skin == "dark" and "light" in _THEMES else "dark")
        return cls._skin

    @classmethod
    def on_change(cls, cb):
        if cb not in cls._on_change:
            cls._on_change.append(cb)
        return cb

    @classmethod
    def off_change(cls, cb):
        try:
            cls._on_change.remove(cb)
        except ValueError:
            pass

    # ---- 颜色 ----
    @classmethod
    def colors(cls) -> dict:
        return dict(_THEMES[cls._skin])

    @classmethod
    def color(cls, name: str, default: str = "#000000") -> str:
        return _THEMES[cls._skin].get(name, default)

    @classmethod
    def console_color(cls, name: str, default: str = "#000000") -> str:
        """返回 QML 生产控制台对应的颜色令牌。"""
        return _CONSOLE_COLORS.get(name, default)

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
