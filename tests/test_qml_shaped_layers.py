from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize
import pytest

from app.models.document import Document
from app.models.layer_properties import ShapeType
from app.models.shaped_layer_new import ShapedLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(tmp_path: Path) -> tuple[WorkspaceViewModel, Path]:
    source = tmp_path / "shape-source.png"
    Image.new("RGBA", (200, 100), (225, 85, 70, 255)).save(source)
    document = Document()
    document.create_new(300, 240)
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    return workspace, source


@pytest.mark.unit
def test_workspace_adds_real_shaped_layer_and_supports_undo(tmp_path: Path):
    workspace, source = _workspace(tmp_path)

    assert workspace.addShapedLayer(str(source), "circle") is True
    assert len(workspace.document.layers) == 1
    layer = workspace.document.layers[0]
    assert isinstance(layer, ShapedLayer)
    assert layer.shape_type == ShapeType.CIRCLE
    assert (layer.x, layer.y, layer.width, layer.height) == (60, 75, 180, 90)
    assert layer.image_source == str(source)
    assert layer.current_image_path == str(source)
    assert workspace.selectedLayerIndex == 0
    assert workspace.selectedLayerType == "异形"
    assert workspace.selectedIsShapedLayer is True
    assert workspace.selectedHasImageSource is True
    assert workspace.selectedShapeTypeId == "circle"
    assert workspace.selectedShapeTypeName == "圆形"
    assert workspace.selectedCornerControlKind == "none"
    assert workspace.selectedSupportsCornerRadius is False
    assert workspace.selectedSupportsShapeCornerRadius is False
    assert workspace.document.is_modified is True

    assert workspace.undo() is True
    assert workspace.document.layers == []
    assert workspace.redo() is True
    assert isinstance(workspace.document.layers[0], ShapedLayer)
    assert workspace.document.layers[0].shape_type == ShapeType.CIRCLE


@pytest.mark.unit
def test_shaped_layer_creation_validates_path_and_shape(tmp_path: Path):
    workspace, source = _workspace(tmp_path)

    assert workspace.addShapedLayer(str(source), "star") is False
    assert workspace.addShapedLayer(str(tmp_path / "missing.png"), "circle") is False
    assert workspace.document.layers == []
    assert "形状" in workspace.statusMessage or "不存在" in workspace.statusMessage


@pytest.mark.unit
def test_shaped_layer_type_and_parameters_are_validated_and_undoable(tmp_path: Path):
    workspace, source = _workspace(tmp_path)
    assert workspace.addShapedLayer(str(source), "circle") is True
    layer = workspace.document.layers[0]

    assert workspace.setSelectedShapeType("right_trapezoid") is True
    assert layer.shape_type == ShapeType.RIGHT_TRAPEZOID
    assert workspace.selectedCornerControlKind == "shape"
    assert workspace.selectedSupportsShapeCornerRadius is True
    assert workspace.selectedTrapezoidTopWidth == 180
    assert workspace.selectedTrapezoidBottomWidth == 144
    assert workspace.selectedTrapezoidSlopeSide == "right"

    assert workspace.setSelectedTrapezoidTopWidth(120) is True
    assert workspace.setSelectedTrapezoidBottomWidth(80) is True
    assert workspace.setSelectedTrapezoidSlopeSide("left") is True
    assert layer.trapezoid_top_width == 120
    assert layer.trapezoid_bottom_width == 80
    assert layer.trapezoid_slope_side == "left"

    assert workspace.setSelectedShapeType("pentagon") is True
    assert workspace.setSelectedPolygonRotation(-30.0) is True
    assert workspace.setSelectedPolygonCornerRadius(999) is True
    assert layer.shape_type == ShapeType.PENTAGON
    assert workspace.selectedCornerControlKind == "shape"
    assert layer.polygon_rotation == pytest.approx(330.0)
    assert layer.polygon_corner_radius == workspace.selectedPolygonCornerRadiusMax == 11

    assert workspace.undo() is True
    assert workspace.document.layers[0].polygon_corner_radius == 0
    assert workspace.redo() is True
    assert workspace.document.layers[0].polygon_corner_radius == 11


@pytest.mark.unit
def test_corner_controls_follow_shaped_geometry_and_vector_mode(tmp_path: Path):
    workspace, source = _workspace(tmp_path)
    assert workspace.addShapedLayer(str(source), "right_trapezoid") is True

    assert workspace.selectedSupportsShapeCornerRadius is True
    assert workspace.setSelectedPolygonCornerRadius(7) is True
    assert workspace.selectedPolygonCornerRadius == 7

    assert workspace.setSelectedShapeType("circle") is True
    assert workspace.selectedCornerControlKind == "none"
    assert workspace.setSelectedPolygonCornerRadius(4) is False

    assert workspace.setSelectedShapeType("rectangle") is True
    assert workspace.selectedCornerControlKind == "rectangle"
    assert workspace.selectedSupportsCornerRadius is True
    assert workspace.setSelectedCornerRadius(12) is True

    assert workspace.convertSelectedToVectorPath() is True
    assert workspace.selectedCornerControlKind == "none"
    assert workspace.selectedSupportsCornerRadius is False
    assert workspace.setSelectedCornerRadius(8) is False


@pytest.mark.unit
def test_shape_commands_reject_wrong_type_and_locked_layer(tmp_path: Path):
    workspace, source = _workspace(tmp_path)
    assert workspace.addImageLayer(str(source)) is True
    assert workspace.selectedIsShapedLayer is False
    assert workspace.setSelectedShapeType("circle") is False

    workspace.document.layers.clear()
    workspace.document.selected_layer_index = -1
    workspace.layerModel.reset_from_document()
    assert workspace.addShapedLayer(str(source), "hexagon") is True
    layer = workspace.document.layers[0]
    layer.locked = True
    workspace.selectionChanged.emit()

    assert workspace.setSelectedShapeType("circle") is False
    assert workspace.setSelectedPolygonRotation(30.0) is False
    assert workspace.setSelectedPolygonCornerRadius(4) is False
    assert layer.shape_type == ShapeType.HEXAGON
    assert layer.polygon_rotation == pytest.approx(0.0)


@pytest.mark.unit
def test_shaped_layer_survives_document_save_round_trip(tmp_path: Path):
    workspace, source = _workspace(tmp_path)
    assert workspace.addShapedLayer(str(source), "right_trapezoid") is True
    assert workspace.setSelectedTrapezoidTopWidth(130) is True
    assert workspace.setSelectedTrapezoidBottomWidth(70) is True
    assert workspace.setSelectedTrapezoidSlopeSide("left") is True
    project = tmp_path / "shaped-layer.cmp"
    assert workspace.saveDocumentTo(str(project)) is True

    loaded = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded.openDocument(str(project)) is True
    loaded.selectLayer(0)
    layer = loaded.document.layers[0]
    assert isinstance(layer, ShapedLayer)
    assert loaded.selectedShapeTypeId == "right_trapezoid"
    assert loaded.selectedTrapezoidTopWidth == 130
    assert loaded.selectedTrapezoidBottomWidth == 70
    assert loaded.selectedTrapezoidSlopeSide == "left"
    assert loaded.selectedImageSource == str(source)


@pytest.mark.integration
def test_circle_shaped_layer_is_visible_in_real_preview(tmp_path: Path):
    workspace, source = _workspace(tmp_path)
    assert workspace.addShapedLayer(str(source), "circle") is True
    assert workspace.renderPreviewNow() is True

    size = QSize()
    image = workspace._preview_provider.requestImage("current", size, QSize())
    assert image.size() == QSize(300, 240)
    assert image.pixelColor(60, 75).alpha() == 0
    center = image.pixelColor(150, 120)
    assert center.alpha() > 0
    assert (center.red(), center.green(), center.blue()) == (225, 85, 70)
