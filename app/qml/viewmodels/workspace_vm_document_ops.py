"""WorkspaceViewModel 文档生命周期与图层创建方法组 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的文档新建/打开/保存/导出与图层创建方法组
（36 个方法），语义不变。依赖主类实例方法（``_set_document``、``_layer_model``、
``_set_status`` 等）与下列模块级名字。
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl, Slot

from app.constants import DEFAULT_TEXT_FONT_FAMILY
from app.models.document import Document
from app.models.shaped_layer_new import ShapedLayer
from app.utils.text_style_ranges import remap_text_style_ranges

from .workspace_vm_shared import _SHAPE_TYPES, _TEXT_ALIGNMENTS


class WorkspaceDocumentOpsMixin:
    @Slot(bool)
    def setExportRunning(self, running: bool) -> None:
        running = bool(running)
        if running != self._export_running:
            self._export_running = running
            self.exportStateChanged.emit()

    def _ensure_operations_available(self) -> bool:
        if not self._export_running:
            return True
        self._set_status("批量导出期间无法修改或切换文档", toast=True)
        return False

    def _set_busy(self, busy: bool) -> None:
        busy = bool(busy)
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit()

    def _set_status(self, message: str, *, toast: bool = False) -> None:
        self._status_message = str(message)
        self.statusChanged.emit()
        if toast:
            self.toastRequested.emit(self._status_message)

    def _set_document(self, document: Document) -> None:
        with self._document_lock:
            if self._crop_edit_original is not None and self._document is not None:
                old_layer = self._layer_model.layer_at(self._crop_edit_index)
                if old_layer is not None:
                    old_layer.crop_rect = list(self._crop_edit_original)
                self._document.is_modified = self._crop_edit_was_modified
            self._crop_edit_index = -1
            self._crop_edit_original = None
            self._selected_vector_node_index = -1
            self._selection_anchor_index = -1
            self._corner_edit_modes.clear()
            self._disconnect_document()
            self._document = document
            self._layer_model.set_document(document)
            self._connect_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.cropEditChanged.emit()
        self.vectorEditChanged.emit()
        self.viewSettingsChanged.emit()
        self.documentObjectChanged.emit(document)

    @Slot(object, result=bool)
    def activateDocument(self, document) -> bool:
        if not self._ensure_operations_available():
            return False
        if not isinstance(document, Document):
            self._set_status("无法切换到无效文档", toast=True)
            return False
        if document is self._document:
            return True

        self._preview_timer.stop()
        self._render_request_id += 1
        self._render_pending = False
        self._preview_provider.clear()
        self._preview_revision += 1
        self._set_document(document)
        self.previewChanged.emit()
        self._set_status(f"已切换到 {self.documentTitle}")
        self.requestPreview(force=True)
        return True

    def _connect_document(self) -> None:
        if self._document is None:
            return
        self._document.document_changed.connect(self._on_document_changed)
        self._document.layer_selected.connect(self._on_layer_selected)
        self._document.layers_selection_changed.connect(self._on_layers_selected)
        self._document.history_changed.connect(self.historyStateChanged.emit)

    def _disconnect_document(self) -> None:
        if self._document is None:
            return
        connections = (
            (self._document.document_changed, self._on_document_changed),
            (self._document.layer_selected, self._on_layer_selected),
            (self._document.layers_selection_changed, self._on_layers_selected),
            (self._document.history_changed, self.historyStateChanged.emit),
        )
        for signal, slot in connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    @Slot()
    def _on_document_changed(self) -> None:
        self.documentInfoChanged.emit()
        if self._suppress_document_selection_notify <= 0:
            self.selectionChanged.emit()

    @Slot(int)
    def _on_layer_selected(self, index: int) -> None:
        del index
        self.selectionChanged.emit()

    @Slot(list)
    def _on_layers_selected(self, indices) -> None:
        del indices
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()

    @staticmethod
    def _local_path(path_or_url: str) -> str:
        text = str(path_or_url or "")
        url = QUrl(text)
        if url.isLocalFile():
            return url.toLocalFile()
        return text

    @staticmethod
    def _image_files(directory: str):
        if not directory or not os.path.isdir(directory):
            return []
        extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
        try:
            return sorted(
                str(path)
                for path in Path(directory).iterdir()
                if path.is_file() and path.suffix.lower() in extensions
            )
        except OSError:
            return []

    @staticmethod
    def _clear_image_layer_cache(layer) -> None:
        for attr in ("_cached_image", "_cached_image_path", "_cached_source_image", "_cached_source_path"):
            if hasattr(layer, attr):
                setattr(layer, attr, None)
        if hasattr(layer, "cached_image"):
            layer.cached_image = None

    def _publish_content_change(self, index: int, status: str) -> None:
        self._layer_model.notify_row(index)
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(status, toast=True)

    def _validated_image_source(self, source_path: str):
        source_path = self._local_path(source_path)
        if os.path.isdir(source_path):
            files = self._image_files(source_path)
            if not files:
                self._set_status("素材文件夹没有可用图片", toast=True)
                return None
            return source_path, True, files[0], files
        if os.path.isfile(source_path):
            try:
                from PIL import Image

                with Image.open(source_path) as image:
                    image.verify()
            except Exception:
                self._set_status("所选文件不是可读取的图片", toast=True)
                return None
            return source_path, False, source_path, [source_path]
        self._set_status("图片源不存在或无法访问", toast=True)
        return None

    def _add_image_source(self, source_path: str, *, require_folder: bool) -> bool:
        if not self._ensure_operations_available():
            return False
        validated = self._validated_image_source(source_path)
        if validated is None:
            return False
        source_path, is_folder, preview_path, files = validated
        if require_folder and not is_folder:
            self._set_status("请选择素材文件夹", toast=True)
            return False
        if not require_folder and is_folder:
            self._set_status("请选择单张图片文件", toast=True)
            return False

        try:
            from PIL import Image

            with Image.open(preview_path) as image:
                source_width, source_height = image.size
            if source_width <= 0 or source_height <= 0:
                raise ValueError("图片尺寸无效")

            max_width = max(1, round(self.canvasWidth * 0.6))
            max_height = max(1, round(self.canvasHeight * 0.6))
            scale = min(max_width / source_width, max_height / source_height, 1.0)
            width = max(1, round(source_width * scale))
            height = max(1, round(source_height * scale))
            x = (self.canvasWidth - width) // 2
            y = (self.canvasHeight - height) // 2

            with self._document_lock:
                self._ensure_history_baseline()
                layer = self._document.add_layer(
                    os.path.basename(source_path),
                    x,
                    y,
                    width,
                    height,
                    image_source=source_path,
                    use_original_size=False,
                    is_folder=is_folder,
                )
                layer.current_image_path = preview_path
                self._clear_image_layer_cache(layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加图片源失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        if is_folder:
            self._set_status(f"已添加素材文件夹 · {len(files)} 张", toast=True)
        else:
            self._set_status(f"已添加图片 {os.path.basename(source_path)}", toast=True)
        return True

    @Slot(int, int, result=bool)
    def newDocument(self, width: int = 1080, height: int = 1350) -> bool:
        if not self._ensure_operations_available():
            return False
        if width <= 0 or height <= 0:
            self._set_status("新建失败：画布尺寸无效", toast=True)
            return False
        document = Document()
        document.create_new(int(width), int(height))
        document._history_manager.clear()
        document.save_state("初始状态")
        self._preview_provider.clear()
        self._preview_revision += 1
        self._set_document(document)
        self.previewChanged.emit()
        self._set_status("已新建空白文档", toast=True)
        self.requestPreview(force=True)
        return True

    @Slot(str, result=bool)
    def createDemoDocument(self, image_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        image_path = self._local_path(image_path)
        if not os.path.isfile(image_path):
            self._set_status("示例文档创建失败：素材不存在", toast=True)
            return False
        from app.models.text_layer import TextLayer

        document = Document()
        document.create_new(1080, 1350)
        document.add_layer(
            "产品底图",
            0,
            0,
            1080,
            1350,
            image_source=image_path,
            use_original_size=False,
            is_folder=False,
        )
        title = TextLayer(name="限量腕表", x=68, y=1040, width=860, height=160)
        title.text_content = "限量腕表"
        title.current_text = "限量腕表"
        title.font_size = 86
        title.text_color = (245, 244, 238, 255)
        title.background_enabled = True
        title.background_color = (17, 24, 22, 238)
        title.background_padding = 24
        title.auto_fit_text_box = False
        document.add_text_layer(title)
        subtitle = TextLayer(name="曜石黑 · 2026", x=76, y=1210, width=680, height=70)
        subtitle.text_content = "曜石黑 · 2026 EDITION"
        subtitle.current_text = "曜石黑 · 2026 EDITION"
        subtitle.font_size = 34
        subtitle.text_color = (70, 215, 173, 255)
        subtitle.auto_fit_text_box = False
        document.add_text_layer(subtitle)
        document.selected_layer_index = 1
        document.selected_layer_indices = [1]
        document.current_file_path = None
        document.is_modified = False
        document._history_manager.clear()
        document.save_state("初始状态")
        self._set_document(document)
        self._set_status("已载入真实模型示例", toast=True)
        self.requestPreview(force=True)
        return True

    @Slot(str, result=bool)
    def openDocument(self, file_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        file_path = self._local_path(file_path)
        candidate = Document()
        if not file_path or not candidate.load_document(file_path):
            self._set_status("打开失败：无法读取项目文件", toast=True)
            return False
        candidate._history_manager.clear()
        candidate.save_state("打开文档")
        self._set_document(candidate)
        self._set_status(f"已打开 {os.path.basename(file_path)}", toast=True)
        self.requestPreview(force=True)
        return True

    @Slot(result=bool)
    def saveDocument(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self.documentPath:
            self._set_status("请先选择项目保存位置", toast=True)
            return False
        return self.saveDocumentTo(self.documentPath)

    @Slot(str, result=bool)
    def saveDocumentTo(self, file_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        file_path = self._local_path(file_path)
        if not file_path:
            self._set_status("保存失败：文件路径为空", toast=True)
            return False
        if not file_path.lower().endswith(".cmp"):
            file_path += ".cmp"
        with self._document_lock:
            success = bool(self._document.save_document(file_path))
        if success:
            self.documentInfoChanged.emit()
            self._set_status(f"已保存 {os.path.basename(file_path)}", toast=True)
        else:
            self._set_status("保存失败：请检查文件路径和权限", toast=True)
        return success

    @Slot(str, result=bool)
    def exportImageTo(self, file_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        file_path = self._local_path(file_path)
        if not file_path:
            self._set_status("导出失败：文件路径为空", toast=True)
            return False
        self._set_busy(True)
        try:
            with self._document_lock:
                success = bool(self._document.export_image(file_path))
        finally:
            self._set_busy(False)
        if success:
            self._set_status(f"已导出 {os.path.basename(file_path)}", toast=True)
        else:
            error = getattr(self._document, "_last_export_error", None) or "未知错误"
            self._set_status(f"导出失败：{error}", toast=True)
        return success

    @Slot(str, result=bool)
    def addImageLayer(self, file_path: str) -> bool:
        return self._add_image_source(file_path, require_folder=False)

    @Slot(result=bool)
    def addEmptyImageLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        try:
            with self._document_lock:
                layer_name = f"图层 {len(self._document.layers) + 1}"
                self._document.add_layer(
                    name=layer_name,
                    x=0,
                    y=0,
                    width=200,
                    height=200,
                    image_source=None,
                    use_original_size=False,
                    is_folder=True,
                )
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加图层失败：{error}", toast=True)
            return False
        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"成功添加图层：{layer_name}", toast=True)
        return True

    @Slot(str, result=bool)
    def addImageFolder(self, folder_path: str) -> bool:
        return self._add_image_source(folder_path, require_folder=True)

    @Slot(str, str, result=bool)
    def addShapedLayer(self, file_path: str, shape_id: str) -> bool:
        if not self._ensure_operations_available():
            return False
        shape_id = str(shape_id or "").strip().lower()
        shape_entry = _SHAPE_TYPES.get(shape_id)
        if shape_entry is None:
            self._set_status("不支持的异形类型", toast=True)
            return False
        validated = self._validated_image_source(file_path)
        if validated is None:
            return False
        source_path, is_folder, preview_path, _files = validated
        if is_folder:
            self._set_status("异形图层创建请选择单张图片", toast=True)
            return False

        try:
            from PIL import Image

            with Image.open(preview_path) as image:
                source_width, source_height = image.size
            if source_width <= 0 or source_height <= 0:
                raise ValueError("图片尺寸无效")
            max_width = max(1, round(self.canvasWidth * 0.6))
            max_height = max(1, round(self.canvasHeight * 0.6))
            scale = min(max_width / source_width, max_height / source_height, 1.0)
            width = max(1, round(source_width * scale))
            height = max(1, round(source_height * scale))
            x = (self.canvasWidth - width) // 2
            y = (self.canvasHeight - height) // 2
            layer = ShapedLayer(
                name=f"{shape_entry[1]} · {os.path.basename(source_path)}",
                x=x,
                y=y,
                width=width,
                height=height,
                image_source=source_path,
                use_original_size=False,
                is_folder=False,
                current_image_path=preview_path,
                shape_type=shape_entry[0],
            )
            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_shaped_layer(layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加异形图层失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"已添加{shape_entry[1]}异形图层", toast=True)
        return True

    @Slot("QVariantMap", result=bool)
    def addConfiguredShapedLayer(self, config) -> bool:
        if not self._ensure_operations_available():
            return False
        config = dict(config or {})
        name = str(config.get("name", "") or "").strip()[:120]
        shape_id = str(config.get("shapeType", "rectangle") or "rectangle").strip().lower()
        shape_entry = _SHAPE_TYPES.get(shape_id)
        if not name:
            self._set_status("图层名称不能为空", toast=True)
            return False
        if shape_entry is None:
            self._set_status("不支持的异形类型", toast=True)
            return False
        try:
            x = int(float(config.get("x", 0)))
            y = int(float(config.get("y", 0)))
            width = int(float(config.get("width", 200)))
            height = int(float(config.get("height", 200)))
        except (TypeError, ValueError):
            self._set_status("异形图层的位置或尺寸无效", toast=True)
            return False
        if not 10 <= width <= 32768 or not 10 <= height <= 32768:
            self._set_status("异形图层尺寸必须在 10 到 32768 像素之间", toast=True)
            return False

        source = str(config.get("source", "") or "").strip()
        source_is_folder = bool(config.get("sourceIsFolder", True))
        source_path = None
        current_image_path = None
        if source:
            validated = self._validated_image_source(source)
            if validated is None:
                return False
            source_path, actual_is_folder, current_image_path, _files = validated
            if actual_is_folder != source_is_folder:
                expected = "素材文件夹" if source_is_folder else "单张图片"
                self._set_status(f"当前内容源模式需要选择{expected}", toast=True)
                return False
            source_is_folder = actual_is_folder

        try:
            layer = ShapedLayer(
                name=name,
                x=x,
                y=y,
                width=width,
                height=height,
                image_source=source_path,
                use_original_size=bool(config.get("useOriginalSize", False)) and not source_is_folder,
                is_folder=source_is_folder,
                current_image_path=current_image_path,
                shape_type=shape_entry[0],
            )
            if shape_id == "right_trapezoid":
                top_ratio = max(30, min(100, int(float(config.get("trapezoidTopRatio", 100)))))
                bottom_ratio = max(30, min(100, int(float(config.get("trapezoidBottomRatio", 80)))))
                slope_side = str(config.get("trapezoidSlopeSide", "right") or "right").lower()
                layer.trapezoid_top_width = round(width * top_ratio / 100)
                layer.trapezoid_bottom_width = round(width * bottom_ratio / 100)
                layer.trapezoid_slope_side = slope_side if slope_side in ("left", "right") else "right"
            elif shape_id in ("pentagon", "hexagon"):
                layer.polygon_rotation = float(config.get("polygonRotation", 0)) % 360.0
                layer.polygon_corner_radius = max(0, int(float(config.get("polygonCornerRadius", 0))))

            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_shaped_layer(layer)
                self._document.is_modified = True
        except (TypeError, ValueError) as error:
            self._set_status(f"异形图层参数无效：{error}", toast=True)
            return False
        except Exception as error:
            self._set_status(f"添加异形图层失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"已添加{shape_entry[1]}异形图层", toast=True)
        return True

    @Slot(str, result=bool)
    def setSelectedImageSource(self, source_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if not self.selectedHasImageSource or layer is None:
            self._set_status("当前图层没有图片内容源", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        validated = self._validated_image_source(source_path)
        if validated is None:
            return False
        source_path, is_folder, preview_path, files = validated
        index = self.selectedLayerIndex

        with self._document_lock:
            self._ensure_history_baseline()
            layer.image_source = source_path
            layer.is_folder = is_folder
            layer.current_image_path = preview_path
            self._clear_image_layer_cache(layer)
            self._document.is_modified = True
            self._document.bump_hit_test_version()
            self._document._invalidate_render_cache()
            self._document.save_state("更改图片内容源")

        description = f"素材文件夹 · {len(files)} 张" if is_folder else os.path.basename(source_path)
        self._publish_content_change(index, f"已更新图片源 · {description}")
        return True

    @Slot(result=bool)
    def showNextSelectedImage(self) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if not self.selectedImageSourceIsFolder or layer is None:
            self._set_status("当前图片源不是素材文件夹", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        files = self._image_files(self.selectedImageSource)
        if not files:
            self._set_status("素材文件夹没有可用图片", toast=True)
            return False
        current = os.path.normcase(str(getattr(layer, "current_image_path", "") or ""))
        normalized = [os.path.normcase(path) for path in files]
        next_index = (normalized.index(current) + 1) % len(files) if current in normalized else 0
        preview_path = files[next_index]
        index = self.selectedLayerIndex

        with self._document_lock:
            self._ensure_history_baseline()
            layer.current_image_path = preview_path
            self._clear_image_layer_cache(layer)
            self._document.is_modified = True
            self._document._invalidate_render_cache()
            self._document.save_state("切换素材预览")

        self._publish_content_change(index, f"当前素材 · {os.path.basename(preview_path)}")
        return True

    @Slot(result=bool)
    def addTextLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        from app.models.text_layer import TextLayer

        width = max(120, min(round(self.canvasWidth * 0.6), 600))
        height = max(64, min(round(self.canvasHeight * 0.12), 180))
        x = (self.canvasWidth - width) // 2
        y = (self.canvasHeight - height) // 2
        text_layer = TextLayer(name="新建文字", x=x, y=y, width=width, height=height)
        text_layer.current_text = "新建文字"
        text_layer.font_size = max(24, min(round(height * 0.45), 72))
        text_layer.auto_fit_text_box = False

        try:
            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_text_layer(text_layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加文字失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已添加文字图层", toast=True)
        return True

    @Slot(result=bool)
    def addQuickTextLayer(self) -> bool:
        """一键建文字图层 —— 旧版「快速文字图层（T）」的对等实现。

        旧版 `layer_controller.add_quick_text_layer()` 的规则照搬：

          - 内容「双击编辑文字」、白色、左对齐、参与绑定
          - 字号 = **画布高 / 12**，夹在 [24, 160]
            （600 高→50px、1080 高→90px；固定 48px 在 1080 上只占宽 16%，太小）
          - 位置 = 画布 **6% 留白**（固定 50,50 在大画布上会挤在左上角）
          - 图层名按内容首行生成并**去重**（连按 T 能区分「双击编辑文字 2/3」）
          - `auto_fit_text_box = True`，否则大字号会被固定 300x100 的框裁掉

        不能直接复用 `addTextLayer()`：那个是测试与内部用的居中建层，内容和
        字号规则都不同，用户按 T 出来的层会跟旧版「长得不一样」。
        """
        if not self._ensure_operations_available():
            return False
        from app.constants import DEFAULT_TEXT_FONT_FAMILY
        from app.models.text_layer import TextLayer

        canvas_width = float(self.canvasWidth)
        canvas_height = float(self.canvasHeight)
        font_size = 48
        if canvas_height > 0:
            font_size = max(24, min(160, round(canvas_height / 12)))
        x = round(canvas_width * 0.06) if canvas_width > 0 else 50
        y = round(canvas_height * 0.06) if canvas_height > 0 else 50

        content = "双击编辑文字"
        base_name = content
        existing = {
            str(getattr(layer, "name", "") or "") for layer in self._document.layers
        }
        name = base_name
        suffix = 2
        while name in existing:
            name = f"{base_name} {suffix}"
            suffix += 1

        try:
            text_layer = TextLayer(name=name, x=int(x), y=int(y), width=300, height=100)
            text_layer.auto_fit_text_box = True
            text_layer.text_binding_enabled = True
            text_layer.font_family = DEFAULT_TEXT_FONT_FAMILY
            text_layer.font_size = font_size
            text_layer.text_color = self._parse_hex_color("#FFFFFF")
            text_layer.text_align = _TEXT_ALIGNMENTS["left"][0]
            lines = text_layer.parse_text_input_to_lines(content)
            text_layer.set_text_lines(lines)
            text_layer.set_current_text(lines[0], force=True)

            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_text_layer(text_layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加文字失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已添加文字图层，可在右侧属性面板调整", toast=True)
        return True

    @Slot("QVariantMap", result=bool)
    def addConfiguredTextLayer(self, config) -> bool:
        if not self._ensure_operations_available():
            return False
        from app.models.text_layer import TextLayer

        config = dict(config or {})
        name = str(config.get("name", "") or "").strip()[:120]
        content = str(config.get("content", "") or "")
        font_family = str(config.get("fontFamily", DEFAULT_TEXT_FONT_FAMILY) or "").strip()
        alignment = str(config.get("alignment", "left") or "left").strip().lower()
        color = self._parse_hex_color(str(config.get("color", "#000000") or "#000000"))
        try:
            font_size = int(float(config.get("fontSize", 24)))
        except (TypeError, ValueError):
            font_size = 0

        if not name:
            self._set_status("图层名称不能为空", toast=True)
            return False
        if not content.strip():
            self._set_status("文字内容不能为空", toast=True)
            return False
        if not font_family:
            self._set_status("字体名称不能为空", toast=True)
            return False
        if not 6 <= font_size <= 240:
            self._set_status("字号必须在 6 到 240 像素之间", toast=True)
            return False
        if alignment not in _TEXT_ALIGNMENTS:
            self._set_status("不支持的文字对齐方式", toast=True)
            return False
        if color is None:
            self._set_status("文字颜色格式无效", toast=True)
            return False

        try:
            text_layer = TextLayer(name=name, x=50, y=50, width=300, height=100)
            # 自动适配边框必须开启（2026-10-28 修）。
            #
            # 旧版 layer_controller.add_configured_text_layer 里对这一行有明确注释：
            # 关掉时文本框固定 300x100，大字号会被直接裁掉 ——
            # 实测 72px 的「限时特惠 5折」只渲染出「限时特惠」，「5折」整段丢失。
            # QML 侧当时写成了 False，正是同一个坑。
            text_layer.auto_fit_text_box = True
            text_layer.text_binding_enabled = bool(config.get("bindingEnabled", True))
            text_layer.font_family = font_family
            text_layer.font_face = str(config.get("fontFace", "") or "").strip()
            text_layer.font_size = font_size
            text_layer.text_color = color
            text_layer.text_align = _TEXT_ALIGNMENTS[alignment][0]
            lines = text_layer.parse_text_input_to_lines(content)
            text_layer.set_text_lines(lines)
            text_layer.set_current_text(lines[0], force=True)

            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_text_layer(text_layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加文字失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已添加文字图层", toast=True)
        return True

    def _change_text_layer(self, index: int, action: str, mutator, status: str) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._layer_model.layer_at(int(index))
        if layer is None or self._layer_model.layer_type_name(layer) != "文字":
            self._set_status("当前图层不是文字图层", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            mutator(layer)
            self._document.is_modified = True
            self._document.bump_hit_test_version()
            self._document._invalidate_render_cache()
            self._document.save_state(action)
        self._publish_content_change(index, status)
        return True

    def _change_selected_text(self, action: str, mutator, status: str) -> bool:
        return self._change_text_layer(self.selectedLayerIndex, action, mutator, status)

    @Slot(int, str, result=bool)
    def setTextContentForLayer(self, index: int, content: str) -> bool:
        content = str(content or "")

        def apply(layer) -> None:
            old_text = str(getattr(layer, "current_text", "") or "")
            old_colors = layer.get_text_color_ranges()
            old_sizes = layer.get_font_size_ranges()
            lines = layer.parse_text_input_to_lines(content)
            new_text = str(lines[0] if lines else "")
            colors, sizes = remap_text_style_ranges(
                old_text,
                new_text,
                old_colors,
                old_sizes,
            )
            layer.set_text_lines(lines)
            layer.set_current_text(new_text, force=True)
            layer.replace_text_style_ranges(colors, sizes)

        return self._change_text_layer(
            int(index),
            "修改文字内容",
            apply,
            "文字内容已更新",
        )
