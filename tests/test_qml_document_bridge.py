from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize
import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.layer_list_model import LayerListModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _image_document(tmp_path: Path) -> Document:
    source = tmp_path / "source.png"
    Image.new("RGBA", (80, 60), (36, 142, 118, 255)).save(source)
    document = Document()
    document.create_new(240, 180)
    document.add_layer(
        "产品图",
        12,
        18,
        80,
        60,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    return document


@pytest.mark.unit
def test_layer_model_exposes_stable_qml_roles(tmp_path: Path):
    document = _image_document(tmp_path)
    document.add_text_layer(TextLayer(name="标题", x=20, y=90, width=120, height=36))
    model = LayerListModel(document)

    assert model.rowCount() == 2
    roles = {bytes(value).decode("ascii"): key for key, value in model.roleNames().items()}
    text_index = model.index(0, 0)
    image_index = model.index(1, 0)

    assert model.data(image_index, roles["name"]) == "产品图"
    assert model.data(image_index, roles["typeName"]) == "图片"
    assert model.data(image_index, roles["shown"]) is True
    assert model.data(text_index, roles["typeName"]) == "文字"
    assert model.data(text_index, roles["glyph"])
    assert model.data(text_index, roles["layerIndex"]) == 1
    assert model.data(image_index, roles["layerIndex"]) == 0


@pytest.mark.unit
def test_workspace_property_command_supports_undo_and_redo(tmp_path: Path):
    document = _image_document(tmp_path)
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    workspace.selectLayer(0)
    workspace.setSelectedX(48)
    workspace.setSelectedOpacity(64)

    assert document.layers[0].x == 48
    assert document.layers[0].opacity == pytest.approx(0.64)
    assert workspace.canUndo is True

    workspace.undo()
    assert document.layers[0].opacity == pytest.approx(1.0)
    workspace.undo()
    assert document.layers[0].x == 12

    workspace.redo()
    workspace.redo()
    assert document.layers[0].x == 48
    assert document.layers[0].opacity == pytest.approx(0.64)


@pytest.mark.unit
def test_workspace_save_and_open_round_trip(tmp_path: Path):
    document = _image_document(tmp_path)
    path = tmp_path / "qml-roundtrip.cmp"
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    assert workspace.saveDocumentTo(str(path)) is True
    assert workspace.documentTitle == "qml-roundtrip.cmp"

    loaded_workspace = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded_workspace.openDocument(str(path)) is True
    assert loaded_workspace.layerModel.rowCount() == 1
    assert loaded_workspace.canvasWidth == 240
    assert loaded_workspace.canvasHeight == 180
    assert loaded_workspace.isModified is False


@pytest.mark.unit
def test_invalid_open_keeps_current_document(tmp_path: Path):
    document = _image_document(tmp_path)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    assert workspace.openDocument(str(tmp_path / "missing.cmp")) is False
    assert workspace.document is document
    assert "失败" in workspace.statusMessage


@pytest.mark.unit
def test_workspace_can_add_text_image_and_delete_selected_layer(tmp_path: Path):
    workspace = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.newDocument(320, 240)
    source = tmp_path / "added.png"
    Image.new("RGBA", (120, 80), (210, 80, 62, 255)).save(source)

    assert workspace.addTextLayer() is True
    assert workspace.selectedLayerType == "文字"
    assert workspace.addImageLayer(str(source)) is True
    assert workspace.layerModel.rowCount() == 2
    assert workspace.selectedLayerType == "图片"
    assert workspace.deleteSelectedLayer() is True
    assert workspace.layerModel.rowCount() == 1
    assert workspace.isModified is True


@pytest.mark.unit
def test_workspace_can_toggle_visibility_and_locking(tmp_path: Path):
    document = _image_document(tmp_path)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    assert workspace.toggleLayerVisible(0) is True
    assert document.layers[0].visible is False
    assert workspace.toggleLayerLocked(0) is True
    assert document.layers[0].locked is True
    assert workspace.deleteSelectedLayer() is False
    assert len(document.layers) == 1


@pytest.mark.unit
def test_workspace_selects_topmost_layer_at_canvas_point(tmp_path: Path):
    document = _image_document(tmp_path)
    document.add_text_layer(TextLayer(name="上层", x=20, y=20, width=80, height=50))
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    assert workspace.selectLayerAt(30, 30) == 1
    assert workspace.selectedLayerName == "上层"
    assert workspace.selectLayerAt(220, 170) == -1
    assert workspace.selectedLayerIndex == -1


@pytest.mark.unit
def test_workspace_hit_test_accounts_for_layer_rotation(tmp_path: Path):
    document = _image_document(tmp_path)
    layer = document.layers[0]
    layer.x = 50
    layer.y = 50
    layer.width = 100
    layer.height = 40
    layer.rotation = 90
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    assert workspace.selectLayerAt(100, 25) == 0
    assert workspace.selectLayerAt(55, 55) == -1


@pytest.mark.unit
def test_workspace_geometry_commit_is_atomic_and_respects_lock(tmp_path: Path):
    document = _image_document(tmp_path)
    document._history_manager.clear()
    document.save_state("初始状态")
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.selectLayer(0)

    assert workspace.applySelectedGeometry(30, 40, 100, 90) is True
    assert (document.layers[0].x, document.layers[0].y) == (30, 40)
    assert (document.layers[0].width, document.layers[0].height) == (100, 90)
    assert workspace.undo() is True
    assert (document.layers[0].x, document.layers[0].y) == (12, 18)
    assert (document.layers[0].width, document.layers[0].height) == (80, 60)

    document.layers[0].locked = True
    assert workspace.applySelectedGeometry(1, 2, 30, 40) is False
    assert (document.layers[0].x, document.layers[0].y) == (12, 18)


@pytest.mark.unit
def test_workspace_rename_rotation_and_alignment_commands(tmp_path: Path):
    document = _image_document(tmp_path)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.selectLayer(0)

    assert workspace.setSelectedName("主产品") is True
    assert workspace.selectedLayerName == "主产品"
    assert workspace.selectedCanRotate is True
    assert workspace.setSelectedRotation(450.0) is True
    assert workspace.selectedRotation == pytest.approx(90.0)
    assert workspace.alignSelected("left") is True
    assert document.layers[0].x == 0
    assert workspace.alignSelected("hcenter") is True
    assert document.layers[0].x == 80
    assert workspace.alignSelected("vcenter") is True
    assert document.layers[0].y == 60

    document.add_text_layer(TextLayer(name="文字", x=0, y=0, width=80, height=30))
    workspace.selectLayer(1)
    assert workspace.selectedCanRotate is False
    assert workspace.setSelectedRotation(30.0) is False


@pytest.mark.integration
def test_workspace_exports_real_document_image(tmp_path: Path):
    document = _image_document(tmp_path)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    output = tmp_path / "qml-export.png"

    assert workspace.exportImageTo(str(output)) is True
    with Image.open(output) as image:
        assert image.size == (240, 180)
        assert image.mode == "RGBA"


@pytest.mark.integration
def test_real_preview_is_published_through_image_provider(tmp_path: Path):
    document = _image_document(tmp_path)
    provider = PreviewImageProvider()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=provider,
        auto_render=False,
    )

    assert workspace.renderPreviewNow() is True
    size = QSize()
    image = provider.requestImage("current", size, QSize())

    assert workspace.previewRevision == 1
    assert workspace.previewSource.startswith("image://documentPreview/current?")
    assert not image.isNull()
    assert image.size() == QSize(240, 180)
    assert image.pixelColor(30, 30).alpha() > 0
    assert workspace.busy is False
