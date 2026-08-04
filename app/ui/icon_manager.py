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

# SVG 路径（Lucide 风格，24x24，stroke）
ICON_SVGS = {
    'success': "M20 6 9 17l-5-5",
    'error': "M18 6 6 18M6 6l12 12",
    'info': "M12 22a10 10 0 100-20 10 10 0 000 20zM12 16v-4M12 8h.01",
    'about': "M12 22a10 10 0 100-20 10 10 0 000 20zM12 16v-4M12 8h.01",
    'warning': "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01",
    'visible': "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7zM12 15a3 3 0 100-6 3 3 0 000 6z",
    'hidden': "M9.88 9.88a3 3 0 104.24 4.24M10.73 5.08A10.43 10.43 0 0 1 12 5c6.5 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68M6.61 6.61A13.5 13.5 0 0 0 2 12s3.5 7 10 7a9.74 9.74 0 0 0 5.39-1.61M2 2l20 20",
    'lock': "M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2zM7 11V7a5 5 0 0 1 10 0v4",
    'unlock': "M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2zM7 11V7a5 5 0 0 1 9.9-1",
    'link': "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
    'unlink': "M18.84 12.25l1.72-1.71a5 5 0 0 0-7.07-7.07l-1.72 1.71M5.17 11.75l-1.71 1.71a5 5 0 0 0 7.07 7.07l1.71-1.71",
    'random': "M2 21h2.5c.9 0 1.8-.4 2.4-1.2l5.2-7.2c.6-.8 1.5-1.2 2.4-1.2H22M2 3h2.5c.9 0 1.8.4 2.4 1.2l5.2 7.2c.6.8 1.5 1.2 2.4 1.2H22M17 3l5 5-5 5M17 15l5 5-5 5",
    'add': "M12 5v14M5 12h14",
    'remove': "M5 12h14",
    'edit': "M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z",
    'copy': "M9 9h10a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
    'paste': "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M15 2H9a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1z",
    'undo': "M3 7v6h6M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13",
    'redo': "M21 7v6h-6M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13",
    'up': "M18 15l-6-6-6 6",
    'down': "M6 9l6 6 6-6",
    'left': "M15 18l-6-6 6-6",
    'right': "M9 18l6-6-6-6",
    'expand': "M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7",
    'collapse': "M21 9h-6V3M3 15h6v6M21 9l-6 6M3 15l6-6",
    'zoom_in': "M11 11m-7 0a7 7 0 1 0 14 0 7 7 0 1 0-14 0M21 21l-4.3-4.3M11 8v6M8 11h6",
    'zoom_out': "M11 11m-7 0a7 7 0 1 0 14 0 7 7 0 1 0-14 0M21 21l-4.3-4.3M8 11h6",
    'fit': "M3 8V5a2 2 0 0 1 2-2h3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M21 16v3a2 2 0 0 1-2 2h-3",
    'folder': "M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z",
    'file': "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6",
    'save': "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2zM17 21v-8H7v8M7 3v5h8",
    'open': "M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM14 2v6h6",
    'new': "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M12 12v6M9 15h6",
    'import': "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
    'export': "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
    'settings': "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z",
    'tools': "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
    'filter': "M22 3H2l8 9.46V19l4 2v-8.54L22 3z",
    'sort': "M11 5h10M11 9h7M11 13h4M3 17l3 3 3-3M6 18V4",
    'refresh': "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M3 21v-5h5",
    'help': "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
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

_STROKE_W = 2.0
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
