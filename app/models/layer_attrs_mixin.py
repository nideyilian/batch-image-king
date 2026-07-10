#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
"""Layer 子 mixin 2: 所有 @property getter/setter（基础属性 + 克隆 + 描边 + 圆角 + 形状 + 绑定 + 渐变）

从原 layer_new.py 拆分。涵盖：
- 基础属性：name, x, y, width, height, visible, opacity, locked, image_source, is_folder, use_original_size,
            fit_mode, crop_direction, blend_mode
- 克隆属性：clone_enabled, clone_rows, clone_columns, clone_row_spacing, clone_column_spacing,
            clone_mirror_mode, clone_fill_enabled, clone_fill_mode, clone_fill_spacing, clone_fill_margin,
            clone_fill_angle, clone_custom_size_enabled, clone_custom_width, clone_custom_height
- 描边属性：stroke_enabled, stroke_width, stroke_color, stroke_type, stroke_join, stroke_cap,
            stroke_dash_length, stroke_dash_gap
- 圆角属性：corner_radius
- 形状属性：shape_type, trapezoid_top_width, trapezoid_bottom_width, trapezoid_slope_side,
            polygon_rotation, polygon_corner_radius
- 绑定属性：bind_enabled, bind_group, bind_strategy

⚠️ 不含 vector_path_*（拆分到 layer_vector_mixin.py）
⚠️ 不含 rotation/flip/aspect_ratio（拆分到 layer_transform_mixin.py）
"""

import os

# 模块级 verbose flag（与原文件保持一致）
_LAYER_RENDER_VERBOSE = os.environ.get("BTPW_LAYER_RENDER_VERBOSE", "0") == "1"


class LayerAttrsMixin:
    """所有 @property getter/setter（拆分自 Layer）。"""

    # ==================== 基础属性 ====================
    @property
    def name(self):
        result = self._property_manager.get_property('name')
        return result

    @name.setter
    def name(self, value):
        self._property_manager.set_property('name', value)

    @property
    def x(self):
        return self._property_manager.get_property('x')

    @x.setter
    def x(self, value):
        self._property_manager.set_property('x', value)

    @property
    def y(self):
        return self._property_manager.get_property('y')

    @y.setter
    def y(self, value):
        self._property_manager.set_property('y', value)

    @property
    def width(self):
        return self._property_manager.get_property('width')

    @width.setter
    def width(self, value):
        if value > 0:
            self._property_manager.set_property('width', value)

    @property
    def height(self):
        return self._property_manager.get_property('height')

    @height.setter
    def height(self, value):
        if value > 0:
            self._property_manager.set_property('height', value)

    @property
    def visible(self):
        return self._property_manager.get_property('visible')

    @visible.setter
    def visible(self, value):
        self._property_manager.set_property('visible', value)

    @property
    def opacity(self):
        return self._property_manager.get_property('opacity')

    @opacity.setter
    def opacity(self, value):
        self._property_manager.set_property('opacity', value)

    @property
    def locked(self):
        return self._property_manager.get_property('locked')

    @locked.setter
    def locked(self, value):
        self._property_manager.set_property('locked', value)

    @property
    def image_source(self):
        return self._property_manager.get_property('image_source')

    @image_source.setter
    def image_source(self, value):
        self._property_manager.set_property('image_source', value)

    @property
    def is_folder(self):
        return self._property_manager.get_property('is_folder')

    @is_folder.setter
    def is_folder(self, value):
        self._property_manager.set_property('is_folder', value)

    @property
    def use_original_size(self):
        return self._property_manager.get_property('use_original_size')

    @use_original_size.setter
    def use_original_size(self, value):
        self._property_manager.set_property('use_original_size', value)

    @property
    def fit_mode(self):
        return self._property_manager.get_property('fit_mode')

    @fit_mode.setter
    def fit_mode(self, value):
        self._property_manager.set_property('fit_mode', value)

    @property
    def crop_direction(self):
        return self._property_manager.get_property('crop_direction')

    @crop_direction.setter
    def crop_direction(self, value):
        self._property_manager.set_property('crop_direction', value)

    @property
    def blend_mode(self):
        return self._property_manager.get_property('blend_mode')

    @blend_mode.setter
    def blend_mode(self, value):
        self._property_manager.set_property('blend_mode', value)

    # ==================== 克隆属性 ====================
    @property
    def clone_enabled(self):
        return self._property_manager.get_property('clone_enabled')

    @clone_enabled.setter
    def clone_enabled(self, value):
        self._property_manager.set_property('clone_enabled', value)

    @property
    def clone_rows(self):
        return self._property_manager.get_property('clone_rows')

    @clone_rows.setter
    def clone_rows(self, value):
        if value > 0:
            self._property_manager.set_property('clone_rows', value)

    @property
    def clone_columns(self):
        return self._property_manager.get_property('clone_columns')

    @clone_columns.setter
    def clone_columns(self, value):
        if value > 0:
            self._property_manager.set_property('clone_columns', value)

    @property
    def clone_row_spacing(self):
        return self._property_manager.get_property('clone_row_spacing')

    @clone_row_spacing.setter
    def clone_row_spacing(self, value):
        if value >= 0:
            self._property_manager.set_property('clone_row_spacing', value)

    @property
    def clone_column_spacing(self):
        return self._property_manager.get_property('clone_column_spacing')

    @clone_column_spacing.setter
    def clone_column_spacing(self, value):
        self._property_manager.set_property('clone_column_spacing', max(0, value))

    @property
    def clone_mirror_mode(self):
        return self._property_manager.get_property('clone_mirror_mode')

    @clone_mirror_mode.setter
    def clone_mirror_mode(self, value):
        self._property_manager.set_property('clone_mirror_mode', value)

    @property
    def clone_fill_enabled(self):
        return self._property_manager.get_property('clone_fill_enabled')

    @clone_fill_enabled.setter
    def clone_fill_enabled(self, value):
        self._property_manager.set_property('clone_fill_enabled', value)
        self._cached_image = None
        self._cache_valid = False

    @property
    def clone_fill_mode(self):
        return self._property_manager.get_property('clone_fill_mode')

    @clone_fill_mode.setter
    def clone_fill_mode(self, value):
        self._property_manager.set_property('clone_fill_mode', value)
        self._cached_image = None
        self._cache_valid = False

    @property
    def clone_fill_spacing(self):
        return self._property_manager.get_property('clone_fill_spacing')

    @clone_fill_spacing.setter
    def clone_fill_spacing(self, value):
        self._property_manager.set_property('clone_fill_spacing', value)
        self._cached_image = None
        self._cache_valid = False

    @property
    def clone_fill_margin(self):
        return self._property_manager.get_property('clone_fill_margin')

    @clone_fill_margin.setter
    def clone_fill_margin(self, value):
        self._property_manager.set_property('clone_fill_margin', value)
        self._cached_image = None
        self._cache_valid = False

    @property
    def clone_fill_angle(self):
        return self._property_manager.get_property('clone_fill_angle')

    @clone_fill_angle.setter
    def clone_fill_angle(self, value):
        self._property_manager.set_property('clone_fill_angle', value)
        self._cached_image = None
        self._cache_valid = False

    @property
    def clone_custom_size_enabled(self):
        return self._property_manager.get_property('clone_custom_size_enabled')

    @clone_custom_size_enabled.setter
    def clone_custom_size_enabled(self, value):
        self._property_manager.set_property('clone_custom_size_enabled', value)
        self._cached_image = None
        self._cache_valid = False

    @property
    def clone_custom_width(self):
        return self._property_manager.get_property('clone_custom_width')

    @clone_custom_width.setter
    def clone_custom_width(self, value):
        if value >= 0:
            self._property_manager.set_property('clone_custom_width', value)
            self._cached_image = None
            self._cache_valid = False

    @property
    def clone_custom_height(self):
        return self._property_manager.get_property('clone_custom_height')

    @clone_custom_height.setter
    def clone_custom_height(self, value):
        if value >= 0:
            self._property_manager.set_property('clone_custom_height', value)
            self._cached_image = None
            self._cache_valid = False

    # ==================== 圆角属性 ====================
    @property
    def corner_radius(self):
        return self._property_manager.get_property('corner_radius')

    @corner_radius.setter
    def corner_radius(self, value):
        self._property_manager.set_property('corner_radius', max(0, value))

    # ==================== 描边属性 ====================
    @property
    def stroke_enabled(self):
        return self._property_manager.get_property('stroke_enabled')

    @stroke_enabled.setter
    def stroke_enabled(self, value):
        self._property_manager.set_property('stroke_enabled', value)
        if _LAYER_RENDER_VERBOSE:
            print(f"[图层] 描边状态改变为: {value}，已清除缓存")

    @property
    def stroke_width(self):
        return self._property_manager.get_property('stroke_width')

    @stroke_width.setter
    def stroke_width(self, value):
        self._property_manager.set_property('stroke_width', max(1, value))

    @property
    def stroke_color(self):
        return self._property_manager.get_property('stroke_color')

    @stroke_color.setter
    def stroke_color(self, value):
        if isinstance(value, (tuple, list)) and len(value) >= 3:
            r = max(0, min(255, int(value[0])))
            g = max(0, min(255, int(value[1])))
            b = max(0, min(255, int(value[2])))
            a = max(0, min(255, int(value[3]))) if len(value) > 3 else 255
            self._property_manager.set_property('stroke_color', (r, g, b, a))

    @property
    def stroke_type(self):
        return self._property_manager.get_property('stroke_type')

    @stroke_type.setter
    def stroke_type(self, value):
        self._property_manager.set_property('stroke_type', max(0, min(2, int(value))))

    @property
    def stroke_join(self):
        return self._property_manager.get_property('stroke_join')

    @stroke_join.setter
    def stroke_join(self, value):
        allowed = {"miter", "round", "bevel"}
        normalized = value if value in allowed else "miter"
        self._property_manager.set_property('stroke_join', normalized)
        self._cached_image = None
        self._cache_valid = False

    @property
    def stroke_cap(self):
        return self._property_manager.get_property('stroke_cap')

    @stroke_cap.setter
    def stroke_cap(self, value):
        allowed = {"butt", "round", "square"}
        normalized = value if value in allowed else "butt"
        self._property_manager.set_property('stroke_cap', normalized)
        self._cached_image = None
        self._cache_valid = False

    @property
    def stroke_dash_length(self):
        return self._property_manager.get_property('stroke_dash_length')

    @stroke_dash_length.setter
    def stroke_dash_length(self, value):
        self._property_manager.set_property('stroke_dash_length', max(0, int(value)))
        self._cached_image = None
        self._cache_valid = False

    @property
    def stroke_dash_gap(self):
        return self._property_manager.get_property('stroke_dash_gap')

    @stroke_dash_gap.setter
    def stroke_dash_gap(self, value):
        self._property_manager.set_property('stroke_dash_gap', max(0, int(value)))
        self._cached_image = None
        self._cache_valid = False

    # ==================== 颜色叠加属性 ====================
    @property
    def color_overlay_enabled(self):
        return self._property_manager.get_property('color_overlay_enabled')

    @color_overlay_enabled.setter
    def color_overlay_enabled(self, value):
        self._property_manager.set_property('color_overlay_enabled', value)
        self._cached_image = None

    @property
    def color_overlay_color(self):
        return self._property_manager.get_property('color_overlay_color')

    @color_overlay_color.setter
    def color_overlay_color(self, value):
        self._property_manager.set_property('color_overlay_color', value)
        self._cached_image = None

    @property
    def color_overlay_opacity(self):
        return self._property_manager.get_property('color_overlay_opacity')

    @color_overlay_opacity.setter
    def color_overlay_opacity(self, value):
        self._property_manager.set_property('color_overlay_opacity', max(0.0, min(1.0, float(value))))
        self._cached_image = None

    # ==================== 渐变叠加属性 ====================
    @property
    def gradient_overlay_enabled(self):
        return self._property_manager.get_property('gradient_overlay_enabled')

    @gradient_overlay_enabled.setter
    def gradient_overlay_enabled(self, value):
        self._property_manager.set_property('gradient_overlay_enabled', value)
        self._cached_image = None

    @property
    def gradient_overlay_colors(self):
        return self._property_manager.get_property('gradient_overlay_colors')

    @gradient_overlay_colors.setter
    def gradient_overlay_colors(self, value):
        self._property_manager.set_property('gradient_overlay_colors', value)
        self._cached_image = None

    @property
    def gradient_overlay_angle(self):
        return self._property_manager.get_property('gradient_overlay_angle')

    @gradient_overlay_angle.setter
    def gradient_overlay_angle(self, value):
        self._property_manager.set_property('gradient_overlay_angle', float(value) % 360)
        self._cached_image = None

    @property
    def gradient_overlay_opacity(self):
        return self._property_manager.get_property('gradient_overlay_opacity')

    @gradient_overlay_opacity.setter
    def gradient_overlay_opacity(self, value):
        self._property_manager.set_property('gradient_overlay_opacity', max(0.0, min(1.0, float(value))))
        self._cached_image = None

    # ==================== 绑定属性 ====================
    @property
    def bind_enabled(self):
        return self._property_manager.get_property('bind_enabled')

    @bind_enabled.setter
    def bind_enabled(self, value):
        self._property_manager.set_property('bind_enabled', value)

    @property
    def bind_group(self):
        return self._property_manager.get_property('bind_group')

    @bind_group.setter
    def bind_group(self, value):
        self._property_manager.set_property('bind_group', value)

    @property
    def bind_strategy(self):
        return self._property_manager.get_property('bind_strategy')

    @bind_strategy.setter
    def bind_strategy(self, value):
        if value in ["filename", "folder"]:
            self._property_manager.set_property('bind_strategy', value)

    # ==================== 形状属性 ====================
    @property
    def shape_type(self):
        """获取形状类型"""
        return self._property_manager.get_property('shape_type')

    @shape_type.setter
    def shape_type(self, value):
        """设置形状类型"""
        self._property_manager.set_property('shape_type', value)
        self._cached_image = None
        if hasattr(self, '_shape_mask_cache'):
            self._shape_mask_cache.clear()

    @property
    def trapezoid_top_width(self):
        """获取梯形上底宽度"""
        return self._property_manager.get_property('trapezoid_top_width')

    @trapezoid_top_width.setter
    def trapezoid_top_width(self, value):
        """设置梯形上底宽度"""
        if value > 0:
            self._property_manager.set_property('trapezoid_top_width', value)
            self._cached_image = None
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()

    @property
    def trapezoid_bottom_width(self):
        """获取梯形下底宽度"""
        return self._property_manager.get_property('trapezoid_bottom_width')

    @trapezoid_bottom_width.setter
    def trapezoid_bottom_width(self, value):
        """设置梯形下底宽度"""
        if value > 0:
            self._property_manager.set_property('trapezoid_bottom_width', value)
            self._cached_image = None
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()

    @property
    def trapezoid_slope_side(self):
        """获取梯形斜边方向"""
        return self._property_manager.get_property('trapezoid_slope_side')

    @trapezoid_slope_side.setter
    def trapezoid_slope_side(self, value):
        """设置梯形斜边方向"""
        if value in ["left", "right"]:
            self._property_manager.set_property('trapezoid_slope_side', value)
            self._cached_image = None
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()

    @property
    def polygon_rotation(self):
        """获取多边形旋转角度"""
        return self._property_manager.get_property('polygon_rotation')

    @polygon_rotation.setter
    def polygon_rotation(self, value):
        """设置多边形旋转角度"""
        normalized_value = float(value) % 360
        if abs(self.polygon_rotation - normalized_value) > 0.001:
            self._property_manager.set_property('polygon_rotation', normalized_value)
            self._cached_image = None
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()

    @property
    def polygon_corner_radius(self):
        """获取多边形圆角半径"""
        return self._property_manager.get_property('polygon_corner_radius')

    @polygon_corner_radius.setter
    def polygon_corner_radius(self, value):
        """设置多边形圆角半径"""
        if value >= 0:
            self._property_manager.set_property('polygon_corner_radius', value)
            self._cached_image = None
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()
