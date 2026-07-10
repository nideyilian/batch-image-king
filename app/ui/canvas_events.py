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

class CanvasWidgetCanvasEvents(object):
    def mousePressEvent(self, event):
        """鼠标按下事件处理"""
        if event.button() == Qt.LeftButton:
            # 参考线优先：命中已有参考线后可拖拽
            orientation, guide_index = self._hit_test_guide(event.pos())
            if orientation:
                self._is_dragging_guide = True
                self._pending_new_guide = False
                self._dragging_guide_orientation = orientation
                self._dragging_guide_index = guide_index
                self._set_selected_guide(orientation, guide_index)
                self._guide_overlay_text = ""
                self.setCursor(Qt.SplitHCursor if orientation == "vertical" else Qt.SplitVCursor)
                event.accept()
                return

            # 从标尺拖拽创建参考线
            if self._is_in_top_ruler(event.pos()):
                self._start_drag_new_guide("horizontal", event.pos())
                event.accept()
                return
            if self._is_in_left_ruler(event.pos()):
                self._start_drag_new_guide("vertical", event.pos())
                event.accept()
                return

            # 点击非参考线区域时取消参考线选中
            self._clear_guide_selection()

            # 如果Space键按下，优先启用画布拖拽模式
            if self.temp_hand_mode:
                self.drag_start = event.pos()
                self.is_dragging = True
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return

            # 尝试获取点击位置的调整控制点
            if self.document.selected_layer_index >= 0:
                handle_node_index, handle_type = self.get_vector_handle_at_position(event.pos(), self.document.selected_layer_index)
                if handle_node_index >= 0:
                    self.is_dragging_vector_handle = True
                    self.vector_handle_node_index = handle_node_index
                    self.vector_handle_type = handle_type
                    self.selected_vector_node_index = handle_node_index
                    self.resize_start_point = event.pos()
                    event.accept()
                    return

                node_index = self.get_vector_node_at_position(event.pos(), self.document.selected_layer_index)
                if node_index >= 0:
                    self.is_dragging_vector_node = True
                    self.vector_node_index = node_index
                    self.selected_vector_node_index = node_index
                    self.resize_start_point = event.pos()
                    event.accept()
                    return

                if self.get_corner_radius_handle_at_position(event.pos(), self.document.selected_layer_index):
                    layer = self.document.layers[self.document.selected_layer_index]
                    if not layer.locked:
                        radius_value, _, _ = self._get_corner_radius_value_and_limit(layer)
                        self.is_dragging_corner_radius = True
                        self.corner_radius_start_point = event.pos()
                        self.corner_radius_start_value = int(radius_value)
                        event.accept()
                        return

                handle_index = self.get_handle_at_position(event.pos(), self.document.selected_layer_index)

                if handle_index >= 0:
                    # 记录开始调整大小的状态
                    self.is_resizing = True
                    self.resize_handle_index = handle_index
                    self.resize_start_point = event.pos()

                    # 记录图层的原始矩形
                    layer = self.document.layers[self.document.selected_layer_index]
                    if bool(getattr(layer, 'auto_fit_text_box', False)):
                        layer.auto_fit_text_box = False
                    if is_layer_group(layer):
                        bounds = group_bounds(self.document.layers, layer, include_hidden=False)
                        if not bounds:
                            event.accept()
                            return
                        left, top, right, bottom = bounds
                        self.resize_start_rect = QRect(left, top, max(1, right - left), max(1, bottom - top))
                        self.resize_start_group_child_rects = {
                            idx: QRect(
                                int(getattr(self.document.layers[idx], 'x', 0)),
                                int(getattr(self.document.layers[idx], 'y', 0)),
                                int(getattr(self.document.layers[idx], 'width', 0)),
                                int(getattr(self.document.layers[idx], 'height', 0)),
                            )
                            for idx in child_indices_for_group(self.document.layers, getattr(layer, 'group_id', ''), include_hidden=False)
                        }
                    else:
                        self.resize_start_rect = QRect(layer.x, layer.y, layer.width, layer.height)
                        self.resize_start_group_child_rects = {}

                    event.accept()
                    return

            # 检查点击的位置是否在图层上
            layer_index = self.get_layer_at_position(event.pos())

            if layer_index >= 0:
                # 立即选中图层（点击选中）
                if not event.modifiers() & Qt.AltModifier:
                    selected_indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
                    if layer_index not in selected_indices:
                        if hasattr(self.document, 'select_layers'):
                            self.document.select_layers([layer_index], primary_index=layer_index)
                        else:
                            self.document.select_layer(layer_index)
                    elif layer_index != self.document.selected_layer_index and hasattr(self.document, 'select_layers'):
                        # 点击已选图层时保留多选，只把点击项设为主选/拖拽基准
                        reordered = [layer_index] + [idx for idx in selected_indices if idx != layer_index]
                        self.document.select_layers(reordered, primary_index=layer_index)

                # 记录鼠标按下状态，为可能的拖拽做准备（按住拖拽）
                self.potential_drag = True
                self.dragging_layer_index = layer_index
                self.drag_start_pos = event.pos()
                self.layer_drag_start = event.pos()
                active_selection = list(getattr(self.document, 'selected_layer_indices', []) or [layer_index])
                if layer_index not in active_selection:
                    active_selection = [layer_index]
                expanded_selection = expand_group_indices(self.document.layers, active_selection, include_groups=False)
                self.dragging_layer_indices = [
                    idx for idx in expanded_selection
                    if (
                        0 <= idx < len(self.document.layers)
                        and not is_layer_group(self.document.layers[idx])
                        and not is_effectively_locked(self.document.layers[idx], self.document.layers)
                    )
                ]
                self.dragging_layer_start_positions = {
                    idx: (int(self.document.layers[idx].x), int(self.document.layers[idx].y))
                    for idx in self.dragging_layer_indices
                }
                if is_layer_group(self.document.layers[layer_index]):
                    bounds = group_bounds(self.document.layers, self.document.layers[layer_index], include_hidden=False)
                    self.dragging_group_start_bounds = bounds
                else:
                    self.dragging_group_start_bounds = None

                # 获取画布矩形
                canvas_rect = self.get_canvas_rect()
                if canvas_rect:
                    # 记录鼠标位置与图层左上角的偏移，以便拖动时保持这个偏移
                    layer = self.document.layers[layer_index]
                    layer_rect = self.get_layer_rect(layer_index)
                    if layer_rect:
                        layer_x = layer_rect.x()
                        layer_y = layer_rect.y()
                    else:
                        layer_x = canvas_rect.x() + int(layer.x * self.zoom_factor)
                        layer_y = canvas_rect.y() + int(layer.y * self.zoom_factor)

                    self.drag_offset_x = event.pos().x() - layer_x
                    self.drag_offset_y = event.pos().y() - layer_y

                event.accept()
                return

            # 如果点击不在图层上，取消选中，并准备画布拖拽
            if self.document.selected_layer_index >= 0:
                self.document.select_layer(-1)
                self.selected_vector_node_index = -1

            # 启动画布拖动模式
            self.drag_start = event.pos()
            self.is_dragging = True
            self.setCursor(Qt.ClosedHandCursor)

        event.accept()

    def mouseDoubleClickEvent(self, event):
        """双击文字图层时打开文案编辑器。"""
        if event.button() == Qt.LeftButton:
            layer_index = self.get_layer_at_position(event.pos())
            if layer_index >= 0:
                layer = self.document.layers[layer_index]
                try:
                    from app.models.text_layer import TextLayer
                    if isinstance(layer, TextLayer):
                        main_window = self._get_main_window()
                        if main_window and hasattr(main_window, 'edit_text_layer'):
                            main_window.edit_text_layer(layer_index)
                            event.accept()
                            return
                except Exception as e:
                    print(f"双击编辑文字图层时出错: {e}")

        QWidget.mouseDoubleClickEvent(self, event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件处理"""
        # 跟踪鼠标位置用于拖拽方向指示器
        self._last_mouse_pos = event.pos()

        if self._is_dragging_guide:
            self._update_dragging_guide_from_pos(event.pos(), event.modifiers())
            # 参考线是视图辅助元素，不触发文档变更，仅刷新当前画布
            self.update()
            event.accept()
            return

        # 发送鼠标位置变化信号
        canvas_rect = self.get_canvas_rect()
        if canvas_rect and canvas_rect.contains(event.pos()):
            # 计算相对于画布的坐标
            relative_x = int((event.pos().x() - canvas_rect.x()) / self.zoom_factor)
            relative_y = int((event.pos().y() - canvas_rect.y()) / self.zoom_factor)
            self.position_changed.emit(relative_x, relative_y)

        if self.is_resizing and self.document.selected_layer_index >= 0:
            # 处理图层调整大小
            layer = self.document.layers[self.document.selected_layer_index]

            # 如果图层被锁定，取消调整大小
            if layer.locked:
                self.is_resizing = False
                self.resize_handle_index = -1
                self.resize_start_rect = None
                self.resize_start_point = None
                return

            # 计算鼠标移动的距离
            dx = event.pos().x() - self.resize_start_point.x()
            dy = event.pos().y() - self.resize_start_point.y()

            # 转换为图层坐标系中的距离
            dx = int(dx / self.zoom_factor)
            dy = int(dy / self.zoom_factor)

            # 根据控制点索引调整图层的位置和尺寸
            new_x = self.resize_start_rect.x()
            new_y = self.resize_start_rect.y()
            new_width = self.resize_start_rect.width()
            new_height = self.resize_start_rect.height()

            # 0: 左上, 1: 上中, 2: 右上, 3: 右中, 4: 右下, 5: 下中, 6: 左下, 7: 左中
            if self.resize_handle_index in [0, 6, 7]:  # 左侧控制点
                new_x += dx
                new_width -= dx
            if self.resize_handle_index in [2, 3, 4]:  # 右侧控制点
                new_width += dx
            if self.resize_handle_index in [0, 1, 2]:  # 上侧控制点
                new_y += dy
                new_height -= dy
            if self.resize_handle_index in [4, 5, 6]:  # 下侧控制点
                new_height += dy

            # 确保图层尺寸不会太小
            min_size = 10
            if new_width < min_size:
                # 如果从左侧调整，需要相应调整x坐标
                if self.resize_handle_index in [0, 6, 7]:
                    new_x = self.resize_start_rect.right() - min_size
                new_width = min_size

            if new_height < min_size:
                # 如果从上侧调整，需要相应调整y坐标
                if self.resize_handle_index in [0, 1, 2]:
                    new_y = self.resize_start_rect.bottom() - min_size
                new_height = min_size

            if is_layer_group(layer):
                # Scale all visible child layers relative to the group's start bounds.
                start_rect = self.resize_start_rect
                child_rects = getattr(self, 'resize_start_group_child_rects', {}) or {}
                scale_x = new_width / max(1, start_rect.width())
                scale_y = new_height / max(1, start_rect.height())
                for idx, child_rect in child_rects.items():
                    if not (0 <= idx < len(self.document.layers)):
                        continue
                    child = self.document.layers[idx]
                    if is_effectively_locked(child, self.document.layers):
                        continue
                    child.x = int(round(new_x + (child_rect.x() - start_rect.x()) * scale_x))
                    child.y = int(round(new_y + (child_rect.y() - start_rect.y()) * scale_y))
                    child.width = max(1, int(round(child_rect.width() * scale_x)))
                    child.height = max(1, int(round(child_rect.height() * scale_y)))
            else:
                # 更新图层属性
                layer.x = new_x
                layer.y = new_y
                layer.width = new_width
                layer.height = new_height

            # 交互过程采用节流刷新，避免每个鼠标事件都触发完整重绘
            self._schedule_interactive_update(require_recompose=True)

            event.accept()
            return

        if self.is_dragging_corner_radius and self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if layer.locked:
                self.is_dragging_corner_radius = False
                self.corner_radius_start_point = None
                return
            if self.corner_radius_start_point is not None:
                dy = event.pos().y() - self.corner_radius_start_point.y()
                delta = int(round(dy / max(0.001, self.zoom_factor)))
                new_radius = self.corner_radius_start_value + delta
                self._set_corner_radius_value(layer, new_radius)
                self._schedule_interactive_update(require_recompose=True)
                event.accept()
                return

        if self.is_dragging_vector_handle and self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if layer.locked:
                self.is_dragging_vector_handle = False
                self.vector_handle_node_index = -1
                self.vector_handle_type = None
                return
            if hasattr(layer, 'update_vector_bezier_handle'):
                rect = self.get_layer_rect(self.document.selected_layer_index)
                if rect:
                    ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
                    local_x = (event.pos().x() - ox) / self.zoom_factor
                    local_y = (event.pos().y() - oy) / self.zoom_factor
                    layer.update_vector_bezier_handle(self.vector_handle_node_index, self.vector_handle_type, local_x, local_y)
                    self._schedule_interactive_update(require_recompose=True)
                    event.accept()
                    return

        if self.is_dragging_vector_node and self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if layer.locked:
                self.is_dragging_vector_node = False
                self.vector_node_index = -1
                return
            if hasattr(layer, 'update_vector_bezier_anchor'):
                rect = self.get_layer_rect(self.document.selected_layer_index)
                if rect:
                    ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
                    local_x = (event.pos().x() - ox) / self.zoom_factor
                    local_y = (event.pos().y() - oy) / self.zoom_factor
                    layer.update_vector_bezier_anchor(self.vector_node_index, local_x, local_y)
                    self._schedule_interactive_update(require_recompose=True)
                    event.accept()
                    return

        elif self.potential_drag and not self.is_dragging_layer:
            # 检查是否超过拖拽阈值且鼠标仍在按下状态
            if self.drag_start_pos:
                distance = (event.pos() - self.drag_start_pos).manhattanLength()
                if distance > self.drag_threshold:
                    # 只有在潜在拖拽状态下才开始实际拖拽
                    layer = self.document.layers[self.dragging_layer_index]
                    drag_indices = getattr(self, 'dragging_layer_indices', [self.dragging_layer_index])
                    if drag_indices and not is_effectively_locked(layer, self.document.layers):  # 确保图层未锁定
                        self.potential_drag = False
                        self.is_dragging_layer = True
                        self.document.save_state("批量移动图层前" if len(drag_indices) > 1 else "移动图层前")
                        self.setCursor(Qt.ClosedHandCursor)
                    else:
                        # 图层锁定，取消拖拽
                        self.potential_drag = False
                        self.drag_start_pos = None

        elif self.is_dragging_layer and self.dragging_layer_index >= 0:
            # 处理图层拖动
            layer = self.document.layers[self.dragging_layer_index]

            # 如果图层被锁定，取消拖动
            if is_effectively_locked(layer, self.document.layers):
                self.is_dragging_layer = False
                self.dragging_layer_index = -1
                self.layer_drag_start = None
                self._interactive_low_quality_active = False
                return

            # 计算新位置
            canvas_rect = self.get_canvas_rect()
            if canvas_rect:
                # 考虑拖动偏移
                new_x = int((event.pos().x() - canvas_rect.x() - self.drag_offset_x) / self.zoom_factor)
                new_y = int((event.pos().y() - canvas_rect.y() - self.drag_offset_y) / self.zoom_factor)
                if not is_layer_group(layer):
                    new_x, new_y = self._apply_guide_snap_for_layer(layer, new_x, new_y)
                start_positions = getattr(self, 'dragging_layer_start_positions', {})
                if is_layer_group(layer):
                    bounds = getattr(self, 'dragging_group_start_bounds', None) or group_bounds(self.document.layers, layer, include_hidden=False)
                    base_start_x, base_start_y = (bounds[0], bounds[1]) if bounds else (new_x, new_y)
                else:
                    base_start_x, base_start_y = start_positions.get(
                        self.dragging_layer_index,
                        (int(layer.x), int(layer.y)),
                    )
                delta_x = new_x - base_start_x
                delta_y = new_y - base_start_y

                # 更新图层位置。多选时保持各图层相对位置。
                drag_indices = getattr(self, 'dragging_layer_indices', [self.dragging_layer_index])
                for idx in drag_indices:
                    if not (0 <= idx < len(self.document.layers)):
                        continue
                    target_layer = self.document.layers[idx]
                    if is_effectively_locked(target_layer, self.document.layers):
                        continue
                    start_x, start_y = start_positions.get(idx, (int(target_layer.x), int(target_layer.y)))
                    target_layer.x = start_x + delta_x
                    target_layer.y = start_y + delta_y

                # 交互过程采用节流刷新，避免每个鼠标事件都触发完整重绘
                self._schedule_interactive_update(require_recompose=True)

            event.accept()
            return

        elif self.is_dragging:
            # 处理画布拖动
            if self.drag_start:
                self.offset += event.pos() - self.drag_start
                self.drag_start = event.pos()
                self._schedule_interactive_update(require_recompose=False)

            event.accept()
            return

        # 根据鼠标位置更新光标
        # 检查是否在控制点上
        if self.document.selected_layer_index >= 0:
            if self._should_skip_hover_hit_test(event.pos()):
                event.accept()
                return
            handle_node_index, _ = self.get_vector_handle_at_position(event.pos(), self.document.selected_layer_index)
            if handle_node_index >= 0:
                self.setCursor(Qt.PointingHandCursor)
                event.accept()
                return
            node_index = self.get_vector_node_at_position(event.pos(), self.document.selected_layer_index)
            if node_index >= 0:
                self.setCursor(Qt.CrossCursor)
                event.accept()
                return
            if self.get_corner_radius_handle_at_position(event.pos(), self.document.selected_layer_index):
                self.setCursor(Qt.SizeVerCursor)
                event.accept()
                return
            handle_index = self.get_handle_at_position(event.pos(), self.document.selected_layer_index)

            if handle_index >= 0:
                self.setCursor(self.get_cursor_for_handle(handle_index))
                event.accept()
                return

        # 检查是否在图层上
        if self.document.selected_layer_index < 0 and self._should_skip_hover_hit_test(event.pos()):
            event.accept()
            return
        layer_index = self.get_layer_at_position(event.pos())

        if layer_index >= 0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            orientation, _ = self._hit_test_guide(event.pos())
            if orientation == "vertical":
                self.setCursor(Qt.SplitHCursor)
            elif orientation == "horizontal":
                self.setCursor(Qt.SplitVCursor)
            elif self._is_in_top_ruler(event.pos()) or self._is_in_left_ruler(event.pos()):
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

        event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件处理"""
        if event.button() == Qt.LeftButton:
            if self._is_dragging_guide:
                if self._should_delete_dragging_guide(event.pos()):
                    if self._dragging_guide_orientation == "vertical" and 0 <= self._dragging_guide_index < len(self.vertical_guides):
                        self.vertical_guides.pop(self._dragging_guide_index)
                    if self._dragging_guide_orientation == "horizontal" and 0 <= self._dragging_guide_index < len(self.horizontal_guides):
                        self.horizontal_guides.pop(self._dragging_guide_index)
                    self._clear_guide_selection()
                else:
                    self._set_selected_guide(self._dragging_guide_orientation, self._dragging_guide_index)

                self._is_dragging_guide = False
                self._pending_new_guide = False
                self._dragging_guide_orientation = None
                self._dragging_guide_index = -1
                self._guide_overlay_text = ""
                self._persist_view_settings_to_document()
                if not self.temp_hand_mode:
                    self.setCursor(Qt.ArrowCursor)
                self.update()
                event.accept()
                return

            # 确保交互结束时立即落地最终一帧
            if self._interactive_update_pending:
                self._interactive_update_timer.stop()
                self._flush_interactive_update()

            if self.is_resizing:
                # 结束图层大小调整
                self.is_resizing = False

                # 如果大小有变化，保存历史记录
                if self.document.selected_layer_index >= 0 and self.resize_start_rect:
                    layer = self.document.layers[self.document.selected_layer_index]
                    changed = False
                    if is_layer_group(layer):
                        bounds = group_bounds(self.document.layers, layer, include_hidden=False)
                        if bounds:
                            left, top, right, bottom = bounds
                            changed = (
                                left != self.resize_start_rect.x() or
                                top != self.resize_start_rect.y() or
                                (right - left) != self.resize_start_rect.width() or
                                (bottom - top) != self.resize_start_rect.height()
                            )
                    else:
                        changed = (
                            layer.x != self.resize_start_rect.x() or
                            layer.y != self.resize_start_rect.y() or
                            layer.width != self.resize_start_rect.width() or
                            layer.height != self.resize_start_rect.height()
                        )
                    if changed:
                        self.document.save_state("调整图层组大小" if is_layer_group(layer) else "调整图层大小")
                        self._request_high_quality_refresh()

                self.resize_handle_index = -1
                self.resize_start_rect = None
                self.resize_start_point = None
                self.resize_start_group_child_rects = {}

            elif self.is_dragging_corner_radius:
                self.is_dragging_corner_radius = False
                self.corner_radius_start_point = None
                self.document.save_state("调整圆角")
                self._request_high_quality_refresh()

            elif self.is_dragging_vector_node:
                self.is_dragging_vector_node = False
                self.vector_node_index = -1
                self.document.save_state("编辑路径节点")
                self._request_high_quality_refresh()

            elif self.is_dragging_vector_handle:
                self.is_dragging_vector_handle = False
                self.vector_handle_node_index = -1
                self.vector_handle_type = None
                self.document.save_state("编辑贝塞尔手柄")
                self._request_high_quality_refresh()

            elif self.is_dragging_layer:
                # 结束图层拖动
                self.is_dragging_layer = False
                self._snap_feedback_active = False

                # 如果位置有变化，保存历史记录
                if self.dragging_layer_index >= 0:
                    drag_count = len(getattr(self, 'dragging_layer_indices', []) or [self.dragging_layer_index])
                    self.document.save_state("批量移动图层" if drag_count > 1 else "移动图层")
                    self._request_high_quality_refresh()

                self.dragging_layer_index = -1
                self.layer_drag_start = None
                self.dragging_layer_indices = []
                self.dragging_layer_start_positions = {}
                self.dragging_group_start_bounds = None

                # 清理拖拽相关状态
                self._clear_drag_state()

            elif self.potential_drag:
                # 如果只是点击没有拖拽，重置潜在拖拽状态
                self.potential_drag = False
                self.dragging_layer_index = -1
                self.drag_start_pos = None
                self.layer_drag_start = None

            elif self.is_dragging:
                # 结束画布拖动
                self.is_dragging = False
                self.drag_start = None
                self._persist_view_settings_to_document()
                # 如果在临时抓手模式，恢复抓手光标，否则恢复箭头光标
                if self.temp_hand_mode:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)

            # 统一恢复默认光标（除非在特殊模式）
            if not self.temp_hand_mode and not self.is_resizing and not self.is_dragging_layer and not self.is_dragging:
                self.setCursor(Qt.ArrowCursor)

        event.accept()

    def keyPressEvent(self, event):
        """键盘事件处理"""
        # 视图快捷键（Photoshop风格）
        if event.modifiers() & Qt.ControlModifier and not event.isAutoRepeat():
            if event.key() == Qt.Key_R:
                self.show_rulers = not self.show_rulers
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return

        # 路径节点快捷键（AI风格）：1=尖角 2=平滑 3=对称
        if self.document.selected_layer_index >= 0 and self.selected_vector_node_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if bool(getattr(layer, 'vector_path_enabled', False)) and hasattr(layer, 'set_vector_node_type'):
                if event.key() == Qt.Key_1:
                    layer.set_vector_node_type(self.selected_vector_node_index, "corner")
                    self.document.save_state("节点类型:尖角")
                    self.document.document_changed.emit()
                    event.accept()
                    return

        # 路径联动与闭合快捷键：Q/W/E 切手柄模式，C 切闭合
        if self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if bool(getattr(layer, 'vector_path_enabled', False)):
                if event.key() == Qt.Key_Q:
                    layer.vector_handle_link_mode = "mirror"
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_W:
                    layer.vector_handle_link_mode = "collinear"
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_E:
                    layer.vector_handle_link_mode = "free"
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_C:
                    layer.vector_path_closed = not bool(getattr(layer, 'vector_path_closed', True))
                    self.document.save_state("切换路径闭合")
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_2:
                    layer.set_vector_node_type(self.selected_vector_node_index, "smooth")
                    self.document.save_state("节点类型:平滑")
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_3:
                    layer.set_vector_node_type(self.selected_vector_node_index, "symmetric")
                    self.document.save_state("节点类型:对称")
                    self.document.document_changed.emit()
                    event.accept()
                    return
            if event.key() == Qt.Key_Semicolon:
                self.show_guides = not self.show_guides
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return

        # 删除当前选中的参考线
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.document.selected_layer_index >= 0 and self.selected_vector_node_index >= 0:
                layer = self.document.layers[self.document.selected_layer_index]
                if bool(getattr(layer, 'vector_path_enabled', False)) and hasattr(layer, 'delete_vector_node'):
                    layer.delete_vector_node(self.selected_vector_node_index)
                    self.selected_vector_node_index = -1
                    self.document.save_state("删除路径节点")
                    self.document.document_changed.emit()
                    event.accept()
                    return
            if self._selected_guide_orientation == "vertical" and 0 <= self._selected_guide_index < len(self.vertical_guides):
                self.vertical_guides.pop(self._selected_guide_index)
                self._clear_guide_selection()
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return
            if self._selected_guide_orientation == "horizontal" and 0 <= self._selected_guide_index < len(self.horizontal_guides):
                self.horizontal_guides.pop(self._selected_guide_index)
                self._clear_guide_selection()
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return

        # 处理Space键启用临时抓手工具
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if not self.space_pressed:
                self.space_pressed = True
                self.temp_hand_mode = True
                # 保存当前光标
                self.original_cursor = self.cursor()
                # 设置抓手光标
                self.setCursor(Qt.OpenHandCursor)
                event.accept()
                return

        # 处理方向键移动选中的图层
        selected_indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
        if not selected_indices and self.document.selected_layer_index >= 0:
            selected_indices = [self.document.selected_layer_index]
        if selected_indices:
            move_step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            dx = dy = 0
            if event.key() == Qt.Key_Left:
                dx = -move_step
            elif event.key() == Qt.Key_Right:
                dx = move_step
            elif event.key() == Qt.Key_Up:
                dy = -move_step
            elif event.key() == Qt.Key_Down:
                dy = move_step

            if dx or dy:
                expanded_indices = expand_group_indices(self.document.layers, selected_indices, include_groups=False)
                movable_indices = [
                    idx for idx in expanded_indices
                    if (
                        0 <= idx < len(self.document.layers)
                        and not is_layer_group(self.document.layers[idx])
                        and not is_effectively_locked(self.document.layers[idx], self.document.layers)
                    )
                ]
                if not movable_indices:
                    event.accept()
                    return
                self.document.save_state("批量移动图层前" if len(movable_indices) > 1 else "移动图层前")
                for idx in movable_indices:
                    layer = self.document.layers[idx]
                    layer.x += dx
                    layer.y += dy
                self.document.save_state("批量移动图层" if len(movable_indices) > 1 else "移动图层")
                self.document.document_changed.emit()
                self.update()
                event.accept()
                return

        QWidget.keyPressEvent(self, event)

    def keyReleaseEvent(self, event):
        """键盘松开事件处理"""
        # 处理Space键释放，禁用临时抓手工具
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if self.space_pressed:
                self.space_pressed = False
                self.temp_hand_mode = False
                # 恢复原来的光标
                self.setCursor(self.original_cursor)
                event.accept()
                return

        QWidget.keyReleaseEvent(self, event)

    def sizeHint(self):
        """返回控件的建议大小"""
        return QSize(800, 600)

    def show_context_menu(self, pos):
        """显示画布右键菜单"""
        menu = QMenu()
        toggle_ruler_action = None
        toggle_guides_action = None
        clear_guides_action = None

        # 获取主窗口引用
        main_window = self._get_main_window()

        # 检查点击位置是否在图层上
        layer_index = self.get_layer_at_position(pos)

        if layer_index >= 0:
            # 点击在图层上 - 显示图层相关菜单
            if layer_index != self.document.selected_layer_index:
                self.document.select_layer(layer_index)

            layer = self.document.layers[layer_index]

            # 图层操作
            select_action = menu.addAction(f"已选中: {layer.name}")
            select_action.setEnabled(False)  # 仅作为信息显示

            menu.addSeparator()

            # 复制粘贴操作
            copy_action = menu.addAction("复制图层")

            paste_action = None
            if main_window and hasattr(main_window, 'layer_clipboard') and main_window.layer_clipboard:
                paste_action = menu.addAction("粘贴图层")

            menu.addSeparator()

            # 图层样式
            copy_style_action = menu.addAction("复制图层样式")

            paste_style_action = None
            if main_window and hasattr(main_window, 'layer_style_clipboard') and main_window.layer_style_clipboard:
                paste_style_action = menu.addAction("粘贴图层样式")

            menu.addSeparator()

            # 图层管理
            edit_text_action = None
            try:
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer):
                    edit_text_action = menu.addAction("编辑文案")
            except Exception:
                edit_text_action = None
            rename_action = menu.addAction("重命名图层")
            delete_action = menu.addAction("删除图层")

            menu.addSeparator()

            # 图层状态
            lock_action = menu.addAction("锁定图层" if not layer.locked else "解锁图层")

            # 路径编辑菜单
            vector_insert_action = None
            vector_delete_action = None
            vector_toggle_closed_action = None
            vector_cycle_type_action = None
            link_mirror_action = None
            link_collinear_action = None
            link_free_action = None
            if bool(getattr(layer, 'vector_path_enabled', False)):
                menu.addSeparator()
                node_index = self.get_vector_node_at_position(pos, layer_index)
                if node_index >= 0:
                    self.selected_vector_node_index = node_index
                self._context_vector_segment_index = self.get_vector_segment_at_position(pos, layer_index)
                vector_menu = menu.addMenu("路径编辑")
                vector_insert_action = vector_menu.addAction("插入节点")
                vector_delete_action = vector_menu.addAction("删除节点")
                vector_toggle_closed_action = vector_menu.addAction("切换路径闭合")
                vector_cycle_type_action = vector_menu.addAction("循环节点类型")
                vector_menu.addSeparator()
                link_mirror_action = vector_menu.addAction("手柄联动:镜像")
                link_collinear_action = vector_menu.addAction("手柄联动:共线")
                link_free_action = vector_menu.addAction("手柄联动:自由")
                if self.selected_vector_node_index < 0:
                    vector_delete_action.setEnabled(False)
                    vector_cycle_type_action.setEnabled(False)
                if self._context_vector_segment_index < 0:
                    vector_insert_action.setEnabled(False)

        else:
            # 点击在空白画布上 - 显示画布相关菜单
            # 粘贴操作
            paste_action = None
            if main_window and hasattr(main_window, 'layer_clipboard') and main_window.layer_clipboard:
                paste_action = menu.addAction("粘贴图层")

            # 添加图层
            add_layer_action = menu.addAction("添加图层")
            add_text_layer_action = menu.addAction("添加文本图层")

            menu.addSeparator()

            # 画布操作
            canvas_size_action = menu.addAction("修改画布尺寸")

            menu.addSeparator()

            # 视图操作
            zoom_in_action = menu.addAction("放大")
            zoom_out_action = menu.addAction("缩小")
            zoom_reset_action = menu.addAction("重置缩放")
            menu.addSeparator()
            toggle_ruler_action = menu.addAction("隐藏标尺" if self.show_rulers else "显示标尺")
            toggle_guides_action = menu.addAction("隐藏参考线" if self.show_guides else "显示参考线")
            clear_guides_action = menu.addAction("清空参考线")

            # 背景设置（如果有的话）
            # background_action = menu.addAction("背景设置")

        # 显示菜单并处理选择
        action = menu.exec(self.mapToGlobal(pos))

        if not action:
            return

        # 处理图层相关操作
        if layer_index >= 0:
            if 'edit_text_action' in locals() and edit_text_action and action == edit_text_action and main_window:
                main_window.edit_text_layer(layer_index)
            elif action.text() == "复制图层" and main_window:
                main_window.copy_layer()
            elif paste_action and action == paste_action and main_window:
                main_window.paste_layer()
            elif action.text() == "复制图层样式" and main_window:
                main_window.copy_layer_style()
            elif paste_style_action and action == paste_style_action and main_window:
                main_window.paste_layer_style()
            elif action.text() == "重命名图层" and main_window:
                main_window.rename_layer()
            elif action.text() == "删除图层" and main_window:
                main_window.delete_layer()
            elif action.text() in ["锁定图层", "解锁图层"]:
                layer.locked = not layer.locked
                self.document.document_changed.emit()
            elif 'vector_insert_action' in locals() and action == vector_insert_action:
                if hasattr(layer, 'insert_vector_node_after') and self._context_vector_segment_index >= 0:
                    layer.insert_vector_node_after(self._context_vector_segment_index)
                    self.document.save_state("插入路径节点")
                    self.document.document_changed.emit()
            elif 'vector_delete_action' in locals() and action == vector_delete_action:
                if hasattr(layer, 'delete_vector_node') and self.selected_vector_node_index >= 0:
                    layer.delete_vector_node(self.selected_vector_node_index)
                    self.selected_vector_node_index = -1
                    self.document.save_state("删除路径节点")
                    self.document.document_changed.emit()
            elif 'vector_toggle_closed_action' in locals() and action == vector_toggle_closed_action:
                layer.vector_path_closed = not bool(getattr(layer, 'vector_path_closed', True))
                self.document.save_state("切换路径闭合")
                self.document.document_changed.emit()
            elif 'vector_cycle_type_action' in locals() and action == vector_cycle_type_action:
                if hasattr(layer, 'cycle_vector_node_type') and self.selected_vector_node_index >= 0:
                    layer.cycle_vector_node_type(self.selected_vector_node_index)
                    self.document.save_state("循环节点类型")
                    self.document.document_changed.emit()
            elif 'link_mirror_action' in locals() and action == link_mirror_action:
                layer.vector_handle_link_mode = "mirror"
                self.document.save_state("手柄联动:镜像")
                self.document.document_changed.emit()
            elif 'link_collinear_action' in locals() and action == link_collinear_action:
                layer.vector_handle_link_mode = "collinear"
                self.document.save_state("手柄联动:共线")
                self.document.document_changed.emit()
            elif 'link_free_action' in locals() and action == link_free_action:
                layer.vector_handle_link_mode = "free"
                self.document.save_state("手柄联动:自由")
                self.document.document_changed.emit()

        else:
            # 处理画布相关操作
            if paste_action and action == paste_action and main_window:
                main_window.paste_layer()
            elif action.text() == "添加图层" and main_window:
                main_window.add_layer()
            elif action.text() == "添加文本图层" and main_window:
                main_window.add_text_layer()
            elif action.text() == "修改画布尺寸" and main_window:
                main_window.resize_canvas()
            elif action.text() == "放大" and main_window:
                main_window.zoom_in()
            elif action.text() == "缩小" and main_window:
                main_window.zoom_out()
            elif action.text() == "重置缩放" and main_window:
                main_window.zoom_reset()
            elif toggle_ruler_action and action == toggle_ruler_action:
                self.show_rulers = not self.show_rulers
                self._persist_view_settings_to_document()
                self.update()
            elif toggle_guides_action and action == toggle_guides_action:
                self.show_guides = not self.show_guides
                self._persist_view_settings_to_document()
                self.update()
            elif clear_guides_action and action == clear_guides_action:
                self.horizontal_guides.clear()
                self.vertical_guides.clear()
                self._persist_view_settings_to_document()
                self.update()

    def _get_main_window(self):
        """获取主窗口引用"""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'layer_clipboard'):  # 主窗口特征
                return parent
            parent = parent.parent()
        return None
