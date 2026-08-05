from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize
import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _effects_workspace(tmp_path: Path) -> WorkspaceViewModel:
    source = tmp_path / "effects-source.png"
    Image.new("RGBA", (100, 80), (70, 160, 125, 255)).save(source)
    document = Document()
    document.create_new(320, 240)
    document.add_layer(
        "产品图",
        20,
        30,
        100,
        80,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    document.add_text_layer(TextLayer(name="标题", x=40, y=140, width=180, height=60))
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.selectLayer(0)
    return workspace


@pytest.mark.unit
def test_image_layer_effect_properties_and_commands_are_atomic(tmp_path: Path):
    workspace = _effects_workspace(tmp_path)
    layer = workspace.document.layers[0]

    assert workspace.selectedSupportsBlendMode is True
    assert workspace.selectedSupportsStroke is True
    assert workspace.selectedSupportsCornerRadius is True
    assert workspace.selectedBlendModeId == "normal"
    assert workspace.selectedBlendModeName == "正常"
    assert workspace.selectedStrokeEnabled is False
    assert workspace.selectedStrokeWidth == 1
    assert workspace.selectedStrokeColor == "#000000"
    assert workspace.selectedCornerRadius == 0
    assert workspace.selectedCornerRadiusMax == 40

    assert workspace.setSelectedBlendMode("multiply") is True
    assert layer.blend_mode == 1
    assert workspace.selectedBlendModeName == "正片叠底"
    assert workspace.undo() is True
    assert workspace.document.layers[0].blend_mode == 0
    assert workspace.redo() is True
    assert workspace.document.layers[0].blend_mode == 1

    assert workspace.setSelectedStrokeEnabled(True) is True
    assert workspace.setSelectedStrokeWidth(18) is True
    assert workspace.setSelectedStrokeColor("#F1786D") is True
    assert workspace.setSelectedCornerRadius(999) is True
    layer = workspace.document.layers[0]
    assert layer.stroke_enabled is True
    assert layer.stroke_width == 18
    assert layer.stroke_color == (241, 120, 109, 255)
    assert layer.corner_radius == 40


@pytest.mark.unit
def test_text_layer_exposes_only_supported_effects(tmp_path: Path):
    workspace = _effects_workspace(tmp_path)
    workspace.selectLayer(1)
    layer = workspace.document.layers[1]

    assert workspace.selectedSupportsBlendMode is False
    assert workspace.selectedSupportsStroke is True
    assert workspace.selectedSupportsCornerRadius is False
    assert workspace.setSelectedBlendMode("screen") is False
    assert workspace.setSelectedCornerRadius(12) is False
    assert not hasattr(layer, "blend_mode")
    assert not hasattr(layer, "corner_radius")

    assert workspace.setSelectedStrokeEnabled(True) is True
    assert workspace.setSelectedStrokeWidth(7) is True
    assert workspace.setSelectedStrokeColor("#46D7AD80") is True
    assert layer.stroke_enabled is True
    assert layer.stroke_width == 7
    assert layer.stroke_color == (70, 215, 173, 128)
    assert workspace.selectedStrokeColor == "#46D7AD80"


@pytest.mark.unit
def test_effect_commands_validate_inputs_and_respect_lock(tmp_path: Path):
    workspace = _effects_workspace(tmp_path)
    layer = workspace.document.layers[0]
    history = workspace.document._history_manager

    assert workspace.setSelectedBlendMode("unknown") is False
    assert workspace.setSelectedStrokeColor("not-a-color") is False
    assert workspace.setSelectedStrokeWidth(0) is True
    assert layer.stroke_width == 1

    history_count = history.get_history_count()
    assert workspace.setSelectedStrokeWidth(1) is True
    assert history.get_history_count() == history_count

    layer.locked = True
    workspace.selectionChanged.emit()
    assert workspace.setSelectedBlendMode("screen") is False
    assert workspace.setSelectedStrokeEnabled(True) is False
    assert workspace.setSelectedCornerRadius(12) is False
    assert layer.blend_mode == 0
    assert layer.stroke_enabled is False
    assert layer.corner_radius == 0


@pytest.mark.unit
def test_layer_effects_survive_document_save_round_trip(tmp_path: Path):
    workspace = _effects_workspace(tmp_path)
    assert workspace.setSelectedBlendMode("soft_light") is True
    assert workspace.setSelectedStrokeEnabled(True) is True
    assert workspace.setSelectedStrokeWidth(9) is True
    assert workspace.setSelectedStrokeColor("#F7BD63") is True
    assert workspace.setSelectedCornerRadius(24) is True

    project = tmp_path / "layer-effects.cmp"
    assert workspace.saveDocumentTo(str(project)) is True

    loaded = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded.openDocument(str(project)) is True
    loaded.selectLayer(0)
    assert loaded.selectedBlendModeId == "soft_light"
    assert loaded.selectedStrokeEnabled is True
    assert loaded.selectedStrokeWidth == 9
    assert loaded.selectedStrokeColor == "#F7BD63"
    assert loaded.selectedCornerRadius == 24


@pytest.mark.integration
def test_corner_radius_is_published_in_real_preview(tmp_path: Path):
    workspace = _effects_workspace(tmp_path)
    assert workspace.setSelectedCornerRadius(24) is True
    assert workspace.renderPreviewNow() is True

    size = QSize()
    image = workspace._preview_provider.requestImage("current", size, QSize())
    assert image.pixelColor(20, 30).alpha() == 0
    assert image.pixelColor(70, 70).alpha() > 0
