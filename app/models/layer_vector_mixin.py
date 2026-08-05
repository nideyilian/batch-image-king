#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layer 子 mixin 4: 矢量路径属性 + 路径编辑 + 路径选择策略

从原 layer_new.py 拆分。涵盖：
- 矢量属性：vector_path_enabled, vector_path_points, vector_path_mode, vector_bezier_nodes,
            vector_path_closed, vector_handle_link_mode
- 4 角 vector 圆角：vector_corner_radius_tl/tr/br/bl
- 路径转换：convert_rect_to_vector_path
- 路径编辑：update_vector_path_node, update_vector_bezier_anchor, update_vector_bezier_handle,
            set_vector_node_type, cycle_vector_node_type, insert_vector_node_after, delete_vector_node
- 渲染策略：_use_rectangle_vector_pipeline
"""

import copy
import math

from app.models.layer_properties import ShapeType


class LayerVectorMixin:
    """矢量路径属性 + 路径编辑 + 路径选择策略（拆分自 Layer）。"""

    # ==================== 4 角 vector 圆角属性 ====================
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

    # ==================== 矢量路径属性 ====================
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

    # ==================== 路径转换与编辑 ====================
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
        node = nodes[node_index]
        node['node_type'] = normalized
        if normalized != "corner":
            ax, ay = node['x'], node['y']
            in_length = math.hypot(node['in_x'] - ax, node['in_y'] - ay)
            out_length = math.hypot(node['out_x'] - ax, node['out_y'] - ay)
            if in_length < 1e-6 and out_length < 1e-6 and len(nodes) >= 2:
                previous = nodes[(node_index - 1) % len(nodes)]
                following = nodes[(node_index + 1) % len(nodes)]
                vx = following['x'] - previous['x']
                vy = following['y'] - previous['y']
                direction_length = math.hypot(vx, vy)
                if direction_length > 1e-6:
                    handle_length = min(
                        math.hypot(ax - previous['x'], ay - previous['y']),
                        math.hypot(following['x'] - ax, following['y'] - ay),
                    ) / 3.0
                    ux, uy = vx / direction_length, vy / direction_length
                    node['in_x'] = ax - ux * handle_length
                    node['in_y'] = ay - uy * handle_length
                    node['out_x'] = ax + ux * handle_length
                    node['out_y'] = ay + uy * handle_length
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
