#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CursorDarkTheme — 全局暗色主题

阶段 1 重构（2026-08-04）：本类不再维护任何十六进制颜色字面量，
所有取值改为引用 `app.ui.design_tokens.Tokens`（唯一事实来源）。
常量名（如 BACKGROUND_PRIMARY、BORDER_SECONDARY）继续保留，
以保证 canvas 绘制等历史调用方无需修改。

本类只负责：
- 全局默认控件外观；
- 焦点 / hover / pressed / disabled；
- Dock / 菜单 / 标签 / 滚动条等框架控件；
- 动态属性选择器（variant / density / role）。
业务文件不应再写整段 QSS，只设置语义属性。
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt

from app.ui.design_tokens import Tokens
from app.ui.tokens_v2 import Typography
from app.ui.theme.provider import build_global_stylesheet
from app.ui.theme.polisher import install_semantic_polisher


class CursorDarkTheme:
    # ---- 颜色常量：全部为 Tokens 的别名，禁止在此写死十六进制 ----
    BACKGROUND_PRIMARY = Tokens.BG_PRIMARY
    BACKGROUND_SECONDARY = Tokens.BG_SECONDARY
    BACKGROUND_TERTIARY = Tokens.BG_TERTIARY
    BACKGROUND_ELEVATED = Tokens.BG_ELEVATED
    BACKGROUND_CANVAS = Tokens.BG_CANVAS
    BACKGROUND_TITLEBAR = Tokens.BG_TITLEBAR

    TEXT_PRIMARY = Tokens.TEXT_PRIMARY
    TEXT_SECONDARY = Tokens.TEXT_SECONDARY
    TEXT_MUTED = Tokens.TEXT_MUTED
    TEXT_DISABLED = Tokens.TEXT_DISABLED
    TEXT_INVERTED = Tokens.TEXT_INVERTED

    ACCENT_PRIMARY = Tokens.ACCENT
    ACCENT_HOVER = Tokens.ACCENT_HOVER
    ACCENT_PRESSED = Tokens.ACCENT_PRESSED

    SUCCESS = Tokens.SUCCESS
    WARNING = Tokens.WARNING
    ERROR = Tokens.ERROR
    INFO = Tokens.INFO

    BORDER_PRIMARY = Tokens.BORDER_PRIMARY
    BORDER_SECONDARY = Tokens.BORDER_CONTROL
    BORDER_SUBTLE = Tokens.BORDER_SUBTLE
    BORDER_FOCUS = Tokens.BORDER_FOCUS

    HOVER_OVERLAY = Tokens.OVERLAY_HOVER
    PRESSED_OVERLAY = Tokens.OVERLAY_PRESSED
    SELECTED_BG = Tokens.BG_SELECTED

    # ---- 控件尺寸 / 输入文本 / 选择背景（供 SpinBox 等全局控件复用） ----
    CONTROL_HEIGHT = Tokens.CONTROL_HEIGHT
    CONTROL_RADIUS = Tokens.CONTROL_RADIUS
    TEXT_INPUT = Tokens.TEXT_INPUT
    SELECTION_BG = Tokens.SELECTION_BG

    # ---- 字重 / 字号（与属性面板共用同一套令牌，单一真源） ----
    FONT_WEIGHT_BOLD = Tokens.FONT_WEIGHT_BOLD
    FONT_WEIGHT_MEDIUM = Tokens.FONT_WEIGHT_MEDIUM
    FONT_SIZE_BASE = Tokens.FONT_SIZE_BASE
    # QSS 专用字体名：只含一个字体，回退交给 _install_font_fallbacks()
    FONT_FAMILY_QSS = Typography.family

    @classmethod
    def apply_to_application(cls, app):
        """应用全局 QSS 与调色板到 QApplication。"""
        app.setStyle("Fusion")
        cls._install_font_fallbacks()
        app.setStyleSheet(cls.get_complete_style())
        app.setPalette(cls.create_fixed_palette())
        install_semantic_polisher(app)

    @staticmethod
    def _install_font_fallbacks():
        """在程序层注册字体回退，替代 QSS 里的多字体并列。

        ⚠ 这不是风格问题，是启动性能问题（2026-10-27 实测）：
        QSS 的 font-family 一旦并列两个以上字体名（含 sans-serif），
        Qt 就要对**每个新建控件**遍历系统全部 2004 个字体族做匹配，
        单个控件入场 0ms → 420ms，主窗口启动多花 3 秒以上。
        实测：1 个名字 0ms / 2 个名字 2124ms / sans-serif 2157ms。

        改用 QFont.insertSubstitutions 后，回退效果一样，
        但字体解析走缓存表，实测 2ms。
        """
        from PySide6.QtGui import QFont

        from app.ui.tokens_v2 import Typography

        for primary, fallbacks in (
            (Typography.family.strip('"'), Typography.family_fallbacks),
            (Typography.family_mono.strip('"'), Typography.family_mono_fallbacks),
        ):
            QFont.insertSubstitutions(primary, list(fallbacks))

    @classmethod
    def create_fixed_palette(cls):
        """构造 Fusion 调色板，保证下拉 / 菜单 / 提示框基础对比度。"""
        p = QPalette()
        p.setColor(QPalette.Window, QColor(cls.BACKGROUND_PRIMARY))
        p.setColor(QPalette.WindowText, QColor(cls.TEXT_PRIMARY))
        p.setColor(QPalette.Base, QColor(cls.BACKGROUND_ELEVATED))
        p.setColor(QPalette.AlternateBase, QColor(cls.BACKGROUND_SECONDARY))
        p.setColor(QPalette.ToolTipBase, QColor(cls.BACKGROUND_ELEVATED))
        p.setColor(QPalette.ToolTipText, QColor(cls.TEXT_PRIMARY))
        p.setColor(QPalette.Text, QColor(cls.TEXT_PRIMARY))
        p.setColor(QPalette.Button, QColor(cls.BACKGROUND_SECONDARY))
        p.setColor(QPalette.ButtonText, QColor(cls.TEXT_PRIMARY))
        p.setColor(QPalette.BrightText, QColor(cls.TEXT_INVERTED))
        p.setColor(QPalette.Highlight, QColor(cls.ACCENT_PRIMARY))
        p.setColor(QPalette.HighlightedText, QColor(cls.TEXT_INVERTED))
        p.setColor(QPalette.Link, QColor(cls.ACCENT_PRIMARY))
        p.setColor(QPalette.LinkVisited, QColor(cls.ACCENT_PRESSED))
        return p

    @classmethod
    def get_complete_style(cls):
        """全局控件 QSS：仅包含框架级默认样式与动态属性选择器。"""
        return f"""
        QWidget {{
            background-color: {cls.BACKGROUND_PRIMARY};
            color: {cls.TEXT_PRIMARY};
            font-family: {cls.FONT_FAMILY_QSS};
            font-size: {cls.FONT_SIZE_BASE}px;
            outline: none;
        }}
        QMainWindow, QDialog, QDockWidget, QWidget#central {{
            background-color: {cls.BACKGROUND_PRIMARY};
        }}
        QMenuBar {{
            background-color: {cls.BACKGROUND_TITLEBAR};
            color: {cls.TEXT_PRIMARY};
            spacing: 2px;
            padding: 2px;
        }}
        QMenuBar::item:selected {{
            background-color: {cls.SELECTED_BG};
            border-radius: {cls.CONTROL_RADIUS}px;
        }}
        QMenu {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 8px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 22px 6px 12px;
            border-radius: {cls.CONTROL_RADIUS}px;
        }}
        QMenu::item:selected {{
            background-color: {cls.SELECTED_BG};
        }}
        QMenu::separator {{
            height: 1px;
            background: {cls.BORDER_PRIMARY};
            margin: 4px 6px;
        }}
        QToolBar {{
            background-color: {cls.BACKGROUND_TITLEBAR};
            border: none;
            /* 4px 栅格：原来是 spacing/padding 各 5px，都是非栅格值。
               5px padding 会把工具栏撑到 41px（28 按钮 + 5×2 + 3），
               而按钮 max-height 无上限，于是被拉伸成 31px —— 不在
               design_spec 的三档（24/28/36）里。改 4px 后
               28 + 4×2 = 36，按钮回到 28。 */
            spacing: 4px;
            padding: 4px;
        }}
        QToolBar::separator {{
            background: {cls.BORDER_PRIMARY};
            width: 1px;
            margin: 4px 4px;
        }}
        QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: {cls.CONTROL_RADIUS}px;
            color: {cls.TEXT_PRIMARY};
            padding: 4px 8px;
        }}
        QToolButton:hover {{
            background-color: {cls.BACKGROUND_SECONDARY};
            border: 1px solid {cls.BORDER_SECONDARY};
        }}
        QToolButton:pressed {{
            background-color: {cls.SELECTED_BG};
        }}
        QToolButton:checked {{
            background-color: {cls.SELECTED_BG};
            border: 1px solid {cls.ACCENT_PRIMARY};
        }}
        QToolButton[variant="primary"] {{
            background-color: {cls.ACCENT_PRIMARY};
            border: 1px solid {cls.ACCENT_PRIMARY};
            color: {cls.TEXT_INVERTED};
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        QToolButton[variant="primary"]:hover {{
            background-color: {cls.ACCENT_HOVER};
            border-color: {cls.ACCENT_HOVER};
        }}
        QToolButton[variant="primary"]:pressed {{
            background-color: {cls.ACCENT_PRESSED};
            border-color: {cls.ACCENT_PRESSED};
        }}
        QToolButton[variant="secondary"] {{
            background-color: {cls.BACKGROUND_TERTIARY};
            border: 1px solid {cls.BORDER_SECONDARY};
            color: {cls.TEXT_PRIMARY};
        }}
        QToolButton[variant="secondary"]:hover {{
            background-color: {cls.BACKGROUND_SECONDARY};
            border-color: {cls.BORDER_FOCUS};
        }}
        QToolButton[variant="ghost"] {{
            background: transparent;
            border: 1px solid {cls.BORDER_SECONDARY};
            color: {cls.TEXT_SECONDARY};
        }}
        QToolButton[variant="ghost"]:hover {{
            background-color: {cls.BACKGROUND_SECONDARY};
            border-color: {cls.BORDER_FOCUS};
            color: {cls.TEXT_PRIMARY};
        }}
        QStatusBar {{
            background-color: {cls.BACKGROUND_TITLEBAR};
            color: {cls.TEXT_SECONDARY};
            border-top: 1px solid {cls.BORDER_PRIMARY};
        }}
        QStatusBar QLabel {{
            color: {cls.TEXT_SECONDARY};
        }}
        QDockWidget {{
            background-color: {cls.BACKGROUND_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            titlebar-close-icon: none;
        }}
        QDockWidget::title {{
            background-color: {cls.BACKGROUND_SECONDARY};
            padding: 6px 12px;
            border-bottom: 1px solid {cls.BORDER_PRIMARY};
            color: {cls.TEXT_PRIMARY};
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
        }}
        QTabBar::tab {{
            background-color: {cls.BACKGROUND_SECONDARY};
            color: {cls.TEXT_MUTED};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-bottom: 2px solid transparent;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            padding: 7px 14px;
            min-width: 72px;
        }}
        QTabBar::tab:selected {{
            background-color: {cls.BACKGROUND_TERTIARY};
            color: {cls.TEXT_PRIMARY};
            border-color: {cls.BORDER_FOCUS};
            border-bottom-color: {cls.ACCENT_PRIMARY};
        }}
        QTabBar::tab:hover {{
            color: {cls.TEXT_SECONDARY};
            background-color: {cls.BACKGROUND_TERTIARY};
        }}
        QTabBar::close-button {{
            border: none;
            background: transparent;
            border-radius: 4px;
            margin: 2px;
            padding: 2px;
        }}
        QTabBar::close-button:hover {{
            background: {cls.HOVER_OVERLAY};
        }}
        QTabWidget::pane {{
            border: 1px solid {cls.BORDER_PRIMARY};
            border-top: none;
            border-bottom-left-radius: 7px;
            border-bottom-right-radius: 7px;
            background-color: {cls.BACKGROUND_PRIMARY};
        }}
        QScrollBar:vertical {{
            background: {cls.BACKGROUND_PRIMARY};
            width: 12px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {cls.BORDER_SECONDARY};
            border-radius: 6px;
            min-height: 32px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {cls.ACCENT_HOVER};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
            background: none;
        }}
        QScrollBar:horizontal {{
            background: {cls.BACKGROUND_PRIMARY};
            height: 12px;
        }}
        QScrollBar::handle:horizontal {{
            background: {cls.BORDER_SECONDARY};
            border-radius: 6px;
            min-width: 32px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {cls.ACCENT_HOVER};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
            background: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            selection-background-color: {cls.SELECTED_BG};
        }}
        QAbstractSpinBox, QSpinBox, QDoubleSpinBox {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_INPUT};
            border: 1px solid {cls.BORDER_SECONDARY};
            border-radius: {cls.CONTROL_RADIUS}px;
            selection-background-color: {cls.SELECTION_BG};
            padding: 3px 6px;
        }}
        QAbstractSpinBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {cls.ACCENT_PRIMARY};
        }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            subcontrol-origin: border;
            width: 18px;
            background: transparent;
            border: none;
        }}
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
            background: {cls.HOVER_OVERLAY};
        }}
        QToolTip {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_FOCUS};
            border-radius: 6px;
            padding: 5px 9px;
        }}
        """ + "\n" + build_global_stylesheet()
