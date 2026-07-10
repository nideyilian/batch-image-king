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

from app.utils.preview_perf import PreviewPerfMonitor, is_perf_enabled, time_block

logger = logging.getLogger(__name__)
class CanvasWidgetCanvasRender(object):
    def _paint_interaction_overlay(self, painter: QPainter):
        """阶段 2：拖拽 overlay 的画法，绕过后台重合成。"""
        overlay = self._interaction_overlay
        canvas_rect = self.get_canvas_rect()
        if canvas_rect is None or canvas_rect.isEmpty():
            return

        # 1. 画底图（按当前 zoom 缩放）
        base_pixmap = overlay.base_pixmap
        if base_pixmap is not None and not base_pixmap.isNull():
            scaled = self._get_scaled_composition_pixmap(
                base_pixmap, canvas_rect.width(), canvas_rect.height()
            )
            if scaled is not None:
                painter.drawPixmap(canvas_rect.x(), canvas_rect.y(), scaled)
        else:
            # 没拿到底图时退回 _get_cached_composition_pixmap 的占位
            cached = self._get_cached_composition_pixmap()
            if cached is not None and not cached.isNull():
                painter.drawPixmap(canvas_rect.x(), canvas_rect.y(), cached)

        # 2. 画活动图层：按 delta 偏移
        delta = overlay.delta
        for idx, surface in overlay.surfaces.items():
            if surface.image is None:
                continue
            # 把 base 像素位置映射到屏幕位置（base_pixmap 是合成原图，缩放到 canvas_rect）
            zoom = self.zoom_factor if self.zoom_factor > 0 else 1.0
            screen_x = canvas_rect.x() + int(round(surface.base_x * zoom)) + delta.x()
            screen_y = canvas_rect.y() + int(round(surface.base_y * zoom)) + delta.y()
            screen_w = max(1, int(round(surface.width * zoom)))
            screen_h = max(1, int(round(surface.height * zoom)))
            target = QRect(screen_x, screen_y, screen_w, screen_h)
            try:
                qimage = self._pil_to_qimage(surface.image)
            except Exception:
                continue
            if qimage.isNull():
                continue
            pix = QPixmap.fromImage(qimage)
            painter.drawPixmap(target, pix)

        # 3. 画画布边框和参考线（与普通 paint 一致）
        painter.setPen(QPen(QColor(CursorDarkTheme.BORDER_SECONDARY), 1, Qt.SolidLine))
        painter.drawRect(canvas_rect)
        self._draw_guides(painter, canvas_rect)

        # 4. 选中框（保持 overlay 期间选中图层可视）
        try:
            self._draw_selection_overlay_for_drag(painter)
        except Exception:
            pass

        # 5. 拖拽增强（边界、方向指示器）+ 标尺
        self._draw_drag_enhancements(painter)
        self._draw_rulers(painter)

    def _pil_to_qimage(self, image):
        """在 overlay 路径上避开 ImageQt，统一走 RGBA 缓冲（更快、零依赖）。"""
        if image is None:
            return QImage()
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        data = image.tobytes("raw", "RGBA")
        qimage = QImage(
            data,
            image.width,
            image.height,
            image.width * 4,
            QImage.Format_RGBA8888,
        )
        return qimage.copy()

    def _draw_selection_overlay_for_drag(self, painter: QPainter):
        """拖拽期间保持选中框/控制点可见。"""
        if self.document.selected_layer_index < 0 or self.document.selected_layer_index >= len(self.document.layers):
            return
        layer = self.document.layers[self.document.selected_layer_index]
        if layer is None:
            return
        canvas_rect = self.get_canvas_rect()
        if canvas_rect is None:
            return
        if is_layer_group(layer):
            self._draw_group_selection(painter, self.document.selected_layer_index)
            return
        # 简化版：用图层真实坐标（拖拽尚未写回时这里用临时 dx/dy）
        zoom = self.zoom_factor if self.zoom_factor > 0 else 1.0
        delta = self._interaction_overlay.delta
        rect = QRect(
            canvas_rect.x() + int(round(int(getattr(layer, "x", 0)) * zoom)) + delta.x(),
            canvas_rect.y() + int(round(int(getattr(layer, "y", 0)) * zoom)) + delta.y(),
            max(1, int(round(int(getattr(layer, "width", 0)) * zoom))),
            max(1, int(round(int(getattr(layer, "height", 0)) * zoom))),
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 160, 230), 2, Qt.DashLine))
        painter.drawRect(rect)

    def _invalidate_hit_cache(self):
        """阶段 6：使 hit-test 缓存失效。"""
        self._hit_cache_generation += 1
        self._hit_rect_cache.clear()
        self._hit_path_cache.clear()
        self._hit_clone_positions_cache.clear()
        self._hit_visible_layers_cache = []
        self._hit_cache_locked_states.clear()

    def _hit_cache_is_fresh(self):
        """检查 hit-test 缓存是否仍然有效。

        命中缓存失效的判定必须覆盖三类变化：
        1. 视图变换（zoom / offset）——几何矩形会变。
        2. 命中测试版本（document.hit_test_version）——图层增删、上下移动、
           显示/隐藏、锁定/解锁、位置/尺寸/旋转、形状/路径/圆角、分身参数、
           组结构等任何影响“点哪里选哪层”的变更。
        3. 显式失效（_hit_cache_generation）——任何文档/合成变化都让旧缓存作废。

        注意：必须检查 _hit_cache_generation。否则 _invalidate_hit_cache()
        清空缓存后若 zoom/offset/版本都未变，这里会误判为“新鲜”，导致点击
        命中落到空缓存（返回 -1），表现为“画面已刷新但点击仍错乱”。
        """
        if self._hit_cache_generation != self._hit_cache_built_generation:
            return False
        if abs(self.zoom_factor - self._hit_cache_zoom) > 1e-6:
            return False
        offset = self.offset
        if offset.x() != self._hit_cache_offset_x or offset.y() != self._hit_cache_offset_y:
            return False
        version = getattr(self.document, "hit_test_version", 0)
        if version != self._hit_cache_hit_version:
            return False
        return True

    def _build_hit_cache(self):
        """为每个图层预计算矩形 + path，分身位置和可见性。"""
        canvas_rect = self.get_canvas_rect()
        if canvas_rect is None:
            return
        self._hit_rect_cache.clear()
        self._hit_path_cache.clear()
        self._hit_clone_positions_cache.clear()
        self._hit_visible_layers_cache = []
        self._hit_cache_locked_states.clear()
        for i, layer in enumerate(self.document.layers):
            if layer is None:
                continue
            self._hit_cache_locked_states[i] = is_effectively_locked(layer, self.document.layers)
            if is_layer_group(layer):
                continue
            if not is_effectively_visible(layer, self.document.layers):
                continue
            self._hit_visible_layers_cache.append(i)
            rect = self.get_layer_rect(i)
            if rect is None:
                continue
            self._hit_rect_cache[i] = rect
            self._hit_path_cache[i] = self._build_rect_path(layer, rect)
            if getattr(layer, "clone_enabled", False) and hasattr(layer, "get_clone_positions"):
                try:
                    self._hit_clone_positions_cache[i] = list(layer.get_clone_positions() or [])
                except Exception:
                    self._hit_clone_positions_cache[i] = []
        self._hit_cache_zoom = self.zoom_factor
        self._hit_cache_offset_x = self.offset.x()
        self._hit_cache_offset_y = self.offset.y()
        self._hit_cache_hit_version = getattr(self.document, "hit_test_version", 0)
        self._hit_cache_built_generation = self._hit_cache_generation

    # 阶段 8：非视觉字段不重建合成图
    _NON_VISUAL_FIELDS = frozenset({
        "name",
        "lock",
        "selection",
        "selected_layer_index",
        "selected_layer_indices",
    })

    def _invalidate_composition_cache(self):
        """文档发生变化时使合成图缓存失效"""
        # 导出高负载模式下允许冻结预览，避免导出线程与预览线程争用
        if self._is_export_preview_frozen():
            if self._composition_pixmap_cache is None:
                self._composition_cache_valid = False
            self._invalidate_scaled_pixmap_cache()
            return

        # 优先基于变更上下文判断是否需要失效合成缓存
        # 非视觉字段（如名称、锁定、选择）不触发合成图重建，只更新覆盖层即可
        context = None
        if hasattr(self.document, "get_change_context"):
            try:
                context = self.document.get_change_context(max_age_ms=1200)
            except Exception:
                context = None

        if context:
            fields = set(context.get("fields", []) or [])
            if fields and fields.issubset(self._NON_VISUAL_FIELDS):
                # 阶段 8：选择变化不重建合成图，只刷 overlay（update()）
                self.update()
                return

        self._composition_invalidation_generation += 1
        self._cancel_pending_async_preview()
        self._composition_cache_valid = False
        # Keep the last completed preview visible while the async renderer catches up.
        self._invalidate_scaled_pixmap_cache()
        # 阶段 6：hit-test 缓存跟随文档/视图变更失效
        self._invalidate_hit_cache()

    def _cancel_pending_async_preview(self):
        """Prevent stale background preview results from replacing newer local frames."""
        with self._async_render_lock:
            if not self._async_render_pending:
                return
            if is_perf_enabled():
                PreviewPerfMonitor.instance().record_dropped_render()
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
        # 阶段 6：视图变换也会让 hit-test 缓存失效
        try:
            self._invalidate_hit_cache()
        except Exception:
            pass

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

    def _is_viewport_only_eligible(self) -> bool:
        """阶段 9：判断是否可以走 viewport-only 渲染。

        条件：画布足够大，zoom 较小（≥2x downsample），且不是 overlay 模式。
        """
        try:
            if getattr(self, "_interaction_overlay", None) is not None and self._interaction_overlay.is_active():
                return False
            if not (self.zoom_factor < 0.6):
                return False
            cw = int(getattr(self.document, "canvas_width", 0))
            ch = int(getattr(self.document, "canvas_height", 0))
            if cw < 2048 or ch < 2048:
                return False
            return True
        except Exception:
            return False

    def _ensure_viewport_only_pixmap(self, canvas_rect):
        """阶段 9：用上一帧 + 当前可见区域切片做低质视图，不再触发后台重渲染。

        这是 fallback：放大镜、缩放滚动时优先复用上一次的合成图，
        保持画面响应。停止后会由 _request_high_quality_refresh 拉起全质量。
        """
        cached = self._composition_pixmap_cache
        if cached is None or cached.isNull():
            return None
        try:
            scaled = self._get_scaled_composition_pixmap(
                cached, canvas_rect.width(), canvas_rect.height()
            )
            return scaled
        except Exception:
            return None

    def _get_cached_composition_pixmap(self):
        """获取合成图QPixmap缓存，必要时重新生成"""
        self._sync_panel_interaction_state()
        perf = PreviewPerfMonitor.instance() if is_perf_enabled() else None
        composition_start = time.perf_counter() if perf is not None else None
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
            if perf is not None and composition_start is not None:
                perf.composition.record((time.perf_counter() - composition_start) * 1000.0)
            return self._composition_pixmap_cache

        self._start_async_composition_render(force_refresh, interactive_low_quality, active_layer_index, request_key)
        if perf is not None and composition_start is not None:
            perf.composition.record((time.perf_counter() - composition_start) * 1000.0)
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

    def _render_composition_image_for_async(self, force_refresh: bool, interactive_low_quality: bool, active_layer_index: int, snapshot_data=None, render_token=None):
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
                cancel_token=render_token,
            )
            if result.cancelled:
                return None
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
            perf = PreviewPerfMonitor.instance() if is_perf_enabled() else None
            if perf is not None:
                pil_start = time.perf_counter()
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
            if perf is not None:
                perf.pil_to_qimage.record((time.perf_counter() - pil_start) * 1000.0)
            return QPixmap.fromImage(qimage)
        except Exception:
            return None

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
            # 阶段 4：每次新请求前，老 token 立即标记 cancel
            try:
                render_token = self._preview_render_token_source.next()
            except Exception:
                render_token = None

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
                    snapshot_data,
                    render_token,
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

        # 阶段 4：token 已取消时直接丢弃本次结果
        try:
            current_token = self._preview_render_token_source.peek()
        except Exception:
            current_token = None
        if current_token is not None and getattr(current_token, "cancelled", False):
            image = None
            error = "cancelled"

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
        perf = PreviewPerfMonitor.instance() if is_perf_enabled() else None
        if perf is not None:
            perf_start = time.perf_counter()
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
            if perf is not None:
                perf.paint.record((time.perf_counter() - perf_start) * 1000.0)
            return

        # 阶段 2：overlay 模式下，不触发后台重渲染，直接画底图 + 活动图层 overlay
        if getattr(self, '_interaction_overlay', None) is not None and self._interaction_overlay.is_active():
            self._paint_interaction_overlay(painter)
            if perf is not None:
                perf.paint.record((time.perf_counter() - perf_start) * 1000.0)
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

            # 阶段 9：视图变换 + 大画布 + 低 zoom 时直接复用上一帧的缩放结果
            if view_transform_active and self._is_viewport_only_eligible():
                vp = self._ensure_viewport_only_pixmap(canvas_rect)
                if vp is not None:
                    painter.drawPixmap(QRect(center_x, center_y, canvas_width, canvas_height), vp)
                else:
                    painter.drawPixmap(QRect(center_x, center_y, canvas_width, canvas_height), pixmap)
            # 视图交互时直接让 Qt 绘制到目标矩形，避免每个滚轮/平移帧分配新的大 QPixmap。
            elif view_transform_active:
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
        if perf is not None:
            perf.paint.record((time.perf_counter() - perf_start) * 1000.0)
