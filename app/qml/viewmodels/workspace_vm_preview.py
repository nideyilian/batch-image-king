"""WorkspaceViewModel 预览管线 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的预览渲染方法组，语义不变。
依赖主类提供的实例属性：``_auto_render``、``_preview_generation``、
``_pending_preview_generation``、``_pending_preview_quality``、``_preview_token_source``、
``_final_preview_timer``、``_preview_timer``、``_render_running``、``_render_pending``、
``_render_request_id``、``_active_render_task``、``_document``、``_document_lock``、
``_preview_provider``、``_preview_revision``、``_text_edit_overlay_visible``、
``_text_edit_layer_index``，以及 ``previewChanged`` 信号与 ``_set_status``/``_set_busy``。
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Slot

from app.utils.layer_tree import is_layer_group

from .workspace_vm_shared import _PreviewTask, _pil_to_qimage


class WorkspacePreviewMixin:
    @Slot(float, float, float, float, result=bool)
    def previewLiveGeometry(self, x: float, y: float, width: float, height: float) -> bool:
        """拖动过程中的画面跟随：把临时几何写进选中图层并立刻要一帧低质量预览。

        与 ``applySelectedGeometry`` 的区别：
        - **不写历史、不置 is_modified、不发 documentInfoChanged**
          （拖动中每帧都改，写历史会把撤销栈撑满）
        - 不走 220ms 的 final 定时器，直接进交互队列，让画面跟手

        松手时仍由 ``commitTransform`` 走一次 ``applySelectedGeometry``
        完成正式的落盘与历史记录。
        """
        # 几何写入与「是否自动渲染」无关：关掉预览时也要能拖动。
        # 只有末尾决定要不要丢一帧渲染时才看 _auto_render。
        indices = [
            int(i)
            for i in list(getattr(self._document, "selected_layer_indices", []) or [])
            if 0 <= int(i) < len(getattr(self._document, "layers", []) or [])
        ]
        if not indices:
            return False
        target_x, target_y = float(x), float(y)
        target_w, target_h = max(1.0, float(width)), max(1.0, float(height))
        try:
            with self._document_lock:
                if len(indices) == 1:
                    layer = self._document.layers[indices[0]]
                    layer.x = int(round(target_x))
                    layer.y = int(round(target_y))
                    layer.width = max(1, int(round(target_w)))
                    layer.height = max(1, int(round(target_h)))
                else:
                    old_x, old_y, old_w, old_h = self._selection_bounds()
                    if old_w <= 0 or old_h <= 0:
                        return False
                    scale_x = target_w / float(old_w)
                    scale_y = target_h / float(old_h)
                    for index in indices:
                        layer = self._document.layers[index]
                        if not hasattr(layer, "x"):
                            continue
                        layer.x = round(target_x + (float(layer.x) - old_x) * scale_x)
                        layer.y = round(target_y + (float(layer.y) - old_y) * scale_y)
                        if hasattr(layer, "width"):
                            layer.width = max(1, round(float(layer.width) * scale_x))
                            layer.height = max(1, round(float(layer.height) * scale_y))
        except Exception:
            return False
        # 只丢一帧交互质量预览，不升级 final
        if not self._auto_render:
            return True
        self._preview_generation += 1
        self._pending_preview_generation = self._preview_generation
        self._pending_preview_quality = "interactive"
        if self._render_running:
            self._render_pending = True
        else:
            self._preview_timer.start(0)
        return True

    @Slot(float, float, float, float, result=bool)
    def restoreSelectedGeometry(self, x: float, y: float, width: float, height: float) -> bool:
        """取消拖动时把几何还原到手势起点。

        ``previewLiveGeometry`` 在拖动过程中会实时改图层几何，所以取消
        （Esc / 鼠标移出）必须显式还原，否则会留下半成品。
        同样不写历史——这次拖动本来就该整体丢弃。
        """
        indices = [
            int(i)
            for i in list(getattr(self._document, "selected_layer_indices", []) or [])
            if 0 <= int(i) < len(getattr(self._document, "layers", []) or [])
        ]
        if not indices:
            return False
        try:
            with self._document_lock:
                if len(indices) == 1:
                    layer = self._document.layers[indices[0]]
                    layer.x = int(round(float(x)))
                    layer.y = int(round(float(y)))
                    if hasattr(layer, "width"):
                        layer.width = max(1, int(round(float(width))))
                        layer.height = max(1, int(round(float(height))))
                else:
                    # 多选：拖动时按比例缩放，还原用同样的比例反向推回
                    current = self._selection_bounds()
                    if current[2] <= 0 or current[3] <= 0:
                        return False
                    scale_x = max(1.0, float(width)) / float(current[2])
                    scale_y = max(1.0, float(height)) / float(current[3])
                    for index in indices:
                        layer = self._document.layers[index]
                        if not hasattr(layer, "x"):
                            continue
                        layer.x = round(float(x) + (float(layer.x) - current[0]) * scale_x)
                        layer.y = round(float(y) + (float(layer.y) - current[1]) * scale_y)
                        if hasattr(layer, "width"):
                            layer.width = max(1, round(float(layer.width) * scale_x))
                            layer.height = max(1, round(float(layer.height) * scale_y))
        except Exception:
            return False
        # 还原后要重画一帧，否则画面还停在拖动中的样子
        if not self._auto_render:
            return True
        self._preview_generation += 1
        self._pending_preview_generation = self._preview_generation
        self._pending_preview_quality = "interactive"
        if self._render_running:
            self._render_pending = True
        else:
            self._preview_timer.start(0)
        return True

    @Slot()
    @Slot(bool)
    def requestPreview(self, force: bool = False) -> None:
        del force
        if not self._auto_render:
            return
        self._preview_generation += 1
        self._pending_preview_generation = self._preview_generation
        self._pending_preview_quality = "interactive"
        self._preview_token_source.cancel()
        self._final_preview_timer.start()
        if self._render_running:
            self._render_pending = True
            return
        self._preview_timer.start()

    @Slot(result=bool)
    def renderPreviewNow(self) -> bool:
        if self._auto_render:
            self._final_preview_timer.stop()
            self._preview_timer.stop()
            self._pending_preview_generation = self._preview_generation
            self._pending_preview_quality = "final"
            self._preview_token_source.cancel()
            if self._render_running:
                self._render_pending = True
                return True
            self._start_preview_render()
            return True
        return self._render_preview_sync()

    @Slot()
    def _queue_final_preview(self) -> None:
        if not self._auto_render:
            return
        # 导出进行中不排队「静止后的全质量帧」：
        # 这一帧是 220ms 无操作后自动触发的，用户此时多半在看导出进度，
        # 画质细节到不了眼睛，却要和 N 个导出线程抢 CPU。
        # 导出结束后第一次真实交互会自然产生新请求，画面不会停在低质量上。
        if bool(getattr(self._document, "_is_batch_export_running", False)):
            return
        self._pending_preview_generation = self._preview_generation
        self._pending_preview_quality = "final"
        self._preview_token_source.cancel()
        if self._render_running:
            self._render_pending = True
            return
        self._preview_timer.start(0)

    def _build_preview_snapshot(self):
        from app.models.document_serializer import DocumentSerializer

        with self._document_lock:
            return DocumentSerializer.serialize_document_data(self._document)

    def _preview_active_layer_index(self) -> int:
        if self._text_edit_overlay_visible:
            index = int(self._text_edit_layer_index)
            if 0 <= index < len(getattr(self._document, "layers", []) or []):
                return index
        indices = [
            int(index)
            for index in list(getattr(self._document, "selected_layer_indices", []) or [])
            if 0 <= int(index) < len(getattr(self._document, "layers", []) or [])
        ]
        if len(indices) != 1:
            return -1
        layer = self._document.layers[indices[0]]
        return -1 if is_layer_group(layer) else indices[0]

    @Slot()
    def _start_preview_render(self) -> None:
        if self._render_running:
            self._render_pending = True
            return
        quality = self._pending_preview_quality or "interactive"
        # 导出进行中强制降到交互质量：此时有 N 个导出线程在抢 CPU
        # （默认 75% 利用率），再跑一帧全质量预览会两头变慢。
        # 用户此时看的是「导出进度」，画质细节不是重点；
        # 导出结束后的第一次预览会自然回到全质量。
        if bool(getattr(self._document, "_is_batch_export_running", False)):
            quality = "interactive"
        generation = self._pending_preview_generation or self._preview_generation
        self._pending_preview_quality = None
        self._pending_preview_generation = generation
        snapshot_data = None
        if bool(getattr(self._document, "_is_batch_export_running", False)):
            try:
                snapshot_data = self._build_preview_snapshot()
            except Exception as error:
                self._set_status(f"预览快照失败：{error}", toast=True)
                return
        self._render_running = True
        self._render_pending = False
        self._render_request_id += 1
        token = self._preview_token_source.next()
        task = _PreviewTask(
            self._render_request_id,
            generation,
            self._document,
            snapshot_data=snapshot_data,
            interactive_low_quality=quality == "interactive",
            active_layer_index=self._preview_active_layer_index(),
            omit_active_layer=self._text_edit_overlay_visible,
            cancel_token=token,
        )
        task.signals.finished.connect(self._on_preview_rendered)
        self._active_render_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(int, int, bool, object, str, float)
    def _on_preview_rendered(
        self,
        request_id: int,
        generation: int,
        interactive_low_quality: bool,
        qimage,
        error: str,
        elapsed: float,
    ) -> None:
        self._render_running = False
        self._active_render_task = None
        # 判定标准是「这份结果比手上这帧新」，而不是「它就是当前最新版本」。
        # 旧实现用 generation == self._preview_generation：拖动时每帧
        # requestPreview 都会把 _preview_generation 推进，渲染回来时
        # generation 必然落后，于是每一帧结果都被丢弃，画面停住不动，
        # 只有彻底停手后那一次才被接受 —— 用户感知就是拖不动、卡顿。
        # 用 request_id 保证不是过期请求（同一次启动里 id 唯一且递增），
        # 用 generation 单调递增保证不拿旧的覆盖新的。
        current_result = (
            request_id == self._render_request_id
            and generation >= self._accepted_preview_generation
        )
        if current_result and qimage is not None and not qimage.isNull():
            self._accepted_preview_generation = generation
            self._preview_provider.set_image(qimage)
            self._preview_revision += 1
            self.previewChanged.emit()
            if not interactive_low_quality:
                self._set_status(f"预览完成 · {elapsed * 1000:.0f} ms")
        elif current_result and error:
            self._set_status(f"预览失败：{error}", toast=True)
        if self._render_pending:
            self._render_pending = False
            self._preview_timer.start(0)

    def _render_preview_sync(self) -> bool:
        from app.services.preview_render_service import render_preview_to_image

        self._set_busy(True)
        try:
            with self._document_lock:
                result = render_preview_to_image(
                    self._document,
                    force_refresh=True,
                    active_layer_index=self._preview_active_layer_index(),
                    omit_active_layer=self._text_edit_overlay_visible,
                )
            if result.image is None:
                self._set_status(f"预览失败：{result.error or '渲染器未返回图像'}", toast=True)
                return False
            qimage = _pil_to_qimage(result.image)
            self._preview_provider.set_image(qimage)
            self._preview_revision += 1
            self.previewChanged.emit()
            self._set_status(f"预览完成 · {result.elapsed * 1000:.0f} ms")
            return True
        except Exception as error:
            self._set_status(f"预览失败：{error}", toast=True)
            return False
        finally:
            self._set_busy(False)
