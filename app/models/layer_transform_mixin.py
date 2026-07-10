#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
"""Layer 子 mixin 3: 变换属性 + 变换操作 + 随机变换 + 图像变换渲染

从原 layer_new.py 拆分。涵盖：
- rotation / flip_horizontal / flip_vertical / aspect_ratio_locked 属性
- 通用操作方法（委托给 self._operations）：get_clone_positions, reset_transformations,
  apply_rotation_preset, get_effective_position, get_effective_clone_positions
- 随机变换相关：random_position_enabled/range, random_scale_enabled/min/max,
  random_rotation_enabled/range + 内部状态 _current_random_offset_x/y/_scale/_rotation
- generate_random_transform_params / reset_random_transforms
- _apply_transformations（应用旋转+翻转到图像）
"""

import os

from PIL.Image import Resampling, Transpose

# 模块级 verbose flag（与原文件保持一致；与 layer_attrs_mixin/layer_rendering_mixin 共享）
_LAYER_RENDER_VERBOSE = os.environ.get("BTPW_LAYER_RENDER_VERBOSE", "0") == "1"


class LayerTransformMixin:
    """变换属性 + 变换操作 + 随机变换 + 图像变换渲染（拆分自 Layer）。"""

    # ==================== 变换属性 ====================
    @property
    def rotation(self):
        """旋转角度（度）"""
        return self._property_manager.get_property('rotation')

    @rotation.setter
    def rotation(self, value):
        # 角度标准化到 0-360 范围
        normalized_value = float(value) % 360
        if abs(self.rotation - normalized_value) > 0.001:  # 避免浮点数精度问题
            self._property_manager.set_property('rotation', normalized_value)
            self._cached_image = None  # 清除缓存，强制重新渲染

    @property
    def flip_horizontal(self):
        """水平翻转"""
        return self._property_manager.get_property('flip_horizontal')

    @flip_horizontal.setter
    def flip_horizontal(self, value):
        if self.flip_horizontal != value:
            self._property_manager.set_property('flip_horizontal', value)
            self._cached_image = None  # 清除缓存，强制重新渲染

    @property
    def flip_vertical(self):
        """垂直翻转"""
        return self._property_manager.get_property('flip_vertical')

    @flip_vertical.setter
    def flip_vertical(self, value):
        if self.flip_vertical != value:
            self._property_manager.set_property('flip_vertical', value)
            self._cached_image = None  # 清除缓存，强制重新渲染

    @property
    def aspect_ratio_locked(self):
        """是否锁定宽高比"""
        return self._property_manager.get_property('aspect_ratio_locked')

    @aspect_ratio_locked.setter
    def aspect_ratio_locked(self, value):
        self._property_manager.set_property('aspect_ratio_locked', value)

    # ==================== 通用操作方法（委托给 self._operations）====================
    def get_clone_positions(self):
        """获取图层所有分身的位置"""
        return self._operations.get_clone_positions()

    def reset_transformations(self):
        """重置所有变换"""
        self._operations.reset_transformations()
        print("重置所有变换")

    def apply_rotation_preset(self, preset):
        """应用旋转预设"""
        self._operations.apply_rotation_preset(preset)

    def get_effective_position(self):
        """获取应用随机偏移后的有效位置"""
        return self._operations.get_effective_position()

    def get_effective_clone_positions(self):
        """获取应用随机偏移后的所有分身位置"""
        if not self.clone_enabled or self.clone_rows <= 0 or self.clone_columns <= 0:
            return [self.get_effective_position()]

        positions = []
        base_x, base_y = self.get_effective_position()

        # 获取实际使用的宽高（考虑自定义大小）
        clone_width = self.width
        clone_height = self.height
        if self.clone_custom_size_enabled:
            if self.clone_custom_width > 0:
                clone_width = self.clone_custom_width
            if self.clone_custom_height > 0:
                clone_height = self.clone_custom_height

        for row in range(self.clone_rows):
            for col in range(self.clone_columns):
                pos_x = base_x + col * (clone_width + self.clone_column_spacing)
                pos_y = base_y + row * (clone_height + self.clone_row_spacing)
                positions.append((pos_x, pos_y))

        return positions

    # ==================== 随机变换属性 ====================
    @property
    def random_position_enabled(self):
        return self._random_position_enabled

    @random_position_enabled.setter
    def random_position_enabled(self, value):
        value = bool(value)
        if self._random_position_enabled != value:
            self._random_position_enabled = value
            self.changed.emit()

    @property
    def random_position_range(self):
        return self._random_position_range

    @random_position_range.setter
    def random_position_range(self, value):
        value = max(0, int(value))
        if self._random_position_range != value:
            self._random_position_range = value
            self.changed.emit()

    @property
    def random_scale_enabled(self):
        return self._random_scale_enabled

    @random_scale_enabled.setter
    def random_scale_enabled(self, value):
        value = bool(value)
        if self._random_scale_enabled != value:
            self._random_scale_enabled = value
            self.changed.emit()

    @property
    def random_scale_min(self):
        return self._random_scale_min

    @random_scale_min.setter
    def random_scale_min(self, value):
        value = float(value)
        if abs(self._random_scale_min - value) > 1e-6:
            self._random_scale_min = value
            if self._random_scale_max < self._random_scale_min:
                self._random_scale_max = self._random_scale_min
            self.changed.emit()

    @property
    def random_scale_max(self):
        return self._random_scale_max

    @random_scale_max.setter
    def random_scale_max(self, value):
        value = float(value)
        if abs(self._random_scale_max - value) > 1e-6:
            self._random_scale_max = value
            if self._random_scale_min > self._random_scale_max:
                self._random_scale_min = self._random_scale_max
            self.changed.emit()

    @property
    def random_rotation_enabled(self):
        return self._random_rotation_enabled

    @random_rotation_enabled.setter
    def random_rotation_enabled(self, value):
        value = bool(value)
        if self._random_rotation_enabled != value:
            self._random_rotation_enabled = value
            self.changed.emit()

    @property
    def random_rotation_range(self):
        return self._random_rotation_range

    @random_rotation_range.setter
    def random_rotation_range(self, value):
        value = max(0.0, min(180.0, float(value)))
        if abs(self._random_rotation_range - value) > 1e-6:
            self._random_rotation_range = value
            self.changed.emit()

    def generate_random_transform_params(self):
        """生成新的随机变换参数（与 Legacy Layer 保持一致）。"""
        import random

        if self._random_position_enabled:
            self._current_random_offset_x = random.randint(-self._random_position_range, self._random_position_range)
            self._current_random_offset_y = random.randint(-self._random_position_range, self._random_position_range)
        else:
            self._current_random_offset_x = 0
            self._current_random_offset_y = 0

        if self._random_scale_enabled:
            min_scale = min(self._random_scale_min, self._random_scale_max)
            max_scale = max(self._random_scale_min, self._random_scale_max)
            self._current_random_scale = random.uniform(min_scale, max_scale)
        else:
            self._current_random_scale = 1.0

        if self._random_rotation_enabled:
            self._current_random_rotation = random.uniform(-self._random_rotation_range, self._random_rotation_range)
        else:
            self._current_random_rotation = 0.0

        self.changed.emit()

    def reset_random_transforms(self):
        """重置所有随机变换到初始状态"""
        self._current_random_offset_x = 0
        self._current_random_offset_y = 0
        self._current_random_scale = 1.0
        self._current_random_rotation = 0.0
        print(f"图层 '{self.name}' 随机变换已重置")
        self.changed.emit()

    def _apply_transformations(self, image):
        """应用图像变换（旋转和翻转）"""
        if image is None:
            return None

        result = image

        # 应用翻转
        if self.flip_horizontal:
            result = result.transpose(Transpose.FLIP_LEFT_RIGHT)
            if _LAYER_RENDER_VERBOSE:
                print("应用水平翻转")

        if self.flip_vertical:
            result = result.transpose(Transpose.FLIP_TOP_BOTTOM)
            if _LAYER_RENDER_VERBOSE:
                print("应用垂直翻转")

        # 应用旋转
        if abs(self.rotation) > 0.001:
            result = self._rotate_rgba_premultiplied(
                result,
                -self.rotation,
                Resampling.BICUBIC,
                (0, 0, 0, 0)
            )
            if _LAYER_RENDER_VERBOSE:
                print(f"应用旋转: {self.rotation}度")

        return result
