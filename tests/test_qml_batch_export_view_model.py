from __future__ import annotations

import datetime
import time
from pathlib import Path

import pytest
from PIL import Image

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _wait_until(qapp, predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    qapp.processEvents()
    assert predicate(), "等待异步批量导出状态超时"


def _workspace() -> WorkspaceViewModel:
    document = Document()
    document.create_new(120, 90)
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


@pytest.mark.unit
def test_batch_export_rejects_invalid_parameters(tmp_path: Path):
    workspace = _workspace()
    view_model = BatchExportViewModel(workspace=workspace)

    view_model.outputDirectory = ""
    assert view_model.startExport() is False
    assert "输出目录" in view_model.errorMessage

    view_model.outputDirectory = str(tmp_path)
    view_model.count = 0
    assert view_model.startExport() is False
    assert "1 到 10000" in view_model.errorMessage

    view_model.count = 2
    view_model.filenameTemplate = "  "
    assert view_model.startExport() is False
    assert "文件名模板" in view_model.errorMessage


@pytest.mark.unit
def test_batch_export_requires_selected_layer_for_unique_use(tmp_path: Path):
    workspace = _workspace()
    view_model = BatchExportViewModel(workspace=workspace)
    view_model.outputDirectory = str(tmp_path)
    view_model.uniqueUseEnabled = True

    assert view_model.startExport() is False
    assert "至少选择一个可用的图片图层" in view_model.errorMessage


@pytest.mark.unit
def test_batch_export_tracks_progress_and_success(qapp, tmp_path: Path):
    workspace = _workspace()

    def runner(document, **kwargs):
        assert kwargs["directory"] == str(tmp_path)
        assert kwargs["count"] == 3
        assert kwargs["filename_template"] == "产品_{number:03d}"
        assert kwargs["file_format"] == "webp"
        assert kwargs["use_smart_sampling"] is False
        document.export_stage_updated.emit("生成画面")
        document.export_progress_updated.emit(2)
        document.file_exported.emit(str(tmp_path / "产品_002.webp"))
        document.export_progress_updated.emit(3)
        return True

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.count = 3
    view_model.filenameTemplate = "产品_{number:03d}"
    view_model.fileFormat = "WEBP"
    view_model.avoidDuplicates = False

    assert view_model.startExport() is True
    assert view_model.running is True
    assert workspace.exportRunning is True
    _wait_until(qapp, lambda: not view_model.running)

    assert view_model.succeeded is True
    assert view_model.current == 3
    assert view_model.total == 3
    assert view_model.progress == pytest.approx(1.0)
    assert view_model.stage == "导出完成"
    assert view_model.lastFile.endswith("产品_002.webp")
    assert view_model.errorMessage == ""
    assert workspace.exportRunning is False


@pytest.mark.unit
def test_batch_export_passes_advanced_runtime_and_safety_settings(qapp, tmp_path: Path):
    workspace = _workspace()

    def runner(document, **kwargs):
        assert kwargs["start_index"] == 42
        assert kwargs["traverse_mode"] is True
        assert kwargs["use_high_performance"] is True
        assert kwargs["use_smart_sampling"] is True
        settings = document.export_settings
        assert settings["batch_preload_enabled"] is False
        assert settings["export_quality_profile"] == "balanced"
        assert settings["export_external_worker_enabled"] is False
        assert settings["export_memory_guard_mode"] == "custom"
        assert settings["export_memory_limit_mb"] == 4096
        assert settings["export_memory_reserve_mb"] == 1024
        assert settings["export_safety_max_consecutive_failures"] == 5
        assert settings["export_safety_failure_rate_limit"] == pytest.approx(0.25)
        assert settings["export_safety_stall_timeout_seconds"] == 90
        return True

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.startIndex = 42
    view_model.traverseMode = True
    view_model.preloadEnabled = False
    view_model.qualityProfile = "balanced"
    view_model.externalWorkerEnabled = False
    view_model.memoryGuardMode = "custom"
    view_model.memoryLimitMB = 4096
    view_model.memoryReserveMB = 1024
    view_model.maxConsecutiveFailures = 5
    view_model.failureRateLimit = 25
    view_model.stallTimeoutSeconds = 90

    assert view_model.startExport() is True
    _wait_until(qapp, lambda: not view_model.running)
    assert view_model.succeeded is True


@pytest.mark.unit
def test_batch_export_validates_advanced_settings(tmp_path: Path):
    workspace = _workspace()
    view_model = BatchExportViewModel(workspace=workspace)
    view_model.outputDirectory = str(tmp_path)

    view_model.startIndex = -1
    assert view_model.startExport() is False
    assert "起始序号" in view_model.errorMessage
    view_model.startIndex = 1
    view_model.memoryReserveMB = 128
    assert view_model.startExport() is False
    assert "内存" in view_model.errorMessage
    view_model.memoryReserveMB = 2048
    view_model.stallTimeoutSeconds = 10
    assert view_model.startExport() is False
    assert "停滞" in view_model.errorMessage


@pytest.mark.unit
def test_batch_export_builds_failure_summary_and_can_retry(qapp, tmp_path: Path):
    workspace = _workspace()
    attempts = []

    def runner(document, **kwargs):
        attempts.append(kwargs["start_index"])
        if len(attempts) == 1:
            document._last_export_report = {
                "exported_count": 2,
                "failed_count": 1,
                "skipped_count": 1,
            }
            document._last_export_error = "部分任务失败"
            return False
        return True

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.startIndex = 8
    assert view_model.startExport() is True
    _wait_until(qapp, lambda: not view_model.running)
    assert view_model.canRetry is True
    assert view_model.failureSummary == "成功 2，失败 1，跳过 1"
    assert view_model.retryExport() is True
    _wait_until(qapp, lambda: not view_model.running)
    assert view_model.succeeded is True
    assert attempts == [8, 8]


@pytest.mark.unit
def test_batch_export_cancel_propagates_and_preserves_canceled_state(qapp, tmp_path: Path):
    workspace = _workspace()

    def runner(document, **kwargs):
        document.export_stage_updated.emit("生成画面")
        while not kwargs["cancel_callback"]():
            time.sleep(0.01)
        document._last_export_error = "导出已取消"
        return False

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.count = 20

    assert view_model.startExport() is True
    _wait_until(qapp, lambda: view_model.stage == "生成画面")
    assert view_model.cancelExport() is True
    _wait_until(qapp, lambda: not view_model.running)

    assert view_model.canceled is True
    assert view_model.succeeded is False
    assert view_model.stage == "已取消"
    assert "取消" in view_model.statusText


@pytest.mark.unit
def test_batch_export_surfaces_runner_failure(qapp, tmp_path: Path):
    workspace = _workspace()

    def runner(document, **kwargs):
        raise RuntimeError("磁盘不可写")

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)

    assert view_model.startExport() is True
    _wait_until(qapp, lambda: not view_model.running)

    assert view_model.succeeded is False
    assert view_model.canceled is False
    assert view_model.stage == "导出失败"
    assert "磁盘不可写" in view_model.errorMessage


@pytest.mark.unit
def test_batch_export_follows_document_and_blocks_workspace_edits(qapp, tmp_path: Path):
    workspace = _workspace()

    def runner(document, **kwargs):
        while not kwargs["cancel_callback"]():
            time.sleep(0.01)
        return False

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    original = view_model.document
    assert workspace.newDocument(300, 240) is True
    assert view_model.document is workspace.document
    assert view_model.document is not original

    view_model.outputDirectory = str(tmp_path)
    assert view_model.startExport() is True
    assert workspace.addTextLayer() is False
    assert workspace.newDocument(640, 480) is False
    assert workspace.document is view_model.document
    assert "导出" in workspace.statusMessage

    view_model.cancelExport()
    _wait_until(qapp, lambda: not view_model.running)
    assert workspace.addTextLayer() is True


@pytest.mark.unit
def test_batch_export_state_is_isolated_per_document(tmp_path: Path):
    workspace = _workspace()
    first = workspace.document
    second = Document()
    second.create_new(300, 240)
    view_model = BatchExportViewModel(workspace=workspace)

    view_model.outputDirectory = str(tmp_path / "first")
    view_model.count = 7
    view_model.filenameTemplate = "first_{number:02d}"
    view_model.fileFormat = "webp"
    view_model.avoidDuplicates = False
    view_model._set_error("第一个文档的错误")

    assert workspace.activateDocument(second) is True
    assert view_model.document is second
    assert view_model.outputDirectory == ""
    assert view_model.count == 10
    assert view_model.customText == "export"
    assert view_model.filenameTemplate.endswith("-export-{number:04d}")
    assert view_model.fileFormat == "png"
    assert view_model.avoidDuplicates is True
    assert view_model.errorMessage == ""

    view_model.outputDirectory = str(tmp_path / "second")
    view_model.count = 3
    view_model.filenameTemplate = "second_{number}"

    assert workspace.activateDocument(first) is True
    assert view_model.outputDirectory == str(tmp_path / "first")
    assert view_model.count == 7
    assert view_model.filenameTemplate == "first_{number:02d}"
    assert view_model.fileFormat == "webp"
    assert view_model.avoidDuplicates is False
    assert view_model.errorMessage == "第一个文档的错误"

    assert workspace.activateDocument(second) is True
    assert view_model.outputDirectory == str(tmp_path / "second")
    assert view_model.count == 3
    assert view_model.filenameTemplate == "second_{number}"
    assert view_model.errorMessage == ""


@pytest.mark.unit
def test_batch_export_restores_legacy_document_settings(tmp_path: Path):
    workspace = _workspace()
    workspace.document.export_settings.update(
        {
            "batch_export_settings_saved": True,
            "last_directory": str(tmp_path / "legacy"),
            "count": 7,
            "use_date": False,
            "custom_text": "旧版导出",
            "use_layer_name": False,
            "number_format_index": 2,
            "format_index": 2,
            "traverse_export": True,
            "smart_sampling": False,
            "max_file_size_kb": 512,
            "use_current_time_for_path": True,
        }
    )

    view_model = BatchExportViewModel(workspace=workspace)

    assert view_model.outputDirectory == str(tmp_path / "legacy")
    assert view_model.count == 7
    assert view_model.useDate is False
    assert view_model.customText == "旧版导出"
    assert view_model.numberFormatIndex == 2
    assert view_model.filenameTemplate == "旧版导出-{number:02d}"
    assert view_model.fileFormat == "bmp"
    assert view_model.traverseMode is True
    assert view_model.avoidDuplicates is False
    assert view_model.maxFileSizeKB == 512
    assert view_model.useCurrentTimeForPath is True


@pytest.mark.unit
def test_traverse_mode_uses_all_possible_combinations(qapp, tmp_path: Path):
    workspace = _workspace()
    workspace.document._calculate_possible_combinations = lambda: 27

    def runner(document, **kwargs):
        assert kwargs["count"] == 27
        assert kwargs["traverse_mode"] is True
        return True

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.count = 2
    view_model.traverseMode = True

    assert view_model.effectiveCount == 27
    assert "27" in view_model.traverseCountText
    assert view_model.startExport() is True
    _wait_until(qapp, lambda: not view_model.running)
    assert view_model.total == 27
    assert view_model.succeeded is True


@pytest.mark.unit
def test_legacy_filename_path_and_unique_layer_settings_are_applied(qapp, tmp_path: Path):
    source = tmp_path / "产品主图.png"
    Image.new("RGBA", (24, 24), (60, 130, 210, 255)).save(source)
    workspace = _workspace()
    workspace.document.add_layer(
        "产品图",
        0,
        0,
        24,
        24,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    today = datetime.datetime.now().strftime("%Y%m%d")
    raw_output = tmp_path / "20240101" / "exports"

    def runner(document, **kwargs):
        assert Path(kwargs["directory"]).parts[-2:] == (today, "exports")
        assert kwargs["filename_template"] == "产品-{layer:0}-{number:03d}"
        assert kwargs["file_format"] == "bmp"
        assert kwargs["use_smart_sampling"] is False
        settings = document.export_settings
        assert settings["max_file_size_kb"] == 640
        assert settings["use_current_time_for_path"] is True
        assert settings["unique_use_enabled"] is True
        assert settings["unique_use_layers"] == [0]
        assert settings["batch_export_settings_saved"] is True
        return True

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(raw_output)
    view_model.useCurrentTimeForPath = True
    view_model.useDate = False
    view_model.customText = "产品"
    view_model.useLayerName = True
    view_model.layerIndex = 0
    view_model.numberFormatIndex = 1
    view_model.fileFormat = "bmp"
    view_model.maxFileSizeKB = 640
    view_model.avoidDuplicates = False
    view_model.uniqueUseEnabled = True
    assert view_model.setUniqueLayerSelected(0, True) is True

    assert view_model.filenameTemplate == "产品-{layer:0}-{number:03d}"
    assert view_model.filenamePreview.endswith(".bmp")
    assert "产品主图" in view_model.filenamePreview
    assert view_model.saveSettings() is True
    assert workspace.document.export_settings["custom_text"] == "产品"
    assert view_model.startExport() is True
    _wait_until(qapp, lambda: not view_model.running)
    assert view_model.succeeded is True


@pytest.mark.integration
def test_batch_export_runs_real_document_pipeline(qapp, tmp_path: Path):
    source = tmp_path / "source.png"
    Image.new("RGBA", (48, 36), (30, 145, 112, 255)).save(source)
    document = Document()
    document.create_new(96, 72)
    document.add_layer(
        "产品",
        10,
        8,
        48,
        36,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    view_model = BatchExportViewModel(workspace=workspace)
    output = tmp_path / "exports"
    view_model.outputDirectory = str(output)
    view_model.count = 2
    view_model.filenameTemplate = "real_{number:02d}"
    view_model.fileFormat = "png"
    view_model.avoidDuplicates = False

    assert view_model.startExport() is True
    _wait_until(qapp, lambda: not view_model.running, timeout=30.0)

    assert view_model.succeeded is True
    files = sorted(output.glob("real_*.png"))
    assert len(files) == 2
    with Image.open(files[0]) as image:
        assert image.size == (96, 72)
