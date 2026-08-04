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

from app.ui.layer_transform_widget import LayerTransformWidget
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.color_picker_dialog_a2 import get_color_a2
from app.ui.shaped_layer_panel import ShapePreviewWidget, ShapeType as PreviewShapeType
from app.ui.dark_theme import CursorDarkTheme
from app.ui.design_tokens import Tokens
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
            #layerPropertiesContent QWidget#layerPropertiesContent {{
                background-color: {Tokens.BG_PRIMARY};
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
            #layerPropertiesContent QPushButton#aspectLockButton {{
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 26px;
                padding: 0;
                font-size: 14px;
            }}
            #layerPropertiesContent QPushButton#colorSwatchButton {{
                min-height: {Tokens.CONTROL_HEIGHT}px;
                text-align: center;
                font-weight: 600;
            }}
            #layerPropertiesContent QPushButton[segmentButton="true"] {{
                min-height: {Tokens.CONTROL_HEIGHT}px;
                padding: 3px 4px;
                font-size: 12px;
            }}
            #layerPropertiesContent QPushButton[segmentButton="true"]:checked {{
                background-color: {Tokens.ACCENT};
                border-color: {Tokens.ACCENT_HOVER};
                color: {Tokens.TEXT_INVERTED};
                font-weight: 700;
            }}
            #layerPropertiesContent QLabel#propertySectionLabel {{
                color: {Tokens.TEXT_MUTED};
                font-size: {Tokens.FONT_SIZE_SMALL}px;
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

    def _label(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

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

    def _make_control_group(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
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

