# -*- coding: utf-8 -*-
"""图标管理器 —— **兼容层**（2026-10-28 起）。

═══════════════════════════════════════════════════════════════════════════
这个文件现在的职责
═══════════════════════════════════════════════════════════════════════════

保留旧 API 签名（`get_icon` / `create_icon_button` / `create_icon_label` /
`apply_icon_to_button` / `create_*_button` 等），内部**全部转调
`app.ui.icon_library`** —— 也就是 Lucide SVG 单一真源。

目的：让 64 个既有调用点零改动就能拿到统一的 Lucide 图标。

    旧：  IconManager.get_icon('delete')
    实际：icon_library.icon('trash-2')   ← 走别名表

═══════════════════════════════════════════════════════════════════════════
已经删除的东西（不要加回来）
═══════════════════════════════════════════════════════════════════════════

- `ICON_SVGS`：51 个手写 path。与 Lucide 同名不同形（save / eye 的弧度都不一致），
  是「两套图标混用」的直接来源。现在统一用 `app/qml/icons/*.svg`。
- `ICONS`：42 个字符图标（⚀ ∞ ⧄ ✎ 💾 📁）。依赖系统字体，换机器可能变豆腐块，
  且与 SVG 笔画重量完全不同。**字符图标不再参与任何渲染。**
- `_render_pixmap` 的字符降级分支：图标缺失时不再画字符，改为
  `icon_library` 的问号兜底图标。

`get_icon_text()` 保留但**已废弃**：它历史上返回字符图标，现在返回空串，
仅供尚未改造的字符串拼接调用方不崩。新代码请用 `IconLabel` / `icon_pixmap()`。

═══════════════════════════════════════════════════════════════════════════
许可证
═══════════════════════════════════════════════════════════════════════════

图标来源 `lucide-static v1.28.0`，ISC License。发行包保留该声明。
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QPushButton

from app.ui.design_tokens import Tokens
from app.ui.icon_library import IconName
from app.ui.icon_library import icon as _icon
from app.ui.icon_library import icon_pixmap as _icon_pixmap

# ── 角色名 → 令牌色值（保留旧调用方的 'secondary' / 'danger' 等写法）────
COLORS = {
    'primary': Tokens.ACCENT,
    'secondary': Tokens.TEXT_SECONDARY,
    'muted': Tokens.TEXT_MUTED,
    'success': Tokens.SUCCESS,
    'warning': Tokens.WARNING,
    'danger': Tokens.ERROR,
    'error': Tokens.ERROR,
    'disabled': Tokens.TEXT_DISABLED,
    'text': Tokens.TEXT_PRIMARY,
    'info': Tokens.INFO,
}


def _color(role):
    """把角色名或十六进制值统一成色值字符串。"""
    if not role:
        return COLORS['secondary']
    if role.startswith('#'):
        return role
    return COLORS.get(role, COLORS['secondary'])


def _button_qss(size):
    """图标按钮的通用 QSS（原来在两个方法里各写一遍，抽出来避免漂移）。"""
    return f"""
            QPushButton[variant="icon"] {{
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton[variant="icon"]:hover {{
                background: {Tokens.OVERLAY_HOVER};
                border-radius: {size // 4}px;
            }}
            QPushButton[variant="icon"]:pressed {{
                background: {Tokens.OVERLAY_PRESSED};
            }}
            QPushButton[variant="icon"]:disabled {{
                opacity: 0.4;
            }}
        """


class IconManager:
    """统一图标管理器（Lucide SVG 真源）。

    所有方法都是 `icon_library` 的薄封装，保留旧签名。
    """

    ICON_FONT_FAMILY = Tokens.FONT_FAMILY
    ICON_FONT_SIZE = 12

    # ── 已废弃 ──────────────────────────────────────────────────
    @classmethod
    def get_icon_text(cls, icon_name):
        """**已废弃**：历史上返回字符图标（⚀ ∞ ⧄ ✎ 💾）。

        字符图标已全部移除，这里返回空串，仅为让旧的字符串拼接调用方不崩。
        需要图标请用 `IconLabel` 或 `icon_library.icon_pixmap()`。
        """
        import warnings

        warnings.warn(
            "IconManager.get_icon_text() 已废弃：字符图标已移除，请改用 "
            "app.ui.icon_library.icon_pixmap() 或 IconLabel",
            DeprecationWarning,
            stacklevel=2,
        )
        return ""

    # ── 颜色 ────────────────────────────────────────────────────
    @classmethod
    def get_color(cls, color_name):
        return _color(color_name)

    # ── 图标 ────────────────────────────────────────────────────
    @classmethod
    def get_icon(cls, icon_name, size=18, color=None):
        """返回 QIcon（Lucide SVG 渲染）。"""
        return _icon(icon_name, color=_color(color), size=size)

    @classmethod
    def get_pixmap(cls, icon_name, size=18, color=None):
        """返回 QPixmap（供 QLabel.setPixmap 这类自绘场景）。"""
        return _icon_pixmap(icon_name, size=size, color=_color(color))

    # ── 按钮工厂 ────────────────────────────────────────────────
    @classmethod
    def create_icon_button(cls, icon_name, size=18, color='secondary', tooltip=None):
        """创建纯图标按钮。"""
        button = QPushButton()
        button.setFixedSize(size, size)
        button.setIcon(cls.get_icon(icon_name, size, color))
        button.setIconSize(QSize(size, size))
        button.setText("")
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("variant", "icon")
        button.setStyleSheet(_button_qss(size))
        if tooltip:
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
        return button

    @classmethod
    def create_checkable_icon_button(cls, icon_name_checked, icon_name_unchecked=None,
                                     size=18, color='secondary', tooltip_checked=None,
                                     tooltip_unchecked=None):
        """创建可切换图标按钮（如 显示/隐藏、锁定/解锁）。"""
        if icon_name_unchecked is None:
            icon_name_unchecked = icon_name_checked
        button = QPushButton()
        button.setFixedSize(size, size)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("variant", "icon")
        icon_checked = cls.get_icon(icon_name_checked, size, color)
        icon_unchecked = cls.get_icon(icon_name_unchecked, size, color)
        button.setIcon(icon_unchecked)
        button.setIconSize(QSize(size, size))
        button.setText("")
        button.setStyleSheet(_button_qss(size))
        button.icon_checked = icon_checked
        button.icon_unchecked = icon_unchecked
        button.tooltip_checked = tooltip_checked
        button.tooltip_unchecked = tooltip_unchecked
        button.toggled.connect(lambda checked: cls._update_checkable_button(button, checked))
        cls._update_checkable_button(button, button.isChecked())
        return button

    @classmethod
    def _update_checkable_button(cls, button, checked):
        button.setIcon(button.icon_checked if checked else button.icon_unchecked)
        tip = button.tooltip_checked if checked else button.tooltip_unchecked
        if tip:
            button.setToolTip(tip)
            button.setAccessibleName(tip)

    @classmethod
    def create_icon_label(cls, icon_name, size=16, color='text'):
        """创建图标 QLabel（真实 SVG 位图，不是字符）。"""
        label = QLabel()
        label.setPixmap(cls.get_pixmap(icon_name, size, color))
        label.setFixedSize(size, size)
        return label

    @classmethod
    def apply_icon_to_button(cls, button, icon_name, color='secondary'):
        """把图标贴到已有按钮上。

        ⚠ 尺寸不要用 `button.height()`：`update_aspect_lock_icon()` 这类方法在
        `show()` 之前就会被调用，那时 height 是默认的 480 或 0，导致同一排按钮里
        出现一个明显偏粗的图标（2026-10-28 实测：比例锁定按钮图标比邻居大一圈）。
        改为固定用 design_spec 的 SM 档（16px），与其它图标按钮一致。
        """
        from app.ui.design_spec import IconSize

        size = IconSize.SM
        existing = button.iconSize()
        if existing.width() > 0:
            # 已经显式设过尺寸的（如图层面板的 16/18），尊重原设置
            size = existing.width()
        button.setIcon(cls.get_icon(icon_name, size, color))
        button.setText("")
        button.setProperty("variant", "icon")


# ── 便捷函数（保持旧签名）─────────────────────────────────────────────

def create_random_button(size=18):
    return IconManager.create_icon_button('random', size, 'secondary', '随机化')


def create_link_button(size=18):
    return IconManager.create_checkable_icon_button('link', 'unlink', size, 'secondary',
                                                    '已链接 - 点击解除', '未链接 - 点击链接')


def create_lock_button(size=18):
    return IconManager.create_checkable_icon_button('lock', 'unlock', size, 'warning',
                                                    '已锁定 - 点击解锁', '未锁定 - 点击锁定')


def create_visibility_button(size=18):
    return IconManager.create_checkable_icon_button('visible', 'hidden', size, 'secondary',
                                                    '可见 - 点击隐藏', '隐藏 - 点击显示')


__all__ = [
    "IconManager",
    "COLORS",
    "IconName",
    "create_random_button",
    "create_link_button",
    "create_lock_button",
    "create_visibility_button",
]
