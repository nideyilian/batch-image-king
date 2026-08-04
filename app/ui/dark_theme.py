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

    @classmethod
    def apply_to_application(cls, app):
        """应用全局 QSS 与调色板到 QApplication。"""
        app.setStyle("Fusion")
        app.setStyleSheet(cls.get_complete_style())
        app.setPalette(cls.create_fixed_palette())

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
            font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
            font-size: 13px;
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
            border-radius: 5px;
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
            border-radius: 5px;
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
            spacing: 5px;
            padding: 5px;
        }}
        QToolBar::separator {{
            background: {cls.BORDER_PRIMARY};
            width: 1px;
            margin: 4px 4px;
        }}
        QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 5px;
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
            font-weight: 600;
        }}
        QTabBar::tab {{
            background-color: {cls.BACKGROUND_SECONDARY};
            color: {cls.TEXT_MUTED};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-bottom: none;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            padding: 7px 14px;
            min-width: 72px;
        }}
        QTabBar::tab:selected {{
            background-color: {cls.BACKGROUND_TERTIARY};
            color: {cls.TEXT_PRIMARY};
            border-color: {cls.BORDER_FOCUS};
        }}
        QTabBar::tab:hover {{
            color: {cls.TEXT_SECONDARY};
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
        QToolTip {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_FOCUS};
            border-radius: 6px;
            padding: 5px 9px;
        }}
        """
