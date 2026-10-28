#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
"""
整合的文字图层参数模块 - 专业UI设计
遵循现代设计原则，将所有参数整合到一个紧凑的界面中
"""

import logging

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QSlider, QFrame,
                               QToolButton, QButtonGroup, QSizePolicy, QCheckBox,
                               QTextEdit, QLineEdit, QComboBox, QScrollArea, QDialog, QCompleter,
                               QGridLayout)
from PySide6.QtCore import Qt, Signal, QSize, QStringListModel, QRectF
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QIcon

import sys
import os
import json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.text_layer import TextLayer, TextAlign, FontStyle
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.design_spec import Scale as _Scale, Space as _Space, Width as _Width
from app.ui.property_panel_a2 import PropertyPanelA2
from app.ui.property_widgets import switch_row


from app.ui.text_panel_widgets import (
    A2Switch, ToggleButton, AlignButtonGroup, ColorIndicator
)

class IntegratedTextPanelContent(object):
    """Mixin for integrated_text_panel_content (split from IntegratedTextPanel)."""

    def _update_responsive_parameter_rows(self):
        available_width = self.width()
        stacked = available_width < 360
        for container in (
            getattr(self, "spacing_params_row", None),
            getattr(self, "text_box_params_row", None),
        ):
            if container is None:
                continue
            grid = container.layout()
            # 单排多参数（间距/字距/边距）容器
            if getattr(container, "_responsive_single", False):
                self._relayout_single_row(container, grid, stacked)
                continue
            second_label = getattr(container, "_responsive_second_label", None)
            second_control = getattr(container, "_responsive_second_control", None)
            if not isinstance(grid, QGridLayout) or second_label is None or second_control is None:
                continue
            if stacked:
                grid.addWidget(second_label, 1, 0)
                grid.addWidget(second_control, 1, 1)
            else:
                grid.addWidget(second_label, 0, 3)
                grid.addWidget(second_control, 0, 4)

    def _relayout_single_row(self, container, grid, stacked):
        """重排「间距 | 字距 | 边距」这类多参数单行容器。

        原实现是「永远一行，不拆」，但面板实际宽度是 344px（属性栏固定宽度），
        而 3 组「标签 40 + 控件 60」加上弹性间隔需要 ~350px —— 放不下。
        结果是 QGridLayout 挤压列宽，标签被压到 12px 高、控件错位，
        截图里能看到「间距」「字距」标签与下方 SpinBox 不对齐。

        窄面板时按 2 行重排（第一行 2 组，第二行 1 组），宽面板保持单行。
        """
        labels = getattr(container, "_responsive_labels", None)
        controls = getattr(container, "_responsive_controls", None)
        if not labels or not controls:
            return

        # 已处于目标形态就跳过，避免每次 resize 都重建布局（会闪）
        want_stacked = stacked
        if getattr(container, "_responsive_is_stacked", None) is want_stacked:
            return
        container._responsive_is_stacked = want_stacked

        for label, control in zip(labels, controls):
            grid.removeWidget(label)
            grid.removeWidget(control)

        # 清掉之前的列拉伸，重新分配
        for col in range(0, 12):
            grid.setColumnStretch(col, 0)

        if want_stacked:
            # 2 行：每组占「标签 + 控件」两列，行内右侧留 stretch 吸收余量
            for index, (label, control) in enumerate(zip(labels, controls)):
                row = index // 2
                base = (index % 2) * 2
                grid.addWidget(label, row, base)
                grid.addWidget(control, row, base + 1)
            grid.setColumnStretch(4, 1)
        else:
            for index, (label, control) in enumerate(zip(labels, controls)):
                col = index * 3
                grid.addWidget(label, 0, col)
                grid.addWidget(control, 0, col + 1)
                grid.setColumnStretch(col + 2, 1)

    def create_advanced_settings(self, parent_layout):
        """创建高级设置区域 - 补充完整内容"""
        # 位置和尺寸组：折叠时保留关键摘要，展开后按职责拆成两个小面板。
        self.pos_group = CollapsibleGroupBox("位置和尺寸", collapsed=True)
        self.pos_group.title_frame.setFixedHeight(PropertyPanelA2.HEADER_HEIGHT)
        self.pos_group.container_layout.setContentsMargins(*PropertyPanelA2.BODY_MARGINS)
        self.pos_group.container_layout.setSpacing(PropertyPanelA2.SECTION_GAP)
        self.position_summary_label = QLabel()
        self.position_summary_label.setProperty("role", "summaryLabel")
        self.position_summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.position_summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        title_layout = self.pos_group.title_frame.layout()
        if title_layout:
            title_layout.insertWidget(1, self.position_summary_label)
            # 摘要标签同样需鼠标穿透，使整条标题栏均可点击折叠
            self.position_summary_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        pos_layout = QVBoxLayout()
        pos_layout.setContentsMargins(0, 0, 0, 0)
        pos_layout.setSpacing(PropertyPanelA2.ROW_GAP)

        self.position_box, position_layout = self._make_subpanel()
        self.size_box, size_layout = self._make_subpanel()

        def make_spin(attr):
            spin = QSpinBox()
            spin.setRange(1, 9999) if attr in ["width", "height"] else spin.setRange(-9999, 9999)
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
        self._sync_position_summary()

        # 文字阴影和发光与背景同属低频视觉效果，集中放在“更多参数”页顶部。
        self.effects_group = CollapsibleGroupBox("文字阴影与发光", collapsed=False)
        self.effects_group.title_frame.setFixedHeight(PropertyPanelA2.HEADER_HEIGHT)
        self.effects_group.container_layout.setContentsMargins(*PropertyPanelA2.BODY_MARGINS)
        self.effects_group.container_layout.setSpacing(PropertyPanelA2.SECTION_GAP)
        self.create_effects_content(self.effects_group)
        parent_layout.addWidget(self.effects_group)
        parent_layout.addWidget(self.pos_group)

        # 文字内容管理功能已移除 - 只保留图层属性中的编辑按钮

        # 背景和渐变已合并到“外观”卡片，避免重复控件覆盖同名状态。

    def _sync_position_summary(self):
        """同步位置折叠组摘要，方便未展开时快速确认图层几何信息。"""
        x_value = self.x_spin.value() if hasattr(self, "x_spin") else 0
        y_value = self.y_spin.value() if hasattr(self, "y_spin") else 0
        width_value = self.width_spin.value() if hasattr(self, "width_spin") else 1
        height_value = self.height_spin.value() if hasattr(self, "height_spin") else 1
        if hasattr(self, "position_summary_label"):
            self.position_summary_label.setText(f"X {x_value} · Y {y_value} · {width_value} × {height_value}")

    def create_effects_content(self, parent_group):
        """创建效果和样式内容"""
        effects_layout = QVBoxLayout()
        effects_layout.setSpacing(8)

        # 阴影效果
        shadow_row, self.shadow_check = switch_row("阴影")
        self.shadow_check.stateChanged.connect(self.on_shadow_enabled_changed)  # 连接信号
        effects_layout.addLayout(shadow_row)

        # 阴影参数
        shadow_params_layout = QHBoxLayout()
        shadow_params_layout.addWidget(QLabel("偏移:"))
        self.shadow_x_spin = QSpinBox()
        self.shadow_x_spin.setRange(-50, 50)
        self.shadow_x_spin.setValue(2)
        self.shadow_x_spin.setFixedWidth(_Width.SPIN)
        self.shadow_x_spin.valueChanged.connect(self.on_shadow_params_changed)  # 连接信号
        shadow_params_layout.addWidget(self.shadow_x_spin)

        shadow_params_layout.addSpacing(10)
        shadow_params_layout.addWidget(QLabel("Y:"))
        self.shadow_y_spin = QSpinBox()
        self.shadow_y_spin.setRange(-50, 50)
        self.shadow_y_spin.setValue(2)
        self.shadow_y_spin.setFixedWidth(_Width.SPIN)
        self.shadow_y_spin.valueChanged.connect(self.on_shadow_params_changed)  # 连接信号
        shadow_params_layout.addWidget(self.shadow_y_spin)

        shadow_params_layout.addSpacing(10)
        shadow_params_layout.addWidget(QLabel("模糊:"))
        self.shadow_blur_spin = QSpinBox()
        self.shadow_blur_spin.setRange(0, 20)
        self.shadow_blur_spin.setValue(3)
        self.shadow_blur_spin.setFixedWidth(_Width.SPIN)
        self.shadow_blur_spin.valueChanged.connect(self.on_shadow_params_changed)  # 连接信号
        shadow_params_layout.addWidget(self.shadow_blur_spin)

        shadow_params_layout.addStretch()
        effects_layout.addLayout(shadow_params_layout)

        # 阴影颜色
        shadow_color_layout = QHBoxLayout()
        shadow_color_layout.addWidget(QLabel("颜色:"))
        self.shadow_color = ColorIndicator((0, 0, 0, 128), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
        self.shadow_color.color_changed.connect(self.on_shadow_color_changed)  # 连接信号
        shadow_color_layout.addWidget(self.shadow_color)
        shadow_color_layout.addStretch()
        effects_layout.addLayout(shadow_color_layout)

        # 发光效果
        glow_row, self.glow_check = switch_row("发光")
        self.glow_check.stateChanged.connect(self.on_glow_enabled_changed)  # 连接信号
        effects_layout.addLayout(glow_row)

        # 发光参数
        glow_params_layout = QHBoxLayout()
        glow_params_layout.addWidget(QLabel("强度:"))
        self.glow_strength_spin = QSpinBox()
        self.glow_strength_spin.setRange(0, 20)
        self.glow_strength_spin.setValue(5)
        self.glow_strength_spin.setFixedWidth(_Width.SPIN)
        self.glow_strength_spin.valueChanged.connect(self.on_glow_params_changed)  # 连接信号
        glow_params_layout.addWidget(self.glow_strength_spin)

        glow_params_layout.addSpacing(10)
        glow_params_layout.addWidget(QLabel("半径:"))
        self.glow_radius_spin = QSpinBox()
        self.glow_radius_spin.setRange(1, 50)
        self.glow_radius_spin.setValue(10)
        self.glow_radius_spin.setFixedWidth(_Width.SPIN)
        self.glow_radius_spin.valueChanged.connect(self.on_glow_params_changed)  # 连接信号
        glow_params_layout.addWidget(self.glow_radius_spin)

        glow_params_layout.addStretch()
        effects_layout.addLayout(glow_params_layout)

        # 发光颜色与透明度
        glow_color_layout = QHBoxLayout()
        glow_color_layout.addWidget(QLabel("颜色:"))
        self.glow_color = ColorIndicator((255, 255, 255, 255), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
        self.glow_color.color_changed.connect(self.on_glow_color_changed)
        glow_color_layout.addWidget(self.glow_color)
        glow_color_layout.addSpacing(10)
        glow_color_layout.addWidget(QLabel("透明度:"))
        self.glow_opacity_spin = QSpinBox()
        self.glow_opacity_spin.setRange(0, 100)
        self.glow_opacity_spin.setSuffix("%")
        self.glow_opacity_spin.setValue(100)
        self.glow_opacity_spin.setFixedWidth(_Width.COMBO)
        self.glow_opacity_spin.valueChanged.connect(self.on_glow_opacity_changed)
        glow_color_layout.addWidget(self.glow_opacity_spin)
        glow_color_layout.addStretch()
        effects_layout.addLayout(glow_color_layout)

        parent_group.add_content_layout(effects_layout)
        # 根据模型能力调整可见性
        self._sync_feature_visibility()



    def create_background_content(self, parent_group):
        """创建背景和渐变内容"""
        bg_layout = QVBoxLayout()
        bg_layout.setSpacing(8)

        # 背景启用
        bg_enable_layout, self.bg_enable_check = switch_row("背景")
        self.bg_enable_check.stateChanged.connect(self.on_background_enabled_changed)  # 连接信号
        bg_layout.addLayout(bg_enable_layout)

        # 背景颜色
        bg_color_layout = QHBoxLayout()
        bg_color_layout.addWidget(QLabel("背景颜色:"))
        self.bg_color = ColorIndicator((255, 255, 255, 255), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
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
        self.bg_opacity_slider.setFixedHeight(_Scale.PX[_Scale.MD])
        # 滑块样式由 panel_qss 的 QSlider 角色统一提供（与全局主题一致）
        self.bg_opacity_slider.valueChanged.connect(self.on_background_opacity_changed)  # 连接信号
        self.bg_opacity_label = QLabel("100%")
        self.bg_opacity_label.setFixedWidth(_Width.VALUE_LABEL)
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
        self.bg_size_slider.setFixedHeight(_Scale.PX[_Scale.MD])
        # 滑块样式由 panel_qss 的 QSlider 角色统一提供
        self.bg_size_slider.valueChanged.connect(self.on_background_size_changed)  # 连接信号
        self.bg_size_label = QLabel("+5")
        self.bg_size_label.setFixedWidth(_Width.VALUE_LABEL)
        self.bg_size_label.setAlignment(Qt.AlignCenter)

        bg_size_layout.addWidget(self.bg_size_slider)
        bg_size_layout.addWidget(self.bg_size_label)
        bg_size_layout.addStretch()
        bg_layout.addLayout(bg_size_layout)

        # 渐变设置
        gradient_layout = QVBoxLayout()
        gradient_layout.setSpacing(_Space.XS)

        # 渐变启用
        gradient_enable_layout, self.gradient_enable_check = switch_row("渐变")
        self.gradient_enable_check.stateChanged.connect(self.on_gradient_enabled_changed)  # 连接信号
        gradient_layout.addLayout(gradient_enable_layout)

        # 渐变类型
        gradient_type_layout = QHBoxLayout()
        gradient_type_layout.addWidget(QLabel("渐变类型:"))
        self.gradient_type_combo = QComboBox()
        self.gradient_type_combo.addItems(["线性", "径向", "角度"])
        self.gradient_type_combo.setFixedWidth(_Width.COMBO)
        # 下拉样式由 panel_qss 的 QComboBox 角色统一提供
        self.gradient_type_combo.currentTextChanged.connect(self.on_gradient_type_changed)  # 连接信号
        gradient_type_layout.addWidget(self.gradient_type_combo)
        gradient_type_layout.addStretch()
        gradient_layout.addLayout(gradient_type_layout)

        # 渐变颜色
        gradient_color_layout = QHBoxLayout()
        gradient_color_layout.addWidget(QLabel("渐变颜色:"))
        self.gradient_start_color = ColorIndicator((0, 0, 0, 255), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
        self.gradient_start_color.color_changed.connect(self.on_gradient_color_changed)  # 连接信号
        gradient_color_layout.addWidget(self.gradient_start_color)
        gradient_color_layout.addWidget(QLabel("→"))
        self.gradient_end_color = ColorIndicator((255, 255, 255, 255), size=PropertyPanelA2.COLOR_SWATCH_SIZE)
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
        self.inline_text_edit.selectionChanged.connect(self._sync_range_color_actions)
        self.range_color_btn.clicked.connect(self.on_apply_range_text_color)
        self.clear_range_color_btn.clicked.connect(self.on_clear_range_text_color)
        self.range_size_btn.clicked.connect(self.on_apply_range_font_size)
        self.clear_range_size_btn.clicked.connect(self.on_clear_range_font_size)
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
        cn_map = getattr(self, "_font_cn_names", None) or {}
        cn_name = cn_map.get(font_name) or self.FONT_CN_ALIAS.get(font_name)
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
        cn_map = getattr(self, "_font_cn_names", None) or {}
        reverse_map = {v: k for k, v in cn_map.items()}
        reverse_map.update({v: k for k, v in self.FONT_CN_ALIAS.items()})
        if name in reverse_map:
            return reverse_map[name]
        if name in cn_map or name in self.FONT_CN_ALIAS:
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
            logger.warning("静默异常已忽略: except in ui/integrated_text_panel_content.py", exc_info=True)
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
            btn.setProperty("segmentButton", True)
            btn.setFixedHeight(PropertyPanelA2.CONTROL_HEIGHT)
            btn.setMinimumWidth(PropertyPanelA2.FONT_BUTTON_MIN_WIDTH)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        self._sync_panel_summaries()

    def _on_font_edit_finished(self):
        """输入框完成编辑后再提交字体，避免输入过程中频繁切换。"""
        if not self.font_combo.lineEdit():
            return
        font_name = self.font_combo.lineEdit().text().strip()
        if font_name:
            self._apply_font_selection(font_name)

    def load_fonts(self):
        """加载字体列表"""
        fonts = []
        chinese_fonts = []
        other_fonts = []
        try:
            # 创建临时TextLayer实例来获取字体列表
            from app.models.text_layer import TextLayer
            temp_layer = TextLayer()
            fonts = list(temp_layer.get_system_fonts() or [])
            self._font_cn_names = dict(temp_layer.get_font_cn_names() or {})
            categorized = temp_layer.get_categorized_fonts() or {}

            # 中文字体优先；补齐 monospace / decorative / other 三档，避免漏字体
            chinese_fonts = list(categorized.get('chinese', []) or [])
            other_fonts = []
            seen_cats = set()
            for cat in ('english', 'monospace', 'decorative', 'other'):
                for f in categorized.get(cat, []) or []:
                    k = str(f or '').strip().casefold()
                    if k and k not in seen_cats:
                        seen_cats.add(k)
                        other_fonts.append(f)
        except Exception as e:
            logger.debug("加载字体列表失败（TextLayer 路径），尝试 Qt 兜底：%s", e, exc_info=True)

        # 兜底：如果上面拿不到任何字体（TextLayer 失败 / 扫描无结果），用 Qt 的系统字体库做最后兜底
        if not fonts:
            try:
                from PySide6.QtGui import QGuiApplication, QFontDatabase
                if QGuiApplication.instance() is not None:
                    fonts = list(dict.fromkeys(QFontDatabase.families()))  # 保序去重
                    chinese_fonts = []
                    other_fonts = list(fonts)
                    self._font_cn_names = self._font_cn_names or {}
            except Exception as e2:
                logger.debug("Qt 字体兜底加载失败：%s", e2, exc_info=True)

        # 极端失败：仍为空 -> 保留最少 5 个常用字体，不至于字体下拉空白
        if not fonts:
            fonts = ["Microsoft YaHei", "Arial", "Times New Roman", "SimSun", "SimHei"]
            chinese_fonts = [f for f in ["Microsoft YaHei", "SimSun", "SimHei"] if f in fonts]
            other_fonts = [f for f in fonts if f not in chinese_fonts]

        self.font_combo.clear()
        self._all_fonts = list(fonts)

        # 先添加中文字体（若分类未生成则回退为一次性全部加在中文字体区）
        if not chinese_fonts and not other_fonts:
            for f in fonts:
                self.font_combo.addItem(self._font_display_name(f), f)
        else:
            for font in chinese_fonts:
                self.font_combo.addItem(self._font_display_name(font), font)
            if chinese_fonts and other_fonts:
                self.font_combo.insertSeparator(len(chinese_fonts))
            for font in other_fonts:
                # 避免重复：中/英分类区字体可能与 chinese_fonts 有交集（分类系统按 family 拆分时偶尔重合）
                if font in chinese_fonts:
                    continue
                self.font_combo.addItem(self._font_display_name(font), font)

        # 设置默认字体
        try:
            default_fonts = ["Microsoft YaHei", "SimSun", "SimHei"]
            for font in default_fonts:
                if font in fonts:
                    self._set_font_combo_text(font)
                    break
        except Exception:
            logger.debug("设置字体下拉默认值失败", exc_info=True)

        display_entries = sorted(set(self._all_fonts + [self._font_display_name(f) for f in self._all_fonts]))
        try:
            self.font_model.setStringList(display_entries)
        except Exception:
            logger.debug("更新字体自动完成模型失败", exc_info=True)
        try:
            self._refresh_recent_font_buttons()
        except Exception:
            pass
        try:
            self._sync_panel_summaries()
        except Exception:
            pass

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
