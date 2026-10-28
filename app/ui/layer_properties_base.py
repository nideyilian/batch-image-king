from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit, QFormLayout,
                               QFileDialog, QGroupBox, QCheckBox, QComboBox,
                               QSlider, QMessageBox, QRadioButton, QButtonGroup,
                               QScrollArea, QFrame, QSizePolicy,
                               QMenu, QMainWindow, QDockWidget, QApplication, QTextEdit,
                               QProgressBar)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSettings, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QColor
import os
import time
from PIL import Image

try:
    from app.models.document_blend import BlendMode
    HAS_BLEND_MODE = True
except ImportError:
    HAS_BLEND_MODE = False

from app.ui.design_spec import Space as _Space
from app.ui.layer_transform_widget import LayerTransformWidget
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.color_picker_dialog_a2 import get_color_a2
from app.ui.shaped_layer_panel import ShapePreviewWidget, ShapeType as PreviewShapeType
from app.ui.dark_theme import CursorDarkTheme
from app.ui.design_tokens import Tokens
from app.ui.property_widgets import (
    PropertySection,
    PropertySwitch,
    blank_field_label,
    field_label,
    property_form,
    switch_row,
)
from app.utils.layer_tree import is_layer_group
from app.services.ai_asset_service import (
    AIAssetRequest,
    AIAssetResult,
    AIAssetService,
    localize_ai_error,
)
from app.services.ai_provider_config import AIProviderStore


class LayerPropertiesBase(object):
    """Mixin for layer_properties_base (split from LayerPropertiesPanel)."""

    def _layer_panel_stylesheet(self):
        """图层属性面板局部样式——与普通文字图层面板共用同一套 Tokens 控件样式。"""
        base = Tokens.control_qss("#layerPropertiesContent")
        extra = f"""
            QTabWidget#layerPropertyTabs {{
                background-color: {Tokens.BG_PRIMARY};
                border: none;
            }}
            QTabWidget#layerPropertyTabs::pane {{
                background-color: {Tokens.BG_PRIMARY};
                border: none;
                border-top: {Tokens.SIDEBAR_BORDER_WIDTH}px solid {Tokens.BORDER_SUBTLE};
            }}
            QTabWidget#layerPropertyTabs QTabBar::tab {{
                min-height: {Tokens.SIDEBAR_TAB_HEIGHT}px;
                max-height: {Tokens.SIDEBAR_TAB_HEIGHT}px;
                margin: 0;
                padding: 0 16px;
                background-color: {Tokens.BG_SECONDARY};
                color: {Tokens.TEXT_MUTED};
                border: none;
                border-bottom: 2px solid transparent;
                border-radius: {Tokens.SIDEBAR_NAV_RADIUS}px;
                font-size: {Tokens.SIDEBAR_BODY_FONT_SIZE}px;
                font-weight: {Tokens.FONT_WEIGHT_MEDIUM};
            }}
            QTabWidget#layerPropertyTabs QTabBar::tab:hover {{
                color: {Tokens.TEXT_PRIMARY};
                background-color: {Tokens.BG_HOVER};
            }}
            QTabWidget#layerPropertyTabs QTabBar::tab:selected {{
                color: {Tokens.TEXT_PRIMARY};
                background-color: {Tokens.BG_PRIMARY};
                border-bottom-color: {Tokens.ACCENT};
                font-weight: {Tokens.FONT_WEIGHT_BOLD};
            }}
            #layerPropertiesContent QWidget#layerPropertiesContent {{
                background-color: {Tokens.BG_PRIMARY};
            }}
            #layerPropertiesContent QFrame[role="propertySection"] {{
                background: transparent;
                border: none;
                border-radius: {Tokens.SIDEBAR_SECTION_RADIUS}px;
            }}
            #layerPropertiesContent QFrame[role="propertySectionHeader"] {{
                background: transparent;
                border: none;
                border-bottom: {Tokens.SIDEBAR_BORDER_WIDTH}px solid {Tokens.BORDER_SOFT};
                border-radius: {Tokens.SIDEBAR_SECTION_RADIUS}px;
            }}
            #layerPropertiesContent QFrame[role="propertySectionBody"] {{
                background: transparent;
                border: none;
                border-radius: {Tokens.SIDEBAR_SECTION_RADIUS}px;
            }}
            #layerPropertiesContent QLabel[role="propertySectionTitle"] {{
                color: {Tokens.TEXT_PRIMARY};
                font-size: {Tokens.SIDEBAR_TITLE_FONT_SIZE}px;
                font-weight: {Tokens.SIDEBAR_TITLE_FONT_WEIGHT};
                background: transparent;
                padding: 0;
            }}
            /* ── 字号层级（2026-10-28 统一）────────────────────────────
               修之前实测这个面板里同时存在 12 / 13 / 14 / 15 四个字号：
                 QLabel(标签)  12px      ← 比它右侧的输入框还小
                 QLineEdit     13px
                 QSpinBox      13px
                 QPushButton   12px      ← 分段按钮比正文还小
                 QLabel(区块)  14px
                 QLabel(启用描边) 15px   ← 全panel最大，因为它是个裸 QLabel
               结果就是"标签比内容小、按钮比标签还小、某一项突然巨大"，
               整片看起来像不同人做的。

               现在收敛成 3 级（对齐 tokens_v2.Typography 的档位）：
                 区块标题  14px  semibold   —— 基本属性 / 图像源 / 高级设置
                 字段标签  12px  medium     —— 名称: / 位置: / 混合模式:
                 输入内容  13px  regular    —— 输入框 / 下拉 / 数字框 / 按钮
               标签比内容小一档是刻意的：它是"说明"，不该抢内容的视觉重量。 */
            #layerPropertiesContent QLabel {{
                font-size: {Tokens.SIDEBAR_BODY_FONT_SIZE}px;   /* 13 */
                min-height: {Tokens.SIDEBAR_BODY_LINE_HEIGHT}px;
            }}
            #layerPropertiesContent QLabel[role="fieldLabel"],
            #layerPropertiesContent QLabel#fieldLabel {{
                font-size: 12px;
                font-weight: {Tokens.FONT_WEIGHT_MEDIUM};
                color: {Tokens.TEXT_SECONDARY};
                min-height: 0;
            }}
            /* 输入类控件统一 13px —— 显式写，不靠继承 */
            #layerPropertiesContent QLineEdit,
            #layerPropertiesContent QSpinBox,
            #layerPropertiesContent QDoubleSpinBox,
            #layerPropertiesContent QComboBox {{
                font-size: {Tokens.SIDEBAR_BODY_FONT_SIZE}px;
            }}
            /* 分段按钮 / 普通按钮统一 13px（原来 12px，比标签还小） */
            #layerPropertiesContent QPushButton {{
                font-size: {Tokens.SIDEBAR_BODY_FONT_SIZE}px;
            }}
            #layerPropertiesContent QProgressBar {{
                min-height: {Tokens.CONTROL_HEIGHT}px;
                max-height: {Tokens.CONTROL_HEIGHT}px;
                color: {Tokens.TEXT_SECONDARY};
                background-color: {Tokens.BG_CONTROL_ALT};
                border: 1px solid {Tokens.BORDER_CONTROL};
                border-radius: {Tokens.CONTROL_RADIUS}px;
                text-align: center;
                font-size: {Tokens.FONT_SIZE_SMALL}px;
            }}
            #layerPropertiesContent QProgressBar::chunk {{
                background-color: {Tokens.ACCENT};
                border-radius: {max(Tokens.CONTROL_RADIUS - 1, 0)}px;
            }}
            #layerPropertiesContent QLineEdit::up-button,
            #layerPropertiesContent QDoubleSpinBox::up-button,
            #layerPropertiesContent QSpinBox::down-button,
            #layerPropertiesContent QDoubleSpinBox::down-button {{
                width: 18px;
                border: none;
                background: transparent;
            }}
            #layerPropertiesContent QComboBox::drop-down {{
                width: 18px;
                border: none;
            }}
            /* 比例锁定按钮：只补「去掉左右内边距」，尺寸仍由代码的
               setFixedSize 供给（2026-10-28）。

               ⚠ 这里不能写 min/max 尺寸。原来写死 26px，26 不在
               design_spec.Scale 的 24/28/36 三档内，而且特异性高于
               uiSize 属性，导致它在同排按钮里永远大一圈。

               真正让 setFixedSize 失效的是全局 QSS 给 QPushButton 设的
               padding: 0 14px —— QSS 的 padding 会把 sizeHint 撑到
               14+16+14=44，setFixedSize(24) 压不住。
               所以这里只写 padding，不写尺寸。 */
            #layerPropertiesContent QPushButton#aspectLockButton {{
                padding: 0;
            }}
            #layerPropertiesContent QPushButton#colorSwatchButton {{
                min-height: {Tokens.CONTROL_HEIGHT}px;
                text-align: center;
                font-weight: 600;
            }}
            #layerPropertiesContent QPushButton[segmentButton="true"] {{
                min-height: {Tokens.CONTROL_HEIGHT}px;
                padding: 3px 4px;
            }}
            #layerPropertiesContent QPushButton[segmentButton="true"]:checked {{
                background-color: {Tokens.ACCENT};
                border-color: {Tokens.ACCENT_HOVER};
                color: {Tokens.TEXT_INVERTED};
                font-weight: 700;
            }}
            #layerPropertiesContent QLabel#propertySectionLabel {{
                color: {Tokens.TEXT_MUTED};
                font-weight: 700;
                padding-top: 2px;
            }}
            #layerPropertiesContent QFrame#propertyDivider {{
                background-color: {Tokens.BORDER_SOFT};
                min-height: 1px;
                max-height: 1px;
                border: none;
            }}
            #layerPropertiesContent QFrame#shapePreviewContainer {{
                background-color: {Tokens.BG_CONTROL_ALT};
                border: 1px solid {Tokens.BORDER_SOFT};
                border-radius: 6px;
            }}
        """
        return base + extra

    #: 属性面板标签列宽 —— 单一真源 = design_spec.Layout.LABEL_WIDTH(72)。
    #:
    #: ⚠ 2026-10-28 二次修：上一版写的是「下限 58 / 上限 84，让 QFormLayout 自己撑」。
    #: 实测照样乱，因为 **QFormLayout 的标签列宽是按「本表单里最长的那个标签」算的**：
    #: 全是两字标签的表单 → 列宽 58；含「裁剪方向:」的表单 → 列宽 84。
    #: 于是同一面板出现 70 / 84 / 96 三个右边缘（实测探针输出）。
    #: 「让布局自己适配」在栅格里等价于「没有栅格」。现在一律固定。
    LABEL_WIDTH = Tokens.LABEL_WIDTH

    def _label(self, text, width=None, inline=False):
        """字段标签 —— 代理到 property_widgets.field_label（唯一实现）。

        不要在面板里再写一份标签工厂：本次整治的根因就是「每个文件自己造标签」，
        造出来的宽度/对齐各不相同，栅格当场失效。
        """
        return field_label(text, width=width, inline=inline)

    def _blank_label(self):
        """占位标签列（整行控件用）。代理到 property_widgets.blank_field_label。"""
        return blank_field_label()

    def _divider(self):
        divider = QFrame()
        divider.setObjectName("propertyDivider")
        divider.setFrameShape(QFrame.HLine)
        return divider

    def _section_label(self, text):
        label = QLabel(text)
        label.setObjectName("propertySectionLabel")
        return label

    def _make_segment_button(self, text, checked=False):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setProperty("segmentButton", True)
        button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        return button

    def _form(self, parent=None):
        """统一表单布局 —— 代理到 property_widgets.property_form（唯一实现）。

        ⚠ 属性面板里有 10+ 个 QFormLayout。2026-10-28 实测它们原来全部没设
        行距列距（吃平台默认 5/3），而且构造完成后还会被 `_apply_compact_layouts`
        整棵树重写一遍 —— 两个写入方互相覆盖。
        现在规格只有一处：property_widgets.property_form()。
        """
        return property_form(parent)

    def _make_control_group(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_Space.XS)
        return widget, layout

    def _is_export_ui_frozen(self):
        """导出期间是否冻结属性面板更新（由导出设置控制）"""
        doc = getattr(self, 'document', None)
        if not doc or not bool(getattr(doc, '_is_batch_export_running', False)):
            return False
        try:
            settings = getattr(doc, 'export_settings', {}) or {}
            return bool(settings.get('freeze_preview_during_export', False))
        except Exception:
            return False

    def _emit_document_change(self, throttled=False, include_layer_changed=False, fields=None, reason=""):
        """统一发射文档变更信号，支持高频交互节流"""
        if not self.document:
            return

        # 由属性面板本地改动触发时，短时间抑制回流到 update_panel 的全量刷新
        self._suppress_panel_refresh_until = time.time() + 0.35

        layer_index = getattr(self.document, "selected_layer_index", -1)
        normalized_fields = list(fields) if fields else []
        if hasattr(self.document, "set_change_context"):
            self.document.set_change_context(
                source="layer_properties_panel",
                layer_index=layer_index,
                fields=normalized_fields,
                reason=reason
            )

        if not throttled:
            self.document.document_changed.emit()
            if include_layer_changed:
                self.document.layer_changed.emit()
            return

        if include_layer_changed:
            self._deferred_layer_changed = True
        self._deferred_context_fields = normalized_fields
        self._deferred_context_reason = reason or ""

        # 高频参数调整采用短延时合并，避免连续重绘
        if self._ui_change_timer.isActive():
            self._ui_change_timer.stop()
        self._ui_change_timer.start(20)

    def _flush_deferred_document_change(self):
        """执行节流后的文档变更发射"""
        if not self.document:
            return

        if hasattr(self.document, "set_change_context"):
            self.document.set_change_context(
                source="layer_properties_panel",
                layer_index=getattr(self.document, "selected_layer_index", -1),
                fields=self._deferred_context_fields,
                reason=self._deferred_context_reason
            )

        self.document.document_changed.emit()
        if self._deferred_layer_changed:
            self.document.layer_changed.emit()
            self._deferred_layer_changed = False
        self._deferred_context_fields = []
        self._deferred_context_reason = ""

    def _save_state_deferred(self, action_name, delay_ms=220):
        """统一延迟保存历史，避免滑块拖动期间产生大量历史快照"""
        if not self.document:
            return

        self._deferred_action_name = action_name
        if self._history_timer.isActive():
            self._history_timer.stop()
        self._history_timer.start(delay_ms)

    def _flush_deferred_history_save(self):
        """写入最后一次延迟的历史记录"""
        if not self.document or not self._deferred_action_name:
            return

        action_name = self._deferred_action_name
        self._deferred_action_name = None
        self.document.save_state(action_name)

    def _on_layers_selection_changed(self, _indices):
        """多选变化时刷新属性面板类型与混合/批量编辑状态。"""
        if self.document and getattr(self.document, 'selected_layer_index', -1) >= 0:
            self.layer_selected(self.document.selected_layer_index)
        else:
            self.update_panel()

    def _selected_editable_layers(self, allow_locked=False):
        """获取属性面板当前应作用的选中图层。"""
        if not self.document or not hasattr(self.document, 'layers'):
            return []
        indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
        if not indices and getattr(self.document, 'selected_layer_index', -1) >= 0:
            indices = [self.document.selected_layer_index]
        layers = []
        for idx in indices:
            if 0 <= idx < len(self.document.layers):
                layer = self.document.layers[idx]
                if is_layer_group(layer):
                    continue
                if allow_locked or not getattr(layer, 'locked', False):
                    layers.append(layer)
        return layers

    def _is_multi_layer_edit(self):
        return len(self._selected_editable_layers(allow_locked=True)) > 1

    def _selected_layers_all_match(self, layer_type):
        layers = self._selected_editable_layers(allow_locked=True)
        return bool(layers) and all(isinstance(layer, layer_type) for layer in layers)

    def _selected_layers_have_mixed_value(self, attr):
        layers = self._selected_editable_layers(allow_locked=True)
        if len(layers) < 2:
            return False
        marker = object()
        first = getattr(layers[0], attr, marker)
        return any(getattr(layer, attr, marker) != first for layer in layers[1:])

    def _apply_to_selected_layers(self, attrs, action_name, fields=None, allow_locked=False, clear_cache=False):
        """把属性字典批量写入当前选区。"""
        layers = self._selected_editable_layers(allow_locked=allow_locked)
        if not layers:
            return 0
        changed_layers = []
        for layer in layers:
            changed = False
            for attr, value in attrs.items():
                if hasattr(layer, attr) and getattr(layer, attr) != value:
                    setattr(layer, attr, value)
                    changed = True
            if changed:
                if clear_cache:
                    if hasattr(layer, 'cached_image'):
                        layer.cached_image = None
                    if hasattr(layer, '_cached_image'):
                        layer._cached_image = None
                changed_layers.append(layer)
        if not changed_layers:
            return 0
        self._emit_document_change(
            throttled=True,
            include_layer_changed=True,
            fields=fields or list(attrs.keys()),
            reason=action_name
        )
        self._save_state_deferred(action_name)
        return len(changed_layers)

    def _block_all_signals(self, block):
        """阻断或恢复所有控件的信号"""
        # 阻断主要控件的信号以避免在更新界面时触发事件
        self.name_edit.blockSignals(block)
        self.x_spin.blockSignals(block)
        self.y_spin.blockSignals(block)
        self.width_spin.blockSignals(block)
        self.height_spin.blockSignals(block)
        self.use_original_size_checkbox.blockSignals(block)
        self.fit_mode_combo.blockSignals(block)
        self.crop_direction_combo.blockSignals(block)
        self.opacity_slider.blockSignals(block)
        self.visible_checkbox.blockSignals(block)
        self.locked_checkbox.blockSignals(block)
        self.folder_radio.blockSignals(block)
        self.file_radio.blockSignals(block)
        self.clone_enabled_checkbox.blockSignals(block)
        self.clone_rows_spin.blockSignals(block)
        self.clone_columns_spin.blockSignals(block)
        self.row_spacing_spin.blockSignals(block)
        self.column_spacing_spin.blockSignals(block)
        if hasattr(self, 'clone_mirror_combo'):
            self.clone_mirror_combo.blockSignals(block)
        self.source_path_edit.blockSignals(block)  # 阻断路径输入框信号

        # 混合模式下拉框
        if hasattr(self, 'blend_mode_combo'):
            self.blend_mode_combo.blockSignals(block)

        # 形状控件
        if hasattr(self, 'shape_type_combo'):
            self.shape_type_combo.blockSignals(block)
        if hasattr(self, 'shape_type_buttons'):
            for button in self.shape_type_buttons:
                button.blockSignals(block)
        if hasattr(self, 'trapezoid_top_spin'):
            self.trapezoid_top_spin.blockSignals(block)
        if hasattr(self, 'trapezoid_bottom_spin'):
            self.trapezoid_bottom_spin.blockSignals(block)
        if hasattr(self, 'trapezoid_side_combo'):
            self.trapezoid_side_combo.blockSignals(block)
        if hasattr(self, 'polygon_rotation_spin'):
            self.polygon_rotation_spin.blockSignals(block)
        if hasattr(self, 'polygon_radius_spin'):
            self.polygon_radius_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_radius_spin'):
            self.vector_corner_radius_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_tl_spin'):
            self.vector_corner_tl_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_tr_spin'):
            self.vector_corner_tr_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_br_spin'):
            self.vector_corner_br_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_bl_spin'):
            self.vector_corner_bl_spin.blockSignals(block)
        if hasattr(self, 'stroke_join_combo'):
            self.stroke_join_combo.blockSignals(block)
        if hasattr(self, 'stroke_cap_combo'):
            self.stroke_cap_combo.blockSignals(block)
        if hasattr(self, 'stroke_dash_length_spin'):
            self.stroke_dash_length_spin.blockSignals(block)
        if hasattr(self, 'stroke_dash_gap_spin'):
            self.stroke_dash_gap_spin.blockSignals(block)
        if hasattr(self, 'stroke_enabled_checkbox'):
            self.stroke_enabled_checkbox.blockSignals(block)
        if hasattr(self, 'stroke_width_spin'):
            self.stroke_width_spin.blockSignals(block)
        if hasattr(self, 'stroke_type_combo'):
            self.stroke_type_combo.blockSignals(block)
        if hasattr(self, 'fill_solid_enabled_checkbox'):
            self.fill_solid_enabled_checkbox.blockSignals(block)
        if hasattr(self, 'fill_gradient_enabled_checkbox'):
            self.fill_gradient_enabled_checkbox.blockSignals(block)
        if hasattr(self, 'fill_mode_buttons'):
            for button in self.fill_mode_buttons:
                button.blockSignals(block)
        if hasattr(self, 'fill_gradient_angle_spin'):
            self.fill_gradient_angle_spin.blockSignals(block)
        if hasattr(self, 'fill_gradient_opacity_spin'):
            self.fill_gradient_opacity_spin.blockSignals(block)

        # 变换控件
        if hasattr(self, 'transform_widget'):
            # 阻断变换控件内部的信号
            self.transform_widget.blockSignals(block)
