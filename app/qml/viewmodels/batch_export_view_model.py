from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from app.models.document import Document


class _BatchExportTaskSignals(QObject):
    finished = Signal(bool, str, bool)


class _BatchExportTask(QRunnable):
    def __init__(
        self,
        document: Document,
        document_lock: threading.RLock,
        runner: Callable,
        parameters: dict,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self.document = document
        self.document_lock = document_lock
        self.runner = runner
        self.parameters = parameters
        self.cancel_event = cancel_event
        self.signals = _BatchExportTaskSignals()

    def run(self) -> None:
        try:
            with self.document_lock:
                success = bool(
                    self.runner(
                        self.document,
                        **self.parameters,
                        cancel_callback=self.cancel_event.is_set,
                    )
                )
            canceled = self.cancel_event.is_set()
            error = str(getattr(self.document, "_last_export_error", "") or "")
            self.signals.finished.emit(success, error, canceled)
        except Exception as error:
            self.signals.finished.emit(False, str(error), self.cancel_event.is_set())


class BatchExportViewModel(QObject):
    configChanged = Signal()
    stateChanged = Signal()
    documentChanged = Signal()

    def __init__(
        self,
        workspace,
        *,
        runner: Optional[Callable] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._runner = runner or self._run_document_export
        self._document: Optional[Document] = None
        self._output_directory = ""
        self._count = 12
        self._filename_template = "image_{number:04d}"
        self._file_format = "png"
        self._avoid_duplicates = True
        self._running = False
        self._succeeded = False
        self._canceled = False
        self._current = 0
        self._total = 0
        self._stage = "等待开始"
        self._last_file = ""
        self._error_message = ""
        self._cancel_event = threading.Event()
        self._active_task = None

        workspace.documentObjectChanged.connect(self.setDocument)
        self.setDocument(workspace.document)

    @staticmethod
    def _run_document_export(document: Document, **kwargs) -> bool:
        return bool(document.batch_export(**kwargs))

    @staticmethod
    def _local_path(path_or_url: str) -> str:
        text = str(path_or_url or "").strip()
        url = QUrl(text)
        return url.toLocalFile() if url.isLocalFile() else text

    @Property(QObject, notify=documentChanged)
    def document(self):
        return self._document

    @Property(str, notify=configChanged)
    def outputDirectory(self) -> str:
        return self._output_directory

    @outputDirectory.setter
    def outputDirectory(self, value: str) -> None:
        value = self._local_path(value)
        if value != self._output_directory:
            self._output_directory = value
            self.configChanged.emit()

    @Property(int, notify=configChanged)
    def count(self) -> int:
        return self._count

    @count.setter
    def count(self, value: int) -> None:
        value = int(value)
        if value != self._count:
            self._count = value
            self.configChanged.emit()

    @Property(str, notify=configChanged)
    def filenameTemplate(self) -> str:
        return self._filename_template

    @filenameTemplate.setter
    def filenameTemplate(self, value: str) -> None:
        value = str(value or "")
        if value != self._filename_template:
            self._filename_template = value
            self.configChanged.emit()

    @Property(str, notify=configChanged)
    def fileFormat(self) -> str:
        return self._file_format

    @fileFormat.setter
    def fileFormat(self, value: str) -> None:
        value = str(value or "").strip().lower()
        if value != self._file_format:
            self._file_format = value
            self.configChanged.emit()

    @Property(bool, notify=configChanged)
    def avoidDuplicates(self) -> bool:
        return self._avoid_duplicates

    @avoidDuplicates.setter
    def avoidDuplicates(self, value: bool) -> None:
        value = bool(value)
        if value != self._avoid_duplicates:
            self._avoid_duplicates = value
            self.configChanged.emit()

    @Property(bool, notify=stateChanged)
    def running(self) -> bool:
        return self._running

    @Property(bool, notify=stateChanged)
    def succeeded(self) -> bool:
        return self._succeeded

    @Property(bool, notify=stateChanged)
    def canceled(self) -> bool:
        return self._canceled

    @Property(int, notify=stateChanged)
    def current(self) -> int:
        return self._current

    @Property(int, notify=stateChanged)
    def total(self) -> int:
        return self._total

    @Property(float, notify=stateChanged)
    def progress(self) -> float:
        if self._total <= 0:
            return 0.0
        return max(0.0, min(1.0, self._current / self._total))

    @Property(str, notify=stateChanged)
    def stage(self) -> str:
        return self._stage

    @Property(str, notify=stateChanged)
    def lastFile(self) -> str:
        return self._last_file

    @Property(str, notify=stateChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Property(str, notify=stateChanged)
    def statusText(self) -> str:
        if self._running:
            return "正在取消..." if self._cancel_event.is_set() else "批量导出进行中"
        if self._succeeded:
            return f"已完成 {self._current} 张图像"
        if self._canceled:
            return f"导出已取消，已完成 {self._current} 张"
        if self._error_message:
            return "批量导出失败"
        return "配置导出任务"

    @Property(str, notify=configChanged)
    def estimatedTime(self) -> str:
        seconds = max(1, round(self._count * 0.7))
        if seconds < 60:
            return f"约 {seconds} 秒"
        return f"约 {seconds // 60} 分 {seconds % 60} 秒"

    def _disconnect_document(self) -> None:
        if self._document is None:
            return
        connections = (
            (self._document.export_progress_updated, self._on_progress),
            (self._document.file_exported, self._on_file_exported),
            (self._document.export_stage_updated, self._on_stage),
        )
        for signal, slot in connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    @Slot(object)
    def setDocument(self, document) -> None:
        if document is self._document:
            return
        if self._running:
            return
        self._disconnect_document()
        self._document = document
        if self._document is not None:
            self._document.export_progress_updated.connect(self._on_progress)
            self._document.file_exported.connect(self._on_file_exported)
            self._document.export_stage_updated.connect(self._on_stage)
        self.documentChanged.emit()

    def _set_error(self, message: str) -> None:
        self._error_message = str(message or "")
        self._succeeded = False
        self._canceled = False
        self._stage = "配置有误"
        self.stateChanged.emit()

    def _validate(self) -> bool:
        if self._document is None:
            self._set_error("当前没有可导出的文档")
            return False
        if not self._output_directory:
            self._set_error("请选择输出目录")
            return False
        if not 1 <= self._count <= 10000:
            self._set_error("导出数量必须在 1 到 10000 之间")
            return False
        if not self._filename_template.strip():
            self._set_error("文件名模板不能为空")
            return False
        if self._file_format not in {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}:
            self._set_error("不支持的导出格式")
            return False
        try:
            Path(self._output_directory).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._set_error(f"无法创建输出目录：{error}")
            return False
        return True

    @Slot(result=bool)
    def startExport(self) -> bool:
        if self._running:
            return False
        if not self._validate():
            return False

        self._cancel_event = threading.Event()
        self._running = True
        self._succeeded = False
        self._canceled = False
        self._current = 0
        self._total = self._count
        self._stage = "准备导出"
        self._last_file = ""
        self._error_message = ""
        self._document._export_canceled = False
        self._workspace.setExportRunning(True)
        self.stateChanged.emit()

        parameters = {
            "directory": self._output_directory,
            "count": self._count,
            "filename_template": self._filename_template.strip(),
            "file_format": self._file_format,
            "start_index": 1,
            "use_high_performance": True,
            "traverse_mode": False,
            "use_smart_sampling": self._avoid_duplicates,
        }
        task = _BatchExportTask(
            self._document,
            self._workspace.documentLock,
            self._runner,
            parameters,
            self._cancel_event,
        )
        task.signals.finished.connect(self._on_finished)
        self._active_task = task
        QThreadPool.globalInstance().start(task)
        return True

    @Slot(result=bool)
    def cancelExport(self) -> bool:
        if not self._running or self._cancel_event.is_set():
            return False
        self._cancel_event.set()
        self._stage = "正在取消"
        if self._document is not None:
            self._document.cancel_export()
        self.stateChanged.emit()
        return True

    @Slot(int)
    def _on_progress(self, current: int) -> None:
        self._current = max(0, min(self._total, int(current)))
        self.stateChanged.emit()

    @Slot(str)
    def _on_stage(self, stage: str) -> None:
        if self._running and not self._cancel_event.is_set():
            self._stage = str(stage or "处理中")
            self.stateChanged.emit()

    @Slot(str)
    def _on_file_exported(self, file_path: str) -> None:
        self._last_file = str(file_path or "")
        self.stateChanged.emit()

    @Slot(bool, str, bool)
    def _on_finished(self, success: bool, error: str, canceled: bool) -> None:
        self._active_task = None
        self._running = False
        self._workspace.setExportRunning(False)
        if canceled:
            self._canceled = True
            self._succeeded = False
            self._stage = "已取消"
            self._error_message = ""
        elif success:
            self._canceled = False
            self._succeeded = True
            self._current = self._total
            self._stage = "导出完成"
            self._error_message = ""
        else:
            self._canceled = False
            self._succeeded = False
            self._stage = "导出失败"
            self._error_message = str(error or "未知错误")
        self.stateChanged.emit()

    @Slot(result=bool)
    def openOutputDirectory(self) -> bool:
        if not self._output_directory or not os.path.isdir(self._output_directory):
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_directory)))
