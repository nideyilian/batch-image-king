from __future__ import annotations

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
    view_model.avoidDuplicates = False

    assert view_model.startExport() is True
    _wait_until(qapp, lambda: not view_model.running, timeout=30.0)

    assert view_model.succeeded is True
    files = sorted(output.glob("real_*.png"))
    assert len(files) == 2
    with Image.open(files[0]) as image:
        assert image.size == (96, 72)
