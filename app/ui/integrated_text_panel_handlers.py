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
from PySide6.QtCore import Qt, Signal, QSize, QStringListModel, QRectF
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QIcon

import sys
import os
import json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.text_layer import TextLayer, TextAlign, FontStyle
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.property_panel_a2 import PropertyPanelA2


from app.ui.text_panel_widgets import (
    A2Switch, ToggleButton, AlignButtonGroup, ColorIndicator
)

class IntegratedTextPanelHandlers(object):
    """Mixin for integrated_text_panel_handlers (split from IntegratedTextPanel)."""

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
            buttons = [
                self.apply_text_btn, self.prev_text_btn, self.next_text_btn,
                self.random_text_btn, self.range_color_btn, self.clear_range_color_btn
            ]
            if hasattr(self, 'full_edit_text_btn'):
                buttons.append(self.full_edit_text_btn)
            for btn in buttons:
                btn.setEnabled(False)
            self._sync_panel_summaries()
            return

        self.setEnabled(True)
        self.create_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        buttons = [
            self.apply_text_btn, self.prev_text_btn, self.next_text_btn,
            self.random_text_btn, self.range_color_btn, self.clear_range_color_btn
        ]
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
                self._sync_position_summary()

        finally:
            self._sync_appearance_visibility()
            self._sync_panel_summaries()
            self._block_panel_controls(False)
            self._sync_range_color_actions()

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
        self._sync_range_color_actions()
        self._sync_panel_summaries()

    def _selected_inline_text_range(self):
        if not self.text_layer or not hasattr(self, "inline_text_edit"):
            return None

        cursor = self.inline_text_edit.textCursor()
        if not cursor.hasSelection():
            return None

        current_text = getattr(self.text_layer, "current_text", "") or ""
        if not current_text:
            return None

        selection_start = min(cursor.position(), cursor.anchor())
        selection_end = max(cursor.position(), cursor.anchor())
        editor_text = self.inline_text_edit.toPlainText()

        if editor_text == current_text:
            if selection_start < selection_end <= len(current_text):
                return selection_start, selection_end
            return None

        selected_text = cursor.selectedText().replace("\u2029", "\n")
        if not selected_text:
            return None

        mapped_start = current_text.find(selected_text)
        if mapped_start < 0:
            return None
        return mapped_start, mapped_start + len(selected_text)

    def _sync_range_color_actions(self):
        if not hasattr(self, "range_color_btn") or not hasattr(self, "clear_range_color_btn"):
            return
        enabled = self._selected_inline_text_range() is not None
        self.range_color_btn.setEnabled(enabled)
        self.clear_range_color_btn.setEnabled(enabled)

    def _initial_selected_range_color(self, start):
        if not self.text_layer or not hasattr(self.text_layer, "get_text_color_ranges"):
            return getattr(self.text_layer, "text_color", (0, 0, 0, 255))
        for item in self.text_layer.get_text_color_ranges():
            if item["start"] <= start < item["end"]:
                return tuple(item["color"])
        return getattr(self.text_layer, "text_color", (0, 0, 0, 255))

    def on_apply_range_text_color(self):
        selected_range = self._selected_inline_text_range()
        if not selected_range or not self.text_layer:
            return

        from app.ui.color_picker_dialog_a2 import get_color_a2

        start, end = selected_range
        initial = self._initial_selected_range_color(start)
        color = get_color_a2(QColor(*initial), self, "选择选区文字颜色")
        if color.isValid() and hasattr(self.text_layer, "set_text_color_range"):
            changed = self.text_layer.set_text_color_range(
                start,
                end,
                (color.red(), color.green(), color.blue(), color.alpha())
            )
            if changed:
                ranges = self.text_layer.get_text_color_ranges()
                self.property_changed.emit("text_color_ranges", ranges)
                self.update_preview()
        self._sync_range_color_actions()

    def on_clear_range_text_color(self):
        selected_range = self._selected_inline_text_range()
        if not selected_range or not self.text_layer:
            return

        start, end = selected_range
        if hasattr(self.text_layer, "clear_text_color_range"):
            changed = self.text_layer.clear_text_color_range(start, end)
            if changed:
                ranges = self.text_layer.get_text_color_ranges()
                self.property_changed.emit("text_color_ranges", ranges)
                self.update_preview()
        self._sync_range_color_actions()

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
        from app.ui.font_picker_dialog_a2 import FontPickerDialogA2
        initial_font = self.text_layer.font_family if self.text_layer else self.font_combo.currentText()
        preview_text = ""
        if self.text_layer:
            preview_text = (getattr(self.text_layer, 'current_text', '') or '').strip()
        dlg = FontPickerDialogA2(self, initial_font=initial_font, preview_text=preview_text)
        if dlg.exec():
            name = dlg.selected_font() or self.font_combo.currentText()
            if name:
                self._apply_font_selection(name)

    def on_font_size_changed(self, size):
        if self.text_layer:
            self.text_layer.font_size = size
            self.property_changed.emit("font_size", size)
        self._sync_panel_summaries()

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
        self._sync_panel_summaries()

    def on_position_changed(self, *args):
        if self.text_layer and hasattr(self, 'x_spin') and hasattr(self, 'y_spin'):
            self.text_layer.x = int(self.x_spin.value())
            self.text_layer.y = int(self.y_spin.value())
            self._sync_position_summary()
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
            self._sync_position_summary()
            self._sync_panel_summaries()
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
            if hasattr(self, "stroke_color_button"):
                self.stroke_color_button.setEnabled(enabled)

            # 如果启用但描边宽度为0（不应该发生，因为范围从1开始），设置默认值
            if enabled and self.text_layer.stroke_width == 0:
                self.text_layer.stroke_width = 2
                self.stroke_width_spin.setValue(2)

            self.property_changed.emit("stroke_enabled", enabled)
        self._sync_panel_summaries()

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
        self._sync_panel_summaries()

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
        self._sync_panel_summaries()

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
            self._sync_appearance_visibility(background_mode="solid" if enabled else "none")
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
            self._sync_appearance_visibility(text_fill_mode="gradient" if enabled else "solid")
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
