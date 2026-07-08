from PySide6.QtCore import QObject, Signal
import os
import builtins
import random
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from enum import Enum, auto
import copy  # 导入copy模块实现深拷贝
import math
from collections import OrderedDict
import hashlib
import threading
from typing import List, Tuple
from app.models.layer_properties import LayerPropertyManager, CommonLayerOperations, ShapeType
from app.utils.render_diagnostics import log_branch, log_sampling
import logging
logger = logging.getLogger(__name__)

_LAYER_RENDER_VERBOSE = os.environ.get("BTPW_LAYER_RENDER_VERBOSE", "0") == "1"


def print(*args, **kwargs):
    """Keep noisy layer diagnostics off unless explicitly enabled."""
    if _LAYER_RENDER_VERBOSE:
        builtins.print(*args, **kwargs)


class FitMode(Enum):
    """图像适配模式枚举"""
    STRETCH = auto()       # 拉伸适配（可能变形）
    SCALE_CROP = auto()    # 等比缩放后裁剪
    SCALE_FIT = auto()     # 等比缩放不裁剪（在目标区域内居中）


class CropDirection(Enum):
    """裁剪方向枚举"""
    CENTER = auto()   # 中心裁剪
    TOP = auto()      # 裁剪底部（保留顶部）
    BOTTOM = auto()   # 裁剪顶部（保留底部）
    LEFT = auto()     # 裁剪右侧（保留左侧）
    RIGHT = auto()    # 裁剪左侧（保留右侧）


class Layer(QObject):
    """重构后的图层模型类 - 使用统一的属性管理"""
    _effects_stage_cache_lock = threading.RLock()
    _effects_stage_cache = OrderedDict()
    _effects_stage_cache_max_entries = 1024

    # 图像适配方式常量（与LegacyLayer兼容）
    FIT_SMART_CROP = 0  # 智能缩放裁剪（保持比例并裁剪）
    FIT_SMART_FIT = 1   # 智能缩放不裁剪（保持比例并居中）

    # 裁剪方向常量（与LegacyLayer兼容）
    CROP_CENTER = 0  # 中心裁剪
    CROP_TOP = 1     # 裁剪底部（保留顶部）
    CROP_BOTTOM = 2  # 裁剪顶部（保留底部）
    CROP_LEFT = 3    # 裁剪右侧（保留左侧）
    CROP_RIGHT = 4   # 裁剪左侧（保留右侧）

    # 信号定义
    changed = Signal()
    
    def __init__(self, name="新图层", x=0, y=0, width=100, height=100, image_source=None,
                 use_original_size=False, is_folder=True, current_image_path=None, parent=None):
        """
        初始化图层

        Args:
            name: 图层名称
            x: X坐标
            y: Y坐标
            width: 宽度
            height: 高度
            image_source: 图像源（文件夹或单个文件路径）
            use_original_size: 是否使用原始图像尺寸
            is_folder: 图像源是否为文件夹
            current_image_path: 当前使用的图像文件路径
            parent: 父对象
        """
        super().__init__(parent)

        # 生成唯一的图层ID，确保每个图层完全独立
        import uuid
        self._layer_id = str(uuid.uuid4())

        # 初始化属性管理器
        self._property_manager = LayerPropertyManager(self)
        
        # 设置初始属性值
        self._property_manager.set_property('name', name, validate=False)
        self._property_manager.set_property('x', x, validate=False)
        self._property_manager.set_property('y', y, validate=False)
        self._property_manager.set_property('width', width, validate=False)
        self._property_manager.set_property('height', height, validate=False)
        self._property_manager.set_property('image_source', image_source, validate=False)
        self._property_manager.set_property('use_original_size', use_original_size, validate=False)
        self._property_manager.set_property('is_folder', is_folder, validate=False)

        # 初始化通用操作管理器
        self._operations = CommonLayerOperations(self)
        
        # 图像相关属性
        self._cached_image = None
        self._cached_image_path = None  # 明确定义缓存路径
        # 源图像缓存：避免交互预览时重复读盘/网络路径
        self._cached_source_image = None
        self._cached_source_path = None
        self._cache_valid = False
        self._state_dirty = False
        self._updating = False  # 防止递归更新
        
        # 随机变换相关属性
        self._random_position_enabled = False
        self._random_position_range = 10
        self._random_scale_enabled = False
        self._random_scale_min = 0.9
        self._random_scale_max = 1.1
        self._random_rotation_enabled = False
        self._random_rotation_range = 5.0
        
        # 当前随机变换状态
        self._current_random_offset_x = 0
        self._current_random_offset_y = 0
        self._current_random_scale = 1.0
        self._current_random_rotation = 0.0
        
        # 设置当前图像路径（如果提供了）
        if current_image_path:
            self._property_manager.set_property('current_image_path', current_image_path, validate=False)
        # 如果图像源是单个文件，直接设置
        elif image_source and not is_folder and os.path.isfile(image_source):
            self._property_manager.set_property('current_image_path', image_source, validate=False)
    
    # 属性访问器 - 使用属性管理器
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
        # 清除缓存
        self._cached_image = None
        self._cache_valid = False
    
    @property
    def clone_custom_width(self):
        return self._property_manager.get_property('clone_custom_width')
    
    @clone_custom_width.setter
    def clone_custom_width(self, value):
        if value >= 0:
            self._property_manager.set_property('clone_custom_width', value)
            # 清除缓存
            self._cached_image = None
            self._cache_valid = False
    
    @property
    def clone_custom_height(self):
        return self._property_manager.get_property('clone_custom_height')
    
    @clone_custom_height.setter
    def clone_custom_height(self, value):
        if value >= 0:
            self._property_manager.set_property('clone_custom_height', value)
            # 清除缓存
            self._cached_image = None
            self._cache_valid = False

    # 圆角和描边属性访问器
    @property
    def corner_radius(self):
        return self._property_manager.get_property('corner_radius')

    @corner_radius.setter
    def corner_radius(self, value):
        self._property_manager.set_property('corner_radius', max(0, value))

    @property
    def vector_corner_radius_tl(self):
        return self._property_manager.get_property('vector_corner_radius_tl')

    @vector_corner_radius_tl.setter
    def vector_corner_radius_tl(self, value):
        self._property_manager.set_property('vector_corner_radius_tl', max(0, int(value)))
        self._cached_image = None
        self._cache_valid = False

    @property
    def vector_corner_radius_tr(self):
        return self._property_manager.get_property('vector_corner_radius_tr')

    @vector_corner_radius_tr.setter
    def vector_corner_radius_tr(self, value):
        self._property_manager.set_property('vector_corner_radius_tr', max(0, int(value)))
        self._cached_image = None
        self._cache_valid = False

    @property
    def vector_corner_radius_br(self):
        return self._property_manager.get_property('vector_corner_radius_br')

    @vector_corner_radius_br.setter
    def vector_corner_radius_br(self, value):
        self._property_manager.set_property('vector_corner_radius_br', max(0, int(value)))
        self._cached_image = None
        self._cache_valid = False

    @property
    def vector_corner_radius_bl(self):
        return self._property_manager.get_property('vector_corner_radius_bl')

    @vector_corner_radius_bl.setter
    def vector_corner_radius_bl(self, value):
        self._property_manager.set_property('vector_corner_radius_bl', max(0, int(value)))
        self._cached_image = None
        self._cache_valid = False

    @property
    def vector_path_enabled(self):
        return self._property_manager.get_property('vector_path_enabled')

    @vector_path_enabled.setter
    def vector_path_enabled(self, value):
        normalized = bool(value)
        self._property_manager.set_property('vector_path_enabled', normalized)
        if normalized and not self._property_manager.get_property('vector_path_points'):
            self.convert_rect_to_vector_path()
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    @property
    def vector_path_points(self):
        return copy.deepcopy(self._property_manager.get_property('vector_path_points'))

    @vector_path_points.setter
    def vector_path_points(self, value):
        from app.utils.vector_layer_geometry import normalize_vector_path_points

        normalized = normalize_vector_path_points(value)
        self._property_manager.set_property('vector_path_points', normalized)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    @property
    def vector_path_mode(self):
        return self._property_manager.get_property('vector_path_mode')

    @vector_path_mode.setter
    def vector_path_mode(self, value):
        normalized = str(value).lower()
        if normalized not in {"polygon", "bezier"}:
            normalized = "polygon"
        self._property_manager.set_property('vector_path_mode', normalized)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    @property
    def vector_bezier_nodes(self):
        return copy.deepcopy(self._property_manager.get_property('vector_bezier_nodes'))

    @vector_bezier_nodes.setter
    def vector_bezier_nodes(self, value):
        from app.utils.vector_layer_geometry import normalize_vector_bezier_nodes

        normalized = normalize_vector_bezier_nodes(value)
        self._property_manager.set_property('vector_bezier_nodes', normalized)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    @property
    def vector_path_closed(self):
        return bool(self._property_manager.get_property('vector_path_closed'))

    @vector_path_closed.setter
    def vector_path_closed(self, value):
        self._property_manager.set_property('vector_path_closed', bool(value))
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    @property
    def vector_handle_link_mode(self):
        return self._property_manager.get_property('vector_handle_link_mode')

    @vector_handle_link_mode.setter
    def vector_handle_link_mode(self, value):
        normalized = str(value).lower()
        if normalized not in {"mirror", "collinear", "free"}:
            normalized = "mirror"
        self._property_manager.set_property('vector_handle_link_mode', normalized)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

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
        # 确保颜色值在有效范围内
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

    # 颜色叠加属性访问器
    @property
    def color_overlay_enabled(self):
        return self._property_manager.get_property('color_overlay_enabled')

    @color_overlay_enabled.setter
    def color_overlay_enabled(self, value):
        self._property_manager.set_property('color_overlay_enabled', value)
        self._cached_image = None  # 清除缓存

    @property
    def color_overlay_color(self):
        return self._property_manager.get_property('color_overlay_color')

    @color_overlay_color.setter
    def color_overlay_color(self, value):
        self._property_manager.set_property('color_overlay_color', value)
        self._cached_image = None  # 清除缓存

    @property
    def color_overlay_opacity(self):
        return self._property_manager.get_property('color_overlay_opacity')

    @color_overlay_opacity.setter
    def color_overlay_opacity(self, value):
        self._property_manager.set_property('color_overlay_opacity', max(0.0, min(1.0, float(value))))
        self._cached_image = None  # 清除缓存

    # 渐变叠加属性访问器
    @property
    def gradient_overlay_enabled(self):
        return self._property_manager.get_property('gradient_overlay_enabled')

    @gradient_overlay_enabled.setter
    def gradient_overlay_enabled(self, value):
        self._property_manager.set_property('gradient_overlay_enabled', value)
        self._cached_image = None  # 清除缓存

    @property
    def gradient_overlay_colors(self):
        return self._property_manager.get_property('gradient_overlay_colors')

    @gradient_overlay_colors.setter
    def gradient_overlay_colors(self, value):
        self._property_manager.set_property('gradient_overlay_colors', value)
        self._cached_image = None  # 清除缓存

    @property
    def gradient_overlay_angle(self):
        return self._property_manager.get_property('gradient_overlay_angle')

    @gradient_overlay_angle.setter
    def gradient_overlay_angle(self, value):
        self._property_manager.set_property('gradient_overlay_angle', float(value) % 360)
        self._cached_image = None  # 清除缓存

    @property
    def gradient_overlay_opacity(self):
        return self._property_manager.get_property('gradient_overlay_opacity')

    @gradient_overlay_opacity.setter
    def gradient_overlay_opacity(self, value):
        self._property_manager.set_property('gradient_overlay_opacity', max(0.0, min(1.0, float(value))))
        self._cached_image = None  # 清除缓存

    # 绑定属性访问器
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
    
    # 形状属性访问器 - 所有图层都可以使用形状功能
    @property
    def shape_type(self):
        """获取形状类型"""
        return self._property_manager.get_property('shape_type')
    
    @shape_type.setter
    def shape_type(self, value):
        """设置形状类型"""
        self._property_manager.set_property('shape_type', value)
        self._cached_image = None  # 清除图像缓存，强制重新渲染
        if hasattr(self, '_shape_mask_cache'):
            self._shape_mask_cache.clear()  # 清除形状蒙版缓存
    
    @property
    def trapezoid_top_width(self):
        """获取梯形上底宽度"""
        return self._property_manager.get_property('trapezoid_top_width')
    
    @trapezoid_top_width.setter
    def trapezoid_top_width(self, value):
        """设置梯形上底宽度"""
        if value > 0:
            self._property_manager.set_property('trapezoid_top_width', value)
            self._cached_image = None  # 清除图像缓存，强制重新渲染
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()  # 清除形状蒙版缓存
    
    @property
    def trapezoid_bottom_width(self):
        """获取梯形下底宽度"""
        return self._property_manager.get_property('trapezoid_bottom_width')
    
    @trapezoid_bottom_width.setter
    def trapezoid_bottom_width(self, value):
        """设置梯形下底宽度"""
        if value > 0:
            self._property_manager.set_property('trapezoid_bottom_width', value)
            self._cached_image = None  # 清除图像缓存，强制重新渲染
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()  # 清除形状蒙版缓存
    
    @property
    def trapezoid_slope_side(self):
        """获取梯形斜边方向"""
        return self._property_manager.get_property('trapezoid_slope_side')
    
    @trapezoid_slope_side.setter
    def trapezoid_slope_side(self, value):
        """设置梯形斜边方向"""
        if value in ["left", "right"]:
            self._property_manager.set_property('trapezoid_slope_side', value)
            self._cached_image = None  # 清除图像缓存，强制重新渲染
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()  # 清除形状蒙版缓存
    
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
            self._cached_image = None  # 清除图像缓存，强制重新渲染
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()  # 清除形状蒙版缓存
    
    @property
    def polygon_corner_radius(self):
        """获取多边形圆角半径"""
        return self._property_manager.get_property('polygon_corner_radius')
    
    @polygon_corner_radius.setter
    def polygon_corner_radius(self, value):
        """设置多边形圆角半径"""
        if value >= 0:
            self._property_manager.set_property('polygon_corner_radius', value)
            self._cached_image = None  # 清除图像缓存，强制重新渲染
            if hasattr(self, '_shape_mask_cache'):
                self._shape_mask_cache.clear()  # 清除形状蒙版缓存
    
    # 变换属性访问器
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
    
    # 锁定比例属性访问器
    @property
    def aspect_ratio_locked(self):
        """是否锁定宽高比"""
        return self._property_manager.get_property('aspect_ratio_locked')

    @aspect_ratio_locked.setter
    def aspect_ratio_locked(self, value):
        self._property_manager.set_property('aspect_ratio_locked', value)
    
    # 通用操作方法 - 委托给操作管理器
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

    # 随机变换属性与方法（与 Legacy Layer 接口对齐）
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
    
    @property
    def current_image_path(self):
        return self._property_manager.get_property('current_image_path')
    
    @current_image_path.setter
    def current_image_path(self, value):
        self._property_manager.set_property('current_image_path', value, validate=False)
    
    @property
    def cached_image(self):
        return self._cached_image
    
    @cached_image.setter
    def cached_image(self, value):
        self._cached_image = value

    @staticmethod
    def _normalize_image_path(path_value):
        """规范化图片路径，统一本地与UNC表示。"""
        if not path_value:
            return path_value
        p = str(path_value).replace('/', os.sep)
        if p.startswith('\\\\'):
            return p
        if p.startswith('//'):
            server_share = p.lstrip('/').replace('/', '\\')
            return f"\\\\{server_share}"
        return os.path.normpath(p)

    @staticmethod
    def _paths_equal(left, right):
        """跨平台稳健路径比较（区分大小写策略跟随系统）。"""
        if not left or not right:
            return False
        try:
            left_abs = os.path.normcase(os.path.abspath(left))
            right_abs = os.path.normcase(os.path.abspath(right))
            return left_abs == right_abs
        except Exception:
            return str(left) == str(right)
    
    # 其他方法保持不变...
    def extract_filename_core(self, filename):
        """
        提取文件名的核心部分用于绑定匹配
        
        Args:
            filename: 文件名（不含扩展名）
            
        Returns:
            str: 核心文件名，例如：
                avatar_001 -> avatar
                bg-002 -> bg
                char_hero_03 -> char_hero
        """
        import re
        
        # 移除常见的数字后缀模式
        patterns = [
            r'[-_]\d+$',        # 匹配 _001, -02 等
            r'[-_]\d+[-_]\d+$', # 匹配 _01_02 等
            r'\d+$',            # 匹配末尾的纯数字
        ]
        
        core_name = filename
        for pattern in patterns:
            core_name = re.sub(pattern, '', core_name)
        
        return core_name.strip('_-') if core_name else filename
    
    def get_bound_images(self, target_core_name):
        """
        获取当前图层文件夹中与目标核心名称匹配的所有图像文件
        
        Args:
            target_core_name: 目标核心名称
            
        Returns:
            list: 匹配的图像文件路径列表
        """
        image_source = self.image_source
        if not image_source or not os.path.isdir(image_source):
            return []
            
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        matching_files = []
        
        for file in os.listdir(image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                filename_without_ext = os.path.splitext(file)[0]
                core_name = self.extract_filename_core(filename_without_ext)
                
                if core_name == target_core_name:
                    matching_files.append(os.path.join(image_source, file))
        
        return matching_files
    
    def get_random_image(self, force_random=False, restrict_to_bound_files=None):
        """从关联文件夹中随机选择一张图片，或加载单个图片"""
        # 简化版本，保持原有逻辑但使用属性管理器
        current_image_path = self.current_image_path
        image_source = self.image_source
        is_folder = self.is_folder
        image_source_norm = self._normalize_image_path(image_source) if image_source else image_source

        # 如果图像源是单个文件：优先命中缓存，避免每帧触发网络路径isfile开销
        if not is_folder and image_source_norm and not force_random:
            try:
                if self._cached_image is not None and self._paths_equal(self._cached_image_path, image_source_norm):
                    return self._cached_image
                if not os.path.isfile(image_source_norm):
                    return None

                old_width, old_height = self.width, self.height
                image = self._load_and_process_image(image_source_norm)
                
                if old_width != self.width or old_height != self.height:
                    self._property_manager.set_property('width', old_width, validate=False)
                    self._property_manager.set_property('height', old_height, validate=False)
                    if image.width != old_width or image.height != old_height:
                        # 使用预乘Alpha缩放以保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_rgba_premultiplied(image, (old_width, old_height), Resampling.BICUBIC)
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)
                
                self._cached_image = image
                self._cached_image_path = image_source_norm
                self._property_manager.set_property('current_image_path', image_source_norm, validate=False)
                return image
            except Exception as e:
                print(f"无法加载图像 {image_source}: {e}")
                err = self._create_error_image()
                self._cached_image = err
                self._cached_image_path = image_source_norm
                return err
        
        # 其他逻辑保持不变...
        return self._get_random_image_impl(force_random, restrict_to_bound_files)
    
    def get_image(self):
        """获取图层的当前图像"""
        current_path = self._normalize_image_path(self.current_image_path) if self.current_image_path else None

        # 热路径优化：缓存命中时直接返回，避免预览时频繁isfile/exists（网络盘尤其昂贵）
        if current_path and self._cached_image is not None and self._paths_equal(self._cached_image_path, current_path):
            return self._cached_image

        if current_path and os.path.isfile(current_path):
            try:
                img = self._load_and_process_image(current_path)
                self._cached_image = img
                self._cached_image_path = current_path
                return img
            except Exception as e:
                print(f"无法加载指定图像 {current_path}: {e}")
                self._property_manager.set_property('current_image_path', None, validate=False)
        elif current_path and not os.path.isfile(current_path):
            self._property_manager.set_property('current_image_path', None, validate=False)
            try:
                if hasattr(self, 'changed') and hasattr(self.changed, 'emit'):
                    self.changed.emit()
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in layer_new.py")
                pass
        
        try:
            src = self._normalize_image_path(self.image_source) if getattr(self, 'image_source', None) else None
            if src and os.path.isfile(src):
                self._property_manager.set_property('current_image_path', src, validate=False)
                try:
                    if self._cached_image is not None and self._paths_equal(self._cached_image_path, src):
                        return self._cached_image
                    img = self._load_and_process_image(src)
                    self._cached_image = img
                    self._cached_image_path = src
                    return img
                except Exception as e:
                    print(f"无法加载图像 {src}: {e}")
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in layer_new.py")
            pass
        
        return self.get_random_image(force_random=False)
    
    def _get_random_image_impl(self, force_random=False, restrict_to_bound_files=None):
        """随机图像选择的内部实现"""
        # 这里简化实现，实际应该包含完整的逻辑
        image_source = self.image_source
        is_folder = self.is_folder
        
        if not image_source or not os.path.isdir(image_source) or not is_folder:
            return None
            
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        image_files = []
        
        for file in os.listdir(image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                image_files.append(os.path.join(image_source, file))

        if not image_files:
            return None

        # 使用缓存（仅当缓存路径与当前目标路径一致时）
        if not force_random and self._cached_image is not None and self._cached_image_path:
            try:
                current_path = self.current_image_path
                if current_path:
                    # 已指定当前路径时，缓存必须与当前路径一致，避免显示旧图
                    if self._paths_equal(self._cached_image_path, current_path):
                        return self._cached_image
                    else:
                        # 路径不一致，主动清缓存，确保后续按新路径加载
                        self._cached_image = None
                        self._cached_image_path = None
                else:
                    # 未指定当前路径时，允许沿用缓存
                    return self._cached_image
            except Exception:
                # 发生路径规范化异常时，保守处理：不使用缓存
                self._cached_image = None
                self._cached_image_path = None

        import random
        if not force_random and self.current_image_path and self.current_image_path in image_files:
            selected_path = self.current_image_path
        else:
            selected_path = random.choice(image_files)
        self._property_manager.set_property('current_image_path', selected_path, validate=False)
        
        try:
            img = self._load_and_process_image(selected_path)
            self._cached_image = img
            self._cached_image_path = selected_path
            return img
        except Exception as e:
            print(f"无法加载图像 {selected_path}: {e}")
            err = self._create_error_image()
            self._cached_image = err
            self._cached_image_path = selected_path
            return err
    
    def _load_and_process_image(self, image_path):
        """加载并处理图像"""
        try:
            from PIL import ImageFile
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            image_path_norm = self._normalize_image_path(image_path)
            if not image_path_norm or not os.path.exists(image_path_norm):
                raise FileNotFoundError(image_path_norm)
            # 先用源图缓存，避免连续交互（拖拽/缩放）反复从磁盘或网络读取同一路径
            if self._cached_source_image is None or not self._paths_equal(self._cached_source_path, image_path_norm):
                img = Image.open(image_path_norm)
                try:
                    img.load()
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in layer_new.py")
                    pass
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                self._cached_source_image = img.copy()
                self._cached_source_path = image_path_norm
                try:
                    img.close()
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in layer_new.py")
                    pass

            return self._process_image(self._cached_source_image.copy())
            
        except Exception as e:
            print(f"图像处理失败: {e}")
            return self._create_error_image()
    
    def _process_image(self, original_image):
        """处理图像的核心逻辑"""
        # 这里简化实现，实际应该包含完整的图像处理逻辑
        target_width = self.width
        target_height = self.height
        use_original_size = self.use_original_size
        fit_mode = self.fit_mode
        
        if use_original_size:
            # 智能裁剪逻辑
            bounds = self._find_non_transparent_bounds(original_image)
            if bounds != (0, 0, original_image.width, original_image.height):
                original_image = original_image.crop(bounds)
        
        # 根据适配模式调整大小
        if fit_mode == 0:  # 智能裁剪
            return self._scale_and_crop(original_image)
        elif fit_mode == 1:  # 智能缩放不裁剪
            return self._scale_to_fit(original_image)
        else:  # 拉伸适配
            # 使用预乘Alpha缩放以保护半透明图像质量
            if original_image.mode == 'RGBA':
                return self._resize_rgba_premultiplied(original_image, (target_width, target_height), Resampling.BICUBIC)
            else:
                return original_image.resize((target_width, target_height), Resampling.BICUBIC)
    
    def _find_non_transparent_bounds(self, image):
        """查找图像中非空白区域的边界"""
        if image.mode != 'RGBA':
            return (0, 0, image.width, image.height)
        
        try:
            img_array = np.array(image)
            alpha = img_array[:, :, 3]
            alpha_threshold = 5
            
            mask = alpha > alpha_threshold
            if not np.any(mask):
                return (0, 0, image.width, image.height)
            
            rows = np.any(mask, axis=1)
            cols = np.any(mask, axis=0)
            
            top = np.argmax(rows)
            bottom = image.height - np.argmax(rows[::-1])
            left = np.argmax(cols)
            right = image.width - np.argmax(cols[::-1])
            
            # 添加边距
            margin = 1
            left = max(0, int(left - margin))
            top = max(0, int(top - margin))
            right = min(image.width, right + margin)
            bottom = min(image.height, bottom + margin)
            
            return (left, top, right, bottom)
            
        except Exception as e:
            print(f"计算非空白区域边界时出错: {e}")
            return (0, 0, image.width, image.height)
    
    def _scale_and_crop(self, image):
        """等比缩放图像并按指定方向裁剪"""
        # 简化实现
        if image is None or image.width == 0 or image.height == 0:
            return None
            
        target_width = self.width
        target_height = self.height
        
        if target_width <= 0 or target_height <= 0:
            return None
        
        # 计算缩放尺寸
        orig_ratio = image.width / image.height
        target_ratio = target_width / target_height
        
        if orig_ratio > target_ratio:
            scale_height = target_height
            scale_width = int(scale_height * orig_ratio)
        else:
            scale_width = target_width
            scale_height = int(scale_width / orig_ratio)
        
        # 缩放 - 使用预乘Alpha保护半透明图像质量
        if image.mode == 'RGBA':
            scaled_image = self._resize_rgba_premultiplied(image, (scale_width, scale_height), Resampling.BICUBIC)
        else:
            scaled_image = image.resize((scale_width, scale_height), Resampling.BICUBIC)
        
        # 裁剪
        crop_direction = self.crop_direction
        if crop_direction == 0:  # 居中
            left = (scale_width - target_width) // 2
            top = (scale_height - target_height) // 2
        elif crop_direction == 1:  # 顶部
            left = (scale_width - target_width) // 2
            top = 0
        elif crop_direction == 2:  # 底部
            left = (scale_width - target_width) // 2
            top = scale_height - target_height
        elif crop_direction == 3:  # 左侧
            left = 0
            top = (scale_height - target_height) // 2
        elif crop_direction == 4:  # 右侧
            left = scale_width - target_width
            top = (scale_height - target_height) // 2
        else:
            left = (scale_width - target_width) // 2
            top = (scale_height - target_height) // 2
        
        # 确保裁剪区域有效
        left = max(0, min(left, scale_width - target_width))
        top = max(0, min(top, scale_height - target_height))
        
        return scaled_image.crop((left, top, left + target_width, top + target_height))
    
    def _scale_to_fit(self, image):
        """等比缩放图像以适应目标区域，不进行裁剪"""
        if image is None or image.width == 0 or image.height == 0:
            return None
            
        target_width = self.width
        target_height = self.height
        
        if target_width <= 0 or target_height <= 0:
            return None
        
        # 计算缩放尺寸
        orig_ratio = image.width / image.height
        target_ratio = target_width / target_height
        
        if orig_ratio > target_ratio:
            scale_width = target_width
            scale_height = int(scale_width / orig_ratio)
        else:
            scale_height = target_height
            scale_width = int(scale_height * orig_ratio)
        
        # 确保尺寸有效
        scale_width = max(1, scale_width)
        scale_height = max(1, scale_height)
        
        # 缩放 - 使用预乘Alpha保护半透明图像质量
        if image.mode == 'RGBA':
            scaled_image = self._resize_rgba_premultiplied(image, (scale_width, scale_height), Resampling.BICUBIC)
        else:
            scaled_image = image.resize((scale_width, scale_height), Resampling.BICUBIC)
        
        # 创建透明背景并居中放置
        result = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
        pos_x = (target_width - scale_width) // 2
        pos_y = (target_height - scale_height) // 2
        result.paste(scaled_image, (pos_x, pos_y), scaled_image)
        
        return result
    
    def apply_effects(self, image):
        """应用图层特效的公共方法"""
        return self._apply_effects(image)

    @classmethod
    def _get_effects_stage_cache(cls, cache_key: str):
        with cls._effects_stage_cache_lock:
            cached = cls._effects_stage_cache.get(cache_key)
            if cached is None:
                return None
            cls._effects_stage_cache.move_to_end(cache_key)
            return cached.copy()

    @classmethod
    def _set_effects_stage_cache(cls, cache_key: str, image):
        if image is None:
            return
        with cls._effects_stage_cache_lock:
            cls._effects_stage_cache[cache_key] = image.copy()
            cls._effects_stage_cache.move_to_end(cache_key)
            while len(cls._effects_stage_cache) > cls._effects_stage_cache_max_entries:
                cls._effects_stage_cache.popitem(last=False)

    def _build_effects_stage_cache_key(self, stage_name: str, image, extra_parts: List[str]) -> str:
        source_parts = [
            f"stage:{stage_name}",
            f"path:{getattr(self, 'current_image_path', '') or ''}",
            f"src:{getattr(self, 'image_source', '') or ''}",
            f"img:{getattr(image, 'width', 0)}x{getattr(image, 'height', 0)}:{getattr(image, 'mode', '')}",
            f"layer:{getattr(self, 'width', 0)}x{getattr(self, 'height', 0)}",
            f"fit:{getattr(self, 'fit_mode', 0)}",
            f"crop:{getattr(self, 'crop_direction', 0)}",
            f"use_orig:{int(bool(getattr(self, 'use_original_size', False)))}",
            f"rot:{float(getattr(self, 'rotation', 0.0)):.3f}",
            f"flip_h:{int(bool(getattr(self, 'flip_horizontal', False)))}",
            f"flip_v:{int(bool(getattr(self, 'flip_vertical', False)))}",
            f"rnd_scale:{float(getattr(self, '_current_random_scale', 1.0)):.6f}",
            f"rnd_rot:{float(getattr(self, '_current_random_rotation', 0.0)):.3f}",
        ]
        source_parts.extend(extra_parts)
        return hashlib.md5("|".join([str(p) for p in source_parts]).encode('utf-8')).hexdigest()

    def _use_rectangle_vector_pipeline(self, stroke_on: bool) -> bool:
        # 非矩形形状统一走新矢量几何管线，避免回退到旧位图遮罩方案
        if self.shape_type != ShapeType.RECTANGLE:
            return True
        return bool(
            self.vector_path_enabled
            or stroke_on
            or self.corner_radius > 0
            or self.vector_corner_radius_tl > 0
            or self.vector_corner_radius_tr > 0
            or self.vector_corner_radius_br > 0
            or self.vector_corner_radius_bl > 0
            or self.stroke_dash_length > 0
            or self.stroke_dash_gap > 0
            or self.stroke_join != "miter"
            or self.stroke_cap != "butt"
        )

    def convert_rect_to_vector_path(self):
        w, h = float(self.width), float(self.height)
        points = [[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]]
        nodes = [
            {'x': 0.0, 'y': 0.0, 'in_x': 0.0, 'in_y': 0.0, 'out_x': 0.0, 'out_y': 0.0, 'node_type': 'corner'},
            {'x': w, 'y': 0.0, 'in_x': w, 'in_y': 0.0, 'out_x': w, 'out_y': 0.0, 'node_type': 'corner'},
            {'x': w, 'y': h, 'in_x': w, 'in_y': h, 'out_x': w, 'out_y': h, 'node_type': 'corner'},
            {'x': 0.0, 'y': h, 'in_x': 0.0, 'in_y': h, 'out_x': 0.0, 'out_y': h, 'node_type': 'corner'},
        ]
        self._property_manager.set_property('vector_path_points', points, validate=False)
        self._property_manager.set_property('vector_path_enabled', True, validate=False)
        self._property_manager.set_property('vector_path_mode', 'bezier', validate=False)
        self._property_manager.set_property('vector_bezier_nodes', nodes, validate=False)
        self._property_manager.set_property('vector_path_closed', True, validate=False)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    def update_vector_path_node(self, node_index: int, x: float, y: float):
        from app.utils.vector_layer_geometry import normalize_vector_path_points, normalize_vector_bezier_nodes

        if not self.vector_path_enabled:
            self.convert_rect_to_vector_path()
        points = normalize_vector_path_points(self.vector_path_points)
        if node_index < 0 or node_index >= len(points):
            return
        points[node_index] = [float(x), float(y)]
        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        new_w = max(1, int(round(max_x - min_x)))
        new_h = max(1, int(round(max_y - min_y)))
        self.x = self.x + int(round(min_x))
        self.y = self.y + int(round(min_y))
        self.width = new_w
        self.height = new_h
        shifted = [[pt[0] - min_x, pt[1] - min_y] for pt in points]
        self._property_manager.set_property('vector_path_points', shifted, validate=False)
        if self.vector_bezier_nodes:
            normalized_nodes = []
            for n in normalize_vector_bezier_nodes(self.vector_bezier_nodes):
                normalized_nodes.append({
                    'x': n['x'] - min_x,
                    'y': n['y'] - min_y,
                    'in_x': n['in_x'] - min_x,
                    'in_y': n['in_y'] - min_y,
                    'out_x': n['out_x'] - min_x,
                    'out_y': n['out_y'] - min_y,
                    'node_type': n.get('node_type', 'corner'),
                })
            self._property_manager.set_property('vector_bezier_nodes', normalized_nodes, validate=False)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    def update_vector_bezier_anchor(self, node_index: int, x: float, y: float):
        from app.utils.vector_layer_geometry import normalize_vector_bezier_nodes

        nodes = normalize_vector_bezier_nodes(self.vector_bezier_nodes)
        if node_index < 0 or node_index >= len(nodes):
            return
        node = nodes[node_index]
        dx = float(x) - node['x']
        dy = float(y) - node['y']
        node['x'] = float(x)
        node['y'] = float(y)
        node['in_x'] += dx
        node['in_y'] += dy
        node['out_x'] += dx
        node['out_y'] += dy
        self._property_manager.set_property('vector_bezier_nodes', nodes, validate=False)
        self._property_manager.set_property('vector_path_points', [[n['x'], n['y']] for n in nodes], validate=False)
        self.update_vector_path_node(node_index, float(x), float(y))

    def update_vector_bezier_handle(self, node_index: int, handle_type: str, x: float, y: float):
        from app.utils.vector_layer_geometry import normalize_vector_bezier_nodes

        nodes = normalize_vector_bezier_nodes(self.vector_bezier_nodes)
        if node_index < 0 or node_index >= len(nodes):
            return
        node = nodes[node_index]
        node_type = node.get('node_type', 'corner')
        ax, ay = node['x'], node['y']
        effective_mode = self.vector_handle_link_mode
        if node_type == 'symmetric':
            effective_mode = 'mirror'
        elif node_type == 'smooth':
            effective_mode = 'collinear'
        elif node_type == 'corner':
            effective_mode = 'free'

        if handle_type == 'in':
            node['in_x'] = float(x)
            node['in_y'] = float(y)
            vx = node['in_x'] - ax
            vy = node['in_y'] - ay
            length = math.hypot(vx, vy)
            if effective_mode == "mirror" and length > 1e-6:
                node['out_x'] = ax - vx
                node['out_y'] = ay - vy
            elif effective_mode == "collinear" and length > 1e-6:
                ovx = node['out_x'] - ax
                ovy = node['out_y'] - ay
                olen = math.hypot(ovx, ovy)
                if olen < 1e-6:
                    olen = length
                ux, uy = -vx / length, -vy / length
                node['out_x'] = ax + ux * olen
                node['out_y'] = ay + uy * olen
        else:
            node['out_x'] = float(x)
            node['out_y'] = float(y)
            vx = node['out_x'] - ax
            vy = node['out_y'] - ay
            length = math.hypot(vx, vy)
            if effective_mode == "mirror" and length > 1e-6:
                node['in_x'] = ax - vx
                node['in_y'] = ay - vy
            elif effective_mode == "collinear" and length > 1e-6:
                ivx = node['in_x'] - ax
                ivy = node['in_y'] - ay
                ilen = math.hypot(ivx, ivy)
                if ilen < 1e-6:
                    ilen = length
                ux, uy = -vx / length, -vy / length
                node['in_x'] = ax + ux * ilen
                node['in_y'] = ay + uy * ilen
        self._property_manager.set_property('vector_bezier_nodes', nodes, validate=False)
        self._property_manager.set_property('vector_path_points', [[n['x'], n['y']] for n in nodes], validate=False)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    def set_vector_node_type(self, node_index: int, node_type: str):
        from app.utils.vector_layer_geometry import normalize_vector_bezier_nodes

        nodes = normalize_vector_bezier_nodes(self.vector_bezier_nodes)
        if node_index < 0 or node_index >= len(nodes):
            return
        normalized = str(node_type).lower()
        if normalized not in {"corner", "smooth", "symmetric"}:
            normalized = "corner"
        nodes[node_index]['node_type'] = normalized
        self._property_manager.set_property('vector_bezier_nodes', nodes, validate=False)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    def cycle_vector_node_type(self, node_index: int):
        from app.utils.vector_layer_geometry import normalize_vector_bezier_nodes

        nodes = normalize_vector_bezier_nodes(self.vector_bezier_nodes)
        if node_index < 0 or node_index >= len(nodes):
            return
        order = ["corner", "smooth", "symmetric"]
        cur = nodes[node_index].get('node_type', 'corner')
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "corner"
        self.set_vector_node_type(node_index, nxt)

    def insert_vector_node_after(self, segment_index: int):
        from app.utils.vector_layer_geometry import normalize_vector_bezier_nodes

        nodes = normalize_vector_bezier_nodes(self.vector_bezier_nodes)
        if len(nodes) < 2:
            return
        closed = bool(self.vector_path_closed)
        max_seg = len(nodes) - 1 if not closed else len(nodes) - 1
        if segment_index < 0 or segment_index > max_seg:
            return
        next_index = (segment_index + 1) % len(nodes)
        if not closed and segment_index == len(nodes) - 1:
            return
        n0 = nodes[segment_index]
        n1 = nodes[next_index]
        mx = (n0['x'] + n1['x']) / 2.0
        my = (n0['y'] + n1['y']) / 2.0
        new_node = {
            'x': mx,
            'y': my,
            'in_x': (n0['out_x'] + mx) / 2.0,
            'in_y': (n0['out_y'] + my) / 2.0,
            'out_x': (n1['in_x'] + mx) / 2.0,
            'out_y': (n1['in_y'] + my) / 2.0,
            'node_type': 'smooth',
        }
        nodes.insert(segment_index + 1, new_node)
        self._property_manager.set_property('vector_bezier_nodes', nodes, validate=False)
        self._property_manager.set_property('vector_path_points', [[n['x'], n['y']] for n in nodes], validate=False)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()

    def delete_vector_node(self, node_index: int):
        from app.utils.vector_layer_geometry import normalize_vector_bezier_nodes

        nodes = normalize_vector_bezier_nodes(self.vector_bezier_nodes)
        min_nodes = 3 if self.vector_path_closed else 2
        if len(nodes) <= min_nodes or node_index < 0 or node_index >= len(nodes):
            return
        del nodes[node_index]
        self._property_manager.set_property('vector_bezier_nodes', nodes, validate=False)
        self._property_manager.set_property('vector_path_points', [[n['x'], n['y']] for n in nodes], validate=False)
        self._cached_image = None
        self._cache_valid = False
        self.changed.emit()
    
    def _apply_effects(self, image):
        """应用图层特效（圆角、描边、形状等）和变换（旋转、翻转）"""
        if image is None:
            return None
        self._render_offset_x = 0
        self._render_offset_y = 0
        
        if _LAYER_RENDER_VERBOSE:
            print(f"应用特效前图像尺寸: {image.width}x{image.height}, 图层尺寸: {self.width}x{self.height}")
        
        # 如果图像尺寸与图层尺寸不匹配，根据模式处理
        if image.width != self.width or image.height != self.height:
            if self.fit_mode == 2:
                # 等比缩放不裁剪模式：保持原图尺寸，继续应用特效
                if _LAYER_RENDER_VERBOSE:
                    print(f"等比缩放不裁剪模式：保持图像尺寸不变 {image.width}x{image.height}，继续应用圆角/描边")
            else:
                if _LAYER_RENDER_VERBOSE:
                    print(f"警告：图像尺寸与图层尺寸不匹配，调整图像大小: {image.width}x{image.height} => {self.width}x{self.height}")
                image = self._resize_rgba_premultiplied(image, (self.width, self.height), Resampling.BICUBIC)
        
        stroke_enabled = self.stroke_enabled and self.stroke_width > 0
        use_vector_pipeline = self._use_rectangle_vector_pipeline(stroke_enabled)
        log_branch(
            "layer_new._apply_effects",
            "enter",
            shape_type=getattr(getattr(self, 'shape_type', None), 'value', getattr(self, 'shape_type', 'unknown')),
            corner_radius=self.corner_radius,
            stroke_enabled=stroke_enabled,
            stroke_type=getattr(self, 'stroke_type', -1),
            stroke_width=getattr(self, 'stroke_width', 0),
            vector_pipeline=use_vector_pipeline,
        )

        # 阶段1：几何与变换（可缓存）
        stage1_extra_parts = [
            f"shape:{getattr(getattr(self, 'shape_type', ''), 'value', getattr(self, 'shape_type', ''))}",
            f"corner:{int(getattr(self, 'corner_radius', 0))}",
            f"vcorner:{int(self.vector_corner_radius_tl)}:{int(self.vector_corner_radius_tr)}:"
            f"{int(self.vector_corner_radius_br)}:{int(self.vector_corner_radius_bl)}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"vpath_on:{int(bool(self.vector_path_enabled))}",
            f"vpath_pts:{str(self.vector_path_points)}",
            f"vpath_mode:{str(self.vector_path_mode)}",
            f"vpath_bezier:{str(self.vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self.vector_path_closed))}",
            f"vpath_link:{str(self.vector_handle_link_mode)}",
            f"trap:{getattr(self, 'trapezoid_top_width', '')},{getattr(self, 'trapezoid_bottom_width', '')},{getattr(self, 'trapezoid_slope_side', '')}",
            f"poly:{getattr(self, 'polygon_rotation', '')},{getattr(self, 'polygon_corner_radius', '')}",
        ]
        stage1_key = self._build_effects_stage_cache_key("geometry", image, stage1_extra_parts)
        result = self._get_effects_stage_cache(stage1_key)
        if result is None:
            result = (image.convert('RGBA') if image.mode != 'RGBA' else image.copy())
            if (self.shape_type != ShapeType.RECTANGLE) and (not use_vector_pipeline):
                result = self._apply_shape_mask(result)
            result = self._apply_transformations(result)
            # 矩形图层若走矢量几何管线，圆角/路径裁剪统一在阶段3处理，避免位图圆角遮罩
            if (
                self.corner_radius > 0
                and self.shape_type == ShapeType.RECTANGLE
                and not stroke_enabled
                and not use_vector_pipeline
            ):
                log_branch("layer_new._apply_effects", "corner_only")
                result = self._apply_corner_radius_improved(result)
            self._set_effects_stage_cache(stage1_key, result)

        # 阶段2：叠加样式（可缓存）
        stage2_extra_parts = [
            f"base:{stage1_key}",
            f"overlay_on:{int(bool(getattr(self, 'color_overlay_enabled', False)))}",
            f"overlay_c:{str(getattr(self, 'color_overlay_color', (255, 255, 255, 255)))}",
            f"overlay_op:{float(getattr(self, 'color_overlay_opacity', 1.0)):.4f}",
            f"grad_on:{int(bool(getattr(self, 'gradient_overlay_enabled', False)))}",
            f"grad_angle:{float(getattr(self, 'gradient_overlay_angle', 0.0)):.3f}",
            f"grad_op:{float(getattr(self, 'gradient_overlay_opacity', 1.0)):.4f}",
            f"grad_colors:{str(getattr(self, 'gradient_overlay_colors', []))}",
        ]
        stage2_key = self._build_effects_stage_cache_key("overlay", image, stage2_extra_parts)
        overlay_result = self._get_effects_stage_cache(stage2_key)
        if overlay_result is None:
            overlay_result = result.copy()
            if self.color_overlay_enabled:
                overlay_result = self._apply_color_overlay(overlay_result)
            if self.gradient_overlay_enabled:
                overlay_result = self._apply_gradient_overlay(overlay_result)
            self._set_effects_stage_cache(stage2_key, overlay_result)
        result = overlay_result
        
        # 阶段3：描边与最终收敛（可缓存）
        stage3_extra_parts = [
            "vec_pipe_ver:v5",
            f"base:{stage2_key}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"stroke_type:{int(getattr(self, 'stroke_type', 0))}",
            f"stroke_w:{int(getattr(self, 'stroke_width', 0))}",
            f"stroke_c:{str(getattr(self, 'stroke_color', (0, 0, 0, 255)))}",
            f"stroke_join:{str(getattr(self, 'stroke_join', 'miter'))}",
            f"stroke_cap:{str(getattr(self, 'stroke_cap', 'butt'))}",
            f"dash_len:{int(getattr(self, 'stroke_dash_length', 0))}",
            f"dash_gap:{int(getattr(self, 'stroke_dash_gap', 0))}",
            f"shape:{getattr(getattr(self, 'shape_type', ''), 'value', getattr(self, 'shape_type', ''))}",
            f"corner:{int(getattr(self, 'corner_radius', 0))}",
            f"vcorner:{int(self.vector_corner_radius_tl)}:{int(self.vector_corner_radius_tr)}:"
            f"{int(self.vector_corner_radius_br)}:{int(self.vector_corner_radius_bl)}",
            f"vpath_on:{int(bool(self.vector_path_enabled))}",
            f"vpath_pts:{str(self.vector_path_points)}",
            f"vpath_mode:{str(self.vector_path_mode)}",
            f"vpath_bezier:{str(self.vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self.vector_path_closed))}",
            f"vpath_link:{str(self.vector_handle_link_mode)}",
            f"vec_pipe:{int(bool(use_vector_pipeline))}",
            f"out_size:{int(getattr(self, 'width', 0))}x{int(getattr(self, 'height', 0))}",
        ]
        stage3_key = self._build_effects_stage_cache_key("stroke_finalize", image, stage3_extra_parts)
        final_result = self._get_effects_stage_cache(stage3_key)
        if final_result is None:
            final_result = result.copy()
            if use_vector_pipeline:
                from app.utils.vector_layer_effects import (
                    VectorEffectParams,
                    alpha_composite_layers,
                    apply_vector_path_effects,
                )

                params = VectorEffectParams.collect(self)
                params.stroke_enabled = bool(stroke_enabled)
                final_result = apply_vector_path_effects(
                    final_result, params, alpha_composite=alpha_composite_layers
                )
                self._render_offset_x = int(final_result.info.get("vector_offset_x", 0))
                self._render_offset_y = int(final_result.info.get("vector_offset_y", 0))
            elif stroke_enabled:
                if self.stroke_type == 0:  # 内描边
                    log_branch("layer_new._apply_effects", "stroke_inner")
                    final_result = self._apply_inner_stroke(final_result)
                elif self.stroke_type == 1:  # 居中描边
                    log_branch("layer_new._apply_effects", "stroke_center")
                    final_result = self._apply_center_stroke(final_result)
                elif self.stroke_type == 2:  # 外描边
                    log_branch("layer_new._apply_effects", "stroke_outer")
                    final_result = self._apply_outer_stroke(final_result)

            # 非矢量管线才强制收敛到图层尺寸；矢量管线允许外扩（居中/外描边）
            if (not use_vector_pipeline) and (final_result.width != self.width or final_result.height != self.height):
                final_result = self._resize_rgba_premultiplied(final_result, (self.width, self.height), Resampling.LANCZOS)

            # 边缘优化：在最终合成前进行一次透明边缘颜色出血，避免白/黑晕
            # 注意：该步骤会创建新图像对象，需保留矢量外扩偏移元数据（vector_offset_x/y），
            # 否则居中/外描边会在画布合成时丢失负偏移，表现为内容相对形状“右下偏移”。
            vector_offset_x = int(getattr(final_result, 'info', {}).get('vector_offset_x', 0))
            vector_offset_y = int(getattr(final_result, 'info', {}).get('vector_offset_y', 0))
            try:
                final_result = self._bleed_transparent_edges(final_result)
                final_result.info["vector_offset_x"] = vector_offset_x
                final_result.info["vector_offset_y"] = vector_offset_y
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in layer_new.py")
                pass
            self._set_effects_stage_cache(stage3_key, final_result)

        self._render_offset_x = int(getattr(final_result, 'info', {}).get('vector_offset_x', 0))
        self._render_offset_y = int(getattr(final_result, 'info', {}).get('vector_offset_y', 0))
        if _LAYER_RENDER_VERBOSE:
            print(f"应用特效后图像尺寸: {final_result.width}x{final_result.height}, 图层尺寸: {self.width}x{self.height}")
        return final_result
    
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
    
    def _apply_corner_radius_improved(self, image):
        """改进的圆角处理"""
        if image is None or self.corner_radius <= 0:
            return image
        
        try:
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # 创建圆角蒙版
            mask = self._create_optimized_corner_mask(self.width, self.height, self.corner_radius)
            # 通过Alpha乘法保持正确边缘过渡（min()会导致半透明边缘台阶）
            return self._apply_mask_to_image(image, mask)
            
        except Exception as e:
            print(f"应用圆角效果时出错: {e}")
            return image
    
    def _get_mask_supersample_scale(self, width, height, edge_size=0):
        """根据图层尺寸与边缘复杂度动态选择超采样倍数。"""
        min_side = max(1, min(int(width), int(height)))
        edge_size = max(0, int(edge_size))

        # 边缘质量优先：避免在大图层上降到2x导致圆角/描边内线台阶
        if min_side <= 256:
            scale = 8
        elif min_side <= 1024:
            scale = 7
        elif min_side <= 2048:
            scale = 6
        else:
            scale = 5

        # 小圆角/细描边对采样更敏感，提升采样倍数
        if edge_size <= 4:
            scale = max(scale, 8 if min_side <= 1024 else 6)
        elif edge_size <= 10:
            scale = max(scale, 7 if min_side <= 1024 else 6)

        log_sampling("layer_new.mask_scale", width, height, edge_size, scale)
        return scale
    
    def _create_antialiased_rounded_rect_mask(self, width, height, radius):
        """使用超采样生成高质量圆角矩形蒙版。"""
        width = max(1, int(width))
        height = max(1, int(height))
        radius = max(0, min(int(radius), min(width, height) // 2))
        
        if radius <= 0:
            return Image.new('L', (width, height), 255)
        
        scale = self._get_mask_supersample_scale(width, height, radius)
        large_size = (width * scale, height * scale)
        large_radius = radius * scale
        
        large_mask = Image.new('L', large_size, 0)
        draw = ImageDraw.Draw(large_mask)
        draw.rounded_rectangle(
            (0, 0, large_size[0] - 1, large_size[1] - 1),
            radius=large_radius,
            fill=255
        )
        
        return large_mask.resize((width, height), Resampling.LANCZOS)
    
    def _create_antialiased_rounded_ring_mask(self, width, height, outer_radius, inset, inner_radius):
        """使用超采样生成高质量圆角环带蒙版（用于描边）。"""
        width = max(1, int(width))
        height = max(1, int(height))
        inset = max(0, int(inset))
        outer_radius = max(0, min(int(outer_radius), min(width, height) // 2))
        inner_radius = max(0, min(int(inner_radius), min(width, height) // 2))
        
        scale = self._get_mask_supersample_scale(width, height, max(outer_radius, inset))
        large_width = width * scale
        large_height = height * scale
        
        large_mask = Image.new('L', (large_width, large_height), 0)
        draw = ImageDraw.Draw(large_mask)
        
        draw.rounded_rectangle(
            (0, 0, large_width - 1, large_height - 1),
            radius=outer_radius * scale,
            fill=255
        )
        
        if inset > 0 and inset * 2 < width and inset * 2 < height:
            large_inset = inset * scale
            draw.rounded_rectangle(
                (
                    large_inset,
                    large_inset,
                    large_width - large_inset - 1,
                    large_height - large_inset - 1
                ),
                radius=inner_radius * scale,
                fill=0
            )
        
        return large_mask.resize((width, height), Resampling.LANCZOS)
    
    def _create_optimized_corner_mask(self, width, height, radius):
        """创建优化的圆角蒙版"""
        try:
            return self._create_antialiased_rounded_rect_mask(width, height, radius)
            
        except Exception as e:
            print(f"创建圆角蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            return mask
    
    def _apply_inner_stroke(self, image):
        """应用内向描边效果"""
        if image is None or self.stroke_width <= 0:
            return image
        
        try:
            # 保持原始图层尺寸
            result_width = self.width
            result_height = self.height
            
            # 创建描边蒙版
            stroke_width = min(self.stroke_width, min(result_width, result_height) // 4)
            stroke_mask = self._create_stroke_mask(result_width, result_height, stroke_width, self.corner_radius)
            
            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self.stroke_color)
            stroke_layer.putalpha(stroke_mask)
            
            # 合成
            result = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
            result = Image.alpha_composite(result, stroke_layer)
            
            # 缩放原图像以适应内容区域
            if stroke_width * 2 < result_width and stroke_width * 2 < result_height:
                content_width = result_width - stroke_width * 2
                content_height = result_height - stroke_width * 2
                scaled_image = self._resize_rgba_premultiplied(image, (content_width, content_height), Resampling.LANCZOS)
                
                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (stroke_width, stroke_width), scaled_image)
                
                if self.shape_type == ShapeType.RECTANGLE:
                    inner_radius = max(0, self.corner_radius - stroke_width) if self.corner_radius > 0 else 0
                    content_mask = self._create_antialiased_rounded_rect_mask(content_width, content_height, inner_radius)
                    alpha_canvas = Image.new('L', (result_width, result_height), 0)
                    alpha_canvas.paste(content_mask, (stroke_width, stroke_width))
                    content_layer = self._apply_mask_to_image(content_layer, alpha_canvas)
                
                # 合成内容
                result = Image.alpha_composite(result, content_layer)
            
            return result
            
        except Exception as e:
            print(f"应用内向描边效果时出错: {e}")
            return image
    
    def _create_stroke_mask(self, width, height, stroke_width, corner_radius):
        """创建描边蒙版（内描边）"""
        try:
            # 非矩形形状使用形状蒙版的形态学腐蚀生成等宽描边
            if self.shape_type != ShapeType.RECTANGLE:
                base = self._create_shape_mask(width, height)
                k = max(3, stroke_width * 2 + 1)
                inner = base.filter(ImageFilter.MinFilter(k))
                stroke = ImageChops.subtract(base, inner)
                return stroke
            
            # 矩形继续使用圆角优化路径
            outer_radius = corner_radius if corner_radius > 0 else 0
            inner_radius = max(0, corner_radius - stroke_width) if corner_radius > 0 else 0
            return self._create_antialiased_rounded_ring_mask(
                width=width,
                height=height,
                outer_radius=outer_radius,
                inset=stroke_width,
                inner_radius=inner_radius
            )
        except Exception as e:
            print(f"创建描边蒙版时出错: {e}")
            return Image.new('L', (width, height), 255)
    
    def _apply_center_stroke(self, image):
        """应用居中描边效果"""
        if image is None or self.stroke_width <= 0:
            return image
        
        try:
            result_width = self.width
            result_height = self.height
            
            # 居中描边：一半向内，一半向外
            half_stroke = self.stroke_width / 2.0
            inner_stroke = int(half_stroke)
            
            # 创建居中描边蒙版
            stroke_mask = self._create_center_stroke_mask(result_width, result_height, inner_stroke, self.corner_radius)
            
            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self.stroke_color)
            stroke_layer.putalpha(stroke_mask)
            
            # 合成
            result = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
            result = Image.alpha_composite(result, stroke_layer)
            
            # 缩放原图像以适应内容区域
            if inner_stroke * 2 < result_width and inner_stroke * 2 < result_height:
                content_width = result_width - inner_stroke * 2
                content_height = result_height - inner_stroke * 2
                scaled_image = self._resize_rgba_premultiplied(image, (content_width, content_height), Resampling.LANCZOS)
                
                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (inner_stroke, inner_stroke), scaled_image)
                
                if self.shape_type == ShapeType.RECTANGLE:
                    inner_radius = max(0, self.corner_radius - inner_stroke) if self.corner_radius > 0 else 0
                    content_mask = self._create_antialiased_rounded_rect_mask(content_width, content_height, inner_radius)
                    alpha_canvas = Image.new('L', (result_width, result_height), 0)
                    alpha_canvas.paste(content_mask, (inner_stroke, inner_stroke))
                    content_layer = self._apply_mask_to_image(content_layer, alpha_canvas)
                
                # 合成内容
                result = Image.alpha_composite(result, content_layer)
            
            return result
            
        except Exception as e:
            print(f"应用居中描边效果时出错: {e}")
            return image
    
    def _create_center_stroke_mask(self, width, height, inner_stroke, corner_radius):
        """创建居中描边蒙版（等宽环带，适配异形）"""
        try:
            if self.shape_type != ShapeType.RECTANGLE:
                base = self._create_shape_mask(width, height)
                k = max(3, inner_stroke * 2 + 1)
                dilated = base.filter(ImageFilter.MaxFilter(k))
                eroded = base.filter(ImageFilter.MinFilter(k))
                stroke = ImageChops.subtract(dilated, eroded)
                return stroke
            
            # 矩形继续原逻辑
            outer_radius = corner_radius + inner_stroke if corner_radius > 0 else inner_stroke
            inner_radius = max(0, corner_radius - inner_stroke) if corner_radius > 0 else 0
            return self._create_antialiased_rounded_ring_mask(
                width=width,
                height=height,
                outer_radius=outer_radius,
                inset=inner_stroke,
                inner_radius=inner_radius
            )
        except Exception as e:
            print(f"创建居中描边蒙版时出错: {e}")
            return Image.new('L', (width, height), 255)
    
    def _apply_outer_stroke(self, image):
        """应用外描边效果"""
        if image is None or self.stroke_width <= 0:
            return image
        
        try:
            # 外描边会增加图层尺寸
            stroke_width = self.stroke_width
            expanded_width = self.width + stroke_width * 2
            expanded_height = self.height + stroke_width * 2
            
            # 创建扩展画布
            expanded_image = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))
            
            # 创建外描边蒙版
            stroke_mask = self._create_outer_stroke_mask(expanded_width, expanded_height, stroke_width, self.corner_radius)
            
            # 创建描边图层
            stroke_layer = Image.new('RGBA', (expanded_width, expanded_height), self.stroke_color)
            stroke_layer.putalpha(stroke_mask)
            
            # 合成描边
            expanded_image = Image.alpha_composite(expanded_image, stroke_layer)
            
            # 将内容图层放到中央，并按内轮廓精确裁切（避免圆角/描边公差）
            content_layer = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))
            content_layer.paste(image, (stroke_width, stroke_width), image)
            if self.shape_type == ShapeType.RECTANGLE:
                inner_radius = max(0, self.corner_radius)
                content_mask = self._create_antialiased_rounded_rect_mask(self.width, self.height, inner_radius)
                alpha_canvas = Image.new('L', (expanded_width, expanded_height), 0)
                alpha_canvas.paste(content_mask, (stroke_width, stroke_width))
                content_layer = self._apply_mask_to_image(content_layer, alpha_canvas)
            expanded_image = Image.alpha_composite(expanded_image, content_layer)
            
            return expanded_image
            
        except Exception as e:
            print(f"应用外描边效果时出错: {e}")
            return image
    
    def _create_outer_stroke_mask(self, width, height, stroke_width, corner_radius):
        """创建外描边蒙版（支持异形）"""
        try:
            if self.shape_type != ShapeType.RECTANGLE:
                # 在扩展画布上创建原始形状蒙版
                base = Image.new('L', (width, height), 0)
                inner = Image.new('L', (width, height), 0)
                # 在中心偏移处绘制原形状
                original = self._create_shape_mask(width - stroke_width * 2, height - stroke_width * 2)
                inner.paste(original, (stroke_width, stroke_width))
                # 膨胀得到外缘
                k = max(3, stroke_width * 2 + 1)
                dilated = inner.filter(ImageFilter.MaxFilter(k))
                stroke = ImageChops.subtract(dilated, inner)
                return stroke
            
            # 矩形继续原逻辑
            outer_radius = corner_radius + stroke_width if corner_radius > 0 else stroke_width
            inner_radius = corner_radius if corner_radius > 0 else 0
            return self._create_antialiased_rounded_ring_mask(
                width=width,
                height=height,
                outer_radius=outer_radius,
                inset=stroke_width,
                inner_radius=inner_radius
            )
        except Exception as e:
            print(f"创建外描边蒙版时出错: {e}")
            return Image.new('L', (width, height), 255)
    
    def _create_error_image(self):
        """创建错误图像（红色底色）"""
        return Image.new('RGBA', (self.width, self.height), (255, 0, 0, 128))
    
    def _apply_shape_mask(self, image):
        """应用形状蒙版到图像"""
        if image is None:
            return None
            
        # 创建形状蒙版
        shape_mask = self._create_shape_mask(image.width, image.height)
        
        # 应用蒙版
        return self._apply_mask_to_image(image, shape_mask)
    
    def _create_shape_mask(self, width, height):
        """创建形状蒙版 - 带缓存优化"""
        # 创建缓存键，包含所有影响形状的属性
        cache_key = (
            width, height, self.shape_type.value,
            self.corner_radius, self.trapezoid_top_width, self.trapezoid_bottom_width,
            self.trapezoid_slope_side, self.polygon_rotation, self.polygon_corner_radius
        )
        
        # 检查缓存
        if not hasattr(self, '_shape_mask_cache'):
            self._shape_mask_cache = {}
        
        if cache_key in self._shape_mask_cache:
            return self._shape_mask_cache[cache_key].copy()
        
        from PIL import ImageDraw
        
        # 创建透明蒙版
        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)
        
        shape_type = self.shape_type
        
        if shape_type == ShapeType.RECTANGLE:
            # 矩形 - 使用传统圆角处理
            if self.corner_radius > 0:
                radius = min(self.corner_radius, min(width, height) // 2)
                draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            else:
                draw.rectangle((0, 0, width-1, height-1), fill=255)
                
        elif shape_type == ShapeType.RIGHT_TRAPEZOID:
            # 直角梯形
            self._draw_right_trapezoid(draw, width, height)
            
        elif shape_type == ShapeType.CIRCLE:
            # 圆形
            self._draw_circle(draw, width, height)
            
        elif shape_type == ShapeType.PENTAGON:
            # 正五边形
            self._draw_regular_polygon(draw, width, height, 5)
            
        elif shape_type == ShapeType.HEXAGON:
            # 正六边形
            self._draw_regular_polygon(draw, width, height, 6)
            
        # 缓存结果
        self._shape_mask_cache[cache_key] = mask.copy()
        return mask
    
    def _draw_right_trapezoid(self, draw, width, height):
        """绘制直角梯形"""
        import math
        
        # 将百分比转换为实际像素值
        top_width_pixels = int(width * self.trapezoid_top_width / 100)
        bottom_width_pixels = int(width * self.trapezoid_bottom_width / 100)
        
        # 确保宽度不超过画布宽度
        top_width = min(top_width_pixels, width)
        bottom_width = min(bottom_width_pixels, width)
        
        # 计算梯形各顶点坐标
        if self.trapezoid_slope_side == "right":
            # 斜边在右侧
            points = [
                (0, 0),  # 左上
                (top_width, 0),  # 右上
                (bottom_width, height),  # 右下
                (0, height)  # 左下
            ]
        else:
            # 斜边在左侧
            points = [
                (width - top_width, 0),  # 左上
                (width, 0),  # 右上
                (width, height),  # 右下
                (width - bottom_width, height)  # 左下
            ]
        
        draw.polygon(points, fill=255)
    
    def _draw_circle(self, draw, width, height):
        """绘制圆形"""
        import math
        
        # 确保圆形在边界内，留一点边距
        margin = 2
        diameter = min(width, height) - margin * 2
        center_x = width // 2
        center_y = height // 2
        radius = diameter // 2
        
        # 绘制圆形
        bbox = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)
        draw.ellipse(bbox, fill=255)
        
        # 如果有多边形圆角设置，应用轻微的内圆角
        if self.polygon_corner_radius > 0:
            self._apply_polygon_corner_radius(draw, width, height, [(center_x, center_y)], radius)
    
    def _draw_regular_polygon(self, draw, width, height, sides):
        """绘制正多边形"""
        import math
        
        center_x = width // 2
        center_y = height // 2
        
        # 计算内切圆半径（确保多边形在边界内）
        margin = 5
        max_radius = min(width, height) // 2 - margin
        
        # 生成多边形顶点
        points = []
        for i in range(sides):
            angle = 2 * math.pi * i / sides + math.radians(self.polygon_rotation)
            x = center_x + max_radius * math.cos(angle - math.pi / 2)  # -pi/2让顶点朝上
            y = center_y + max_radius * math.sin(angle - math.pi / 2)
            points.append((int(x), int(y)))
        
        # 绘制多边形
        draw.polygon(points, fill=255)
        
        # 应用多边形圆角
        if self.polygon_corner_radius > 0:
            self._apply_polygon_corner_radius(draw, width, height, points, max_radius)
    
    def _apply_polygon_corner_radius(self, draw, width, height, vertices, max_radius):
        """应用多边形圆角效果"""
        import math
        
        if self.polygon_corner_radius <= 0 or len(vertices) < 3:
            return
            
        # 限制圆角半径
        corner_radius = min(self.polygon_corner_radius, max_radius // 4)
        
        # 在顶点处绘制小圆角
        for i, (x, y) in enumerate(vertices):
            next_i = (i + 1) % len(vertices)
            prev_i = (i - 1) % len(vertices)
            
            # 计算顶点处的圆角
            prev_vertex = vertices[prev_i]
            next_vertex = vertices[next_i]
            
            # 绘制小圆角
            small_radius = min(corner_radius, 5)  # 限制小圆角大小
            draw.ellipse((x - small_radius, y - small_radius, 
                         x + small_radius, y + small_radius), fill=255)
    
    def _apply_mask_to_image(self, image, mask):
        if image is None or mask is None:
            return image
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        from PIL import ImageChops
        r, g, b, a = image.split()
        new_alpha = ImageChops.multiply(a, mask)
        return Image.merge('RGBA', (r, g, b, new_alpha))
    
    def serialize(self):
        """将图层序列化为字典"""
        # 获取属性管理器序列化的数据
        data = self._property_manager.serialize_properties()
        
        # 添加图层特有属性
        data.update({
            'layer_id': self._layer_id,
            'layer_type': 'Layer',
            'random_position_enabled': self._random_position_enabled,
            'random_position_range': self._random_position_range,
            'random_scale_enabled': self._random_scale_enabled,
            'random_scale_min': self._random_scale_min,
            'random_scale_max': self._random_scale_max,
            'random_rotation_enabled': self._random_rotation_enabled,
            'random_rotation_range': self._random_rotation_range,
        })
        
        return data

    # 兼容别名：历史记录(document.save_state/_restore_state)使用 to_dict/from_dict
    def to_dict(self):
        """序列化图层的别名，供文档历史记录使用"""
        return self.serialize()

    @classmethod
    def from_dict(cls, data, parent=None):
        """反序列化图层的别名，供文档历史记录使用。
        根据图层类型标记选择具体子类，保证 TextLayer/ShapedLayer 撤销后类型不退化。"""
        layer_type = data.get('layer_type') or data.get('type')
        target_cls = cls
        if layer_type == 'TextLayer' or layer_type == 'text':
            from app.models.text_layer import TextLayer
            target_cls = TextLayer
        elif layer_type == 'ShapedLayer':
            from app.models.shaped_layer_new import ShapedLayer
            target_cls = ShapedLayer
        if not hasattr(target_cls, 'deserialize'):
            target_cls = cls
        return target_cls.deserialize(data, parent=parent)
    
    def duplicate(self, parent=None):
        """复制图层，创建一个完全相同的新实例"""
        # 序列化当前图层
        data = self.serialize()
        
        # 反序列化创建新实例
        return self.deserialize(data, parent=parent if parent is not None else self.parent())
    
    @classmethod
    def deserialize(cls, data, parent=None):
        """从字典反序列化图层"""
        # 创建新实例
        layer = cls(parent=parent)
        
        # 反序列化属性
        if 'layer_id' in data:
            layer._layer_id = data['layer_id']
        
        # 使用属性管理器反序列化
        properties_data = {k: v for k, v in data.items() if k not in ['layer_id', 'layer_type']}
        layer._property_manager.deserialize_properties(properties_data)

        # 恢复属性管理器之外的图层参数
        layer.random_position_enabled = data.get('random_position_enabled', False)
        layer.random_position_range = data.get('random_position_range', 10)
        layer.random_scale_enabled = data.get('random_scale_enabled', False)
        layer.random_scale_min = data.get('random_scale_min', 0.9)
        layer.random_scale_max = data.get('random_scale_max', 1.1)
        layer.random_rotation_enabled = data.get('random_rotation_enabled', False)
        layer.random_rotation_range = data.get('random_rotation_range', 5.0)
        
        return layer
    def _resize_rgba_premultiplied(self, image, size, resample=Resampling.LANCZOS):
        from app.utils.rgba_resampler import resize_rgba_premultiplied

        return resize_rgba_premultiplied(image, size, resample)

    def _rotate_rgba_premultiplied(self, image, angle, resample=Resampling.BICUBIC, fillcolor=(0, 0, 0, 0)):
        from app.utils.rgba_resampler import rotate_rgba_premultiplied

        return rotate_rgba_premultiplied(
            image,
            angle,
            resample=resample,
            expand=True,
            fillcolor=fillcolor,
        )

    def _bleed_transparent_edges(self, image: Image.Image) -> Image.Image:
        """将不透明区域的颜色向半透明边缘传播，避免白/黑边缘晕圈"""
        original_info = dict(getattr(image, "info", {}) or {})
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        arr = np.array(image, dtype=np.float32) / 255.0
        rgb = arr[:, :, :3]
        a = arr[:, :, 3:4]
        premul = rgb * a

        # 将各通道转换为图像以使用MaxFilter
        r_img = Image.fromarray((premul[:, :, 0] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))
        g_img = Image.fromarray((premul[:, :, 1] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))
        b_img = Image.fromarray((premul[:, :, 2] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))
        a_img = Image.fromarray((a[:, :, 0] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))

        r2 = np.array(r_img, dtype=np.float32) / 255.0
        g2 = np.array(g_img, dtype=np.float32) / 255.0
        b2 = np.array(b_img, dtype=np.float32) / 255.0
        a2 = np.array(a_img, dtype=np.float32) / 255.0

        eps = 1e-6
        rgb_bleed = np.stack([
            np.divide(r2, a2 + eps),
            np.divide(g2, a2 + eps),
            np.divide(b2, a2 + eps)
        ], axis=2)

        # 在半透明区域使用出血颜色，其它保持原色
        alpha_mask = (a[:, :, 0] > 0.0) & (a[:, :, 0] < 0.98)
        rgb_out = rgb.copy()
        rgb_out[alpha_mask] = rgb_bleed[alpha_mask]

        out = np.concatenate([np.clip(rgb_out, 0.0, 1.0), a], axis=2)
        result = Image.fromarray((out * 255.0).astype(np.uint8), 'RGBA')
        if original_info:
            result.info.update(original_info)
        return result

    def _apply_color_overlay(self, image):
        """应用颜色叠加"""
        if image is None or not self.color_overlay_enabled or self.color_overlay_opacity <= 0:
            return image
            
        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            # 获取颜色
            color = self.color_overlay_color
            if not isinstance(color, (list, tuple)):
                return image
                
            # 处理颜色格式
            if len(color) == 3:
                r, g, b = color
                a = 255
            elif len(color) >= 4:
                r, g, b, a = color[:4]
            else:
                return image
                
            # 创建纯色层
            overlay = Image.new('RGBA', image.size, (int(r), int(g), int(b), int(a)))
            
            # 使用原图的alpha通道作为蒙版
            orig_r, orig_g, orig_b, orig_a = image.split()
            overlay.putalpha(orig_a)
            
            # 混合
            return Image.blend(image, overlay, self.color_overlay_opacity)
            
        except Exception as e:
            print(f"应用颜色叠加出错: {e}")
            return image

    def _apply_gradient_overlay(self, image):
        """应用渐变叠加"""
        if image is None or not self.gradient_overlay_enabled or self.gradient_overlay_opacity <= 0:
            return image
            
        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            # 创建渐变层
            gradient = self._create_linear_gradient(
                image.width, 
                image.height, 
                self.gradient_overlay_colors, 
                self.gradient_overlay_angle
            )
            
            if gradient is None:
                return image
            
            # 使用原图的alpha通道作为蒙版
            orig_r, orig_g, orig_b, orig_a = image.split()
            
            # 确保gradient有alpha通道
            if gradient.mode != 'RGBA':
                gradient = gradient.convert('RGBA')
            
            grad_r, grad_g, grad_b, grad_a = gradient.split()
            
            # 组合alpha
            from PIL import ImageChops
            new_alpha = ImageChops.multiply(orig_a, grad_a)
            
            gradient.putalpha(new_alpha)
            
            # 混合
            return Image.blend(image, gradient, self.gradient_overlay_opacity)
            
        except Exception as e:
            print(f"应用渐变叠加出错: {e}")
            return image
            
    def _create_linear_gradient(self, width, height, colors, angle):
        """创建线性渐变图像"""
        try:
            import math
            
            if not colors or len(colors) < 2:
                # 默认黑白
                colors = [(0, 0, 0, 255), (255, 255, 255, 255)]
                
            # 计算角度
            rad = math.radians(angle)
            dx = math.cos(rad)
            dy = -math.sin(rad) # PIL坐标系Y轴向下
            
            # 中心点
            cx, cy = width / 2, height / 2
            
            # 计算投影范围
            corners = [
                (0, 0), (width, 0), (0, height), (width, height)
            ]
            projections = [x * dx + y * dy for x, y in corners]
            min_p = min(projections)
            max_p = max(projections)
            range_p = max_p - min_p
            if range_p == 0: range_p = 1
            
            # 生成网格
            x = np.arange(width)
            y = np.arange(height)
            xv, yv = np.meshgrid(x, y)
            
            # 计算投影并归一化
            p = xv * dx + yv * dy
            t = (p - min_p) / range_p
            t = np.clip(t, 0, 1)
            
            # 颜色插值
            num_stops = len(colors)
            
            if num_stops == 2:
                c1 = np.array(colors[0])
                c2 = np.array(colors[1])
                
                t_exp = t[:, :, np.newaxis]
                res = c1 * (1 - t_exp) + c2 * t_exp
                rgba = res.astype(np.uint8)
            else:
                # 简单处理多色：均匀分布
                # 更复杂的处理需要根据stops位置插值
                # 这里简化：将t映射到 0..num_stops-1
                scaled_t = t * (num_stops - 1)
                indices = np.floor(scaled_t).astype(int)
                indices = np.clip(indices, 0, num_stops - 2)
                
                local_t = scaled_t - indices
                local_t_exp = local_t[:, :, np.newaxis]
                
                # 准备颜色数组
                colors_arr = np.array(colors)
                c_start = colors_arr[indices]
                c_end = colors_arr[indices + 1]
                
                res = c_start * (1 - local_t_exp) + c_end * local_t_exp
                rgba = res.astype(np.uint8)
                
            return Image.fromarray(rgba, 'RGBA')
            
        except Exception as e:
            print(f"创建渐变出错: {e}")
            return None
