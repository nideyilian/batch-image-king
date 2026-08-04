# -*- coding: utf-8 -*-
"""
图标管理器（阶段 2 升级，2026-08-04）

- 统一用 SVG（Lucide 风格，24x24 视图，1.75px 视觉线宽）替换字体字符 / Emoji，
  避免跨平台字体差异导致的渲染不一致。
- 颜色全部取自 design_tokens（暗色主题），不再使用旧亮色板。
- 图标按 (名称, 尺寸, 颜色, DPR) 缓存为 QPixmap / QIcon。
- 保留原有方法签名；对尚未绘制 SVG 的图标名自动降级为字符渲染，保证调用方零改动。
- 许可证：内置图标参考 Lucide（MIT License），发行包保留该声明（见 README）。
"""

from PySide6.QtWidgets import QPushButton, QLabel
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QGuiApplication

from app.ui.design_tokens import Tokens


# 字符图标表（仅用于未绘制 SVG 的降级兜底，逐步淘汰）
ICONS = {
    'random': '⚀', 'link': '∞', 'unlink': '⧄', 'lock': '🔒', 'unlock': '🔓',
    'visible': '●', 'hidden': '○', 'warning': '⚠', 'info': 'ℹ', 'success': '✓',
    'error': '✗', 'add': '+', 'remove': '−', 'edit': '✎', 'copy': '⧉',
    'paste': '⧈', 'cut': '✂', 'undo': '↶', 'redo': '↷', 'up': '▲', 'down': '▼',
    'left': '◀', 'right': '▶', 'expand': '⊞', 'collapse': '⊟', 'zoom_in': '⊕',
    'zoom_out': '⊖', 'fit': '⊡', 'folder': '📁', 'file': '📄', 'save': '💾',
    'open': '📂', 'new': '📄', 'import': '⬇', 'export': '⬆', 'settings': '⚙',
    'tools': '🔧', 'filter': '⧩', 'sort': '⇅', 'refresh': '↻', 'help': '❓',
    'about': 'ℹ',
}

# SVG 路径（iOS / SF Symbols Outline 风格，24x24，stroke）
# 设计要点：视觉线宽更细、几何对称、圆角端点柔和、留白充足。
ICON_SVGS = {
    'success': "M5 12.5 10 17.5 19 7",
    'error': "M6 6 18 18M18 6 6 18",
    'info': "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5M12 8.2h.02",
    'about': "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5M12 8.2h.02",
    'warning': "M12 4 3 20h18L12 4ZM12 9.5v5M12 17.2h.02",
    'visible': "M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12 19 18.5 12 18.5 1.5 12 1.5 12ZM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
    'hidden': "M9.9 5.1A10 10 0 0 1 12 5c6.5 0 10.5 6.5 10.5 6.5a17 17 0 0 1-2.6 3.4M6.3 6.3A17 17 0 0 0 1.5 12S5 18.5 12 18.5a10 10 0 0 0 5.2-1.4M2 2l20 20",
    'lock': "M7 11V8a5 5 0 0 1 10 0v3M6 11h12a1.5 1.5 0 0 1 1.5 1.5v6A1.5 1.5 0 0 1 18 20H6a1.5 1.5 0 0 1-1.5-1.5v-6A1.5 1.5 0 0 1 6 11ZM12 14.5v3",
    'unlock': "M7 11V8a5 5 0 0 1 9.8-1.5M6 11h12a1.5 1.5 0 0 1 1.5 1.5v6A1.5 1.5 0 0 1 18 20H6a1.5 1.5 0 0 1-1.5-1.5v-6A1.5 1.5 0 0 1 6 11ZM12 14.5v3",
    'link': "M10.5 13.5a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1.5 1.5M13.5 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1.5-1.5",
    'unlink': "M18.5 12.5 20 11a3.5 3.5 0 0 0-5-5l-1.5 1.5M5.5 11.5 4 13a3.5 3.5 0 0 0 5 5l1.5-1.5",
    'random': "M16 4h4v4M20 4 13 11M4 4l7 7M20 20l-7-7M4 20 20 4",
    'add': "M12 5v14M5 12h14",
    'remove': "M5 12h14",
    'edit': "M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z",
    'copy': "M9 9h10a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2ZM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
    'paste': "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M15 2H9a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1Z",
    'undo': "M3 7v6h6M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13",
    'redo': "M21 7v6h-6M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13",
    'up': "M6 15 12 9 18 15",
    'down': "M6 9 12 15 18 9",
    'left': "M15 6 9 12 15 18",
    'right': "M9 6 15 12 9 18",
    'expand': "M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3",
    'collapse': "M21 9h-6V3M3 15h6v6M21 9l-6 6M3 15l6-6",
    'zoom_in': "M10.5 4.5a6 6 0 1 1 0 12 6 6 0 0 1 0-12ZM21 21l-4.8-4.8M10.5 7.5v6M7.5 10.5h6",
    'zoom_out': "M10.5 4.5a6 6 0 1 1 0 12 6 6 0 0 1 0-12ZM21 21l-4.8-4.8M7.5 10.5h6",
    'fit': "M3 8V6a2 2 0 0 1 2-2h2M21 8V6a2 2 0 0 0-2-2h-2M3 16v2a2 2 0 0 0 2 2h2M21 16v2a2 2 0 0 1-2 2h-2",
    'folder': "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z",
    'file': "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5ZM14 3v5h5",
    'save': "M5 3h11l4 4v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM8 3v5h6V3M8 14h8v6H8Z",
    'open': "M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2ZM14 2v6h6",
    'new': "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M12 11v7M8.5 14.5h7",
    'import': "M12 3v12M7 10l5 5 5-5M5 21h14a1 1 0 0 0 1-1V6",
    'export': "M12 15V3M7 8l5-5 5 5M5 21h14a1 1 0 0 0 1-1V6",
    'settings': "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM19.4 13a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z",
    'tools': "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z",
    'filter': "M3.5 5h17a1 1 0 0 1 .8 1.6L14 13.5V19l-4 2v-7.5L2.7 6.6A1 1 0 0 1 3.5 5Z",
    'sort': "M8 4v16M8 4 4 8M8 4l4 4M16 20V4M16 20l-4-4M16 20l4-4",
    'refresh': "M20 11a8 8 0 1 0-1.5 5M20 5v6h-6M4 13a8 8 0 1 0 1.5-5M4 19v-6h6",
    'help': "M9.5 9a2.5 2.5 0 0 1 4.8.9c0 1.7-2.3 2.6-2.3 2.6M12 17h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
}

# 角色 -> 令牌颜色（暗色主题）
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

_STROKE_W = 1.5
_CACHE = {}


def _dpr():
    try:
        screen = QGuiApplication.primaryScreen()
        return screen.devicePixelRatio() if screen else 1.0
    except Exception:
        return 1.0


def _svg_bytes(name, color):
    d = ICON_SVGS[name]
    color = color if color.startswith('#') else '#FFFFFF'
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{_STROKE_W}" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{d}"/></svg>'
    )
    return svg.encode('utf-8')


def _has_qapp():
    try:
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() is not None
    except Exception:
        return False


def _render_pixmap(name, size, color):
    key = (name, size, color, round(_dpr(), 2))
    if key in _CACHE:
        return _CACHE[key]
    # headless（无 QApplication，如单元测试）无法安全创建 QPixmap / QSvgRenderer，
    # 直接返回空 pixmap，避免原生异常；真实界面下 QApplication 存在，正常渲染。
    if not _has_qapp():
        px = QPixmap()
        _CACHE[key] = px
        return px
    dpr = _dpr()
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.transparent)
    # 存在 QApplication 时优先使用 SVG 渲染；未定义 SVG 的图标字符降级。
    if name in ICON_SVGS:
        from PySide6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(_svg_bytes(name, color))
        if renderer.isValid():
            renderer.render(QPainter(px))
        renderer.deleteLater()
    else:
        # 字符降级
        painter = QPainter(px)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        font = QFont(Tokens.FONT_FAMILY, int(size * 0.7))
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(px.rect(), Qt.AlignCenter, ICONS.get(name, '?'))
        painter.end()
    px.setDevicePixelRatio(dpr)
    _CACHE[key] = px
    return px


class IconManager:
    """统一图标管理器（SVG 优先，字符降级）"""

    ICON_FONT_FAMILY = Tokens.FONT_FAMILY
    ICON_FONT_SIZE = 12

    @classmethod
    def get_icon_text(cls, icon_name):
        """获取字符图标文本（兼容旧调用方 / 降级）"""
        return ICONS.get(icon_name, '?')

    @classmethod
    def get_color(cls, color_name):
        return COLORS.get(color_name, COLORS['text'])

    @classmethod
    def get_icon(cls, icon_name, size=18, color=None):
        """返回 QIcon（SVG 渲染；未定义则字符降级）。"""
        if color is None:
            color = COLORS['secondary']
        elif not color.startswith('#'):
            color = cls.get_color(color)
        # headless（无 QApplication）下无法安全构造 QPixmap，直接返回空图标，
        # 真实界面下正常渲染。
        if not _has_qapp():
            return QIcon()
        return QIcon(_render_pixmap(icon_name, size, color))

    @classmethod
    def create_icon_button(cls, icon_name, size=18, color='secondary', tooltip=None):
        button = QPushButton()
        button.setFixedSize(size, size)
        button.setIcon(cls.get_icon(icon_name, size, color))
        button.setIconSize(QSize(size, size))
        button.setText("")
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("variant", "icon")
        button.setStyleSheet(f"""
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
        """)
        if tooltip:
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
        return button

    @classmethod
    def create_checkable_icon_button(cls, icon_name_checked, icon_name_unchecked=None,
                                     size=18, color='secondary', tooltip_checked=None,
                                     tooltip_unchecked=None):
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
        button.setStyleSheet(f"""
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
        """)
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
        label = QLabel()
        icon = cls.get_icon(icon_name, size, color)
        label.setPixmap(icon.pixmap(size, size))
        label.setFixedSize(size, size)
        return label

    @classmethod
    def apply_icon_to_button(cls, button, icon_name, color='secondary'):
        button.setIcon(cls.get_icon(icon_name, button.height() or 18, color))
        button.setText("")
        button.setProperty("variant", "icon")


# 便捷函数（保持旧签名）
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
