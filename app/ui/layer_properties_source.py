import logging

logger = logging.getLogger(__name__)
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


class LayerPropertiesSource(object):
    """Mixin for layer_properties_source (split from LayerPropertiesPanel)."""

    def browse_image(self):
        """浏览并选择图像文件"""
        if not self.current_layer:
            return

        # 打开文件对话框
        if self.folder_radio.isChecked():
            folder_path = QFileDialog.getExistingDirectory(self, "选择图像文件夹")
            if folder_path:
                safe_print(f"选择文件夹: {folder_path}")  # 调试信息

                # 保存当前状态
                self.document.save_state("更改图层图像源前")

                # 更新图层图像源
                self.current_layer.image_source = folder_path
                self.current_layer.is_folder = True
                self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                self.current_layer.cached_image = None

                # 清除快速渲染器缓存（关键修复）
                self.document._invalidate_render_cache()

                # 更新路径显示
                self.source_path_edit.setText(folder_path)
                self.current_image_label.setText("当前图像: 无")

                # 更新随机按钮状态
                self.random_btn.setEnabled(True)

                # 通知文档已更改
                self.document.document_changed.emit()

                # 保存更改后的状态
                self.document.save_state("更改图层图像源")
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择图像文件",
                "",
                "图像文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*.*)"
            )

            if file_path:
                safe_print(f"选择文件: {file_path}")  # 调试信息

                # 保存当前状态
                self.document.save_state("更改图层图像源前")

                # 更新图层图像源
                self.current_layer.image_source = file_path
                self.current_layer.is_folder = False
                self.current_layer.current_image_path = file_path  # 🔧 修复：使用公共属性
                self.current_layer.cached_image = None

                # 清除快速渲染器缓存（关键修复）
                self.document._invalidate_render_cache()

                # 更新路径显示
                self.source_path_edit.setText(file_path)
                if os.path.isfile(file_path):
                    self.current_image_label.setText(f"当前图像: {os.path.basename(file_path)}")
                else:
                    # 文件不存在，清空并显示无
                    self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                    self.current_image_label.setText("当前图像: 无")

                # 更新随机按钮状态
                self.random_btn.setEnabled(False)

                # 通知文档已更改
                self.document.document_changed.emit()

                # 保存更改后的状态
                self.document.save_state("更改图层图像源")

    def randomize_image(self):
        """随机选择图像"""
        if not self.current_layer or not self.current_layer.is_folder:
            return

        safe_print("随机选择图像")  # 调试信息

        # 保存当前状态
        self.document.save_state("随机选择图像前")

        # 使用文件限制进行随机选择
        image = self._randomize_layer_with_restrictions(self.current_layer)
        if image:
            if hasattr(self.current_layer, 'current_image_path') and self.current_layer.current_image_path and os.path.isfile(self.current_layer.current_image_path):
                self.current_image_label.setText(f"当前图像: {os.path.basename(self.current_layer.current_image_path)}")
            else:
                self.current_image_label.setText("当前图像: 无")

            # 如果使用原始尺寸，更新尺寸控件
            if self.current_layer.use_original_size:
                self.width_spin.setValue(self.current_layer.width)
                self.height_spin.setValue(self.current_layer.height)

            # 使渲染缓存失效，确保预览窗口显示最新的随机图像
            self.document._invalidate_render_cache()

            # 强制通知文档已更改，确保UI刷新
            self.document.document_changed.emit()
            self.document.layer_changed.emit()  # 也发送图层变化信号

            # 保存更改后的状态
            self.document.save_state("随机选择图像")

    def _randomize_layer_with_restrictions(self, layer):
        """使用文件限制随机化图层"""
        try:
            # 首先确保绑定管理器分析了文件限制
            if hasattr(self.document, 'binding_manager') and self.document.binding_manager.global_enabled:
                safe_print(f"[图层属性] 为单图层随机化分析文件限制...")
                self.document.binding_manager.analyze_and_restrict_layer_files(self.document.layers)

                # 检查是否是绑定图层
                if self.document.binding_manager.is_layer_bound(layer):
                    safe_print(f"[图层属性] 图层 '{layer.name}' 是绑定图层，使用绑定组随机化")
                    # 绑定图层：使用绑定管理器处理
                    bound_layers_mapping = self.document.binding_manager.randomize_bound_layers(self.document.layers)
                    if id(layer) in bound_layers_mapping:
                        safe_print(f"[图层属性] 绑定图层 '{layer.name}' 已更新")
                        return layer.cached_image  # 返回更新后的图像
                    else:
                        safe_print(f"[图层属性] 警告：绑定图层 '{layer.name}' 未在绑定结果中")
                        return layer.get_random_image(force_random=True)
                else:
                    # 非绑定图层：使用文件限制
                    restricted_files = self.document.binding_manager.get_layer_file_restrictions(layer)
                    if restricted_files:
                        safe_print(f"[图层属性] 图层 '{layer.name}' 使用文件限制随机化，可选文件: {len(restricted_files)} 个")
                        return layer.get_random_image(force_random=True, restrict_to_bound_files=restricted_files)
                    else:
                        safe_print(f"[图层属性] 图层 '{layer.name}' 无文件限制，正常随机化")
                        return layer.get_random_image(force_random=True)
            else:
                # 没有绑定管理器或未启用，正常随机化
                safe_print(f"[图层属性] 图层 '{layer.name}' 正常随机化（无绑定管理器）")
                return layer.get_random_image(force_random=True)

        except Exception as e:
            safe_print(f"[图层属性] 随机化图层 '{layer.name}' 时出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时回退到正常随机化
            return layer.get_random_image(force_random=True)

    def handle_folder_toggled(self, checked):
        """处理文件夹单选按钮状态变化"""
        if checked and not self._source_type_changing:
            self.toggle_source_type(self.folder_radio)

    def handle_file_toggled(self, checked):
        """处理单个文件单选按钮状态变化"""
        if checked and not self._source_type_changing:
            self.toggle_source_type(self.file_radio)

    def toggle_source_type(self, button):
        """切换图像源类型（文件夹/单个文件）"""
        if not self.current_layer:
            return

        # 防止递归
        self._source_type_changing = True
        try:
            is_folder = (button == self.folder_radio)
            safe_print(f"切换图像源类型: {'文件夹' if is_folder else '单个文件'}")  # 调试信息

            # 如果状态没有变化，则不处理
            if self.current_layer.is_folder == is_folder:
                self._source_type_changing = False
                return

            # 保存当前状态
            if self.document:
                self.document.save_state("切换图像源类型前")

            # 更新图像源类型
            self.current_layer.is_folder = is_folder

            # 清除当前图像
            self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
            self.current_layer.cached_image = None
            self.current_image_label.setText("当前图像: 无")

            # 更新随机按钮状态
            self.random_btn.setEnabled(is_folder)

            # 标记文档为已修改
            if self.document:
                self.document.is_modified = True
                self.document.save_state("切换图像源类型")

                # 延迟发送变更信号以避免递归
                QTimer.singleShot(0, self.document.document_changed.emit)

            # 确保UI更新以反映变化
            self.update_panel()
        finally:
            self._source_type_changing = False

    def on_layer_changed(self):
        """当图层列表变化时调用"""
        safe_print("图层列表已变化")
        # 如果有图层但没有选中的图层，自动选择第一个
        if hasattr(self.document, 'layers') and len(self.document.layers) > 0:
            if self.document.selected_layer_index < 0:
                safe_print("自动选择第一个图层")
                self.document.select_layer(0)
            elif self.document.selected_layer_index >= len(self.document.layers):
                safe_print("选中索引超出范围，重置为最后一个图层")
                # 修复：重置为最后一个图层而不是第一个，这样更符合用户预期
                # 因为通常删除图层等操作会导致索引超出范围，选择最后一个图层更合理
                self.document.select_layer(len(self.document.layers) - 1)

    def set_document(self, document):
        """设置关联的文档"""
        # 如果有旧文档，断开信号连接
        if self.document:
            self.document.layer_changed.disconnect(self.on_layer_changed)
            self.document.layer_selected.disconnect(self.layer_selected)
            if hasattr(self.document, 'layers_selection_changed'):
                try:
                    self.document.layers_selection_changed.disconnect(self._on_layers_selection_changed)
                except Exception:
                    logger.debug("静默异常已忽略: except in ui/layer_properties_source.py")
                    pass
            self.document.document_changed.disconnect(self.delayed_update_panel)

        # 设置新文档
        self.document = document
        self.current_layer = None
        if self.text_layer_panel:
            self.text_layer_panel.set_document(document)

        # 如果新文档不为空，连接信号
        if self.document:
            self.document.layer_changed.connect(self.on_layer_changed)
            self.document.layer_selected.connect(self.layer_selected)
            if hasattr(self.document, 'layers_selection_changed'):
                self.document.layers_selection_changed.connect(self._on_layers_selection_changed)
            self.document.document_changed.connect(self.delayed_update_panel)

            # 如果文档有图层且已选择图层，直接触发选择
            if hasattr(self.document, 'layers') and len(self.document.layers) > 0:
                if hasattr(self.document, 'selected_layer_index') and self.document.selected_layer_index >= 0:
                    self.layer_selected(self.document.selected_layer_index)
                else:
                    # 自动选择第一个图层
                    self.document.select_layer(0)
        else:
            # 禁用所有控件
            self.set_controls_enabled(False)

    def update_clone_enabled(self, enabled):
        """更新图层分身启用状态"""
        if not self.current_layer:
            return

        # 保存当前状态
        if self.document:
            self.document.save_state("修改图层分身设置前")

        safe_print(f"更新图层分身: {enabled}")

        # 确保图层有所有必要的分身属性
        self._ensure_clone_properties()

        # 如果启用分身，并且行列都是1，则自动设置为2x2以便立即看到效果
        if enabled and self.current_layer.clone_rows == 1 and self.current_layer.clone_columns == 1:
            self.current_layer.clone_rows = 2
            self.current_layer.clone_columns = 2
            self.clone_rows_spin.setValue(2)
            self.clone_columns_spin.setValue(2)
            # 确保UI更新以反映新值
            self.clone_rows_spin.valueChanged.emit(2)
            self.clone_columns_spin.valueChanged.emit(2)

        # 设置分身启用状态
        self.current_layer.clone_enabled = enabled

        # 清除图层缓存以便重新渲染
        self.current_layer.cached_image = None

        # 启用或禁用分身设置控件
        self.clone_rows_spin.setEnabled(enabled)
        self.clone_columns_spin.setEnabled(enabled)
        self.row_spacing_spin.setEnabled(enabled)
        self.column_spacing_spin.setEnabled(enabled)

        # 绑定入口已移至左侧栏，这里无需管理右侧按钮状态

        # 通知文档变化
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改图层分身设置后")

    def update_clone_mirror_mode_index(self, index):
        if not self.current_layer:
            return
        if self.document:
            self.document.save_state("修改图层分身镜像前")
        text = self.clone_mirror_combo.itemText(index)
        mode_map = {"无镜像": "none", "左右镜像": "horizontal", "上下镜像": "vertical"}
        self._ensure_clone_properties()
        self.current_layer.clone_mirror_mode = mode_map.get(text, "none")
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.layer_changed.emit()
            self.document.save_state("修改图层分身镜像后")

    def _ensure_clone_properties(self):
        """确保图层具有所有必要的分身属性"""
        if not self.current_layer:
            return

        # 设置默认的分身属性（如果不存在）
        if not hasattr(self.current_layer, 'clone_enabled'):
            self.current_layer.clone_enabled = False
        if not hasattr(self.current_layer, 'clone_rows'):
            self.current_layer.clone_rows = 2  # 默认设置为2行
        if not hasattr(self.current_layer, 'clone_columns'):
            self.current_layer.clone_columns = 2  # 默认设置为2列
        if not hasattr(self.current_layer, 'clone_row_spacing'):
            self.current_layer.clone_row_spacing = 10  # 设置默认间距
        if not hasattr(self.current_layer, 'clone_column_spacing'):
            self.current_layer.clone_column_spacing = 10  # 设置默认间距
        if not hasattr(self.current_layer, 'clone_mirror_mode'):
            self.current_layer.clone_mirror_mode = "none"
        if not hasattr(self.current_layer, 'clone_custom_size_enabled'):
            self.current_layer.clone_custom_size_enabled = False
        if not hasattr(self.current_layer, 'clone_custom_width'):
            self.current_layer.clone_custom_width = self.current_layer.width if hasattr(self.current_layer, 'width') else 100
        if not hasattr(self.current_layer, 'clone_custom_height'):
            self.current_layer.clone_custom_height = self.current_layer.height if hasattr(self.current_layer, 'height') else 100

        if not hasattr(self.current_layer, 'clone_fill_enabled'):
            self.current_layer.clone_fill_enabled = False
        if not hasattr(self.current_layer, 'clone_fill_mode'):
            self.current_layer.clone_fill_mode = "grid"
        if not hasattr(self.current_layer, 'clone_fill_spacing'):
            self.current_layer.clone_fill_spacing = 0
        if not hasattr(self.current_layer, 'clone_fill_margin'):
            self.current_layer.clone_fill_margin = 0  # 添加边距属性初始化
        if not hasattr(self.current_layer, 'clone_fill_angle'):
            self.current_layer.clone_fill_angle = 0.0

        # 添加get_clone_positions方法如果不存在
        if not hasattr(self.current_layer, 'get_clone_positions') or not callable(getattr(self.current_layer, 'get_clone_positions')):
            # 创建一个更稳定的方法，不依赖闭包捕获层属性
            def get_clone_positions(self):
                """获取分身的所有位置，返回(x, y)坐标列表"""
                if not self.clone_enabled:
                    return [(self.x, self.y)]  # 未启用分身时只返回原始位置

                # 如果启用了填充模式，使用填充算法
                if hasattr(self, 'clone_fill_enabled') and self.clone_fill_enabled:
                    return self._get_fill_positions()

                # 否则使用基本网格分身
                positions = []
                for row in range(self.clone_rows):
                    for col in range(self.clone_columns):
                        x = self.x + col * (self.width + self.clone_column_spacing)
                        y = self.y + row * (self.height + self.clone_row_spacing)
                        positions.append((x, y))

                return positions

            def _get_fill_positions(self):
                """获取填充模式的位置，支持网格、错位、边框排列"""
                spacing = int(getattr(self, 'clone_fill_spacing', 0))
                angle_deg = float(getattr(self, 'clone_fill_angle', 0.0))
                mode = str(getattr(self, 'clone_fill_mode', 'grid'))
                margin = int(getattr(self, 'clone_fill_margin', 0))  # 新增边距参数

                dx = max(1, int(self.width + spacing))
                dy = max(1, int(self.height + spacing))
                positions = []

                # 获取画布尺寸（使用估计值或默认值）
                canvas_width = getattr(self, '_canvas_width', 800)  # 默认值
                canvas_height = getattr(self, '_canvas_height', 600)  # 默认值

                base_x = self.x
                base_y = self.y

                import math
                angle = math.radians(angle_deg % 360.0)
                cx = canvas_width / 2.0
                cy = canvas_height / 2.0

                if mode == 'border':
                    # 边框排列：确保四角有元素，行距列距统一，支持边距
                    # 应用边距到画布尺寸
                    effective_width = canvas_width - 2 * margin
                    effective_height = canvas_height - 2 * margin

                    # 计算每边的元素数量，确保四角都有元素
                    # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                    top_bottom_count = max(2, (effective_width + dx) // dx)  # 至少2个（两角）
                    # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                    left_right_count = max(2, (effective_height + dy) // dy)  # 至少2个（两角）

                    # 计算统一的间距，确保元素均匀分布
                    if top_bottom_count > 1:
                        top_bottom_spacing = (effective_width - self.width) / (top_bottom_count - 1)
                    else:
                        top_bottom_spacing = 0

                    if left_right_count > 1:
                        left_right_spacing = (effective_height - self.height) / (left_right_count - 1)
                    else:
                        left_right_spacing = 0

                    # 顶部边缘（包括左上角和右上角）
                    for i in range(top_bottom_count):
                        x = margin + int(i * top_bottom_spacing)
                        if x <= canvas_width - self.width - margin:  # 确保不超出有效区域
                            positions.append((x, margin))

                    # 底部边缘（包括左下角和右下角）
                    for i in range(top_bottom_count):
                        x = margin + int(i * top_bottom_spacing)
                        if x <= canvas_width - self.width - margin:  # 确保不超出有效区域
                            positions.append((x, canvas_height - self.height - margin))

                    # 左侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = margin + int(i * left_right_spacing)
                        if margin < y < canvas_height - self.height - margin:  # 确保有效位置
                            positions.append((margin, y))

                    # 右侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = margin + int(i * left_right_spacing)
                        if margin < y < canvas_height - self.height - margin:  # 确保有效位置
                            positions.append((canvas_width - self.width - margin, y))
                else:
                    # 网格或错位排列
                    start_y = -self.height
                    end_y = canvas_height + self.height
                    step_y = dy
                    i_row = 0
                    for row_y in range(start_y, end_y + 1, step_y):
                        offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                        for col_x in range(-self.width, canvas_width + self.width + 1, dx):
                            x0 = base_x + col_x + offset
                            y0 = base_y + row_y
                            if angle != 0.0:
                                rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                                ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                                x = int(rx)
                                y = int(ry)
                            else:
                                x = x0
                                y = y0
                            positions.append((x, y))
                        i_row += 1

                return positions if positions else [(self.x, self.y)]

            # 使用方法类型绑定到图层实例
            import types
            self.current_layer.get_clone_positions = types.MethodType(get_clone_positions, self.current_layer)

    def update_clone_custom_size_enabled(self, enabled):
        """更新分身自定义大小启用状态"""
        if not self.current_layer:
            return

        # 保存当前状态
        if self.document:
            self.document.save_state("修改分身自定义大小设置前")

        safe_print(f"更新分身自定义大小: {enabled}")

        # 确保图层有所有必要的分身属性
        self._ensure_clone_properties()

        # 设置自定义大小启用状态
        self.current_layer.clone_custom_size_enabled = enabled

        # 启用或禁用自定义大小控件
        self.clone_width_spin.setEnabled(enabled)
        self.clone_height_spin.setEnabled(enabled)

        # 如果启用，设置初始值为当前图层大小
        if enabled:
            self.clone_width_spin.setValue(self.current_layer.width)
            self.clone_height_spin.setValue(self.current_layer.height)
            self.current_layer.clone_custom_width = self.current_layer.width
            self.current_layer.clone_custom_height = self.current_layer.height

        # 清除图层缓存以便重新渲染
        self.current_layer.cached_image = None

        # 通知文档变化
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改分身自定义大小设置后")

    def update_clone_custom_size(self):
        """更新分身自定义大小"""
        if not self.current_layer:
            return

        # 确保图层有所有必要的分身属性
        self._ensure_clone_properties()

        # 更新自定义大小
        self.current_layer.clone_custom_width = self.clone_width_spin.value()
        self.current_layer.clone_custom_height = self.clone_height_spin.value()

        # 清除图层缓存以便重新渲染
        self.current_layer.cached_image = None

        safe_print(f"[UI] 更新分身自定义大小: 宽={self.current_layer.clone_custom_width}, 高={self.current_layer.clone_custom_height}")
        safe_print(f"[UI] 当前图层: {self.current_layer.name}, 原始尺寸: {self.current_layer.width}x{self.current_layer.height}")
        safe_print(f"[UI] 自定义大小启用: {self.current_layer.clone_custom_size_enabled}")

        # 通知文档变化
        if self.document:
            self._emit_document_change(throttled=True, fields=["clone_custom_size"], reason="clone_custom_size")
            # 强制更新画布
            if hasattr(self.document, 'canvas_updated'):
                self.document.canvas_updated.emit()
            self._save_state_deferred("修改分身自定义大小")

    def update_clone_settings(self):
        """更新图层分身设置"""
        if not self.current_layer:
            return

        try:
            # 确保图层有所有必要的分身属性
            self._ensure_clone_properties()

            # 更新图层分身设置
            self.current_layer.clone_rows = self.clone_rows_spin.value()
            self.current_layer.clone_columns = self.clone_columns_spin.value()
            self.current_layer.clone_row_spacing = self.row_spacing_spin.value()
            self.current_layer.clone_column_spacing = self.column_spacing_spin.value()

            # 清除图层缓存以便重新渲染
            self.current_layer.cached_image = None

            safe_print(f"更新分身设置: 行={self.current_layer.clone_rows}, 列={self.current_layer.clone_columns}, 行距={self.current_layer.clone_row_spacing}, 列距={self.current_layer.clone_column_spacing}")

            # 通知文档变化
            if self.document:
                self._emit_document_change(throttled=True, fields=["clone_grid"], reason="clone_grid")
                self._save_state_deferred("修改图层分身设置")

        except Exception as e:
            safe_print(f"更新分身设置出错: {e}")

    def update_fill_enabled(self, enabled):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_enabled = bool(enabled)
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
        self.current_layer.clone_fill_mode = mode_map.get(text, "grid")
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
            self._emit_document_change(throttled=True, fields=["fill_spacing"], reason="fill_spacing")
            self._save_state_deferred("修改元素填充间距")

    def update_fill_margin(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_margin = int(value)
        self.current_layer.cached_image = None
        if self.document:
            self._emit_document_change(throttled=True, fields=["fill_margin"], reason="fill_margin")
            self._save_state_deferred("修改元素填充边距")

    def update_fill_angle(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_angle = float(value)
        self.current_layer.cached_image = None
        if self.document:
            self._emit_document_change(throttled=True, fields=["fill_angle"], reason="fill_angle")
            self._save_state_deferred("修改元素填充角度")

    def sync_ui_with_layer(self):
        """同步UI控件值与当前图层属性"""
        if not self.current_layer:
            return

        # 阻止信号，避免递归更新
        self.blockSignals(True)

        try:
            # 同步名称 - 添加调试信息
            print(f"[调试] 图层对象: {self.current_layer}")
            print(f"[调试] 图层name属性: {self.current_layer.name}")
            print(f"[调试] name属性类型: {type(self.current_layer.name)}")

            # 同步名称
            layer_name = self.current_layer.name
            if isinstance(layer_name, str):
                self.name_edit.setText(layer_name)
            else:
                print(f"[错误] 图层名称不是字符串，而是: {type(layer_name)}")
                # 尝试获取字符串表示
                self.name_edit.setText(str(layer_name))

            # 同步位置
            self.x_spin.setValue(self.current_layer.x)
            self.y_spin.setValue(self.current_layer.y)

            # 同步尺寸
            self.width_spin.setValue(self.current_layer.width)
            self.height_spin.setValue(self.current_layer.height)

            # 同步透明度
            opacity_percent = int(self.current_layer.opacity * 100)
            self.opacity_slider.setValue(opacity_percent)
            self.opacity_label.setText(f"{opacity_percent}%")

            # 同步其他控件状态
            self.visible_checkbox.setChecked(self.current_layer.visible)
            self.locked_checkbox.setChecked(self.current_layer.locked)
            self.use_original_size_checkbox.setChecked(self.current_layer.use_original_size)

            # 同步适配模式
            self.fit_mode_combo.setCurrentIndex(self.current_layer.fit_mode)

            # 同步裁剪方向
            self.crop_direction_combo.setCurrentIndex(self.current_layer.crop_direction)
            self.crop_direction_combo.setEnabled(self.current_layer.fit_mode == 1)

            # 同步启用状态
            self.width_spin.setEnabled(not self.current_layer.use_original_size and not self.current_layer.locked)
            self.height_spin.setEnabled(not self.current_layer.use_original_size and not self.current_layer.locked)

            # 同步图像路径
            if hasattr(self.current_layer, 'image_source') and self.current_layer.image_source:
                self.source_path_edit.setText(self.current_layer.image_source)
                # 更新图像名称显示（校验文件存在性）
                if hasattr(self.current_layer, 'current_image_path') and self.current_layer.current_image_path and os.path.isfile(self.current_layer.current_image_path):
                    self.current_image_label.setText(f"当前图像: {os.path.basename(self.current_layer.current_image_path)}")
                else:
                    # 文件不存在或未设置
                    if hasattr(self.current_layer, 'current_image_path'):
                        self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                    self.current_image_label.setText("当前图像: 无")
                # 更新随机按钮状态
                self.random_btn.setEnabled(self.current_layer.is_folder)
            else:
                self.source_path_edit.setText("")
                self.current_image_label.setText("当前图像: 无")
                self.random_btn.setEnabled(False)

            # 同步随机变换控件
            if hasattr(self, 'random_transform_widget') and self.random_transform_widget:
                self.random_transform_widget.update_from_layer()
                safe_print("同步随机变换控件")

            # 同步形状参数可见性
            if hasattr(self.current_layer, 'shape_type'):
                shape_type = self.current_layer.shape_type
                if hasattr(shape_type, 'value'):
                    shape_type_value = shape_type.value
                else:
                    shape_type_value = str(shape_type)
                print(f"同步形状参数可见性: {shape_type_value}")

                # 同步形状类型下拉框
                shape_type_map = {
                    "rectangle": "矩形",
                    "right_trapezoid": "直角梯形",
                    "circle": "圆形",
                    "pentagon": "正五边形",
                    "hexagon": "正六边形"
                }
                shape_type_text = shape_type_map.get(shape_type_value, "矩形")
                self.shape_type_combo.setCurrentText(shape_type_text)
                self._sync_shape_segment_buttons(shape_type_text)

                self.update_shape_params_visibility(shape_type_value)

            mirror_mode = getattr(self.current_layer, 'clone_mirror_mode', 'none')
            mirror_text_map = {
                'none': '无镜像',
                'horizontal': '左右镜像',
                'vertical': '上下镜像'
            }
            self.clone_mirror_combo.setCurrentText(mirror_text_map.get(mirror_mode, '无镜像'))

            safe_print(f"同步UI与图层完成: 尺寸={self.current_layer.width}x{self.current_layer.height}")
        finally:
            # 恢复信号
            self.blockSignals(False)

