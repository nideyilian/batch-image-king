from __future__ import annotations

import math
import os
from pathlib import Path
import re
import threading
from typing import Optional
import uuid

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QImage

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.layer_list_model import LayerListModel


def _pil_to_qimage(image) -> QImage:
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format_RGBA8888,
    ).copy()


class _PreviewTaskSignals(QObject):
    finished = Signal(int, object, str, float)


class _PreviewTask(QRunnable):
    def __init__(self, request_id: int, document: Document, document_lock: threading.RLock) -> None:
        super().__init__()
        self.request_id = request_id
        self.document = document
        self.document_lock = document_lock
        self.signals = _PreviewTaskSignals()

    def run(self) -> None:
        from app.services.preview_render_service import render_preview_to_image

        try:
            with self.document_lock:
                result = render_preview_to_image(self.document, force_refresh=True)
            qimage = _pil_to_qimage(result.image) if result.image is not None else None
            self.signals.finished.emit(
                self.request_id,
                qimage,
                str(result.error or ""),
                float(result.elapsed),
            )
        except Exception as error:
            self.signals.finished.emit(self.request_id, None, str(error), 0.0)


class WorkspaceViewModel(QObject):
    documentObjectChanged = Signal(object)
    documentInfoChanged = Signal()
    selectionChanged = Signal()
    previewChanged = Signal()
    statusChanged = Signal()
    busyChanged = Signal()
    historyStateChanged = Signal()
    exportStateChanged = Signal()
    toastRequested = Signal(str)

    def __init__(
        self,
        document: Optional[Document] = None,
        preview_provider: Optional[PreviewImageProvider] = None,
        *,
        auto_render: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._document: Optional[Document] = None
        self._preview_provider = preview_provider or PreviewImageProvider()
        self._layer_model = LayerListModel(parent=self)
        self._preview_revision = 0
        self._status_message = "就绪"
        self._busy = False
        self._export_running = False
        self._auto_render = bool(auto_render)
        self._document_lock = threading.RLock()
        self._render_request_id = 0
        self._render_running = False
        self._render_pending = False
        self._active_render_task = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(70)
        self._preview_timer.timeout.connect(self._start_preview_render)
        self._set_document(document or Document())
        if self._auto_render:
            self.requestPreview()

    @property
    def document(self) -> Document:
        return self._document

    @property
    def documentLock(self) -> threading.RLock:
        return self._document_lock

    @Property(QObject, constant=True)
    def layerModel(self):
        return self._layer_model

    @Property(str, notify=documentInfoChanged)
    def documentTitle(self) -> str:
        path = getattr(self._document, "current_file_path", None)
        return os.path.basename(path) if path else "未命名项目.cmp"

    @Property(str, notify=documentInfoChanged)
    def documentPath(self) -> str:
        return str(getattr(self._document, "current_file_path", None) or "")

    @Property(bool, notify=documentInfoChanged)
    def hasFilePath(self) -> bool:
        return bool(self.documentPath)

    @Property(bool, notify=documentInfoChanged)
    def isModified(self) -> bool:
        return bool(getattr(self._document, "is_modified", False))

    @Property(int, notify=documentInfoChanged)
    def canvasWidth(self) -> int:
        return int(getattr(self._document, "canvas_width", 0))

    @Property(int, notify=documentInfoChanged)
    def canvasHeight(self) -> int:
        return int(getattr(self._document, "canvas_height", 0))

    @Property(int, notify=selectionChanged)
    def selectedLayerIndex(self) -> int:
        return int(getattr(self._document, "selected_layer_index", -1))

    def _selected_layer(self):
        return self._layer_model.layer_at(self.selectedLayerIndex)

    @Property(str, notify=selectionChanged)
    def selectedLayerName(self) -> str:
        layer = self._selected_layer()
        return str(getattr(layer, "name", "未选择图层"))

    @Property(str, notify=selectionChanged)
    def selectedLayerType(self) -> str:
        layer = self._selected_layer()
        return self._layer_model.layer_type_name(layer) if layer is not None else ""

    @Property(int, notify=selectionChanged)
    def selectedX(self) -> int:
        return int(getattr(self._selected_layer(), "x", 0))

    @Property(int, notify=selectionChanged)
    def selectedY(self) -> int:
        return int(getattr(self._selected_layer(), "y", 0))

    @Property(int, notify=selectionChanged)
    def selectedWidth(self) -> int:
        return int(getattr(self._selected_layer(), "width", 0))

    @Property(int, notify=selectionChanged)
    def selectedHeight(self) -> int:
        return int(getattr(self._selected_layer(), "height", 0))

    @Property(int, notify=selectionChanged)
    def selectedOpacity(self) -> int:
        return round(float(getattr(self._selected_layer(), "opacity", 1.0)) * 100)

    @Property(bool, notify=selectionChanged)
    def selectedVisible(self) -> bool:
        return bool(getattr(self._selected_layer(), "visible", False))

    @Property(bool, notify=selectionChanged)
    def selectedLocked(self) -> bool:
        return bool(getattr(self._selected_layer(), "locked", False))

    @Property(float, notify=selectionChanged)
    def selectedRotation(self) -> float:
        layer = self._selected_layer()
        return float(getattr(layer, "rotation", 0.0) or 0.0)

    @Property(bool, notify=selectionChanged)
    def selectedCanRotate(self) -> bool:
        layer = self._selected_layer()
        return layer is not None and hasattr(layer, "rotation")

    @Property(bool, notify=selectionChanged)
    def selectedIsImageLayer(self) -> bool:
        return self.selectedLayerType == "图片"

    @Property(bool, notify=selectionChanged)
    def selectedIsTextLayer(self) -> bool:
        return self.selectedLayerType == "文字"

    @Property(str, notify=selectionChanged)
    def selectedImageSource(self) -> str:
        if not self.selectedIsImageLayer:
            return ""
        return str(getattr(self._selected_layer(), "image_source", "") or "")

    @Property(bool, notify=selectionChanged)
    def selectedImageSourceIsFolder(self) -> bool:
        return self.selectedIsImageLayer and bool(getattr(self._selected_layer(), "is_folder", False))

    @Property(int, notify=selectionChanged)
    def selectedImageSourceCount(self) -> int:
        if not self.selectedImageSourceIsFolder:
            return 1 if self.selectedImageSource else 0
        return len(self._image_files(self.selectedImageSource))

    @Property(str, notify=selectionChanged)
    def selectedImageCurrentFile(self) -> str:
        if not self.selectedIsImageLayer:
            return ""
        layer = self._selected_layer()
        path = getattr(layer, "current_image_path", None) or getattr(layer, "image_source", None)
        return os.path.basename(str(path)) if path else ""

    @Property(str, notify=selectionChanged)
    def selectedTextContent(self) -> str:
        if not self.selectedIsTextLayer:
            return ""
        return str(getattr(self._selected_layer(), "text_content", "") or "")

    @Property(bool, notify=selectionChanged)
    def selectedTextBindingEnabled(self) -> bool:
        return self.selectedIsTextLayer and bool(
            getattr(self._selected_layer(), "text_binding_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedTextCandidateCount(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        layer = self._selected_layer()
        if self.selectedTextBindingEnabled:
            return len(layer.get_text_lines())
        return 1 if self.selectedTextContent else 0

    @Property(int, notify=selectionChanged)
    def selectedTextFontSize(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        return int(getattr(self._selected_layer(), "font_size", 0) or 0)

    @Property(bool, notify=selectionChanged)
    def canDuplicateLayer(self) -> bool:
        layer = self._selected_layer()
        return bool(
            layer is not None
            and not self._export_running
            and not bool(getattr(layer, "locked", False))
            and callable(getattr(layer, "duplicate", None))
        )

    @Property(bool, notify=selectionChanged)
    def canMoveLayerForward(self) -> bool:
        index = self.selectedLayerIndex
        layer = self._selected_layer()
        neighbor = self._layer_model.layer_at(index + 1)
        return bool(
            layer is not None
            and neighbor is not None
            and not self._export_running
            and not bool(getattr(layer, "locked", False))
            and not bool(getattr(neighbor, "locked", False))
        )

    @Property(bool, notify=selectionChanged)
    def canMoveLayerBackward(self) -> bool:
        index = self.selectedLayerIndex
        layer = self._selected_layer()
        neighbor = self._layer_model.layer_at(index - 1)
        return bool(
            layer is not None
            and neighbor is not None
            and not self._export_running
            and not bool(getattr(layer, "locked", False))
            and not bool(getattr(neighbor, "locked", False))
        )

    @Property(int, notify=previewChanged)
    def previewRevision(self) -> int:
        return self._preview_revision

    @Property(str, notify=previewChanged)
    def previewSource(self) -> str:
        return f"image://documentPreview/current?revision={self._preview_revision}"

    @Property(str, notify=statusChanged)
    def statusMessage(self) -> str:
        return self._status_message

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=historyStateChanged)
    def canUndo(self) -> bool:
        return bool(self._document and self._document.can_undo())

    @Property(bool, notify=historyStateChanged)
    def canRedo(self) -> bool:
        return bool(self._document and self._document.can_redo())

    @Property(bool, notify=exportStateChanged)
    def exportRunning(self) -> bool:
        return self._export_running

    @Property(bool, notify=exportStateChanged)
    def operationsBlocked(self) -> bool:
        return self._export_running

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
            self._disconnect_document()
            self._document = document
            self._layer_model.set_document(document)
            self._connect_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.documentObjectChanged.emit(document)

    def _connect_document(self) -> None:
        if self._document is None:
            return
        self._document.document_changed.connect(self._on_document_changed)
        self._document.layer_selected.connect(self._on_layer_selected)
        self._document.history_changed.connect(self.historyStateChanged.emit)

    def _disconnect_document(self) -> None:
        if self._document is None:
            return
        connections = (
            (self._document.document_changed, self._on_document_changed),
            (self._document.layer_selected, self._on_layer_selected),
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
        self.selectionChanged.emit()

    @Slot(int)
    def _on_layer_selected(self, index: int) -> None:
        del index
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
        extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}
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

    @Slot(str, result=bool)
    def addImageFolder(self, folder_path: str) -> bool:
        return self._add_image_source(folder_path, require_folder=True)

    @Slot(str, result=bool)
    def setSelectedImageSource(self, source_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if not self.selectedIsImageLayer or layer is None:
            self._set_status("当前图层不是图片图层", toast=True)
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
            lines = layer.parse_text_input_to_lines(content)
            layer.set_text_lines(lines)
            layer.set_current_text(lines[0] if lines else "", force=True)

        return self._change_text_layer(
            int(index),
            "修改文字内容",
            apply,
            "文字内容已更新",
        )

    @Slot(str, result=bool)
    def setSelectedTextContent(self, content: str) -> bool:
        return self.setTextContentForLayer(self.selectedLayerIndex, content)

    @Slot(bool, result=bool)
    def setSelectedTextBindingEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)

        def apply(layer) -> None:
            layer.text_binding_enabled = enabled
            lines = layer.get_text_lines()
            layer.set_current_text(lines[0] if lines else "", force=True)

        mode = "按行随机" if enabled else "整段排版"
        return self._change_selected_text("切换文字内容模式", apply, f"文字模式 · {mode}")

    @Slot(int, result=bool)
    def setSelectedTextFontSize(self, value: int) -> bool:
        value = int(value)
        if not 1 <= value <= 1000:
            self._set_status("字号必须在 1 到 1000 之间", toast=True)
            return False
        return self._change_selected_text(
            "修改文字字号",
            lambda layer: setattr(layer, "font_size", value),
            f"文字字号 · {value} px",
        )

    @Slot(result=bool)
    def deleteSelectedLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        index = self.selectedLayerIndex
        layer = self._layer_model.layer_at(index)
        if layer is None:
            self._set_status("没有可删除的图层", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定，无法删除", toast=True)
            return False

        try:
            with self._document_lock:
                before_count = len(self._document.layers)
                self._ensure_history_baseline()
                self._document.remove_layer(index)
                if len(self._document.layers) == before_count:
                    return False
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"删除图层失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已删除图层", toast=True)
        return True

    def _duplicate_layer_name(self, original_name: str) -> str:
        original_name = str(original_name or "未命名图层")
        match = re.match(r"^(.*?)(?: 副本(?: \d+)?)?$", original_name)
        base_name = (match.group(1) if match else original_name).strip() or "未命名图层"
        existing_names = {str(getattr(layer, "name", "")) for layer in self._document.layers}
        candidate = f"{base_name} 副本"
        if candidate not in existing_names:
            return candidate
        number = 2
        while f"{base_name} 副本 {number}" in existing_names:
            number += 1
        return f"{base_name} 副本 {number}"

    @Slot(result=bool)
    def duplicateSelectedLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self.canDuplicateLayer:
            self._set_status("当前图层无法复制", toast=True)
            return False
        index = self.selectedLayerIndex
        original = self._selected_layer()

        try:
            with self._document_lock:
                self._ensure_history_baseline()
                try:
                    duplicate = original.duplicate(parent=self._document)
                except TypeError:
                    duplicate = original.duplicate()
                if duplicate is None:
                    raise RuntimeError("图层复制失败")

                if hasattr(duplicate, "_layer_id"):
                    duplicate._layer_id = str(uuid.uuid4())
                duplicate.name = self._duplicate_layer_name(getattr(original, "name", ""))

                if hasattr(duplicate, "x") and hasattr(duplicate, "width"):
                    max_x = max(0, self.canvasWidth - int(getattr(duplicate, "width", 0) or 0))
                    duplicate.x = min(max_x, max(0, int(getattr(original, "x", 0) or 0) + 12))
                if hasattr(duplicate, "y") and hasattr(duplicate, "height"):
                    max_y = max(0, self.canvasHeight - int(getattr(duplicate, "height", 0) or 0))
                    duplicate.y = min(max_y, max(0, int(getattr(original, "y", 0) or 0) + 12))

                changed_signal = getattr(duplicate, "changed", None)
                if changed_signal is not None:
                    changed_signal.connect(self._document.document_changed.emit)

                insert_index = index + 1
                self._document.layers.insert(insert_index, duplicate)
                self._document.selected_layer_index = insert_index
                self._document.selected_layer_indices = [insert_index]
                self._document.is_modified = True
                self._document._invalidate_render_cache()
                self._document.bump_hit_test_version()
                self._document.layer_changed.emit()
                self._document.layer_selected.emit(insert_index)
                self._document.layers_selection_changed.emit([insert_index])
                self._document.document_changed.emit()
                self._document.save_state("复制图层")
        except Exception as error:
            self._set_status(f"复制图层失败：{error}", toast=True)
            return False

        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"已创建 {duplicate.name}", toast=True)
        return True

    @Slot(str, result=bool)
    def moveSelectedLayer(self, direction: str) -> bool:
        if not self._ensure_operations_available():
            return False
        direction = str(direction or "").lower()
        allowed = self.canMoveLayerForward if direction == "forward" else self.canMoveLayerBackward
        if direction not in {"forward", "backward"} or not allowed:
            self._set_status("图层已在边界或相邻图层已锁定", toast=True)
            return False
        index = self.selectedLayerIndex
        selected_layer = self._selected_layer()

        with self._document_lock:
            self._ensure_history_baseline()
            if direction == "forward":
                self._document.move_layer_down(index)
                action_text = "前移一层"
            else:
                self._document.move_layer_up(index)
                action_text = "后移一层"
            try:
                new_index = self._document.layers.index(selected_layer)
            except ValueError:
                return False
            if new_index == index:
                return False
            self._document.is_modified = True
            self._document._invalidate_render_cache()
            self._document.document_changed.emit()

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"图层已{action_text}", toast=True)
        return True

    @Slot(int, result=bool)
    def selectLayer(self, index: int) -> bool:
        if self._layer_model.layer_at(index) is None:
            return False
        self._document.selected_layer_index = int(index)
        self._document.selected_layer_indices = [int(index)]
        self.selectionChanged.emit()
        return True

    @Slot(result=bool)
    def clearSelection(self) -> bool:
        if self.selectedLayerIndex < 0:
            return True
        self._document.selected_layer_index = -1
        self._document.selected_layer_indices = []
        self.selectionChanged.emit()
        return True

    @staticmethod
    def _layer_contains_point(layer, x: float, y: float) -> bool:
        width = float(getattr(layer, "width", 0) or 0)
        height = float(getattr(layer, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return False
        left = float(getattr(layer, "x", 0) or 0)
        top = float(getattr(layer, "y", 0) or 0)
        center_x = left + width / 2.0
        center_y = top + height / 2.0
        offset_x = float(x) - center_x
        offset_y = float(y) - center_y
        angle = math.radians(float(getattr(layer, "rotation", 0.0) or 0.0))
        cosine = math.cos(angle)
        sine = math.sin(angle)
        local_x = cosine * offset_x + sine * offset_y
        local_y = -sine * offset_x + cosine * offset_y
        return abs(local_x) <= width / 2.0 and abs(local_y) <= height / 2.0

    @Slot(float, float, result=int)
    def selectLayerAt(self, x: float, y: float) -> int:
        for index in range(self._layer_model.rowCount() - 1, -1, -1):
            layer = self._layer_model.layer_at(index)
            if layer is None:
                continue
            if not bool(getattr(layer, "visible", True)) or bool(getattr(layer, "locked", False)):
                continue
            if self._layer_contains_point(layer, x, y):
                self.selectLayer(index)
                return index
        self.clearSelection()
        return -1

    def _ensure_history_baseline(self) -> None:
        manager = self._document._history_manager
        if manager.get_history_count() == 0:
            self._document.save_state("初始状态")

    def _set_layer_attrs(self, index: int, changes: dict, action: str, *, render: bool = True) -> bool:
        if not self._ensure_operations_available():
            return False
        with self._document_lock:
            layer = self._layer_model.layer_at(index)
            if layer is None:
                return False
            if any(attr not in ("visible", "locked") for attr in changes) and bool(
                getattr(layer, "locked", False)
            ):
                self._set_status("图层已锁定", toast=True)
                return False
            effective_changes = {
                attr: value
                for attr, value in changes.items()
                if getattr(layer, attr, None) != value
            }
            if not effective_changes:
                return True
            self._ensure_history_baseline()
            for attr, value in effective_changes.items():
                setattr(layer, attr, value)
            self._document.is_modified = True
            if any(
                attr in ("x", "y", "width", "height", "rotation", "visible", "locked")
                for attr in effective_changes
            ):
                self._document.bump_hit_test_version()
            if any(attr not in ("name", "locked") for attr in effective_changes):
                invalidate = getattr(self._document, "_invalidate_render_cache", None)
                if callable(invalidate):
                    invalidate()
            self._document.save_state(action)
        self._layer_model.notify_row(index)
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        if render:
            self.requestPreview(force=True)
        return True

    def _set_layer_attr(self, index: int, attr: str, value, action: str, *, render: bool = True) -> bool:
        return self._set_layer_attrs(index, {attr: value}, action, render=render)

    @Slot(str, result=bool)
    def setSelectedName(self, value: str) -> bool:
        value = str(value or "").strip()
        if not value:
            self._set_status("图层名称不能为空", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "name",
            value[:120],
            "重命名图层",
            render=False,
        )

    @Slot(float, result=bool)
    def setSelectedRotation(self, value: float) -> bool:
        if not self.selectedCanRotate:
            self._set_status("当前图层不支持旋转", toast=True)
            return False
        value = float(value) % 360.0
        return self._set_layer_attr(self.selectedLayerIndex, "rotation", value, "旋转图层")

    @Slot(int, int, int, int, result=bool)
    def applySelectedGeometry(self, x: int, y: int, width: int, height: int) -> bool:
        if width <= 0 or height <= 0:
            self._set_status("图层尺寸必须大于零", toast=True)
            return False
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            {
                "x": int(x),
                "y": int(y),
                "width": int(width),
                "height": int(height),
            },
            "画布变换图层",
        )

    @Slot(str, result=bool)
    def alignSelected(self, mode: str) -> bool:
        layer = self._selected_layer()
        if layer is None:
            return False
        width = int(getattr(layer, "width", 0))
        height = int(getattr(layer, "height", 0))
        alignments = {
            "left": {"x": 0},
            "hcenter": {"x": (self.canvasWidth - width) // 2},
            "vcenter": {"y": (self.canvasHeight - height) // 2},
        }
        changes = alignments.get(str(mode))
        if changes is None:
            return False
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "对齐图层")

    @Slot(int, result=bool)
    def setSelectedX(self, value: int) -> bool:
        return self._set_layer_attr(self.selectedLayerIndex, "x", int(value), "修改 X 坐标")

    @Slot(int, result=bool)
    def setSelectedY(self, value: int) -> bool:
        return self._set_layer_attr(self.selectedLayerIndex, "y", int(value), "修改 Y 坐标")

    @Slot(int, result=bool)
    def setSelectedWidth(self, value: int) -> bool:
        if value <= 0:
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "width", int(value), "修改图层宽度")

    @Slot(int, result=bool)
    def setSelectedHeight(self, value: int) -> bool:
        if value <= 0:
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "height", int(value), "修改图层高度")

    @Slot(int, result=bool)
    def setSelectedOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))
        return self._set_layer_attr(self.selectedLayerIndex, "opacity", value / 100.0, "修改不透明度")

    @Slot(int, result=bool)
    def toggleLayerVisible(self, index: int) -> bool:
        layer = self._layer_model.layer_at(index)
        return bool(layer) and self._set_layer_attr(index, "visible", not bool(layer.visible), "切换图层可见性")

    @Slot(int, result=bool)
    def toggleLayerLocked(self, index: int) -> bool:
        layer = self._layer_model.layer_at(index)
        return bool(layer) and self._set_layer_attr(
            index,
            "locked",
            not bool(layer.locked),
            "切换图层锁定",
            render=False,
        )

    @Slot(result=bool)
    def undo(self) -> bool:
        if not self._ensure_operations_available():
            return False
        with self._document_lock:
            if not self._document.undo():
                return False
            self._document.is_modified = True
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已撤销", toast=True)
        return True

    @Slot(result=bool)
    def redo(self) -> bool:
        if not self._ensure_operations_available():
            return False
        with self._document_lock:
            if not self._document.redo():
                return False
            self._document.is_modified = True
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已重做", toast=True)
        return True

    @Slot()
    @Slot(bool)
    def requestPreview(self, force: bool = False) -> None:
        del force
        if not self._auto_render:
            return
        if self._render_running:
            self._render_pending = True
            return
        self._preview_timer.start()

    @Slot(result=bool)
    def renderPreviewNow(self) -> bool:
        if self._auto_render:
            self._preview_timer.stop()
            self._start_preview_render()
            return True
        return self._render_preview_sync()

    @Slot()
    def _start_preview_render(self) -> None:
        if self._render_running:
            self._render_pending = True
            return
        self._render_running = True
        self._render_pending = False
        self._render_request_id += 1
        self._set_busy(True)
        task = _PreviewTask(self._render_request_id, self._document, self._document_lock)
        task.signals.finished.connect(self._on_preview_rendered)
        self._active_render_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(int, object, str, float)
    def _on_preview_rendered(self, request_id: int, qimage, error: str, elapsed: float) -> None:
        self._render_running = False
        self._active_render_task = None
        if request_id == self._render_request_id and qimage is not None and not qimage.isNull():
            self._preview_provider.set_image(qimage)
            self._preview_revision += 1
            self.previewChanged.emit()
            self._set_status(f"预览完成 · {elapsed * 1000:.0f} ms")
        elif error:
            self._set_status(f"预览失败：{error}", toast=True)
        self._set_busy(False)
        if self._render_pending:
            self._render_pending = False
            self._preview_timer.start()

    def _render_preview_sync(self) -> bool:
        from app.services.preview_render_service import render_preview_to_image

        self._set_busy(True)
        try:
            with self._document_lock:
                result = render_preview_to_image(self._document, force_refresh=True)
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
