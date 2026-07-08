from app.utils.print_utils import safe_print
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


class LayerPropertiesRefresh(object):
    """Mixin for layer_properties_refresh (split from LayerPropertiesPanel)."""

    def set_controls_enabled(self, enabled):
        """启用或禁用所有控件"""
        if enabled and self.current_layer is None:
            safe_print("警告: 尝试启用控件，但current_layer为None")
            return

        safe_print(f"设置控件状态: {'启用' if enabled else '禁用'}")

        try:
            # 基本控件
            if hasattr(self, 'name_edit'):
                self.name_edit.setEnabled(enabled)

            # 获取锁定状态
            is_locked = enabled and self.current_layer and hasattr(self.current_layer, 'locked') and self.current_layer.locked

            # 位置和尺寸控件 - 只有在未锁定时启用
            position_enabled = enabled and not is_locked
            if hasattr(self, 'x_spin'):
                self.x_spin.setEnabled(position_enabled)
            if hasattr(self, 'y_spin'):
                self.y_spin.setEnabled(position_enabled)
            if hasattr(self, 'width_spin'):
                self.width_spin.setEnabled(position_enabled)
            if hasattr(self, 'height_spin'):
                self.height_spin.setEnabled(position_enabled)
            if hasattr(self, 'aspect_lock_btn'):
                self.aspect_lock_btn.setEnabled(position_enabled)

            # 样式控件 - 只有在未锁定时启用
            if hasattr(self, 'use_original_size_checkbox'):
                self.use_original_size_checkbox.setEnabled(position_enabled)
            if hasattr(self, 'fit_mode_combo'):
                self.fit_mode_combo.setEnabled(position_enabled)
            if hasattr(self, 'crop_direction_combo'):
                self.crop_direction_combo.setEnabled(position_enabled)

            # 混合模式
            if hasattr(self, 'blend_mode_combo'):
                self.blend_mode_combo.setEnabled(position_enabled)

            # 杂项控件
            if hasattr(self, 'opacity_slider'):
                self.opacity_slider.setEnabled(position_enabled)
            if hasattr(self, 'visible_checkbox'):
                self.visible_checkbox.setEnabled(enabled)  # 可见性总是可以更改
            if hasattr(self, 'locked_checkbox'):
                self.locked_checkbox.setEnabled(enabled)   # 锁定状态总是可以更改

            # 图像源控件
            source_enabled = enabled and not is_locked
            if hasattr(self, 'folder_radio'):
                self.folder_radio.setEnabled(source_enabled)
            if hasattr(self, 'file_radio'):
                self.file_radio.setEnabled(source_enabled)
            if hasattr(self, 'source_path_edit'):
                self.source_path_edit.setEnabled(source_enabled)  # 路径输入框与其他图像源控件同步
            if hasattr(self, 'browse_btn'):
                self.browse_btn.setEnabled(source_enabled)
            if hasattr(self, 'random_btn') and hasattr(self, 'folder_radio'):
                self.random_btn.setEnabled(source_enabled and self.folder_radio.isChecked())

            # 分身设置
            clone_enabled = enabled and not is_locked
            if hasattr(self, 'clone_enabled_checkbox'):
                self.clone_enabled_checkbox.setEnabled(clone_enabled)

                # 分身详细设置 - 只有在启用分身且未锁定时才启用
                clone_settings_enabled = clone_enabled and self.clone_enabled_checkbox.isChecked()
                if hasattr(self, 'clone_rows_spin'):
                    self.clone_rows_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'clone_columns_spin'):
                    self.clone_columns_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'row_spacing_spin'):
                    self.row_spacing_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'column_spacing_spin'):
                    self.column_spacing_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'clone_custom_size_checkbox'):
                    self.clone_custom_size_checkbox.setEnabled(clone_settings_enabled)
                    # 自定义大小控件只有在启用分身和启用自定义大小时才可用
                    custom_size_enabled = clone_settings_enabled and self.clone_custom_size_checkbox.isChecked()
                    if hasattr(self, 'clone_width_spin'):
                        self.clone_width_spin.setEnabled(custom_size_enabled)
                    if hasattr(self, 'clone_height_spin'):
                        self.clone_height_spin.setEnabled(custom_size_enabled)

            # 绑定入口已移至左侧栏，右侧不再维护 manage_binding_btn 状态

            # 形状控件设置
            shape_enabled = enabled and not is_locked
            if hasattr(self, 'shape_type_combo'):
                self.shape_type_combo.setEnabled(shape_enabled)
            if hasattr(self, 'shape_type_buttons'):
                for button in self.shape_type_buttons:
                    button.setEnabled(shape_enabled)
            if hasattr(self, 'shape_params_widget'):
                self.shape_params_widget.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_radius_spin'):
                self.vector_corner_radius_spin.setEnabled(shape_enabled)
            if hasattr(self, 'convert_to_path_btn'):
                self.convert_to_path_btn.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_tl_spin'):
                self.vector_corner_tl_spin.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_tr_spin'):
                self.vector_corner_tr_spin.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_br_spin'):
                self.vector_corner_br_spin.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_bl_spin'):
                self.vector_corner_bl_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_join_combo'):
                self.stroke_join_combo.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_cap_combo'):
                self.stroke_cap_combo.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_dash_length_spin'):
                self.stroke_dash_length_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_dash_gap_spin'):
                self.stroke_dash_gap_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_enabled_checkbox'):
                self.stroke_enabled_checkbox.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_width_spin'):
                self.stroke_width_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_type_combo'):
                self.stroke_type_combo.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_color_btn'):
                self.stroke_color_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_solid_enabled_checkbox'):
                self.fill_solid_enabled_checkbox.setEnabled(shape_enabled)
            if hasattr(self, 'fill_mode_buttons'):
                for button in self.fill_mode_buttons:
                    button.setEnabled(shape_enabled)
            if hasattr(self, 'fill_solid_color_btn'):
                self.fill_solid_color_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_enabled_checkbox'):
                self.fill_gradient_enabled_checkbox.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_start_btn'):
                self.fill_gradient_start_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_end_btn'):
                self.fill_gradient_end_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_angle_spin'):
                self.fill_gradient_angle_spin.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_opacity_spin'):
                self.fill_gradient_opacity_spin.setEnabled(shape_enabled)

            # 变换控件设置
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(self.current_layer if enabled and not is_locked else None)

            # 设置随机变换控件的图层
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(self.current_layer if enabled and not is_locked else None)

            # 同步独立模块窗口启用态（随面板整体状态变化）
            for dock in self._module_docks.values():
                dock.setEnabled(enabled)

        except Exception as e:
            safe_print(f"设置控件状态时出错: {e}")
            import traceback
            traceback.print_exc()

    def layer_selected(self, layer_index):
        """当选择图层时更新面板"""
        if not self.document:
            safe_print("警告: document为空，无法选择图层")
            return

        safe_print(f"选择图层: {layer_index}")

        # 检查索引是否有效
        if not hasattr(self.document, 'layers'):
            safe_print("警告: document没有layers属性")
            return

        if not isinstance(self.document.layers, list):
            safe_print(f"警告: document.layers不是列表，而是 {type(self.document.layers)}")
            return

        if layer_index < 0 or layer_index >= len(self.document.layers):
            safe_print(f"警告: 图层索引 {layer_index} 超出范围 0-{len(self.document.layers)-1}")
            self.current_layer = None
            self.set_controls_enabled(False)
            return

        # 设置当前图层并更新面板
        self.current_layer = self.document.layers[layer_index]
        print(f"图层已选中: {self.current_layer.name}")
        print(f"图层形状类型: {getattr(self.current_layer, 'shape_type', '无')}")

        if is_layer_group(self.current_layer):
            self.text_layer_panel.hide()
            self.shaped_layer_panel.hide()
            self.normal_layer_panel.show()
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(None)
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(None)
            self.update_panel()
            return

        # 检查图层类型并切换面板
        from app.models.text_layer import TextLayer
        try:
            from app.models.shaped_layer_new import ShapedLayer as NewShapedLayer
            ShapedLayerType = NewShapedLayer
        except ImportError:
            from app.models.shaped_layer import ShapedLayer
            ShapedLayerType = ShapedLayer
        is_multi = self._is_multi_layer_edit()
        is_text_layer = isinstance(self.current_layer, TextLayer)
        is_shaped_layer = isinstance(self.current_layer, ShapedLayerType)
        if is_multi:
            is_text_layer = is_text_layer and self._selected_layers_all_match(TextLayer)
            is_shaped_layer = is_shaped_layer and self._selected_layers_all_match(ShapedLayerType)

        if is_text_layer:
            # 显示文字图层面板，隐藏其他面板
            self.normal_layer_panel.hide()
            self.shaped_layer_panel.hide()
            self.text_layer_panel.show()
            self.text_layer_panel.set_text_layer(self.current_layer)
        elif is_shaped_layer:
            # 异形图层需要通用属性与特有属性同时可用：同时显示普通面板与异形面板
            self.text_layer_panel.hide()
            self.normal_layer_panel.show()
            self.shaped_layer_panel.show()
            self.shaped_layer_panel.set_layer(self.current_layer)

            # 设置变换控件的图层（通用属性仍然适用）
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(self.current_layer)
            # 设置随机变换控件的图层
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(self.current_layer)
        else:
            # 显示普通图层面板，隐藏其他面板
            self.text_layer_panel.hide()
            self.shaped_layer_panel.hide()
            self.normal_layer_panel.show()

            # 设置变换控件的图层
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(self.current_layer)

            # 设置随机变换控件的图层
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(self.current_layer)

        # 更新面板 - 这会同时设置控件状态
        self.update_panel()

    def update_panel(self):
        """更新面板显示当前选中图层的属性"""
        if self._is_export_ui_frozen():
            return
        if not self.document or not hasattr(self.document, 'selected_layer_index') or self.document.selected_layer_index < 0:
            self.set_controls_enabled(False)
            return

        layer_index = self.document.selected_layer_index
        if layer_index < 0 or layer_index >= len(self.document.layers):
            self.set_controls_enabled(False)
            return

        layer = self.document.layers[layer_index]
        self.current_layer = layer
        if is_layer_group(layer):
            self._update_group_panel(layer)
            return
        selected_layers = self._selected_editable_layers(allow_locked=True)
        is_multi = len(selected_layers) > 1

        safe_print(f"更新图层属性面板，图层索引: {layer_index}, 名称: {layer.name}")

        # 检查是否是文字图层
        from app.models.text_layer import TextLayer
        if isinstance(layer, TextLayer) and not is_multi:
            # 文字图层由文字图层面板处理
            return

        # 普通图层处理
        # 阻断信号连接，避免触发事件
        self._block_all_signals(True)

        try:
            # 更新控件值
            # 名称
            self.name_edit.setText(f"已选择 {len(selected_layers)} 个图层" if is_multi else layer.name)
            self.name_edit.setEnabled(not is_multi)

            # 位置
            self.x_spin.setValue(layer.x)
            self.y_spin.setValue(layer.y)

            # 尺寸
            self.width_spin.setValue(layer.width)
            self.height_spin.setValue(layer.height)
            mixed_tip = "多选：当前值不完全相同，修改后会应用到所有未锁定选中图层"
            for attr, widget in (
                ("x", self.x_spin),
                ("y", self.y_spin),
                ("width", self.width_spin),
                ("height", self.height_spin),
                ("opacity", self.opacity_slider),
            ):
                if hasattr(widget, 'setToolTip'):
                    widget.setToolTip(mixed_tip if is_multi and self._selected_layers_have_mixed_value(attr) else "")

            # 初始化锁定比例状态
            if hasattr(layer, 'aspect_ratio_locked'):
                self.aspect_ratio_locked = layer.aspect_ratio_locked
                self.aspect_lock_btn.setChecked(layer.aspect_ratio_locked)
            else:
                self.aspect_ratio_locked = False
                self.aspect_lock_btn.setChecked(False)

            # 计算并保存当前宽高比
            if layer.height > 0:
                self.original_aspect_ratio = layer.width / layer.height
            else:
                self.original_aspect_ratio = 1.0

            # 更新锁定按钮图标
            self.update_aspect_lock_icon()

            # 原始尺寸
            use_original_size = hasattr(layer, 'use_original_size') and layer.use_original_size
            self.use_original_size_checkbox.setChecked(use_original_size)

            # 适配模式
            fit_mode = 0
            if hasattr(layer, 'fit_mode'):
                fit_mode = layer.fit_mode if isinstance(layer.fit_mode, int) else 0
            self.fit_mode_combo.setCurrentIndex(fit_mode)

            # 裁剪方向
            crop_direction = 0
            if hasattr(layer, 'crop_direction'):
                crop_direction = layer.crop_direction if isinstance(layer.crop_direction, int) and 0 <= layer.crop_direction <= 4 else 0
            self.crop_direction_combo.setCurrentIndex(crop_direction)

            # 混合模式
            if hasattr(self, 'blend_mode_combo'):
                try:
                    if hasattr(layer, 'blend_mode'):
                        # 获取混合模式值
                        mode_value = layer.blend_mode

                        # 转换数字为字符串
                        mode_names = [
                            "正常", "正片叠底", "滤色", "叠加", "柔光", "强光",
                            "颜色减淡", "颜色加深", "变暗", "变亮", "差值", "排除",
                            "色相", "饱和度", "颜色", "明度"
                        ]

                        if isinstance(mode_value, int) and 0 <= mode_value < len(mode_names):
                            mode_text = mode_names[mode_value]
                        else:
                            # 如果是字符串或其他类型，尝试直接使用
                            mode_text = str(mode_value)

                        # 查找是否存在于下拉框中
                        index = self.blend_mode_combo.findText(mode_text)
                        if index >= 0:
                            self.blend_mode_combo.setCurrentIndex(index)
                        else:
                            # 如果没有找到，设为正常模式
                            self.blend_mode_combo.setCurrentText("正常")
                    else:
                        # 如果没有blend_mode属性，设为"正常"
                        self.blend_mode_combo.setCurrentText("正常")
                except Exception as e:
                    safe_print(f"设置混合模式出错: {e}")
                    self.blend_mode_combo.setCurrentText("正常")

            # 不透明度
            opacity = 1.0 if not hasattr(layer, 'opacity') else layer.opacity
            opacity_percent = int(opacity * 100)
            self.opacity_slider.setValue(opacity_percent)
            self.opacity_label.setText(f"{opacity_percent}%")

            # 可见性
            visible = True if not hasattr(layer, 'visible') else layer.visible
            self.visible_checkbox.setChecked(visible)

            # 锁定状态
            locked = False if not hasattr(layer, 'locked') else layer.locked
            self.locked_checkbox.setChecked(locked)

            # 形状属性
            if not hasattr(layer, 'shape_type'):
                shape_type = "rectangle"
            else:
                # 处理枚举类型，获取字符串值
                shape_type_value = layer.shape_type
                if hasattr(shape_type_value, 'value'):
                    shape_type = shape_type_value.value
                else:
                    shape_type = str(shape_type_value)

            shape_type_map = {
                "rectangle": "矩形",
                "right_trapezoid": "直角梯形",
                "circle": "圆形",
                "pentagon": "正五边形",
                "hexagon": "正六边形"
            }
            shape_type_text = shape_type_map.get(shape_type, "矩形")
            self.shape_type_combo.setCurrentText(shape_type_text)
            self._sync_shape_segment_buttons(shape_type_text)

            # 更新形状参数控件的可见性
            print(f"准备更新形状参数可见性: shape_type={shape_type}")
            print(f"形状参数容器是否可见: {self.shape_params_widget.isVisible()}")

            # 确保形状参数容器是可见的
            self.shape_params_widget.setVisible(True)
            print(f"设置形状参数容器为可见")

            self.update_shape_params_visibility(shape_type)

            # 梯形参数
            if hasattr(layer, 'trapezoid_top_width'):
                self.trapezoid_top_spin.setValue(layer.trapezoid_top_width)
            if hasattr(layer, 'trapezoid_bottom_width'):
                self.trapezoid_bottom_spin.setValue(layer.trapezoid_bottom_width)
            if hasattr(layer, 'trapezoid_slope_side'):
                side_text = "左侧" if layer.trapezoid_slope_side == "left" else "右侧"
                self.trapezoid_side_combo.setCurrentText(side_text)

            # 多边形参数
            if hasattr(layer, 'polygon_rotation'):
                self.polygon_rotation_spin.setValue(layer.polygon_rotation)
            if hasattr(layer, 'polygon_corner_radius'):
                self.polygon_radius_spin.setValue(layer.polygon_corner_radius)

            # 矢量外观属性
            self.vector_corner_tl_spin.setValue(int(getattr(layer, 'vector_corner_radius_tl', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_tr_spin.setValue(int(getattr(layer, 'vector_corner_radius_tr', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_br_spin.setValue(int(getattr(layer, 'vector_corner_radius_br', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_bl_spin.setValue(int(getattr(layer, 'vector_corner_radius_bl', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_radius_spin.setValue(max(
                self.vector_corner_tl_spin.value(),
                self.vector_corner_tr_spin.value(),
                self.vector_corner_br_spin.value(),
                self.vector_corner_bl_spin.value()
            ))
            join_map = {"miter": "斜接", "round": "圆角", "bevel": "斜切"}
            cap_map = {"butt": "平头", "round": "圆头", "square": "方头"}
            self.stroke_join_combo.setCurrentText(join_map.get(getattr(layer, 'stroke_join', 'miter'), "斜接"))
            self.stroke_cap_combo.setCurrentText(cap_map.get(getattr(layer, 'stroke_cap', 'butt'), "平头"))
            self.stroke_dash_length_spin.setValue(int(getattr(layer, 'stroke_dash_length', 0)))
            self.stroke_dash_gap_spin.setValue(int(getattr(layer, 'stroke_dash_gap', 0)))
            self.stroke_enabled_checkbox.setChecked(bool(getattr(layer, 'stroke_enabled', False)))
            self.stroke_width_spin.setValue(int(getattr(layer, 'stroke_width', 1)))
            self.stroke_type_combo.setCurrentIndex(int(getattr(layer, 'stroke_type', 0)))

            stroke_color = tuple(getattr(layer, 'stroke_color', (0, 0, 0, 255)))
            self._set_button_color(self.stroke_color_btn, stroke_color)
            fill_color = tuple(getattr(layer, 'color_overlay_color', (255, 0, 0, 255)))
            self._set_button_color(self.fill_solid_color_btn, fill_color)
            grad_colors = list(getattr(layer, 'gradient_overlay_colors', [(0, 0, 0, 255), (255, 255, 255, 255)]))
            if len(grad_colors) < 2:
                grad_colors = [(0, 0, 0, 255), (255, 255, 255, 255)]
            self._set_button_color(self.fill_gradient_start_btn, tuple(grad_colors[0]))
            self._set_button_color(self.fill_gradient_end_btn, tuple(grad_colors[1]))
            self.fill_solid_enabled_checkbox.setChecked(bool(getattr(layer, 'color_overlay_enabled', False)))
            self.fill_gradient_enabled_checkbox.setChecked(bool(getattr(layer, 'gradient_overlay_enabled', False)))
            self.fill_gradient_angle_spin.setValue(float(getattr(layer, 'gradient_overlay_angle', 90.0)))
            self.fill_gradient_opacity_spin.setValue(int(float(getattr(layer, 'gradient_overlay_opacity', 1.0)) * 100))
            self._sync_appearance_visibility()

            # 更新形状预览
            try:
                from app.models.layer_properties import ShapeType as LPShapeType
                lp_type = layer.shape_type if hasattr(layer, 'shape_type') else LPShapeType.RECTANGLE
                # 映射到预览用枚举
                mapping = {
                    LPShapeType.RECTANGLE: PreviewShapeType.RECTANGLE,
                    LPShapeType.RIGHT_TRAPEZOID: PreviewShapeType.RIGHT_TRAPEZOID,
                    LPShapeType.CIRCLE: PreviewShapeType.CIRCLE,
                    LPShapeType.PENTAGON: PreviewShapeType.PENTAGON,
                    LPShapeType.HEXAGON: PreviewShapeType.HEXAGON,
                }
                self.shape_preview.set_shape_type(mapping.get(lp_type, PreviewShapeType.RECTANGLE))
                if hasattr(layer, 'trapezoid_top_width') and hasattr(layer, 'trapezoid_bottom_width') and hasattr(layer, 'trapezoid_slope_side'):
                    self.shape_preview.set_trapezoid_params(
                        layer.trapezoid_top_width,
                        layer.trapezoid_bottom_width,
                        layer.trapezoid_slope_side
                    )
                sides = 5 if (hasattr(layer, 'shape_type') and str(getattr(layer, 'shape_type').value) == 'pentagon') else 6
                if hasattr(layer, 'polygon_rotation'):
                    self.shape_preview.set_polygon_params(layer.polygon_rotation, sides)
                self.shape_preview.update()
            except Exception:
                pass

            # 图像源类型
            is_folder = True if not hasattr(layer, 'is_folder') else layer.is_folder
            self.folder_radio.setChecked(is_folder)
            self.file_radio.setChecked(not is_folder)

            # 图像源路径
            image_source = "" if not hasattr(layer, 'image_source') or layer.image_source is None else layer.image_source
            self.source_path_edit.setText(image_source)

            # 当前图像预览 - 添加文件存在性检查
            if hasattr(layer, 'current_image_path') and layer.current_image_path:
                if os.path.isfile(layer.current_image_path):
                    filename = os.path.basename(layer.current_image_path)
                    self.current_image_label.setText(f"当前图像: {filename}")
                else:
                    # 文件不存在，清空路径并显示无
                    # 🔧 关键修复：使用公共属性setter
                    layer.current_image_path = None
                    self.current_image_label.setText("当前图像: 无")
            else:
                self.current_image_label.setText("当前图像: 无")

            # 更新分身设置 - 安全地检查属性是否存在
            has_clone_properties = (hasattr(layer, 'clone_enabled') and
                                  hasattr(layer, 'clone_rows') and
                                  hasattr(layer, 'clone_columns') and
                                  hasattr(layer, 'clone_row_spacing') and
                                  hasattr(layer, 'clone_column_spacing'))

            if has_clone_properties:
                try:
                    self.clone_enabled_checkbox.setChecked(layer.clone_enabled)
                    self.clone_rows_spin.setValue(layer.clone_rows)
                    self.clone_columns_spin.setValue(layer.clone_columns)
                    self.row_spacing_spin.setValue(layer.clone_row_spacing)
                    self.column_spacing_spin.setValue(layer.clone_column_spacing)

                    # 更新自定义大小设置
                    custom_size_enabled = getattr(layer, 'clone_custom_size_enabled', False)
                    self.clone_custom_size_checkbox.setChecked(custom_size_enabled)
                    self.clone_width_spin.setEnabled(custom_size_enabled)
                    self.clone_height_spin.setEnabled(custom_size_enabled)
                    if hasattr(layer, 'clone_custom_width'):
                        self.clone_width_spin.setValue(layer.clone_custom_width)
                    if hasattr(layer, 'clone_custom_height'):
                        self.clone_height_spin.setValue(layer.clone_custom_height)

                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    mirror_text_map = {
                        'none': '无镜像',
                        'horizontal': '左右镜像',
                        'vertical': '上下镜像'
                    }
                    self.clone_mirror_combo.setCurrentText(mirror_text_map.get(mirror_mode, '无镜像'))
                except Exception as e:
                    safe_print(f"更新分身设置出错: {e}")
                    self.clone_enabled_checkbox.setChecked(False)
                    self.clone_rows_spin.setValue(1)
                    self.clone_columns_spin.setValue(1)
                    self.row_spacing_spin.setValue(0)
                    self.column_spacing_spin.setValue(0)
                    self.clone_mirror_combo.setCurrentText('无镜像')
            else:
                # 初始化分身属性为默认值
                if hasattr(layer, 'clone_enabled'):
                    layer.clone_enabled = False
                if hasattr(layer, 'clone_rows'):
                    layer.clone_rows = 1
                if hasattr(layer, 'clone_columns'):
                    layer.clone_columns = 1
                if hasattr(layer, 'clone_row_spacing'):
                    layer.clone_row_spacing = 0
                if hasattr(layer, 'clone_column_spacing'):
                    layer.clone_column_spacing = 0
                if not hasattr(layer, 'clone_mirror_mode'):
                    layer.clone_mirror_mode = 'none'

                self.clone_enabled_checkbox.setChecked(False)
                self.clone_rows_spin.setValue(1)
                self.clone_columns_spin.setValue(1)
                self.row_spacing_spin.setValue(0)
                self.column_spacing_spin.setValue(0)
                self.clone_mirror_combo.setCurrentText('无镜像')

            # 更新绑定设置 - 安全地检查属性是否存在
            has_bind_properties = (hasattr(layer, 'bind_enabled') and
                                 hasattr(layer, 'bind_group') and
                                 hasattr(layer, 'bind_strategy'))

            if has_bind_properties:
                try:
                    # 绑定状态显示
                    bind_status = f"已绑定到组: {layer.bind_group}" if layer.bind_group else "未绑定"
                    self.bind_status_label.setText(bind_status)

                    # 绑定策略已简化，不再需要UI控件
                    pass
                except Exception as e:
                    safe_print(f"更新绑定设置出错: {e}")
                    self.bind_status_label.setText("未绑定")
            else:
                # 初始化绑定属性为默认值
                if not hasattr(layer, 'bind_enabled'):
                    layer.bind_enabled = False
                if not hasattr(layer, 'bind_group'):
                    layer.bind_group = None
                if not hasattr(layer, 'bind_strategy'):
                    layer.bind_strategy = "filename"

                self.bind_status_label.setText("未绑定")

        finally:
            # 恢复信号连接
            self._block_all_signals(False)

        # 启用控件并设置其状态
        self.set_controls_enabled(True)
        if is_multi:
            self.name_edit.setEnabled(False)

    def _update_group_panel(self, group):
        """显示图层组的基础属性，组不参与位置/尺寸/效果编辑。"""
        self._block_all_signals(True)
        try:
            if self.text_layer_panel:
                self.text_layer_panel.hide()
            if hasattr(self, 'shaped_layer_panel') and self.shaped_layer_panel:
                self.shaped_layer_panel.hide()
            if hasattr(self, 'normal_layer_panel') and self.normal_layer_panel:
                self.normal_layer_panel.show()

            self.name_edit.setText(getattr(group, 'name', '图层组'))
            self.visible_checkbox.setChecked(bool(getattr(group, 'visible', True)))
            self.locked_checkbox.setChecked(bool(getattr(group, 'locked', False)))
            if hasattr(self, 'opacity_label'):
                self.opacity_label.setText("--")
            if hasattr(self, 'current_image_label'):
                self.current_image_label.setText("图层组")

            self.set_controls_enabled(False)
            self.name_edit.setEnabled(True)
            self.visible_checkbox.setEnabled(True)
            self.locked_checkbox.setEnabled(True)
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(None)
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(None)
        finally:
            self._block_all_signals(False)

