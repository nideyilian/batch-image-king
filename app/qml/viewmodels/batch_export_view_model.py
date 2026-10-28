from __future__ import annotations

import datetime
import os
import re
import threading
from pathlib import Path
from typing import Callable, Optional
from weakref import WeakKeyDictionary

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

    _DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d", "%y%m%d")
    _NUMBER_FORMATS = ("{number:04d}", "{number:03d}", "{number:02d}", "{number:d}")
    _FORMAT_BY_INDEX = {0: "png", 1: "jpg", 2: "bmp"}
    _INDEX_BY_FORMAT = {"png": 0, "jpg": 1, "jpeg": 1, "bmp": 2}

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
        self._count = 10
        self._use_date = True
        self._date_format_index = 0
        self._custom_text = "export"
        self._use_layer_name = False
        self._layer_index = 0
        self._number_format_index = 0
        self._filename_template = ""
        self._manual_filename_template = False
        self._file_format = "png"
        self._avoid_duplicates = True
        self._start_index = 1
        self._traverse_mode = False
        self._traverse_count = 0
        self._traverse_error = ""
        self._max_file_size_kb = 299
        self._use_current_time_for_path = False
        self._unique_use_enabled = False
        self._selected_unique_layers = set()
        self._use_high_performance = True
        self._preload_enabled = True
        self._quality_profile = "quality"
        self._memory_guard_mode = "auto"
        self._memory_limit_mb = 0
        self._memory_reserve_mb = 2048
        self._max_consecutive_failures = 8
        self._failure_rate_limit = 45
        self._stall_timeout_seconds = 180
        self._external_worker_enabled = True
        self._running = False
        self._succeeded = False
        self._canceled = False
        self._current = 0
        self._total = 0
        self._stage = "等待开始"
        self._last_file = ""
        self._error_message = ""
        self._failure_summary = ""
        self._degradation_summary = ""
        self._adjustment_summary = ""
        self._cancel_event = threading.Event()
        self._active_task = None
        self._document_states = WeakKeyDictionary()
        self._filename_template = self._build_filename_template()

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

    def _build_filename_template(self) -> str:
        parts = []
        if self._use_date:
            format_string = self._DATE_FORMATS[max(0, min(self._date_format_index, 2))]
            parts.append(datetime.datetime.now().strftime(format_string))
        custom_text = self._custom_text.strip()
        if custom_text:
            parts.append(custom_text)
        if self._use_layer_name and self._document is not None and self._document.layers:
            layer_index = max(0, min(self._layer_index, len(self._document.layers) - 1))
            parts.append(f"{{layer:{layer_index}}}")
        number_format = self._NUMBER_FORMATS[max(0, min(self._number_format_index, 3))]
        parts.append(number_format)
        return "-".join(parts)

    def _rebuild_filename_template(self) -> None:
        self._manual_filename_template = False
        self._filename_template = self._build_filename_template()
        self.configChanged.emit()

    @staticmethod
    def _is_valid_yyyymmdd(value: str) -> bool:
        try:
            datetime.datetime.strptime(value, "%Y%m%d")
            return True
        except ValueError:
            return False

    @classmethod
    def _replace_path_date_with_today(cls, path: str) -> str:
        today = datetime.datetime.now().strftime("%Y%m%d")

        def replace(match) -> str:
            value = match.group(0)
            return today if cls._is_valid_yyyymmdd(value) else value

        return re.sub(r"(?<!\d)(?:19|20)\d{6}(?!\d)", replace, str(path or ""))

    def _resolved_output_directory(self) -> str:
        if self._use_current_time_for_path:
            return self._replace_path_date_with_today(self._output_directory)
        return self._output_directory

    @staticmethod
    def _is_text_layer(layer) -> bool:
        if layer is None:
            return False
        if hasattr(layer, "get_text_lines") and callable(getattr(layer, "get_text_lines", None)):
            return True
        if layer.__class__.__name__ == "TextLayer":
            return True
        return bool(hasattr(layer, "text_content") and not hasattr(layer, "image_source"))

    @classmethod
    def _is_unique_use_eligible_layer(cls, layer) -> bool:
        if layer is None or cls._is_text_layer(layer):
            return False
        source = getattr(layer, "image_source", None) or getattr(layer, "_image_source", None)
        if source:
            return True
        return bool(getattr(layer, "image_paths", None))

    def _refresh_traverse_count(self) -> None:
        self._traverse_count = 0
        self._traverse_error = ""
        if not self._traverse_mode or self._document is None:
            return
        try:
            self._traverse_count = int(self._document._calculate_possible_combinations())
        except Exception as error:
            self._traverse_error = str(error or "无法计算组合数量")

    def _current_filename_template(self) -> str:
        if self._manual_filename_template:
            return self._filename_template.strip()
        self._filename_template = self._build_filename_template()
        return self._filename_template

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
        return self._current_filename_template()

    @filenameTemplate.setter
    def filenameTemplate(self, value: str) -> None:
        value = str(value or "")
        if value != self._filename_template or not self._manual_filename_template:
            self._filename_template = value
            self._manual_filename_template = True
            self.configChanged.emit()

    @Property(bool, notify=configChanged)
    def useDate(self) -> bool:
        return self._use_date

    @useDate.setter
    def useDate(self, value: bool) -> None:
        value = bool(value)
        if value != self._use_date:
            self._use_date = value
            self._rebuild_filename_template()

    @Property(int, notify=configChanged)
    def dateFormatIndex(self) -> int:
        return self._date_format_index

    @dateFormatIndex.setter
    def dateFormatIndex(self, value: int) -> None:
        value = max(0, min(int(value), len(self._DATE_FORMATS) - 1))
        if value != self._date_format_index:
            self._date_format_index = value
            self._rebuild_filename_template()

    @Property(str, notify=configChanged)
    def customText(self) -> str:
        return self._custom_text

    @customText.setter
    def customText(self, value: str) -> None:
        value = str(value or "")
        if value != self._custom_text:
            self._custom_text = value
            self._rebuild_filename_template()

    @Property(bool, notify=configChanged)
    def useLayerName(self) -> bool:
        return self._use_layer_name

    @useLayerName.setter
    def useLayerName(self, value: bool) -> None:
        value = bool(value)
        if value != self._use_layer_name:
            self._use_layer_name = value
            self._rebuild_filename_template()

    @Property(int, notify=configChanged)
    def layerIndex(self) -> int:
        return self._layer_index

    @layerIndex.setter
    def layerIndex(self, value: int) -> None:
        value = max(0, int(value))
        if value != self._layer_index:
            self._layer_index = value
            self._rebuild_filename_template()

    @Property(int, notify=configChanged)
    def numberFormatIndex(self) -> int:
        return self._number_format_index

    @numberFormatIndex.setter
    def numberFormatIndex(self, value: int) -> None:
        value = max(0, min(int(value), len(self._NUMBER_FORMATS) - 1))
        if value != self._number_format_index:
            self._number_format_index = value
            self._rebuild_filename_template()

    @Property("QVariantList", notify=configChanged)
    def layerOptions(self):
        if self._document is None:
            return []
        return [
            {"label": f"{getattr(layer, 'name', f'图层 {index + 1}')} (图层 {index + 1})", "value": index}
            for index, layer in enumerate(self._document.layers)
        ]

    @Property(str, notify=configChanged)
    def filenamePreview(self) -> str:
        preview = self._current_filename_template()
        if self._document is not None and self._document.layers:
            layer_index = max(0, min(self._layer_index, len(self._document.layers) - 1))
            layer = self._document.layers[layer_index]
            path = str(getattr(layer, "current_image_path", "") or "")
            if path:
                layer_name = Path(path).stem
                extractor = getattr(self._document, "_extract_main_filename", None)
                if callable(extractor):
                    layer_name = extractor(layer_name) or layer_name
            else:
                layer_name = "[实际图像名称]"
            preview = preview.replace(f"{{layer:{layer_index}}}", layer_name)
        try:
            preview = preview.format(number=self._start_index)
        except (KeyError, ValueError):
            pass
        extension = "jpg" if self._file_format == "jpeg" else self._file_format
        return f"{preview}.{extension}"

    @Property(str, notify=configChanged)
    def fileFormat(self) -> str:
        return self._file_format

    @fileFormat.setter
    def fileFormat(self, value: str) -> None:
        value = str(value or "").strip().lower()
        if value == "jpeg":
            value = "jpg"
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

    def _set_config_value(self, attribute: str, value) -> None:
        if getattr(self, attribute) != value:
            setattr(self, attribute, value)
            self.configChanged.emit()

    @Property(int, notify=configChanged)
    def startIndex(self) -> int:
        return self._start_index

    @startIndex.setter
    def startIndex(self, value: int) -> None:
        self._set_config_value("_start_index", int(value))

    @Property(bool, notify=configChanged)
    def traverseMode(self) -> bool:
        return self._traverse_mode

    @traverseMode.setter
    def traverseMode(self, value: bool) -> None:
        value = bool(value)
        if value != self._traverse_mode:
            self._traverse_mode = value
            self._refresh_traverse_count()
            self.configChanged.emit()

    @Property(int, notify=configChanged)
    def effectiveCount(self) -> int:
        return self._traverse_count if self._traverse_mode else self._count

    @Property(str, notify=configChanged)
    def traverseCountText(self) -> str:
        if not self._traverse_mode:
            return ""
        if self._traverse_error:
            return "无法计算组合数"
        if self._traverse_count > 10000:
            return f"将导出 {self._traverse_count} 个组合 · 注意数量很大"
        if self._traverse_count > 1000:
            return f"将导出 {self._traverse_count} 个组合 · 数量较大"
        return f"将导出 {self._traverse_count} 个组合"

    @Property(int, notify=configChanged)
    def maxFileSizeKB(self) -> int:
        return self._max_file_size_kb

    @maxFileSizeKB.setter
    def maxFileSizeKB(self, value: int) -> None:
        self._set_config_value("_max_file_size_kb", int(value))

    @Property(bool, notify=configChanged)
    def useCurrentTimeForPath(self) -> bool:
        return self._use_current_time_for_path

    @useCurrentTimeForPath.setter
    def useCurrentTimeForPath(self, value: bool) -> None:
        self._set_config_value("_use_current_time_for_path", bool(value))

    @Property(bool, notify=configChanged)
    def uniqueUseEnabled(self) -> bool:
        return self._unique_use_enabled

    @uniqueUseEnabled.setter
    def uniqueUseEnabled(self, value: bool) -> None:
        self._set_config_value("_unique_use_enabled", bool(value))

    @Property("QVariantList", notify=configChanged)
    def uniqueLayerOptions(self):
        if self._document is None:
            return []
        options = []
        for index, layer in enumerate(self._document.layers):
            eligible = self._is_unique_use_eligible_layer(layer)
            options.append(
                {
                    "index": index,
                    "label": str(getattr(layer, "name", f"图层 {index + 1}")),
                    "eligible": eligible,
                    "selected": eligible and index in self._selected_unique_layers,
                }
            )
        return options

    @Slot(int, bool, result=bool)
    def setUniqueLayerSelected(self, layer_index: int, selected: bool) -> bool:
        if self._document is None or not 0 <= layer_index < len(self._document.layers):
            return False
        if not self._is_unique_use_eligible_layer(self._document.layers[layer_index]):
            return False
        if selected:
            self._selected_unique_layers.add(int(layer_index))
        else:
            self._selected_unique_layers.discard(int(layer_index))
        self.configChanged.emit()
        return True

    @Property(bool, notify=configChanged)
    def useHighPerformance(self) -> bool:
        return self._use_high_performance

    @useHighPerformance.setter
    def useHighPerformance(self, value: bool) -> None:
        self._set_config_value("_use_high_performance", bool(value))

    @Property(bool, notify=configChanged)
    def preloadEnabled(self) -> bool:
        return self._preload_enabled

    @preloadEnabled.setter
    def preloadEnabled(self, value: bool) -> None:
        self._set_config_value("_preload_enabled", bool(value))

    @Property(str, notify=configChanged)
    def qualityProfile(self) -> str:
        return self._quality_profile

    @qualityProfile.setter
    def qualityProfile(self, value: str) -> None:
        self._set_config_value("_quality_profile", str(value or "quality").lower())

    @Property(str, notify=configChanged)
    def memoryGuardMode(self) -> str:
        return self._memory_guard_mode

    @memoryGuardMode.setter
    def memoryGuardMode(self, value: str) -> None:
        self._set_config_value("_memory_guard_mode", str(value or "auto").lower())

    @Property(int, notify=configChanged)
    def memoryLimitMB(self) -> int:
        return self._memory_limit_mb

    @memoryLimitMB.setter
    def memoryLimitMB(self, value: int) -> None:
        self._set_config_value("_memory_limit_mb", int(value))

    @Property(int, notify=configChanged)
    def memoryReserveMB(self) -> int:
        return self._memory_reserve_mb

    @memoryReserveMB.setter
    def memoryReserveMB(self, value: int) -> None:
        self._set_config_value("_memory_reserve_mb", int(value))

    @Property(int, notify=configChanged)
    def maxConsecutiveFailures(self) -> int:
        return self._max_consecutive_failures

    @maxConsecutiveFailures.setter
    def maxConsecutiveFailures(self, value: int) -> None:
        self._set_config_value("_max_consecutive_failures", int(value))

    @Property(int, notify=configChanged)
    def failureRateLimit(self) -> int:
        return self._failure_rate_limit

    @failureRateLimit.setter
    def failureRateLimit(self, value: int) -> None:
        self._set_config_value("_failure_rate_limit", int(value))

    @Property(int, notify=configChanged)
    def stallTimeoutSeconds(self) -> int:
        return self._stall_timeout_seconds

    @stallTimeoutSeconds.setter
    def stallTimeoutSeconds(self, value: int) -> None:
        self._set_config_value("_stall_timeout_seconds", int(value))

    @Property(bool, notify=configChanged)
    def externalWorkerEnabled(self) -> bool:
        return self._external_worker_enabled

    @externalWorkerEnabled.setter
    def externalWorkerEnabled(self, value: bool) -> None:
        self._set_config_value("_external_worker_enabled", bool(value))

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
    def failureSummary(self) -> str:
        return self._failure_summary

    @Property(str, notify=stateChanged)
    def degradationSummary(self) -> str:
        """导出过程中的降级告警（空串表示无）。

        降级不等于失败：素材目录丢失、分类筛选为空、去重失效这类问题
        照样能出图，但出来的图「不对」。经典版在完成提示里会带一句
        「结果可能不符合预期」，QML 版必须同样让用户看见，而不是去翻日志。
        """
        return self._degradation_summary

    @Property(str, notify=stateChanged)
    def adjustmentSummary(self) -> str:
        """实际导出数量少于请求数量时的说明（空串表示无调整）。"""
        return self._adjustment_summary

    @Property(bool, notify=stateChanged)
    def canRetry(self) -> bool:
        return not self._running and (self._canceled or bool(self._error_message))

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
        seconds = max(1, round(self.effectiveCount * 0.7))
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
            (self._document.layers_changed, self._on_document_layers_changed),
        )
        for signal, slot in connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    @Slot()
    def _on_document_layers_changed(self) -> None:
        if self._document is None:
            return
        eligible = {
            index
            for index, layer in enumerate(self._document.layers)
            if self._is_unique_use_eligible_layer(layer)
        }
        self._selected_unique_layers.intersection_update(eligible)
        if self._document.layers:
            self._layer_index = min(self._layer_index, len(self._document.layers) - 1)
        else:
            self._layer_index = 0
        self._refresh_traverse_count()
        if not self._manual_filename_template:
            self._filename_template = self._build_filename_template()
        self.configChanged.emit()

    def _snapshot_state(self) -> dict:
        return {
            "output_directory": self._output_directory,
            "count": self._count,
            "filename_template": self._filename_template,
            "manual_filename_template": self._manual_filename_template,
            "use_date": self._use_date,
            "date_format_index": self._date_format_index,
            "custom_text": self._custom_text,
            "use_layer_name": self._use_layer_name,
            "layer_index": self._layer_index,
            "number_format_index": self._number_format_index,
            "file_format": self._file_format,
            "avoid_duplicates": self._avoid_duplicates,
            "start_index": self._start_index,
            "traverse_mode": self._traverse_mode,
            "max_file_size_kb": self._max_file_size_kb,
            "use_current_time_for_path": self._use_current_time_for_path,
            "unique_use_enabled": self._unique_use_enabled,
            "selected_unique_layers": set(self._selected_unique_layers),
            "use_high_performance": self._use_high_performance,
            "preload_enabled": self._preload_enabled,
            "quality_profile": self._quality_profile,
            "memory_guard_mode": self._memory_guard_mode,
            "memory_limit_mb": self._memory_limit_mb,
            "memory_reserve_mb": self._memory_reserve_mb,
            "max_consecutive_failures": self._max_consecutive_failures,
            "failure_rate_limit": self._failure_rate_limit,
            "stall_timeout_seconds": self._stall_timeout_seconds,
            "external_worker_enabled": self._external_worker_enabled,
            "succeeded": self._succeeded,
            "canceled": self._canceled,
            "current": self._current,
            "total": self._total,
            "stage": self._stage,
            "last_file": self._last_file,
            "error_message": self._error_message,
            "failure_summary": self._failure_summary,
        }

    @staticmethod
    def _default_state() -> dict:
        return {
            "output_directory": "",
            "count": 10,
            "filename_template": "",
            "manual_filename_template": False,
            "use_date": True,
            "date_format_index": 0,
            "custom_text": "export",
            "use_layer_name": False,
            "layer_index": 0,
            "number_format_index": 0,
            "file_format": "png",
            "avoid_duplicates": True,
            "start_index": 1,
            "traverse_mode": False,
            "max_file_size_kb": 299,
            "use_current_time_for_path": False,
            "unique_use_enabled": False,
            "selected_unique_layers": set(),
            "use_high_performance": True,
            "preload_enabled": True,
            "quality_profile": "quality",
            "memory_guard_mode": "auto",
            "memory_limit_mb": 0,
            "memory_reserve_mb": 2048,
            "max_consecutive_failures": 8,
            "failure_rate_limit": 45,
            "stall_timeout_seconds": 180,
            "external_worker_enabled": True,
            "succeeded": False,
            "canceled": False,
            "current": 0,
            "total": 0,
            "stage": "等待开始",
            "last_file": "",
            "error_message": "",
            "failure_summary": "",
        }

    def _state_from_document(self, document) -> dict:
        state = self._default_state()
        if document is None:
            return state
        settings = getattr(document, "export_settings", {}) or {}
        has_saved_config = bool(
            settings.get("batch_export_settings_saved")
            or settings.get("last_directory")
            or settings.get("directory")
        )
        if not has_saved_config:
            return state
        configured_format = str(settings.get("format") or "").strip().lower()
        if configured_format in {"webp", "tiff"}:
            format_name = configured_format
        else:
            format_name = self._FORMAT_BY_INDEX.get(int(settings.get("format_index", 1) or 0), "jpg")
        failure_rate = float(settings.get("export_safety_failure_rate_limit", 0.45) or 0.45)
        if failure_rate <= 1:
            failure_rate *= 100
        state.update(
            {
                "output_directory": str(settings.get("last_directory") or settings.get("directory") or ""),
                "count": int(settings.get("count", 10) or 10),
                "use_date": bool(settings.get("use_date", True)),
                "date_format_index": int(settings.get("date_format_index", 0) or 0),
                "custom_text": str(settings.get("custom_text", "export") or ""),
                "use_layer_name": bool(settings.get("use_layer_name", False)),
                "layer_index": int(settings.get("layer_index", 0) or 0),
                "number_format_index": int(settings.get("number_format_index", 0) or 0),
                "file_format": format_name,
                "avoid_duplicates": bool(settings.get("smart_sampling", True)),
                "start_index": int(settings.get("start_index", 1) or 1),
                "traverse_mode": bool(settings.get("traverse_export", False)),
                "max_file_size_kb": int(settings.get("max_file_size_kb", 299) or 0),
                "use_current_time_for_path": bool(settings.get("use_current_time_for_path", False)),
                "unique_use_enabled": bool(settings.get("unique_use_enabled", False)),
                "selected_unique_layers": {
                    int(index) for index in settings.get("unique_use_layers", []) if str(index).lstrip("-").isdigit()
                },
                "use_high_performance": bool(settings.get("use_high_performance", True)),
                "preload_enabled": bool(settings.get("batch_preload_enabled", True)),
                "quality_profile": str(settings.get("export_quality_profile", "quality") or "quality"),
                "memory_guard_mode": str(settings.get("export_memory_guard_mode", "auto") or "auto"),
                "memory_limit_mb": int(settings.get("export_memory_limit_mb", 0) or 0),
                "memory_reserve_mb": int(settings.get("export_memory_reserve_mb", 2048) or 2048),
                "max_consecutive_failures": int(settings.get("export_safety_max_consecutive_failures", 8) or 8),
                "failure_rate_limit": int(round(failure_rate)),
                "stall_timeout_seconds": int(settings.get("export_safety_stall_timeout_seconds", 180) or 180),
                "external_worker_enabled": bool(settings.get("export_external_worker_enabled", True)),
            }
        )
        return state

    def _restore_state(self, state: dict) -> None:
        self._output_directory = state["output_directory"]
        self._count = state["count"]
        self._filename_template = state["filename_template"]
        self._manual_filename_template = state["manual_filename_template"]
        self._use_date = state["use_date"]
        self._date_format_index = state["date_format_index"]
        self._custom_text = state["custom_text"]
        self._use_layer_name = state["use_layer_name"]
        self._layer_index = state["layer_index"]
        self._number_format_index = state["number_format_index"]
        self._file_format = state["file_format"]
        self._avoid_duplicates = state["avoid_duplicates"]
        self._start_index = state["start_index"]
        self._traverse_mode = state["traverse_mode"]
        self._max_file_size_kb = state["max_file_size_kb"]
        self._use_current_time_for_path = state["use_current_time_for_path"]
        self._unique_use_enabled = state["unique_use_enabled"]
        self._selected_unique_layers = set(state["selected_unique_layers"])
        self._use_high_performance = state["use_high_performance"]
        self._preload_enabled = state["preload_enabled"]
        self._quality_profile = state["quality_profile"]
        self._memory_guard_mode = state["memory_guard_mode"]
        self._memory_limit_mb = state["memory_limit_mb"]
        self._memory_reserve_mb = state["memory_reserve_mb"]
        self._max_consecutive_failures = state["max_consecutive_failures"]
        self._failure_rate_limit = state["failure_rate_limit"]
        self._stall_timeout_seconds = state["stall_timeout_seconds"]
        self._external_worker_enabled = state["external_worker_enabled"]
        self._succeeded = state["succeeded"]
        self._canceled = state["canceled"]
        self._current = state["current"]
        self._total = state["total"]
        self._stage = state["stage"]
        self._last_file = state["last_file"]
        self._error_message = state["error_message"]
        self._failure_summary = state["failure_summary"]
        self._refresh_traverse_count()
        if not self._manual_filename_template:
            self._filename_template = self._build_filename_template()

    @Slot(object)
    def setDocument(self, document) -> None:
        if document is self._document:
            return
        if self._running:
            return
        if self._document is not None:
            self._document_states[self._document] = self._snapshot_state()
        self._disconnect_document()
        self._document = document
        self._restore_state(self._document_states.get(document, self._state_from_document(document)))
        if self._document is not None:
            self._document.export_progress_updated.connect(self._on_progress)
            self._document.file_exported.connect(self._on_file_exported)
            self._document.export_stage_updated.connect(self._on_stage)
            self._document.layers_changed.connect(self._on_document_layers_changed)
        self.configChanged.emit()
        self.stateChanged.emit()
        self.documentChanged.emit()

    def _set_error(self, message: str) -> None:
        self._error_message = str(message or "")
        self._succeeded = False
        self._canceled = False
        self._stage = "配置有误"
        self.stateChanged.emit()

    @staticmethod
    def _format_degradation_summary(diagnostics) -> str:
        """把预计算诊断里的降级信息转成一句人话，无降级返回空串。

        数据来源是 ``document._last_precompute_diagnostics``，
        由 ``optimized_batch_executor`` 在预计算阶段写入。
        """
        if not isinstance(diagnostics, dict):
            return ""
        degradations = diagnostics.get("degradations")
        if not degradations:
            return ""
        try:
            total = int(diagnostics.get("degradation_total", 0) or 0)
        except (TypeError, ValueError):
            total = 0
        kinds = len(degradations)
        if total <= 0:
            total = kinds
        return f"有 {kinds} 类降级（共 {total} 次），结果可能不符合预期"

    @staticmethod
    def _format_adjustment_summary(adjustment) -> str:
        """把「实际导出数 < 请求数」的调整信息转成一句人话。

        用户填的是 500 张、实际只出了 300 张时，必须当场说明差额和原因，
        否则只会觉得「怎么少了一半」。
        """
        if not isinstance(adjustment, dict):
            return ""
        requested = adjustment.get("requested")
        planned = adjustment.get("planned")
        if not requested or planned is None:
            return ""
        try:
            requested_int = int(requested)
            planned_int = int(planned)
        except (TypeError, ValueError):
            return ""
        if planned_int >= requested_int:
            return ""
        message = f"实际导出 {planned_int} 张（请求 {requested_int} 张）"
        reasons = [
            str(reason).strip()
            for reason in (adjustment.get("reasons") or [])
            if str(reason).strip()
        ]
        if reasons:
            message += f"；原因：{'；'.join(reasons[:2])}"
        return message

    def _collect_export_settings(self) -> dict:
        format_index = self._INDEX_BY_FORMAT.get(self._file_format, 0)
        number_index = max(0, min(self._number_format_index, len(self._NUMBER_FORMATS) - 1))
        eligible_unique_layers = []
        if self._document is not None:
            eligible_unique_layers = [
                index
                for index in sorted(self._selected_unique_layers)
                if 0 <= index < len(self._document.layers)
                and self._is_unique_use_eligible_layer(self._document.layers[index])
            ]
        return {
            "count": self._count,
            "use_date": self._use_date,
            "date_format": self._DATE_FORMATS[max(0, min(self._date_format_index, 2))],
            "date_format_index": self._date_format_index,
            "custom_text": self._custom_text,
            "use_layer_name": self._use_layer_name,
            "layer_index": self._layer_index,
            "number_format": self._NUMBER_FORMATS[number_index],
            "number_format_index": number_index,
            "format": self._file_format,
            "format_index": format_index,
            "filename_template": self._current_filename_template(),
            "last_directory": self._output_directory,
            "directory": self._output_directory,
            "start_index": self._start_index,
            "use_high_performance": self._use_high_performance,
            "traverse_export": self._traverse_mode,
            "smart_sampling": self._avoid_duplicates,
            "max_file_size_kb": self._max_file_size_kb,
            "use_current_time_for_path": self._use_current_time_for_path,
            "export_quality_profile": self._quality_profile,
            "allow_lossy_size_reduction": self._quality_profile == "size",
            "export_backend": "pillow",
            "auto_runtime_tuning_enabled": True,
            "freeze_preview_during_export": True,
            "batch_preload_enabled": self._preload_enabled,
            "export_external_worker_enabled": self._external_worker_enabled,
            "export_safety_enabled": True,
            "export_safety_max_consecutive_failures": self._max_consecutive_failures,
            "export_safety_failure_rate_limit": self._failure_rate_limit / 100.0,
            "export_safety_stall_timeout_seconds": self._stall_timeout_seconds,
            "export_memory_guard_mode": self._memory_guard_mode,
            "export_memory_limit_mb": self._memory_limit_mb,
            "export_memory_reserve_mb": self._memory_reserve_mb,
            "unique_use_enabled": self._unique_use_enabled,
            "unique_use_layers": eligible_unique_layers,
            "dynamic_budget_enabled": True,
            "dynamic_budget_binding_enabled": True,
            "dynamic_budget_standard_enabled": True,
            "dynamic_budget_recent_n": 12,
            "batch_export_settings_saved": True,
        }

    def _persist_settings(self, mark_document: bool = False) -> bool:
        if self._document is None:
            return False
        self._document.export_settings.update(self._collect_export_settings())
        if mark_document:
            if hasattr(self._document, "set_modified"):
                self._document.set_modified(True)
            else:
                self._document.is_modified = True
            save_state = getattr(self._document, "save_state", None)
            if callable(save_state):
                save_state("保存批量导出设置")
        return True

    @Slot(result=bool)
    def saveSettings(self) -> bool:
        return self._persist_settings(mark_document=True)

    def _validate(self) -> bool:
        if self._document is None:
            self._set_error("当前没有可导出的文档")
            return False
        if not self._output_directory:
            self._set_error("请选择输出目录")
            return False
        if self._unique_use_enabled:
            has_selected_unique_layer = any(
                0 <= index < len(self._document.layers)
                and self._is_unique_use_eligible_layer(self._document.layers[index])
                for index in self._selected_unique_layers
            )
            if not has_selected_unique_layer:
                self._set_error("单次用图至少选择一个可用的图片图层")
                return False
        self._refresh_traverse_count()
        if self._traverse_mode and self._traverse_error:
            self._set_error(f"无法计算组合数量：{self._traverse_error}")
            return False
        if self._traverse_mode and self._traverse_count <= 0:
            self._set_error("没有可导出的组合")
            return False
        if not self._traverse_mode and not 1 <= self._count <= 10000:
            self._set_error("导出数量必须在 1 到 10000 之间")
            return False
        if not 0 <= self._start_index <= 999999999:
            self._set_error("起始序号必须在 0 到 999999999 之间")
            return False
        if not self._current_filename_template():
            self._set_error("文件名模板不能为空")
            return False
        if self._file_format not in {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}:
            self._set_error("不支持的导出格式")
            return False
        if self._quality_profile not in {"quality", "balanced", "speed", "size"}:
            self._set_error("不支持的质量策略")
            return False
        if self._memory_guard_mode not in {"auto", "low", "custom", "off"}:
            self._set_error("不支持的内存保护模式")
            return False
        if self._memory_limit_mb < 0 or self._memory_reserve_mb < 256:
            self._set_error("内存限制参数无效")
            return False
        if not 0 <= self._max_file_size_kb <= 102400:
            self._set_error("最大文件大小必须在 0 到 102400 KB 之间")
            return False
        if not 1 <= self._max_consecutive_failures <= 100:
            self._set_error("连续失败阈值必须在 1 到 100 之间")
            return False
        if not 1 <= self._failure_rate_limit <= 100:
            self._set_error("失败率阈值必须在 1% 到 100% 之间")
            return False
        if not 30 <= self._stall_timeout_seconds <= 3600:
            self._set_error("停滞超时必须在 30 到 3600 秒之间")
            return False
        try:
            Path(self._resolved_output_directory()).mkdir(parents=True, exist_ok=True)
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

        export_count = self.effectiveCount
        export_directory = self._resolved_output_directory()
        filename_template = self._current_filename_template()
        self._cancel_event = threading.Event()
        self._running = True
        self._succeeded = False
        self._canceled = False
        self._current = 0
        self._total = export_count
        self._stage = "准备导出"
        self._last_file = ""
        self._error_message = ""
        self._failure_summary = ""
        self._degradation_summary = ""
        self._adjustment_summary = ""
        self._document._export_canceled = False
        self._workspace.setExportRunning(True)
        self.stateChanged.emit()

        self._persist_settings(mark_document=False)
        parameters = {
            "directory": export_directory,
            "count": export_count,
            "filename_template": filename_template,
            "file_format": self._file_format,
            "start_index": self._start_index,
            "use_high_performance": self._use_high_performance,
            "traverse_mode": self._traverse_mode,
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
    def retryExport(self) -> bool:
        if not self.canRetry:
            return False
        return self.startExport()

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
        if not self._running:
            return
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
        # 降级 / 数量调整提示：取消不算，用户主动停的没有「结果不符合预期」问题。
        self._degradation_summary = ""
        self._adjustment_summary = ""
        if not canceled and self._document is not None:
            self._degradation_summary = self._format_degradation_summary(
                getattr(self._document, "_last_precompute_diagnostics", None)
            )
            self._adjustment_summary = self._format_adjustment_summary(
                getattr(self._document, "_last_export_adjustment", None)
            )
        report = getattr(self._document, "_last_export_report", None)
        if isinstance(report, dict):
            failed = int(report.get("failed_count", report.get("failed", 0)) or 0)
            exported = int(report.get("exported_count", report.get("completed", self._current)) or 0)
            skipped = int(report.get("skipped_count", report.get("skipped", 0)) or 0)
            if failed or skipped:
                self._failure_summary = f"成功 {exported}，失败 {failed}，跳过 {skipped}"
        if not self._failure_summary and self._error_message:
            self._failure_summary = self._error_message
        self.stateChanged.emit()

    @Slot(result=bool)
    def openOutputDirectory(self) -> bool:
        output_directory = self._resolved_output_directory()
        if not output_directory or not os.path.isdir(output_directory):
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(output_directory)))
