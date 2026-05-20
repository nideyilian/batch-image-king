#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整合的文字图层参数模块 - 专业UI设计
遵循现代设计原则，将所有参数整合到一个紧凑的界面中
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QSlider, QFrame,
                               QToolButton, QButtonGroup, QSizePolicy, QCheckBox,
                               QTextEdit, QLineEdit, QComboBox, QScrollArea, QDialog, QCompleter,
                               QGridLayout)
from PySide6.QtCore import Qt, Signal, QSize, QStringListModel
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QIcon

import sys
import os
import json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.text_layer import TextLayer, TextAlign, FontStyle
from app.ui.enhanced_font_selector import EnhancedFontSelector
from app.ui.collapsible_group import CollapsibleGroupBox


class ToggleButton(QToolButton):
    """切换按钮 - 用于粗体、斜体等样式切换"""
    def __init__(self, text="", checkable=True):
        super().__init__()
        self.setText(text)
        self.setCheckable(checkable)
        self.setAutoRaise(True)
        self.setFixedSize(28, 28)
        self.setStyleSheet("""
            QToolButton {
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                background-color: #2F2F2F;
                color: #F4F4F5;
                font-weight: bold;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #4A4A4A;
                border-color: #606064;
            }
            QToolButton:checked {
                background-color: #2F9CF4;
                border-color: #55B2FF;
                color: #FFFFFF;
            }
            QToolButton:pressed {
                background-color: #0D5A8C;
            }
        """)


class AlignButtonGroup(QWidget):
    """对齐按钮组"""
    alignment_changed = Signal(TextAlign)

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        # 左对齐
        self.left_btn = QToolButton()
        self.left_btn.setText("L")
        self.left_btn.setCheckable(True)
        self.left_btn.setChecked(True)
        self.left_btn.setFixedSize(28, 28)
        self.apply_button_style(self.left_btn)

        # 居中对齐
        self.center_btn = QToolButton()
        self.center_btn.setText("C")
        self.center_btn.setCheckable(True)
        self.apply_button_style(self.center_btn)

        # 右对齐
        self.right_btn = QToolButton()
        self.right_btn.setText("R")
        self.right_btn.setCheckable(True)
        self.apply_button_style(self.right_btn)

        self.button_group.addButton(self.left_btn, 0)
        self.button_group.addButton(self.center_btn, 1)
        self.button_group.addButton(self.right_btn, 2)

        layout.addWidget(self.left_btn)
        layout.addWidget(self.center_btn)
        layout.addWidget(self.right_btn)

        # 连接信号
        self.left_btn.clicked.connect(lambda: self.alignment_changed.emit(TextAlign.LEFT))
        self.center_btn.clicked.connect(lambda: self.alignment_changed.emit(TextAlign.CENTER))
        self.right_btn.clicked.connect(lambda: self.alignment_changed.emit(TextAlign.RIGHT))

    def apply_button_style(self, button):
        button.setStyleSheet("""
            QToolButton {
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                background-color: #2F2F2F;
                color: #F4F4F5;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #4A4A4A;
                border-color: #606064;
            }
            QToolButton:checked {
                background-color: #2F9CF4;
                border-color: #55B2FF;
                color: #FFFFFF;
            }
        """)

    def set_alignment(self, align):
        if align == TextAlign.LEFT:
            self.left_btn.setChecked(True)
        elif align == TextAlign.CENTER:
            self.center_btn.setChecked(True)
        elif align == TextAlign.RIGHT:
            self.right_btn.setChecked(True)


class ColorIndicator(QPushButton):
    """颜色指示器 - 点击选择颜色，带下拉箭头"""
    color_changed = Signal(tuple)  # RGBA元组

    def __init__(self, color=(0, 0, 0, 255), size=24):
        super().__init__()
        self.current_color = color
        self._indicator_size = size
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.update_color_display()
        self.clicked.connect(self.choose_color)

    def update_color_display(self):
        r, g, b, a = self.current_color
        size = self._indicator_size
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba({r}, {g}, {b}, {a});
                border: 1px solid #8E8E93;
                border-radius: 4px;
                min-width: {size}px;
                max-width: {size}px;
                min-height: {size}px;
                max-height: {size}px;
                padding: 0;
            }}
            QPushButton:hover {{
                border-color: #55B2FF;
            }}
        """)
        self.setText("")

    def choose_color(self):
        from PySide6.QtWidgets import QColorDialog
        # 使用当前颜色的RGB值和透明度创建QColor对象
        current_r, current_g, current_b, current_a = self.current_color
        initial_color = QColor(current_r, current_g, current_b, current_a)

        color = QColorDialog.getColor(
            initial_color,
            self,
            "选择颜色"
        )
        if color.isValid():
            # 保存新的颜色（包括透明度）
            self.current_color = (color.red(), color.green(), color.blue(), color.alpha())
            self.update_color_display()
            self.color_changed.emit(self.current_color)


class IntegratedTextPanel(QWidget):
    """整合的文字图层参数面板 - 专业UI设计"""

    # 信号定义
    property_changed = Signal(str, object)  # 属性变更通知
    create_text_requested = Signal(str)     # 创建新文字
    FONT_CN_ALIAS = {
        "Microsoft YaHei": "微软雅黑",
        "Microsoft JhengHei": "微软正黑体",
        "SimSun": "宋体",
        "NSimSun": "新宋体",
        "SimHei": "黑体",
        "KaiTi": "楷体",
        "FangSong": "仿宋",
        "DengXian": "等线",
        "YouYuan": "幼圆",
        "STSong": "华文宋体",
        "STKaiti": "华文楷体",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_layer = None
        self._font_change_guard = False
        self._all_fonts = []
        self._recent_font_limit = 8
        self._recent_font_display_limit = 4
        self._recent_fonts = []
        self._load_recent_fonts()
        self.setup_ui()
        self.connect_signals()
        self.load_fonts()  # 加载字体列表

    def setup_ui(self):
        """设置UI界面"""
        # 保持右侧属性栏宽度稳定，不被内容撑大
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setObjectName("IntegratedTextPanel")
        self.setStyleSheet(self._panel_stylesheet())
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)  # 减少外边距
        main_layout.setSpacing(6)  # 减少卡片间距

        # 1. 快速操作栏
        self.create_action_bar(main_layout)

        # 2. 文字内容区：对齐参考图的“文字内容”主入口
        self.create_text_content_card(main_layout)

        # 3. 核心参数卡片
        self.create_core_params_card(main_layout)

        # 4. 高级设置区域
        self.create_advanced_settings(main_layout)

        # 添加弹性空间
        main_layout.addStretch()

    def _panel_stylesheet(self):
        """Photoshop 风格的深色属性面板统一样式。"""
        return """
            #IntegratedTextPanel {
                background: #181818;
                color: #F4F4F5;
                font-size: 12px;
            }
            QLabel {
                color: #F4F4F5;
                background: transparent;
            }
            QFrame[role="section"] {
                background-color: #1F1F1F;
                border: 1px solid #303033;
                border-radius: 7px;
            }
            QLabel[role="sectionTitle"] {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton, QToolButton {
                min-height: 28px;
                border: 1px solid #3A3A3D;
                border-radius: 4px;
                background-color: #2A2A2A;
                color: #F4F4F5;
                padding: 4px 10px;
            }
            QPushButton:hover, QToolButton:hover {
                background-color: #303030;
                border-color: #55B2FF;
            }
            QPushButton:pressed, QToolButton:pressed {
                background-color: #1F7EC8;
                border-color: #2D95F0;
            }
            QPushButton:disabled, QToolButton:disabled {
                color: #606064;
                background-color: #20252B;
                border-color: #252528;
            }
            QCheckBox {
                color: #F4F4F5;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 1px solid #58636F;
                background: #2F2F2F;
            }
            QCheckBox::indicator:checked {
                background: #2F9CF4;
                border-color: #55B2FF;
            }
            QTextEdit, QLineEdit, QComboBox, QSpinBox {
                background-color: #2F2F2F;
                color: #E9EEF3;
                border: 1px solid #3A3A3D;
                border-radius: 4px;
                selection-background-color: #0E76D8;
                padding: 4px 6px;
            }
            QTextEdit:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border-color: #2F9CF4;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #3A3A3D;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #2F9CF4;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #55B2FF;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            QFrame[role="coreDivider"] {
                background-color: #34383B;
                border: none;
            }
        """

    def _make_section_card(self, title_text, reset_handler=None):
        """创建统一的参数分区卡片。"""
        card = QFrame()
        card.setProperty("role", "section")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)  # 减少内边距
        card_layout.setSpacing(6)  # 减少内部间距

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(title_text)
        title.setProperty("role", "sectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        if reset_handler:
            reset_btn = QToolButton()
            reset_btn.setText("🔄 重置")  # 添加刷新图标
            reset_btn.setToolTip(f"重置{title_text}")
            reset_btn.clicked.connect(reset_handler)
            title_row.addWidget(reset_btn)

        card_layout.addLayout(title_row)
        return card, card_layout

    def _make_core_divider(self, vertical=False):
        line = QFrame()
        line.setProperty("role", "coreDivider")
        if vertical:
            line.setFixedWidth(1)
            line.setMinimumHeight(32)  # 减少高度
        else:
            line.setFixedHeight(1)
        return line

    def _make_core_group(self, label_text, widget, min_width=0):
        group = QWidget()
        group.setMinimumWidth(min_width)
        group.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)  # 减少间距
        label = QLabel(label_text)
        label.setStyleSheet("font-size: 12px; font-weight: 600; color: #F4F4F5;")  # 减少字体
        layout.addWidget(label)
        layout.addWidget(widget)
        return group

    def _style_core_button(self, button, radius=8):
        button.setStyleSheet(f"""
            QToolButton, QPushButton {{
                background-color: #2C2D2E;
                color: #F4F4F5;
                border: 1px solid #55585C;
                border-radius: {radius}px;
                padding: 4px 10px;
                min-height: 34px;
            }}
            QToolButton:hover, QPushButton:hover {{
                background-color: #343638;
                border-color: #6A6D72;
            }}
            QToolButton:checked, QPushButton:checked {{
                background-color: #2F9CF4;
                border-color: #55B2FF;
                color: #FFFFFF;
            }}
        """)

    def _style_core_spinbox(self, spin, width=112):
        spin.setFixedWidth(width)
        spin.setFixedHeight(32)  # 减少高度
        spin.setStyleSheet("""
            QSpinBox {
                background-color: #2C2D2E;
                color: #F4F4F5;
                border: 1px solid #55585C;
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 13px;
            }
            QSpinBox:disabled {
                background-color: #242526;
                color: #8E8E93;
            }
        """)

    def _style_switch_checkbox(self, checkbox):
        """样式化开关复选框为圆形切换样式"""
        checkbox.setText("")
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setFixedSize(52, 30)
        checkbox.setStyleSheet("""
            QCheckBox {
                spacing: 0;
                padding: 0;
            }
            QCheckBox::indicator {
                width: 52px;
                height: 30px;
                border-radius: 15px;
                border: 1px solid #45484C;
                background: #3A3C3F;
                position: relative;
            }
            QCheckBox::indicator:checked {
                background: #2F9CF4;
                border-color: #55B2FF;
            }
            QCheckBox::indicator:after {
                content: '';
                position: absolute;
                width: 24px;
                height: 24px;
                border-radius: 12px;
                background: white;
                left: 3px;
                top: 2px;
            }
            QCheckBox::indicator:checked:after {
                left: 25px;
            }
        """)

    def create_preview_card(self, parent_layout):
        """创建文字预览卡片"""
        card = QFrame()
        card.setFrameStyle(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #303033;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)

        # 预览标题
        title = QLabel("文字预览")
        title.setStyleSheet("font-weight: bold; font-size: 12px; color: #FFFFFF;")
        card_layout.addWidget(title)

        # 预览区域
        self.preview_label = QLabel("示例文字")
        self.preview_label.setMinimumHeight(50)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2F2F2F;
                border: 1px solid #3A3A3D;
                border-radius: 4px;
                padding: 12px;
                font-size: 18px;
                color: #FFFFFF;
            }
        """)
        card_layout.addWidget(self.preview_label)

        parent_layout.addWidget(card)

    def create_action_bar(self, parent_layout):
        """创建快速操作栏"""
        action_card, card_layout = self._make_section_card("文字突出")
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        # 创建文字按钮
        self.create_btn = QPushButton("+ 文字")
        self.create_btn.setFixedHeight(32)
        self.create_btn.setToolTip("创建新的文字图层")

        # 编辑文字按钮
        self.edit_btn = QPushButton("编辑文案")
        self.edit_btn.setFixedHeight(32)
        self.edit_btn.setEnabled(False)
        self.edit_btn.setToolTip("打开完整文案编辑器")

        # 重置按钮
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setFixedHeight(32)
        self.reset_btn.setEnabled(False)
        self.reset_btn.setToolTip("重置文字样式")

        action_bar.addWidget(self.create_btn)
        action_bar.addWidget(self.edit_btn)
        action_bar.addWidget(self.reset_btn)

        # 绑定模式开关：开启时每行是独立文案；关闭时保留真实换行
        self.binding_mode_check = QCheckBox("启用绑定模式(按行文案)")
        self.binding_mode_check.setChecked(True)
        self.binding_mode_check.setToolTip("开启后每行作为独立文案用于绑定匹配；关闭后换行为真实换行")
        action_bar.addStretch()
        action_bar.addWidget(self.binding_mode_check)

        card_layout.addLayout(action_bar)
        parent_layout.addWidget(action_card)

    def create_text_content_card(self, parent_layout):
        """创建可直接编辑的文字内容卡片。"""
        card, card_layout = self._make_section_card("文字内容")
        title_item = card_layout.itemAt(0)
        title_layout = title_item.layout() if title_item else None
        if title_layout:
            self.full_edit_text_btn = QPushButton("编辑文案")
            self.full_edit_text_btn.setFixedHeight(26)
            self.full_edit_text_btn.setMinimumWidth(72)
            self.full_edit_text_btn.setToolTip("打开文字编辑器")
            title_layout.addWidget(self.full_edit_text_btn)

        self.inline_text_edit = QTextEdit()
        self.inline_text_edit.setAcceptRichText(False)
        self.inline_text_edit.setMinimumHeight(82)
        self.inline_text_edit.setMaximumHeight(128)
        self.inline_text_edit.setPlaceholderText("输入当前文案；开启绑定模式时，每行可作为一个候选文案")
        card_layout.addWidget(self.inline_text_edit)

        text_actions = QHBoxLayout()
        text_actions.setSpacing(8)

        self.apply_text_btn = QPushButton("应用")
        self.apply_text_btn.setToolTip("将输入框内容应用到当前文字图层")
        self.prev_text_btn = QToolButton()
        self.prev_text_btn.setText("上一条")
        self.prev_text_btn.setToolTip("切换到上一条候选文案")
        self.next_text_btn = QToolButton()
        self.next_text_btn.setText("下一条")
        self.next_text_btn.setToolTip("切换到下一条候选文案")
        self.random_text_btn = QToolButton()
        self.random_text_btn.setText("随机")
        self.random_text_btn.setToolTip("随机选择一条候选文案")

        self.text_count_label = QLabel("0 条")
        self.text_count_label.setStyleSheet("color: #8E8E93;")

        text_actions.addWidget(self.apply_text_btn)
        text_actions.addWidget(self.prev_text_btn)
        text_actions.addWidget(self.next_text_btn)
        text_actions.addWidget(self.random_text_btn)
        text_actions.addStretch()
        text_actions.addWidget(self.text_count_label)
        card_layout.addLayout(text_actions)

        parent_layout.addWidget(card)

    def create_core_params_card(self, parent_layout):
        """创建核心参数卡片。"""
        card, card_layout = self._make_section_card("核心参数", self.reset_core_params)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(10)

        def label(text):
            widget = QLabel(text)
            widget.setMinimumWidth(58)
            widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            widget.setStyleSheet("font-size: 12px; font-weight: 700; color: #F4F4F5;")
            return widget

        def row(title, *widgets, stretch_last=True):
            line = QHBoxLayout()
            line.setSpacing(8)
            line.addWidget(label(title))
            for widget in widgets:
                if stretch_last and widget is widgets[-1]:
                    line.addWidget(widget, 1)
                else:
                    line.addWidget(widget)
            card_layout.addLayout(line)
            return line

        def make_spin(width=76):
            spin = QSpinBox()
            spin.setFixedWidth(width)
            spin.setFixedHeight(30)
            spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            return spin

        def make_button(text, width=None):
            button = QPushButton(text)
            button.setFixedHeight(30)
            if width is not None:
                button.setFixedWidth(width)
            return button

        def make_tool(text, width=42):
            button = QToolButton()
            button.setText(text)
            button.setFixedSize(width, 30)
            return button

        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.NoInsert)
        self.font_combo.setMaxVisibleItems(18)
        self.font_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.font_combo.setMinimumContentsLength(8)
        self.font_combo.setFixedHeight(30)
        self.font_combo.setMinimumWidth(0)
        self.font_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if self.font_combo.lineEdit():
            self.font_combo.lineEdit().setPlaceholderText("搜索字体（支持模糊匹配）")

        self.font_model = QStringListModel(self)
        self.font_completer = QCompleter(self.font_model, self)
        self.font_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.font_completer.setFilterMode(Qt.MatchContains)
        self.font_completer.setCompletionMode(QCompleter.PopupCompletion)
        if self.font_combo.lineEdit():
            self.font_combo.lineEdit().setCompleter(self.font_completer)

        self.font_settings_btn = make_button("选择", 56)
        self.font_settings_btn.setToolTip("打开高级字体选择器")
        self.font_more_btn = make_button("...", 32)
        self.font_more_btn.setToolTip("更多字体选项")
        self.font_more_btn.hide()
        row("字体", self.font_combo, self.font_settings_btn, stretch_last=False)

        card_layout.addWidget(self._make_core_divider())

        quick_layout = QVBoxLayout()
        quick_layout.setSpacing(6)
        quick_title = QLabel("常用")
        quick_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #F4F4F5;")
        quick_layout.addWidget(quick_title)
        quick_buttons_row = QGridLayout()
        quick_buttons_row.setHorizontalSpacing(8)
        quick_buttons_row.setVerticalSpacing(6)
        self.quick_font_buttons = []
        for index, (font_name, display_name) in enumerate([("SimHei", "黑体"), ("SimSun", "宋体"), ("KaiTi", "楷体"), ("Arial", "Arial")]):
            btn = make_tool(display_name, width=56)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"快速切换到 {display_name}")
            btn.clicked.connect(lambda checked=False, fn=font_name: self._apply_font_selection(fn))
            quick_buttons_row.addWidget(btn, index // 4, index % 4)
            self.quick_font_buttons.append(btn)
        quick_layout.addLayout(quick_buttons_row)
        card_layout.addLayout(quick_layout)

        recent_layout = QVBoxLayout()
        recent_layout.setSpacing(6)
        recent_title = QLabel("最近")
        recent_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #F4F4F5;")
        recent_layout.addWidget(recent_title)
        self.recent_fonts_layout = QHBoxLayout()
        self.recent_fonts_layout.setSpacing(8)
        recent_layout.addLayout(self.recent_fonts_layout)
        card_layout.addLayout(recent_layout)
        self._refresh_recent_font_buttons()

        card_layout.addWidget(self._make_core_divider())

        self.font_size_spin = make_spin(76)
        self.font_size_spin.setRange(6, 200)
        self.font_size_spin.setValue(24)
        self.font_size_spin.setSuffix("px")
        self.bold_btn = ToggleButton("B")
        self.bold_btn.setFixedSize(42, 30)
        self.italic_btn = ToggleButton("I")
        self.italic_btn.setFixedSize(42, 30)
        row("大小", self.font_size_spin, self.bold_btn, self.italic_btn, stretch_last=False)

        self.align_group = AlignButtonGroup()
        for button in (self.align_group.left_btn, self.align_group.center_btn, self.align_group.right_btn):
            button.setFixedSize(42, 30)
        self.vertical_layout_check = QCheckBox("竖排")
        row("对齐", self.align_group, self.vertical_layout_check, stretch_last=False)

        card_layout.addWidget(self._make_core_divider())

        self.text_color = ColorIndicator((0, 0, 0, 255), size=30)
        row("填充色", self.text_color, stretch_last=False)
        self.stroke_enable_check = QCheckBox("描边")
        self.stroke_enable_check.stateChanged.connect(self.on_stroke_enabled_changed)
        self.stroke_color = ColorIndicator((0, 0, 0, 255), size=30)
        self.stroke_color.setEnabled(False)
        row("描边", self.stroke_enable_check, self.stroke_color, stretch_last=False)
        self.stroke_width_spin = make_spin(76)
        self.stroke_width_spin.setRange(1, 20)
        self.stroke_width_spin.setValue(2)
        self.stroke_width_spin.setSuffix("px")
        self.stroke_width_spin.setEnabled(False)
        row("描边宽", self.stroke_width_spin, stretch_last=False)

        card_layout.addWidget(self._make_core_divider())

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setMinimumWidth(90)
        self.opacity_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setFixedWidth(48)
        self.opacity_label.setAlignment(Qt.AlignCenter)
        row("透明度", self.opacity_slider, self.opacity_label, stretch_last=False)

        self.line_spacing_spin = make_spin(76)
        self.line_spacing_spin.setRange(50, 300)  # 50% - 300%
        self.line_spacing_spin.setValue(120)  # 默认120% (1.2倍)
        self.line_spacing_spin.setSuffix("%")
        self.letter_spacing_spin = make_spin(76)
        self.letter_spacing_spin.setRange(-20, 100)  # -20px 到 100px
        self.letter_spacing_spin.setValue(0)  # 默认0px
        self.letter_spacing_spin.setSuffix("px")
        row("间距", self.line_spacing_spin, QLabel("字距"), self.letter_spacing_spin, stretch_last=False)

        card_layout.addWidget(self._make_core_divider())

        self.auto_fit_check = QCheckBox("自动适配边框")
        self.auto_fit_check.setChecked(True)
        self.text_box_padding_spin = make_spin(76)
        self.text_box_padding_spin.setRange(0, 200)
        self.text_box_padding_spin.setValue(5)
        self.text_box_padding_spin.setSuffix("px")
        row("文本框", self.auto_fit_check, QLabel("边距"), self.text_box_padding_spin, stretch_last=False)

        parent_layout.addWidget(card)

    def create_advanced_settings(self, parent_layout):
        """创建高级设置区域 - 补充完整内容"""
        # 位置和变换组
        self.pos_group = CollapsibleGroupBox("位置和变换", collapsed=True)
        pos_layout = QGridLayout()
        pos_layout.setHorizontalSpacing(8)
        pos_layout.setVerticalSpacing(8)

        # X, Y, W, H
        for index, (label, attr) in enumerate([("X:", "x"), ("Y:", "y"), ("W:", "width"), ("H:", "height")]):
            row_index = index // 2
            col_index = (index % 2) * 2
            label_widget = QLabel(label)
            label_widget.setMinimumWidth(22)
            pos_layout.addWidget(label_widget, row_index, col_index)
            spin = QSpinBox()
            if attr in ["width", "height"]:
                spin.setRange(1, 9999)  # 修复：宽度和高度必须为正数
            else:
                spin.setRange(-9999, 9999)  # X和Y可以是负数
            spin.setFixedHeight(30)
            spin.setMinimumWidth(72)
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            spin.setStyleSheet("""
                QSpinBox {
                    background-color: #2F2F2F;
                    color: #F4F4F5;
                    border: 1px solid #5A5A5A;
                    border-radius: 4px;
                    padding: 4px;
                }
            """)
            setattr(self, f"{attr}_spin", spin)
            pos_layout.addWidget(spin, row_index, col_index + 1)

        self.pos_group.add_content_layout(pos_layout)
        parent_layout.addWidget(self.pos_group)

        # 效果和样式组 - 补充完整内容
        self.effects_group = CollapsibleGroupBox("效果和样式", collapsed=True)
        self.create_effects_content(self.effects_group)
        parent_layout.addWidget(self.effects_group)

        # 文字内容管理功能已移除 - 只保留图层属性中的编辑按钮

        # 背景和渐变组 - 补充完整内容
        self.bg_group = CollapsibleGroupBox("背景和渐变", collapsed=True)
        self.create_background_content(self.bg_group)
        parent_layout.addWidget(self.bg_group)

    def create_effects_content(self, parent_group):
        """创建效果和样式内容"""
        effects_layout = QVBoxLayout()
        effects_layout.setSpacing(8)

        # 阴影效果
        shadow_row = QHBoxLayout()
        shadow_row.addWidget(QLabel("阴影:"))
        self.shadow_check = QCheckBox("启用阴影")
        self.shadow_check.setStyleSheet("color: #F4F4F5;")
        self.shadow_check.stateChanged.connect(self.on_shadow_enabled_changed)  # 连接信号
        shadow_row.addWidget(self.shadow_check)
        shadow_row.addStretch()
        effects_layout.addLayout(shadow_row)

        # 阴影参数
        shadow_params_layout = QHBoxLayout()
        shadow_params_layout.addWidget(QLabel("偏移:"))
        self.shadow_x_spin = QSpinBox()
        self.shadow_x_spin.setRange(-50, 50)
        self.shadow_x_spin.setValue(2)
        self.shadow_x_spin.setFixedWidth(60)
        self.shadow_x_spin.valueChanged.connect(self.on_shadow_params_changed)  # 连接信号
        shadow_params_layout.addWidget(self.shadow_x_spin)

        shadow_params_layout.addSpacing(10)
        shadow_params_layout.addWidget(QLabel("Y:"))
        self.shadow_y_spin = QSpinBox()
        self.shadow_y_spin.setRange(-50, 50)
        self.shadow_y_spin.setValue(2)
        self.shadow_y_spin.setFixedWidth(60)
        self.shadow_y_spin.valueChanged.connect(self.on_shadow_params_changed)  # 连接信号
        shadow_params_layout.addWidget(self.shadow_y_spin)

        shadow_params_layout.addSpacing(10)
        shadow_params_layout.addWidget(QLabel("模糊:"))
        self.shadow_blur_spin = QSpinBox()
        self.shadow_blur_spin.setRange(0, 20)
        self.shadow_blur_spin.setValue(3)
        self.shadow_blur_spin.setFixedWidth(60)
        self.shadow_blur_spin.valueChanged.connect(self.on_shadow_params_changed)  # 连接信号
        shadow_params_layout.addWidget(self.shadow_blur_spin)

        shadow_params_layout.addStretch()
        effects_layout.addLayout(shadow_params_layout)

        # 阴影颜色
        shadow_color_layout = QHBoxLayout()
        shadow_color_layout.addWidget(QLabel("颜色:"))
        self.shadow_color = ColorIndicator((0, 0, 0, 128))
        self.shadow_color.color_changed.connect(self.on_shadow_color_changed)  # 连接信号
        shadow_color_layout.addWidget(self.shadow_color)
        shadow_color_layout.addStretch()
        effects_layout.addLayout(shadow_color_layout)

        # 发光效果
        glow_row = QHBoxLayout()
        glow_row.addWidget(QLabel("发光:"))
        self.glow_check = QCheckBox("启用发光")
        self.glow_check.setStyleSheet("color: #F4F4F5;")
        self.glow_check.stateChanged.connect(self.on_glow_enabled_changed)  # 连接信号
        glow_row.addWidget(self.glow_check)
        glow_row.addStretch()
        effects_layout.addLayout(glow_row)

        # 发光参数
        glow_params_layout = QHBoxLayout()
        glow_params_layout.addWidget(QLabel("强度:"))
        self.glow_strength_spin = QSpinBox()
        self.glow_strength_spin.setRange(0, 20)
        self.glow_strength_spin.setValue(5)
        self.glow_strength_spin.setFixedWidth(60)
        self.glow_strength_spin.valueChanged.connect(self.on_glow_params_changed)  # 连接信号
        glow_params_layout.addWidget(self.glow_strength_spin)

        glow_params_layout.addSpacing(10)
        glow_params_layout.addWidget(QLabel("半径:"))
        self.glow_radius_spin = QSpinBox()
        self.glow_radius_spin.setRange(1, 50)
        self.glow_radius_spin.setValue(10)
        self.glow_radius_spin.setFixedWidth(60)
        self.glow_radius_spin.valueChanged.connect(self.on_glow_params_changed)  # 连接信号
        glow_params_layout.addWidget(self.glow_radius_spin)

        glow_params_layout.addStretch()
        effects_layout.addLayout(glow_params_layout)

        parent_group.add_content_layout(effects_layout)
        # 根据模型能力调整可见性
        self._sync_feature_visibility()



    def create_background_content(self, parent_group):
        """创建背景和渐变内容"""
        bg_layout = QVBoxLayout()
        bg_layout.setSpacing(8)

        # 背景启用
        bg_enable_layout = QHBoxLayout()
        self.bg_enable_check = QCheckBox("启用背景")
        self.bg_enable_check.setStyleSheet("color: #F4F4F5;")
        self.bg_enable_check.stateChanged.connect(self.on_background_enabled_changed)  # 连接信号
        bg_enable_layout.addWidget(self.bg_enable_check)
        bg_enable_layout.addStretch()
        bg_layout.addLayout(bg_enable_layout)

        # 背景颜色
        bg_color_layout = QHBoxLayout()
        bg_color_layout.addWidget(QLabel("背景颜色:"))
        self.bg_color = ColorIndicator((255, 255, 255, 255))
        self.bg_color.color_changed.connect(self.on_background_color_changed)  # 连接信号
        bg_color_layout.addWidget(self.bg_color)
        bg_color_layout.addStretch()
        bg_layout.addLayout(bg_color_layout)

        # 背景透明度
        bg_opacity_layout = QHBoxLayout()
        bg_opacity_layout.addWidget(QLabel("背景透明度:"))
        self.bg_opacity_slider = QSlider(Qt.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(100)  # 默认100%透明度
        self.bg_opacity_slider.setFixedHeight(20)
        self.bg_opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #2F2F2F;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #2F9CF4;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
        """)
        self.bg_opacity_slider.valueChanged.connect(self.on_background_opacity_changed)  # 连接信号
        self.bg_opacity_label = QLabel("100%")
        self.bg_opacity_label.setFixedWidth(35)
        self.bg_opacity_label.setAlignment(Qt.AlignCenter)

        bg_opacity_layout.addWidget(self.bg_opacity_slider)
        bg_opacity_layout.addWidget(self.bg_opacity_label)
        bg_opacity_layout.addStretch()
        bg_layout.addLayout(bg_opacity_layout)

        # 背景大小（内边距）- 新增控件
        bg_size_layout = QHBoxLayout()
        bg_size_layout.addWidget(QLabel("背景大小:"))
        self.bg_size_slider = QSlider(Qt.Horizontal)
        self.bg_size_slider.setRange(-50, 50)  # 支持负值（背景小于文字）到正值（背景大于文字）
        self.bg_size_slider.setValue(5)  # 默认5像素内边距
        self.bg_size_slider.setFixedHeight(20)
        self.bg_size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #2F2F2F;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #2F9CF4;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
        """)
        self.bg_size_slider.valueChanged.connect(self.on_background_size_changed)  # 连接信号
        self.bg_size_label = QLabel("+5")
        self.bg_size_label.setFixedWidth(35)
        self.bg_size_label.setAlignment(Qt.AlignCenter)

        bg_size_layout.addWidget(self.bg_size_slider)
        bg_size_layout.addWidget(self.bg_size_label)
        bg_size_layout.addStretch()
        bg_layout.addLayout(bg_size_layout)

        # 渐变设置
        gradient_layout = QVBoxLayout()
        gradient_layout.setSpacing(6)

        # 渐变启用
        gradient_enable_layout = QHBoxLayout()
        self.gradient_enable_check = QCheckBox("启用渐变")
        self.gradient_enable_check.setStyleSheet("color: #F4F4F5;")
        self.gradient_enable_check.stateChanged.connect(self.on_gradient_enabled_changed)  # 连接信号
        gradient_enable_layout.addWidget(self.gradient_enable_check)
        gradient_enable_layout.addStretch()
        gradient_layout.addLayout(gradient_enable_layout)

        # 渐变类型
        gradient_type_layout = QHBoxLayout()
        gradient_type_layout.addWidget(QLabel("渐变类型:"))
        self.gradient_type_combo = QComboBox()
        self.gradient_type_combo.addItems(["线性", "径向", "角度"])
        self.gradient_type_combo.setFixedWidth(80)
        self.gradient_type_combo.setStyleSheet("""
            QComboBox {
                background-color: #2F2F2F;
                color: #F4F4F5;
                border: 1px solid #5A5A5A;
                border-radius: 3px;
                padding: 4px;
            }
        """)
        self.gradient_type_combo.currentTextChanged.connect(self.on_gradient_type_changed)  # 连接信号
        gradient_type_layout.addWidget(self.gradient_type_combo)
        gradient_type_layout.addStretch()
        gradient_layout.addLayout(gradient_type_layout)

        # 渐变颜色
        gradient_color_layout = QHBoxLayout()
        gradient_color_layout.addWidget(QLabel("渐变颜色:"))
        self.gradient_start_color = ColorIndicator((0, 0, 0, 255))
        self.gradient_start_color.color_changed.connect(self.on_gradient_color_changed)  # 连接信号
        gradient_color_layout.addWidget(self.gradient_start_color)
        gradient_color_layout.addWidget(QLabel("→"))
        self.gradient_end_color = ColorIndicator((255, 255, 255, 255))
        self.gradient_end_color.color_changed.connect(self.on_gradient_color_changed)  # 连接信号
        gradient_color_layout.addWidget(self.gradient_end_color)
        gradient_color_layout.addStretch()
        gradient_layout.addLayout(gradient_color_layout)

        bg_layout.addLayout(gradient_layout)

        parent_group.add_content_layout(bg_layout)

    def connect_signals(self):
        """连接信号"""
        # 字体相关
        self.font_combo.textActivated.connect(self.on_font_changed)
        if self.font_combo.lineEdit():
            self.font_combo.lineEdit().editingFinished.connect(self._on_font_edit_finished)
        if hasattr(self, "font_completer"):
            self.font_completer.activated.connect(self.on_font_changed)

        # 位置和尺寸控件信号连接
        if hasattr(self, 'x_spin'):
            self.x_spin.valueChanged.connect(self.on_position_changed)
            self.y_spin.valueChanged.connect(self.on_position_changed)
            self.width_spin.valueChanged.connect(self.on_size_changed)
            self.height_spin.valueChanged.connect(self.on_size_changed)

        # 文案编辑入口不依赖字体扫描结果，避免字体加载异常时按钮失效。
        self.create_btn.clicked.connect(self.on_create_text)
        self.edit_btn.clicked.connect(self.on_edit_text)
        self.reset_btn.clicked.connect(self.on_reset_style)
        self.binding_mode_check.stateChanged.connect(self.on_binding_mode_changed)
        self.apply_text_btn.clicked.connect(self.on_apply_inline_text)
        if hasattr(self, 'full_edit_text_btn'):
            self.full_edit_text_btn.clicked.connect(self.on_edit_text)
        self.prev_text_btn.clicked.connect(lambda: self.on_step_text(-1))
        self.next_text_btn.clicked.connect(lambda: self.on_step_text(1))
        self.random_text_btn.clicked.connect(self.on_random_text)

    def _set_font_combo_text(self, font_name: str):
        """设置字体下拉当前值，并避免递归触发"""
        canonical = self._normalize_font_name(font_name)
        idx = self._find_font_combo_index(canonical)
        self._font_change_guard = True
        try:
            if idx >= 0:
                self.font_combo.setCurrentIndex(idx)
            else:
                self.font_combo.setEditText(self._font_display_name(canonical))
        finally:
            self._font_change_guard = False

    def _font_display_name(self, font_name: str) -> str:
        cn_name = self.FONT_CN_ALIAS.get(font_name)
        if cn_name:
            return cn_name
        return font_name

    def _font_chip_text(self, font_name: str) -> str:
        text = self._font_display_name(font_name)
        if len(text) > 8:
            return f"{text[:8]}..."
        return text

    def _normalize_font_name(self, font_name: str) -> str:
        name = (font_name or "").strip()
        if not name:
            return name
        reverse_map = {v: k for k, v in self.FONT_CN_ALIAS.items()}
        if name in reverse_map:
            return reverse_map[name]
        if name in self.FONT_CN_ALIAS:
            return name
        if name.endswith(")") and " (" in name:
            inside = name.rsplit(" (", 1)[-1].rstrip(")")
            if inside:
                return inside.strip()
        return name

    def _find_font_combo_index(self, font_name: str) -> int:
        for i in range(self.font_combo.count()):
            data = self.font_combo.itemData(i, Qt.UserRole)
            text = self.font_combo.itemText(i)
            if data == font_name or text == font_name:
                return i
        return -1

    def _recent_fonts_file(self) -> Path:
        config_dir = Path.home() / ".config" / "批图王"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "recent_fonts.json"

    def _load_recent_fonts(self):
        try:
            file_path = self._recent_fonts_file()
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fonts = data.get("recent", [])
                self._recent_fonts = [f for f in fonts if isinstance(f, str) and f.strip()]
            else:
                self._recent_fonts = []
        except Exception:
            self._recent_fonts = []

    def _save_recent_fonts(self):
        try:
            file_path = self._recent_fonts_file()
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"recent": self._recent_fonts[:self._recent_font_limit]}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _clear_layout_widgets(self, layout: QHBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_recent_font_buttons(self):
        if not hasattr(self, "recent_fonts_layout"):
            return
        self._clear_layout_widgets(self.recent_fonts_layout)
        for font_name in self._recent_fonts[:self._recent_font_display_limit]:
            # 显示完整字体名称或缩写
            display_name = self._font_display_name(font_name)
            if len(display_name) > 6:
                display_name = f"{display_name[:4]}..."
            btn = QToolButton()
            btn.setText(display_name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"切换到最近字体：{self._font_display_name(font_name)}")
            btn.setFixedSize(56, 30)
            btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #4F4F4F;
                    border-radius: 8px;
                    background-color: #2C2D2E;
                    color: #F4F4F5;
                    padding: 2px 4px;
                    font-size: 11px;
                }
                QToolButton:hover {
                    background-color: #3A3A3A;
                    border-color: #606064;
                }
            """)
            btn.clicked.connect(lambda checked=False, fn=font_name: self._apply_font_selection(fn, add_to_recent=False))
            self.recent_fonts_layout.addWidget(btn)

    def _push_recent_font(self, font_name: str):
        self._recent_fonts = [f for f in self._recent_fonts if f != font_name]
        self._recent_fonts.insert(0, font_name)
        self._recent_fonts = self._recent_fonts[:self._recent_font_limit]
        self._refresh_recent_font_buttons()
        self._save_recent_fonts()

    def _apply_font_selection(self, font_name: str, add_to_recent: bool = True):
        font_name = self._normalize_font_name(font_name)
        if not font_name:
            return

        if self._find_font_combo_index(font_name) == -1:
            self.font_combo.addItem(self._font_display_name(font_name), font_name)
            self._all_fonts.append(font_name)
            display_entries = sorted(set(self._all_fonts + [self._font_display_name(f) for f in self._all_fonts]))
            self.font_model.setStringList(display_entries)

        self._set_font_combo_text(font_name)

        if self.text_layer:
            self.text_layer.font_family = font_name
            self.property_changed.emit("font_family", font_name)

        if add_to_recent:
            self._push_recent_font(font_name)

    def _on_font_edit_finished(self):
        """输入框完成编辑后再提交字体，避免输入过程中频繁切换。"""
        if not self.font_combo.lineEdit():
            return
        font_name = self.font_combo.lineEdit().text().strip()
        if font_name:
            self._apply_font_selection(font_name)

    def load_fonts(self):
        """加载字体列表"""
        try:
            # 创建临时TextLayer实例来获取字体列表
            from app.models.text_layer import TextLayer
            temp_layer = TextLayer()
            fonts = temp_layer.get_system_fonts()
            self.font_combo.clear()
            self._all_fonts = list(fonts)

            # 添加常用中文字体优先
            chinese_fonts = [f for f in fonts if any(kw in f.lower() for kw in ['microsoft', 'sim', 'chinese', 'yahei', 'simsun', 'kaiti', 'fangsong'])]
            other_fonts = [f for f in fonts if f not in chinese_fonts]

            # 先添加中文字体
            for font in sorted(chinese_fonts):
                self.font_combo.addItem(self._font_display_name(font), font)

            # 添加分隔线
            if chinese_fonts and other_fonts:
                self.font_combo.insertSeparator(len(chinese_fonts))

            # 添加其他字体
            for font in sorted(other_fonts):
                self.font_combo.addItem(self._font_display_name(font), font)

            # 设置默认字体
            default_fonts = ["Microsoft YaHei", "SimSun", "SimHei"]
            for font in default_fonts:
                if font in fonts:
                    self._set_font_combo_text(font)
                    break
        except Exception as e:
            print(f"加载字体列表失败: {e}")
            # 加载基本字体作为备选
            basic_fonts = ["Microsoft YaHei", "Arial", "Times New Roman", "SimSun", "SimHei"]
            self._all_fonts = list(basic_fonts)
            for font in basic_fonts:
                self.font_combo.addItem(self._font_display_name(font), font)

        display_entries = sorted(set(self._all_fonts + [self._font_display_name(f) for f in self._all_fonts]))
        self.font_model.setStringList(display_entries)
        self._refresh_recent_font_buttons()

        # 其他信号连接
        self.font_size_spin.valueChanged.connect(self.on_font_size_changed)
        self.bold_btn.clicked.connect(self.on_style_changed)
        self.italic_btn.clicked.connect(self.on_style_changed)
        self.align_group.alignment_changed.connect(self.on_alignment_changed)

        # 颜色和效果
        self.text_color.color_changed.connect(self.on_text_color_changed)
        self.stroke_width_spin.valueChanged.connect(self.on_stroke_changed)
        self.stroke_color.color_changed.connect(self.on_stroke_color_changed)

        # 透明度
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)

        # 行间距和字间距
        self.line_spacing_spin.valueChanged.connect(self.on_line_spacing_changed)
        self.letter_spacing_spin.valueChanged.connect(self.on_letter_spacing_changed)
        self.auto_fit_check.stateChanged.connect(self.on_auto_fit_changed)
        self.text_box_padding_spin.valueChanged.connect(self.on_text_box_padding_changed)
        self.vertical_layout_check.stateChanged.connect(self.on_vertical_layout_changed)

        if hasattr(self, 'x_spin'):
            self.x_spin.valueChanged.connect(self.on_position_changed)
        if hasattr(self, 'y_spin'):
            self.y_spin.valueChanged.connect(self.on_position_changed)
        if hasattr(self, 'width_spin'):
            self.width_spin.valueChanged.connect(self.on_size_changed)
        if hasattr(self, 'height_spin'):
            self.height_spin.valueChanged.connect(self.on_size_changed)
        self.font_settings_btn.clicked.connect(self.on_open_font_selector)

    def set_text_layer(self, text_layer):
        """设置文字图层"""
        self.text_layer = text_layer
        self.update_ui()
        self._sync_feature_visibility()

    def update_preview(self):
        """更新预览 - 由于预览卡片已移除，此方法目前为空实现"""
        # 预览功能已移除，因为预览窗口已经可以查看文字效果
        pass

    def _block_panel_controls(self, blocked):
        """批量阻断子控件信号，避免 UI 刷新时回写模型。"""
        self.blockSignals(blocked)
        for widget in self.findChildren(QWidget):
            if widget is not self:
                widget.blockSignals(blocked)

    def update_ui(self):
        """更新UI显示"""
        if not self.text_layer:
            self.setEnabled(False)
            # 移除预览标签引用，因为预览卡片已移除
            self.create_btn.setEnabled(True)
            self.edit_btn.setEnabled(False)
            self.reset_btn.setEnabled(False)
            self.inline_text_edit.clear()
            self.text_count_label.setText("0 条")
            buttons = [self.apply_text_btn, self.prev_text_btn, self.next_text_btn, self.random_text_btn]
            if hasattr(self, 'full_edit_text_btn'):
                buttons.append(self.full_edit_text_btn)
            for btn in buttons:
                btn.setEnabled(False)
            return

        self.setEnabled(True)
        self.create_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        buttons = [self.apply_text_btn, self.prev_text_btn, self.next_text_btn, self.random_text_btn]
        if hasattr(self, 'full_edit_text_btn'):
            buttons.append(self.full_edit_text_btn)
        for btn in buttons:
            btn.setEnabled(True)

        # 阻断信号，避免循环更新
        self._block_panel_controls(True)

        try:
            # 字体相关
            self._set_font_combo_text(self.text_layer.font_family)
            self.font_size_spin.setValue(self.text_layer.font_size)

            # 样式 - 修复类型映射问题
            font_style = self.text_layer.font_style
            if isinstance(font_style, str):
                font_style = FontStyle[font_style]
            self.bold_btn.setChecked(font_style in [FontStyle.BOLD, FontStyle.BOLD_ITALIC])
            self.italic_btn.setChecked(font_style in [FontStyle.ITALIC, FontStyle.BOLD_ITALIC])

            # 对齐 - 修复类型映射问题
            text_align = self.text_layer.text_align
            if isinstance(text_align, str):
                text_align = TextAlign[text_align]
            self.align_group.set_alignment(text_align)

            # 颜色
            self.text_color.current_color = self.text_layer.text_color
            self.text_color.update_color_display()

            # 描边
            stroke_enabled = getattr(self.text_layer, 'stroke_enabled', False)
            self.stroke_enable_check.setChecked(stroke_enabled)
            self.stroke_width_spin.setEnabled(stroke_enabled)
            self.stroke_color.setEnabled(stroke_enabled)
            self.stroke_width_spin.setValue(self.text_layer.stroke_width)
            self.stroke_color.current_color = self.text_layer.stroke_color
            self.stroke_color.update_color_display()

            # 透明度
            self.opacity_slider.setValue(int(self.text_layer.opacity * 100))
            self.opacity_label.setText(f"{int(self.text_layer.opacity * 100)}%")

            # 行间距和字间距
            if hasattr(self, 'line_spacing_spin'):
                # 将倍数转换为百分比（1.2 -> 120%）
                line_spacing_percent = int(self.text_layer.line_spacing * 100)
                self.line_spacing_spin.setValue(line_spacing_percent)

            if hasattr(self, 'letter_spacing_spin'):
                letter_spacing = getattr(self.text_layer, 'letter_spacing', 0)
                self.letter_spacing_spin.setValue(letter_spacing)

            auto_fit = bool(getattr(self.text_layer, 'auto_fit_text_box', True))
            text_box_padding = int(getattr(self.text_layer, 'text_box_padding', 5))
            vertical_layout = bool(getattr(self.text_layer, 'vertical_layout', False))
            self.auto_fit_check.setChecked(auto_fit)
            self.text_box_padding_spin.setValue(text_box_padding)
            self.vertical_layout_check.setChecked(vertical_layout)

            # 绑定模式
            binding_enabled = bool(getattr(self.text_layer, 'text_binding_enabled', True))
            self.binding_mode_check.setChecked(binding_enabled)
            self._sync_inline_text_editor()

            # 背景透明度 - 从背景颜色的alpha通道获取
            if hasattr(self, 'bg_opacity_slider'):
                bg_alpha = self.text_layer.background_color[3] if len(self.text_layer.background_color) > 3 else 255
                bg_opacity = int(bg_alpha / 255.0 * 100)
                self.bg_opacity_slider.setValue(bg_opacity)
                self.bg_opacity_label.setText(f"{bg_opacity}%")

            # 背景大小（内边距）- 新增
            if hasattr(self, 'bg_size_slider'):
                bg_padding = getattr(self.text_layer, 'background_padding', 5)
                self.bg_size_slider.setValue(bg_padding)
                sign = "+" if bg_padding >= 0 else ""
                self.bg_size_label.setText(f"{sign}{bg_padding}")

            # 背景启用状态
            if hasattr(self, 'bg_enable_check'):
                background_enabled = getattr(self.text_layer, 'background_enabled', False)
                self.bg_enable_check.setChecked(background_enabled)
                if hasattr(self, 'bg_color'):
                    self.bg_color.setEnabled(background_enabled)
                if hasattr(self, 'bg_opacity_slider'):
                    self.bg_opacity_slider.setEnabled(background_enabled)
                if hasattr(self, 'bg_size_slider'):
                    self.bg_size_slider.setEnabled(background_enabled)

            # 背景颜色
            if hasattr(self, 'bg_color'):
                self.bg_color.current_color = self.text_layer.background_color
                self.bg_color.update_color_display()

            # 渐变启用状态
            if hasattr(self, 'gradient_enable_check'):
                gradient_enabled = getattr(self.text_layer, 'gradient_enabled', False)
                self.gradient_enable_check.setChecked(gradient_enabled)
                if hasattr(self, 'gradient_type_combo'):
                    self.gradient_type_combo.setEnabled(gradient_enabled)
                if hasattr(self, 'gradient_start_color'):
                    self.gradient_start_color.setEnabled(gradient_enabled)
                if hasattr(self, 'gradient_end_color'):
                    self.gradient_end_color.setEnabled(gradient_enabled)

            # 渐变类型
            if hasattr(self, 'gradient_type_combo'):
                gradient_type = getattr(self.text_layer, 'gradient_type', 'LINEAR')
                type_mapping = {
                    'LINEAR': '线性',
                    'RADIAL': '径向',
                    'ANGULAR': '角度'
                }
                chinese_type = type_mapping.get(gradient_type, '线性')
                index = self.gradient_type_combo.findText(chinese_type)
                if index >= 0:
                    self.gradient_type_combo.setCurrentIndex(index)

            # 渐变颜色
            if hasattr(self, 'gradient_start_color'):
                self.gradient_start_color.current_color = self.text_layer.gradient_start_color
                self.gradient_start_color.update_color_display()
            if hasattr(self, 'gradient_end_color'):
                self.gradient_end_color.current_color = self.text_layer.gradient_end_color
                self.gradient_end_color.update_color_display()



            # 位置大小 - 修复：确保UI控件初始化正确，避免覆盖图层属性
            if hasattr(self, 'x_spin'):
                # 先设置UI控件的值，避免触发信号导致循环更新
                self.x_spin.blockSignals(True)
                self.y_spin.blockSignals(True)
                self.width_spin.blockSignals(True)
                self.height_spin.blockSignals(True)

                self.x_spin.setValue(self.text_layer.x)
                self.y_spin.setValue(self.text_layer.y)
                self.width_spin.setValue(self.text_layer.width)
                self.height_spin.setValue(self.text_layer.height)
                self.width_spin.setEnabled(not auto_fit)
                self.height_spin.setEnabled(not auto_fit)

                self.x_spin.blockSignals(False)
                self.y_spin.blockSignals(False)
                self.width_spin.blockSignals(False)
                self.height_spin.blockSignals(False)

        finally:
            self._block_panel_controls(False)

    # 事件处理
    def _is_checked(self, state):
        """兼容 PySide6 int 与 Qt.CheckState。"""
        if isinstance(state, bool):
            return state
        value = getattr(state, "value", state)
        return value == 2 or state == Qt.Checked or state == Qt.CheckState.Checked

    def _sync_inline_text_editor(self):
        """从文字图层同步当前文案到内嵌编辑区。"""
        if not self.text_layer or not hasattr(self, "inline_text_edit"):
            return

        binding_enabled = bool(getattr(self.text_layer, 'text_binding_enabled', True))
        lines = self.text_layer.get_text_lines() if hasattr(self.text_layer, 'get_text_lines') else []
        if binding_enabled:
            text = "\n".join(lines) if lines else (getattr(self.text_layer, "current_text", "") or "")
        else:
            text = lines[0] if lines else (getattr(self.text_layer, "current_text", "") or "")

        self.inline_text_edit.blockSignals(True)
        self.inline_text_edit.setPlainText(text)
        self.inline_text_edit.blockSignals(False)

        count = len(lines) if lines else 0
        self.text_count_label.setText(f"{count} 条")
        has_multiple = count > 1
        self.prev_text_btn.setEnabled(has_multiple)
        self.next_text_btn.setEnabled(has_multiple)
        self.random_text_btn.setEnabled(has_multiple)

    def _current_text_index(self):
        if not self.text_layer:
            return 0
        lines = self.text_layer.get_text_lines() if hasattr(self.text_layer, 'get_text_lines') else []
        current = getattr(self.text_layer, "current_text", "")
        try:
            return lines.index(current)
        except ValueError:
            return 0

    def _apply_text_content(self, text):
        """将完整文案写回文字图层，并统一触发刷新/保存信号。"""
        if not self.text_layer:
            return

        final_text = "" if text is None else str(text)
        self.text_layer.text_content = final_text
        new_lines = self.text_layer.get_text_lines() if hasattr(self.text_layer, 'get_text_lines') else []
        next_text = new_lines[0] if new_lines else final_text
        self.text_layer.current_text = next_text
        self.property_changed.emit("text_lines", new_lines)
        self.property_changed.emit("current_text", self.text_layer.current_text)
        self.update_preview()
        self._sync_inline_text_editor()

    def on_apply_inline_text(self):
        """应用内嵌编辑区内容，像 Photoshop 属性栏一样即时更新当前文字。"""
        if not self.text_layer:
            return
        self._apply_text_content(self.inline_text_edit.toPlainText())

    def on_step_text(self, step):
        """按候选文案向前/向后切换。"""
        if not self.text_layer:
            return
        lines = self.text_layer.get_text_lines() if hasattr(self.text_layer, 'get_text_lines') else []
        if len(lines) <= 1:
            return
        next_index = (self._current_text_index() + step) % len(lines)
        self.text_layer.current_text = lines[next_index]
        self.property_changed.emit("current_text", lines[next_index])
        self.update_preview()

    def reset_core_params(self):
        """只重置核心文字参数，保留位置、背景和文案。"""
        if not self.text_layer:
            return
        self.text_layer.font_family = "Microsoft YaHei"
        self.text_layer.font_size = 24
        self.text_layer.font_style = FontStyle.NORMAL
        self.text_layer.text_align = TextAlign.LEFT
        self.text_layer.text_color = (0, 0, 0, 255)
        self.text_layer.stroke_enabled = False
        self.text_layer.stroke_width = 2
        self.text_layer.stroke_color = (255, 255, 255, 255)
        self.text_layer.opacity = 1.0
        self.text_layer.line_spacing = 1.2
        self.text_layer.letter_spacing = 0
        self.text_layer.text_box_padding = 5
        self.text_layer.auto_fit_text_box = True
        self.text_layer.vertical_layout = False
        self.update_ui()
        self.property_changed.emit("core_params_reset", True)

    def on_font_changed(self, font_name):
        if self._font_change_guard:
            return
        self._apply_font_selection(font_name)

    def on_open_font_selector(self):
        """打开增强字体选择器对话框，支持分组/搜索/预览/收藏"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("选择字体")
        layout = QVBoxLayout(dlg)
        selector = EnhancedFontSelector(dlg)
        if self.text_layer:
            selector.set_current_font(self.text_layer.font_family)
            preview_text = (getattr(self.text_layer, 'current_text', '') or '').strip()
            if preview_text and hasattr(selector, 'preview_text_edit'):
                selector.preview_text_edit.setText(preview_text)
        layout.addWidget(selector)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        selected_font = {"name": None}
        def _on_font_change(name: str):
            selected_font["name"] = name
        selector.font_changed.connect(_on_font_change)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec():
            name = selected_font["name"] or selector.current_font or self.font_combo.currentText()
            if name:
                self._apply_font_selection(name)

    def on_font_size_changed(self, size):
        if self.text_layer:
            self.text_layer.font_size = size
            self.property_changed.emit("font_size", size)

    def on_style_changed(self):
        if self.text_layer:
            bold = self.bold_btn.isChecked()
            italic = self.italic_btn.isChecked()

            if bold and italic:
                self.text_layer.font_style = FontStyle.BOLD_ITALIC
            elif bold:
                self.text_layer.font_style = FontStyle.BOLD
            elif italic:
                self.text_layer.font_style = FontStyle.ITALIC
            else:
                self.text_layer.font_style = FontStyle.NORMAL

            self.property_changed.emit("font_style", self.text_layer.font_style)

    def on_alignment_changed(self, align):
        if self.text_layer:
            self.text_layer.text_align = align
            self.property_changed.emit("text_align", align)

    def on_position_changed(self, *args):
        if self.text_layer and hasattr(self, 'x_spin') and hasattr(self, 'y_spin'):
            self.text_layer.x = int(self.x_spin.value())
            self.text_layer.y = int(self.y_spin.value())
            self.property_changed.emit("position", (self.text_layer.x, self.text_layer.y))

    def on_size_changed(self, *args):
        if self.text_layer and hasattr(self, 'width_spin') and hasattr(self, 'height_spin'):
            if bool(getattr(self.text_layer, 'auto_fit_text_box', False)):
                self.text_layer.auto_fit_text_box = False
                if hasattr(self, 'auto_fit_check'):
                    self.auto_fit_check.blockSignals(True)
                    self.auto_fit_check.setChecked(False)
                    self.auto_fit_check.blockSignals(False)
            w = max(1, int(self.width_spin.value()))
            h = max(1, int(self.height_spin.value()))
            self.text_layer.width = w
            self.text_layer.height = h
            self.property_changed.emit("size", (w, h))

    def on_text_color_changed(self, color):
        if self.text_layer:
            self.text_layer.text_color = color
            self.property_changed.emit("text_color", color)

    def on_stroke_changed(self, width):
        if self.text_layer:
            self.text_layer.stroke_width = width
            self.property_changed.emit("stroke_width", width)

    def on_stroke_enabled_changed(self, state):
        """描边启用状态改变"""
        if self.text_layer:
            enabled = self._is_checked(state)
            self.text_layer.stroke_enabled = enabled

            # 启用/禁用描边控件
            self.stroke_width_spin.setEnabled(enabled)
            self.stroke_color.setEnabled(enabled)

            # 如果启用但描边宽度为0（不应该发生，因为范围从1开始），设置默认值
            if enabled and self.text_layer.stroke_width == 0:
                self.text_layer.stroke_width = 2
                self.stroke_width_spin.setValue(2)

            self.property_changed.emit("stroke_enabled", enabled)

    def on_stroke_color_changed(self, color):
        if self.text_layer:
            self.text_layer.stroke_color = color
            self.property_changed.emit("stroke_color", color)

    def on_opacity_changed(self, value):
        if self.text_layer:
            self.text_layer.opacity = value / 100.0
            self.opacity_label.setText(f"{value}%")
            self.property_changed.emit("opacity", self.text_layer.opacity)

    def on_line_spacing_changed(self, value):
        """行间距改变"""
        if self.text_layer:
            # 将百分比转换为倍数（120% -> 1.2）
            spacing = value / 100.0
            self.text_layer.line_spacing = spacing
            self.property_changed.emit("line_spacing", spacing)

    def on_letter_spacing_changed(self, value):
        """字间距改变"""
        if self.text_layer:
            self.text_layer.letter_spacing = value
            self.property_changed.emit("letter_spacing", value)

    def on_auto_fit_changed(self, state):
        """自动适配边框开关"""
        if self.text_layer:
            enabled = self._is_checked(state)
            self.text_layer.auto_fit_text_box = enabled
            if hasattr(self, 'width_spin'):
                self.width_spin.setEnabled(not enabled)
            if hasattr(self, 'height_spin'):
                self.height_spin.setEnabled(not enabled)
            self.property_changed.emit("auto_fit_text_box", enabled)

    def on_text_box_padding_changed(self, value):
        """文字边距改变"""
        if self.text_layer:
            self.text_layer.text_box_padding = int(value)
            self.property_changed.emit("text_box_padding", int(value))

    def on_vertical_layout_changed(self, state):
        """竖排开关"""
        if self.text_layer:
            enabled = self._is_checked(state)
            self.text_layer.vertical_layout = bool(enabled)
            # 显式发出属性变化，确保画布/属性面板链路同步刷新
            self.property_changed.emit("vertical_layout", bool(enabled))

    def on_create_text(self):
        """创建新文字 - 使用极简编辑器"""
        # 创建极简编辑器用于输入新文字
        from app.ui.minimal_text_editor_dialog import MinimalTextEditorDialog
        dialog = MinimalTextEditorDialog(self)
        dialog.setWindowTitle("创建文字")
        dialog.set_text_content("")  # 空文本用于创建新文字

        # 显示对话框
        if dialog.exec() == QDialog.Accepted:
            new_text = dialog.get_current_text().strip()
            if new_text:
                if self.text_layer:
                    # 添加到现有图层：按绑定模式解析输入
                    self._apply_text_content(new_text)
                else:
                    # 创建新图层时保留完整文本，由创建逻辑按绑定模式解析
                    self.create_text_requested.emit(new_text)

    def _sync_feature_visibility(self):
        """根据TextLayer是否具备相关属性，显示/隐藏对应UI，避免UI-功能脱节"""
        layer = getattr(self, 'text_layer', None)
        if not layer:
            # 默认隐藏效果组，避免误导
            self.effects_group.setVisible(False)
            return
        # 只有当模型具备阴影或发光相关属性时才显示效果组
        has_shadow = all(hasattr(layer, attr) for attr in [
            'shadow_enabled', 'shadow_offset_x', 'shadow_offset_y', 'shadow_blur', 'shadow_color'
        ])
        has_glow = all(hasattr(layer, attr) for attr in [
            'glow_enabled', 'glow_strength', 'glow_radius'
        ])
        self.effects_group.setVisible(has_shadow or has_glow)

    def on_edit_text(self):
        """编辑当前文字 - 统一入口"""
        self.open_text_editor()

    def open_text_editor(self):
        """极简文字编辑器 - 显示所有文案内容"""
        if not self.text_layer:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "请先选中文本图层")
            return

        # 根据绑定模式准备编辑文本
        binding_enabled = bool(getattr(self.text_layer, 'text_binding_enabled', True))
        all_text_lines = self.text_layer.get_text_lines() if hasattr(self.text_layer, 'get_text_lines') else []
        if binding_enabled:
            if not all_text_lines:
                all_text_lines = [self.get_current_text_content()]
            all_text_content = '\n'.join(all_text_lines)
        else:
            if all_text_lines:
                all_text_content = str(all_text_lines[0])
            else:
                all_text_content = self.get_current_text_content()

        # 创建极简编辑器
        from app.ui.minimal_text_editor_dialog import MinimalTextEditorDialog
        dialog = MinimalTextEditorDialog(self)
        dialog.setWindowTitle("编辑所有文案")

        # 设置所有文案内容
        dialog.set_text_content(all_text_content)

        # 显示对话框 - 使用QDialog的标准返回值
        if dialog.exec() == QDialog.Accepted:
            # 应用编辑后的所有文案
            final_text = dialog.get_current_text()
            if self.text_layer:
                # 按绑定模式解析输入
                self._apply_text_content(final_text)

    def on_binding_mode_changed(self, state):
        """切换文字绑定模式"""
        if not self.text_layer:
            return
        enabled = self._is_checked(state)
        self.text_layer.text_binding_enabled = enabled
        self.property_changed.emit("text_binding_enabled", enabled)
        self._sync_inline_text_editor()

    def get_current_text_content(self):
        """获取当前文案内容，支持多种回退策略"""
        if not self.text_layer:
            return ""

        # 优先级1：直接获取图层当前文本（包括空字符串）
        if self.text_layer.current_text is not None:
            return self.text_layer.current_text

        # 优先级2：从文字列表中获取第一个
        text_lines = self.text_layer.get_text_lines()
        if text_lines:
            return text_lines[0]

        # 优先级3：从显示控件获取（去除占位符）
        if hasattr(self, 'current_text_display'):
            display_text = self.current_text_display.text()
            if display_text and display_text != "示例文字":
                return display_text

        # 默认返回空字符串
        return ""

    def sync_text_to_list(self, text):
        """同步文本到文字列表"""
        if not text or not hasattr(self, 'text_list_widget'):
            return

        # 如果列表为空，添加当前文本
        if self.text_list_widget.count() == 0:
            self.text_list_widget.addItem(text)
        else:
            # 更新当前选中的项，或者添加新项
            current_row = self.text_list_widget.currentRow()
            if current_row >= 0:
                self.text_list_widget.item(current_row).setText(text)
            else:
                self.text_list_widget.addItem(text)

    def on_reset_style(self):
        """重置样式"""
        if not self.text_layer:
            return

        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "重置样式",
            "确定要重置所有样式设置吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # 重置为默认值
            self.text_layer.font_family = "Microsoft YaHei"
            self.text_layer.font_size = 24
            self.text_layer.font_style = FontStyle.NORMAL
            self.text_layer.text_align = TextAlign.LEFT
            self.text_layer.text_color = (0, 0, 0, 255)
            self.text_layer.stroke_enabled = False  # 重置描边启用状态
            self.text_layer.stroke_width = 0
            self.text_layer.stroke_color = (0, 0, 0, 255)
            self.text_layer.opacity = 1.0

            self.update_ui()

    # 缺失的事件处理函数 - 添加所有缺失的处理器
    def on_shadow_enabled_changed(self, state):
        """阴影启用状态改变"""
        if self.text_layer:
            enabled = self._is_checked(state)
            self.text_layer.shadow_enabled = enabled
            self.property_changed.emit("shadow_enabled", enabled)
            self.update_preview()

    def on_shadow_params_changed(self):
        """阴影参数改变"""
        if self.text_layer:
            self.text_layer.shadow_offset_x = self.shadow_x_spin.value()
            self.text_layer.shadow_offset_y = self.shadow_y_spin.value()
            self.text_layer.shadow_blur = self.shadow_blur_spin.value()
            self.property_changed.emit("shadow_params", (self.shadow_x_spin.value(), self.shadow_y_spin.value(), self.shadow_blur_spin.value()))
            self.update_preview()

    def on_shadow_color_changed(self, color):
        """阴影颜色改变"""
        if self.text_layer:
            self.text_layer.shadow_color = color
            self.property_changed.emit("shadow_color", color)
            self.update_preview()

    def on_glow_enabled_changed(self, state):
        """发光启用状态改变"""
        if self.text_layer:
            enabled = self._is_checked(state)
            self.text_layer.glow_enabled = enabled
            self.property_changed.emit("glow_enabled", enabled)
            self.update_preview()

    def on_glow_params_changed(self):
        """发光参数改变"""
        if self.text_layer:
            self.text_layer.glow_strength = self.glow_strength_spin.value()
            self.text_layer.glow_radius = self.glow_radius_spin.value()
            self.property_changed.emit("glow_params", (self.glow_strength_spin.value(), self.glow_radius_spin.value()))
            self.update_preview()

    def on_cycle_text(self):
        """循环切换文字"""
        if self.text_layer:
            lines = self.text_layer.get_text_lines()
            if len(lines) > 1:
                current_index = 0
                for i, line in enumerate(lines):
                    if line == self.text_layer.current_text:
                        current_index = i
                        break

                next_index = (current_index + 1) % len(lines)
                self.text_layer.current_text = lines[next_index]
                self.property_changed.emit("current_text", lines[next_index])
                self.update_preview()

    def on_random_text(self):
        """随机选择文字"""
        if self.text_layer:
            lines = self.text_layer.get_text_lines()
            if len(lines) > 1:
                import random
                random_text = random.choice(lines)
                self.text_layer.current_text = random_text
                self.property_changed.emit("current_text", random_text)
                self.update_preview()

    def on_background_enabled_changed(self, state):
        """背景启用状态改变"""
        if self.text_layer:
            enabled = self._is_checked(state)
            self.text_layer.background_enabled = enabled
            self.property_changed.emit("background_enabled", enabled)
            self.update_preview()

    def on_background_color_changed(self, color):
        """背景颜色改变"""
        if self.text_layer:
            self.text_layer.background_color = color
            self.property_changed.emit("background_color", color)
            self.update_preview()

    def on_background_opacity_changed(self, value):
        """背景透明度改变 - 通过修改背景颜色的alpha通道实现"""
        if self.text_layer:
            # 获取当前背景颜色并修改alpha值
            current_color = self.text_layer.background_color
            # 修复：确保100%透明度对应255，0%对应0
            alpha_value = int(value * 255 / 100)  # 更精确的计算
            new_color = (current_color[0], current_color[1], current_color[2], alpha_value)
            self.text_layer.background_color = new_color
            self.bg_opacity_label.setText(f"{value}%")
            self.property_changed.emit("background_color", new_color)

    def on_background_size_changed(self, value):
        """背景大小改变 - 通过修改background_padding实现"""
        if self.text_layer:
            self.text_layer.background_padding = value
            # 更新标签显示，正值显示+号，负值显示-号
            sign = "+" if value >= 0 else ""
            self.bg_size_label.setText(f"{sign}{value}")
            self.property_changed.emit("background_padding", value)
            self.update_preview()

    def on_gradient_enabled_changed(self, state):
        """渐变启用状态改变"""
        if self.text_layer:
            enabled = self._is_checked(state)
            self.text_layer.gradient_enabled = enabled
            self.property_changed.emit("gradient_enabled", enabled)
            self.update_preview()

    def on_gradient_type_changed(self, gradient_type):
        """渐变类型改变"""
        if self.text_layer:
            # 将中文映射到英文枚举值
            type_mapping = {
                "线性": "LINEAR",
                "径向": "RADIAL",
                "角度": "ANGULAR"
            }
            english_type = type_mapping.get(gradient_type, "LINEAR")
            self.text_layer.gradient_type = english_type
            self.property_changed.emit("gradient_type", english_type)
            self.update_preview()

    def on_gradient_color_changed(self, color):
        """渐变颜色改变"""
        if self.text_layer:
            # 根据发送者判断是起始颜色还是结束颜色
            sender = self.sender()
            if sender == self.gradient_start_color:
                self.text_layer.gradient_start_color = color
                self.property_changed.emit("gradient_start_color", color)
            elif sender == self.gradient_end_color:
                self.text_layer.gradient_end_color = color
                self.property_changed.emit("gradient_end_color", color)
            self.update_preview()




# 测试代码
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建测试窗口
    window = QMainWindow()
    window.setWindowTitle("整合文字图层参数面板 - 专业UI设计")
    window.resize(400, 700)

    # 创建面板
    panel = IntegratedTextPanel()

    # 创建测试文字图层
    text_layer = TextLayer()
    text_layer.name = "测试文字"
    text_layer.current_text = "专业UI设计测试"
    text_layer.font_family = "Microsoft YaHei"
    text_layer.font_size = 28
    text_layer.text_color = (255, 255, 255, 255)
    text_layer.opacity = 0.9

    panel.set_text_layer(text_layer)

    window.setCentralWidget(panel)
    window.show()

    print("✅ 整合文字图层参数面板创建成功")
    print("🎯 设计特点:")
    print("   • 卡片式布局，视觉层次清晰")
    print("   • 核心参数优先展示")
    print("   • 专业切换按钮和对齐控件")
    print("   • 紧凑布局，空间利用率高")
    print("   • 现代扁平化设计风格")

    sys.exit(app.exec())
