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

class CanvasWidgetCanvasView(object):
    def _load_view_settings_from_document(self):
        """从文档恢复画布视图参数"""
        if not hasattr(self.document, 'get_view_settings'):
            return
        settings = self.document.get_view_settings()
        self.show_rulers = bool(settings.get('show_rulers', self.show_rulers))
        self.show_guides = bool(settings.get('show_guides', self.show_guides))
        self.snap_to_guides = bool(settings.get('snap_to_guides', self.snap_to_guides))
        self._ruler_size = int(settings.get('ruler_size', self._ruler_size))
        self.horizontal_guides = [int(v) for v in (settings.get('horizontal_guides', []) or [])]
        self.vertical_guides = [int(v) for v in (settings.get('vertical_guides', []) or [])]
        self.zoom_factor = float(settings.get('zoom_factor', self.zoom_factor))
        self.zoom_factor = max(0.1, min(10.0, self.zoom_factor))
        offset_x = int(settings.get('offset_x', self.offset.x()))
        offset_y = int(settings.get('offset_y', self.offset.y()))
        self.offset = QPoint(offset_x, offset_y)

    def _persist_view_settings_to_document(self):
        """将画布视图参数回写到文档，确保保存/预设为全量参数"""
        if not hasattr(self.document, 'set_view_settings'):
            return
        self.document.set_view_settings({
            'show_rulers': self.show_rulers,
            'show_guides': self.show_guides,
            'snap_to_guides': self.snap_to_guides,
            'ruler_size': self._ruler_size,
            'horizontal_guides': list(self.horizontal_guides),
            'vertical_guides': list(self.vertical_guides),
            'zoom_factor': float(self.zoom_factor),
            'offset_x': int(self.offset.x()),
            'offset_y': int(self.offset.y()),
        })

    def _is_export_preview_frozen(self) -> bool:
        """导出期间是否冻结预览重渲染（性能策略）"""
        if not bool(getattr(self.document, '_is_batch_export_running', False)):
            return False
        try:
            settings = getattr(self.document, 'export_settings', {}) or {}
            return bool(settings.get('freeze_preview_during_export', False))
        except Exception:
            return False

    def _is_view_transform_active(self) -> bool:
        """Return True while the user is only changing the viewport."""
        return bool(self._zoom_interaction_active or self.is_dragging)

    def _schedule_interactive_update(self, require_recompose: bool = False):
        """交互过程按固定帧率触发刷新。
        require_recompose=True: 需要重建合成图（图层几何变化）
        require_recompose=False: 仅视图变化（平移等），不重算合成图
        """
        now_ms = time.time() * 1000.0
        elapsed_ms = now_ms - self._last_interactive_update_ms
        if require_recompose:
            self._interactive_requires_recompose = True
            self._interactive_low_quality_active = True

        if elapsed_ms >= self._interactive_frame_interval_ms:
            self._flush_interactive_update()
            return

        if self._interactive_update_pending:
            return

        self._interactive_update_pending = True
        wait_ms = max(1, int(self._interactive_frame_interval_ms - elapsed_ms))
        self._interactive_update_timer.start(wait_ms)

    def _flush_interactive_update(self):
        """执行一次节流后的交互刷新"""
        self._interactive_update_pending = False
        self._last_interactive_update_ms = time.time() * 1000.0
        if self._is_export_preview_frozen():
            self._interactive_requires_recompose = False
            self._interactive_low_quality_active = False
            self._panel_interaction_active = False
            self._panel_interaction_layer_index = -1
            return
        if self._interactive_requires_recompose:
            # 交互期间只标记画面过期，不取消正在跑的后台预览，避免鼠标高频移动导致渲染线程一直重启。
            self._composition_cache_valid = False
            self._invalidate_scaled_pixmap_cache()
        self._interactive_requires_recompose = False
        self.update()

    def _request_high_quality_refresh(self):
        """交互结束后强制回填一帧高质量预览。"""
        self._interactive_low_quality_active = False
        self._force_high_quality_refresh = True
        self._invalidate_composition_cache()
        self.update()

    def _on_zoom_interaction_idle(self):
        """滚轮缩放停止后回填一帧平滑缩放的预览。"""
        if not self._zoom_interaction_active:
            return
        self._zoom_interaction_active = False
        self._invalidate_scaled_pixmap_cache()
        self._persist_view_settings_to_document()
        self.update()

    def _get_interaction_active_layer_index(self) -> int:
        """获取当前交互中的活动图层索引；无活动图层返回 -1。"""
        if self.is_dragging_layer and self.dragging_layer_index >= 0:
            return int(self.dragging_layer_index)
        if self.is_resizing and self.document.selected_layer_index >= 0:
            return int(self.document.selected_layer_index)
        if self.is_dragging_corner_radius and self.document.selected_layer_index >= 0:
            return int(self.document.selected_layer_index)
        if self._panel_interaction_active and self._panel_interaction_layer_index >= 0:
            return int(self._panel_interaction_layer_index)
        return -1

    def _sync_panel_interaction_state(self):
        """根据属性面板高频参数变更上下文，驱动增量渲染会话。"""
        if not hasattr(self.document, "get_change_context"):
            return
        try:
            ctx = self.document.get_change_context(max_age_ms=220)
        except Exception:
            ctx = None
        if not ctx or ctx.get("source") != "layer_properties_panel":
            return

        layer_index = int(ctx.get("layer_index", -1))
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        fields = set(ctx.get("fields", []) or [])
        if fields and fields.isdisjoint(self._panel_interaction_fields):
            return

        self._panel_interaction_active = True
        self._panel_interaction_layer_index = layer_index
        self._interactive_low_quality_active = True
        # 持续收到高频参数变化时会不断重置计时，停止后自动回填高质量
        self._panel_interaction_idle_timer.start(160)

    def _on_panel_interaction_idle(self):
        """属性面板高频交互停止，触发高质量回填。"""
        if not self._panel_interaction_active:
            return
        self._panel_interaction_active = False
        self._panel_interaction_layer_index = -1
        self._request_high_quality_refresh()

    def get_canvas_rect(self):
        """获取画布在屏幕上的矩形区域"""
        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            return None

        # 计算缩放后的尺寸
        canvas_width = int(self.document.canvas_width * self.zoom_factor)
        canvas_height = int(self.document.canvas_height * self.zoom_factor)
        ruler = self._get_ruler_thickness()

        # 计算画布居中位置
        content_width = max(1, self.width() - ruler)
        content_height = max(1, self.height() - ruler)
        center_x = ruler + max(0, (content_width - canvas_width) // 2) + self.offset.x()
        center_y = ruler + max(0, (content_height - canvas_height) // 2) + self.offset.y()

        return QRect(center_x, center_y, canvas_width, canvas_height)

    def wheelEvent(self, event):
        """处理鼠标滚轮事件实现缩放"""
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return

        old_zoom = float(self.zoom_factor)
        old_canvas_rect = self.get_canvas_rect()
        cursor_doc_x = cursor_doc_y = None
        if old_canvas_rect and old_zoom > 0:
            cursor_doc_x = (event.position().x() - old_canvas_rect.x()) / old_zoom
            cursor_doc_y = (event.position().y() - old_canvas_rect.y()) / old_zoom

        # 计算放大或缩小的新缩放因子
        if delta > 0:
            self.zoom_factor *= 1.1  # 放大
        else:
            self.zoom_factor /= 1.1  # 缩小

        # 限制缩放范围
        self.zoom_factor = max(0.1, min(10.0, self.zoom_factor))
        if abs(self.zoom_factor - old_zoom) < 1e-6:
            event.accept()
            return

        self._zoom_interaction_active = True
        self._zoom_idle_timer.start(140)
        self._invalidate_scaled_pixmap_cache()

        if cursor_doc_x is not None and cursor_doc_y is not None:
            new_canvas_rect = self.get_canvas_rect()
            if new_canvas_rect:
                target_x = event.position().x() - cursor_doc_x * self.zoom_factor
                target_y = event.position().y() - cursor_doc_y * self.zoom_factor
                self.offset += QPoint(
                    int(round(target_x - new_canvas_rect.x())),
                    int(round(target_y - new_canvas_rect.y()))
                )

        self.update()
        # 就地文字编辑器随缩放同步位置与字号
        try:
            self._sync_text_editor_geometry()
        except Exception:
            pass
        event.accept()

    def _should_skip_hover_hit_test(self, pos: QPoint) -> bool:
        """Throttle expensive hover hit testing when the mouse is simply moving."""
        now_ms = time.time() * 1000.0
        if (
            now_ms - self._last_hover_hit_test_ms < self._hover_hit_test_interval_ms
            and (pos - self._last_hover_pos).manhattanLength() < 4
        ):
            return True
        self._last_hover_hit_test_ms = now_ms
        self._last_hover_pos = QPoint(pos)
        return False
