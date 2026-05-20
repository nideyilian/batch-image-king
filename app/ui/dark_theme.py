#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
现代暗色主题样式系统
基于 Codex 桌面端的低对比暗色设计规范。
"""

from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

class CursorDarkTheme:
    """Codex 风格的暗色主题配色方案"""

    # 基础色彩系统
    BACKGROUND_PRIMARY = "#181818"      # 主内容背景
    BACKGROUND_SECONDARY = "#1F1F1F"    # 侧栏/停靠区背景
    BACKGROUND_TERTIARY = "#2A2A2A"     # 普通控件背景
    BACKGROUND_ELEVATED = "#2F2F2F"     # 输入框/弹层背景
    BACKGROUND_CANVAS = "#151515"       # 画布工作区背景
    BACKGROUND_TITLEBAR = "#202024"     # 菜单栏/工具栏背景

    # 文本颜色系统
    TEXT_PRIMARY = "#F4F4F5"            # 主要文本
    TEXT_SECONDARY = "#C7C7C9"          # 次要文本
    TEXT_MUTED = "#8E8E93"              # 暗淡文本
    TEXT_DISABLED = "#606064"           # 禁用文本
    TEXT_INVERTED = "#FFFFFF"           # 反转文本

    # 强调色系统
    ACCENT_PRIMARY = "#2F9CF4"          # 主强调色
    ACCENT_HOVER = "#55B2FF"            # 悬浮状态
    ACCENT_PRESSED = "#1F7EC8"          # 按下状态

    # 状态色系统
    SUCCESS = "#30D158"                 # 成功色
    WARNING = "#FF8A3D"                 # 警告色
    ERROR = "#FF453A"                   # 错误色
    INFO = "#38A5FF"                    # 信息色

    # 边框色系统
    BORDER_PRIMARY = "#303033"          # 主要边框
    BORDER_SECONDARY = "#3A3A3D"        # 次要边框
    BORDER_SUBTLE = "#252528"           # 弱分割线
    BORDER_FOCUS = "#2F9CF4"            # 焦点边框

    # 交互状态
    HOVER_BG = "#303030"
    SELECTED_BG = "#242B33"
    HOVER_OVERLAY = "rgba(255, 255, 255, 0.07)"
    PRESSED_OVERLAY = "rgba(255, 255, 255, 0.11)"

    # 字体系统
    FONT_FAMILY = "Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif"

    @classmethod
    def create_fixed_palette(cls):
        """创建固定的调色板，完全覆盖系统主题"""
        palette = QPalette()

        # 设置所有可能的颜色角色，确保完全覆盖系统主题

        # 活动状态
        palette.setColor(QPalette.Active, QPalette.Window, QColor(cls.BACKGROUND_PRIMARY))
        palette.setColor(QPalette.Active, QPalette.WindowText, QColor(cls.TEXT_PRIMARY))
        palette.setColor(QPalette.Active, QPalette.Base, QColor(cls.BACKGROUND_ELEVATED))
        palette.setColor(QPalette.Active, QPalette.AlternateBase, QColor(cls.BACKGROUND_SECONDARY))
        palette.setColor(QPalette.Active, QPalette.Text, QColor(cls.TEXT_PRIMARY))
        palette.setColor(QPalette.Active, QPalette.BrightText, QColor(cls.TEXT_INVERTED))
        palette.setColor(QPalette.Active, QPalette.Button, QColor(cls.BACKGROUND_TERTIARY))
        palette.setColor(QPalette.Active, QPalette.ButtonText, QColor(cls.TEXT_PRIMARY))
        palette.setColor(QPalette.Active, QPalette.Highlight, QColor(cls.ACCENT_PRIMARY))
        palette.setColor(QPalette.Active, QPalette.HighlightedText, QColor(cls.TEXT_INVERTED))
        palette.setColor(QPalette.Active, QPalette.Link, QColor(cls.ACCENT_PRIMARY))
        palette.setColor(QPalette.Active, QPalette.LinkVisited, QColor(cls.ACCENT_PRESSED))

        # 非活动状态
        palette.setColor(QPalette.Inactive, QPalette.Window, QColor(cls.BACKGROUND_PRIMARY))
        palette.setColor(QPalette.Inactive, QPalette.WindowText, QColor(cls.TEXT_SECONDARY))
        palette.setColor(QPalette.Inactive, QPalette.Base, QColor(cls.BACKGROUND_ELEVATED))
        palette.setColor(QPalette.Inactive, QPalette.AlternateBase, QColor(cls.BACKGROUND_SECONDARY))
        palette.setColor(QPalette.Inactive, QPalette.Text, QColor(cls.TEXT_SECONDARY))
        palette.setColor(QPalette.Inactive, QPalette.BrightText, QColor(cls.TEXT_INVERTED))
        palette.setColor(QPalette.Inactive, QPalette.Button, QColor(cls.BACKGROUND_TERTIARY))
        palette.setColor(QPalette.Inactive, QPalette.ButtonText, QColor(cls.TEXT_SECONDARY))
        palette.setColor(QPalette.Inactive, QPalette.Highlight, QColor(cls.ACCENT_PRIMARY))
        palette.setColor(QPalette.Inactive, QPalette.HighlightedText, QColor(cls.TEXT_INVERTED))

        # 禁用状态
        palette.setColor(QPalette.Disabled, QPalette.Window, QColor(cls.BACKGROUND_PRIMARY))
        palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(cls.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.Base, QColor(cls.BACKGROUND_SECONDARY))
        palette.setColor(QPalette.Disabled, QPalette.AlternateBase, QColor(cls.BACKGROUND_SECONDARY))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(cls.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.BrightText, QColor(cls.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.Button, QColor(cls.BACKGROUND_SECONDARY))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(cls.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(cls.TEXT_MUTED))
        palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(cls.TEXT_DISABLED))

        return palette

    @classmethod
    def get_complete_style(cls):
        """获取完整的应用程序样式，增强覆盖系统主题"""
        return f"""
        * {{
            color: {cls.TEXT_PRIMARY};
            font-family: {cls.FONT_FAMILY};
        }}

        QMainWindow, QDialog, QWidget {{
            background-color: {cls.BACKGROUND_PRIMARY};
            color: {cls.TEXT_PRIMARY};
            font-family: {cls.FONT_FAMILY};
            font-size: 9pt;
        }}

        QToolTip {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_SECONDARY};
            border-radius: 6px;
            padding: 6px 8px;
        }}

        QFrame[role="section"], QFrame[role="card"], QWidget[role="section"] {{
            background-color: {cls.BACKGROUND_SECONDARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 7px;
        }}

        QLabel[role="sectionTitle"] {{
            color: {cls.TEXT_INVERTED};
            font-size: 13px;
            font-weight: 700;
            background: transparent;
        }}

        QLabel[role="hint"] {{
            color: {cls.TEXT_MUTED};
            font-size: 9pt;
            background: transparent;
        }}

        QPushButton, QToolButton {{
            background-color: {cls.BACKGROUND_TERTIARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 4px;
            padding: 3px 8px;
            min-height: 20px;
            font-size: 9pt;
        }}

        QPushButton:hover, QToolButton:hover {{
            background-color: {cls.HOVER_BG};
            border-color: {cls.ACCENT_HOVER};
        }}

        QPushButton:pressed, QToolButton:pressed {{
            background-color: {cls.ACCENT_PRESSED};
            border-color: {cls.ACCENT_PRIMARY};
            color: {cls.TEXT_INVERTED};
        }}

        QPushButton:disabled, QToolButton:disabled {{
            background-color: {cls.BACKGROUND_SECONDARY};
            color: {cls.TEXT_DISABLED};
            border-color: {cls.BORDER_SUBTLE};
        }}

        QPushButton#primaryButton, QPushButton[variant="primary"], QToolButton[variant="primary"] {{
            background-color: {cls.ACCENT_PRIMARY};
            border-color: {cls.ACCENT_HOVER};
            color: {cls.TEXT_INVERTED};
            font-weight: 700;
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_SECONDARY};
            border-radius: 4px;
            padding: 3px 5px;
            font-size: 9pt;
            selection-background-color: {cls.ACCENT_PRIMARY};
        }}

        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {cls.BORDER_FOCUS};
            outline: none;
        }}

        QSpinBox, QDoubleSpinBox {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_SECONDARY};
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 9pt;
        }}

        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {cls.BORDER_FOCUS};
        }}

        QComboBox {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_SECONDARY};
            border-radius: 4px;
            padding: 3px 6px;
            font-size: 9pt;
        }}

        QComboBox:focus {{
            border-color: {cls.BORDER_FOCUS};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 18px;
        }}

        QComboBox::down-arrow {{
            width: 0;
            height: 0;
        }}

        QComboBox QAbstractItemView {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            selection-background-color: {cls.ACCENT_PRIMARY};
            outline: 0;
        }}

        QListWidget, QTreeWidget, QTableWidget {{
            background-color: {cls.BACKGROUND_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 6px;
            outline: none;
            font-size: 9pt;
        }}

        QListWidget::item, QTreeWidget::item, QTableWidget::item {{
            min-height: 22px;
            padding: 2px 4px;
            border-radius: 4px;
        }}

        QListWidget::item:hover, QTreeWidget::item:hover {{
            background-color: {cls.HOVER_BG};
        }}

        QListWidget::item:selected, QTreeWidget::item:selected {{
            background-color: {cls.SELECTED_BG};
            color: {cls.TEXT_PRIMARY};
            border-left: 2px solid {cls.ACCENT_PRIMARY};
        }}

        QCheckBox, QRadioButton {{
            color: {cls.TEXT_PRIMARY};
            font-size: 9pt;
        }}

        QLabel {{
            color: {cls.TEXT_PRIMARY};
            font-size: 9pt;
            background: transparent;
        }}

        QGroupBox {{
            color: {cls.TEXT_PRIMARY};
            font-size: 9pt;
            font-weight: bold;
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 5px;
            margin-top: 7px;
            padding-top: 7px;
            background-color: {cls.BACKGROUND_SECONDARY};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {cls.TEXT_INVERTED};
        }}

        QTabWidget::pane {{
            background-color: {cls.BACKGROUND_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 4px;
        }}

        QTabBar::tab {{
            color: {cls.TEXT_SECONDARY};
            padding: 5px 10px;
            border: 1px solid transparent;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            background: transparent;
        }}

        QTabBar::tab:selected {{
            color: {cls.TEXT_INVERTED};
            background-color: {cls.BACKGROUND_SECONDARY};
            border-color: {cls.BORDER_PRIMARY};
        }}

        QTabBar::tab:hover {{
            color: {cls.TEXT_INVERTED};
            background-color: {cls.HOVER_BG};
        }}

        QScrollBar:vertical {{
            background-color: {cls.BACKGROUND_PRIMARY};
            width: 9px;
            border-radius: 4px;
        }}

        QScrollBar::handle:vertical {{
            background-color: {cls.BORDER_SECONDARY};
            border-radius: 6px;
            min-height: 20px;
            margin: 2px;
        }}

        QScrollBar::handle:vertical:hover {{
            background-color: {cls.TEXT_MUTED};
        }}

        QScrollBar:horizontal {{
            background-color: {cls.BACKGROUND_PRIMARY};
            height: 9px;
            border-radius: 4px;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {cls.BORDER_SECONDARY};
            border-radius: 6px;
            min-width: 20px;
            margin: 2px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background-color: {cls.TEXT_MUTED};
        }}

        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0;
            height: 0;
            border: none;
            background: transparent;
        }}

        QMenuBar {{
            background-color: {cls.BACKGROUND_TITLEBAR};
            color: {cls.TEXT_PRIMARY};
            border-bottom: 1px solid {cls.BORDER_PRIMARY};
        }}

        QMenuBar::item {{
            background: transparent;
            padding: 4px 8px;
        }}

        QMenuBar::item:selected {{
            background-color: {cls.HOVER_BG};
            border-radius: 4px;
        }}

        QMenu {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 6px;
            padding: 5px;
        }}

        QMenu::item {{
            padding: 6px 26px 6px 12px;
            border-radius: 4px;
        }}

        QMenu::item:selected {{
            background-color: {cls.HOVER_BG};
            color: {cls.TEXT_PRIMARY};
        }}

        QToolBar {{
            background-color: {cls.BACKGROUND_TITLEBAR};
            border: none;
            border-bottom: 1px solid {cls.BORDER_PRIMARY};
            spacing: 3px;
            padding: 3px;
        }}

        QToolBar::separator {{
            background-color: {cls.BORDER_PRIMARY};
            width: 1px;
            margin: 2px 4px;
        }}

        QDockWidget {{
            color: {cls.TEXT_PRIMARY};
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }}

        QDockWidget::title {{
            background-color: {cls.BACKGROUND_SECONDARY};
            color: {cls.TEXT_SECONDARY};
            padding: 4px 7px;
            border: 1px solid {cls.BORDER_PRIMARY};
            border-bottom: none;
            font-weight: 600;
        }}

        QSplitter::handle {{
            background-color: {cls.BORDER_PRIMARY};
        }}

        QProgressBar {{
            background-color: {cls.BACKGROUND_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: 4px;
            text-align: center;
        }}

        QProgressBar::chunk {{
            background-color: {cls.ACCENT_PRIMARY};
            border-radius: 3px;
        }}

        QStatusBar {{
            background-color: {cls.BACKGROUND_TITLEBAR};
            color: {cls.TEXT_SECONDARY};
            border-top: 1px solid {cls.BORDER_PRIMARY};
        }}

        QCheckBox::indicator, QRadioButton::indicator {{
            width: 13px;
            height: 13px;
            border-radius: 3px;
            border: 1px solid {cls.BORDER_SECONDARY};
            background: {cls.BACKGROUND_ELEVATED};
        }}

        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {cls.ACCENT_PRIMARY};
            border-color: {cls.ACCENT_HOVER};
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: {cls.BORDER_SECONDARY};
            border-radius: 2px;
        }}

        QSlider::sub-page:horizontal {{
            background: {cls.ACCENT_PRIMARY};
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            background: {cls.ACCENT_HOVER};
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}

        QHeaderView::section {{
            background-color: {cls.BACKGROUND_SECONDARY};
            color: {cls.TEXT_SECONDARY};
            border: none;
            border-right: 1px solid {cls.BORDER_PRIMARY};
            border-bottom: 1px solid {cls.BORDER_PRIMARY};
            padding: 5px 7px;
        }}
        """

    @classmethod
    def apply_to_application(cls, app):
        """将主题应用到整个应用程序，完全覆盖系统主题"""
        # 先设置固定调色板
        app.setPalette(cls.create_fixed_palette())

        # 再应用样式表
        app.setStyleSheet(cls.get_complete_style())

        # 禁用系统主题检测相关属性
        app.setAttribute(Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)

    @classmethod
    def get_semantic_colors(cls):
        """获取语义化颜色映射"""
        return {
            'primary': cls.ACCENT_PRIMARY,
            'success': cls.SUCCESS,
            'warning': cls.WARNING,
            'error': cls.ERROR,
            'info': cls.INFO,
            'muted': cls.TEXT_MUTED,
            'disabled': cls.TEXT_DISABLED,
        }
