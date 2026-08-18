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


class LayerAttrs(object):
    """Mixin for layer_attrs (split from Layer)."""

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

