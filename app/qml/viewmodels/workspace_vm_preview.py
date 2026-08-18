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
        current_result = (
            request_id == self._render_request_id
            and generation == self._preview_generation
        )
        if current_result and qimage is not None and not qimage.isNull():
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
