#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layer 类（聚合类，2674 行 → 6 个聚焦子 mixin + 1 个聚合类）

为降低单文件体积，原 Layer 单一巨型类已拆分为 6 个聚焦子 mixin：

  - layer_image_source_mixin.py    (LayerImageSourceMixin)
      图像源管理 + 加载/缩放/裁剪 + 图像缓存
  - layer_attrs_mixin.py            (LayerAttrsMixin)
      所有 @property getter/setter（基础 + 克隆 + 描边 + 圆角 + 形状 + 绑定 + 渐变）
  - layer_transform_mixin.py        (LayerTransformMixin)
      rotation/flip/aspect_ratio + 随机变换 + 变换操作 + _apply_transformations
  - layer_vector_mixin.py           (LayerVectorMixin)
      vector_path_* + 4 角圆角 + 路径编辑 + _use_rectangle_vector_pipeline
  - layer_rendering_mixin.py        (LayerRenderingMixin)
      _apply_effects 三阶段渲染管线 + 描边 + 形状蒙版 + 颜色/渐变叠加 + 边缘处理
  - layer_serialize_mixin.py        (LayerSerializeMixin)
      serialize/deserialize/duplicate/from_dict/to_dict

Layer 通过多继承聚合上述 mixin，外部 `from app.models.layer_new import
Layer` / `from app.models.layer_new import FitMode, CropDirection` 写法继续有效。

⚠️ 与 layer_attrs/transform/vector/image/effects 区分：那些是 Layer 类的早期
   拆分产物（b24b2e3 commit）中的独立 mixin（基于 object），本文件中的
   *_mixin 后缀文件是当前实际使用的 Layer 拆分。
"""

import os
import builtins
import uuid
import threading
import logging
from collections import OrderedDict
from enum import Enum, auto

from PySide6.QtCore import QObject, Signal

from app.models.layer_properties import LayerPropertyManager, CommonLayerOperations
from app.models.layer_image_source_mixin import LayerImageSourceMixin
from app.models.layer_attrs_mixin import LayerAttrsMixin
from app.models.layer_transform_mixin import LayerTransformMixin
from app.models.layer_vector_mixin import LayerVectorMixin
from app.models.layer_rendering_mixin import LayerRenderingMixin
from app.models.layer_serialize_mixin import LayerSerializeMixin

logger = logging.getLogger(__name__)

# 模块级 verbose flag（与 layer_attrs_mixin / layer_transform_mixin / layer_rendering_mixin 共享）
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


class Layer(
    LayerImageSourceMixin,
    LayerAttrsMixin,
    LayerTransformMixin,
    LayerVectorMixin,
    LayerRenderingMixin,
    LayerSerializeMixin,
    QObject,
):
    """图层模型类（聚合类，行为与原单一类完全一致）。

    拆分前所有方法定义均保留在 6 个子 mixin 中；本类仅持有：

    - 类级 effects stage 缓存（_effects_stage_cache_*）和形状蒙版缓存槽位
    - 实例属性（_property_manager / _operations / _cached_image 等）
    - __init__ 初始化 + 随机变换状态

    方法解析顺序 (MRO)：ImageSource → Attrs → Transform → Vector → Rendering →
    Serialize → QObject，确保跨 mixin 调用 self.* 能正确解析。
    """

    # 类级 effects stage 缓存（由 LayerRenderingMixin 使用，保留在这里以保证 id 一致）
    _effects_stage_cache_lock = threading.RLock()
    _effects_stage_cache = OrderedDict()
    _effects_stage_cache_max_entries = 1024

    # 图像适配方式常量（与LegacyLayer兼容）
    FIT_SMART_CROP = 0
    FIT_SMART_FIT = 1

    # 裁剪方向常量（与LegacyLayer兼容）
    CROP_CENTER = 0
    CROP_TOP = 1
    CROP_BOTTOM = 2
    CROP_LEFT = 3
    CROP_RIGHT = 4

    # 信号定义
    changed = Signal()

    def __init__(self, name="新图层", x=0, y=0, width=100, height=100, image_source=None,
                 use_original_size=False, is_folder=True, current_image_path=None, parent=None):
        super().__init__(parent)

        # 生成唯一的图层ID，确保每个图层完全独立
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
        self._cached_image_path = None
        # 源图像缓存：避免交互预览时重复读盘/网络路径
        self._cached_source_image = None
        self._cached_source_path = None
        self._cache_valid = False
        self._state_dirty = False
        self._updating = False

        # 形状蒙版缓存（由 LayerRenderingMixin 懒初始化）
        self._shape_mask_cache = {}

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

        # 渲染偏移（由 _apply_effects 写入）
        self._render_offset_x = 0
        self._render_offset_y = 0

        # 设置当前图像路径（如果提供了）
        if current_image_path:
            self._property_manager.set_property('current_image_path', current_image_path, validate=False)
        elif image_source and not is_folder and os.path.isfile(image_source):
            self._property_manager.set_property('current_image_path', image_source, validate=False)


__all__ = ["Layer", "FitMode", "CropDirection"]
