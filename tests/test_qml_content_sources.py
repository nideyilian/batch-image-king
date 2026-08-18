from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Optional, Tuple

from PIL import Image
import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(document: Optional[Document] = None) -> WorkspaceViewModel:
    if document is None:
        document = Document()
        document.create_new(320, 240)
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


def _write_image(path: Path, color: Tuple[int, int, int, int], size=(80, 60)) -> None:
    mode = "RGB" if path.suffix.lower() in {".jpg", ".jpeg"} else "RGBA"
    Image.new(mode, size, color[:3] if mode == "RGB" else color).save(path)


def _source_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "product-assets"
    folder.mkdir()
    _write_image(folder / "01-red.png", (220, 70, 60, 255))
    _write_image(folder / "02-green.png", (45, 170, 115, 255))
    _write_image(folder / "03-blue.jpg", (55, 95, 200, 255))
    (folder / "notes.txt").write_text("not an image", encoding="utf-8")
    return folder


def _wait_until(qapp, predicate, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    qapp.processEvents()
    assert predicate(), "等待真实内容源批量导出超时"


@pytest.mark.unit
def test_workspace_adds_folder_source_layer_and_cycles_preview(tmp_path: Path):
    folder = _source_folder(tmp_path)
    workspace = _workspace()

    assert workspace.addImageFolder(str(folder)) is True
    assert workspace.selectedIsImageLayer is True
    assert workspace.selectedIsTextLayer is False
    assert os.path.normcase(workspace.selectedImageSource) == os.path.normcase(str(folder))
    assert workspace.selectedImageSourceIsFolder is True
    assert workspace.selectedImageSourceCount == 3
    assert workspace.selectedImageCurrentFile == "01-red.png"
    assert workspace.layerModel.rowCount() == 1

    assert workspace.showNextSelectedImage() is True
    assert workspace.selectedImageCurrentFile == "02-green.png"
    assert Path(workspace.document.layers[0].current_image_path).name == "02-green.png"


@pytest.mark.unit
def test_workspace_replaces_image_source_and_rejects_empty_folder(tmp_path: Path):
    original = tmp_path / "original.png"
    _write_image(original, (60, 120, 180, 255))
    document = Document()
    document.create_new(320, 240)
    document.add_layer(
        "原图",
        20,
        30,
        80,
        60,
        image_source=str(original),
        use_original_size=False,
        is_folder=False,
    )
    document._history_manager.clear()
    workspace = _workspace(document)
    folder = _source_folder(tmp_path)

    assert workspace.setSelectedImageSource(str(folder)) is True
    assert document.layers[0].is_folder is True
    assert workspace.selectedImageSourceCount == 3

    empty = tmp_path / "empty"
    empty.mkdir()
    assert workspace.setSelectedImageSource(str(empty)) is False
    assert os.path.normcase(document.layers[0].image_source) == os.path.normcase(str(folder))
    assert "没有可用图片" in workspace.statusMessage

    assert workspace.undo() is True
    assert document.layers[0].is_folder is False
    assert os.path.normcase(document.layers[0].image_source) == os.path.normcase(str(original))


@pytest.mark.unit
def test_workspace_edits_text_candidates_layout_mode_and_font_size():
    document = Document()
    document.create_new(320, 240)
    text_layer = TextLayer(name="标题", x=20, y=30, width=220, height=80)
    document.add_text_layer(text_layer)
    document._history_manager.clear()
    workspace = _workspace(document)

    assert workspace.selectedIsTextLayer is True
    assert workspace.setSelectedTextContent("春季上新\n限时特惠\n新品首发") is True
    assert workspace.selectedTextBindingEnabled is True
    assert workspace.selectedTextCandidateCount == 3
    assert text_layer.get_text_lines() == ["春季上新", "限时特惠", "新品首发"]
    assert text_layer.current_text == "春季上新"

    assert workspace.setSelectedTextBindingEnabled(False) is True
    assert workspace.selectedTextCandidateCount == 1
    assert workspace.selectedTextContent == "春季上新\n限时特惠\n新品首发"

    assert workspace.setSelectedTextContent("第一行\n第二行") is True
    assert text_layer.get_text_lines() == ["第一行\n第二行"]
    assert text_layer.current_text == "第一行\n第二行"
    assert workspace.setSelectedTextFontSize(42) is True
    assert workspace.selectedTextFontSize == 42

    assert workspace.undo() is True
    assert workspace.selectedTextFontSize != 42


@pytest.mark.unit
def test_text_commit_targets_original_layer_after_selection_changes():
    document = Document()
    document.create_new(320, 240)
    first = TextLayer(name="第一层", x=10, y=10, width=180, height=50)
    second = TextLayer(name="第二层", x=10, y=80, width=180, height=50)
    document.add_text_layer(first)
    document.add_text_layer(second)
    workspace = _workspace(document)
    workspace.selectLayer(1)

    assert workspace.setTextContentForLayer(0, "旧编辑器提交") is True
    assert first.current_text == "旧编辑器提交"
    assert second.current_text != "旧编辑器提交"
    assert workspace.selectedLayerIndex == 1


@pytest.mark.unit
def test_content_source_commands_respect_layer_type_and_lock(tmp_path: Path):
    folder = _source_folder(tmp_path)
    document = Document()
    document.create_new(320, 240)
    text_layer = TextLayer(name="锁定文字", x=10, y=10, width=180, height=60)
    text_layer.locked = True
    document.add_text_layer(text_layer)
    workspace = _workspace(document)

    assert workspace.setSelectedImageSource(str(folder)) is False
    assert workspace.setSelectedTextContent("不能修改") is False
    assert workspace.addImageFolder(str(tmp_path / "missing")) is False
    assert text_layer.current_text != "不能修改"


@pytest.mark.unit
def test_content_sources_survive_document_save_round_trip(tmp_path: Path):
    folder = _source_folder(tmp_path)
    workspace = _workspace()
    assert workspace.addImageFolder(str(folder)) is True
    assert workspace.addTextLayer() is True
    assert workspace.setSelectedTextContent("文案 A\n文案 B") is True
    assert workspace.setSelectedTextBindingEnabled(True) is True
    assert workspace.setSelectedTextFontSize(36) is True

    project = tmp_path / "content-sources.cmp"
    assert workspace.saveDocumentTo(str(project)) is True

    loaded = _workspace()
    assert loaded.openDocument(str(project)) is True
    image_layer = loaded.document.layers[0]
    text_layer = loaded.document.layers[1]
    assert image_layer.is_folder is True
    assert os.path.normcase(image_layer.image_source) == os.path.normcase(str(folder))
    assert text_layer.get_text_lines() == ["文案 A", "文案 B"]
    assert text_layer.text_binding_enabled is True
    assert text_layer.font_size == 36


@pytest.mark.integration
def test_folder_source_produces_distinct_real_batch_outputs(qapp, tmp_path: Path):
    folder = _source_folder(tmp_path)
    workspace = _workspace()
    assert workspace.addImageFolder(str(folder)) is True
    batch_export = BatchExportViewModel(workspace=workspace)
    output = tmp_path / "batch"
    batch_export.outputDirectory = str(output)
    batch_export.filenameTemplate = "folder_{number:02d}"
    batch_export.count = 2
    batch_export.avoidDuplicates = True

    assert batch_export.startExport() is True
    _wait_until(qapp, lambda: not batch_export.running)

    assert batch_export.succeeded is True
    files = sorted(output.glob("folder_*.png"))
    assert len(files) == 2
    assert files[0].read_bytes() != files[1].read_bytes()
