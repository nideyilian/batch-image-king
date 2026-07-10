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
import logging

logger = logging.getLogger(__name__)
class CanvasWidgetCanvasRender(object):
    def _invalidate_composition_cache(self):
        """文档发生变化时使合成图缓存失效"""
        # 导出高负载模式下允许冻结预览，避免导出线程与预览线程争用
        if self._is_export_preview_frozen():
            if self._composition_pixmap_cache is None:
                self._composition_cache_valid = False
            self._invalidate_scaled_pixmap_cache()
            return

        # 优先基于变更上下文判断是否需要失效合成缓存
        # 非视觉字段（如名称、锁定）不触发合成图重建，只更新覆盖层即可
        context = None
        if hasattr(self.document, "get_change_context"):
            try:
                context = self.document.get_change_context(max_age_ms=1200)
            except Exception:
                context = None

        if context:
            fields = set(context.get("fields", []) or [])
            non_visual_fields = {"name", "lock", "selection"}
            if fields and fields.issubset(non_visual_fields):
                self._invalidate_scaled_pixmap_cache()
                return

        self._composition_invalidation_generation += 1
        self._cancel_pending_async_preview()
        self._composition_cache_valid = False
        # Keep the last completed preview visible while the async renderer catches up.
        self._invalidate_scaled_pixmap_cache()

    def _cancel_pending_async_preview(self):
        """Prevent stale background preview results from replacing newer local frames."""
        with self._async_render_lock:
            if not self._async_render_pending:
                return
            self._async_render_generation += 1
            self._async_render_pending = False
            self._async_render_result = None
            self._async_render_error = None
            self._async_render_restart_requested = False
            self._async_render_restart_args = None
            self._async_render_request_key = None

    def _invalidate_scaled_pixmap_cache(self):
        """使缩放后的QPixmap缓存失效"""
        self._scaled_composition_pixmap_cache.clear()
        self._scaled_composition_cache_key = None
        self._composition_mipmap_cache_key = None
        self._composition_mipmap_cache = []

    def _get_scaled_composition_pixmap(self, source_pixmap, target_width, target_height):
        """获取按当前缩放尺寸缓存的QPixmap"""
        if source_pixmap is None:
            return None

        if target_width <= 0 or target_height <= 0:
            return source_pixmap

        cache_key = (
            int(source_pixmap.cacheKey()),
            int(target_width),
            int(target_height),
        )
        cached = self._scaled_composition_pixmap_cache.get(cache_key)
        if cached is not None:
            self._scaled_composition_pixmap_cache.move_to_end(cache_key)
            return cached

        transform_mode = Qt.FastTransformation if self._zoom_interaction_active else Qt.SmoothTransformation
        source_for_scale = self._select_mipmap_source(source_pixmap, target_width, target_height)
        scaled = source_for_scale.scaled(
            target_width,
            target_height,
            Qt.IgnoreAspectRatio,
            transform_mode
        )
        self._scaled_composition_pixmap_cache[cache_key] = scaled
        self._scaled_composition_pixmap_cache.move_to_end(cache_key)
        while len(self._scaled_composition_pixmap_cache) > self._max_scaled_composition_cache_entries:
            self._scaled_composition_pixmap_cache.popitem(last=False)
        self._scaled_composition_cache_key = cache_key
        return scaled

    def _select_mipmap_source(self, source_pixmap, target_width: int, target_height: int):
        """Choose the smallest cached mip level that is still larger than the target."""
        source_max_edge = max(source_pixmap.width(), source_pixmap.height())
        target_max_edge = max(int(target_width), int(target_height))
        if target_max_edge <= 0 or target_max_edge >= int(source_max_edge * 0.75):
            return source_pixmap

        levels = self._get_composition_mipmap_chain(source_pixmap)
        best = source_pixmap
        for level in levels[1:]:
            level_max_edge = max(level.width(), level.height())
            if level_max_edge >= target_max_edge:
                best = level
            else:
                break
        return best

    def _get_composition_mipmap_chain(self, source_pixmap):
        """Build a small half-size pixmap pyramid for large zoomed-out previews."""
        source_key = int(source_pixmap.cacheKey())
        if self._composition_mipmap_cache_key == source_key and self._composition_mipmap_cache:
            return self._composition_mipmap_cache

        levels = [source_pixmap]
        current = source_pixmap
        for _ in range(6):
            next_width = max(1, current.width() // 2)
            next_height = max(1, current.height() // 2)
            if next_width == current.width() and next_height == current.height():
                break
            current = current.scaled(
                next_width,
                next_height,
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation
            )
            levels.append(current)
            if max(next_width, next_height) <= 512:
                break

        self._composition_mipmap_cache_key = source_key
        self._composition_mipmap_cache = levels
        return levels

    def _create_blank_composition_pixmap(self):
        """Create a transparent placeholder so paintEvent never performs a full render."""
        try:
            pixmap = QPixmap(1, 1)
            if pixmap.isNull():
                return None
            pixmap.fill(Qt.transparent)
            self._composition_pixmap_cache = pixmap
            self._composition_cache_valid = False
            self._invalidate_scaled_pixmap_cache()
            return pixmap
        except Exception:
            logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
            return None

    def _get_cached_composition_pixmap(self):
        """获取合成图QPixmap缓存，必要时重新生成"""
        self._sync_panel_interaction_state()
        force_refresh = bool(getattr(self.document, '_needs_cache_refresh', False) or self._force_high_quality_refresh)
        if self._composition_cache_valid and self._composition_pixmap_cache is not None and not force_refresh:
            return self._composition_pixmap_cache
        if self._is_export_preview_frozen() and self._composition_pixmap_cache is not None:
            return self._composition_pixmap_cache

        interactive_low_quality = bool(
            self._interactive_low_quality_active
            and not self._force_high_quality_refresh
            and (
                self.is_dragging_layer
                or self.is_resizing
                or self.is_dragging_corner_radius
                or self._panel_interaction_active
            )
        )
        # 随机化/整体失效场景：首帧先用低质量即时出图，点击立即刷新
        quick_first_frame = bool(
            getattr(self.document, '_quick_first_frame', False)
            and not self._interactive_low_quality_active
            and not self._force_high_quality_refresh
        )
        if quick_first_frame and not interactive_low_quality:
            interactive_low_quality = True
            self._pending_quick_frame_completion = True
        active_layer_index = self._get_interaction_active_layer_index()
        request_key = (
            int(self._composition_invalidation_generation),
            bool(force_refresh),
            bool(interactive_low_quality),
            int(active_layer_index),
        )
        if self._composition_pixmap_cache is not None:
            self._start_async_composition_render(force_refresh, interactive_low_quality, active_layer_index, request_key)
            return self._composition_pixmap_cache

        self._start_async_composition_render(force_refresh, interactive_low_quality, active_layer_index, request_key)
        return self._create_blank_composition_pixmap()

    def _build_async_render_snapshot(self):
        """Capture an immutable document snapshot for the background preview worker."""
        try:
            from app.models.document_serializer import DocumentSerializer
            snapshot = DocumentSerializer.serialize_document_data(self.document)
            if isinstance(snapshot, dict):
                return snapshot
        except Exception:
            logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
            pass
        return None

    def _restore_async_render_snapshot(self, snapshot_data):
        """Restore a preview-only document from serialized data in the worker thread."""
        if not isinstance(snapshot_data, dict):
            return None
        try:
            from app.models.document import Document
            from app.models.document_serializer import DocumentSerializer
            snapshot_document = Document(parent=None)
            if not DocumentSerializer.restore_document_data(snapshot_document, snapshot_data):
                return None
            snapshot_document._is_batch_export_running = False
            snapshot_document._export_canceled = False
            snapshot_document._needs_cache_refresh = False
            return snapshot_document
        except Exception:
            logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
            return None

    def _render_composition_image_for_async(self, force_refresh: bool, interactive_low_quality: bool, active_layer_index: int, snapshot_data=None):
        """Render a PIL composition outside paintEvent; QPixmap conversion stays on the GUI thread."""
        render_document = self._restore_async_render_snapshot(snapshot_data)
        using_snapshot = render_document is not None
        if not using_snapshot:
            render_document = self.document
        try:
            from app.services.preview_render_service import render_preview_to_image

            result = render_preview_to_image(
                render_document,
                force_refresh=force_refresh,
                interactive_low_quality=interactive_low_quality,
                active_layer_index=active_layer_index,
            )
            if result.image is not None:
                return result.image
        except Exception:
            logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
            pass

        try:
            from app.services.render_service import render_document_legacy_fallback

            image = render_document_legacy_fallback(render_document)
            if image is not None:
                return image
        except Exception:
            logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
            pass

        if using_snapshot:
            try:
                from app.services.render_service import render_document_legacy_fallback

                return render_document_legacy_fallback(self.document)
            except Exception:
                logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
                return None
        return None

    def _composition_to_pixmap(self, composition):
        if not composition:
            return None
        try:
            from PIL import ImageQt
            qimage = ImageQt.toqimage(composition)
        except Exception:
            try:
                rgba = composition.convert("RGBA")
                img_data = rgba.tobytes("raw", "RGBA")
                qimage = QImage(img_data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888)
            except Exception:
                logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
                return None
        return QPixmap.fromImage(qimage)

    def _start_async_composition_render(self, force_refresh: bool, interactive_low_quality: bool, active_layer_index: int, request_key=None):
        """Start one background preview render and keep painting the previous pixmap meanwhile."""
        if request_key is None:
            request_key = (
                int(self._composition_invalidation_generation),
                bool(force_refresh),
                bool(interactive_low_quality),
                int(active_layer_index),
            )
        with self._async_render_lock:
            if self._async_render_pending:
                if self._async_render_request_key != request_key:
                    self._async_render_restart_requested = True
                    self._async_render_restart_args = (
                        force_refresh,
                        interactive_low_quality,
                        active_layer_index,
                        request_key,
                    )
                return
            self._async_render_pending = True
            self._async_render_result = None
            self._async_render_error = None
            self._async_render_request_key = request_key
            self._async_render_restart_args = None
            self._async_render_generation += 1
            generation = self._async_render_generation

        if force_refresh:
            self.document._needs_cache_refresh = False
        if self._force_high_quality_refresh:
            self._force_high_quality_refresh = False
        snapshot_data = self._build_async_render_snapshot() if self._should_isolate_async_preview(interactive_low_quality) else None

        def _worker():
            image = None
            error = None
            try:
                image = self._render_composition_image_for_async(
                    force_refresh,
                    interactive_low_quality,
                    active_layer_index,
                    snapshot_data
                )
            except Exception as exc:
                error = exc
            with self._async_render_lock:
                if generation == self._async_render_generation:
                    self._async_render_result = image
                    self._async_render_error = error
                    self._async_render_pending = False

        try:
            QThreadPool.globalInstance().start(_CanvasPreviewRenderTask(_worker))
        except Exception:
            threading.Thread(target=_worker, name="CanvasPreviewRender", daemon=True).start()
        if not self._async_render_timer.isActive():
            self._async_render_timer.start()

    def _should_isolate_async_preview(self, interactive_low_quality: bool) -> bool:
        """Use heavyweight document snapshots only when export state may mutate layers."""
        if interactive_low_quality:
            return False
        return bool(getattr(self.document, '_is_batch_export_running', False))

    def _poll_async_render_result(self):
        """Install a completed background render result on the GUI thread."""
        with self._async_render_lock:
            if self._async_render_pending:
                return
            image = self._async_render_result
            error = self._async_render_error
            restart = self._async_render_restart_requested
            restart_args = self._async_render_restart_args
            self._async_render_result = None
            self._async_render_error = None
            self._async_render_restart_requested = False
            self._async_render_restart_args = None
            self._async_render_request_key = None

        if image is None and error is None and not restart:
            self._async_render_timer.stop()
            return

        if image is not None:
            pixmap = self._composition_to_pixmap(image)
            if pixmap is not None:
                self._composition_pixmap_cache = pixmap
                self._composition_cache_valid = not restart
                self._invalidate_scaled_pixmap_cache()
                self.update()

        # 快速首帧回填完成：清除标记，并触发一次全质量补全渲染
        if getattr(self, '_pending_quick_frame_completion', False) and image is not None:
            self._pending_quick_frame_completion = False
            if getattr(self.document, '_quick_first_frame', False):
                try:
                    self.document._quick_first_frame = False
                except Exception:
                    logger.warning("静默异常已忽略: except Exception: in canvas_render.py", exc_info=True)
                    pass
            # 重新启动一次全质量渲染（不低质量），覆盖快速首帧
            if not restart:
                force_refresh = True
                active_layer_index = self._get_interaction_active_layer_index()
                request_key = (
                    int(self._composition_invalidation_generation),
                    True,
                    False,
                    int(active_layer_index),
                )
                self._start_async_composition_render(force_refresh, False, active_layer_index, request_key)

        if restart:
            if restart_args:
                self._start_async_composition_render(*restart_args)
            else:
                force_refresh = bool(getattr(self.document, '_needs_cache_refresh', False) or self._force_high_quality_refresh)
                interactive_low_quality = bool(
                    self._interactive_low_quality_active
                    and not self._force_high_quality_refresh
                    and (
                        self.is_dragging_layer
                        or self.is_resizing
                        or self.is_dragging_corner_radius
                        or self._panel_interaction_active
                    )
                )
                active_layer_index = self._get_interaction_active_layer_index()
                request_key = (
                    int(self._composition_invalidation_generation),
                    bool(force_refresh),
                    bool(interactive_low_quality),
                    int(active_layer_index),
                )
                self._start_async_composition_render(force_refresh, interactive_low_quality, active_layer_index, request_key)
        else:
            self._async_render_timer.stop()

    def draw_transparency_checkerboard(self, painter):
        """绘制表示透明区域的棋盘格背景"""

        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            return

        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return

        # 使用缓存图案平铺，避免每帧双层循环 fillRect
        self._ensure_checkerboard_cache()
        if self._checkerboard_cache:
            painter.drawTiledPixmap(canvas_rect, self._checkerboard_cache)

    def _get_ruler_thickness(self):
        return self._ruler_size if self.show_rulers else 0

    def _ensure_checkerboard_cache(self):
        """确保棋盘格缓存已创建"""
        cache_size = QSize(self._checkerboard_cell_size * 2, self._checkerboard_cell_size * 2)
        if self._checkerboard_cache and self._checkerboard_cache_size == cache_size:
            return

        pixmap = QPixmap(cache_size)
        pixmap.fill(Qt.transparent)
        cache_painter = QPainter(pixmap)
        dark = QColor(180, 180, 180)
        light = QColor(220, 220, 220)
        cell = self._checkerboard_cell_size
        cache_painter.fillRect(0, 0, cell, cell, light)
        cache_painter.fillRect(cell, 0, cell, cell, dark)
        cache_painter.fillRect(0, cell, cell, cell, dark)
        cache_painter.fillRect(cell, cell, cell, cell, light)
        cache_painter.end()

        self._checkerboard_cache = pixmap
        self._checkerboard_cache_size = cache_size

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        view_transform_active = self._is_view_transform_active()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, not view_transform_active)

        # 绘制画布背景（棋盘格背景表示透明区域）
        self.draw_transparency_checkerboard(painter)

        # 如果文档没有设置尺寸，显示提示信息
        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            painter.setPen(QColor(CursorDarkTheme.TEXT_SECONDARY))
            painter.drawText(self.rect(), Qt.AlignCenter, "请创建新画布或打开现有文档")
            return

        pixmap = self._get_cached_composition_pixmap()
        if pixmap:
            canvas_rect = self.get_canvas_rect()
            if not canvas_rect:
                return
            canvas_width = canvas_rect.width()
            canvas_height = canvas_rect.height()
            center_x = canvas_rect.x()
            center_y = canvas_rect.y()

            # 视图交互时直接让 Qt 绘制到目标矩形，避免每个滚轮/平移帧分配新的大 QPixmap。
            if view_transform_active:
                painter.drawPixmap(QRect(center_x, center_y, canvas_width, canvas_height), pixmap)
            else:
                scaled_pixmap = self._get_scaled_composition_pixmap(pixmap, canvas_width, canvas_height)
                if scaled_pixmap:
                    painter.drawPixmap(center_x, center_y, scaled_pixmap)

            # 绘制画布边框
            painter.setPen(QPen(QColor(CursorDarkTheme.BORDER_SECONDARY), 1, Qt.SolidLine))
            painter.drawRect(center_x, center_y, canvas_width, canvas_height)
            self._draw_guides(painter, canvas_rect)

            # 如果有选中的图层，绘制图层边框和控制点
            if self.document.selected_layer_index >= 0 and self.document.selected_layer_index < len(self.document.layers):
                layer = self.document.layers[self.document.selected_layer_index]
                if is_layer_group(layer):
                    self._draw_group_selection(painter, self.document.selected_layer_index)
                    return

                # 判断是否启用了分身效果（安全地检查属性是否存在）
                is_clone_enabled = (hasattr(layer, 'clone_enabled') and layer.clone_enabled)

                if is_clone_enabled:
                    try:
                        # 获取所有分身位置
                        if hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                            clone_positions = layer.get_clone_positions()
                        else:
                            # 如果方法不存在，则回退到单图层渲染
                            is_clone_enabled = False
                            clone_positions = [(layer.x, layer.y)]

                        fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
                        if fill_enabled:
                            spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                            angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                            mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                            dx = max(1, int(layer.width + spacing))
                            dy = max(1, int(layer.height + spacing))
                            positions = []
                            cx = self.document.canvas_width / 2.0
                            cy = self.document.canvas_height / 2.0
                            base_x = layer.x
                            base_y = layer.y
                            import math
                            angle = math.radians(angle_deg % 360.0)
                            start_y = -layer.height
                            end_y = self.document.canvas_height + layer.height
                            if mode == 'border':
                                # 边框排列：确保四角有元素，行距列距统一
                                positions = []

                                # 获取边距参数
                                margin = int(getattr(layer, 'clone_fill_margin', 0))
                                effective_width = self.document.canvas_width - 2 * margin
                                effective_height = self.document.canvas_height - 2 * margin

                                # 计算每边的元素数量，确保四角都有元素
                                # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                                top_bottom_count = max(2, (effective_width + dx) // dx)  # 至少2个（两角）
                                # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                                left_right_count = max(2, (effective_height + dy) // dy)  # 至少2个（两角）

                                # 计算统一的间距，确保元素均匀分布
                                if top_bottom_count > 1:
                                    top_bottom_spacing = (effective_width - layer.width) / (top_bottom_count - 1)
                                else:
                                    top_bottom_spacing = 0

                                if left_right_count > 1:
                                    left_right_spacing = (effective_height - layer.height) / (left_right_count - 1)
                                else:
                                    left_right_spacing = 0

                                # 顶部边缘（包括左上角和右上角）
                                for i in range(top_bottom_count):
                                    x = margin + int(i * top_bottom_spacing)
                                    if x <= self.document.canvas_width - layer.width - margin:  # 确保不超出画布边距范围
                                        positions.append((x, margin))

                                # 底部边缘（包括左下角和右下角）
                                for i in range(top_bottom_count):
                                    x = margin + int(i * top_bottom_spacing)
                                    if x <= self.document.canvas_width - layer.width - margin:  # 确保不超出画布边距范围
                                        positions.append((x, self.document.canvas_height - layer.height - margin))

                                # 左侧边缘（不包括已经放置的角落元素）
                                for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                    y = margin + int(i * left_right_spacing)
                                    if margin < y < self.document.canvas_height - layer.height - margin:  # 确保有效位置
                                        positions.append((margin, y))

                                # 右侧边缘（不包括已经放置的角落元素）
                                for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                    y = margin + int(i * left_right_spacing)
                                    if margin < y < self.document.canvas_height - layer.height - margin:  # 确保有效位置
                                        positions.append((self.document.canvas_width - layer.width - margin, y))
                            else:
                                step_y = dy
                                i_row = 0
                                for row_y in range(start_y, end_y + 1, step_y):
                                    offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                                    for col_x in range(-layer.width, self.document.canvas_width + layer.width + 1, dx):
                                        x0 = base_x + col_x + offset
                                        y0 = base_y + row_y
                                        if angle != 0.0:
                                            rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                                            ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                                            x = int(rx)
                                            y = int(ry)
                                        else:
                                            x = x0
                                            y = y0
                                        positions.append((x, y))
                                    i_row += 1
                            clone_positions = positions if positions else clone_positions

                        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                        if mirror_mode and mirror_mode != 'none':
                            positions = clone_positions[:]
                            min_x = min([x for x, _ in positions])
                            max_x = max([x + layer.width for x, _ in positions])
                            min_y = min([y for _, y in positions])
                            max_y = max([y + layer.height for _, y in positions])
                            group_width = max_x - min_x
                            group_height = max_y - min_y
                            mirrored_positions = []
                            if mirror_mode == 'horizontal':
                                mirrored_left = self.document.canvas_width - (min_x + group_width)
                                for cx, cy in positions:
                                    offset_x = cx - min_x
                                    mirrored_positions.append((mirrored_left + offset_x, cy))
                            elif mirror_mode == 'vertical':
                                mirrored_top = self.document.canvas_height - (min_y + group_height)
                                for cx, cy in positions:
                                    offset_y = cy - min_y
                                    mirrored_positions.append((cx, mirrored_top + offset_y))
                            clone_positions = clone_positions + mirrored_positions

                        # 绘制每个分身的边框和控制点
                        for clone_pos in clone_positions:
                            clone_x, clone_y = clone_pos
                            display_rect = self._get_display_rect_for_layer_position(layer, clone_x, clone_y, canvas_rect)
                            display_x = display_rect.x()
                            display_y = display_rect.y()
                            layer_width = display_rect.width()
                            layer_height = display_rect.height()

                            # 绘制分身边框 - 使用更明显的样式和颜色
                            is_primary = (clone_x == layer.x and clone_y == layer.y)

                            # 清除画刷以防止填充
                            painter.setBrush(Qt.NoBrush)

                            # 根据图层形状绘制对应轮廓，避免双重轮廓问题
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

                            if is_primary:
                                # 主图层（原始位置）使用蓝色边框
                                painter.setPen(QPen(QColor(0, 160, 230), 2, Qt.DashLine))
                            else:
                                # 分身使用淡色边框
                                painter.setPen(QPen(QColor(0, 160, 230, 70), 1, Qt.DotLine))

                            # 根据形状类型绘制对应轮廓
                            if shape == "rectangle":
                                painter.drawPath(self._build_rect_path(layer, display_rect))
                            elif shape == "circle":
                                r = int(min(layer_width, layer_height) / 2)
                                cx = display_x + layer_width // 2
                                cy = display_y + layer_height // 2
                                painter.drawEllipse(QRect(cx - r, cy - r, r * 2, r * 2))
                            elif shape == "right_trapezoid":
                                # 使用图层实际的梯形参数
                                top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                                bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                                slope_side = getattr(layer, 'trapezoid_slope_side', 'right')

                                top_width = layer_width * top_width_percent
                                bottom_width = layer_width * bottom_width_percent

                                if slope_side == "right":
                                    # 斜边在右侧
                                    points = [
                                        QPoint(int(display_x), display_y),  # 左上
                                        QPoint(int(display_x + top_width), display_y),  # 右上
                                        QPoint(int(display_x + bottom_width), display_y + layer_height),  # 右下
                                        QPoint(int(display_x), display_y + layer_height)  # 左下
                                    ]
                                else:
                                    # 斜边在左侧
                                    points = [
                                        QPoint(int(display_x + layer_width - top_width), display_y),  # 左上
                                        QPoint(int(display_x + layer_width), display_y),  # 右上
                                        QPoint(int(display_x + layer_width), display_y + layer_height),  # 右下
                                        QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height)  # 左下
                                    ]
                                painter.drawPolygon(points)
                            elif shape == "pentagon":
                                import math
                                cx = display_x + layer_width / 2
                                cy = display_y + layer_height / 2
                                r = min(layer_width, layer_height) / 2 * 0.9
                                pts = []
                                for i in range(5):
                                    a = 2 * math.pi * i / 5 - math.pi / 2
                                    x = int(cx + r * math.cos(a))
                                    y = int(cy + r * math.sin(a))
                                    pts.append(QPoint(x, y))
                                painter.drawPolygon(pts)
                            elif shape == "hexagon":
                                import math
                                cx = display_x + layer_width / 2
                                cy = display_y + layer_height / 2
                                r = min(layer_width, layer_height) / 2 * 0.9
                                pts = []
                                for i in range(6):
                                    a = 2 * math.pi * i / 6
                                    x = int(cx + r * math.cos(a))
                                    y = int(cy + r * math.sin(a))
                                    pts.append(QPoint(x, y))
                                painter.drawPolygon(pts)

                            # 为主分身绘制控制点
                            if is_primary and not layer.locked and not layer.use_original_size:
                                # 绘制图层控制点
                                painter.setBrush(QBrush(QColor(0, 160, 230)))
                                handle_size = 8
                                handle_points = []

                                # 根据形状类型绘制对应的控制点
                                if shape == "rectangle":
                                    # 矩形：四角和四边中点
                                    handle_points = [
                                        QPoint(display_x, display_y),  # 左上
                                        QPoint(display_x + layer_width // 2, display_y),  # 上中
                                        QPoint(display_x + layer_width, display_y),  # 右上
                                        QPoint(display_x + layer_width, display_y + layer_height // 2),  # 右中
                                        QPoint(display_x + layer_width, display_y + layer_height),  # 右下
                                        QPoint(display_x + layer_width // 2, display_y + layer_height),  # 下中
                                        QPoint(display_x, display_y + layer_height),  # 左下
                                        QPoint(display_x, display_y + layer_height // 2),  # 左中
                                    ]
                                elif shape == "circle":
                                    # 圆形：四个方向点
                                    r = int(min(layer_width, layer_height) / 2)
                                    cx = display_x + layer_width // 2
                                    cy = display_y + layer_height // 2
                                    handle_points = [
                                        QPoint(cx, display_y),  # 上
                                        QPoint(display_x + layer_width, cy),  # 右
                                        QPoint(cx, display_y + layer_height),  # 下
                                        QPoint(display_x, cy),  # 左
                                    ]
                                elif shape == "right_trapezoid":
                                    # 直角梯形：使用图层真实参数
                                    top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                                    bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                                    slope_side = getattr(layer, 'trapezoid_slope_side', 'right')

                                    top_width = layer_width * top_width_percent
                                    bottom_width = layer_width * bottom_width_percent

                                    if slope_side == "right":
                                        handle_points = [
                                            QPoint(int(display_x), display_y),  # 左上
                                            QPoint(int(display_x + top_width), display_y),  # 右上
                                            QPoint(int(display_x + bottom_width), display_y + layer_height),  # 右下
                                            QPoint(int(display_x), display_y + layer_height),  # 左下
                                        ]
                                    else:
                                        handle_points = [
                                            QPoint(int(display_x + layer_width - top_width), display_y),  # 左上
                                            QPoint(int(display_x + layer_width), display_y),  # 右上
                                            QPoint(int(display_x + layer_width), display_y + layer_height),  # 右下
                                            QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height),  # 左下
                                        ]
                                elif shape == "pentagon":
                                    # 正五边形：五个顶点
                                    import math
                                    cx = display_x + layer_width / 2
                                    cy = display_y + layer_height / 2
                                    r = min(layer_width, layer_height) / 2 * 0.9
                                    for i in range(5):
                                        a = 2 * math.pi * i / 5 - math.pi / 2
                                        x = int(cx + r * math.cos(a))
                                        y = int(cy + r * math.sin(a))
                                        handle_points.append(QPoint(x, y))
                                elif shape == "hexagon":
                                    # 正六边形：六个顶点
                                    import math
                                    cx = display_x + layer_width / 2
                                    cy = display_y + layer_height / 2
                                    r = min(layer_width, layer_height) / 2 * 0.9
                                    for i in range(6):
                                        a = 2 * math.pi * i / 6
                                        x = int(cx + r * math.cos(a))
                                        y = int(cy + r * math.sin(a))
                                        handle_points.append(QPoint(x, y))

                                for point in handle_points:
                                    painter.drawRect(point.x() - handle_size // 2, point.y() - handle_size // 2,
                                                       handle_size, handle_size)
                                self._draw_corner_radius_handle(painter, layer, display_rect)
                    except Exception as e:
                        print(f"绘制分身出错: {e}")
                        is_clone_enabled = False

                if not is_clone_enabled:
                    painter.setBrush(Qt.NoBrush)
                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    positions = [(layer.x, layer.y)]
                    if mirror_mode and mirror_mode != 'none':
                        if mirror_mode == 'horizontal':
                            mx = self.document.canvas_width - (layer.x + layer.width)
                            my = layer.y
                            positions.append((mx, my))
                        elif mirror_mode == 'vertical':
                            mx = layer.x
                            my = self.document.canvas_height - (layer.y + layer.height)
                            positions.append((mx, my))

                    for px, py in positions:
                        display_rect = self._get_display_rect_for_layer_position(layer, px, py, canvas_rect)
                        display_x = display_rect.x()
                        display_y = display_rect.y()
                        layer_width = display_rect.width()
                        layer_height = display_rect.height()

                        if hasattr(layer, 'shape_type'):
                            shape_type = layer.shape_type
                            from app.models.layer_properties import ShapeType
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
                            shape = "rectangle"

                        is_primary = (px == layer.x and py == layer.y)
                        if is_primary:
                            painter.setPen(QPen(QColor(0, 160, 230), 2, Qt.DashLine))
                        else:
                            painter.setPen(QPen(QColor(0, 160, 230, 70), 1, Qt.DotLine))

                        if shape == "rectangle":
                            painter.drawPath(self._build_rect_path(layer, display_rect))
                        elif shape == "circle":
                            r = int(min(layer_width, layer_height) / 2)
                            cx = display_x + layer_width // 2
                            cy = display_y + layer_height // 2
                            painter.drawEllipse(QRect(cx - r, cy - r, r * 2, r * 2))
                        elif shape == "right_trapezoid":
                            top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                            bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                            slope_side = getattr(layer, 'trapezoid_slope_side', 'right')
                            top_width = layer_width * top_width_percent
                            bottom_width = layer_width * bottom_width_percent
                            if slope_side == "right":
                                points = [
                                    QPoint(int(display_x), display_y),
                                    QPoint(int(display_x + top_width), display_y),
                                    QPoint(int(display_x + bottom_width), display_y + layer_height),
                                    QPoint(int(display_x), display_y + layer_height)
                                ]
                            else:
                                points = [
                                    QPoint(int(display_x + layer_width - top_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y + layer_height),
                                    QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height)
                                ]
                            painter.drawPolygon(points)
                        elif shape == "pentagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            pts = []
                            for i in range(5):
                                a = 2 * math.pi * i / 5 - math.pi / 2
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                pts.append(QPoint(x, y))
                            painter.drawPolygon(pts)
                        elif shape == "hexagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            pts = []
                            for i in range(6):
                                a = 2 * math.pi * i / 6
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                pts.append(QPoint(x, y))
                            painter.drawPolygon(pts)

                    if is_primary and not layer.locked and not layer.use_original_size:
                        painter.setBrush(QBrush(QColor(0, 160, 230)))
                        handle_size = 8
                        handle_points = []
                        if shape == "rectangle":
                            handle_points = [
                                QPoint(display_x, display_y),
                                QPoint(display_x + layer_width // 2, display_y),
                                QPoint(display_x + layer_width, display_y),
                                QPoint(display_x + layer_width, display_y + layer_height // 2),
                                QPoint(display_x + layer_width, display_y + layer_height),
                                QPoint(display_x + layer_width // 2, display_y + layer_height),
                                QPoint(display_x, display_y + layer_height),
                                QPoint(display_x, display_y + layer_height // 2),
                            ]
                        elif shape == "circle":
                            r = int(min(layer_width, layer_height) / 2)
                            cx = display_x + layer_width // 2
                            cy = display_y + layer_height // 2
                            handle_points = [
                                QPoint(cx, display_y),
                                QPoint(display_x + layer_width, cy),
                                QPoint(cx, display_y + layer_height),
                                QPoint(display_x, cy),
                            ]
                        elif shape == "right_trapezoid":
                            top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                            bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                            slope_side = getattr(layer, 'trapezoid_slope_side', 'right')
                            top_width = layer_width * top_width_percent
                            bottom_width = layer_width * bottom_width_percent
                            if slope_side == "right":
                                handle_points = [
                                    QPoint(int(display_x), display_y),
                                    QPoint(int(display_x + top_width), display_y),
                                    QPoint(int(display_x + bottom_width), display_y + layer_height),
                                    QPoint(int(display_x), display_y + layer_height),
                                ]
                            else:
                                handle_points = [
                                    QPoint(int(display_x + layer_width - top_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y + layer_height),
                                    QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height),
                                ]
                        elif shape == "pentagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            for i in range(5):
                                a = 2 * math.pi * i / 5 - math.pi / 2
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                handle_points.append(QPoint(x, y))
                        elif shape == "hexagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            for i in range(6):
                                a = 2 * math.pi * i / 6
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                handle_points.append(QPoint(x, y))
                        for point in handle_points:
                            painter.drawRect(point.x() - handle_size // 2, point.y() - handle_size // 2, handle_size, handle_size)
                        self._draw_corner_radius_handle(painter, layer, display_rect)

                        if bool(getattr(layer, 'vector_path_enabled', False)):
                            mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
                            if mode == 'bezier':
                                bez_nodes = self._get_vector_bezier_nodes_screen(layer, display_rect)
                                painter.setPen(QPen(QColor(255, 210, 120), 1, Qt.SolidLine))
                                for n in bez_nodes:
                                    painter.drawLine(n['anchor'], n['in'])
                                    painter.drawLine(n['anchor'], n['out'])
                                    painter.setBrush(QBrush(QColor(255, 220, 120)))
                                    painter.drawRect(n['in'].x() - 4, n['in'].y() - 4, 8, 8)
                                    painter.drawRect(n['out'].x() - 4, n['out'].y() - 4, 8, 8)
                                    painter.setBrush(QBrush(QColor(255, 170, 0)))
                                    painter.drawEllipse(n['anchor'].x() - 5, n['anchor'].y() - 5, 10, 10)
                            else:
                                node_points = self._get_vector_node_points(layer, display_rect)
                                painter.setBrush(QBrush(QColor(255, 170, 0)))
                                painter.setPen(QPen(QColor(255, 210, 120), 1, Qt.SolidLine))
                                node_size = 10
                                for np in node_points:
                                    painter.drawEllipse(np.x() - node_size // 2, np.y() - node_size // 2, node_size, node_size)

        # 绘制拖拽交互增强效果
        self._draw_drag_enhancements(painter)
        self._draw_rulers(painter)
