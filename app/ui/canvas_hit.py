# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
"""Canvas widget components."""

from collections import OrderedDict
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QMenu
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPixmap, QCursor, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, QTimer, QRunnable, QThreadPool
from app.ui.dark_theme import CursorDarkTheme
from app.utils.layer_tree import (    child_indices_for_group,    expand_group_indices,    group_bounds,    is_layer_group,    is_effectively_locked,    is_effectively_visible,)
import time
import threading

class CanvasWidgetCanvasHit(object):
    def get_layer_rect(self, layer_index):
        """获取指定图层在视图中的矩形区域"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return None

        layer = self.document.layers[layer_index]
        if layer is None:
            return None

        # 获取画布矩形
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return None

        if is_layer_group(layer):
            bounds = group_bounds(self.document.layers, layer, include_hidden=False)
            if not bounds:
                return None
            left, top, right, bottom = bounds
            return QRect(
                canvas_rect.x() + int(left * self.zoom_factor),
                canvas_rect.y() + int(top * self.zoom_factor),
                max(1, int((right - left) * self.zoom_factor)),
                max(1, int((bottom - top) * self.zoom_factor)),
            )

        expand = self._get_vector_stroke_expand_px(layer)
        # 以图层几何为“矢量容器”，边框按有效渲染边界显示，而不是旧矩形框
        offset_x = int(getattr(layer, "_render_offset_x", -expand))
        offset_y = int(getattr(layer, "_render_offset_y", -expand))
        layer_x = canvas_rect.x() + int((layer.x + offset_x) * self.zoom_factor)
        layer_y = canvas_rect.y() + int((layer.y + offset_y) * self.zoom_factor)
        layer_width = int((layer.width + expand * 2) * self.zoom_factor)
        layer_height = int((layer.height + expand * 2) * self.zoom_factor)

        return QRect(layer_x, layer_y, layer_width, layer_height)

    def _draw_group_selection(self, painter, group_index):
        """Draw a Photoshop-like transform box around the selected group."""
        if group_index < 0 or group_index >= len(self.document.layers):
            return
        group = self.document.layers[group_index]
        if not is_layer_group(group):
            return
        rect = self.get_layer_rect(group_index)
        if not rect:
            return
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 160, 230), 2, Qt.DashLine))
        painter.drawRect(rect)
        if is_effectively_locked(group, self.document.layers):
            return
        painter.setBrush(QBrush(QColor(0, 160, 230)))
        handle_size = 8
        points = [
            QPoint(rect.left(), rect.top()),
            QPoint(rect.left() + rect.width() // 2, rect.top()),
            QPoint(rect.right(), rect.top()),
            QPoint(rect.right(), rect.top() + rect.height() // 2),
            QPoint(rect.right(), rect.bottom()),
            QPoint(rect.left() + rect.width() // 2, rect.bottom()),
            QPoint(rect.left(), rect.bottom()),
            QPoint(rect.left(), rect.top() + rect.height() // 2),
        ]
        half = handle_size // 2
        for point in points:
            painter.drawRect(point.x() - half, point.y() - half, handle_size, handle_size)

    def _is_vector_container_active(self, layer) -> bool:
        if layer is None:
            return False
        shape_type = getattr(layer, 'shape_type', None)
        if shape_type is not None and hasattr(shape_type, 'value'):
            if str(shape_type.value) != "rectangle":
                return False
        elif shape_type is not None and str(shape_type) != "rectangle":
            return False
        stroke_enabled = bool(getattr(layer, 'stroke_enabled', False)) and int(getattr(layer, 'stroke_width', 0)) > 0
        return bool(
            getattr(layer, 'vector_path_enabled', False)
            or stroke_enabled
            or int(getattr(layer, 'corner_radius', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_tl', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_tr', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_br', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_bl', 0)) > 0
            or int(getattr(layer, 'stroke_dash_length', 0)) > 0
            or int(getattr(layer, 'stroke_dash_gap', 0)) > 0
            or str(getattr(layer, 'stroke_join', 'miter')) != "miter"
            or str(getattr(layer, 'stroke_cap', 'butt')) != "butt"
        )

    def _get_vector_stroke_expand_px(self, layer) -> int:
        if not self._is_vector_container_active(layer):
            return 0
        if not (bool(getattr(layer, 'stroke_enabled', False)) and int(getattr(layer, 'stroke_width', 0)) > 0):
            return 0
        stroke_w = max(1, int(getattr(layer, 'stroke_width', 1)))
        stroke_type = int(getattr(layer, 'stroke_type', 0))
        if stroke_type == 2:
            return stroke_w
        if stroke_type == 1:
            return (stroke_w + 1) // 2
        return 0

    def _get_display_rect_for_layer_position(self, layer, px: int, py: int, canvas_rect: QRect) -> QRect:
        """给定逻辑位置，返回实际绘制边界矩形（含矢量外扩与偏移）。"""
        expand = self._get_vector_stroke_expand_px(layer)
        default_off_x = -expand if expand > 0 else 0
        default_off_y = -expand if expand > 0 else 0
        off_x = int(getattr(layer, "_render_offset_x", default_off_x))
        off_y = int(getattr(layer, "_render_offset_y", default_off_y))
        w = int(getattr(layer, "width", 0)) + expand * 2
        h = int(getattr(layer, "height", 0)) + expand * 2
        x = canvas_rect.x() + int((int(px) + off_x) * self.zoom_factor)
        y = canvas_rect.y() + int((int(py) + off_y) * self.zoom_factor)
        return QRect(x, y, int(w * self.zoom_factor), int(h * self.zoom_factor))

    def _is_rectangle_shape(self, layer) -> bool:
        """判断图层是否为矩形形状（兼容枚举和值字符串）"""
        shape_type = getattr(layer, 'shape_type', None)
        if shape_type is None:
            return True
        if hasattr(shape_type, 'value'):
            return str(shape_type.value) == "rectangle"
        return str(shape_type) == "rectangle"

    def _build_rect_path(self, layer, rect: QRect) -> QPainterPath:
        """构建矩形图层的矢量路径（支持圆角）"""
        path = QPainterPath()
        if rect.width() <= 0 or rect.height() <= 0:
            return path
        ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
        if bool(getattr(layer, 'vector_path_enabled', False)):
            bezier_nodes = getattr(layer, 'vector_bezier_nodes', []) or []
            mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
            if mode == 'bezier' and len(bezier_nodes) >= 3:
                nodes = self._get_vector_bezier_nodes_screen(layer, rect)
                path.moveTo(nodes[0]['anchor'])
                for i in range(len(nodes)):
                    cur = nodes[i]
                    nxt = nodes[(i + 1) % len(nodes)]
                    path.cubicTo(cur['out'], nxt['in'], nxt['anchor'])
                path.closeSubpath()
                return path
            node_points = self._get_vector_node_points(layer, rect)
            if len(node_points) >= 3:
                path.moveTo(node_points[0])
                for pt in node_points[1:]:
                    path.lineTo(pt)
                path.closeSubpath()
                return path
        from app.utils.vector_layer_geometry import build_vector_outline_points_px

        shape_type_value = str(
            getattr(
                getattr(layer, "shape_type", "rectangle"),
                "value",
                getattr(layer, "shape_type", "rectangle"),
            )
        )
        pts, _ = build_vector_outline_points_px(
            int(getattr(layer, "width", 0) or 1),
            int(getattr(layer, "height", 0) or 1),
            int(getattr(layer, "corner_radius", 0)),
            int(getattr(layer, "vector_corner_radius_tl", 0)),
            int(getattr(layer, "vector_corner_radius_tr", 0)),
            int(getattr(layer, "vector_corner_radius_br", 0)),
            int(getattr(layer, "vector_corner_radius_bl", 0)),
            bool(getattr(layer, "vector_path_enabled", False)),
            str(getattr(layer, "vector_path_mode", "polygon")),
            getattr(layer, "vector_path_points", []),
            getattr(layer, "vector_bezier_nodes", []),
            bool(getattr(layer, "vector_path_closed", True)),
            shape_type_value,
            int(getattr(layer, "trapezoid_top_width", 100)),
            int(getattr(layer, "trapezoid_bottom_width", 80)),
            str(getattr(layer, "trapezoid_slope_side", "right")),
            float(getattr(layer, "polygon_rotation", 0.0)),
            int(getattr(layer, "polygon_corner_radius", 0)),
        )
        if len(pts) >= 3:
            z = float(self.zoom_factor)
            path.moveTo(
                QPoint(int(ox + pts[0][0] * z), int(oy + pts[0][1] * z))
            )
            for px, py in pts[1:]:
                path.lineTo(QPoint(int(ox + px * z), int(oy + py * z)))
            path.closeSubpath()
        else:
            path.addRect(QRect(int(ox), int(oy), int(getattr(layer, 'width', 0) * self.zoom_factor), int(getattr(layer, 'height', 0) * self.zoom_factor)))
        return path

    def _get_vector_node_points(self, layer, rect: QRect):
        points = getattr(layer, 'vector_path_points', []) or []
        if not points:
            return []
        ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
        result = []
        for pt in points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                px = int(ox + float(pt[0]) * self.zoom_factor)
                py = int(oy + float(pt[1]) * self.zoom_factor)
                result.append(QPoint(px, py))
        return result

    def _get_vector_bezier_nodes_screen(self, layer, rect: QRect):
        nodes = getattr(layer, 'vector_bezier_nodes', []) or []
        ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
        result = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            ax = int(ox + float(n.get('x', 0.0)) * self.zoom_factor)
            ay = int(oy + float(n.get('y', 0.0)) * self.zoom_factor)
            ix = int(ox + float(n.get('in_x', n.get('x', 0.0))) * self.zoom_factor)
            iy = int(oy + float(n.get('in_y', n.get('y', 0.0))) * self.zoom_factor)
            hx = int(ox + float(n.get('out_x', n.get('x', 0.0))) * self.zoom_factor)
            hy = int(oy + float(n.get('out_y', n.get('y', 0.0))) * self.zoom_factor)
            result.append({
                'anchor': QPoint(ax, ay),
                'in': QPoint(ix, iy),
                'out': QPoint(hx, hy),
            })
        return result

    def _get_layer_local_origin_in_rect(self, layer, rect: QRect):
        """把 layer 本地坐标 (0,0) 映射到屏幕坐标；兼容外扩描边偏移。"""
        off_x = float(getattr(layer, '_render_offset_x', 0))
        off_y = float(getattr(layer, '_render_offset_y', 0))
        ox = int(round(rect.x() - off_x * self.zoom_factor))
        oy = int(round(rect.y() - off_y * self.zoom_factor))
        return ox, oy

    def get_vector_node_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1
        layer = self.document.layers[layer_index]
        if layer is None or is_layer_group(layer) or is_effectively_locked(layer, self.document.layers):
            return -1
        if not bool(getattr(layer, 'vector_path_enabled', False)):
            return -1
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1
        handle_size = 10
        half = handle_size // 2
        mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
        if mode == 'bezier':
            anchor_points = [n['anchor'] for n in self._get_vector_bezier_nodes_screen(layer, rect)]
        else:
            anchor_points = self._get_vector_node_points(layer, rect)
        for i, p in enumerate(anchor_points):
            if QRect(p.x() - half, p.y() - half, handle_size, handle_size).contains(pos):
                return i
        return -1

    def get_vector_handle_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1, None
        layer = self.document.layers[layer_index]
        if layer is None or is_layer_group(layer) or is_effectively_locked(layer, self.document.layers):
            return -1, None
        if not bool(getattr(layer, 'vector_path_enabled', False)):
            return -1, None
        if str(getattr(layer, 'vector_path_mode', 'polygon')) != 'bezier':
            return -1, None
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1, None
        nodes = self._get_vector_bezier_nodes_screen(layer, rect)
        handle_size = 8
        half = handle_size // 2
        for i, n in enumerate(nodes):
            for t in ('in', 'out'):
                p = n[t]
                if QRect(p.x() - half, p.y() - half, handle_size, handle_size).contains(pos):
                    return i, t
        return -1, None

    def _distance_point_to_segment(self, p: QPoint, a: QPoint, b: QPoint) -> float:
        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        px, py = p.x(), p.y()
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        seg_len2 = float(vx * vx + vy * vy)
        if seg_len2 <= 1e-6:
            return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / seg_len2))
        proj_x = ax + t * vx
        proj_y = ay + t * vy
        dx = px - proj_x
        dy = py - proj_y
        return (dx * dx + dy * dy) ** 0.5

    def get_vector_segment_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1
        layer = self.document.layers[layer_index]
        if layer is None or is_layer_group(layer) or not bool(getattr(layer, 'vector_path_enabled', False)):
            return -1
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1
        mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
        closed = bool(getattr(layer, 'vector_path_closed', True))
        if mode == 'bezier':
            nodes = self._get_vector_bezier_nodes_screen(layer, rect)
            anchors = [n['anchor'] for n in nodes]
        else:
            anchors = self._get_vector_node_points(layer, rect)
        if len(anchors) < 2:
            return -1
        seg_count = len(anchors) if closed else len(anchors) - 1
        best_idx = -1
        best_dist = 1e9
        for i in range(seg_count):
            a = anchors[i]
            b = anchors[(i + 1) % len(anchors)]
            d = self._distance_point_to_segment(pos, a, b)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx if best_dist <= 14.0 else -1

    def get_layer_at_position(self, pos):
        """获取鼠标位置所在的图层索引"""
        # If a group is already selected, treat its visible child bounds as one
        # editable object so dragging in the preview keeps the group selected.
        selected_index = getattr(self.document, "selected_layer_index", -1)
        if 0 <= selected_index < len(self.document.layers):
            selected_layer = self.document.layers[selected_index]
            if is_layer_group(selected_layer) and not is_effectively_locked(selected_layer, self.document.layers):
                rect = self.get_layer_rect(selected_index)
                if rect and rect.contains(pos):
                    return selected_index

        # 从上到下（从顶层到底层）检查图层
        for i in range(len(self.document.layers) - 1, -1, -1):
            layer = self.document.layers[i]
            if layer is None or is_layer_group(layer):
                continue
            if (not is_effectively_visible(layer, self.document.layers)) or is_effectively_locked(layer, self.document.layers):
                continue

            # 判断是否启用了分身效果
            is_clone_enabled = (hasattr(layer, 'clone_enabled') and layer.clone_enabled)

            if is_clone_enabled:
                # 先检查原始位置
                rect = self.get_layer_rect(i)
                if rect and self._build_rect_path(layer, rect).contains(pos):
                    return i

                # 如果有分身功能，还需要检查所有分身位置
                try:
                    if hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                        clone_positions = layer.get_clone_positions()

                        # 获取画布矩形
                        canvas_rect = self.get_canvas_rect()
                        if not canvas_rect:
                            continue

                        # 检查每个分身位置
                        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                        positions = clone_positions
                        if mirror_mode and mirror_mode != 'none':
                            base = positions[:]
                            min_x = min([x for x, _ in base])
                            max_x = max([x + layer.width for x, _ in base])
                            min_y = min([y for _, y in base])
                            max_y = max([y + layer.height for _, y in base])
                            group_width = max_x - min_x
                            group_height = max_y - min_y
                            mirrored_positions = []
                            if mirror_mode == 'horizontal':
                                mirrored_left = self.document.canvas_width - (min_x + group_width)
                                for cx, cy in base:
                                    offset_x = cx - min_x
                                    mirrored_positions.append((mirrored_left + offset_x, cy))
                            elif mirror_mode == 'vertical':
                                mirrored_top = self.document.canvas_height - (min_y + group_height)
                                for cx, cy in base:
                                    offset_y = cy - min_y
                                    mirrored_positions.append((cx, mirrored_top + offset_y))
                            positions = positions + mirrored_positions
                        for clone_pos in positions:
                            clone_x, clone_y = clone_pos
                            clone_rect = self._get_display_rect_for_layer_position(layer, clone_x, clone_y, canvas_rect)
                            if self._build_rect_path(layer, clone_rect).contains(pos):
                                return i
                except Exception as e:
                    print(f"检查分身图层点击失败: {e}")
            else:
                # 常规图层
                rect = self.get_layer_rect(i)
                if rect and self._build_rect_path(layer, rect).contains(pos):
                    return i

        return -1  # 没有找到图层

    def get_handle_at_position(self, pos, layer_index):
        """获取鼠标位置所在的控制点索引"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1

        layer = self.document.layers[layer_index]
        if layer is None:
            return -1
        if is_layer_group(layer):
            if is_effectively_locked(layer, self.document.layers):
                return -1
            rect = self.get_layer_rect(layer_index)
            if not rect:
                return -1
            handle_size = 8
            half_handle = handle_size // 2
            handle_points = [
                QPoint(rect.left(), rect.top()),
                QPoint(rect.left() + rect.width() // 2, rect.top()),
                QPoint(rect.right(), rect.top()),
                QPoint(rect.right(), rect.top() + rect.height() // 2),
                QPoint(rect.right(), rect.bottom()),
                QPoint(rect.left() + rect.width() // 2, rect.bottom()),
                QPoint(rect.left(), rect.bottom()),
                QPoint(rect.left(), rect.top() + rect.height() // 2),
            ]
            for i, point in enumerate(handle_points):
                handle_rect = QRect(point.x() - half_handle, point.y() - half_handle, handle_size, handle_size)
                if handle_rect.contains(pos):
                    return i
            return -1
        if is_effectively_locked(layer, self.document.layers) or getattr(layer, 'use_original_size', False):
            return -1  # 锁定的图层或使用原始尺寸的图层不能调整大小
        if self._is_vector_container_active(layer):
            # 矢量容器模式下禁用旧矩形缩放控制点，避免和路径锚点编辑冲突
            return -1

        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1

        handle_size = 8
        half_handle = handle_size // 2

        # 获取图层形状类型
        if hasattr(layer, 'shape_type'):
            # 异形图层使用shape_type属性
            try:
                from app.models.layer_properties import ShapeType
            except ImportError:
                from app.models.shaped_layer_new import ShapeType
            shape_type = layer.shape_type
            # 将ShapeType映射到对应的绘制逻辑
            if shape_type == ShapeType.RECTANGLE:
                shape = "rectangle"
            elif shape_type == ShapeType.CIRCLE:
                shape = "circle"
            elif shape_type == ShapeType.RIGHT_TRAPEZOID:
                shape = "right_trapezoid"
            elif shape_type == ShapeType.PENTAGON:
                shape = "pentagon"
            elif shape_type == ShapeType.HEXAGON:
                shape = "hexagon"
            else:
                shape = "rectangle"
        else:
            # 普通图层默认为矩形
            shape = "rectangle"

        if shape == "rectangle":
            handle_points = [
                QPoint(rect.left(), rect.top()),
                QPoint(rect.left() + rect.width() // 2, rect.top()),
                QPoint(rect.right(), rect.top()),
                QPoint(rect.right(), rect.top() + rect.height() // 2),
                QPoint(rect.right(), rect.bottom()),
                QPoint(rect.left() + rect.width() // 2, rect.bottom()),
                QPoint(rect.left(), rect.bottom()),
                QPoint(rect.left(), rect.top() + rect.height() // 2),
            ]
            index_map = list(range(8))
        elif shape == "circle":
            cx = rect.left() + rect.width() // 2
            cy = rect.top() + rect.height() // 2
            handle_points = [
                QPoint(cx, rect.top()),
                QPoint(rect.right(), cy),
                QPoint(cx, rect.bottom()),
                QPoint(rect.left(), cy),
            ]
            index_map = [1, 3, 5, 7]
        elif shape == "right_trapezoid":
            layer_width = rect.width()
            layer_height = rect.height()
            top_width = int(layer_width * 0.7)
            bottom_width = layer_width
            offset = int((bottom_width - top_width) * 0.3)
            handle_points = [
                QPoint(rect.left() + offset, rect.top()),
                QPoint(rect.left() + offset + top_width, rect.top()),
                QPoint(rect.right(), rect.bottom()),
                QPoint(rect.left(), rect.bottom()),
            ]
            index_map = [0, 2, 4, 6]
        elif shape == "pentagon" or shape == "hexagon":
            import math
            n = 5 if shape == "pentagon" else 6
            cx = rect.left() + rect.width() / 2
            cy = rect.top() + rect.height() / 2
            r = min(rect.width(), rect.height()) / 2 * 0.9
            pts = []
            for i in range(n):
                a = 2 * math.pi * i / n - (math.pi / 2 if shape == "pentagon" else 0)
                x = int(cx + r * math.cos(a))
                y = int(cy + r * math.sin(a))
                pts.append(QPoint(x, y))
            handle_points = pts
            index_map = [0, 2, 4, 6][:len(handle_points)]
        else:
            handle_points = []
            index_map = []

        for i, point in enumerate(handle_points):
            handle_rect = QRect(point.x() - half_handle, point.y() - half_handle, handle_size, handle_size)
            if handle_rect.contains(pos):
                if index_map:
                    return index_map[i]
                return i

        return -1  # 没有找到控制点

    def _get_shape_value(self, layer) -> str:
        shape_type = getattr(layer, "shape_type", None)
        if shape_type is None:
            return "rectangle"
        if hasattr(shape_type, "value"):
            return str(shape_type.value)
        return str(shape_type)

    def _is_corner_radius_draggable(self, layer) -> bool:
        if layer is None:
            return False
        if bool(getattr(layer, "vector_path_enabled", False)):
            return False
        shape = self._get_shape_value(layer)
        return shape in {"rectangle", "right_trapezoid", "pentagon", "hexagon"}

    def _get_corner_radius_value_and_limit(self, layer):
        shape = self._get_shape_value(layer)
        width = max(1, int(getattr(layer, "width", 1)))
        height = max(1, int(getattr(layer, "height", 1)))
        if shape == "rectangle":
            value = int(getattr(layer, "corner_radius", 0))
            max_value = max(0, min(width, height) // 2)
            return value, max_value, "rectangle"
        value = int(getattr(layer, "polygon_corner_radius", 0))
        max_value = max(0, min(width, height) // 4)
        return value, max_value, "polygon"

    def _set_corner_radius_value(self, layer, value: int):
        clamped = max(0, int(value))
        _, max_value, radius_kind = self._get_corner_radius_value_and_limit(layer)
        clamped = min(clamped, max_value)
        if radius_kind == "rectangle":
            layer.corner_radius = clamped
            if hasattr(layer, "vector_corner_radius_tl"):
                layer.vector_corner_radius_tl = clamped
            if hasattr(layer, "vector_corner_radius_tr"):
                layer.vector_corner_radius_tr = clamped
            if hasattr(layer, "vector_corner_radius_br"):
                layer.vector_corner_radius_br = clamped
            if hasattr(layer, "vector_corner_radius_bl"):
                layer.vector_corner_radius_bl = clamped
        else:
            if hasattr(layer, "polygon_corner_radius"):
                layer.polygon_corner_radius = clamped

    def _get_corner_radius_handle_point(self, layer, rect: QRect):
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return None
        if not self._is_corner_radius_draggable(layer):
            return None
        radius_value, _, _ = self._get_corner_radius_value_and_limit(layer)
        inset_px = int(radius_value * self.zoom_factor)
        base_y = rect.top() + 14
        handle_y = base_y + max(0, inset_px)
        max_y = rect.top() + max(16, rect.height() // 2)
        handle_y = min(handle_y, max_y)
        handle_x = rect.left() + rect.width() // 2
        return QPoint(handle_x, handle_y)

    def get_corner_radius_handle_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return False
        layer = self.document.layers[layer_index]
        if layer is None or is_layer_group(layer) or is_effectively_locked(layer, self.document.layers):
            return False
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return False
        handle_pt = self._get_corner_radius_handle_point(layer, rect)
        if handle_pt is None:
            return False
        size = 12
        half = size // 2
        return QRect(handle_pt.x() - half, handle_pt.y() - half, size, size).contains(pos)

    def _draw_corner_radius_handle(self, painter: QPainter, layer, rect: QRect):
        handle_pt = self._get_corner_radius_handle_point(layer, rect)
        if handle_pt is None:
            return
        anchor_x = rect.left() + rect.width() // 2
        anchor_y = rect.top() + 6
        painter.setPen(QPen(QColor(255, 196, 72), 1, Qt.SolidLine))
        painter.drawLine(anchor_x, anchor_y, handle_pt.x(), handle_pt.y())
        painter.setBrush(QBrush(QColor(255, 136, 0)))
        painter.drawEllipse(handle_pt.x() - 6, handle_pt.y() - 6, 12, 12)

    def get_cursor_for_handle(self, handle_index):
        """根据控制点索引返回相应的光标"""
        # 0: 左上, 1: 上中, 2: 右上, 3: 右中, 4: 右下, 5: 下中, 6: 左下, 7: 左中
        cursors = [
            Qt.SizeFDiagCursor,  # 左上
            Qt.SizeVerCursor,    # 上中
            Qt.SizeBDiagCursor,  # 右上
            Qt.SizeHorCursor,    # 右中
            Qt.SizeFDiagCursor,  # 右下
            Qt.SizeVerCursor,    # 下中
            Qt.SizeBDiagCursor,  # 左下
            Qt.SizeHorCursor,    # 左中
        ]

        if 0 <= handle_index < len(cursors):
            return cursors[handle_index]

        return Qt.ArrowCursor

    def _is_in_top_ruler(self, pos):
        if not self.show_rulers:
            return False
        ruler = self._get_ruler_thickness()
        canvas_rect = self.get_canvas_rect()
        return canvas_rect is not None and 0 <= pos.y() < ruler and pos.x() >= canvas_rect.x()

    def _is_in_left_ruler(self, pos):
        if not self.show_rulers:
            return False
        ruler = self._get_ruler_thickness()
        canvas_rect = self.get_canvas_rect()
        return canvas_rect is not None and 0 <= pos.x() < ruler and pos.y() >= canvas_rect.y()

    def _hit_test_guide(self, pos):
        """命中测试参考线，返回 (orientation, index) 或 (None, -1)"""
        if not self.show_guides:
            return None, -1
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return None, -1

        for i, gx in enumerate(self.vertical_guides):
            x = canvas_rect.x() + int(gx * self.zoom_factor)
            if abs(pos.x() - x) <= self._guide_hit_tolerance and canvas_rect.top() <= pos.y() <= canvas_rect.bottom():
                return "vertical", i

        for i, gy in enumerate(self.horizontal_guides):
            y = canvas_rect.y() + int(gy * self.zoom_factor)
            if abs(pos.y() - y) <= self._guide_hit_tolerance and canvas_rect.left() <= pos.x() <= canvas_rect.right():
                return "horizontal", i
        return None, -1

    def _clear_guide_selection(self):
        self._selected_guide_orientation = None
        self._selected_guide_index = -1

    def _set_selected_guide(self, orientation, index):
        self._selected_guide_orientation = orientation
        self._selected_guide_index = index

    def _should_delete_dragging_guide(self, pos):
        """是否应删除当前拖拽参考线（拖回标尺或拖出工作区）"""
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return False
        ruler = self._get_ruler_thickness()
        if self._dragging_guide_orientation == "vertical":
            # Photoshop语义：垂直参考线拖回左侧标尺删除
            if self.show_rulers and pos.x() <= ruler:
                return True
            return pos.x() < canvas_rect.x() - 30 or pos.x() > canvas_rect.right() + 30
        if self._dragging_guide_orientation == "horizontal":
            # Photoshop语义：水平参考线拖回顶部标尺删除
            if self.show_rulers and pos.y() <= ruler:
                return True
            return pos.y() < canvas_rect.y() - 30 or pos.y() > canvas_rect.bottom() + 30
        return False

    def _start_drag_new_guide(self, orientation, pos):
        """从标尺开始拖拽新参考线"""
        self._is_dragging_guide = True
        self._pending_new_guide = True
        self._dragging_guide_orientation = orientation
        self._clear_guide_selection()
        if orientation == "vertical":
            self.vertical_guides.append(0)
            self._dragging_guide_index = len(self.vertical_guides) - 1
        else:
            self.horizontal_guides.append(0)
            self._dragging_guide_index = len(self.horizontal_guides) - 1
        self._update_dragging_guide_from_pos(pos, Qt.NoModifier)
        self.setCursor(Qt.SplitHCursor if orientation == "vertical" else Qt.SplitVCursor)

    def _update_dragging_guide_from_pos(self, pos, modifiers=Qt.NoModifier):
        if not self._is_dragging_guide or self._dragging_guide_index < 0:
            return
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return

        if self._dragging_guide_orientation == "vertical":
            gx = int((pos.x() - canvas_rect.x()) / self.zoom_factor)
            if modifiers & Qt.ShiftModifier:
                gx = int(round(gx / 10.0) * 10)
            if 0 <= self._dragging_guide_index < len(self.vertical_guides):
                self.vertical_guides[self._dragging_guide_index] = gx
            self._guide_overlay_text = f"X: {gx}px"
        elif self._dragging_guide_orientation == "horizontal":
            gy = int((pos.y() - canvas_rect.y()) / self.zoom_factor)
            if modifiers & Qt.ShiftModifier:
                gy = int(round(gy / 10.0) * 10)
            if 0 <= self._dragging_guide_index < len(self.horizontal_guides):
                self.horizontal_guides[self._dragging_guide_index] = gy
            self._guide_overlay_text = f"Y: {gy}px"
        self._guide_overlay_pos = QPoint(pos.x(), pos.y())

    def _apply_guide_snap_for_layer(self, layer, new_x, new_y):
        """对图层位置应用参考线吸附（边缘/中心）"""
        self._snap_feedback_active = False
        self._snap_feedback_vertical = None
        self._snap_feedback_horizontal = None
        self._snap_feedback_text = ""
        if not self.snap_to_guides or not self.show_guides:
            return new_x, new_y
        if self.zoom_factor <= 0:
            return new_x, new_y

        tolerance_doc = self._snap_tolerance_px / self.zoom_factor
        width = int(getattr(layer, "width", 0))
        height = int(getattr(layer, "height", 0))

        # 垂直参考线吸附：左边/中心/右边
        x_points = [
            ("left", float(new_x)),
            ("center", float(new_x) + width / 2.0),
            ("right", float(new_x) + width),
        ]
        best_dx = None
        best_snap_x = None
        for gx in self.vertical_guides:
            gx_f = float(gx)
            for _, px in x_points:
                d = gx_f - px
                if abs(d) <= tolerance_doc and (best_dx is None or abs(d) < abs(best_dx)):
                    best_dx = d
                    best_snap_x = gx
        if best_dx is not None:
            new_x = int(round(float(new_x) + best_dx))

        # 水平参考线吸附：上边/中心/下边
        y_points = [
            ("top", float(new_y)),
            ("center", float(new_y) + height / 2.0),
            ("bottom", float(new_y) + height),
        ]
        best_dy = None
        best_snap_y = None
        for gy in self.horizontal_guides:
            gy_f = float(gy)
            for _, py in y_points:
                d = gy_f - py
                if abs(d) <= tolerance_doc and (best_dy is None or abs(d) < abs(best_dy)):
                    best_dy = d
                    best_snap_y = gy
        if best_dy is not None:
            new_y = int(round(float(new_y) + best_dy))

        if best_dx is not None or best_dy is not None:
            self._snap_feedback_active = True
            self._snap_feedback_vertical = best_snap_x
            self._snap_feedback_horizontal = best_snap_y
            label_parts = ["SNAP"]
            if best_snap_x is not None:
                label_parts.append(f"X:{int(best_snap_x)}")
            if best_snap_y is not None:
                label_parts.append(f"Y:{int(best_snap_y)}")
            self._snap_feedback_text = " ".join(label_parts)
            canvas_rect = self.get_canvas_rect()
            if canvas_rect:
                self._snap_feedback_pos = QPoint(
                    canvas_rect.x() + int((new_x + width / 2.0) * self.zoom_factor),
                    canvas_rect.y() + int((new_y + height / 2.0) * self.zoom_factor),
                )

        return new_x, new_y
