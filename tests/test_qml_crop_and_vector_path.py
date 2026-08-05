from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from app.models.document import Document
from app.models.layer_new import Layer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(image_path: Path) -> tuple[WorkspaceViewModel, Layer]:
    document = Document()
    document.create_new(240, 180)
    layer = document.add_layer(
        "裁剪素材",
        20,
        20,
        160,
        120,
        image_source=str(image_path),
        is_folder=False,
    )
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    return workspace, layer


@pytest.fixture
def split_image(tmp_path: Path) -> Path:
    path = tmp_path / "split.png"
    image = Image.new("RGBA", (200, 100), (220, 30, 30, 255))
    image.paste((20, 60, 230, 255), (100, 0, 200, 100))
    image.save(path)
    return path


@pytest.mark.unit
def test_free_crop_commands_validate_undo_and_round_trip(split_image: Path, tmp_path: Path):
    workspace, layer = _workspace(split_image)

    assert workspace.selectedSupportsFreeCrop is True
    assert workspace.selectedCropRect == [0.0, 0.0, 1.0, 1.0]
    assert workspace.startCropEdit() is True
    assert workspace.cropEditing is True
    assert workspace.updateCropRect(0.5, -1.0, 2.0, 1.0) is True
    assert workspace.selectedCropRect == [0.5, 0.0, 1.0, 1.0]
    assert workspace.confirmCropEdit() is True
    assert workspace.cropEditing is False
    assert layer.crop_rect == [0.5, 0.0, 1.0, 1.0]

    assert workspace.undo() is True
    assert workspace.selectedCropRect == [0.0, 0.0, 1.0, 1.0]
    assert workspace.redo() is True
    assert workspace.selectedCropRect == [0.5, 0.0, 1.0, 1.0]

    project = tmp_path / "crop.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    loaded = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
    assert loaded.openDocument(str(project)) is True
    assert loaded.selectedCropRect == [0.5, 0.0, 1.0, 1.0]


@pytest.mark.integration
def test_free_crop_changes_real_image_pixels(split_image: Path):
    workspace, layer = _workspace(split_image)
    layer.fit_mode = Layer.FIT_SMART_CROP
    before = layer.get_image().copy()
    assert before.getpixel((5, before.height // 2))[0] > 150

    assert workspace.startCropEdit() is True
    assert workspace.updateCropRect(0.5, 0.0, 1.0, 1.0) is True
    assert workspace.confirmCropEdit() is True
    after = layer.get_image().copy()

    center = after.getpixel((after.width // 2, after.height // 2))
    assert center[2] > 180
    assert center[0] < 80


@pytest.mark.unit
def test_crop_cancel_restores_original_value(split_image: Path):
    workspace, layer = _workspace(split_image)
    assert workspace.startCropEdit() is True
    assert workspace.updateCropRect(0.1, 0.2, 0.8, 0.9) is True
    assert layer.crop_rect == [0.1, 0.2, 0.8, 0.9]
    assert workspace.cancelCropEdit() is True
    assert layer.crop_rect == [0.0, 0.0, 1.0, 1.0]
    assert workspace.canUndo is False


@pytest.mark.unit
def test_vector_path_commands_cover_nodes_handles_and_serialization(split_image: Path, tmp_path: Path):
    workspace, layer = _workspace(split_image)

    assert workspace.convertSelectedToVectorPath() is True
    assert workspace.selectedVectorPathEnabled is True
    assert workspace.selectedVectorPathMode == "bezier"
    assert len(workspace.selectedVectorNodes) == 4

    assert workspace.selectVectorNode(0) is True
    assert workspace.selectedVectorNodeIndex == 0
    assert workspace.moveSelectedVectorNode(0, 12.0, 8.0) is True
    assert workspace.selectedVectorNodes[0]["x"] == pytest.approx(12.0)
    assert workspace.setSelectedVectorNodeType("smooth") is True
    assert workspace.selectedVectorNodes[0]["node_type"] == "smooth"
    assert workspace.insertVectorNodeAfter(0) is True
    assert len(workspace.selectedVectorNodes) == 5
    assert workspace.deleteSelectedVectorNode() is True
    assert len(workspace.selectedVectorNodes) == 4
    assert workspace.setSelectedVectorPathClosed(False) is True
    assert workspace.selectedVectorPathClosed is False
    assert workspace.setSelectedVectorHandleLinkMode("collinear") is True

    project = tmp_path / "vector.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    loaded = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
    assert loaded.openDocument(str(project)) is True
    assert loaded.selectedVectorPathEnabled is True
    assert loaded.selectedVectorPathClosed is False
    assert len(loaded.selectedVectorNodes) == 4


@pytest.mark.unit
def test_collinear_out_handle_uses_y_unit_vector():
    layer = Layer(width=100, height=100)
    layer.convert_rect_to_vector_path()
    nodes = layer.vector_bezier_nodes
    nodes[0].update(
        {
            "x": 50.0,
            "y": 50.0,
            "in_x": 50.0,
            "in_y": 40.0,
            "out_x": 60.0,
            "out_y": 50.0,
            "node_type": "smooth",
        }
    )
    layer.vector_bezier_nodes = nodes
    layer.vector_handle_link_mode = "collinear"

    layer.update_vector_bezier_handle(0, "out", 60.0, 70.0)
    node = layer.vector_bezier_nodes[0]
    dx = node["in_x"] - node["x"]
    dy = node["in_y"] - node["y"]
    assert dy == pytest.approx(dx * 2.0)
