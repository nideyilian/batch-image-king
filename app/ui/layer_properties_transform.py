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


class LayerPropertiesTransform(object):
    """Mixin for layer_properties_transform (split from LayerPropertiesPanel)."""

    def update_blend_mode(self, mode):
        """更新混合模式"""
        if not self.current_layer:
            return

        safe_print(f"更新混合模式: {mode}")  # 调试信息

        # 保存当前状态
        self.document.save_state("更改混合模式前")

        # 转换混合模式字符串为数字
        mode_map = {
            "正常": 0,
            "正片叠底": 1,
            "滤色": 2,
            "叠加": 3,
            "柔光": 4,
            "强光": 5,
            "颜色减淡": 6,
            "颜色加深": 7,
            "变暗": 8,
            "变亮": 9,
            "差值": 10,
            "排除": 11,
            "色相": 12,
            "饱和度": 13,
            "颜色": 14,
            "明度": 15
        }

        # 获取对应的数字值
        mode_value = mode_map.get(mode, 0)  # 默认为正常模式

        # 更新混合模式
        self.current_layer.blend_mode = mode_value

        # 使渲染缓存失效，确保预览窗口显示最新的混合效果
        self.document._invalidate_render_cache()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改混合模式")

    def handle_path_input(self):
        """处理用户输入的路径"""
        if not self.current_layer:
            return

        path = self.source_path_edit.text()
        if not path or path.strip() == "":
            return

        safe_print(f"处理路径输入: {path}")

        # 检查路径是否存在
        if not os.path.exists(path):
            QMessageBox.warning(self, "路径错误", f"无法访问路径:\n{path}\n请确认路径存在且有权限访问。")
            return

        # 保存当前状态
        self.document.save_state("更改图层图像源前")

        # 确定是文件夹还是文件
        is_folder = os.path.isdir(path)

        # 如果类型不匹配当前选择，更新单选按钮状态
        if is_folder != self.folder_radio.isChecked():
            if is_folder:
                self.folder_radio.setChecked(True)
            else:
                self.file_radio.setChecked(True)

        # 更新图层图像源
        self.current_layer.image_source = path
        self.current_layer.is_folder = is_folder

        if is_folder:
            # 文件夹处理
            self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
            self.current_image_label.setText("当前图像: 无")
            # 启用随机按钮
            self.random_btn.setEnabled(True)
        else:
            # 文件处理
            self.current_layer.current_image_path = path  # 🔧 修复：使用公共属性
            if os.path.isfile(path):
                self.current_image_label.setText(f"当前图像: {os.path.basename(path)}")
            else:
                self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                self.current_image_label.setText("当前图像: 无")
            # 禁用随机按钮
            self.random_btn.setEnabled(False)

        # 清除缓存图像
        self.current_layer.cached_image = None

        # 清除快速渲染器缓存（关键修复）
        self.document._invalidate_render_cache()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改图层图像源")

    def open_binding_manager(self):
        """打开绑定管理器"""
        if not self.document:
            return

        # 确保文档有绑定管理器（兼容性检查）
        if not hasattr(self.document, 'binding_manager'):
            try:
                from app.models.binding_manager import LayerBindingManager
                self.document.binding_manager = LayerBindingManager()
                safe_print("为文档初始化绑定管理器")
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "错误", f"无法初始化绑定管理器: {str(e)}")
                return

        try:
            from app.ui.binding_manager_dialog import LayerBindingManagerDialog
            dialog = LayerBindingManagerDialog(self.document, self)
            result = dialog.exec()

            # 刷新当前图层的绑定状态显示
            if self.current_layer:
                self.update_bind_status()

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开绑定管理器时出错: {str(e)}")

    def open_size_match_manager(self):
        """打开图层大小匹配管理器"""
        if not self.document:
            return
        try:
            from app.ui.layer_size_match_dialog import LayerSizeMatchDialog
            dialog = LayerSizeMatchDialog(self.document, self)
            dialog.exec()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开图层大小匹配管理器时出错: {str(e)}")

    def update_bind_status(self):
        """更新绑定状态显示"""
        if not self.current_layer or not self.document:
            return

        try:
            binding_info = self.document.binding_manager.get_layer_binding_info(self.current_layer)
            if binding_info:
                group_id, group_name = binding_info
                self.bind_status_label.setText(f"已绑定到: {group_name}")
                self.bind_status_label.setStyleSheet("color: #2F9CF4; font-weight: bold; font-size: 9pt;")
            else:
                self.bind_status_label.setText("未绑定")
                self.bind_status_label.setStyleSheet("color: #606064; font-size: 9pt;")
        except Exception as e:
            safe_print(f"更新绑定状态时出错: {e}")
            self.bind_status_label.setText("未绑定")
            self.bind_status_label.setStyleSheet("color: #606064; font-size: 9pt;")

    def update_layer_rotation(self, rotation):
        """更新图层旋转角度"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新图层旋转角度: {rotation}°")

        # 更新图层属性
        self.current_layer.rotation = rotation

        # 高频旋转输入采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["rotation"], reason="rotation")
        self._save_state_deferred("旋转图层")

    def update_layer_flip_horizontal(self, flip):
        """更新图层水平翻转"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新图层水平翻转: {flip}")

        # 保存状态
        self.document.save_state("水平翻转图层前")

        # 更新图层属性
        self.current_layer.flip_horizontal = flip

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("水平翻转图层")

    def update_layer_flip_vertical(self, flip):
        """更新图层垂直翻转"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新图层垂直翻转: {flip}")

        # 保存状态
        self.document.save_state("垂直翻转图层前")

        # 更新图层属性
        self.current_layer.flip_vertical = flip

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("垂直翻转图层")

    def reset_layer_transforms(self):
        """重置图层所有变换"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print("重置图层所有变换")

        # 保存状态
        self.document.save_state("重置变换前")

        # 重置图层变换
        self.current_layer.reset_transformations()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("重置变换")

    # 随机变换相关方法
    def update_random_position_enabled(self, enabled):
        """更新随机位置抖动启用状态"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机位置抖动启用状态: {enabled}")

        # 保存状态
        self.document.save_state("更改随机位置抖动设置前")

        # 更新图层属性
        self.current_layer.random_position_enabled = enabled

        # 如果启用了随机位置但还没有生成随机参数，自动生成
        if enabled:
            if hasattr(self.current_layer, 'generate_random_transform_params'):
                self.current_layer.generate_random_transform_params()
                safe_print("自动生成随机变换参数")

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("更改随机位置抖动设置")

    def update_random_position_range(self, range_value):
        """更新随机位置抖动范围"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机位置抖动范围: {range_value}")

        # 更新图层属性
        self.current_layer.random_position_range = range_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_position_range"], reason="random_position_range")
        self._save_state_deferred("更改随机位置抖动范围")

    def update_random_scale_enabled(self, enabled):
        """更新随机缩放启用状态"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机缩放启用状态: {enabled}")

        # 保存状态
        self.document.save_state("更改随机缩放设置前")

        # 更新图层属性
        self.current_layer.random_scale_enabled = enabled

        # 如果启用了随机缩放但还没有生成随机参数，自动生成
        if enabled:
            if hasattr(self.current_layer, 'generate_random_transform_params'):
                self.current_layer.generate_random_transform_params()
                safe_print("自动生成随机变换参数")

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("更改随机缩放设置")

    def update_random_scale_min(self, min_value):
        """更新最小随机缩放比例"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新最小随机缩放比例: {min_value}")

        # 更新图层属性
        self.current_layer.random_scale_min = min_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_scale_min"], reason="random_scale_min")
        self._save_state_deferred("更改最小随机缩放比例")

    def update_random_scale_max(self, max_value):
        """更新最大随机缩放比例"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新最大随机缩放比例: {max_value}")

        # 更新图层属性
        self.current_layer.random_scale_max = max_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_scale_max"], reason="random_scale_max")
        self._save_state_deferred("更改最大随机缩放比例")

    def update_random_rotation_enabled(self, enabled):
        """更新随机旋转启用状态"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机旋转启用状态: {enabled}")

        # 保存状态
        self.document.save_state("更改随机旋转设置前")

        # 更新图层属性
        self.current_layer.random_rotation_enabled = enabled

        # 如果启用了随机旋转但还没有生成随机参数，自动生成
        if enabled:
            if hasattr(self.current_layer, 'generate_random_transform_params'):
                self.current_layer.generate_random_transform_params()
                safe_print("自动生成随机变换参数")

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("更改随机旋转设置")

    def update_random_rotation_range(self, range_value):
        """更新随机旋转角度范围"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机旋转角度范围: {range_value}")

        # 更新图层属性
        self.current_layer.random_rotation_range = range_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_rotation_range"], reason="random_rotation_range")
        self._save_state_deferred("更改随机旋转角度范围")

    def generate_random_params(self):
        """为当前图层生成新的随机变换参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"为图层 '{self.current_layer.name}' 生成新的随机变换参数")

        # 保存状态
        self.document.save_state("生成随机变换参数前")

        # 生成随机参数
        if hasattr(self.current_layer, 'generate_random_transform_params'):
            self.current_layer.generate_random_transform_params()

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("生成随机变换参数")

    def reset_random_params(self):
        """重置当前图层的随机变换参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"重置图层 '{self.current_layer.name}' 的随机变换参数")

        # 保存状态
        self.document.save_state("重置随机变换参数前")

        # 重置随机参数
        if hasattr(self.current_layer, 'reset_random_transforms'):
            self.current_layer.reset_random_transforms()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("重置随机变换参数")

