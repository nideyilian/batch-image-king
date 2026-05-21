from PySide6.QtCore import QObject, Signal, Property
import os
import builtins
import sys
import random
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from enum import Enum, auto
import copy  # 导入copy模块实现深拷贝
from collections import OrderedDict
import hashlib
import threading
from typing import List, Tuple
import math
from app.utils.image.high_quality_resampler import HighQualityResampler
from app.utils.render_diagnostics import log_branch


_LAYER_DEBUG = os.environ.get("BTPW_LAYER_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")


def print(*args, **kwargs):
    """Keep noisy layer diagnostics off the interactive preview path by default."""
    if _LAYER_DEBUG:
        builtins.print(*args, **kwargs)


def _is_batch_render_context() -> bool:
    """Cheap call-stack check used by legacy layer code.

    The previous inspect.stack() call allocates FrameInfo objects for the whole
    stack on every image load. Walking frames directly is much lighter and keeps
    the same behavior for batch/export detection.
    """
    frame = sys._getframe(1)
    checked = 0
    while frame is not None and checked < 32:
        name = frame.f_code.co_name
        if (
            "batch_export" in name
            or "render_batch" in name
            or "export_batch" in name
            or "generate_combinations" in name
        ):
            return True
        frame = frame.f_back
        checked += 1
    return False


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
    """图层模型类"""
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
                 use_original_size=False, is_folder=True, parent=None):
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
            parent: 父对象
        """
        super().__init__(parent)

        # 生成唯一的图层ID，确保每个图层完全独立
        import uuid
        self._layer_id = str(uuid.uuid4())

        # 基本属性
        self._name = name
        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._visible = True
        self._opacity = 1.0
        self._locked = False

        # 图像属性 - 确保每个图层有独立的图像缓存
        self._image_source = image_source
        self._is_folder = is_folder
        self._use_original_size = use_original_size
        self._current_image_path = None
        self._cached_image = None
        self._cached_image_path = None  # 明确定义缓存路径
        self._smart_crop_enabled = False  # 智能裁剪功能
        
        # 显示样式
        self._fit_mode = 0  # 0=拉伸适配, 1=等比缩放
        self._crop_direction = 0  # 0=居中, 1=顶部, 2=底部, 3=左侧, 4=右侧
        self._corner_radius = 0
        self._vector_corner_radius_tl = 0
        self._vector_corner_radius_tr = 0
        self._vector_corner_radius_br = 0
        self._vector_corner_radius_bl = 0
        self._vector_path_enabled = False
        self._vector_path_points = []
        self._vector_path_mode = "polygon"  # polygon/bezier
        self._vector_bezier_nodes = []
        self._vector_path_closed = True
        self._vector_handle_link_mode = "mirror"  # mirror/collinear/free
        self._stroke_enabled = False
        self._stroke_width = 1
        self._stroke_color = (0, 0, 0, 255)  # RGBA
        self._stroke_type = 0  # 0=内描边, 1=居中描边, 2=外描边
        self._stroke_join = "miter"  # miter/round/bevel
        self._stroke_cap = "butt"    # butt/round/square
        self._stroke_dash_length = 0
        self._stroke_dash_gap = 0
        
        # 颜色叠加
        self._color_overlay_enabled = False
        self._color_overlay_color = (255, 0, 0, 255)
        self._color_overlay_opacity = 1.0
        
        # 渐变叠加
        self._gradient_overlay_enabled = False
        self._gradient_overlay_colors = [(0, 0, 0, 255), (255, 255, 255, 255)]  # Start, End
        self._gradient_overlay_angle = 90.0
        self._gradient_overlay_opacity = 1.0
        self._gradient_overlay_scale = 1.0  # Reserved
        self._gradient_overlay_reverse = False # Reserved
        
        # 混合模式
        self._blend_mode = 0  # 默认为普通模式
        
        # 图层分身设置
        self._clone_enabled = False  # 是否启用分身
        self._clone_rows = 1  # 分身行数
        self._clone_columns = 1  # 分身列数
        self._clone_row_spacing = 0  # 行间距
        self._clone_column_spacing = 0  # 列间距
        self._clone_custom_size_enabled = False  # 是否启用分身自定义大小
        self._clone_custom_width = 0  # 分身自定义宽度（0表示使用原图大小）
        self._clone_custom_height = 0  # 分身自定义高度（0表示使用原图大小）
        
        # 图层绑定设置
        self._bind_enabled = False  # 是否启用绑定功能
        self._bind_group = None  # 绑定组名称，相同组名的图层会绑定
        self._bind_strategy = "filename"  # 绑定策略：filename(文件名匹配) / folder(文件夹结构匹配)
        
        # 变换属性
        self._rotation = 0.0  # 旋转角度（度）
        self._flip_horizontal = False  # 水平翻转
        self._flip_vertical = False  # 垂直翻转

        # 尺寸锁定属性
        self._aspect_ratio_locked = False  # 是否锁定宽高比

        # 状态隔离标志
        self._state_dirty = False  # 标记图层状态是否需要更新
        self._cache_valid = False  # 标记缓存是否有效
        self._updating = False  # 防止递归更新
        
        # 随机变换属性 - 与手动变换分离，不冲突
        self._random_position_enabled = False  # 启用随机位置抖动
        self._random_position_range = 10  # 位置抖动范围（像素）
        self._random_scale_enabled = False  # 启用随机缩放
        self._random_scale_min = 0.9  # 最小缩放比例
        self._random_scale_max = 1.1  # 最大缩放比例
        self._random_rotation_enabled = False  # 启用随机旋转
        self._random_rotation_range = 5.0  # 随机旋转角度范围（度）
        
        # 当前随机变换状态（每次随机时生成）
        self._current_random_offset_x = 0
        self._current_random_offset_y = 0
        self._current_random_scale = 1.0
        self._current_random_rotation = 0.0
        
        # 如果图像源是单个文件，直接设置
        if image_source and not is_folder and os.path.isfile(image_source):
            self._current_image_path = image_source
    
    # 属性访问器
    @property
    def name(self):
        return self._name
        
    @name.setter
    def name(self, value):
        if self._updating:
            return
        if self._name != value:
            self._updating = True
            try:
                self._name = value
                self._mark_dirty()
                self.changed.emit()
            finally:
                self._updating = False
    
    @property
    def x(self):
        return self._x
    
    @x.setter
    def x(self, value):
        if self._x != value:
            self._x = value
            self.changed.emit()
    
    @property
    def y(self):
        return self._y
    
    @y.setter
    def y(self, value):
        if self._y != value:
            self._y = value
            self.changed.emit()
    
    @property
    def width(self):
        return self._width
    
    @width.setter
    def width(self, value):
        if self._width != value and value > 0:
            self._width = value
            self.changed.emit()
    
    @property
    def height(self):
        return self._height
    
    @height.setter
    def height(self, value):
        if self._height != value and value > 0:
            self._height = value
            self.changed.emit()
    
    @property
    def visible(self):
        return self._visible
    
    @visible.setter
    def visible(self, value):
        if self._updating:
            return
        if self._visible != value:
            self._updating = True
            try:
                self._visible = value
                self._mark_dirty()
                self.changed.emit()
            finally:
                self._updating = False
    
    @property
    def opacity(self):
        return self._opacity
    
    @opacity.setter
    def opacity(self, value):
        if self._updating:
            return
        if self._opacity != value:
            self._updating = True
            try:
                self._opacity = max(0.0, min(1.0, value))
                self._mark_dirty()
                self.changed.emit()
            finally:
                self._updating = False
    
    @property
    def locked(self):
        return self._locked
    
    @locked.setter
    def locked(self, value):
        if self._locked != value:
            self._locked = value
            self.changed.emit()
    
    @property
    def image_source(self):
        return self._image_source
    
    @image_source.setter
    def image_source(self, value):
        if self._image_source != value:
            self._image_source = value
            self._cached_image = None
            self.changed.emit()
    
    @property
    def is_folder(self):
        return self._is_folder
    
    @is_folder.setter
    def is_folder(self, value):
        if self._is_folder != value:
            self._is_folder = value
            self._cached_image = None
            self.changed.emit()
    
    @property
    def use_original_size(self):
        return self._use_original_size
    
    @use_original_size.setter
    def use_original_size(self, value):
        if self._use_original_size != value:
            self._use_original_size = value
            self._cached_image = None
            self.changed.emit()
    
    @property
    def fit_mode(self):
        return self._fit_mode
    
    @fit_mode.setter
    def fit_mode(self, value):
        if self._fit_mode != value:
            self._fit_mode = value
            self._cached_image = None
            self.changed.emit()
    
    @property
    def crop_direction(self):
        return self._crop_direction
    
    @crop_direction.setter
    def crop_direction(self, value):
        if self._crop_direction != value:
            self._crop_direction = value
            self._cached_image = None
            self.changed.emit()
    
    @property
    def blend_mode(self):
        return self._blend_mode
    
    @blend_mode.setter
    def blend_mode(self, value):
        if self._blend_mode != value:
            self._blend_mode = value
            self.changed.emit()
    
    @property
    def clone_enabled(self):
        return self._clone_enabled
        
    @clone_enabled.setter
    def clone_enabled(self, value):
        if self._clone_enabled != value:
            self._clone_enabled = value
            self.changed.emit()
    
    @property
    def clone_rows(self):
        return self._clone_rows
        
    @clone_rows.setter
    def clone_rows(self, value):
        if self._clone_rows != value and value > 0:
            self._clone_rows = value
            self.changed.emit()
    
    @property
    def clone_columns(self):
        return self._clone_columns
        
    @clone_columns.setter
    def clone_columns(self, value):
        if self._clone_columns != value and value > 0:
            self._clone_columns = value
            self.changed.emit()
    
    @property
    def clone_row_spacing(self):
        return self._clone_row_spacing
        
    @clone_row_spacing.setter
    def clone_row_spacing(self, value):
        if self._clone_row_spacing != value and value >= 0:
            self._clone_row_spacing = value
            self.changed.emit()
    
    @property
    def clone_column_spacing(self):
        return self._clone_column_spacing
    
    @clone_column_spacing.setter
    def clone_column_spacing(self, value):
        if self._clone_column_spacing != value:
            self._clone_column_spacing = max(0, value)
            self.changed.emit()
    
    @property
    def clone_custom_size_enabled(self):
        return self._clone_custom_size_enabled
    
    @clone_custom_size_enabled.setter
    def clone_custom_size_enabled(self, value):
        if self._clone_custom_size_enabled != value:
            self._clone_custom_size_enabled = value
            self.cached_image = None
            self.changed.emit()
    
    @property
    def clone_custom_width(self):
        return self._clone_custom_width
    
    @clone_custom_width.setter
    def clone_custom_width(self, value):
        if self._clone_custom_width != value and value >= 0:
            self._clone_custom_width = value
            self.cached_image = None
            self.changed.emit()
    
    @property
    def clone_custom_height(self):
        return self._clone_custom_height
    
    @clone_custom_height.setter
    def clone_custom_height(self, value):
        if self._clone_custom_height != value and value >= 0:
            self._clone_custom_height = value
            self.cached_image = None
            self.changed.emit()

    # 圆角和描边属性访问器
    @property
    def corner_radius(self):
        return self._corner_radius

    @corner_radius.setter
    def corner_radius(self, value):
        if self._corner_radius != value:
            self._corner_radius = max(0, value)
            # 🔧 修复：清除所有缓存
            self._cached_image = None
            if hasattr(self, 'cached_image'):
                self.cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_corner_radius_tl(self):
        return self._vector_corner_radius_tl

    @vector_corner_radius_tl.setter
    def vector_corner_radius_tl(self, value):
        value = max(0, int(value))
        if self._vector_corner_radius_tl != value:
            self._vector_corner_radius_tl = value
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_corner_radius_tr(self):
        return self._vector_corner_radius_tr

    @vector_corner_radius_tr.setter
    def vector_corner_radius_tr(self, value):
        value = max(0, int(value))
        if self._vector_corner_radius_tr != value:
            self._vector_corner_radius_tr = value
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_corner_radius_br(self):
        return self._vector_corner_radius_br

    @vector_corner_radius_br.setter
    def vector_corner_radius_br(self, value):
        value = max(0, int(value))
        if self._vector_corner_radius_br != value:
            self._vector_corner_radius_br = value
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_corner_radius_bl(self):
        return self._vector_corner_radius_bl

    @vector_corner_radius_bl.setter
    def vector_corner_radius_bl(self, value):
        value = max(0, int(value))
        if self._vector_corner_radius_bl != value:
            self._vector_corner_radius_bl = value
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_path_enabled(self):
        return self._vector_path_enabled

    @vector_path_enabled.setter
    def vector_path_enabled(self, value):
        normalized = bool(value)
        if self._vector_path_enabled != normalized:
            self._vector_path_enabled = normalized
            if normalized and not self._vector_path_points:
                self.convert_rect_to_vector_path()
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_path_points(self):
        return copy.deepcopy(self._vector_path_points)

    @vector_path_points.setter
    def vector_path_points(self, value):
        normalized = self._normalize_vector_path_points(value)
        if self._vector_path_points != normalized:
            self._vector_path_points = normalized
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_path_mode(self):
        return self._vector_path_mode

    @vector_path_mode.setter
    def vector_path_mode(self, value):
        normalized = str(value).lower()
        if normalized not in {"polygon", "bezier"}:
            normalized = "polygon"
        if self._vector_path_mode != normalized:
            self._vector_path_mode = normalized
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_bezier_nodes(self):
        return copy.deepcopy(self._vector_bezier_nodes)

    @vector_bezier_nodes.setter
    def vector_bezier_nodes(self, value):
        normalized = self._normalize_vector_bezier_nodes(value)
        if self._vector_bezier_nodes != normalized:
            self._vector_bezier_nodes = normalized
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_path_closed(self):
        return bool(self._vector_path_closed)

    @vector_path_closed.setter
    def vector_path_closed(self, value):
        normalized = bool(value)
        if self._vector_path_closed != normalized:
            self._vector_path_closed = normalized
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def vector_handle_link_mode(self):
        return self._vector_handle_link_mode

    @vector_handle_link_mode.setter
    def vector_handle_link_mode(self, value):
        normalized = str(value).lower()
        if normalized not in {"mirror", "collinear", "free"}:
            normalized = "mirror"
        if self._vector_handle_link_mode != normalized:
            self._vector_handle_link_mode = normalized
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def stroke_enabled(self):
        return self._stroke_enabled

    @stroke_enabled.setter
    def stroke_enabled(self, value):
        if self._stroke_enabled != value:
            self._stroke_enabled = value
            # 🔧 修复：清除所有缓存
            self._cached_image = None
            if hasattr(self, 'cached_image'):
                self.cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            print(f"[图层] 描边状态改变为: {value}，已清除缓存")
            self.changed.emit()

    @property
    def stroke_width(self):
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, value):
        if self._stroke_width != value:
            self._stroke_width = max(1, value)
            # 🔧 修复：清除所有缓存
            self._cached_image = None
            if hasattr(self, 'cached_image'):
                self.cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def stroke_color(self):
        return self._stroke_color

    @stroke_color.setter
    def stroke_color(self, value):
        if self._stroke_color != value:
            # 确保颜色值在有效范围内
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                r = max(0, min(255, int(value[0])))
                g = max(0, min(255, int(value[1])))
                b = max(0, min(255, int(value[2])))
                a = max(0, min(255, int(value[3]))) if len(value) > 3 else 255
                self._stroke_color = (r, g, b, a)
                # 🔧 修复：清除所有缓存
                self._cached_image = None
                if hasattr(self, 'cached_image'):
                    self.cached_image = None
                if hasattr(self, '_cache_valid'):
                    self._cache_valid = False
                self.changed.emit()

    @property
    def stroke_type(self):
        return self._stroke_type

    @stroke_type.setter
    def stroke_type(self, value):
        if self._stroke_type != value:
            self._stroke_type = max(0, min(2, int(value)))  # 限制在0-2范围内
            # 🔧 修复：清除所有缓存
            self._cached_image = None
            if hasattr(self, 'cached_image'):
                self.cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def stroke_join(self):
        return self._stroke_join

    @stroke_join.setter
    def stroke_join(self, value):
        allowed = {"miter", "round", "bevel"}
        normalized = value if value in allowed else "miter"
        if self._stroke_join != normalized:
            self._stroke_join = normalized
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def stroke_cap(self):
        return self._stroke_cap

    @stroke_cap.setter
    def stroke_cap(self, value):
        allowed = {"butt", "round", "square"}
        normalized = value if value in allowed else "butt"
        if self._stroke_cap != normalized:
            self._stroke_cap = normalized
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def stroke_dash_length(self):
        return self._stroke_dash_length

    @stroke_dash_length.setter
    def stroke_dash_length(self, value):
        value = max(0, int(value))
        if self._stroke_dash_length != value:
            self._stroke_dash_length = value
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    @property
    def stroke_dash_gap(self):
        return self._stroke_dash_gap

    @stroke_dash_gap.setter
    def stroke_dash_gap(self, value):
        value = max(0, int(value))
        if self._stroke_dash_gap != value:
            self._stroke_dash_gap = value
            self._cached_image = None
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.changed.emit()

    def _normalize_vector_path_points(self, points):
        """标准化路径点结构为 [[x,y], ...]"""
        normalized = []
        if not isinstance(points, (list, tuple)):
            return normalized
        for pt in points:
            if isinstance(pt, dict):
                x = pt.get('x')
                y = pt.get('y')
            elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                x, y = pt[0], pt[1]
            else:
                continue
            try:
                normalized.append([float(x), float(y)])
            except Exception:
                continue
        return normalized

    def _normalize_vector_bezier_nodes(self, nodes):
        """标准化贝塞尔节点结构"""
        normalized = []
        if not isinstance(nodes, (list, tuple)):
            return normalized
        for n in nodes:
            if not isinstance(n, dict):
                continue
            try:
                x = float(n.get('x', 0.0))
                y = float(n.get('y', 0.0))
                in_x = float(n.get('in_x', x))
                in_y = float(n.get('in_y', y))
                out_x = float(n.get('out_x', x))
                out_y = float(n.get('out_y', y))
            except Exception:
                continue
            normalized.append({
                'x': x,
                'y': y,
                'in_x': in_x,
                'in_y': in_y,
                'out_x': out_x,
                'out_y': out_y,
                'node_type': str(n.get('node_type', 'corner')).lower() if str(n.get('node_type', 'corner')).lower() in {'corner', 'smooth', 'symmetric'} else 'corner',
            })
        return normalized

    def convert_rect_to_vector_path(self):
        """将当前矩形边界转换为可编辑路径节点"""
        self._vector_path_points = [
            [0.0, 0.0],
            [float(self._width), 0.0],
            [float(self._width), float(self._height)],
            [0.0, float(self._height)],
        ]
        self._vector_path_enabled = True
        self._vector_path_mode = "bezier"
        self._vector_bezier_nodes = [
            {'x': 0.0, 'y': 0.0, 'in_x': 0.0, 'in_y': 0.0, 'out_x': 0.0, 'out_y': 0.0, 'node_type': 'corner'},
            {'x': float(self._width), 'y': 0.0, 'in_x': float(self._width), 'in_y': 0.0, 'out_x': float(self._width), 'out_y': 0.0, 'node_type': 'corner'},
            {'x': float(self._width), 'y': float(self._height), 'in_x': float(self._width), 'in_y': float(self._height), 'out_x': float(self._width), 'out_y': float(self._height), 'node_type': 'corner'},
            {'x': 0.0, 'y': float(self._height), 'in_x': 0.0, 'in_y': float(self._height), 'out_x': 0.0, 'out_y': float(self._height), 'node_type': 'corner'},
        ]
        self._vector_path_closed = True
        self._cached_image = None
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        self.changed.emit()

    def update_vector_path_node(self, node_index: int, x: float, y: float):
        """更新指定路径节点，并同步图层边界与相对点"""
        if not self._vector_path_enabled:
            self.convert_rect_to_vector_path()
        points = self._normalize_vector_path_points(self._vector_path_points)
        if node_index < 0 or node_index >= len(points):
            return
        points[node_index] = [float(x), float(y)]
        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        new_w = max(1, int(round(max_x - min_x)))
        new_h = max(1, int(round(max_y - min_y)))
        self._x += int(round(min_x))
        self._y += int(round(min_y))
        self._width = new_w
        self._height = new_h
        self._vector_path_points = [[pt[0] - min_x, pt[1] - min_y] for pt in points]
        if self._vector_bezier_nodes:
            normalized_nodes = []
            for n in self._normalize_vector_bezier_nodes(self._vector_bezier_nodes):
                normalized_nodes.append({
                    'x': n['x'] - min_x,
                    'y': n['y'] - min_y,
                    'in_x': n['in_x'] - min_x,
                    'in_y': n['in_y'] - min_y,
                    'out_x': n['out_x'] - min_x,
                    'out_y': n['out_y'] - min_y,
                    'node_type': n.get('node_type', 'corner'),
                })
            self._vector_bezier_nodes = normalized_nodes
        self._cached_image = None
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        self.changed.emit()

    def update_vector_bezier_anchor(self, node_index: int, x: float, y: float):
        nodes = self._normalize_vector_bezier_nodes(self._vector_bezier_nodes)
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
        self._vector_bezier_nodes = nodes
        self._vector_path_points = [[n['x'], n['y']] for n in nodes]
        self.update_vector_path_node(node_index, float(x), float(y))

    def update_vector_bezier_handle(self, node_index: int, handle_type: str, x: float, y: float):
        nodes = self._normalize_vector_bezier_nodes(self._vector_bezier_nodes)
        if node_index < 0 or node_index >= len(nodes):
            return
        node = nodes[node_index]
        node_type = node.get('node_type', 'corner')
        ax, ay = node['x'], node['y']
        if handle_type == 'in':
            node['in_x'] = float(x)
            node['in_y'] = float(y)
            vx = node['in_x'] - ax
            vy = node['in_y'] - ay
            length = math.hypot(vx, vy)
            effective_mode = self._vector_handle_link_mode
            if node_type == 'symmetric':
                effective_mode = 'mirror'
            elif node_type == 'smooth':
                effective_mode = 'collinear'
            elif node_type == 'corner':
                effective_mode = 'free'
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
            effective_mode = self._vector_handle_link_mode
            if node_type == 'symmetric':
                effective_mode = 'mirror'
            elif node_type == 'smooth':
                effective_mode = 'collinear'
            elif node_type == 'corner':
                effective_mode = 'free'
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
        self._vector_bezier_nodes = nodes
        self._cached_image = None
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        self.changed.emit()

    def set_vector_node_type(self, node_index: int, node_type: str):
        nodes = self._normalize_vector_bezier_nodes(self._vector_bezier_nodes)
        if node_index < 0 or node_index >= len(nodes):
            return
        normalized = str(node_type).lower()
        if normalized not in {"corner", "smooth", "symmetric"}:
            normalized = "corner"
        nodes[node_index]['node_type'] = normalized
        self._vector_bezier_nodes = nodes
        self._cached_image = None
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        self.changed.emit()

    def cycle_vector_node_type(self, node_index: int):
        nodes = self._normalize_vector_bezier_nodes(self._vector_bezier_nodes)
        if node_index < 0 or node_index >= len(nodes):
            return
        order = ["corner", "smooth", "symmetric"]
        cur = nodes[node_index].get('node_type', 'corner')
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "corner"
        self.set_vector_node_type(node_index, nxt)

    def insert_vector_node_after(self, segment_index: int):
        nodes = self._normalize_vector_bezier_nodes(self._vector_bezier_nodes)
        if len(nodes) < 2:
            return
        closed = bool(self._vector_path_closed)
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
        self._vector_bezier_nodes = nodes
        self._vector_path_points = [[n['x'], n['y']] for n in nodes]
        self._cached_image = None
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        self.changed.emit()

    def delete_vector_node(self, node_index: int):
        nodes = self._normalize_vector_bezier_nodes(self._vector_bezier_nodes)
        min_nodes = 3 if self._vector_path_closed else 2
        if len(nodes) <= min_nodes or node_index < 0 or node_index >= len(nodes):
            return
        del nodes[node_index]
        self._vector_bezier_nodes = nodes
        self._vector_path_points = [[n['x'], n['y']] for n in nodes]
        self._cached_image = None
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        self.changed.emit()

    # 颜色叠加属性访问器
    @property
    def color_overlay_enabled(self):
        return self._color_overlay_enabled
        
    @color_overlay_enabled.setter
    def color_overlay_enabled(self, value):
        if self._color_overlay_enabled != value:
            self._color_overlay_enabled = value
            self._cached_image = None
            self.changed.emit()
            
    @property
    def color_overlay_color(self):
        return self._color_overlay_color
        
    @color_overlay_color.setter
    def color_overlay_color(self, value):
        if self._color_overlay_color != value:
            self._color_overlay_color = value
            self._cached_image = None
            self.changed.emit()
            
    @property
    def color_overlay_opacity(self):
        return self._color_overlay_opacity
        
    @color_overlay_opacity.setter
    def color_overlay_opacity(self, value):
        if self._color_overlay_opacity != value:
            self._color_overlay_opacity = max(0.0, min(1.0, float(value)))
            self._cached_image = None
            self.changed.emit()

    # 渐变叠加属性访问器
    @property
    def gradient_overlay_enabled(self):
        return self._gradient_overlay_enabled
        
    @gradient_overlay_enabled.setter
    def gradient_overlay_enabled(self, value):
        if self._gradient_overlay_enabled != value:
            self._gradient_overlay_enabled = value
            self._cached_image = None
            self.changed.emit()
            
    @property
    def gradient_overlay_colors(self):
        return self._gradient_overlay_colors
        
    @gradient_overlay_colors.setter
    def gradient_overlay_colors(self, value):
        if self._gradient_overlay_colors != value:
            self._gradient_overlay_colors = value
            self._cached_image = None
            self.changed.emit()
            
    @property
    def gradient_overlay_angle(self):
        return self._gradient_overlay_angle
        
    @gradient_overlay_angle.setter
    def gradient_overlay_angle(self, value):
        if self._gradient_overlay_angle != value:
            self._gradient_overlay_angle = float(value)
            self._cached_image = None
            self.changed.emit()
            
    @property
    def gradient_overlay_opacity(self):
        return self._gradient_overlay_opacity
        
    @gradient_overlay_opacity.setter
    def gradient_overlay_opacity(self, value):
        if self._gradient_overlay_opacity != value:
            self._gradient_overlay_opacity = max(0.0, min(1.0, float(value)))
            self._cached_image = None
            self.changed.emit()

    # 绑定属性访问器
    @property
    def bind_enabled(self):
        return self._bind_enabled
    
    @bind_enabled.setter
    def bind_enabled(self, value):
        if self._bind_enabled != value:
            self._bind_enabled = value
            self.changed.emit()
    
    @property
    def bind_group(self):
        return self._bind_group
    
    @bind_group.setter
    def bind_group(self, value):
        if self._bind_group != value:
            self._bind_group = value
            self.changed.emit()
    
    @property
    def bind_strategy(self):
        return self._bind_strategy
    
    @bind_strategy.setter
    def bind_strategy(self, value):
        if self._bind_strategy != value and value in ["filename", "folder"]:
            self._bind_strategy = value
            self.changed.emit()
    
    # 变换属性访问器
    @property
    def rotation(self):
        """旋转角度（度）"""
        return self._rotation
    
    @rotation.setter
    def rotation(self, value):
        # 角度标准化到 0-360 范围
        value = float(value) % 360
        if abs(self._rotation - value) > 0.001:  # 避免浮点数精度问题
            self._rotation = value
            self._cached_image = None  # 清除缓存，强制重新渲染
            self.changed.emit()
    
    @property
    def flip_horizontal(self):
        """水平翻转"""
        return self._flip_horizontal
    
    @flip_horizontal.setter
    def flip_horizontal(self, value):
        if self._flip_horizontal != value:
            self._flip_horizontal = value
            self._cached_image = None  # 清除缓存，强制重新渲染
            self.changed.emit()
    
    @property
    def flip_vertical(self):
        """垂直翻转"""
        return self._flip_vertical
    
    @flip_vertical.setter
    def flip_vertical(self, value):
        if self._flip_vertical != value:
            self._flip_vertical = value
            self._cached_image = None  # 清除缓存，强制重新渲染
            self.changed.emit()
    
    # 随机变换属性访问器
    @property
    def random_position_enabled(self):
        """随机位置抖动启用状态"""
        return self._random_position_enabled
    
    @random_position_enabled.setter
    def random_position_enabled(self, value):
        if self._random_position_enabled != value:
            self._random_position_enabled = value
            self.changed.emit()
    
    @property
    def random_position_range(self):
        """随机位置抖动范围（像素）"""
        return self._random_position_range
    
    @random_position_range.setter
    def random_position_range(self, value):
        if self._random_position_range != value and value >= 0:
            self._random_position_range = value
            self.changed.emit()
    
    @property
    def random_scale_enabled(self):
        """随机缩放启用状态"""
        return self._random_scale_enabled
    
    @random_scale_enabled.setter
    def random_scale_enabled(self, value):
        if self._random_scale_enabled != value:
            self._random_scale_enabled = value
            self.changed.emit()
    
    @property
    def random_scale_min(self):
        """最小随机缩放比例"""
        return self._random_scale_min
    
    @random_scale_min.setter
    def random_scale_min(self, value):
        if abs(self._random_scale_min - value) > 0.001 and 0.1 <= value <= 2.0:
            self._random_scale_min = value
            # 确保最小值不大于最大值
            if self._random_scale_min > self._random_scale_max:
                self._random_scale_max = self._random_scale_min
            self.changed.emit()
    
    @property
    def random_scale_max(self):
        """最大随机缩放比例"""
        return self._random_scale_max
    
    @random_scale_max.setter
    def random_scale_max(self, value):
        if abs(self._random_scale_max - value) > 0.001 and 0.1 <= value <= 2.0:
            self._random_scale_max = value
            # 确保最大值不小于最小值
            if self._random_scale_max < self._random_scale_min:
                self._random_scale_min = self._random_scale_max
            self.changed.emit()
    
    @property
    def random_rotation_enabled(self):
        """随机旋转启用状态"""
        return self._random_rotation_enabled
    
    @random_rotation_enabled.setter
    def random_rotation_enabled(self, value):
        if self._random_rotation_enabled != value:
            self._random_rotation_enabled = value
            self.changed.emit()
    
    @property
    def random_rotation_range(self):
        """随机旋转角度范围（度）"""
        return self._random_rotation_range
    
    @random_rotation_range.setter
    def random_rotation_range(self, value):
        if abs(self._random_rotation_range - value) > 0.001 and 0 <= value <= 180:
            self._random_rotation_range = value
            self.changed.emit()

    # 锁定比例属性访问器
    @property
    def aspect_ratio_locked(self):
        """是否锁定宽高比"""
        return self._aspect_ratio_locked

    @aspect_ratio_locked.setter
    def aspect_ratio_locked(self, value):
        if self._aspect_ratio_locked != value:
            self._aspect_ratio_locked = value
            self.changed.emit()
    
    def get_clone_positions(self):
        """获取图层所有分身的位置
        
        Returns:
            List[Tuple[int, int]]: 包含所有分身位置的列表，每个元素是(x, y)坐标
        """
        if not self._clone_enabled or self._clone_rows <= 0 or self._clone_columns <= 0:
            return [(self._x, self._y)]
        
        positions = []
        
        # 获取实际使用的宽高（考虑自定义大小）
        clone_width = self._clone_custom_width if self._clone_custom_size_enabled and self._clone_custom_width > 0 else self._width
        clone_height = self._clone_custom_height if self._clone_custom_size_enabled and self._clone_custom_height > 0 else self._height
        
        for row in range(self._clone_rows):
            for col in range(self._clone_columns):
                pos_x = self._x + col * (clone_width + self._clone_column_spacing)
                pos_y = self._y + row * (clone_height + self._clone_row_spacing)
                positions.append((pos_x, pos_y))
        
        return positions
    
    def get_clone_sizes(self):
        """获取图层所有分身的尺寸信息
        
        Returns:
            List[Tuple[int, int]]: 包含所有分身尺寸的列表，每个元素是(width, height)
        """
        if not self._clone_enabled or self._clone_rows <= 0 or self._clone_columns <= 0:
            return [(self._width, self._height)]
        
        # 获取实际使用的宽高（考虑自定义大小）
        clone_width = self._clone_custom_width if self._clone_custom_size_enabled and self._clone_custom_width > 0 else self._width
        clone_height = self._clone_custom_height if self._clone_custom_size_enabled and self._clone_custom_height > 0 else self._height
        
        # 所有分身使用相同的尺寸
        count = self._clone_rows * self._clone_columns
        return [(clone_width, clone_height) for _ in range(count)]
    
    def generate_random_transform_params(self):
        """生成新的随机变换参数
        
        这个方法会生成新的随机位置偏移、缩放比例和旋转角度，
        存储在内部状态中，用于后续的渲染。
        """
        import random
        
        # 生成随机位置偏移
        if self._random_position_enabled:
            self._current_random_offset_x = random.randint(-self._random_position_range, self._random_position_range)
            self._current_random_offset_y = random.randint(-self._random_position_range, self._random_position_range)
        else:
            self._current_random_offset_x = 0
            self._current_random_offset_y = 0
        
        # 生成随机缩放比例
        if self._random_scale_enabled:
            self._current_random_scale = random.uniform(self._random_scale_min, self._random_scale_max)
        else:
            self._current_random_scale = 1.0
        
        # 生成随机旋转角度
        if self._random_rotation_enabled:
            self._current_random_rotation = random.uniform(-self._random_rotation_range, self._random_rotation_range)
        else:
            self._current_random_rotation = 0.0
        
        print(f"图层 '{self._name}' 随机变换参数: 位置偏移({self._current_random_offset_x}, {self._current_random_offset_y}), 缩放{self._current_random_scale:.3f}, 旋转{self._current_random_rotation:.1f}°")
        self.changed.emit()
    
    def get_effective_position(self):
        """获取应用随机偏移后的有效位置
        
        Returns:
            Tuple[int, int]: (x, y) 有效位置坐标
        """
        effective_x = self._x + self._current_random_offset_x
        effective_y = self._y + self._current_random_offset_y
        return (effective_x, effective_y)
    
    def get_effective_clone_positions(self):
        """获取应用随机偏移后的所有分身位置
        
        Returns:
            List[Tuple[int, int]]: 包含所有分身有效位置的列表
        """
        if not self._clone_enabled or self._clone_rows <= 0 or self._clone_columns <= 0:
            return [self.get_effective_position()]
        
        positions = []
        base_x, base_y = self.get_effective_position()
        
        # 获取实际使用的宽高（考虑自定义大小）
        clone_width = self._clone_custom_width if self._clone_custom_size_enabled and self._clone_custom_width > 0 else self._width
        clone_height = self._clone_custom_height if self._clone_custom_size_enabled and self._clone_custom_height > 0 else self._height
        
        for row in range(self._clone_rows):
            for col in range(self._clone_columns):
                pos_x = base_x + col * (clone_width + self._clone_column_spacing)
                pos_y = base_y + row * (clone_height + self._clone_row_spacing)
                positions.append((pos_x, pos_y))
        
        return positions
    
    def reset_random_transforms(self):
        """重置所有随机变换到初始状态"""
        self._current_random_offset_x = 0
        self._current_random_offset_y = 0
        self._current_random_scale = 1.0
        self._current_random_rotation = 0.0
        print(f"图层 '{self._name}' 随机变换已重置")
        self.changed.emit()
    
    @property
    def current_image_path(self):
        return self._current_image_path
    
    @property
    def cached_image(self):
        return self._cached_image
    
    @cached_image.setter
    def cached_image(self, value):
        self._cached_image = value
    
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
        if not self._image_source or not os.path.isdir(self._image_source):
            return []
            
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        matching_files = []
        
        for file in os.listdir(self._image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                filename_without_ext = os.path.splitext(file)[0]
                core_name = self.extract_filename_core(filename_without_ext)
                
                if core_name == target_core_name:
                    matching_files.append(os.path.join(self._image_source, file))
        
        return matching_files
    
    def get_random_image(self, force_random=False, restrict_to_bound_files=None):
        """从关联文件夹中随机选择一张图片，或加载单个图片

        Args:
            force_random: 是否强制重新随机选择，忽略缓存
            restrict_to_bound_files: 限制可选择的文件列表（用于绑定管理器）
        """
        # 🔧 智能修复：检测是否为批量模式，预览启用缓存，批量禁用缓存
        is_batch_mode = _is_batch_render_context()

        # 检查调用栈，判断是否为批量导出模式
        if is_batch_mode:
            # 批量模式：禁用缓存验证，避免重复图片问题
            print(f"[图层] 🔧 批量模式：强制重新加载图像: {self.name}")
        else:
            # 预览模式：启用缓存验证，提高预览性能
            if not force_random and self._validate_cache() and self._cached_image is not None:
                print(f"[图层] ✅ 预览模式：使用缓存图像: {self.name}")
                return self._cached_image
            
        # 🔧 预计算导出修复：优先使用已指定的当前图像路径
        if self._current_image_path and os.path.isfile(self._current_image_path):
            try:
                print(f"[图层] 使用预设图像路径: {self._current_image_path}")
                # 保存当前尺寸，以便检测是否被意外更改
                old_width, old_height = self._width, self._height

                # 加载并处理图像
                image = self._load_and_process_image(self._current_image_path)

                # 如果尺寸被意外更改，恢复原有尺寸并打印警告
                if old_width != self._width or old_height != self._height:
                    print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                    self._width = old_width
                    self._height = old_height

                    # 如果尺寸发生变化，可能需要重新处理图像以匹配正确尺寸
                    if image.width != old_width or image.height != old_height:
                        print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                        # 使用预乘Alpha缩放保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_with_premultiplied_alpha(image, (old_width, old_height))
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)
                        # 🔧 关键修复：在批量模式下禁用缓存存储
                        if not is_batch_mode:
                            self._cached_image = image

                # 确保启用分身时图像正确处理
                if self._clone_enabled:
                    print(f"分身已启用，使用预设路径: {self._current_image_path}")
                return image
            except Exception as e:
                print(f"无法加载预设图像 {self._current_image_path}: {e}")
                # 在预计算模式下，如果指定图像加载失败，不应该继续随机选择
                if not force_random:
                    print(f"[图层] 预计算模式下指定图像加载失败，返回错误图像")
                    return self._create_error_image()
                # 清除无效的当前路径，继续执行随机选择
                self._current_image_path = None
            
        # 如果图像源是单个文件，直接使用（除非强制随机且实际是文件夹）
        # 规范化路径以正确识别UNC上的单文件
        def _normalize_path(p):
            if not p:
                return p
            p = p.replace('/', os.sep)
            if p.startswith('\\\\'):
                return p
            if p.startswith('//'):
                server_share = p.lstrip('/').replace('/', '\\')
                return f"\\\\{server_share}"
            return os.path.normpath(p)

        image_source_norm = _normalize_path(self._image_source) if self._image_source else self._image_source

        if not self._is_folder and image_source_norm and os.path.isfile(image_source_norm) and not force_random:
            try:
                print(f"加载单个图像: {image_source_norm}, 智能裁剪={self._use_original_size}")
                # 保存当前尺寸，以便检测是否被意外更改
                old_width, old_height = self._width, self._height

                # 加载并处理图像
                image = self._load_and_process_image(image_source_norm)
                
                # 如果尺寸被意外更改，恢复原有尺寸并打印警告
                if old_width != self._width or old_height != self._height:
                    print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                    self._width = old_width
                    self._height = old_height
                    
                    # 如果尺寸发生变化，可能需要重新处理图像以匹配正确尺寸
                    if image.width != old_width or image.height != old_height:
                        print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                        # 使用预乘Alpha缩放保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_with_premultiplied_alpha(image, (old_width, old_height))
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)
                        self._cached_image = image
                
                # 确保启用分身时图像正确处理
                if self._clone_enabled:
                    print(f"分身已启用，加载图像: {self._image_source}")
                return image
            except Exception as e:
                print(f"无法加载图像 {self._image_source}: {e}")
                return self._create_error_image()
                
        # 如果图像源是文件夹，随机选择图片
        if not self._image_source or not os.path.isdir(self._image_source):
            return None
            
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        image_files = []
        
        for file in os.listdir(self._image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                image_files.append(os.path.join(self._image_source, file))

        if not image_files:
            return None

        # 如果有文件限制，只使用限制范围内的文件
        if restrict_to_bound_files:
            # 将限制文件列表转换为绝对路径进行比较
            restricted_files = []
            for restricted_file in restrict_to_bound_files:
                if os.path.isabs(restricted_file):
                    restricted_files.append(restricted_file)
                else:
                    restricted_files.append(os.path.join(self._image_source, restricted_file))

            # 过滤出在限制范围内的文件
            image_files = [f for f in image_files if f in restricted_files]

            if not image_files:
                print(f"警告：文件限制后没有可用文件，图层: {self.name}")
                return None

        # 如果强制随机且有多个文件，尝试选择与当前不同的文件
        if force_random and len(image_files) > 1 and self._current_image_path:
            # 过滤掉当前图片，从剩余的图片中随机选择
            available_files = [f for f in image_files if f != self._current_image_path]
            if available_files:
                # 使用更好的随机选择算法
                import time
                import hashlib

                # 创建基于时间和文件路径的随机种子
                seed_string = f"{time.time_ns()}_{self._image_source}_{len(available_files)}"
                seed_hash = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
                random.seed(seed_hash)

                image_path = random.choice(available_files)
                print(f"强制随机选择新图片: {os.path.basename(image_path)} (避免重复: {os.path.basename(self._current_image_path)}) [种子:{seed_hash}]")

                # 恢复随机状态
                random.seed()
            else:
                image_path = random.choice(image_files)
                print(f"强制随机选择图片: {os.path.basename(image_path)} (无其他选择)")
        else:
            # 即使不是强制随机，也使用更好的随机算法
            if force_random or len(image_files) > 1:
                import time
                import hashlib

                seed_string = f"{time.time_ns()}_{self._image_source}_{random.random()}"
                seed_hash = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
                random.seed(seed_hash)

                image_path = random.choice(image_files)
                if force_random:
                    print(f"强制随机选择图片: {os.path.basename(image_path)} [种子:{seed_hash}]")

                # 恢复随机状态
                random.seed()
            else:
                image_path = random.choice(image_files)

        self._current_image_path = image_path

        # 如果是强制随机，清除缓存确保重新加载
        if force_random:
            self._cached_image = None

        try:
            # 保存当前尺寸，以便检测是否被意外更改
            old_width, old_height = self._width, self._height

            # 加载并处理图像
            image = self._load_and_process_image(image_path)
            
            # 如果尺寸被意外更改，恢复原有尺寸并打印警告
            if old_width != self._width or old_height != self._height:
                print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                self._width = old_width
                self._height = old_height
                
                # 如果尺寸发生变化，可能需要重新处理图像以匹配正确尺寸
                if image.width != old_width or image.height != old_height:
                    print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                    image = image.resize((old_width, old_height), Resampling.BICUBIC)
                    self._cached_image = image
            
            return image
        except Exception as e:
            # 使用日志记录错误，同时保持原有的print输出
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(f"无法加载图像 {image_path}: {e}", exc_info=True)
            except:
                pass
            print(f"无法加载图像 {image_path}: {e}")
            return self._create_error_image()

    def get_image(self):
        """获取图层的当前图像

        这是一个兼容性方法，用于支持旧的代码调用

        Returns:
            PIL.Image: 图层的当前图像
        """
        # 如果有当前指定的图像路径，使用它
        if hasattr(self, '_current_image_path') and self._current_image_path:
            try:
                # 保存当前尺寸，以便检测是否被意外更改
                old_width, old_height = self._width, self._height

                # 加载并处理图像
                image = self._load_and_process_image(self._current_image_path)

                # 如果尺寸被意外更改，恢复原有尺寸
                if old_width != self._width or old_height != self._height:
                    print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                    self._width = old_width
                    self._height = old_height

                    # 如果尺寸发生变化，重新调整图像尺寸
                    if image.width != old_width or image.height != old_height:
                        print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                        # 使用预乘Alpha缩放保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_with_premultiplied_alpha(image, (old_width, old_height))
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)
                        self._cached_image = image

                # 确保启用分身时图像正确处理
                if self._clone_enabled:
                    print(f"分身已启用，使用路径: {self._current_image_path}")
                return image
            except Exception as e:
                print(f"无法加载指定图像 {self._current_image_path}: {e}")
                # 清除无效的当前路径，继续执行随机选择
                self._current_image_path = None
                # 通知文档状态已更改，需要UI更新
                if hasattr(self, 'changed') and hasattr(self.changed, 'emit'):
                    self.changed.emit()

        # 🔧 关键修复：完全禁用图层缓存使用，避免重复图片问题
        # 注释掉缓存使用，确保每次都重新加载图像
        # if hasattr(self, '_cached_image') and self._cached_image is not None:
        #     # 使用已缓存的图像
        #     image = self._cached_image
        #     # ... 缓存处理逻辑 ...
        #     return image
        print(f"[图层] 🔧 跳过缓存图像使用: {self.name} (强制重新加载)")

        # 否则获取随机图像
        return self.get_random_image(force_random=False)

    def _find_non_transparent_bounds(self, image):
        """查找图像中非空白区域的边界，使用更高效的检测方法
        
        Args:
            image: PIL图像对象，必须是RGBA模式
            
        Returns:
            元组 (left, top, right, bottom)，表示非空白区域的边界
        """
        if image.mode != 'RGBA':
            print("警告: 图像不是RGBA模式，无法检测透明度")
            return (0, 0, image.width, image.height)
        
        try:
            # 获取图像尺寸
            width, height = image.size
            print(f"检测非空白区域，图像尺寸: {width}x{height}")
            
            # 转换为numpy数组进行更高效的处理
            img_array = np.array(image)
            
            # 提取alpha通道
            alpha = img_array[:, :, 3]
            
            # 使用更低的透明度阈值，只要不是完全透明就算作内容
            alpha_threshold = 5
            
            # 找到alpha通道大于阈值的像素位置
            mask = alpha > alpha_threshold
            
            # 如果没有找到任何非透明像素，返回整个图像
            if not np.any(mask):
                print("未找到任何非透明像素，返回完整图像")
                return (0, 0, width, height)
            
            # 找到非透明区域的边界
            rows = np.any(mask, axis=1)
            cols = np.any(mask, axis=0)
            
            # 确定边界
            top = np.argmax(rows)
            bottom = height - np.argmax(rows[::-1])
            left = np.argmax(cols)
            right = width - np.argmax(cols[::-1])
            
            # 添加边距，避免太紧贴内容
            margin = 1
            left = max(0, int(left - margin))
            top = max(0, int(top - margin))
            right = min(width, right + margin)
            bottom = min(height, bottom + margin)
            
            print(f"找到非空白区域: ({left}, {top}, {right}, {bottom})")
            
            # 检查裁剪区域是否太小或太接近原图
            crop_width = right - left
            crop_height = bottom - top
            
            # 如果裁剪区域太小，返回完整图像
            if crop_width < 10 or crop_height < 10:
                print(f"裁剪区域过小 {crop_width}x{crop_height}，返回完整图像")
                return (0, 0, width, height)
                
            # 如果裁剪区域占比超过95%，返回完整图像
            crop_area = crop_width * crop_height
            original_area = width * height
            crop_ratio = crop_area / original_area
            
            if crop_ratio > 0.95:
                print(f"裁剪区域占比 {crop_ratio:.2%} 过大，几乎是整图，返回完整图像")
                return (0, 0, width, height)
                
            return (left, top, right, bottom)
            
        except Exception as e:
            print(f"计算非空白区域边界时出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时返回完整图像
            return (0, 0, image.width, image.height)
    
    def _load_and_process_image(self, image_path):
        """加载并处理图像，支持去除空白像素模式（优化版本）"""
        try:
            # 🔧 检测是否为批量模式
            is_batch_mode = _is_batch_render_context()

            # 尝试使用图像优化器进行快速加载
            try:
                from app.utils.image_optimizer import get_image_optimizer
                optimizer = get_image_optimizer()

                # 对于简单的适配模式，直接使用优化器
                if not self._smart_crop_enabled:
                    optimized_image = optimizer.load_image_optimized(
                        image_path,
                        (self._width, self._height),
                        fit_mode=self._fit_mode
                    )

                    if optimized_image:
                        # 🔧 智能修复：预览模式启用缓存存储，批量模式禁用缓存存储
                        if not is_batch_mode:
                            # 预览模式：启用缓存存储，提高预览性能
                            self._cached_image = optimized_image
                            self._cached_image_path = image_path
                            self._cache_valid = True
                        # 批量模式：不存储缓存，避免重复图片问题
                        return optimized_image

            except ImportError:
                # 图像优化器不可用，使用原有逻辑
                pass
            # 使用PIL打开图像（规范化路径，兼容UNC与正斜杠）
            def _normalize_path(p):
                if not p:
                    return p
                p = p.replace('/', os.sep)
                if p.startswith('\\\\'):
                    return p
                if p.startswith('//'):
                    server_share = p.lstrip('/').replace('/', '\\')
                    return f"\\\\{server_share}"
                return os.path.normpath(p)

            image_path_norm = _normalize_path(image_path)

            with Image.open(image_path_norm) as _img:
                original_image = _img if _img.mode == 'RGBA' else _img.convert('RGBA')
            # 复制为内存图，避免持有底层文件句柄
            original_image = original_image.copy()
            
            # 保存用户设置的目标尺寸（这个不能改变！）
            target_width = self._width
            target_height = self._height
            
            # 批处理模式下减少日志输出
            is_batch_mode = getattr(self, '_is_batch_mode', False)
            if not is_batch_mode:
                print(f"加载图像: {image_path}")
                print(f"用户设置的图层尺寸: {target_width}x{target_height}（此尺寸严格不变）")
                print(f"原始图像尺寸: {original_image.width}x{original_image.height}")
                print(f"处理模式: 智能裁剪={self._use_original_size}, 适配模式={self._fit_mode}")
                print(f"旋转角度: {self._rotation}度")
            
            # 使用中间变量来保存处理结果
            processed_image = original_image
            
            # 如果启用智能裁剪，先裁剪非空白区域
            if self._use_original_size:
                if not is_batch_mode:
                    print(f"========== 开始智能裁剪 ==========")
                
                # 查找非空白区域
                bounds = self._find_non_transparent_bounds(original_image)
                left, top, right, bottom = bounds
                
                # 检查是否需要裁剪
                needs_cropping = (left > 0 or top > 0 or right < original_image.width or bottom < original_image.height)
                
                if needs_cropping:
                    if not is_batch_mode:
                        print(f"执行智能裁剪: ({left}, {top}, {right}, {bottom})")
                    cropped_image = original_image.crop((left, top, right, bottom))
                    if not is_batch_mode:
                        print(f"裁剪结果: {cropped_image.width}x{cropped_image.height}")
                    processed_image = cropped_image
                else:
                    if not is_batch_mode:
                        print("不需要裁剪，保持原图")
                    processed_image = original_image
                
                if not is_batch_mode:
                    print(f"智能裁剪后图像尺寸: {processed_image.width}x{processed_image.height}")
                    print(f"========== 智能裁剪结束 ==========")
            
            # 创建一个透明背景图像，尺寸为图层尺寸
            final_image = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            
            # 根据适配模式调整图像大小并放置在图层中
            if self._fit_mode == 0:  # 智能裁剪(等比缩放后裁剪)
                print(f"使用智能裁剪(等比缩放后裁剪)模式")
                
                # 计算等比缩放尺寸
                src_ratio = processed_image.width / processed_image.height
                target_ratio = target_width / target_height
                
                if src_ratio > target_ratio:
                    # 源图更宽，以高度为基准缩放
                    scale_height = target_height
                    scale_width = int(scale_height * src_ratio)
                    print(f"等比缩放: 源图更宽，以高度为基准，缩放尺寸 {scale_width}x{scale_height}")
                else:
                    # 源图更高，以宽度为基准缩放
                    scale_width = target_width
                    scale_height = int(scale_width / src_ratio)
                    print(f"等比缩放: 源图更高，以宽度为基准，缩放尺寸 {scale_width}x{scale_height}")
                
                # 等比缩放
                scaled_image = processed_image.resize((scale_width, scale_height), Resampling.BICUBIC)
                
                # 根据裁剪方向决定裁剪区域
                if self._crop_direction == 0:  # 居中
                    left = (scale_width - target_width) // 2
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：居中")
                elif self._crop_direction == 1:  # 顶部
                    left = (scale_width - target_width) // 2
                    top = 0
                    print(f"裁剪方向：顶部")
                elif self._crop_direction == 2:  # 底部
                    left = (scale_width - target_width) // 2
                    top = scale_height - target_height
                    print(f"裁剪方向：底部")
                elif self._crop_direction == 3:  # 左侧
                    left = 0
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：左侧")
                elif self._crop_direction == 4:  # 右侧
                    left = scale_width - target_width
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：右侧")
                else:  # 默认居中
                    left = (scale_width - target_width) // 2
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：默认居中")
                
                # 确保裁剪区域不超出图像范围
                left = max(0, min(left, scale_width - target_width))
                top = max(0, min(top, scale_height - target_height))
                
                print(f"裁剪区域: ({left}, {top}, {left+target_width}, {top+target_height})")
                cropped_image = scaled_image.crop((left, top, left + target_width, top + target_height))
                print(f"返回裁剪图像: {cropped_image.width}x{cropped_image.height}")
                final_image = cropped_image
            elif self._fit_mode == 1:  # 智能缩放不裁剪
                print(f"使用智能缩放不裁剪模式")
                # 计算等比缩放尺寸
                src_ratio = processed_image.width / processed_image.height
                target_ratio = target_width / target_height
                
                if src_ratio > target_ratio:
                    # 源图更宽，以宽度为基准缩放
                    scale_width = target_width
                    scale_height = int(scale_width / src_ratio)
                else:
                    # 源图更高或相等，以高度为基准缩放
                    scale_height = target_height
                    scale_width = int(scale_height * src_ratio)
                
                # 等比缩放确保不会为0
                scale_width = max(1, scale_width)
                scale_height = max(1, scale_height)
                
                # 等比缩放
                scaled_image = processed_image.resize((scale_width, scale_height), Resampling.BICUBIC)
                
                # 计算居中位置
                x = (target_width - scale_width) // 2
                y = (target_height - scale_height) // 2
                
                # 将缩放后的图像粘贴到透明背景的中心
                final_image.paste(scaled_image, (x, y), scaled_image)
                
                if not is_batch_mode:
                    print(f"智能缩放不裁剪: 原图宽高比 {src_ratio:.2f}, 目标宽高比 {target_ratio:.2f}")
                    print(f"智能缩放不裁剪: {'原图更宽' if src_ratio > target_ratio else '原图更高'}, 缩放尺寸 {scale_width}x{scale_height}")
                    print(f"智能缩放不裁剪: 最终尺寸 {target_width}x{target_height}, 内容位置 ({x}, {y})")
            else:  # 拉伸适配
                if not is_batch_mode:
                    print(f"使用拉伸适配调整到图层尺寸: {target_width}x{target_height}")
                resized_image = processed_image.resize((target_width, target_height), Resampling.BICUBIC)
                final_image = resized_image
            
            # 🔧 智能修复：预览模式启用缓存存储，批量模式禁用缓存存储
            if not is_batch_mode:
                # 预览模式：启用缓存存储，提高预览性能
                self._cached_image = final_image
                self._cached_image_path = image_path
                self._cache_valid = True
            # 批量模式：不存储缓存，避免重复图片问题

            return final_image
            
        except Exception as e:
            # 批处理模式下减少错误日志输出
            is_batch_mode = getattr(self, '_is_batch_mode', False)
            if not is_batch_mode:
                print(f"图像处理失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 🔧 关键修复：清理无效的current_image_path
            if hasattr(self, '_current_image_path') and self._current_image_path:
                print(f"清理无效的current_image_path: {self._current_image_path}")
                self._current_image_path = None
                # 通知UI状态已改变
                if hasattr(self, 'changed') and hasattr(self.changed, 'emit'):
                    self.changed.emit()
            
            # 创建错误提示图像
            error_image = self._create_error_image()
            # 🔧 关键修复：禁用错误图像缓存存储
            # self._cached_image = error_image
            return error_image
    
    def _scale_and_crop(self, image):
        """等比缩放图像并按指定方向裁剪"""
        try:
            # 确保图像是有效的
            if image is None or image.width == 0 or image.height == 0:
                return None
                
            # 确保目标尺寸有效
            if self._width <= 0 or self._height <= 0:
                return None
                
            # 使用当前图层设置的尺寸
            target_width = self._width
            target_height = self._height
                
            # 打印调试信息 - 批处理模式下减少日志
            is_batch_mode = getattr(self, '_is_batch_mode', False)
            if not is_batch_mode:
                print(f"等比缩放: 图层尺寸 {target_width}x{target_height}, 图像尺寸 {image.width}x{image.height}")
                
            # 计算原始宽高比
            orig_width, orig_height = image.size
            orig_ratio = orig_width / orig_height
            
            # 计算目标宽高比
            target_ratio = target_width / target_height
            
            print(f"等比缩放: 原始宽高比 {orig_ratio:.2f}, 目标宽高比 {target_ratio:.2f}")
            
            # 确定缩放后的尺寸
            if orig_ratio > target_ratio:
                # 原图更宽，以高度为基准缩放
                scale_height = target_height
                scale_width = int(scale_height * orig_ratio)
                print(f"等比缩放: 原图更宽, 缩放尺寸 {scale_width}x{scale_height}")
            else:
                # 原图更高，以宽度为基准缩放
                scale_width = target_width
                scale_height = int(scale_width / orig_ratio)
                print(f"等比缩放: 原图更高, 缩放尺寸 {scale_width}x{scale_height}")
                
            # 等比缩放图像
            scaled_image = image.resize((scale_width, scale_height), Resampling.BICUBIC)
            
            # 根据裁剪方向决定裁剪区域
            if self._crop_direction == 0:
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
            elif self._crop_direction == 1:
                left = (scale_width - target_width) // 2
                top = 0
            elif self._crop_direction == 2:
                left = (scale_width - target_width) // 2
                top = scale_height - target_height
            elif self._crop_direction == 3:
                left = 0
                top = (scale_height - target_height) // 2
            elif self._crop_direction == 4:
                left = scale_width - target_width
                top = (scale_height - target_height) // 2
            else:
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
            
            print(f"裁剪: 区域 ({left}, {top}, {left+target_width}, {top+target_height})")
            
            # 确保裁剪区域不超出图像范围
            left = max(0, min(left, scale_width - target_width))
            top = max(0, min(top, scale_height - target_height))
            
            # 裁剪图像
            cropped_image = scaled_image.crop((left, top, left + target_width, top + target_height))
            print(f"裁剪后尺寸: {cropped_image.width}x{cropped_image.height}, 期望尺寸: {target_width}x{target_height}")
            
            return cropped_image
        except Exception as e:
            print(f"等比缩放裁剪失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _scale_content_and_crop(self, image, target_width, target_height):
        """等比缩放裁剪后的内容图像，保持内容比例"""
        try:
            # 检查参数有效性
            if image is None or image.width == 0 or image.height == 0:
                print("警告：输入图像无效或尺寸为零")
                return None
            if target_width <= 0 or target_height <= 0:
                print(f"警告：目标尺寸无效：{target_width}x{target_height}")
                return None
            
            print(f"内容等比缩放：原始尺寸={image.width}x{image.height}, 目标尺寸={target_width}x{target_height}")
            
            # 计算比例
            src_ratio = image.width / image.height
            target_ratio = target_width / target_height
            
            print(f"内容等比缩放：原始宽高比={src_ratio:.2f}, 目标宽高比={target_ratio:.2f}")
            
            # 确定缩放方式
            if src_ratio > target_ratio:
                # 源图更宽，以高度为基准缩放
                scale_height = target_height
                scale_width = int(scale_height * src_ratio)
                print(f"源图更宽：以高度为基准缩放，缩放尺寸={scale_width}x{scale_height}")
            else:
                # 源图更高，以宽度为基准缩放
                scale_width = target_width
                scale_height = int(scale_width / src_ratio)
                print(f"源图更高：以宽度为基准缩放，缩放尺寸={scale_width}x{scale_height}")
            
            # 安全检查：确保缩放尺寸不为零
            if scale_width <= 0 or scale_height <= 0:
                print(f"警告：计算的缩放尺寸无效：{scale_width}x{scale_height}，回退到目标尺寸")
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            
            # 等比缩放
            try:
                scaled_image = HighQualityResampler.resize(image, (scale_width, scale_height), method=Resampling.LANCZOS, enable_sharpening=True)
                print(f"等比缩放后尺寸：{scaled_image.width}x{scaled_image.height}")
            except Exception as e:
                print(f"等比缩放失败：{e}，回退到直接缩放")
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            
            # 根据裁剪方向确定裁剪区域
            if self._crop_direction == 0:  # 居中
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：居中")
            elif self._crop_direction == 1:  # 顶部
                left = (scale_width - target_width) // 2
                top = 0
                print(f"裁剪方向：顶部")
            elif self._crop_direction == 2:  # 底部
                left = (scale_width - target_width) // 2
                top = scale_height - target_height
                print(f"裁剪方向：底部")
            elif self._crop_direction == 3:  # 左侧
                left = 0
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：左侧")
            elif self._crop_direction == 4:  # 右侧
                left = scale_width - target_width
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：右侧")
            else:  # 默认居中
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：默认居中")
            
            # 确保裁剪区域不超出图像范围
            left = max(0, min(left, scale_width - target_width))
            top = max(0, min(top, scale_height - target_height))
            right = left + target_width
            bottom = top + target_height
            
            # 确保裁剪区域的正确性
            if right > scale_width:
                right = scale_width
                left = max(0, right - target_width)
            if bottom > scale_height:
                bottom = scale_height
                top = max(0, bottom - target_height)
            
            print(f"裁剪区域：({left}, {top}, {right}, {bottom})")
            
            # 检查最终裁剪区域
            final_width = right - left
            final_height = bottom - top
            if final_width != target_width or final_height != target_height:
                print(f"警告：计算的裁剪区域尺寸 {final_width}x{final_height} 与目标尺寸 {target_width}x{target_height} 不符")
                # 如果裁剪区域尺寸不正确，可能需要调整策略
                if final_width <= 0 or final_height <= 0:
                    print("裁剪区域无效，回退到直接缩放")
                    return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            
            # 裁剪并返回
            try:
                cropped_image = scaled_image.crop((left, top, right, bottom))
                print(f"裁剪后最终尺寸：{cropped_image.width}x{cropped_image.height}")
                
                # 最终检查
                if cropped_image.width != target_width or cropped_image.height != target_height:
                    print(f"警告：最终图像尺寸 {cropped_image.width}x{cropped_image.height} 与目标尺寸 {target_width}x{target_height} 不符，调整大小")
                    cropped_image = HighQualityResampler.resize(cropped_image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
                
                return cropped_image
            except Exception as e:
                print(f"裁剪失败：{e}，回退到直接缩放")
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
        except Exception as e:
            print(f"等比缩放裁剪内容失败: {e}")
            import traceback
            traceback.print_exc()
            # 发生任何错误，尝试直接缩放原图
            try:
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            except:
                return None
    
    def _scale_to_fit(self, image):
        """等比缩放图像以适应目标区域，不进行裁剪，保持图像完整并最大化利用空间"""
        try:
            # 确保图像是有效的
            if image is None or image.width == 0 or image.height == 0:
                print("警告: 输入图像无效")
                return None
                
            # 确保目标尺寸有效
            if self._width <= 0 or self._height <= 0:
                print("警告: 目标尺寸无效")
                return None
                
            # 使用当前图层设置的尺寸
            target_width = self._width
            target_height = self._height
                
            # 打印调试信息
            print(f"等比缩放适配: 目标尺寸 {target_width}x{target_height}, 源图尺寸 {image.width}x{image.height}")
                
            # 计算原始宽高比
            orig_width, orig_height = image.size
            orig_ratio = orig_width / orig_height if orig_height > 0 else 1.0
            
            # 计算目标宽高比
            target_ratio = target_width / target_height if target_height > 0 else 1.0
            
            print(f"等比缩放适配: 源图比例 {orig_ratio:.3f}, 目标比例 {target_ratio:.3f}")
            
            # 计算缩放尺寸，确保内容完全可见且最大化填充空间
            if orig_ratio > target_ratio:
                # 原图更宽，以宽度为基准缩放（让宽度正好适合目标宽度）
                scale_width = target_width
                scale_height = int(scale_width / orig_ratio)
                print(f"等比缩放适配: 源图更宽，以宽度为基准，缩放尺寸 {scale_width}x{scale_height}")
            else:
                # 原图更高或比例相同，以高度为基准缩放（让高度正好适合目标高度）
                scale_height = target_height
                scale_width = int(scale_height * orig_ratio)
                print(f"等比缩放适配: 源图更高或等比，以高度为基准，缩放尺寸 {scale_width}x{scale_height}")
                
            # 确保计算结果不为零
            scale_width = max(1, scale_width)
            scale_height = max(1, scale_height)
            
            # 等比缩放图像
            scaled_image = HighQualityResampler.resize(image, (scale_width, scale_height), method=Resampling.LANCZOS, enable_sharpening=True)
            print(f"缩放后图像尺寸: {scaled_image.width}x{scaled_image.height}")
            
            # 创建透明背景图像
            result_image = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            
            # 计算居中位置
            pos_x = (target_width - scale_width) // 2
            pos_y = (target_height - scale_height) // 2
            
            # 将缩放后的图像粘贴到透明背景中央
            result_image.paste(scaled_image, (pos_x, pos_y))
            
            print(f"等比缩放适配: 最终尺寸 {result_image.width}x{result_image.height}, 内容位置 ({pos_x}, {pos_y})")
            
            return result_image
        except Exception as e:
            print(f"等比缩放适配失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _scale_content_to_fit(self, content_image, target_width, target_height):
        """对智能裁剪后的内容等比缩放以适应目标区域，不裁剪"""
        # 直接使用_scale_to_fit方法，保持代码一致性
        return self._scale_to_fit(content_image)
    
    def _apply_color_overlay(self, image):
        """应用颜色叠加"""
        if image is None:
            return None
            
        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            # 1. 创建纯色图层
            color = self._color_overlay_color
            if len(color) == 3:
                color = (*color, 255)
            
            # 使用原图大小
            overlay = Image.new('RGBA', image.size, color)
            
            # 2. 提取原图Alpha通道作为蒙版
            alpha = image.split()[3]
            
            # 将蒙版应用到纯色层
            # 注意：如果原图有半透明像素，alpha会保留这种半透明
            # 如果纯色层本身也是半透明的（color alpha < 255），那么需要组合
            # 这里我们假设color alpha只控制颜色本身的透明度，
            # 但最终的alpha必须受限于原图的形状(alpha)
            
            # 组合Alpha: min(original_alpha, color_alpha) ?
            # 通常Color Overlay是替换颜色，保留原图Alpha。
            # 但如果Overlay Color是半透明的，那么结果也应该是半透明的？
            # Photoshop: Color Overlay (Red, 50% Opacity) on Black Square -> Dark Red?
            # No, Photoshop "Opacity" in Layer Style is the blend opacity.
            # The Color Picker alpha is usually 100%.
            
            # Let's assume overlay.putalpha(alpha) sets the alpha channel to exactly 'alpha'.
            # This ignores the alpha of the color itself if it had any.
            # But our color is (R,G,B,A).
            
            # Correct logic:
            # Result Alpha = Original Alpha * (Color Alpha / 255)
            # But usually Color Overlay color is opaque.
            
            # Let's stick to simple:
            overlay.putalpha(alpha)
            
            # 3. 混合
            if self._color_overlay_opacity >= 1.0:
                return overlay
            
            return Image.blend(image, overlay, self._color_overlay_opacity)
            
        except Exception as e:
            print(f"[颜色叠加] 失败: {e}")
            return image

    def _apply_gradient_overlay(self, image):
        """应用渐变叠加"""
        if image is None:
            return None
            
        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            width, height = image.size
            
            # 1. 生成渐变图像
            # 计算对角线长度，确保旋转后覆盖全图
            diag = int(math.ceil(math.sqrt(width**2 + height**2)))
            if diag == 0: diag = 1
            
            # 创建渐变数据 (numpy)
            # 确保颜色列表有效
            if not self._gradient_overlay_colors or len(self._gradient_overlay_colors) < 2:
                # 默认黑白
                colors = [(0, 0, 0, 255), (255, 255, 255, 255)]
            else:
                colors = self._gradient_overlay_colors
                
            start_color = np.array(colors[0], dtype=float)
            end_color = np.array(colors[1], dtype=float)
            
            # 确保颜色是RGBA
            if len(start_color) == 3: start_color = np.append(start_color, 255.0)
            if len(end_color) == 3: end_color = np.append(end_color, 255.0)
            
            # 生成垂直渐变 (1 x diag)
            # 0.0 -> 1.0
            y = np.linspace(0, 1, diag).reshape(diag, 1)
            
            # 线性插值
            gradient_col = start_color * (1.0 - y) + end_color * y
            
            # 转换为uint8
            gradient_col = np.clip(gradient_col, 0, 255).astype(np.uint8)
            
            # 扩展为 (diag, diag)
            # 先转为Image strip (1, diag)
            # 注意: numpy array is (height, width, channels) -> (diag, 1, 4)
            gradient_strip = Image.fromarray(gradient_col.reshape(diag, 1, 4), 'RGBA')
            
            # Resize to (diag, diag) -> Stretch horizontally
            gradient_square = gradient_strip.resize((diag, diag), Resampling.NEAREST)
            
            # 2. 旋转
            # Photoshop默认90度是下到上？
            # 我们生成的是上到下。
            # 旋转 self._gradient_overlay_angle
            rotated_gradient = gradient_square.rotate(self._gradient_overlay_angle, expand=False, resample=Resampling.BILINEAR)
            
            # 3. 裁剪中心
            left = (diag - width) // 2
            top = (diag - height) // 2
            gradient_layer = rotated_gradient.crop((left, top, left + width, top + height))
            
            # 4. 应用蒙版
            alpha = image.split()[3]
            gradient_layer.putalpha(alpha)
            
            # 5. 混合
            if self._gradient_overlay_opacity >= 1.0:
                return gradient_layer
            
            return Image.blend(image, gradient_layer, self._gradient_overlay_opacity)
            
        except Exception as e:
            print(f"[渐变叠加] 失败: {e}")
            import traceback
            traceback.print_exc()
            return image

    def apply_effects(self, image):
        """应用图层特效的公共方法，调用私有实现"""
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
            f"path:{self._current_image_path or ''}",
            f"src:{self._image_source or ''}",
            f"img:{getattr(image, 'width', 0)}x{getattr(image, 'height', 0)}:{getattr(image, 'mode', '')}",
            f"layer:{self._width}x{self._height}",
            f"fit:{self._fit_mode}",
            f"crop:{self._crop_direction}",
            f"use_orig:{int(bool(self._use_original_size))}",
            f"rot:{float(self._rotation):.3f}",
            f"flip_h:{int(bool(self._flip_horizontal))}",
            f"flip_v:{int(bool(self._flip_vertical))}",
            f"rnd_scale:{float(getattr(self, '_current_random_scale', 1.0)):.6f}",
            f"rnd_rot:{float(getattr(self, '_current_random_rotation', 0.0)):.3f}",
        ]
        source_parts.extend(extra_parts)
        return hashlib.md5("|".join([str(p) for p in source_parts]).encode('utf-8')).hexdigest()
    
    def _apply_effects(self, image):
        """应用图层特效（圆角、描边等）和变换（旋转、翻转）"""
        if image is None:
            return None
        self._render_offset_x = 0
        self._render_offset_y = 0
        
        # 批处理模式下减少日志输出
        is_batch_mode = getattr(self, '_is_batch_mode', False)
        if not is_batch_mode:
            print(f"应用特效前图像尺寸: {image.width}x{image.height}, 图层尺寸: {self._width}x{self._height}")
        
        # 如果图像尺寸与图层尺寸不匹配，根据模式处理
        if image.width != self._width or image.height != self._height:
            if self._fit_mode == 2:
                # 等比缩放不裁剪模式：保持原图尺寸，继续应用特效
                if not is_batch_mode:
                    print(f"等比缩放不裁剪模式：保持图像尺寸不变 {image.width}x{image.height}，继续应用圆角/描边")
            else:
                if not is_batch_mode:
                    print(f"警告：图像尺寸与图层尺寸不匹配，调整图像大小: {image.width}x{image.height} => {self._width}x{self._height}")
                image = image.resize((self._width, self._height), Resampling.BICUBIC)
        
        stroke_enabled = self._stroke_enabled and self._stroke_width > 0
        log_branch(
            "layer._apply_effects",
            "enter",
            corner_radius=self._corner_radius,
            stroke_enabled=stroke_enabled,
            stroke_type=self._stroke_type,
            stroke_width=self._stroke_width,
        )

        # 阶段1：几何与变换（可缓存）
        stage1_extra_parts = [
            f"corner:{int(self._corner_radius)}",
            f"vcorner:{int(self._vector_corner_radius_tl)}:{int(self._vector_corner_radius_tr)}:"
            f"{int(self._vector_corner_radius_br)}:{int(self._vector_corner_radius_bl)}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"vpath_on:{int(bool(self._vector_path_enabled))}",
            f"vpath_pts:{str(self._vector_path_points)}",
            f"vpath_mode:{str(self._vector_path_mode)}",
            f"vpath_bezier:{str(self._vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self._vector_path_closed))}",
            f"vpath_link:{str(self._vector_handle_link_mode)}",
            f"shape:{getattr(getattr(self, '_shape_type', ''), 'value', getattr(self, '_shape_type', ''))}",
            f"trap:{getattr(self, '_trapezoid_top_width', '')},{getattr(self, '_trapezoid_bottom_width', '')},{getattr(self, '_trapezoid_slope_side', '')}",
            f"poly:{getattr(self, '_polygon_rotation', '')},{getattr(self, '_polygon_corner_radius', '')}",
        ]
        stage1_key = self._build_effects_stage_cache_key("geometry", image, stage1_extra_parts)
        result = self._get_effects_stage_cache(stage1_key)
        if result is None:
            result = (image.convert('RGBA') if image.mode != 'RGBA' else image.copy())
            result = self._apply_transformations(result)
            # 统一走矢量几何路径，不再在此阶段做位图圆角遮罩后处理
            self._set_effects_stage_cache(stage1_key, result)

        # 阶段2：叠加样式（可缓存）
        stage2_extra_parts = [
            f"base:{stage1_key}",
            f"overlay_on:{int(bool(self._color_overlay_enabled))}",
            f"overlay_c:{str(self._color_overlay_color)}",
            f"overlay_op:{float(self._color_overlay_opacity):.4f}",
            f"grad_on:{int(bool(self._gradient_overlay_enabled))}",
            f"grad_angle:{float(self._gradient_overlay_angle):.3f}",
            f"grad_op:{float(self._gradient_overlay_opacity):.4f}",
            f"grad_colors:{str(self._gradient_overlay_colors)}",
        ]
        stage2_key = self._build_effects_stage_cache_key("overlay", image, stage2_extra_parts)
        overlay_result = self._get_effects_stage_cache(stage2_key)
        if overlay_result is None:
            overlay_result = result.copy()
            if self._color_overlay_enabled:
                overlay_result = self._apply_color_overlay(overlay_result)
            if self._gradient_overlay_enabled:
                overlay_result = self._apply_gradient_overlay(overlay_result)
            self._set_effects_stage_cache(stage2_key, overlay_result)
        result = overlay_result
        
        # 阶段3：描边与最终收敛（可缓存）
        stage3_extra_parts = [
            "vec_pipe_ver:v4",
            f"base:{stage2_key}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"stroke_type:{int(self._stroke_type)}",
            f"stroke_w:{int(self._stroke_width)}",
            f"stroke_c:{str(self._stroke_color)}",
            f"stroke_join:{str(self._stroke_join)}",
            f"stroke_cap:{str(self._stroke_cap)}",
            f"dash_len:{int(self._stroke_dash_length)}",
            f"dash_gap:{int(self._stroke_dash_gap)}",
            f"corner:{int(self._corner_radius)}",
            f"vcorner:{int(self._vector_corner_radius_tl)}:{int(self._vector_corner_radius_tr)}:"
            f"{int(self._vector_corner_radius_br)}:{int(self._vector_corner_radius_bl)}",
            f"vpath_on:{int(bool(self._vector_path_enabled))}",
            f"vpath_pts:{str(self._vector_path_points)}",
            f"vpath_mode:{str(self._vector_path_mode)}",
            f"vpath_bezier:{str(self._vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self._vector_path_closed))}",
            f"vpath_link:{str(self._vector_handle_link_mode)}",
            f"shape:{getattr(getattr(self, '_shape_type', ''), 'value', getattr(self, '_shape_type', ''))}",
            f"trap:{getattr(self, '_trapezoid_top_width', '')},{getattr(self, '_trapezoid_bottom_width', '')},{getattr(self, '_trapezoid_slope_side', '')}",
            f"poly:{getattr(self, '_polygon_rotation', '')},{getattr(self, '_polygon_corner_radius', '')}",
            f"out_size:{int(self._width)}x{int(self._height)}",
            f"fit:{int(self._fit_mode)}",
        ]
        stage3_key = self._build_effects_stage_cache_key("stroke_finalize", image, stage3_extra_parts)
        final_result = self._get_effects_stage_cache(stage3_key)
        if final_result is None:
            final_result = result.copy()
            shape_type_value = str(getattr(getattr(self, "_shape_type", None), "value", getattr(self, "_shape_type", "rectangle")))
            non_rect_shape = shape_type_value != "rectangle"
            use_vector_stroke_pipeline = bool(
                non_rect_shape
                or self._vector_path_enabled
                or stroke_enabled
                or self._corner_radius > 0
                or getattr(self, '_vector_corner_radius_tl', 0) > 0
                or getattr(self, '_vector_corner_radius_tr', 0) > 0
                or getattr(self, '_vector_corner_radius_br', 0) > 0
                or getattr(self, '_vector_corner_radius_bl', 0) > 0
                or self._stroke_dash_length > 0
                or self._stroke_dash_gap > 0
                or self._stroke_join != "miter"
                or self._stroke_cap != "butt"
            )
            if use_vector_stroke_pipeline:
                final_result = self._apply_vector_path_effects(final_result, stroke_enabled)
            elif stroke_enabled:
                if self._stroke_type == 0:  # 内描边
                    log_branch("layer._apply_effects", "stroke_inner")
                    final_result = self._apply_inner_stroke(final_result)
                elif self._stroke_type == 1:  # 居中描边
                    log_branch("layer._apply_effects", "stroke_center")
                    final_result = self._apply_center_stroke(final_result)
                elif self._stroke_type == 2:  # 外描边
                    log_branch("layer._apply_effects", "stroke_outer")
                    final_result = self._apply_outer_stroke(final_result)

            # 非矢量管线才强制收敛到图层尺寸；矢量管线允许外扩（居中/外描边）
            if (not use_vector_stroke_pipeline) and self._fit_mode != 2 and (final_result.width != self._width or final_result.height != self._height):
                if not is_batch_mode:
                    print(f"警告：应用特效后图像尺寸变化: {final_result.width}x{final_result.height}，调整为图层尺寸: {self._width}x{self._height}")
                final_result = final_result.resize((self._width, self._height), Resampling.BICUBIC)
            self._set_effects_stage_cache(stage3_key, final_result)

        self._render_offset_x = int(getattr(final_result, 'info', {}).get('vector_offset_x', 0))
        self._render_offset_y = int(getattr(final_result, 'info', {}).get('vector_offset_y', 0))
        if not is_batch_mode:
            print(f"应用特效后图像尺寸: {final_result.width}x{final_result.height}, 图层尺寸: {self._width}x{self._height}")
        return final_result

    def _build_rounded_rect_outline_points_px(self):
        from app.utils.vector_layer_geometry import build_rounded_rect_outline_points

        return build_rounded_rect_outline_points(
            float(self._width),
            float(self._height),
            float(self._corner_radius),
            float(self._vector_corner_radius_tl),
            float(self._vector_corner_radius_tr),
            float(self._vector_corner_radius_br),
            float(self._vector_corner_radius_bl),
        )

    def _build_vector_outline_points_px(self):
        from app.utils.vector_layer_geometry import build_vector_outline_points_px

        return build_vector_outline_points_px(
            int(self._width),
            int(self._height),
            int(self._corner_radius),
            int(self._vector_corner_radius_tl),
            int(self._vector_corner_radius_tr),
            int(self._vector_corner_radius_br),
            int(self._vector_corner_radius_bl),
            bool(self._vector_path_enabled),
            str(self._vector_path_mode),
            self._vector_path_points,
            self._vector_bezier_nodes,
            bool(self._vector_path_closed),
            str(getattr(getattr(self, "_shape_type", "rectangle"), "value", getattr(self, "_shape_type", "rectangle"))),
            int(getattr(self, "_trapezoid_top_width", 100)),
            int(getattr(self, "_trapezoid_bottom_width", 80)),
            str(getattr(self, "_trapezoid_slope_side", "right")),
            float(getattr(self, "_polygon_rotation", 0.0)),
            int(getattr(self, "_polygon_corner_radius", 0)),
        )

    def _apply_vector_path_effects(self, image, stroke_enabled):
        """基于可编辑路径应用内容裁剪与描边几何，保证导出一致"""
        from app.utils.vector_layer_effects import VectorEffectParams, apply_vector_path_effects

        p = VectorEffectParams(
            width=int(self._width),
            height=int(self._height),
            corner_radius=int(self._corner_radius),
            vector_corner_radius_tl=int(self._vector_corner_radius_tl),
            vector_corner_radius_tr=int(self._vector_corner_radius_tr),
            vector_corner_radius_br=int(self._vector_corner_radius_br),
            vector_corner_radius_bl=int(self._vector_corner_radius_bl),
            vector_path_enabled=bool(self._vector_path_enabled),
            vector_path_points=self._vector_path_points,
            vector_path_mode=str(self._vector_path_mode),
            vector_bezier_nodes=self._vector_bezier_nodes,
            vector_path_closed=bool(self._vector_path_closed),
            shape_type=str(getattr(getattr(self, "_shape_type", "rectangle"), "value", getattr(self, "_shape_type", "rectangle"))),
            trapezoid_top_width=int(getattr(self, "_trapezoid_top_width", 100)),
            trapezoid_bottom_width=int(getattr(self, "_trapezoid_bottom_width", 80)),
            trapezoid_slope_side=str(getattr(self, "_trapezoid_slope_side", "right")),
            polygon_rotation=float(getattr(self, "_polygon_rotation", 0.0)),
            polygon_corner_radius=int(getattr(self, "_polygon_corner_radius", 0)),
            stroke_enabled=bool(stroke_enabled),
            stroke_width=int(self._stroke_width),
            stroke_type=int(self._stroke_type),
            stroke_color=tuple(self._stroke_color),
            stroke_join=str(self._stroke_join),
            stroke_cap=str(self._stroke_cap),
            stroke_dash_length=int(self._stroke_dash_length),
            stroke_dash_gap=int(self._stroke_dash_gap),
        )
        result = apply_vector_path_effects(image, p, alpha_composite=self._safe_alpha_composite)
        self._render_offset_x = int(result.info.get("vector_offset_x", 0))
        self._render_offset_y = int(result.info.get("vector_offset_y", 0))
        return result

    def _apply_inner_stroke(self, image):
        """应用内向描边效果，保持图层尺寸不变 - 使用现代样式渲染器"""
        if image is None or self._stroke_width <= 0:
            return image

        try:
            # 强制使用本地几何描边实现，确保颜色/对齐/透明参数稳定生效
            raise RuntimeError("force_legacy_stroke_pipeline")
            # 🚀 使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代内描边，宽度: {self._stroke_width}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:
                quality = "fast"
            elif image.width * image.height > 250000:
                quality = "medium"
            else:
                quality = "high"

            result = modern_renderer.apply_modern_stroke(
                image, self._stroke_width, self._stroke_color, "inner", quality, self._corner_radius
            )

            if result is not None:
                print(f"[图层效果] 现代内描边成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代内描边返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代内描边失败: {modern_e}")
            # 降级到原有实现
            # 保持原始图层尺寸
            result_width = self._width
            result_height = self._height

            # 创建高质量描边蒙版
            stroke_width = min(self._stroke_width, min(result_width, result_height) // 4)  # 限制描边宽度
            stroke_mask = self._create_stroke_mask(result_width, result_height, stroke_width, self._corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self._stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 使用改进的合成方式避免黑色边缘
            result = self._safe_alpha_composite(image.convert('RGBA'), stroke_layer)

            # 将原图像内容粘贴到描边上方（保留原图像内容）
            if stroke_width * 2 < result_width and stroke_width * 2 < result_height:
                # 创建内容区域的高质量蒙版
                inner_radius = max(0, self._corner_radius - stroke_width) if self._corner_radius > 0 else 0
                content_mask = self._create_content_mask(result_width, result_height, stroke_width, inner_radius)

                # 缩放原图像以适应内容区域
                content_width = result_width - stroke_width * 2
                content_height = result_height - stroke_width * 2
                scaled_image = image.resize((content_width, content_height), Resampling.LANCZOS)

                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (stroke_width, stroke_width), scaled_image)
                content_layer.putalpha(content_mask)

                # 使用改进的合成方式
                result = self._safe_alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用内向描边效果时出错: {e}")
            return image

    def _apply_center_stroke(self, image):
        """应用居中描边效果，保持图层尺寸不变 - 使用现代样式渲染器"""
        if image is None or self._stroke_width <= 0:
            return image

        try:
            # 强制使用本地几何描边实现，确保颜色/对齐/透明参数稳定生效
            raise RuntimeError("force_legacy_stroke_pipeline")
            # 🚀 使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代居中描边，宽度: {self._stroke_width}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:
                quality = "fast"
            elif image.width * image.height > 250000:
                quality = "medium"
            else:
                quality = "high"

            result = modern_renderer.apply_modern_stroke(
                image, self._stroke_width, self._stroke_color, "center", quality, self._corner_radius
            )

            if result is not None:
                print(f"[图层效果] 现代居中描边成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代居中描边返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代居中描边失败: {modern_e}")
            # 降级到原有实现
            # 保持原始图层尺寸
            result_width = self._width
            result_height = self._height

            # 居中描边：一半向内，一半向外，但最终保持图层尺寸
            half_stroke = self._stroke_width / 2.0

            # 创建高质量居中描边蒙版
            inner_stroke = int(half_stroke)
            stroke_mask = self._create_center_stroke_mask(result_width, result_height, inner_stroke, self._corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self._stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 使用改进的合成方式避免黑色边缘
            result = self._safe_alpha_composite(image.convert('RGBA'), stroke_layer)

            # 将原图像内容缩放并居中放置
            if inner_stroke * 2 < result_width and inner_stroke * 2 < result_height:
                # 创建内容区域的高质量蒙版
                inner_radius = max(0, self._corner_radius - half_stroke) if self._corner_radius > 0 else 0
                content_mask = self._create_content_mask(result_width, result_height, inner_stroke, inner_radius)

                # 缩放原图像以适应内容区域
                content_width = result_width - inner_stroke * 2
                content_height = result_height - inner_stroke * 2
                scaled_image = image.resize((content_width, content_height), Resampling.LANCZOS)

                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (inner_stroke, inner_stroke), scaled_image)
                content_layer.putalpha(content_mask)

                # 使用改进的合成方式
                result = self._safe_alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用居中描边效果时出错: {e}")
            return image

    def _apply_outer_stroke(self, image):
        """应用外描边效果 - 使用现代样式渲染器（不改变图层尺寸）"""
        if image is None or self._stroke_width <= 0:
            return image

        try:
            # 强制使用本地几何描边实现，确保颜色/对齐/透明参数稳定生效
            raise RuntimeError("force_legacy_stroke_pipeline")
            # 🚀 使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代外描边，宽度: {self._stroke_width}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:
                quality = "fast"
            elif image.width * image.height > 250000:
                quality = "medium"
            else:
                quality = "high"

            result = modern_renderer.apply_modern_stroke(
                image, self._stroke_width, self._stroke_color, "outer", quality, self._corner_radius
            )

            if result is not None:
                print(f"[图层效果] 现代外描边成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代外描边返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代外描边失败: {modern_e}")
            # 降级到原有实现
            # 外描边会增加图层尺寸
            stroke_width = self._stroke_width
            expanded_width = self._width + stroke_width * 2
            expanded_height = self._height + stroke_width * 2

            # 创建扩展画布
            expanded_image = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))

            # 创建高质量外描边蒙版
            stroke_mask = self._create_outer_stroke_mask(expanded_width, expanded_height, stroke_width, self._corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (expanded_width, expanded_height), self._stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 使用改进的合成方式避免黑色边缘
            expanded_image = self._safe_alpha_composite(expanded_image, stroke_layer)

            # 将内容图层放到中央并按内轮廓裁切，确保与描边几何严格一致
            content_layer = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))
            content_layer.paste(image, (stroke_width, stroke_width), image)
            content_mask = self._create_content_mask(expanded_width, expanded_height, stroke_width, self._corner_radius)
            content_layer.putalpha(content_mask)
            expanded_image = self._safe_alpha_composite(expanded_image, content_layer)

            return expanded_image

        except Exception as e:
            print(f"应用外描边效果时出错: {e}")
            return image

    def _apply_corner_radius_improved(self, image):
        """改进的圆角处理，使用现代样式渲染器"""
        if image is None or self._corner_radius <= 0:
            return image

        try:
            # 🚀 新方案：使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代样式渲染器，半径: {self._corner_radius}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:  # 大图像使用快速模式
                quality = "fast"
            elif image.width * image.height > 250000:  # 中图像使用中等质量
                quality = "medium"
            else:  # 小图像使用高质量
                quality = "high"

            result = modern_renderer.apply_modern_corner_radius(image, self._corner_radius, quality)

            if result is not None:
                print(f"[图层效果] 现代圆角渲染成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代圆角渲染返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代圆角处理失败: {modern_e}")
            # 降级到增强圆角渲染器
            try:
                from app.utils.enhanced_corner_renderer import get_enhanced_corner_renderer
                enhanced_renderer = get_enhanced_corner_renderer()
                result = enhanced_renderer.apply_enhanced_corner_radius(image, self._corner_radius)
                if result is not None:
                    return result
            except Exception as enhanced_e:
                print(f"[图层效果] 增强圆角处理也失败: {enhanced_e}")
            # 继续降级到终极圆角渲染器
            try:
                from app.utils.enhanced_corner_renderer import get_ultimate_corner_renderer
                ultimate_renderer = get_ultimate_corner_renderer()

                print(f"[图层效果] 使用终极圆角渲染器，半径: {self._corner_radius}")

                result = ultimate_renderer.apply_ultimate_corner_radius(image, self._corner_radius)

                if result is not None:
                    print(f"[图层效果] 终极圆角渲染成功")
                    return result
                else:
                    print(f"[图层效果] 终极圆角渲染返回None，使用降级方案")

            except Exception as ultimate_e:
                print(f"[图层效果] 终极圆角处理失败: {ultimate_e}")



        # 最终降级：使用优化的传统方法
        try:
            print(f"[图层效果] 使用优化传统圆角处理，半径: {self._corner_radius}")

            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # 创建优化的圆角蒙版
            mask = self._create_optimized_corner_mask(self._width, self._height, self._corner_radius)

            # 使用numpy进行精确的Alpha混合
            import numpy as np

            # 分离RGBA通道
            r, g, b, a = image.split()

            # 转换为numpy数组进行精确计算
            a_array = np.array(a, dtype=np.float32) / 255.0
            mask_array = np.array(mask, dtype=np.float32) / 255.0

            # 精确的Alpha混合
            new_alpha_array = a_array * mask_array

            # 转换回PIL格式
            new_alpha_array = np.clip(new_alpha_array * 255, 0, 255).astype(np.uint8)
            new_alpha = Image.fromarray(new_alpha_array, mode='L')

            # 重新组合图像
            result = Image.merge('RGBA', (r, g, b, new_alpha))

            print(f"[图层效果] 优化传统圆角处理完成")
            return result

        except Exception as fallback_e:
            print(f"[图层效果] 所有圆角处理方法都失败: {fallback_e}")
            return image

    def _create_optimized_corner_mask(self, width, height, radius):
        """创建优化的圆角蒙版，平衡质量和性能"""
        try:
            # 🎯 智能超采样：根据半径大小调整超采样倍数
            if radius <= 5:
                scale = 2  # 小半径用2倍超采样
            elif radius <= 15:
                scale = 3  # 中等半径用3倍超采样
            else:
                scale = 4  # 大半径用4倍超采样

            large_width = width * scale
            large_height = height * scale
            large_radius = radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 绘制圆角矩形
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=large_radius,
                fill=255
            )

            # 🎯 优化：根据半径大小调整模糊强度
            if radius > 10:
                # 大半径：使用轻微模糊进一步平滑
                large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=0.8))
            elif radius > 5:
                # 中等半径：使用很轻的模糊
                large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=0.4))
            # 小半径不需要额外模糊

            # 缩放回原始尺寸，使用最高质量重采样
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            # 🎯 最终优化：对小半径进行微调
            if radius <= 3:
                mask = mask.filter(ImageFilter.GaussianBlur(radius=0.1))

            return mask

        except Exception as e:
            print(f"[图层效果] 创建优化圆角蒙版失败: {e}")
            # 回退到传统平滑蒙版
            return self._create_smooth_corner_mask(width, height, radius)

    def _create_smooth_corner_mask(self, width, height, radius):
        """创建平滑的圆角蒙版，使用抗锯齿（降级方案）"""
        try:
            # 创建更大的蒙版用于抗锯齿
            scale = 4  # 超采样倍数
            large_width = width * scale
            large_height = height * scale
            large_radius = radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 绘制圆角矩形
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=large_radius,
                fill=255
            )

            # 缩放回原始尺寸，这会产生抗锯齿效果
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"[图层效果] 创建平滑圆角蒙版失败: {e}")
            # 回退到最简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            return mask

    def _create_stroke_mask(self, width, height, stroke_width, corner_radius):
        """创建高质量的描边蒙版，避免黑色弧线"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = stroke_width * scale
            large_radius = corner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 外层边界（图层边缘）
            outer_radius = large_radius if large_radius > 0 else 0
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=int(outer_radius),
                fill=255
            )

            # 内层边界（描边内边缘）
            inner_radius = max(0, large_radius - large_stroke) if large_radius > 0 else 0

            if large_stroke * 2 < large_width and large_stroke * 2 < large_height:
                draw.rounded_rectangle(
                    (int(large_stroke), int(large_stroke),
                     large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                    radius=int(inner_radius),
                    fill=0
                )

            # 缩放回原始尺寸，产生抗锯齿效果
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建描边蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)

            outer_radius = corner_radius if corner_radius > 0 else 0
            draw.rounded_rectangle((0, 0, width-1, height-1), radius=outer_radius, fill=255)

            inner_radius = max(0, corner_radius - stroke_width) if corner_radius > 0 else 0
            if stroke_width * 2 < width and stroke_width * 2 < height:
                draw.rounded_rectangle(
                    (stroke_width, stroke_width, width - stroke_width - 1, height - stroke_width - 1),
                    radius=inner_radius, fill=0
                )

            return mask

    def _create_content_mask(self, width, height, stroke_width, inner_radius):
        """创建内容区域的高质量蒙版"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = stroke_width * scale
            large_radius = inner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 绘制内容区域
            draw.rounded_rectangle(
                (int(large_stroke), int(large_stroke),
                 large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                radius=int(large_radius),
                fill=255
            )

            # 缩放回原始尺寸
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建内容蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle(
                (stroke_width, stroke_width, width - stroke_width - 1, height - stroke_width - 1),
                radius=inner_radius, fill=255
            )
            return mask

    def _create_center_stroke_mask(self, width, height, inner_stroke, corner_radius):
        """创建居中描边的高质量蒙版"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = inner_stroke * scale
            large_radius = corner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 外层边界（描边外边缘）
            outer_radius = large_radius + large_stroke if large_radius > 0 else large_stroke
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=int(outer_radius),
                fill=255
            )

            # 内层边界（描边内边缘）
            inner_radius = max(0, large_radius - large_stroke) if large_radius > 0 else 0

            if large_stroke * 2 < large_width and large_stroke * 2 < large_height:
                draw.rounded_rectangle(
                    (int(large_stroke), int(large_stroke),
                     large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                    radius=int(inner_radius),
                    fill=0
                )

            # 缩放回原始尺寸
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建居中描边蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)

            outer_radius = corner_radius + inner_stroke if corner_radius > 0 else inner_stroke
            draw.rounded_rectangle((0, 0, width-1, height-1), radius=outer_radius, fill=255)

            inner_radius = max(0, corner_radius - inner_stroke) if corner_radius > 0 else 0
            if inner_stroke * 2 < width and inner_stroke * 2 < height:
                draw.rounded_rectangle(
                    (inner_stroke, inner_stroke, width - inner_stroke - 1, height - inner_stroke - 1),
                    radius=inner_radius, fill=0
                )

            return mask

    def _create_outer_stroke_mask(self, width, height, stroke_width, corner_radius):
        """创建外描边的高质量蒙版"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = stroke_width * scale
            large_radius = corner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 外层边界（描边外边缘）
            outer_radius = large_radius + large_stroke if large_radius > 0 else large_stroke
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=int(outer_radius),
                fill=255
            )

            # 内层边界（原图像边缘）
            inner_radius = large_radius if large_radius > 0 else 0
            draw.rounded_rectangle(
                (int(large_stroke), int(large_stroke),
                 large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                radius=int(inner_radius),
                fill=0
            )

            # 缩放回原始尺寸
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建外描边蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)

            outer_radius = corner_radius + stroke_width if corner_radius > 0 else stroke_width
            draw.rounded_rectangle((0, 0, width-1, height-1), radius=outer_radius, fill=255)

            inner_radius = corner_radius if corner_radius > 0 else 0
            draw.rounded_rectangle(
                (stroke_width, stroke_width, width - stroke_width - 1, height - stroke_width - 1),
                radius=inner_radius, fill=0
            )

            return mask

    def _safe_alpha_composite(self, base, overlay):
        """安全的alpha合成，避免黑色边缘问题 - 使用高质量修复器"""
        try:
            # 🔧 修复：使用高质量修复器进行合成，解决深色边缘问题
            from app.utils.image_quality_fixer import get_image_quality_fixer
            quality_fixer = get_image_quality_fixer()
            
            result = quality_fixer.composite_with_quality(
                background=base,
                foreground=overlay,
                position=(0, 0),
                opacity=1.0,
                fix_edges=True,
                enhance_aa=True
            )
            
            print(f"[图层效果] 使用高质量安全合成")
            return result
            
        except Exception as quality_e:
            print(f"高质量安全合成失败: {quality_e}，使用传统方法")
            # 降级到传统方法
            try:
                # 确保两个图像都是RGBA模式
                if base.mode != 'RGBA':
                    base = base.convert('RGBA')
                if overlay.mode != 'RGBA':
                    overlay = overlay.convert('RGBA')

                # 使用PIL的paste方法进行合成，这样可以更好地处理透明度
                result = base.copy()
                result.paste(overlay, (0, 0), overlay)

                return result

            except Exception as e:
                print(f"安全alpha合成失败，回退到标准方法: {e}")
                return Image.alpha_composite(base, overlay)

    def _apply_transformations(self, image):
        """应用图像变换（旋转和翻转）"""
        if image is None:
            return None
        
        result = image
        
        # 第一步：应用手动翻转
        if self._flip_horizontal:
            result = result.transpose(Transpose.FLIP_LEFT_RIGHT)
            print("应用水平翻转")
        
        if self._flip_vertical:
            result = result.transpose(Transpose.FLIP_TOP_BOTTOM)
            print("应用垂直翻转")
        
        # 第二步：应用手动旋转
        if abs(self._rotation) > 0.001:  # 避免浮点数精度问题
            # 检查是否是90度的倍数旋转
            rotation_angle = self._rotation % 360
            is_90_degree_rotation = (abs(rotation_angle % 90) < 0.1)
            
            if is_90_degree_rotation:
                # 对于90度的倍数旋转，使用expand=True以保持图像完整性
                result = HighQualityResampler.rotate_high_quality(
                    result,
                    -self._rotation,
                    expand=True,
                    resample=Resampling.BICUBIC,
                    enable_premultiplied=True
                )
                print(f"应用90度倍数旋转: {self._rotation}度 (扩展画布)")
                
                # 如果旋转后尺寸与图层尺寸不匹配，需要调整
                if result.width != self._width or result.height != self._height:
                    # 对于智能缩放模式，保持宽高比
                    if self._fit_mode == 1:  # 智能缩放不裁剪
                        # 计算等比缩放以适应图层尺寸
                        scale_ratio = min(self._width / result.width, self._height / result.height)
                        new_width = int(result.width * scale_ratio)
                        new_height = int(result.height * scale_ratio)
                        
                        # 缩放图像
                        scaled_result = result.resize((new_width, new_height), Resampling.BICUBIC)
                        
                        # 创建图层尺寸的画布并居中放置
                        centered_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                        paste_x = (self._width - new_width) // 2
                        paste_y = (self._height - new_height) // 2
                        centered_result.paste(scaled_result, (paste_x, paste_y), scaled_result)
                        result = centered_result
                        
                        print(f"旋转后智能缩放: {result.width}x{result.height} -> {new_width}x{new_height}, 居中于 ({paste_x}, {paste_y})")
                    else:
                        # 对于其他模式，直接调整尺寸
                        result = result.resize((self._width, self._height), Resampling.BICUBIC)
                        print(f"旋转后调整尺寸: {self._width}x{self._height}")
            else:
                # 对于非90度倍数的旋转，也扩展画布以避免裁剪
                result = result.rotate(
                    -self._rotation,  # PIL使用逆时针为正，我们使用顺时针为正
                    expand=True,       # 扩展画布以容纳完整的旋转后图像
                    fillcolor=(0, 0, 0, 0),  # 透明填充
                    resample=Resampling.BICUBIC   # 高质量重采样
                )
                print(f"应用任意角度旋转: {self._rotation}度 (扩展画布)")
        
        # 第三步：应用随机变换（在手动变换之后）
        result = self._apply_random_transformations(result)
        
        return result
    
    def _apply_random_transformations(self, image):
        """应用随机变换（随机缩放和随机旋转）
        
        注意：随机位置偏移在渲染时处理，不在此处理
        """
        if image is None:
            return None
        
        result = image
        
        # 应用随机缩放
        if self._random_scale_enabled and abs(self._current_random_scale - 1.0) > 0.001:
            # 计算新尺寸
            new_width = int(result.width * self._current_random_scale)
            new_height = int(result.height * self._current_random_scale)
            
            # 缩放图像
            scaled_image = HighQualityResampler.resize(result, (new_width, new_height), method=Resampling.LANCZOS, enable_sharpening=False)
            
            # 创建一个与原图层尺寸相同的透明画布
            canvas = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
            
            # 计算居中位置
            paste_x = (self._width - new_width) // 2
            paste_y = (self._height - new_height) // 2
            
            # 将缩放后的图像粘贴到画布中央
            canvas.paste(scaled_image, (paste_x, paste_y), scaled_image if scaled_image.mode == 'RGBA' else None)
            
            result = canvas
            print(f"应用随机缩放: {self._current_random_scale:.3f}")
        
        # 应用随机旋转
        if self._random_rotation_enabled and abs(self._current_random_rotation) > 0.001:
            result = result.rotate(
                -self._current_random_rotation,  # PIL使用逆时针为正，我们使用顺时针为正
                expand=False,      # 不扩展画布尺寸
                fillcolor=(0, 0, 0, 0),  # 透明填充
                resample=Resampling.BICUBIC   # 高质量重采样
            )
            print(f"应用随机旋转: {self._current_random_rotation:.1f}度")
        
        return result
    
    def reset_transformations(self):
        """重置所有变换"""
        self._rotation = 0.0
        self._flip_horizontal = False
        self._flip_vertical = False
        self._cached_image = None
        self.changed.emit()
        print("重置所有变换")
    
    def apply_rotation_preset(self, preset):
        """应用旋转预设"""
        presets = {
            'rotate_90': 90.0,
            'rotate_180': 180.0,
            'rotate_270': 270.0,
            'rotate_45': 45.0,
            'rotate_-45': -45.0
        }
        
        if preset in presets:
            self.rotation = presets[preset]
            print(f"应用旋转预设: {preset} ({presets[preset]}度)")
    
    def _create_error_image(self):
        """创建错误图像（红色底色）"""
        error_image = Image.new('RGBA', (self._width, self._height), (255, 0, 0, 128))
        return error_image
    
    def _resize_with_premultiplied_alpha(self, image, size):
        """使用预乘Alpha方法缩放图像，避免半透明边缘暗晕"""
        try:
            import numpy as np
            
            if image.mode != 'RGBA':
                return image.resize(size, Resampling.BICUBIC)
            
            # 转换为浮点数组
            arr = np.array(image, dtype=np.float32) / 255.0
            rgb = arr[:, :, :3]
            alpha = arr[:, :, 3:4]
            
            # 预乘Alpha
            premul_rgb = rgb * alpha
            premul_img_arr = np.concatenate([premul_rgb, alpha], axis=2)
            premul_img = Image.fromarray((np.clip(premul_img_arr, 0.0, 1.0) * 255.0).astype(np.uint8), 'RGBA')
            
            # 缩放
            resized_premul = premul_img.resize(size, Resampling.BICUBIC)
            
            # 反预乘
            resized_arr = np.array(resized_premul, dtype=np.float32) / 255.0
            r_rgb = resized_arr[:, :, :3]
            r_alpha = resized_arr[:, :, 3:4]
            
            # 避免除零
            mask = r_alpha > 1e-6
            unpremul_rgb = np.zeros_like(r_rgb)
            mask_3ch = np.repeat(mask, 3, axis=2)
            np.divide(r_rgb, r_alpha, out=unpremul_rgb, where=mask_3ch)
            
            # 重组
            result_arr = np.concatenate([unpremul_rgb, r_alpha], axis=2)
            return Image.fromarray((np.clip(result_arr, 0.0, 1.0) * 255.0).astype(np.uint8), 'RGBA')
            
        except Exception as e:
            print(f"预乘Alpha缩放失败: {e}")
            return image.resize(size, Resampling.BICUBIC)

    def _mark_dirty(self):
        """标记图层状态为脏，需要更新"""
        self._state_dirty = True
        self._cache_valid = False
        # 🔧 修复：清除所有图像缓存
        self._cached_image = None
        if hasattr(self, 'cached_image'):
            self.cached_image = None
        # 清理缓存路径，确保重新验证
        self._cached_image_path = None

    def _is_cache_valid(self):
        """检查缓存是否有效"""
        if not self._cache_valid:
            return False
        if not hasattr(self, '_cached_image') or self._cached_image is None:
            return False
        if hasattr(self, '_current_image_path') and self._current_image_path:
            # 检查缓存路径是否匹配当前路径
            return (hasattr(self, '_cached_image_path') and
                   self._cached_image_path == self._current_image_path)
        return True

    def _validate_cache(self):
        """验证并更新缓存状态"""
        if self._is_cache_valid():
            return True
        # 缓存无效，清理
        self.clear_cache()
        return False

    def clear_cache(self):
        """清理图像缓存，释放内存"""
        try:
            if hasattr(self, '_cached_image') and self._cached_image:
                # 关闭PIL图像对象
                if hasattr(self._cached_image, 'close'):
                    self._cached_image.close()
                self._cached_image = None

            if hasattr(self, '_cached_images') and self._cached_images:
                # 清理多个缓存图像
                for img in self._cached_images.values():
                    if img and hasattr(img, 'close'):
                        img.close()
                self._cached_images.clear()

            # 清理其他可能的图像缓存
            if hasattr(self, 'cached_image') and self.cached_image:
                if hasattr(self.cached_image, 'close'):
                    self.cached_image.close()
                self.cached_image = None

            # 重置缓存状态
            self._cache_valid = False
            self._cached_image_path = None

        except Exception as e:
            # 静默处理清理错误，不影响主要功能
            pass

    def serialize(self):
        """将图层序列化为字典"""
        # 使用统一的序列化工具
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.serialize_layer(self)
    
    def duplicate(self, parent=None):
        """复制图层，创建一个完全相同的新实例"""
        # 使用统一的序列化工具进行复制
        from app.utils.layer_serializer import LayerSerializer
        
        # 传递parent参数
        kwargs = {}
        if parent is not None:
            kwargs['parent'] = parent
        else:
            kwargs['parent'] = self.parent()
            
        return LayerSerializer.duplicate_layer(self, target_layer_class=Layer, **kwargs)
    
    @classmethod
    def deserialize(cls, data, parent=None):
        """从字典反序列化图层"""
        # 使用统一的序列化工具
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.deserialize_layer(data, cls, parent=parent)
