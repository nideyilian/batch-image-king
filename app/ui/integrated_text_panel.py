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
                               QGridLayout, QTabWidget)
from PySide6.QtCore import Qt, Signal, QSize, QStringListModel, QRectF
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QIcon

import sys
import os
import json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.text_layer import TextLayer, TextAlign, FontStyle
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.design_tokens import Tokens
from app.ui.property_panel_a2 import PropertyPanelA2



from app.ui.text_panel_widgets import (
    A2Switch, ToggleButton, AlignButtonGroup, ColorIndicator
)
from app.ui.integrated_text_panel_base import IntegratedTextPanelBase
from app.ui.integrated_text_panel_content import IntegratedTextPanelContent
from app.ui.integrated_text_panel_handlers import IntegratedTextPanelHandlers

class IntegratedTextPanel(QWidget, IntegratedTextPanelBase, IntegratedTextPanelContent, IntegratedTextPanelHandlers):
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
        self._font_cn_names = {}
        self._recent_font_limit = 8
        self._recent_font_display_limit = 4
        self._recent_fonts = []
        self._load_recent_fonts()
        self.setup_ui()
        self.connect_signals()
        self.load_fonts()  # 加载字体列表

    def setup_ui(self):
        """设置UI界面 - 紧凑型布局，减少启用组件，一屏尽可能多展示"""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setObjectName("IntegratedTextPanel")
        self.setStyleSheet(self._panel_stylesheet() + self._tab_stylesheet())
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.parameter_tabs = QTabWidget()
        self.parameter_tabs.setObjectName("textLayerPropertyTabs")
        self.parameter_tabs.setDocumentMode(True)
        self.parameter_tabs.tabBar().setExpanding(True)
        self.parameter_tabs.tabBar().setUsesScrollButtons(False)
        # Tab栏高度略紧凑
        self.parameter_tabs.tabBar().setFixedHeight(34)
        self.basic_scroll_area, self.basic_tab_content, self.basic_layout = self._create_parameter_tab("基本参数")
        self.more_scroll_area, self.more_tab_content, self.more_layout = self._create_parameter_tab("更多参数")
        main_layout.addWidget(self.parameter_tabs)

        # 基本参数：文字内容、字体、排版、外观、位置尺寸（常用，折叠默认展开）
        self.create_text_content_card(self.basic_layout)
        self.create_font_card(self.basic_layout)
        self.create_typography_card(self.basic_layout)
        self.create_appearance_card(self.basic_layout)
        self.create_position_dimension_card(self.basic_layout)

        # 更多参数：背景（低频）、阴影与发光（低频）
        self.create_background_card(self.more_layout)
        self.create_effects_only_settings(self.more_layout)
        self._sync_panel_summaries()

        self.basic_layout.addStretch()
        self.more_layout.addStretch()

    def _panel_stylesheet(self):
        """Photoshop 风格的深色属性面板统一样式。"""
        return PropertyPanelA2.stylesheet("#IntegratedTextPanel")

    def _tab_stylesheet(self):
        return f"""
            #IntegratedTextPanel QTabWidget#textLayerPropertyTabs {{
                background-color: {PropertyPanelA2.PANEL_BG};
                border: none;
            }}
            #IntegratedTextPanel QTabWidget#textLayerPropertyTabs::pane {{
                background-color: {PropertyPanelA2.PANEL_BG};
                border: none;
                border-top: 1px solid {Tokens.BORDER_SUBTLE};
            }}
            #IntegratedTextPanel QTabWidget#textLayerPropertyTabs QTabBar::tab {{
                min-height: 34px;
                max-height: 34px;
                margin: 0;
                padding: 0 14px;
                background-color: {PropertyPanelA2.CARD_BG};
                color: {PropertyPanelA2.TEXT_MUTED};
                border: none;
                border-bottom: 2px solid transparent;
                font-size: {Tokens.FONT_SIZE_BASE}px;
                font-weight: {Tokens.FONT_WEIGHT_MEDIUM};
            }}
            #IntegratedTextPanel QTabWidget#textLayerPropertyTabs QTabBar::tab:hover {{
                color: {PropertyPanelA2.TEXT_PRIMARY};
                background-color: {PropertyPanelA2.CONTROL_BG_HOVER};
            }}
            #IntegratedTextPanel QTabWidget#textLayerPropertyTabs QTabBar::tab:selected {{
                color: {PropertyPanelA2.TEXT_PRIMARY};
                background-color: {PropertyPanelA2.PANEL_BG};
                border-bottom-color: {PropertyPanelA2.ACCENT};
                font-weight: {Tokens.FONT_WEIGHT_BOLD};
            }}
            #IntegratedTextPanel QScrollArea {{
                background: {PropertyPanelA2.PANEL_BG};
                border: none;
            }}
            #IntegratedTextPanel QLabel[role="mutedLabel"] {{
                min-height: 0px;
                padding-top: 2px;
                padding-bottom: 1px;
            }}
        """

    def _create_parameter_tab(self, label):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        content = QWidget()
        content.setObjectName("textParameterTabContent")
        content.setAttribute(Qt.WA_StyledBackground, True)
        content.setStyleSheet(f"QWidget#textParameterTabContent {{ background-color: {PropertyPanelA2.PANEL_BG}; }}")
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(*(PropertyPanelA2.PANEL_MARGIN,) * 4)
        layout.setSpacing(PropertyPanelA2.CARD_GAP)
        scroll_area.setWidget(content)
        self.parameter_tabs.addTab(scroll_area, label)
        return scroll_area, content, layout

    def _make_section_card(self, title_text, reset_handler=None):
        """创建 A v2 风格的模块卡片：标题栏带右侧摘要，正文保持紧凑。"""
        card = QFrame()
        card.setProperty("role", "section")
        outer_layout = QVBoxLayout(card)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header = QFrame()
        header.setProperty("role", "sectionHeader")
        header.setFixedHeight(PropertyPanelA2.HEADER_HEIGHT)
        title_row = QHBoxLayout(header)
        title_row.setContentsMargins(PropertyPanelA2.BODY_MARGINS[0], 0, PropertyPanelA2.BODY_MARGINS[2], 0)
        title_row.setSpacing(PropertyPanelA2.ROW_GAP)

        title = QLabel(title_text)
        title.setProperty("role", "sectionTitle")
        summary = QLabel("")
        summary.setProperty("role", "summaryLabel")
        summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        card.title_label = title
        card.summary_label = summary
        card.title_layout = title_row
        card.header_frame = header
        title_row.addWidget(title)
        title_row.addWidget(summary, 1)

        if reset_handler:
            reset_btn = QToolButton()
            reset_btn.setText("重置")
            reset_btn.setToolTip(f"重置{title_text}")
            reset_btn.setProperty("actionButton", True)
            reset_btn.setFixedSize(PropertyPanelA2.ACTION_BUTTON_WIDTH, PropertyPanelA2.CONTROL_HEIGHT)
            reset_btn.clicked.connect(reset_handler)
            card.reset_button = reset_btn
            title_row.addWidget(reset_btn)

        body = QFrame()
        body.setProperty("role", "sectionBody")
        card_layout = QVBoxLayout(body)
        card_layout.setContentsMargins(*PropertyPanelA2.BODY_MARGINS)
        card_layout.setSpacing(PropertyPanelA2.SECTION_GAP)
        card.body_frame = body
        card.body_layout = card_layout
        outer_layout.addWidget(header)
        outer_layout.addWidget(body)
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
        label.setProperty("role", "fieldLabel")  # 字号/字重/颜色统一由 panel_qss 提供
        layout.addWidget(label)
        layout.addWidget(widget)
        return group

    def _style_core_button(self, button, radius=8):
        button.setStyleSheet(f"""
            QToolButton, QPushButton {{
                background-color: {PropertyPanelA2.CONTROL_BG_ALT};
                color: {PropertyPanelA2.TEXT_PRIMARY};
                border: 1px solid {PropertyPanelA2.BORDER_CONTROL};
                border-radius: {radius}px;
                padding: 4px 10px;
                min-height: {PropertyPanelA2.CONTROL_HEIGHT}px;
            }}
            QToolButton:hover, QPushButton:hover {{
                background-color: {PropertyPanelA2.CONTROL_BG_HOVER};
                border-color: {PropertyPanelA2.BORDER_CONTROL};
            }}
            QToolButton:checked, QPushButton:checked {{
                background-color: {PropertyPanelA2.ACCENT};
                border-color: {PropertyPanelA2.ACCENT_HOVER};
                color: {PropertyPanelA2.TEXT_INVERTED};
            }}
        """)

    def _label(self, text, width=PropertyPanelA2.LABEL_WIDTH):
        label = QLabel(text)
        label.setFixedWidth(width)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setProperty("role", "fieldLabel")
        return label

    def _muted_label(self, text):
        label = QLabel(text)
        label.setProperty("role", "mutedLabel")
        return label

    def _make_param_row(self, title, *widgets, stretch_last=True):
        row = QHBoxLayout()
        row.setSpacing(PropertyPanelA2.ROW_GAP)
        row.addWidget(self._label(title))
        for widget in widgets:
            if stretch_last and widget is widgets[-1]:
                row.addWidget(widget, 1)
            else:
                row.addWidget(widget)
        return row

    def _make_spin(self, width=PropertyPanelA2.SPIN_WIDTH):
        spin = QSpinBox()
        spin.setFixedWidth(width)
        spin.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return spin

    def _make_button(self, text, width=None):
        button = QPushButton(text)
        button.setProperty("actionButton", True)
        button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        button.setMaximumHeight(PropertyPanelA2.CONTROL_HEIGHT)
        if width is not None:
            button.setFixedWidth(width)
        return button

    def _make_tool(self, text, width=PropertyPanelA2.ACTION_BUTTON_WIDTH):
        button = QToolButton()
        button.setText(text)
        button.setProperty("actionButton", True)
        button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        button.setMaximumHeight(PropertyPanelA2.CONTROL_HEIGHT)
        if width:
            button.setMinimumWidth(width)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def _make_segment_button(self, text, checked=False):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setProperty("segmentButton", True)
        button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        button.setMaximumHeight(PropertyPanelA2.CONTROL_HEIGHT)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def _make_segment_row(self, specs, active_value, handler=None, property_name="mode"):
        layout = QHBoxLayout()
        layout.setSpacing(PropertyPanelA2.SEGMENT_GAP)
        group = QButtonGroup(self)
        group.setExclusive(True)
        buttons = []
        for text, value in specs:
            button = self._make_segment_button(text, checked=(value == active_value))
            button.setProperty(property_name, value)
            if handler:
                button.clicked.connect(lambda checked=False, item_value=value: handler(item_value))
            group.addButton(button)
            buttons.append(button)
            layout.addWidget(button)
        return layout, group, buttons

    def _make_subpanel(self):
        panel = QFrame()
        panel.setProperty("role", "subPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*PropertyPanelA2.SUBPANEL_MARGINS)
        layout.setSpacing(PropertyPanelA2.ROW_GAP)
        return panel, layout

    def _make_compact_value_button(self, text):
        button = QPushButton(text)
        button.setProperty("compactValue", True)
        button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def _make_parameter_grid(self, *pairs, single_row=False):
        container = QFrame()
        container.setProperty("role", "parameterGrid")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(PropertyPanelA2.ROW_GAP)
        grid.setVerticalSpacing(PropertyPanelA2.ROW_GAP)

        if single_row:
            # 多组参数排在同一行：间距 | 字距 | 边距
            count = len(pairs)
            for index, (title, control) in enumerate(pairs):
                col = index * 3
                title_label = self._label(title, width=PropertyPanelA2.SECONDARY_LABEL_WIDTH)
                grid.addWidget(title_label, 0, col)
                grid.addWidget(control, 0, col + 1)
                grid.setColumnMinimumWidth(col + 2, PropertyPanelA2.ROW_GAP)
            # 各组之间的弹性间隔，保证横向均匀分布
            for c in range(2, count * 3, 3):
                grid.setColumnStretch(c, 1)
            container._responsive_single = True
            container._responsive_count = count
            container._responsive_labels = [grid.itemAtPosition(0, i * 3).widget() for i in range(count)]
            container._responsive_controls = [grid.itemAtPosition(0, i * 3 + 1).widget() for i in range(count)]
            return container

        for index, (title, control) in enumerate(pairs):
            row_index = index // 2
            base_col = (index % 2) * 3
            title_label = self._label(title) if index % 2 == 0 else self._label(title, width=PropertyPanelA2.SECONDARY_LABEL_WIDTH)
            grid.addWidget(title_label, row_index, base_col)
            grid.addWidget(control, row_index, base_col + 1)
            if index % 2 == 0:
                grid.setColumnMinimumWidth(base_col + 2, PropertyPanelA2.ROW_GAP)
            if index == 1:
                container._responsive_second_label = title_label
                container._responsive_second_control = control

        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(5, 1)
        return container

    def _style_core_spinbox(self, spin, width=112):
        spin.setFixedWidth(width)
        spin.setFixedHeight(32)  # 减少高度
        spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {PropertyPanelA2.CONTROL_BG_ALT};
                color: {PropertyPanelA2.TEXT_PRIMARY};
                border: 1px solid {PropertyPanelA2.BORDER_CONTROL};
                border-radius: {PropertyPanelA2.CONTROL_RADIUS}px;
                padding: 4px 8px;
                font-size: {PropertyPanelA2.FONT_SIZE_BASE}px;
            }}
            QSpinBox:disabled {{
                background-color: {PropertyPanelA2.CARD_BG};
                color: {PropertyPanelA2.TEXT_MUTED};
            }}
        """)

    def _style_switch_checkbox(self, checkbox):
        """样式化开关复选框为圆形切换样式"""
        checkbox.setText("")
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setProperty("role", "switch")
        checkbox.setFixedSize(*PropertyPanelA2.SWITCH_SIZE)

    def create_preview_card(self, parent_layout):
        """创建文字预览卡片（样式由 panel_qss 的 previewCard / previewTitle / previewArea 角色统一提供）"""
        card = QFrame()
        card.setFrameStyle(QFrame.StyledPanel)
        card.setProperty("role", "previewCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)

        # 预览标题
        title = QLabel("文字预览")
        title.setProperty("role", "previewTitle")
        card_layout.addWidget(title)

        # 预览区域
        self.preview_label = QLabel("示例文字")
        self.preview_label.setMinimumHeight(50)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setProperty("role", "previewArea")
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
        """创建可直接编辑的文字内容卡片（紧凑型）。"""
        card, card_layout = self._make_section_card("文字内容")
        self.content_card = card
        self.content_card_title = card.title_label
        self.content_summary_label = card.summary_label
        # 紧凑内部边距和间距
        card_layout.setContentsMargins(8, 5, 8, 6)
        card_layout.setSpacing(5)

        self.create_btn = QPushButton("+ 文字", self)
        self.create_btn.setToolTip("创建新的文字图层")
        self.create_btn.hide()

        self.reset_btn = QPushButton("重置", self)
        self.reset_btn.setEnabled(False)
        self.reset_btn.setToolTip("重置文字样式")
        self.reset_btn.hide()

        self.full_edit_text_btn = QPushButton("编辑文案", self)
        self.full_edit_text_btn.setToolTip("打开文字编辑器")
        self.full_edit_text_btn.hide()
        self.edit_btn = self.full_edit_text_btn

        self.binding_mode_check = QCheckBox("绑定")
        self.binding_mode_check.setProperty("role", "inlineCheck")
        self.binding_mode_check.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        self.binding_mode_check.setChecked(True)
        self.binding_mode_check.setToolTip("开启后每行作为独立文案用于绑定匹配；关闭后换行为真实换行")

        self.inline_text_edit = QTextEdit()
        self.inline_text_edit.setAcceptRichText(False)
        # 紧凑文字输入框：默认2-3行可见，避免首屏过高
        self.inline_text_edit.setFixedHeight(72)
        self.inline_text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.inline_text_edit.setPlaceholderText("输入当前文案；开启绑定模式时，每行可作为一个候选文案")
        card_layout.addWidget(self.inline_text_edit)

        text_actions = QHBoxLayout()
        text_actions.setSpacing(4)

        self.apply_text_btn = QPushButton("应用", self)
        self.apply_text_btn.setProperty("actionButton", True)
        self.apply_text_btn.setToolTip("将输入框内容应用到当前文字图层")
        self.apply_text_btn.hide()
        self.prev_text_btn = self._make_tool("上一条")
        self.prev_text_btn.setToolTip("切换到上一条候选文案")
        self.next_text_btn = self._make_tool("下一条")
        self.next_text_btn.setToolTip("切换到下一条候选文案")
        self.random_text_btn = self._make_tool("随机")
        self.random_text_btn.setToolTip("随机选择一条候选文案")
        self.range_color_btn = self._make_tool("颜色")
        self.range_color_btn.setToolTip("为当前文案中的选中文字设置颜色")
        self.range_color_btn.setEnabled(False)
        self.clear_range_color_btn = self._make_tool("清色")
        self.clear_range_color_btn.setToolTip("清除当前文案中选中文字的局部颜色")
        self.clear_range_color_btn.setEnabled(False)
        self.range_size_btn = self._make_tool("字号")
        self.range_size_btn.setToolTip("为选中文字设置独立字号（同一图层内混合字号）")
        self.range_size_btn.setEnabled(False)
        self.clear_range_size_btn = self._make_tool("清字号")
        self.clear_range_size_btn.setToolTip("清除选中文字的独立字号，恢复为图层字号")
        self.clear_range_size_btn.setEnabled(False)

        self.text_count_label = QLabel("0 条")
        self.text_count_label.setProperty("role", "summaryLabel")

        for button in (self.prev_text_btn, self.next_text_btn, self.random_text_btn):
            button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            text_actions.addWidget(button)
        for button in (self.range_color_btn, self.clear_range_color_btn, self.range_size_btn, self.clear_range_size_btn):
            button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            text_actions.addWidget(button)
        text_actions.addWidget(self.binding_mode_check)
        text_actions.addStretch()
        text_actions.addWidget(self.text_count_label)
        card_layout.addLayout(text_actions)

        parent_layout.addWidget(card)

    def create_font_card(self, parent_layout):
        """创建字体卡片（紧凑型）。"""
        card, card_layout = self._make_section_card("字体", self.reset_core_params)
        self.font_card = card
        self.font_card_title = card.title_label
        self.font_summary_label = card.summary_label
        self.font_reset_btn = getattr(card, "reset_button", None)
        # 紧凑内部边距
        card_layout.setContentsMargins(8, 5, 8, 6)
        card_layout.setSpacing(5)

        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.NoInsert)
        self.font_combo.setMaxVisibleItems(18)
        self.font_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.font_combo.setMinimumContentsLength(8)
        self.font_combo.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
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

        self.font_settings_btn = self._make_button("选择", PropertyPanelA2.ACTION_BUTTON_WIDTH)
        self.font_settings_btn.setToolTip("打开高级字体选择器")
        self.font_more_btn = self._make_button("...", 32)
        self.font_more_btn.setToolTip("更多字体选项")
        self.font_more_btn.hide()
        card_layout.addLayout(self._make_param_row("字体", self.font_combo, self.font_settings_btn, stretch_last=False))

        # 常用字体按钮：直接展示，去掉"常用"小标题（节省约24px+间距）
        quick_buttons_row = QHBoxLayout()
        quick_buttons_row.setSpacing(PropertyPanelA2.ROW_GAP)
        self.quick_font_button_group = QButtonGroup(self)
        self.quick_font_button_group.setExclusive(True)
        self.quick_font_buttons = []
        for font_name, display_name in [("Microsoft YaHei", "雅黑"), ("SimSun", "宋体"), ("KaiTi", "楷体"), ("Arial", "Arial")]:
            btn = self._make_segment_button(display_name, checked=(font_name == "Microsoft YaHei"))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"快速切换到 {display_name}")
            btn.clicked.connect(lambda checked=False, fn=font_name: self._apply_font_selection(fn))
            self.quick_font_button_group.addButton(btn)
            quick_buttons_row.addWidget(btn)
            self.quick_font_buttons.append(btn)
        card_layout.addLayout(quick_buttons_row)

        # 最近字体：初始不显示（默认setVisible(False)，无内容时不占垂直空间）；有记录时_refresh会自动显示
        self.recent_fonts_layout = QHBoxLayout()
        self.recent_fonts_layout.setSpacing(PropertyPanelA2.ROW_GAP)
        self.recent_fonts_container = QWidget()
        self.recent_fonts_container.setLayout(self.recent_fonts_layout)
        self.recent_fonts_container.setVisible(False)
        card_layout.addWidget(self.recent_fonts_container)
        self._refresh_recent_font_buttons()

        parent_layout.addWidget(card)

    def create_typography_card(self, parent_layout):
        """创建排版卡片（紧凑型）。"""
        card, card_layout = self._make_section_card("排版")
        self.typography_card = card
        self.typography_card_title = card.title_label
        self.typography_summary_label = card.summary_label
        # 紧凑布局：减小边距和内部间距
        card_layout.setContentsMargins(8, 5, 8, 6)
        card_layout.setSpacing(5)

        self.font_size_spin = self._make_spin(76)
        self.font_size_spin.setRange(6, 200)
        self.font_size_spin.setValue(24)
        self.font_size_spin.setSuffix("px")
        self.font_size_spin.setMinimumWidth(PropertyPanelA2.SPIN_WIDTH)
        self.font_size_spin.setMaximumWidth(16777215)
        self.font_size_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.bold_btn = ToggleButton("B")
        self.bold_btn.setFixedSize(PropertyPanelA2.ICON_BUTTON_WIDTH, PropertyPanelA2.CONTROL_HEIGHT)
        self.italic_btn = ToggleButton("I")
        self.italic_btn.setFixedSize(PropertyPanelA2.ICON_BUTTON_WIDTH, PropertyPanelA2.CONTROL_HEIGHT)
        self.typography_size_row = self._make_param_row(
            "大小",
            self.font_size_spin,
            self.bold_btn,
            self.italic_btn,
            stretch_last=False,
        )
        card_layout.addLayout(self.typography_size_row)

        self.align_group = AlignButtonGroup()
        for text, button in (("左", self.align_group.left_btn), ("中", self.align_group.center_btn), ("右", self.align_group.right_btn)):
            button.setText(text)
            button.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
            button.setMinimumWidth(PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.vertical_layout_check = QCheckBox("竖排")
        self.vertical_layout_check.setProperty("role", "inlineCheck")
        self.vertical_layout_check.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        self.vertical_layout_check.setMinimumWidth(PropertyPanelA2.ACTION_BUTTON_WIDTH)
        self.typography_align_row = self._make_param_row(
            "对齐",
            self.align_group,
            self.vertical_layout_check,
            stretch_last=False,
        )
        card_layout.addLayout(self.typography_align_row)

        # 文本框（自动适配）和 间距/字距/边距 合并展示，去掉中间分割线，减少垂直空白
        self.auto_fit_check = QCheckBox("自动适配边框")
        self.auto_fit_check.setChecked(True)
        self.auto_fit_row = self._make_param_row("文本框", self.auto_fit_check)
        card_layout.addLayout(self.auto_fit_row)

        self.line_spacing_spin = self._make_spin(60)
        self.line_spacing_spin.setRange(50, 300)
        self.line_spacing_spin.setValue(120)
        self.line_spacing_spin.setSuffix("%")
        self.letter_spacing_spin = self._make_spin(60)
        self.letter_spacing_spin.setRange(-20, 100)
        self.letter_spacing_spin.setValue(0)
        self.letter_spacing_spin.setSuffix("px")
        self.text_box_padding_spin = self._make_spin(60)
        self.text_box_padding_spin.setRange(0, 200)
        self.text_box_padding_spin.setValue(5)
        self.text_box_padding_spin.setSuffix("px")
        # 间距、字距、边距 三个参数排成同一行
        self.spacing_params_row = self._make_parameter_grid(
            ("间距", self.line_spacing_spin),
            ("字距", self.letter_spacing_spin),
            ("边距", self.text_box_padding_spin),
            single_row=True,
        )
        self.text_box_params_row = self.spacing_params_row
        card_layout.addWidget(self.spacing_params_row)

        parent_layout.addWidget(card)

    def create_appearance_card(self, parent_layout):
        """创建外观卡片（紧凑型）：删除独立启用面板，将描边开关与参数同一行合并。"""
        card, card_layout = self._make_section_card("外观")
        self.appearance_card = card
        self.appearance_card_title = card.title_label
        self.appearance_summary_label = card.summary_label
        # 紧凑内部布局：去除多余空白
        card_layout.setContentsMargins(8, 5, 8, 6)
        card_layout.setSpacing(5)

        # 文字填充模式分段按钮（无/纯色/渐变），去除"文字填充"小标题
        text_fill_layout, self.text_fill_button_group, self.text_fill_mode_buttons = self._make_segment_row(
            [("无", "none"), ("纯色", "solid"), ("渐变", "gradient")],
            "solid",
            self._set_text_fill_mode,
            "textFillMode",
        )
        card_layout.addLayout(text_fill_layout)

        # 纯色填充（颜色 + 透明度，纵向挨着，无分割线）
        self.text_color_controls, text_color_layout = self._make_subpanel()
        # 减小子面板内边距
        text_color_layout.setContentsMargins(6, 4, 6, 4)
        text_color_layout.setSpacing(4)
        self.text_color = ColorIndicator((0, 0, 0, 255), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
        self.text_color_button = self._make_compact_value_button("文字颜色")
        self.text_color_button.clicked.connect(self.text_color.click)
        text_color_layout.addLayout(self._make_param_row("颜色", self.text_color_button, self.text_color, stretch_last=False))

        # 透明度：紧跟颜色行，共用 subpanel，减少垂直间距
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setMinimumWidth(90)
        self.opacity_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setFixedWidth(42)
        self.opacity_label.setAlignment(Qt.AlignCenter)
        text_color_layout.addLayout(self._make_param_row("透明", self.opacity_slider, self.opacity_label, stretch_last=False))
        card_layout.addWidget(self.text_color_controls)

        # 渐变填充控件（与纯色控件互斥显示）
        self.gradient_controls, gradient_controls_layout = self._make_subpanel()
        gradient_controls_layout.setContentsMargins(6, 4, 6, 4)
        gradient_controls_layout.setSpacing(4)
        self.gradient_enable_check = A2Switch()
        self.gradient_enable_check.hide()  # 隐藏独立开关：已用顶部分段按钮控制
        self.gradient_type_combo = QComboBox()
        self.gradient_type_combo.addItems(["线性", "径向", "角度"])
        self.gradient_type_combo.setFixedWidth(80)
        gradient_controls_layout.addLayout(self._make_param_row("类型", self.gradient_type_combo, stretch_last=False))
        gradient_color_layout = QHBoxLayout()
        self.gradient_start_color = ColorIndicator((0, 0, 0, 255))
        self.gradient_start_color.color_changed.connect(self.on_gradient_color_changed)
        gradient_color_layout.addWidget(self.gradient_start_color)
        gradient_color_layout.addWidget(QLabel("→"))
        self.gradient_end_color = ColorIndicator((255, 255, 255, 255))
        self.gradient_end_color.color_changed.connect(self.on_gradient_color_changed)
        gradient_color_layout.addWidget(self.gradient_end_color)
        gradient_color_layout.addStretch()
        gradient_controls_layout.addLayout(self._make_param_row("渐变色", QWidget(), stretch_last=False))
        gradient_controls_layout.addLayout(gradient_color_layout)
        card_layout.addWidget(self.gradient_controls)

        # 描边：紧凑一行布局——复选框代替独立的48px启用面板；不添加"描边"小标题和分割线
        # □ 描边  [宽度spin]  [颜色按钮] [色板] —— 全塞入一行，极大节省空间
        stroke_row_wrap = QHBoxLayout()
        stroke_row_wrap.setContentsMargins(0, 0, 0, 0)
        stroke_row_wrap.setSpacing(PropertyPanelA2.ROW_GAP)
        self.stroke_enable_check = QCheckBox("描边")  # 替代 A2Switch + stroke_title_label 行
        self.stroke_enable_check.setProperty("role", "inlineCheck")
        self.stroke_enable_check.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
        self.stroke_enable_check.stateChanged.connect(self.on_stroke_enabled_changed)
        self.stroke_width_spin = self._make_spin(68)
        self.stroke_width_spin.setRange(1, 20)
        self.stroke_width_spin.setValue(2)
        self.stroke_width_spin.setSuffix("px")
        self.stroke_width_spin.setEnabled(False)
        self.stroke_color = ColorIndicator((0, 0, 0, 255), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
        self.stroke_color.setEnabled(False)
        self.stroke_color_button = self._make_compact_value_button("描边色")
        self.stroke_color_button.clicked.connect(self.stroke_color.click)
        self.stroke_color_button.setEnabled(False)

        stroke_row_wrap.addWidget(self.stroke_enable_check)
        stroke_row_wrap.addSpacing(4)
        stroke_row_wrap.addWidget(self.stroke_width_spin)
        stroke_row_wrap.addWidget(self.stroke_color_button, 1)
        stroke_row_wrap.addWidget(self.stroke_color)
        card_layout.addLayout(stroke_row_wrap)

        # 占位兼容：保留旧的属性引用，避免handlers中对stroke_toggle_panel/stroke_controls的引用报错
        self.stroke_toggle_panel, _ = self._make_subpanel()
        self.stroke_toggle_panel.setVisible(False)
        self.stroke_controls, _ = self._make_subpanel()
        self.stroke_controls.setVisible(False)
        # 隐藏不必要的标题标签（避免sync时找不到）
        self.stroke_title_label = QLabel()
        self.stroke_title_label.setVisible(False)

        parent_layout.addWidget(card)

    def create_background_card(self, parent_layout):
        """创建文字背景卡片（紧凑型）；该低频效果仅出现在“更多参数”页。"""
        card, card_layout = self._make_section_card("文字背景")
        self.background_card = card
        self.background_card_title = card.title_label
        self.background_summary_label = card.summary_label
        card_layout.setContentsMargins(8, 5, 8, 6)
        card_layout.setSpacing(5)

        # 背景模式（无/纯色/渐变）分段按钮，顶部分段即代表启用与否，无需独立开关
        background_layout, self.background_button_group, self.background_mode_buttons = self._make_segment_row(
            [("无", "none"), ("纯色", "solid"), ("渐变", "gradient")],
            "none",
            self._set_background_mode,
            "backgroundMode",
        )
        card_layout.addLayout(background_layout)

        self.background_controls, bg_layout = self._make_subpanel()
        bg_layout.setContentsMargins(6, 4, 6, 4)
        bg_layout.setSpacing(4)
        self.bg_enable_check = A2Switch()
        self.bg_enable_check.hide()  # 用分段按钮控制显隐，不再显示独立开关
        self.bg_enable_check.stateChanged.connect(self.on_background_enabled_changed)
        self.bg_color = ColorIndicator((255, 255, 255, 255), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
        self.bg_color.color_changed.connect(self.on_background_color_changed)
        self.bg_color_button = self._make_compact_value_button("背景颜色")
        self.bg_color_button.clicked.connect(self.bg_color.click)
        bg_layout.addLayout(self._make_param_row("颜色", self.bg_color_button, self.bg_color, stretch_last=False))

        self.bg_opacity_slider = QSlider(Qt.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(100)
        self.bg_opacity_slider.valueChanged.connect(self.on_background_opacity_changed)
        self.bg_opacity_label = QLabel("100%")
        self.bg_opacity_label.setFixedWidth(42)
        self.bg_opacity_label.setAlignment(Qt.AlignCenter)
        bg_layout.addLayout(self._make_param_row("透明", self.bg_opacity_slider, self.bg_opacity_label, stretch_last=False))

        self.bg_size_slider = QSlider(Qt.Horizontal)
        self.bg_size_slider.setRange(-50, 50)
        self.bg_size_slider.setValue(5)
        self.bg_size_slider.valueChanged.connect(self.on_background_size_changed)
        self.bg_size_label = QLabel("+5")
        self.bg_size_label.setFixedWidth(42)
        self.bg_size_label.setAlignment(Qt.AlignCenter)
        bg_layout.addLayout(self._make_param_row("大小", self.bg_size_slider, self.bg_size_label, stretch_last=False))
        card_layout.addWidget(self.background_controls)

        # 背景渐变类型：和背景控件合并到同一子面板（可见时显示），不用额外摘要行
        # 背景高级摘要（保留引用兼容，默认隐藏）
        self.background_advanced_row, background_advanced_layout = self._make_subpanel()
        self.background_advanced_row.setVisible(False)
        background_advanced_header = QHBoxLayout()
        background_advanced_header.setContentsMargins(0, 0, 0, 0)
        self.background_advanced_summary = QLabel("透明度、大小、渐变类型")
        self.background_advanced_summary.setProperty("role", "summaryLabel")
        self.background_advanced_summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        background_advanced_header.addStretch()
        background_advanced_header.addWidget(self.background_advanced_summary)
        background_advanced_layout.addLayout(background_advanced_header)

        self._sync_appearance_visibility()
        parent_layout.addWidget(card)

    def create_position_dimension_card(self, parent_layout):
        """基本参数页底部：位置和尺寸（默认折叠，节省首屏高度；展开时可编辑）。
        保留与 handlers 兼容的属性名：x_spin, y_spin, width_spin, height_spin, position_summary_label。"""
        self.pos_group = CollapsibleGroupBox("位置和尺寸", collapsed=True)  # 默认折叠：显著降低首屏高度
        self.pos_group.title_frame.setFixedHeight(PropertyPanelA2.HEADER_HEIGHT)
        self.pos_group.container_layout.setContentsMargins(8, 5, 8, 6)
        self.pos_group.container_layout.setSpacing(5)
        self.position_summary_label = QLabel()
        self.position_summary_label.setProperty("role", "summaryLabel")
        self.position_summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.position_summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        title_layout = self.pos_group.title_frame.layout()
        if title_layout:
            title_layout.insertWidget(1, self.position_summary_label)
            self.position_summary_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        pos_layout = QVBoxLayout()
        pos_layout.setContentsMargins(0, 0, 0, 0)
        pos_layout.setSpacing(PropertyPanelA2.ROW_GAP)

        self.position_box, position_layout = self._make_subpanel()
        self.size_box, size_layout = self._make_subpanel()

        def make_spin(attr):
            spin = QSpinBox()
            if attr in ("width", "height"):
                spin.setRange(1, 9999)
            else:
                spin.setRange(-9999, 9999)
            spin.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
            spin.setMinimumWidth(74)
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return spin

        def add_pair_row(layout, first, second):
            row = QHBoxLayout()
            row.setSpacing(PropertyPanelA2.ROW_GAP)
            for title, attr in (first, second):
                label = self._label(title, width=PropertyPanelA2.POSITION_LABEL_WIDTH)
                spin = make_spin(attr)
                setattr(self, f"{attr}_spin", spin)
                row.addWidget(label)
                row.addWidget(spin, 1)
            layout.addLayout(row)

        position_layout.addWidget(self._muted_label("位置"))
        add_pair_row(position_layout, ("X", "x"), ("Y", "y"))
        size_layout.addWidget(self._muted_label("尺寸"))
        add_pair_row(size_layout, ("W", "width"), ("H", "height"))

        pos_layout.addWidget(self.position_box)
        pos_layout.addWidget(self.size_box)
        self.pos_group.add_content_layout(pos_layout)
        # 折叠/展开时同步摘要（值变化时由handlers触发刷新）
        self._sync_position_summary()
        parent_layout.addWidget(self.pos_group)

    def create_effects_only_settings(self, parent_layout):
        """更多参数页：仅保留阴影与发光（低频视觉效果）。
        位置与尺寸已迁移至基本参数页的 create_position_dimension_card。"""
        from app.ui.property_widgets import switch_row

        self.effects_group = CollapsibleGroupBox("文字阴影与发光", collapsed=False)
        self.effects_group.title_frame.setFixedHeight(PropertyPanelA2.HEADER_HEIGHT)
        self.effects_group.container_layout.setContentsMargins(8, 5, 8, 6)
        self.effects_group.container_layout.setSpacing(5)
        self.create_effects_content(self.effects_group)
        parent_layout.addWidget(self.effects_group)

    def _checked_segment_value(self, buttons, property_name, default_value):
        for button in buttons:
            if button.isChecked():
                return button.property(property_name) or default_value
        return default_value

    def _set_text_fill_mode(self, mode, update_layer=True):
        mode = mode if mode in {"none", "solid", "gradient"} else "solid"
        for button in getattr(self, "text_fill_mode_buttons", []):
            button.setChecked(button.property("textFillMode") == mode)

        if update_layer and self.text_layer:
            gradient_enabled = mode == "gradient"
            if hasattr(self.text_layer, "gradient_enabled"):
                self.text_layer.gradient_enabled = gradient_enabled
                self.property_changed.emit("gradient_enabled", gradient_enabled)

            current_color = getattr(self.text_layer, "text_color", (0, 0, 0, 255))
            if len(current_color) >= 4:
                if mode == "none" and current_color[3] != 0:
                    new_color = (current_color[0], current_color[1], current_color[2], 0)
                    self.text_layer.text_color = new_color
                    self.text_color.current_color = new_color
                    self.text_color.update_color_display()
                    self.property_changed.emit("text_color", new_color)
                elif mode != "none" and current_color[3] == 0:
                    new_color = (current_color[0], current_color[1], current_color[2], 255)
                    self.text_layer.text_color = new_color
                    self.text_color.current_color = new_color
                    self.text_color.update_color_display()
                    self.property_changed.emit("text_color", new_color)

        self._sync_appearance_visibility(text_fill_mode=mode)

    def _set_background_mode(self, mode, update_layer=True):
        mode = mode if mode in {"none", "solid", "gradient"} else "none"
        for button in getattr(self, "background_mode_buttons", []):
            button.setChecked(button.property("backgroundMode") == mode)

        enabled = mode != "none"
        if update_layer and self.text_layer and hasattr(self.text_layer, "background_enabled"):
            self.text_layer.background_enabled = enabled
            self.property_changed.emit("background_enabled", enabled)

        if hasattr(self, "bg_enable_check"):
            self.bg_enable_check.setChecked(enabled)
        self._sync_appearance_visibility(background_mode=mode)

    def _sync_appearance_visibility(self, text_fill_mode=None, background_mode=None):
        if text_fill_mode is None:
            if self.text_layer:
                color = getattr(self.text_layer, "text_color", (0, 0, 0, 255))
                if getattr(self.text_layer, "gradient_enabled", False):
                    text_fill_mode = "gradient"
                elif len(color) >= 4 and color[3] == 0:
                    text_fill_mode = "none"
                else:
                    text_fill_mode = "solid"
            else:
                text_fill_mode = self._checked_segment_value(
                    getattr(self, "text_fill_mode_buttons", []), "textFillMode", "solid"
                )

        if background_mode is None:
            if self.text_layer:
                background_mode = "solid" if getattr(self.text_layer, "background_enabled", False) else "none"
            else:
                background_mode = self._checked_segment_value(
                    getattr(self, "background_mode_buttons", []), "backgroundMode", "none"
                )

        for button in getattr(self, "text_fill_mode_buttons", []):
            button.setChecked(button.property("textFillMode") == text_fill_mode)
        for button in getattr(self, "background_mode_buttons", []):
            button.setChecked(button.property("backgroundMode") == background_mode)

        text_color_visible = text_fill_mode == "solid"
        gradient_visible = text_fill_mode == "gradient"
        if hasattr(self, "text_color_controls"):
            self.text_color_controls.setVisible(text_color_visible)
        if hasattr(self, "gradient_controls"):
            self.gradient_controls.setVisible(gradient_visible)
        if hasattr(self, "gradient_enable_check"):
            self.gradient_enable_check.setChecked(gradient_visible)
        for control_name in ("gradient_type_combo", "gradient_start_color", "gradient_end_color"):
            if hasattr(self, control_name):
                getattr(self, control_name).setEnabled(gradient_visible)

        background_visible = background_mode != "none"
        if hasattr(self, "background_controls"):
            self.background_controls.setVisible(background_visible)
        for control_name in ("bg_color", "bg_opacity_slider", "bg_size_slider"):
            if hasattr(self, control_name):
                getattr(self, control_name).setEnabled(background_visible)
        if hasattr(self, "bg_color_button"):
            self.bg_color_button.setEnabled(background_visible)
        if hasattr(self, "stroke_enable_check"):
            stroke_visible = self.stroke_enable_check.isChecked()
            for control_name in ("stroke_width_spin", "stroke_color", "stroke_color_button"):
                if hasattr(self, control_name):
                    getattr(self, control_name).setEnabled(stroke_visible)
        self._sync_panel_summaries(text_fill_mode=text_fill_mode, background_mode=background_mode)

    def _set_summary_text(self, label_name, text):
        label = getattr(self, label_name, None)
        if label is not None:
            label.setText(text)

    def _alignment_summary_text(self):
        if hasattr(self, "align_group"):
            if self.align_group.center_btn.isChecked():
                return "居中"
            if self.align_group.right_btn.isChecked():
                return "右对齐"
        return "左对齐"

    def _sync_panel_summaries(self, text_fill_mode=None, background_mode=None):
        if hasattr(self, "text_count_label") and hasattr(self, "binding_mode_check"):
            count_text = self.text_count_label.text() or "0 条"
            binding_text = "绑定模式开启" if self.binding_mode_check.isChecked() else "绑定模式关闭"
            self._set_summary_text("content_summary_label", f"{count_text} · {binding_text}")

        if hasattr(self, "font_combo") and hasattr(self, "font_size_spin"):
            font_text = self.font_combo.currentText().strip() or "微软雅黑"
            self._set_summary_text("font_summary_label", f"{font_text} · {self.font_size_spin.value()}px")

        if hasattr(self, "auto_fit_check"):
            box_text = "自动边框" if self.auto_fit_check.isChecked() else "手动尺寸"
            self._set_summary_text("typography_summary_label", f"{self._alignment_summary_text()} · {box_text}")

        if text_fill_mode is None:
            text_fill_mode = self._checked_segment_value(
                getattr(self, "text_fill_mode_buttons", []), "textFillMode", "solid"
            )
        if background_mode is None:
            background_mode = self._checked_segment_value(
                getattr(self, "background_mode_buttons", []), "backgroundMode", "none"
            )
        text_fill_label = {"none": "无文字", "solid": "纯色文字", "gradient": "渐变文字"}.get(text_fill_mode, "纯色文字")
        background_label = {"none": "无背景", "solid": "纯色背景", "gradient": "渐变背景"}.get(background_mode, "无背景")
        stroke_label = "描边开启" if getattr(self, "stroke_enable_check", None) and self.stroke_enable_check.isChecked() else "描边关闭"
        self._set_summary_text("appearance_summary_label", f"{text_fill_label} · {stroke_label}")
        self._set_summary_text("background_summary_label", background_label)

    def create_core_params_card(self, parent_layout):
        """创建核心参数卡片。"""
        card, card_layout = self._make_section_card("核心参数", self.reset_core_params)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(10)

        def label(text):
            widget = QLabel(text)
            widget.setFixedWidth(58)
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            widget.setProperty("role", "fieldLabel")
            return widget

        def row(title, *widgets, stretch_last=True):
            line = QHBoxLayout()
            line.setSpacing(6)
            line.addWidget(label(title))
            for widget in widgets:
                if stretch_last and widget is widgets[-1]:
                    line.addWidget(widget, 1)
                else:
                    line.addWidget(widget)
            card_layout.addLayout(line)
            return line

        def inline_label(text, width=None):
            widget = QLabel(text)
            if width is not None:
                widget.setFixedWidth(width)
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            widget.setProperty("role", "fieldLabel")
            return widget

        def parameter_grid(*pairs):
            container = QWidget()
            container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid = QGridLayout(container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(8)

            for index, (title, control) in enumerate(pairs):
                row_index = index // 2
                base_col = (index % 2) * 3
                title_label = label(title) if index % 2 == 0 else inline_label(title, 40)
                grid.addWidget(title_label, row_index, base_col)
                grid.addWidget(control, row_index, base_col + 1)
                if index % 2 == 0:
                    grid.setColumnMinimumWidth(base_col + 2, 18)
                if index == 1:
                    container._responsive_second_label = title_label
                    container._responsive_second_control = control

            grid.setColumnStretch(2, 1)
            grid.setColumnStretch(5, 1)
            card_layout.addWidget(container)
            return container

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
        quick_title.setProperty("role", "fieldLabel")
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
        recent_title.setProperty("role", "fieldLabel")
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
        self.bold_btn.setFixedSize(PropertyPanelA2.ICON_BUTTON_WIDTH, PropertyPanelA2.CONTROL_HEIGHT)
        self.italic_btn = ToggleButton("I")
        self.italic_btn.setFixedSize(PropertyPanelA2.ICON_BUTTON_WIDTH, PropertyPanelA2.CONTROL_HEIGHT)
        row("大小", self.font_size_spin, self.bold_btn, self.italic_btn, stretch_last=False)

        self.align_group = AlignButtonGroup()
        for button in (self.align_group.left_btn, self.align_group.center_btn, self.align_group.right_btn):
            button.setFixedSize(PropertyPanelA2.ICON_BUTTON_WIDTH, PropertyPanelA2.CONTROL_HEIGHT)
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
        self.spacing_params_row = parameter_grid(
            ("间距", self.line_spacing_spin),
            ("字距", self.letter_spacing_spin),
        )

        card_layout.addWidget(self._make_core_divider())

        self.auto_fit_check = QCheckBox("自动适配边框")
        self.auto_fit_check.setChecked(True)
        self.text_box_padding_spin = make_spin(76)
        self.text_box_padding_spin.setRange(0, 200)
        self.text_box_padding_spin.setValue(5)
        self.text_box_padding_spin.setSuffix("px")
        self.text_box_params_row = parameter_grid(
            ("文本框", self.auto_fit_check),
            ("边距", self.text_box_padding_spin),
        )

        parent_layout.addWidget(card)


    def resizeEvent(self, event):
        """窄面板下拆分参数行，避免标签和控件互相压住。"""
        super().resizeEvent(event)
        self._update_responsive_parameter_rows()



# 以下方法实现位于各个 mixin 模块中，通过多重继承组合进来。
# 主类仅保留类声明、类级属性、__init__ 与 Qt 事件重写 resizeEvent。
