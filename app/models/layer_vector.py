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
import logging
logger = logging.getLogger(__name__)


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


class LayerVector(object):
    """Mixin for layer_vector (split from Layer)."""

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
                logger.warning("静默异常已忽略: except Exception: in layer_vector.py", exc_info=True)
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
                logger.warning("静默异常已忽略: except Exception: in layer_vector.py", exc_info=True)
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
    