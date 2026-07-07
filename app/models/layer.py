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



from app.models.layer_attrs import LayerAttrs
from app.models.layer_vector import LayerVector
from app.models.layer_image import LayerImage
from app.models.layer_effects import LayerEffects
from app.models.layer_transform import LayerTransform

class Layer(QObject, LayerAttrs, LayerVector, LayerImage, LayerEffects, LayerTransform):
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
    


# 以下方法实现位于各个 mixin 模块中，通过多重继承组合进来。
# 主类仅保留类级属性、changed 信号与 __init__。

__all__ = [
    'Layer',
    'FitMode',
    'CropDirection',
]
