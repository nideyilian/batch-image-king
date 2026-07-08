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


class LayerPropertiesAttr(object):
    """Mixin for layer_properties_attr (split from LayerPropertiesPanel)."""

    def update_layer_name(self, name):
        """更新图层名称"""
        if not self.current_layer:
            return

        safe_print(f"更新图层名称: {name}")  # 调试信息

        # 保存当前状态
        self.document.save_state("修改图层名称前")

        # 更新图层名称
        self.current_layer.name = name

        # 通知文档已更改
        self._emit_document_change(
            throttled=False,
            include_layer_changed=True,
            fields=["name"],
            reason="name"
        )

        # 保存更改后的状态
        self.document.save_state("修改图层名称")

    def update_layer_position(self):
        """更新图层位置"""
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            changed = self._apply_to_selected_layers(
                {"x": self.x_spin.value(), "y": self.y_spin.value()},
                "批量移动图层",
                fields=["position"],
                allow_locked=False,
                clear_cache=False,
            )
            if changed:
                safe_print(f"批量更新图层位置: {changed} 个图层")
            return
        if self.current_layer.locked:
            return

        safe_print(f"更新图层位置: X={self.x_spin.value()}, Y={self.y_spin.value()}")  # 调试信息

        # 更新图层位置
        self.current_layer.x = self.x_spin.value()
        self.current_layer.y = self.y_spin.value()

        # 高频输入采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["position"], reason="position")
        self._save_state_deferred("移动图层")

    def update_layer_size(self):
        """更新图层尺寸"""
        if not self.current_layer or self._updating_size:
            return
        if self._is_multi_layer_edit():
            changed = self._apply_to_selected_layers(
                {"width": self.width_spin.value(), "height": self.height_spin.value()},
                "批量调整图层尺寸",
                fields=["size"],
                allow_locked=False,
                clear_cache=True,
            )
            if changed:
                safe_print(f"批量更新图层尺寸: {changed} 个图层")
            return
        if self.current_layer.locked:
            return

        # 防止递归更新
        self._updating_size = True

        try:
            new_width = self.width_spin.value()
            new_height = self.height_spin.value()

            safe_print(f"更新图层尺寸: 宽={new_width}, 高={new_height}")  # 调试信息

            # 如果启用了锁定比例，需要判断哪个尺寸发生了变化
            if self.aspect_ratio_locked:
                current_width = self.current_layer.width
                current_height = self.current_layer.height

                # 判断是宽度还是高度发生了变化
                width_changed = new_width != current_width
                height_changed = new_height != current_height

                if width_changed and not height_changed:
                    # 宽度改变，计算新高度
                    calculated_height = self.calculate_locked_size('width', new_width)
                    if calculated_height is not None:
                        new_height = calculated_height
                        # 使用 blockSignals 避免触发信号
                        self.height_spin.blockSignals(True)
                        self.height_spin.setValue(new_height)
                        self.height_spin.blockSignals(False)
                        safe_print(f"锁定比例: 宽度改变为{new_width}，自动调整高度为{new_height}")

                elif height_changed and not width_changed:
                    # 高度改变，计算新宽度
                    calculated_width = self.calculate_locked_size('height', new_height)
                    if calculated_width is not None:
                        new_width = calculated_width
                        # 使用 blockSignals 避免触发信号
                        self.width_spin.blockSignals(True)
                        self.width_spin.setValue(new_width)
                        self.width_spin.blockSignals(False)
                        safe_print(f"锁定比例: 高度改变为{new_height}，自动调整宽度为{new_width}")

                elif width_changed and height_changed:
                    # 两个都改变了，优先使用宽度的变化
                    calculated_height = self.calculate_locked_size('width', new_width)
                    if calculated_height is not None:
                        new_height = calculated_height
                        # 使用 blockSignals 避免触发信号
                        self.height_spin.blockSignals(True)
                        self.height_spin.setValue(new_height)
                        self.height_spin.blockSignals(False)
                        safe_print(f"锁定比例: 两个尺寸都改变，以宽度为准，调整高度为{new_height}")

            # 更新图层尺寸
            self.current_layer.width = new_width
            self.current_layer.height = new_height

            # 清除缓存图像以强制重新加载
            self.current_layer.cached_image = None

            # 高频输入采用节流刷新与延迟历史保存
            self._emit_document_change(throttled=True, fields=["size"], reason="size")
            self._save_state_deferred("调整图层尺寸")

        finally:
            self._updating_size = False

    def update_use_original_size(self, use_original):
        """更新是否使用智能裁剪"""
        if not self.current_layer:
            return

        safe_print(f"更新智能裁剪状态: {use_original}")

        # 保存当前状态用于撤销
        self.document.save_state("更改智能裁剪设置前")

        # 记录当前图层尺寸
        width = self.current_layer.width
        height = self.current_layer.height
        safe_print(f"图层当前尺寸: {width}x{height}")

        # 更新图层的智能裁剪设置
        self.current_layer.use_original_size = use_original

        # 清除缓存图像，强制重新加载和处理
        self.current_layer.cached_image = None

        # 立即更新图层图像，这会触发智能裁剪过程
        if self.current_layer.image_source:
            safe_print(f"正在应用智能裁剪")
            self.current_layer.get_random_image()

        # 确保尺寸控件始终可用，智能裁剪只影响图像处理方式，不影响UI控件状态
        enabled = not self.current_layer.locked
        self.width_spin.setEnabled(enabled)
        self.height_spin.setEnabled(enabled)

        # 通知文档内容已更改，触发重绘
        self.document.document_changed.emit()

        # 保存修改后的状态
        self.document.save_state("更改智能裁剪设置后")

    def update_fit_mode(self, mode):
        """更新图像适配模式"""
        if not self.current_layer:
            return

        safe_print(f"更新适配模式: {mode}")  # 调试信息

        # 保存当前状态
        self.document.save_state("更改适配模式前")

        # 更新适配模式
        self.current_layer.fit_mode = mode

        # 更新裁剪方向控件的启用状态
        from app.models.document import Layer
        self.crop_direction_combo.setEnabled(mode == Layer.FIT_SMART_CROP)

        # 清除缓存图像以强制重新加载
        self.current_layer.cached_image = None

        # 立即重新加载和处理图像
        if self.current_layer.image_source:
            safe_print(f"正在应用新的适配模式")
            self.current_layer.get_random_image()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改适配模式")

    def update_crop_direction(self, direction):
        """更新裁剪方向"""
        if not self.current_layer:
            return

        safe_print(f"更新裁剪方向: {direction}")  # 调试信息

        # 保存当前状态
        self.document.save_state("更改裁剪方向前")

        # 更新裁剪方向
        self.current_layer.crop_direction = direction

        # 清除缓存图像以强制重新加载
        self.current_layer.cached_image = None

        # 立即重新加载和处理图像
        if self.current_layer.image_source:
            safe_print(f"正在应用新的裁剪方向")
            self.current_layer.get_random_image()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改裁剪方向")

    def update_layer_opacity(self, opacity):
        """更新图层透明度"""
        if not self.current_layer:
            return

        safe_print(f"更新透明度: {opacity}%")  # 调试信息
        if self._is_multi_layer_edit():
            changed = self._apply_to_selected_layers(
                {"opacity": opacity / 100.0},
                "批量修改图层透明度",
                fields=["opacity"],
                allow_locked=False,
                clear_cache=False,
            )
            self.opacity_label.setText(f"{opacity}%")
            if changed:
                safe_print(f"批量更新透明度: {changed} 个图层")
            return

        # 更新图层透明度
        self.current_layer.opacity = opacity / 100.0
        self.opacity_label.setText(f"{opacity}%")

        # 滑块调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["opacity"], reason="opacity")
        self._save_state_deferred("修改图层透明度")

    def update_layer_visibility(self, visible):
        """更新图层可见性"""
        if not self.current_layer:
            return

        safe_print(f"更新可见性: {visible}")  # 调试信息

        if self._is_multi_layer_edit():
            self.document.save_state("批量切换图层可见性前")
            changed = self._apply_to_selected_layers(
                {"visible": visible},
                "批量切换图层可见性",
                fields=["visibility"],
                allow_locked=True,
                clear_cache=False,
            )
            return

        # 保存当前状态
        self.document.save_state("切换图层可见性前")

        # 更新图层可见性
        self.current_layer.visible = visible

        # 通知文档已更改
        self._emit_document_change(
            throttled=False,
            fields=["visibility"],
            reason="visibility"
        )

        # 保存更改后的状态
        self.document.save_state("切换图层可见性")

    def update_layer_lock(self, locked):
        """更新图层锁定状态"""
        if not self.current_layer:
            return

        safe_print(f"更新锁定状态: {locked}")  # 调试信息

        if is_layer_group(self.current_layer):
            self.document.save_state("切换图层组锁定状态前")
            self.current_layer.locked = locked
            self._emit_document_change(
                throttled=False,
                fields=["lock"],
                reason="lock"
            )
            self.document.save_state("切换图层组锁定状态")
            self._update_group_panel(self.current_layer)
            return

        if self._is_multi_layer_edit():
            self.document.save_state("批量切换图层锁定状态前")
            changed = self._apply_to_selected_layers(
                {"locked": locked},
                "批量切换图层锁定状态",
                fields=["lock"],
                allow_locked=True,
                clear_cache=False,
            )
            self.x_spin.setEnabled(not locked)
            self.y_spin.setEnabled(not locked)
            self.width_spin.setEnabled(not locked)
            self.height_spin.setEnabled(not locked)
            return

        # 保存当前状态
        self.document.save_state("切换图层锁定状态前")

        # 更新图层锁定状态
        self.current_layer.locked = locked

        # 调整位置和尺寸控件的启用状态
        self.x_spin.setEnabled(not locked)
        self.y_spin.setEnabled(not locked)

        # 尺寸控件始终可用，除非图层被锁定
        self.width_spin.setEnabled(not locked)
        self.height_spin.setEnabled(not locked)

        # 通知文档已更改
        self._emit_document_change(
            throttled=False,
            fields=["lock"],
            reason="lock"
        )

        # 保存更改后的状态
        self.document.save_state("切换图层锁定状态")

