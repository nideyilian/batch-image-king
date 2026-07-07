# -*- coding: utf-8 -*-
"""Canvas widget components."""

from collections import OrderedDict
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QMenu
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPixmap, QCursor, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, QTimer, QRunnable, QThreadPool
from app.ui.dark_theme import CursorDarkTheme
from app.utils.layer_tree import (    child_indices_for_group,    expand_group_indices,    group_bounds,    is_layer_group,    is_effectively_locked,    is_effectively_visible,)
import time
import threading

class CanvasWidgetCanvasDraw(object):
    def _draw_guides(self, painter, canvas_rect):
        """绘制参考线"""
        if not self.show_guides:
            return

        for i, gx in enumerate(self.vertical_guides):
            is_active = (
                (self._is_dragging_guide and self._dragging_guide_orientation == "vertical" and self._dragging_guide_index == i) or
                (not self._is_dragging_guide and self._selected_guide_orientation == "vertical" and self._selected_guide_index == i)
            )
            painter.setPen(QPen(QColor(255, 160, 60, 230) if is_active else QColor(0, 170, 255, 220), 1, Qt.SolidLine if is_active else Qt.DashLine))
            x = canvas_rect.x() + int(gx * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())

        for i, gy in enumerate(self.horizontal_guides):
            is_active = (
                (self._is_dragging_guide and self._dragging_guide_orientation == "horizontal" and self._dragging_guide_index == i) or
                (not self._is_dragging_guide and self._selected_guide_orientation == "horizontal" and self._selected_guide_index == i)
            )
            painter.setPen(QPen(QColor(255, 160, 60, 230) if is_active else QColor(0, 170, 255, 220), 1, Qt.SolidLine if is_active else Qt.DashLine))
            y = canvas_rect.y() + int(gy * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        if self._is_dragging_guide and self._guide_overlay_text:
            self._draw_guide_overlay(painter, self._guide_overlay_text, self._guide_overlay_pos)
        if self._snap_feedback_active:
            self._draw_snap_feedback(painter, canvas_rect)

    def _draw_guide_overlay(self, painter, text, pos):
        """拖拽参考线时显示当前位置参数"""
        metrics = painter.fontMetrics()
        w = metrics.horizontalAdvance(text) + 12
        h = metrics.height() + 8
        x = min(max(0, pos.x() + 12), max(0, self.width() - w))
        y = min(max(0, pos.y() + 12), max(0, self.height() - h))
        rect = QRect(x, y, w, h)
        painter.fillRect(rect, QColor(32, 32, 32, 220))
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawRect(rect)
        painter.drawText(rect.adjusted(6, 4, -6, -4), Qt.AlignLeft | Qt.AlignVCenter, text)

    def _draw_snap_feedback(self, painter, canvas_rect):
        """绘制吸附成功反馈：高亮参考线 + SNAP 文本"""
        highlight_pen = QPen(QColor(255, 180, 40, 255), 2, Qt.SolidLine)
        painter.setPen(highlight_pen)
        if self._snap_feedback_vertical is not None:
            x = canvas_rect.x() + int(self._snap_feedback_vertical * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())
        if self._snap_feedback_horizontal is not None:
            y = canvas_rect.y() + int(self._snap_feedback_horizontal * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        if self._snap_feedback_text:
            self._draw_guide_overlay(painter, self._snap_feedback_text, self._snap_feedback_pos)

    def _draw_rulers(self, painter):
        """绘制标尺"""
        if not self.show_rulers:
            return

        ruler = self._get_ruler_thickness()
        rect = self.rect()
        canvas_rect = self.get_canvas_rect()

        painter.fillRect(0, 0, rect.width(), ruler, QColor(CursorDarkTheme.BACKGROUND_TITLEBAR))
        painter.fillRect(0, 0, ruler, rect.height(), QColor(CursorDarkTheme.BACKGROUND_TITLEBAR))
        painter.fillRect(0, 0, ruler, ruler, QColor(CursorDarkTheme.BACKGROUND_SECONDARY))
        painter.setPen(QPen(QColor(CursorDarkTheme.BORDER_PRIMARY), 1))
        painter.drawLine(ruler, 0, rect.width(), 0)
        painter.drawLine(0, ruler, 0, rect.height())

        if not canvas_rect:
            return

        # 动态刻度步进：尽量保证大刻度约 80~120 像素
        base_steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
        unit_per_big = 100
        for s in base_steps:
            if s * self.zoom_factor >= 80:
                unit_per_big = s
                break
        unit_per_minor = max(1, unit_per_big // 10)

        # 顶部水平标尺
        painter.setPen(QPen(QColor(CursorDarkTheme.TEXT_MUTED), 1))
        start_x = -canvas_rect.x() / self.zoom_factor
        end_x = (self.width() - canvas_rect.x()) / self.zoom_factor
        minor_start = int(start_x // unit_per_minor) * unit_per_minor
        x_val = minor_start
        while x_val <= end_x:
            x = canvas_rect.x() + int(x_val * self.zoom_factor)
            if x_val % unit_per_big == 0:
                painter.drawLine(x, ruler - 12, x, ruler)
                painter.drawText(x + 2, 11, f"{int(x_val)}")
            elif x_val % (unit_per_big // 2 if unit_per_big >= 2 else 1) == 0:
                painter.drawLine(x, ruler - 8, x, ruler)
            else:
                painter.drawLine(x, ruler - 5, x, ruler)
            x_val += unit_per_minor

        # 左侧垂直标尺
        start_y = -canvas_rect.y() / self.zoom_factor
        end_y = (self.height() - canvas_rect.y()) / self.zoom_factor
        minor_start = int(start_y // unit_per_minor) * unit_per_minor
        y_val = minor_start
        while y_val <= end_y:
            y = canvas_rect.y() + int(y_val * self.zoom_factor)
            if y_val % unit_per_big == 0:
                painter.drawLine(ruler - 12, y, ruler, y)
                painter.drawText(2, y - 2, f"{int(y_val)}")
            elif y_val % (unit_per_big // 2 if unit_per_big >= 2 else 1) == 0:
                painter.drawLine(ruler - 8, y, ruler, y)
            else:
                painter.drawLine(ruler - 5, y, ruler, y)
            y_val += unit_per_minor

    def _draw_drag_enhancements(self, painter):
        """绘制拖拽交互增强效果"""
        if not self.is_dragging_layer or self.dragging_layer_index < 0:
            return

        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return

        layer = self.document.layers[self.dragging_layer_index]

        # 1. 绘制拖拽边界提示
        if self.show_drag_bounds:
            self._draw_drag_bounds(painter, canvas_rect, layer)

        # 2. 绘制拖拽预览（幽灵图层）
        if self.drag_preview_enabled:
            self._draw_drag_preview(painter, canvas_rect, layer)

    def _draw_drag_bounds(self, painter, canvas_rect, layer):
        """绘制拖拽边界提示"""
        # 计算图层在画布中的边界
        layer_right = layer.x + layer.width
        layer_bottom = layer.y + layer.height

        # 保存当前画笔
        original_pen = painter.pen()

        # 设置边界提示样式
        bound_pen = QPen(QColor(255, 100, 100, 150), 2, Qt.DashLine)
        painter.setPen(bound_pen)

        # 绘制边界警告线
        margin = 10  # 边界警告距离

        # 左边界警告
        if layer.x < margin:
            x = canvas_rect.x() + int(margin * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())

        # 右边界警告
        if layer_right > self.document.canvas_width - margin:
            x = canvas_rect.right() - int(margin * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())

        # 上边界警告
        if layer.y < margin:
            y = canvas_rect.y() + int(margin * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        # 下边界警告
        if layer_bottom > self.document.canvas_height - margin:
            y = canvas_rect.bottom() - int(margin * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        # 恢复原始画笔
        painter.setPen(original_pen)

    def _draw_drag_preview(self, painter, canvas_rect, layer):
        """绘制拖拽预览（幽灵图层）"""
        # 计算图层当前位置
        layer_x = canvas_rect.x() + int(layer.x * self.zoom_factor)
        layer_y = canvas_rect.y() + int(layer.y * self.zoom_factor)
        layer_width = int(layer.width * self.zoom_factor)
        layer_height = int(layer.height * self.zoom_factor)

        # 保存当前状态
        original_pen = painter.pen()
        original_brush = painter.brush()

        # 设置预览样式
        preview_color = QColor(0, 160, 230, int(255 * self.drag_preview_opacity))
        painter.setPen(QPen(preview_color, 2, Qt.SolidLine))
        painter.setBrush(QBrush(QColor(0, 160, 230, int(100 * self.drag_preview_opacity))))

        # 获取图层形状类型
        if hasattr(layer, 'shape_type'):
            # 异形图层使用shape_type属性
            try:
                from app.models.layer_properties import ShapeType
            except ImportError:
                from app.models.shaped_layer import ShapeType
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
            painter.drawRect(layer_x, layer_y, layer_width, layer_height)
        elif shape == "circle":
            r = int(min(layer_width, layer_height) / 2)
            cx = layer_x + layer_width // 2
            cy = layer_y + layer_height // 2
            painter.drawEllipse(QRect(cx - r, cy - r, r * 2, r * 2))
        elif shape == "right_trapezoid":
            # 使用图层实际的梯形参数
            top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
            bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
            slope_side = getattr(layer, 'trapezoid_slope_side', 'right')

            top_width = int(layer_width * top_width_percent)
            bottom_width = int(layer_width * bottom_width_percent)

            if slope_side == "right":
                # 斜边在右侧
                points = [
                    QPoint(int(layer_x), int(layer_y)),  # 左上
                    QPoint(int(layer_x + top_width), int(layer_y)),  # 右上
                    QPoint(int(layer_x + bottom_width), int(layer_y + layer_height)),  # 右下
                    QPoint(int(layer_x), int(layer_y + layer_height))  # 左下
                ]
            else:
                # 斜边在左侧
                points = [
                    QPoint(int(layer_x + layer_width - top_width), int(layer_y)),  # 左上
                    QPoint(int(layer_x + layer_width), int(layer_y)),  # 右上
                    QPoint(int(layer_x + layer_width), int(layer_y + layer_height)),  # 右下
                    QPoint(int(layer_x + layer_width - bottom_width), int(layer_y + layer_height))  # 左下
                ]
            painter.drawPolygon(points)
        elif shape == "pentagon" or shape == "hexagon":
            import math
            n = 5 if shape == "pentagon" else 6
            cx = layer_x + layer_width / 2
            cy = layer_y + layer_height / 2
            r = min(layer_width, layer_height) / 2 * 0.9
            pts = []
            for i in range(n):
                a = 2 * math.pi * i / n - (math.pi / 2 if shape == "pentagon" else 0)
                x = int(cx + r * math.cos(a))
                y = int(cy + r * math.sin(a))
                pts.append(QPoint(x, y))
            painter.drawPolygon(pts)

        # 绘制拖拽方向指示器
        self._draw_drag_direction_indicator(painter, layer_x, layer_y, layer_width, layer_height)

        # 恢复原始状态
        painter.setPen(original_pen)
        painter.setBrush(original_brush)

    def _draw_drag_direction_indicator(self, painter, x, y, width, height):
        """绘制拖拽方向指示器"""
        if not hasattr(self, 'layer_drag_start') or not self.layer_drag_start:
            return

        # 计算拖拽方向
        if hasattr(self, '_last_mouse_pos'):
            current_pos = self._last_mouse_pos
        else:
            return

        drag_start = self.layer_drag_start
        delta_x = current_pos.x() - drag_start.x()
        delta_y = current_pos.y() - drag_start.y()

        # 如果移动距离太小，不显示方向指示器
        if abs(delta_x) < 5 and abs(delta_y) < 5:
            return

        # 计算图层中心点
        center_x = x + width // 2
        center_y = y + height // 2

        # 绘制方向箭头
        arrow_length = 30
        arrow_color = QColor(255, 255, 0, 200)
        painter.setPen(QPen(arrow_color, 3, Qt.SolidLine))

        # 计算箭头方向
        import math
        angle = math.atan2(delta_y, delta_x)
        end_x = center_x + int(arrow_length * math.cos(angle))
        end_y = center_y + int(arrow_length * math.sin(angle))

        # 绘制箭头主线
        painter.drawLine(center_x, center_y, end_x, end_y)

        # 绘制箭头头部
        arrow_head_length = 10
        arrow_head_angle = math.pi / 6  # 30度

        # 左侧箭头线
        left_x = end_x - int(arrow_head_length * math.cos(angle - arrow_head_angle))
        left_y = end_y - int(arrow_head_length * math.sin(angle - arrow_head_angle))
        painter.drawLine(end_x, end_y, left_x, left_y)

        # 右侧箭头线
        right_x = end_x - int(arrow_head_length * math.cos(angle + arrow_head_angle))
        right_y = end_y - int(arrow_head_length * math.sin(angle + arrow_head_angle))
        painter.drawLine(end_x, end_y, right_x, right_y)

    def _clear_drag_state(self):
        """清理所有拖拽相关状态"""
        self.drag_ghost_layer = None
        self._last_mouse_pos = None
        self.potential_drag = False
        self.drag_start_pos = None
        self.dragging_group_start_bounds = None
        self._interactive_low_quality_active = False

        # 恢复正常光标
        if not self.temp_hand_mode:
            self.setCursor(Qt.ArrowCursor)
