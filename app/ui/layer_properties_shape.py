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
from app.utils.layer_tree import is_layer_group
from app.services.ai_asset_service import (
    AIAssetRequest,
    AIAssetResult,
    AIAssetService,
    localize_ai_error,
)
from app.services.ai_provider_config import AIProviderStore


class LayerPropertiesShape(object):
    """Mixin for layer_properties_shape (split from LayerPropertiesPanel)."""

    def on_shaped_layer_changed(self):
        """异形图层属性改变处理"""
        if self.current_layer and hasattr(self.current_layer, 'cached_image'):
            self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()

    def on_shaped_layer_param_changed(self):
        """异形图层参数变更处理 - 同步基本属性面板"""
        if self.current_layer and self.document:
            # 同步基本属性面板中的形状参数显示
            self.sync_ui_with_layer()
            # 触发文档变更
            self.document.document_changed.emit()

    def _sync_shape_segment_buttons(self, shape_type_text):
        """同步形状分段按钮状态，保留隐藏下拉框兼容旧逻辑。"""
        if not hasattr(self, "shape_type_buttons"):
            return
        text_map = {
            "矩形": "矩形",
            "直角梯形": "梯形",
            "圆形": "圆形",
            "正五边形": "五边",
            "正六边形": "六边",
        }
        visible_text = text_map.get(shape_type_text, "矩形")
        for button in self.shape_type_buttons:
            button.blockSignals(True)
            try:
                button.setChecked(button.text() == visible_text)
            finally:
                button.blockSignals(False)

    def _current_fill_mode(self):
        if getattr(self, "fill_gradient_enabled_checkbox", None) and self.fill_gradient_enabled_checkbox.isChecked():
            return "gradient"
        if getattr(self, "fill_solid_enabled_checkbox", None) and self.fill_solid_enabled_checkbox.isChecked():
            return "solid"
        return "none"

    def _set_fill_mode(self, mode, update_layer=True):
        """切换填充模式，并保持旧复选框与新分段按钮同步。"""
        if mode not in {"none", "solid", "gradient"}:
            mode = "none"

        solid_enabled = mode == "solid"
        gradient_enabled = mode == "gradient"

        for button in getattr(self, "fill_mode_buttons", []):
            button.blockSignals(True)
            try:
                button.setChecked(button.property("fillMode") == mode)
            finally:
                button.blockSignals(False)

        self._block_all_signals(True)
        try:
            if hasattr(self, "fill_solid_enabled_checkbox"):
                self.fill_solid_enabled_checkbox.setChecked(solid_enabled)
            if hasattr(self, "fill_gradient_enabled_checkbox"):
                self.fill_gradient_enabled_checkbox.setChecked(gradient_enabled)
        finally:
            self._block_all_signals(False)

        if update_layer and self.current_layer and not self.current_layer.locked:
            self.current_layer.color_overlay_enabled = solid_enabled
            self.current_layer.gradient_overlay_enabled = gradient_enabled
            self._emit_document_change(throttled=True, fields=["fill_mode"], reason="fill_mode")
            self._save_state_deferred("切换填充模式")

        self._sync_appearance_visibility()

    def _sync_appearance_visibility(self):
        """根据填充/描边开关收起无关控件。"""
        mode = self._current_fill_mode()
        for button in getattr(self, "fill_mode_buttons", []):
            button.blockSignals(True)
            try:
                button.setChecked(button.property("fillMode") == mode)
            finally:
                button.blockSignals(False)

        if hasattr(self, "fill_solid_controls_widget"):
            self.fill_solid_controls_widget.setVisible(mode == "solid")
        if hasattr(self, "fill_gradient_controls_widget"):
            self.fill_gradient_controls_widget.setVisible(mode == "gradient")

        stroke_enabled = bool(
            hasattr(self, "stroke_enabled_checkbox") and self.stroke_enabled_checkbox.isChecked()
        )
        if hasattr(self, "stroke_controls_widget"):
            self.stroke_controls_widget.setVisible(stroke_enabled)
        if hasattr(self, "stroke_advanced_group"):
            self.stroke_advanced_group.setVisible(stroke_enabled)

    def update_shape_type(self, shape_type_text):
        """更新形状类型"""
        if not self.current_layer or self.current_layer.locked:
            if hasattr(self, "shape_type_combo"):
                self.shape_type_combo.blockSignals(True)
                try:
                    self.shape_type_combo.setCurrentText(shape_type_text)
                finally:
                    self.shape_type_combo.blockSignals(False)
            self._sync_shape_segment_buttons(shape_type_text)
            return

        safe_print(f"更新形状类型: {shape_type_text}")

        # 导入ShapeType枚举
        from app.models.layer_properties import ShapeType

        # 保存当前状态
        self.document.save_state("更改形状类型前")

        # 转换形状类型文本为枚举值
        shape_type_map = {
            "矩形": ShapeType.RECTANGLE,
            "直角梯形": ShapeType.RIGHT_TRAPEZOID,
            "圆形": ShapeType.CIRCLE,
            "正五边形": ShapeType.PENTAGON,
            "正六边形": ShapeType.HEXAGON
        }

        shape_type_value = shape_type_map.get(shape_type_text, ShapeType.RECTANGLE)

        # 更新图层形状类型
        self.current_layer.shape_type = shape_type_value
        if hasattr(self, "shape_type_combo"):
            self.shape_type_combo.blockSignals(True)
            try:
                self.shape_type_combo.setCurrentText(shape_type_text)
            finally:
                self.shape_type_combo.blockSignals(False)
        self._sync_shape_segment_buttons(shape_type_text)

        # 更新形状参数控件的可见性
        print(f"形状类型变更: {shape_type_value.value}")
        self.update_shape_params_visibility(shape_type_value.value)

        # 更新形状预览
        try:
            mapping = {
                "矩形": PreviewShapeType.RECTANGLE,
                "直角梯形": PreviewShapeType.RIGHT_TRAPEZOID,
                "圆形": PreviewShapeType.CIRCLE,
                "正五边形": PreviewShapeType.PENTAGON,
                "正六边形": PreviewShapeType.HEXAGON,
            }
            self.shape_preview.set_shape_type(mapping.get(shape_type_text, PreviewShapeType.RECTANGLE))
            # 多边形边数设置
            sides = 5 if shape_type_text == "正五边形" else (6 if shape_type_text == "正六边形" else 5)
            self.shape_preview.set_polygon_params(self.polygon_rotation_spin.value(), sides)
            self.shape_preview.update()
        except Exception:
            pass

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改形状类型")

    def update_trapezoid_params(self):
        """更新梯形参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新梯形参数")

        # 更新梯形参数
        self.current_layer.trapezoid_top_width = self.trapezoid_top_spin.value()
        self.current_layer.trapezoid_bottom_width = self.trapezoid_bottom_spin.value()

        # 转换斜边方向
        side_text = self.trapezoid_side_combo.currentText()
        side_value = "left" if side_text == "左侧" else "right"
        self.current_layer.trapezoid_slope_side = side_value

        # 同步形状预览
        try:
            self.shape_preview.set_trapezoid_params(
                self.trapezoid_top_spin.value(),
                self.trapezoid_bottom_spin.value(),
                "left" if self.trapezoid_side_combo.currentText() == "左侧" else "right"
            )
            self.shape_preview.update()
        except Exception:
            pass

        # 高频参数调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["trapezoid_params"], reason="trapezoid_params")
        self._save_state_deferred("更改梯形参数")

    def update_polygon_params(self):
        """更新多边形参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新多边形参数")

        # 更新多边形参数
        self.current_layer.polygon_rotation = self.polygon_rotation_spin.value()
        self.current_layer.polygon_corner_radius = self.polygon_radius_spin.value()

        # 同步形状预览
        try:
            sides = 5 if self.shape_type_combo.currentText() == "正五边形" else (6 if self.shape_type_combo.currentText() == "正六边形" else 5)
            self.shape_preview.set_polygon_params(self.polygon_rotation_spin.value(), sides)
            self.shape_preview.update()
        except Exception:
            pass

        # 高频参数调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["polygon_params"], reason="polygon_params")
        self._save_state_deferred("更改多边形参数")

    def update_vector_corner_radius_all(self, value):
        """统一设置四角矢量圆角"""
        if not self.current_layer or self.current_layer.locked:
            return
        radius = int(value)
        self.current_layer.vector_corner_radius_tl = radius
        self.current_layer.vector_corner_radius_tr = radius
        self.current_layer.vector_corner_radius_br = radius
        self.current_layer.vector_corner_radius_bl = radius
        self.current_layer.corner_radius = radius
        self._block_all_signals(True)
        try:
            self.vector_corner_tl_spin.setValue(radius)
            self.vector_corner_tr_spin.setValue(radius)
            self.vector_corner_br_spin.setValue(radius)
            self.vector_corner_bl_spin.setValue(radius)
        finally:
            self._block_all_signals(False)
        self._emit_document_change(throttled=True, fields=["vector_corner_radius"], reason="vector_corner_radius")
        self._save_state_deferred("调整矢量圆角")

    def convert_rect_to_path_nodes(self):
        """将当前矩形转换为可编辑路径节点"""
        if not self.current_layer or self.current_layer.locked:
            return
        if hasattr(self.current_layer, 'convert_rect_to_vector_path'):
            self.current_layer.convert_rect_to_vector_path()
            self._emit_document_change(throttled=False, fields=["vector_path"], reason="vector_path")
            self._save_state_deferred("矩形转路径")

    def update_vector_corner_radii_detail(self):
        """分别设置四角矢量圆角"""
        if not self.current_layer or self.current_layer.locked:
            return
        tl = int(self.vector_corner_tl_spin.value())
        tr = int(self.vector_corner_tr_spin.value())
        br = int(self.vector_corner_br_spin.value())
        bl = int(self.vector_corner_bl_spin.value())
        self.current_layer.vector_corner_radius_tl = tl
        self.current_layer.vector_corner_radius_tr = tr
        self.current_layer.vector_corner_radius_br = br
        self.current_layer.vector_corner_radius_bl = bl
        self.current_layer.corner_radius = max(tl, tr, br, bl)
        self._block_all_signals(True)
        try:
            self.vector_corner_radius_spin.setValue(max(tl, tr, br, bl))
        finally:
            self._block_all_signals(False)
        self._emit_document_change(throttled=True, fields=["vector_corner_radius_detail"], reason="vector_corner_radius_detail")
        self._save_state_deferred("调整四角圆角")

    def update_stroke_join(self, text):
        if not self.current_layer or self.current_layer.locked:
            return
        join_map = {"斜接": "miter", "圆角": "round", "斜切": "bevel"}
        self.current_layer.stroke_join = join_map.get(text, "miter")
        self._emit_document_change(throttled=True, fields=["stroke_join"], reason="stroke_join")
        self._save_state_deferred("调整描边连接")

    def update_stroke_cap(self, text):
        if not self.current_layer or self.current_layer.locked:
            return
        cap_map = {"平头": "butt", "圆头": "round", "方头": "square"}
        self.current_layer.stroke_cap = cap_map.get(text, "butt")
        self._emit_document_change(throttled=True, fields=["stroke_cap"], reason="stroke_cap")
        self._save_state_deferred("调整描边端点")

    def update_stroke_dash(self):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.stroke_dash_length = int(self.stroke_dash_length_spin.value())
        self.current_layer.stroke_dash_gap = int(self.stroke_dash_gap_spin.value())
        self._emit_document_change(throttled=True, fields=["stroke_dash"], reason="stroke_dash")
        self._save_state_deferred("调整描边虚线")

    def update_stroke_enabled(self, enabled):
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            self._apply_to_selected_layers(
                {"stroke_enabled": bool(enabled)},
                "批量切换描边",
                fields=["stroke_enabled"],
                allow_locked=False,
                clear_cache=True,
            )
            self._sync_appearance_visibility()
            return
        if self.current_layer.locked:
            return
        self.current_layer.stroke_enabled = bool(enabled)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=True, fields=["stroke_enabled"], reason="stroke_enabled")
        self._save_state_deferred("切换描边")

    def update_stroke_width(self, value):
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            self._apply_to_selected_layers(
                {"stroke_width": int(value)},
                "批量调整描边粗细",
                fields=["stroke_width"],
                allow_locked=False,
                clear_cache=True,
            )
            return
        if self.current_layer.locked:
            return
        self.current_layer.stroke_width = int(value)
        self._emit_document_change(throttled=True, fields=["stroke_width"], reason="stroke_width")
        self._save_state_deferred("调整描边粗细")

    def update_stroke_type(self, index):
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            self._apply_to_selected_layers(
                {"stroke_type": int(index)},
                "批量调整描边对齐",
                fields=["stroke_type"],
                allow_locked=False,
                clear_cache=True,
            )
            return
        if self.current_layer.locked:
            return
        self.current_layer.stroke_type = int(index)
        self._emit_document_change(throttled=True, fields=["stroke_type"], reason="stroke_type")
        self._save_state_deferred("调整描边对齐")

    def pick_stroke_color(self):
        if not self.current_layer or self.current_layer.locked:
            return
        current = tuple(getattr(self.current_layer, 'stroke_color', (0, 0, 0, 255)))
        color = get_color_a2(QColor(current[0], current[1], current[2], current[3]), self, "选择描边颜色")
        if not color.isValid():
            return
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        self.current_layer.stroke_color = rgba
        self.current_layer.stroke_enabled = True
        self._set_button_color(self.stroke_color_btn, rgba)
        self._block_all_signals(True)
        try:
            self.stroke_enabled_checkbox.setChecked(True)
        finally:
            self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=False, fields=["stroke_color"], reason="stroke_color")
        self._save_state_deferred("修改描边颜色")

    def update_fill_solid_enabled(self, enabled):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.color_overlay_enabled = bool(enabled)
        if enabled:
            self.current_layer.gradient_overlay_enabled = False
            self._block_all_signals(True)
            try:
                self.fill_gradient_enabled_checkbox.setChecked(False)
            finally:
                self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=True, fields=["fill_solid_enabled"], reason="fill_solid_enabled")
        self._save_state_deferred("切换纯色填充")

    def pick_fill_solid_color(self):
        if not self.current_layer or self.current_layer.locked:
            return
        current = tuple(getattr(self.current_layer, 'color_overlay_color', (255, 0, 0, 255)))
        color = get_color_a2(QColor(current[0], current[1], current[2], current[3]), self, "选择填充颜色")
        if not color.isValid():
            return
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        self.current_layer.color_overlay_color = rgba
        self.current_layer.color_overlay_enabled = True
        self.current_layer.gradient_overlay_enabled = False
        self._set_button_color(self.fill_solid_color_btn, rgba)
        self._block_all_signals(True)
        try:
            self.fill_solid_enabled_checkbox.setChecked(True)
            self.fill_gradient_enabled_checkbox.setChecked(False)
        finally:
            self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=False, fields=["fill_solid_color"], reason="fill_solid_color")
        self._save_state_deferred("修改填充颜色")

    def update_fill_gradient_enabled(self, enabled):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.gradient_overlay_enabled = bool(enabled)
        if enabled:
            self.current_layer.color_overlay_enabled = False
            self._block_all_signals(True)
            try:
                self.fill_solid_enabled_checkbox.setChecked(False)
            finally:
                self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=True, fields=["fill_gradient_enabled"], reason="fill_gradient_enabled")
        self._save_state_deferred("切换渐变填充")

    def pick_gradient_start_color(self):
        self._pick_gradient_color(0, self.fill_gradient_start_btn, "选择渐变起点色")

    def pick_gradient_end_color(self):
        self._pick_gradient_color(1, self.fill_gradient_end_btn, "选择渐变终点色")

    def _pick_gradient_color(self, idx, btn, title):
        if not self.current_layer or self.current_layer.locked:
            return
        colors = list(getattr(self.current_layer, 'gradient_overlay_colors', [(0, 0, 0, 255), (255, 255, 255, 255)]))
        if len(colors) < 2:
            colors = [(0, 0, 0, 255), (255, 255, 255, 255)]
        current = tuple(colors[idx])
        color = get_color_a2(QColor(current[0], current[1], current[2], current[3]), self, title)
        if not color.isValid():
            return
        colors[idx] = (color.red(), color.green(), color.blue(), color.alpha())
        self.current_layer.gradient_overlay_colors = colors
        self.current_layer.gradient_overlay_enabled = True
        self.current_layer.color_overlay_enabled = False
        self._set_button_color(btn, colors[idx])
        self._block_all_signals(True)
        try:
            self.fill_gradient_enabled_checkbox.setChecked(True)
            self.fill_solid_enabled_checkbox.setChecked(False)
        finally:
            self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=False, fields=["fill_gradient_colors"], reason="fill_gradient_colors")
        self._save_state_deferred("修改渐变颜色")

    def update_fill_gradient_angle(self, value):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.gradient_overlay_angle = float(value)
        self._emit_document_change(throttled=True, fields=["fill_gradient_angle"], reason="fill_gradient_angle")
        self._save_state_deferred("调整渐变角度")

    def update_fill_gradient_opacity(self, value):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.gradient_overlay_opacity = float(value) / 100.0
        self._emit_document_change(throttled=True, fields=["fill_gradient_opacity"], reason="fill_gradient_opacity")
        self._save_state_deferred("调整渐变不透明度")

    def _set_button_color(self, btn, rgba):
        if not btn:
            return
        r, g, b, a = [int(x) for x in rgba]
        text_color = "#111214" if (r * 0.299 + g * 0.587 + b * 0.114) > 170 else "#F4F4F5"
        label = btn.property("swatchLabel")
        if label is None:
            label = btn.text() or ""
        btn.setStyleSheet(
            f"background-color: rgba({r}, {g}, {b}, {a});"
            f"color: {text_color};"
            "border: 1px solid #34363A; border-radius: 5px;"
            "min-height: 27px; padding: 3px 8px; font-weight: 600;"
        )
        btn.setText(str(label))

    def update_shape_params_visibility(self, shape_type):
        """根据形状类型更新参数控件的可见性"""
        print(f"更新形状参数可见性: shape_type={shape_type}")
        print(f"布局行数: {self.shape_params_layout.rowCount()}")

        # 隐藏所有形状参数控件
        for i in range(self.shape_params_layout.rowCount()):
            item = self.shape_params_layout.itemAt(i, QFormLayout.LabelRole)
            if item:
                print(f"隐藏标签行 {i}: {item.widget()}")
                item.widget().hide()
            item = self.shape_params_layout.itemAt(i, QFormLayout.FieldRole)
            if item:
                print(f"隐藏字段行 {i}: {item.widget()}")
                item.widget().hide()

        # 根据形状类型显示相应的参数控件
        print(f"处理形状类型: {shape_type}")
        if shape_type == "right_trapezoid":
            # 显示梯形参数
            print("显示梯形参数")
            self._show_shape_param_rows([0, 1, 2])  # 上底宽度, 下底宽度, 斜边方向
        elif shape_type in ["pentagon", "hexagon"]:
            # 显示多边形参数
            print("显示多边形参数")
            self._show_shape_param_rows([3, 4])  # 旋转角度, 圆角半径
        elif shape_type == "circle":
            # 圆形不需要额外参数
            print("圆形无额外参数")
            pass
        elif shape_type == "rectangle":
            # 矩形不需要额外参数
            print("矩形无额外参数")
            pass
        else:
            # 未识别的形状类型，不显示额外参数
            print(f"未识别的形状类型: {shape_type}")
            pass

    def _show_shape_param_rows(self, row_indices):
        """显示指定的形状参数行"""
        print(f"显示形状参数行: {row_indices}")
        for row_index in row_indices:
            print(f"处理行 {row_index}")
            if row_index < self.shape_params_layout.rowCount():
                label_item = self.shape_params_layout.itemAt(row_index, QFormLayout.LabelRole)
                field_item = self.shape_params_layout.itemAt(row_index, QFormLayout.FieldRole)
                print(f"标签项: {label_item}, 字段项: {field_item}")
                if label_item and label_item.widget():
                    print(f"显示标签行 {row_index}")
                    label_item.widget().show()
                if field_item and field_item.widget():
                    print(f"显示字段行 {row_index}")
                    field_item.widget().show()
            else:
                print(f"行 {row_index} 超出范围，总行数: {self.shape_params_layout.rowCount()}")


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")
    def update_fill_enabled(self, enabled):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_enabled = enabled
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充启用")

    def update_fill_mode(self, index):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        text = self.fill_mode_combo.itemText(index)
        mode_map = {"常规网格": "grid", "错位排列": "staggered", "边框排列": "border"}
        mode = mode_map.get(text, "grid")
        self.current_layer.clone_fill_mode = mode
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充排列")

    def update_fill_spacing(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_spacing = int(value)
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充间距")

    def update_fill_angle(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_angle = float(value)
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充角度")
            # 同步元素填充
            self._ensure_clone_properties()
            self.fill_enabled_checkbox.setChecked(bool(getattr(self.current_layer, 'clone_fill_enabled', False)))
            mode = getattr(self.current_layer, 'clone_fill_mode', 'grid')
            # 正确设置下拉框索引：grid=0, staggered=1, border=2
            index_map = {'grid': 0, 'staggered': 1, 'border': 2}
            self.fill_mode_combo.setCurrentIndex(index_map.get(mode, 0))
            self.fill_spacing_spin.setValue(int(getattr(self.current_layer, 'clone_fill_spacing', 0)))
            self.fill_margin_spin.setValue(int(getattr(self.current_layer, 'clone_fill_margin', 0)))
            self.fill_angle_spin.setValue(float(getattr(self.current_layer, 'clone_fill_angle', 0.0)))
