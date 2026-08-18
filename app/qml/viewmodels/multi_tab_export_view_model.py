from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Property,
    QRunnable,
    QThreadPool,
    Qt,
    QUrl,
    Signal,
    Slot,
)


class _MultiTabExportSignals(QObject):
    documentStarted = Signal(int)
    documentFinished = Signal(int, bool, str, bool)
    finished = Signal(bool, bool)


class _MultiTabExportTask(QRunnable):
    def __init__(self, jobs, runner: Callable, cancel_event: threading.Event) -> None:
        super().__init__()
        self.jobs = jobs
        self.runner = runner
        self.cancel_event = cancel_event
        self.signals = _MultiTabExportSignals()

    def run(self) -> None:
        all_succeeded = True
        for job in self.jobs:
            if self.cancel_event.is_set():
                break
            index = int(job["index"])
            document = job["document"]
            self.signals.documentStarted.emit(index)
            try:
                success = bool(
                    self.runner(
                        document,
                        **job["parameters"],
                        cancel_callback=self.cancel_event.is_set,
                    )
                )
                error = str(getattr(document, "_last_export_error", "") or "")
            except Exception as exc:
                success = False
                error = str(exc)
            canceled = self.cancel_event.is_set()
            all_succeeded = all_succeeded and success
            self.signals.documentFinished.emit(index, success, error, canceled)
            if canceled:
                break
        self.signals.finished.emit(all_succeeded and not self.cancel_event.is_set(), self.cancel_event.is_set())


class MultiTabExportViewModel(QAbstractListModel):
    TitleRole = Qt.UserRole + 1
    EnabledRole = Qt.UserRole + 2
    CountRole = Qt.UserRole + 3
    StartIndexRole = Qt.UserRole + 4
    SubdirectoryRole = Qt.UserRole + 5
    StatusRole = Qt.UserRole + 6
    ProgressRole = Qt.UserRole + 7
    ErrorRole = Qt.UserRole + 8
    CanvasSizeRole = Qt.UserRole + 9

    configChanged = Signal()
    stateChanged = Signal()
    countChanged = Signal()

    def __init__(self, workspace, sessions, *, runner: Optional[Callable] = None, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._sessions = sessions
        self._runner = runner or self._run_document_export
        self._entries = []
        self._output_directory = ""
        self._filename_template = "image_{number:04d}"
        self._file_format = "png"
        self._avoid_duplicates = True
        self._traverse_mode = False
        self._running = False
        self._canceled = False
        self._succeeded = False
        self._active_document_index = -1
        self._failure_summary = ""
        self._cancel_event = threading.Event()
        self._task = None
        self._progress_slots = {}
        sessions.countChanged.connect(self.refreshDocuments)
        sessions.dataChanged.connect(lambda *_args: self.refreshDocuments())
        self.refreshDocuments()

    @staticmethod
    def _run_document_export(document, **kwargs) -> bool:
        return bool(document.batch_export(**kwargs))

    @staticmethod
    def _local_path(path_or_url: str) -> str:
        text = str(path_or_url or "").strip()
        url = QUrl(text)
        return url.toLocalFile() if url.isLocalFile() else text

    def roleNames(self):
        return {
            self.TitleRole: QByteArray(b"title"),
            self.EnabledRole: QByteArray(b"selectedForExport"),
            self.CountRole: QByteArray(b"exportCount"),
            self.StartIndexRole: QByteArray(b"startIndex"),
            self.SubdirectoryRole: QByteArray(b"subdirectory"),
            self.StatusRole: QByteArray(b"status"),
            self.ProgressRole: QByteArray(b"progress"),
            self.ErrorRole: QByteArray(b"error"),
            self.CanvasSizeRole: QByteArray(b"canvasSize"),
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        mapping = {
            Qt.DisplayRole: entry["title"],
            self.TitleRole: entry["title"],
            self.EnabledRole: entry["enabled"],
            self.CountRole: entry["count"],
            self.StartIndexRole: entry["start_index"],
            self.SubdirectoryRole: entry["subdirectory"],
            self.StatusRole: entry["status"],
            self.ProgressRole: entry["progress"],
            self.ErrorRole: entry["error"],
            self.CanvasSizeRole: entry["canvas_size"],
        }
        return mapping.get(role)

    def _emit_row(self, row: int) -> None:
        if not 0 <= row < len(self._entries):
            return
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, list(self.roleNames().keys()))
        self.stateChanged.emit()

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._entries)

    @Property(str, notify=configChanged)
    def outputDirectory(self) -> str:
        return self._output_directory

    @outputDirectory.setter
    def outputDirectory(self, value: str) -> None:
        value = self._local_path(value)
        if value != self._output_directory:
            self._output_directory = value
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
        value = str(value or "").lower()
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

    @Property(bool, notify=configChanged)
    def traverseMode(self) -> bool:
        return self._traverse_mode

    @traverseMode.setter
    def traverseMode(self, value: bool) -> None:
        value = bool(value)
        if value != self._traverse_mode:
            self._traverse_mode = value
            self.configChanged.emit()

    @Property(bool, notify=stateChanged)
    def running(self) -> bool:
        return self._running

    @Property(bool, notify=stateChanged)
    def canceled(self) -> bool:
        return self._canceled

    @Property(bool, notify=stateChanged)
    def succeeded(self) -> bool:
        return self._succeeded

    @Property(int, notify=configChanged)
    def selectedDocumentCount(self) -> int:
        return sum(1 for entry in self._entries if entry["enabled"])

    @Property(int, notify=configChanged)
    def totalImages(self) -> int:
        return sum(entry["count"] for entry in self._entries if entry["enabled"])

    @Property(int, notify=stateChanged)
    def completedImages(self) -> int:
        return sum(entry["progress"] for entry in self._entries if entry["enabled"])

    @Property(float, notify=stateChanged)
    def progress(self) -> float:
        return self.completedImages / self.totalImages if self.totalImages else 0.0

    @Property(str, notify=stateChanged)
    def statusText(self) -> str:
        if self._running:
            return "正在取消队列" if self._cancel_event.is_set() else "正在导出标签页队列"
        if self._canceled:
            return "多标签导出已取消"
        if self._succeeded:
            return "全部标签页导出完成"
        if self._failure_summary:
            return "部分标签页导出失败"
        return "配置多标签导出"

    @Property(str, notify=stateChanged)
    def failureSummary(self) -> str:
        return self._failure_summary

    @Slot()
    def refreshDocuments(self) -> None:
        if self._running:
            return
        old = {id(entry["document"]): entry for entry in self._entries}
        entries = []
        for index in range(self._sessions.count):
            document = self._sessions.documentAt(index)
            if document is None:
                continue
            previous = old.get(id(document), {})
            model_index = self._sessions.index(index, 0)
            title = self._sessions.data(model_index, self._sessions.TitleRole)
            entries.append(
                {
                    "document": document,
                    "title": str(title or f"标签页 {index + 1}"),
                    "enabled": previous.get("enabled", True),
                    "count": int(previous.get("count", 10)),
                    "start_index": int(previous.get("start_index", 1)),
                    "subdirectory": str(previous.get("subdirectory", f"tab_{index + 1:02d}")),
                    "status": "等待",
                    "progress": 0,
                    "error": "",
                    "canvas_size": f"{int(document.canvas_width)} x {int(document.canvas_height)}",
                }
            )
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()
        self.countChanged.emit()
        self.configChanged.emit()
        self.stateChanged.emit()

    @Slot(int, bool, result=bool)
    def setDocumentEnabled(self, row: int, enabled: bool) -> bool:
        if self._running or not 0 <= int(row) < len(self._entries):
            return False
        self._entries[int(row)]["enabled"] = bool(enabled)
        self._emit_row(int(row))
        self.configChanged.emit()
        return True

    @Slot(int, int, result=bool)
    def setDocumentCount(self, row: int, count: int) -> bool:
        if self._running or not 0 <= int(row) < len(self._entries) or not 1 <= int(count) <= 10000:
            return False
        self._entries[int(row)]["count"] = int(count)
        self._emit_row(int(row))
        self.configChanged.emit()
        return True

    @Slot(int, int, result=bool)
    def setDocumentStartIndex(self, row: int, start_index: int) -> bool:
        if self._running or not 0 <= int(row) < len(self._entries) or int(start_index) < 0:
            return False
        self._entries[int(row)]["start_index"] = int(start_index)
        self._emit_row(int(row))
        return True

    @Slot(int, str, result=bool)
    def setDocumentSubdirectory(self, row: int, subdirectory: str) -> bool:
        if self._running or not 0 <= int(row) < len(self._entries):
            return False
        text = str(subdirectory or "").strip().replace("\\", "/").strip("/")
        if not text or ".." in Path(text).parts:
            return False
        self._entries[int(row)]["subdirectory"] = text
        self._emit_row(int(row))
        return True

    def _disconnect_progress(self) -> None:
        for document, slot in list(self._progress_slots.items()):
            try:
                document.export_progress_updated.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._progress_slots.clear()

    @Slot(result=bool)
    def startExport(self) -> bool:
        if self._running or not self._output_directory or not self._filename_template.strip():
            return False
        if self._file_format not in {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}:
            return False
        selected = [(index, entry) for index, entry in enumerate(self._entries) if entry["enabled"]]
        if not selected:
            return False
        try:
            Path(self._output_directory).mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        self._cancel_event = threading.Event()
        self._running = True
        self._canceled = False
        self._succeeded = False
        self._failure_summary = ""
        jobs = []
        for index, entry in selected:
            entry.update(status="排队", progress=0, error="")
            directory = os.path.join(self._output_directory, entry["subdirectory"])
            jobs.append(
                {
                    "index": index,
                    "document": entry["document"],
                    "parameters": {
                        "directory": directory,
                        "count": entry["count"],
                        "filename_template": self._filename_template.strip(),
                        "file_format": self._file_format,
                        "start_index": entry["start_index"],
                        "use_high_performance": True,
                        "traverse_mode": self._traverse_mode,
                        "use_smart_sampling": self._avoid_duplicates,
                    },
                }
            )
            slot = lambda current, row=index: self._on_document_progress(row, current)
            entry["document"].export_progress_updated.connect(slot)
            self._progress_slots[entry["document"]] = slot

        self._workspace.setExportRunning(True)
        self.stateChanged.emit()
        task = _MultiTabExportTask(jobs, self._runner, self._cancel_event)
        task.signals.documentStarted.connect(self._on_document_started)
        task.signals.documentFinished.connect(self._on_document_finished)
        task.signals.finished.connect(self._on_finished)
        self._task = task
        QThreadPool.globalInstance().start(task)
        return True

    @Slot(result=bool)
    def cancelExport(self) -> bool:
        if not self._running or self._cancel_event.is_set():
            return False
        self._cancel_event.set()
        if 0 <= self._active_document_index < len(self._entries):
            self._entries[self._active_document_index]["document"].cancel_export()
        self.stateChanged.emit()
        return True

    @Slot(int)
    def _on_document_started(self, row: int) -> None:
        self._active_document_index = int(row)
        self._entries[int(row)]["status"] = "导出中"
        self._emit_row(int(row))

    @Slot(int, int)
    def _on_document_progress(self, row: int, current: int) -> None:
        if 0 <= int(row) < len(self._entries):
            entry = self._entries[int(row)]
            entry["progress"] = max(0, min(entry["count"], int(current)))
            self._emit_row(int(row))

    @Slot(int, bool, str, bool)
    def _on_document_finished(self, row: int, success: bool, error: str, canceled: bool) -> None:
        entry = self._entries[int(row)]
        entry["status"] = "已取消" if canceled else ("完成" if success else "失败")
        entry["error"] = str(error or "")
        if success:
            entry["progress"] = entry["count"]
        self._emit_row(int(row))

    @Slot(bool, bool)
    def _on_finished(self, success: bool, canceled: bool) -> None:
        self._disconnect_progress()
        self._task = None
        self._running = False
        self._canceled = bool(canceled)
        self._succeeded = bool(success)
        self._active_document_index = -1
        failures = [entry for entry in self._entries if entry["enabled"] and entry["status"] == "失败"]
        if failures:
            self._failure_summary = "；".join(
                f"{entry['title']}：{entry['error'] or '未知错误'}" for entry in failures
            )
        self._workspace.setExportRunning(False)
        self.stateChanged.emit()
