from __future__ import annotations

from pathlib import Path
import random

from PIL import Image, ImageDraw
import pytest

from app.models.document import Document
from app.models.layer_new import Layer
from app.models.shaped_layer_new import ShapedLayer
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _source_image(path: Path) -> Path:
    image = Image.new("RGBA", (200, 100), (230, 70, 60, 255))
    ImageDraw.Draw(image).rectangle((100, 0, 199, 99), fill=(60, 180, 110, 255))
    image.save(path)
    return path


def _workspace(tmp_path: Path) -> tuple[WorkspaceViewModel, Path]:
    source = _source_image(tmp_path / "transform-source.png")
    document = Document()
    document.create_new(360, 280)
    document.add_layer(
        "产品图",
        20,
        30,
        160,
        80,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    document.add_text_layer(TextLayer(name="标题", x=30, y=190, width=180, height=50))
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.selectLayer(0)
    return workspace, source


@pytest.mark.unit
def test_aspect_ratio_lock_updates_dimensions_atomically(tmp_path: Path):
    workspace, _source = _workspace(tmp_path)

    assert workspace.selectedSupportsAspectRatioLock is True
    assert workspace.selectedAspectRatioLocked is False
    assert workspace.setSelectedAspectRatioLocked(True) is True
    assert workspace.selectedAspectRatioLocked is True

    assert workspace.setSelectedWidth(240) is True
    layer = workspace.document.layers[0]
    assert (layer.width, layer.height) == (240, 120)

    assert workspace.undo() is True
    layer = workspace.document.layers[0]
    assert (layer.width, layer.height) == (160, 80)
    assert layer.aspect_ratio_locked is True
    assert workspace.redo() is True
    assert (workspace.document.layers[0].width, workspace.document.layers[0].height) == (240, 120)

    assert workspace.setSelectedHeight(60) is True
    assert (workspace.document.layers[0].width, workspace.document.layers[0].height) == (120, 60)


@pytest.mark.unit
def test_transform_controls_reject_text_and_locked_layers(tmp_path: Path):
    workspace, _source = _workspace(tmp_path)
    layer = workspace.document.layers[0]
    layer.locked = True
    workspace.selectionChanged.emit()

    assert workspace.setSelectedAspectRatioLocked(True) is False
    assert workspace.setSelectedRandomPositionEnabled(True) is False
    assert workspace.setSelectedRandomScaleEnabled(True) is False
    assert workspace.setSelectedRandomRotationEnabled(True) is False
    assert layer.aspect_ratio_locked is False
    assert layer.random_position_enabled is False

    workspace.selectLayer(1)
    assert workspace.selectedSupportsAspectRatioLock is False
    assert workspace.selectedSupportsRandomTransform is False
    assert workspace.setSelectedAspectRatioLocked(True) is False
    assert workspace.setSelectedRandomPositionRange(24) is False
    assert workspace.regenerateSelectedRandomTransform() is False


@pytest.mark.unit
def test_random_transform_configuration_and_preview_generation(tmp_path: Path, monkeypatch):
    workspace, _source = _workspace(tmp_path)
    layer = workspace.document.layers[0]

    assert workspace.selectedSupportsRandomTransform is True
    assert workspace.selectedRandomPositionEnabled is False
    assert workspace.selectedRandomPositionRange == 10
    assert workspace.selectedRandomScaleEnabled is False
    assert workspace.selectedRandomScaleMinPercent == 90
    assert workspace.selectedRandomScaleMaxPercent == 110
    assert workspace.selectedRandomRotationEnabled is False
    assert workspace.selectedRandomRotationRange == pytest.approx(5.0)

    assert workspace.setSelectedRandomPositionEnabled(True) is True
    assert workspace.setSelectedRandomPositionRange(24) is True
    assert workspace.setSelectedRandomScaleEnabled(True) is True
    assert workspace.setSelectedRandomScaleMinPercent(80) is True
    assert workspace.setSelectedRandomScaleMaxPercent(125) is True
    assert workspace.setSelectedRandomRotationEnabled(True) is True
    assert workspace.setSelectedRandomRotationRange(12.5) is True
    assert workspace.selectedRandomTransformEnabledCount == 3

    random_offsets = iter((-7, 8))
    random_values = iter((0.95, -4.5))
    monkeypatch.setattr(random, "randint", lambda _low, _high: next(random_offsets))
    monkeypatch.setattr(random, "uniform", lambda _low, _high: next(random_values))

    assert workspace.regenerateSelectedRandomTransform() is True
    assert (layer._current_random_offset_x, layer._current_random_offset_y) == (-7, 8)
    assert layer._current_random_scale == pytest.approx(0.95)
    assert layer._current_random_rotation == pytest.approx(-4.5)
    assert workspace.selectedRandomOffsetX == -7
    assert workspace.selectedRandomOffsetY == 8
    assert workspace.selectedRandomScalePercent == 95
    assert workspace.selectedRandomRotation == pytest.approx(-4.5)
    assert "-7/+8" in workspace.selectedRandomPreviewSummary


@pytest.mark.unit
def test_random_transform_ranges_are_clamped_and_linked(tmp_path: Path):
    workspace, _source = _workspace(tmp_path)

    assert workspace.setSelectedRandomPositionRange(-20) is True
    assert workspace.selectedRandomPositionRange == 0
    assert workspace.setSelectedRandomPositionRange(20000) is True
    assert workspace.selectedRandomPositionRange == 10000

    assert workspace.setSelectedRandomScaleMinPercent(150) is True
    assert workspace.selectedRandomScaleMinPercent == 150
    assert workspace.selectedRandomScaleMaxPercent == 150
    assert workspace.setSelectedRandomScaleMaxPercent(80) is True
    assert workspace.selectedRandomScaleMinPercent == 80
    assert workspace.selectedRandomScaleMaxPercent == 80
    assert workspace.setSelectedRandomScaleMinPercent(0) is True
    assert workspace.selectedRandomScaleMinPercent == 1
    assert workspace.setSelectedRandomScaleMaxPercent(5000) is True
    assert workspace.selectedRandomScaleMaxPercent == 1000

    assert workspace.setSelectedRandomRotationRange(999.0) is True
    assert workspace.selectedRandomRotationRange == pytest.approx(180.0)
    assert workspace.setSelectedRandomRotationRange(-10.0) is True
    assert workspace.selectedRandomRotationRange == pytest.approx(0.0)


@pytest.mark.unit
def test_locked_and_random_transform_settings_survive_save_round_trip(tmp_path: Path):
    workspace, _source = _workspace(tmp_path)
    assert workspace.setSelectedAspectRatioLocked(True) is True
    assert workspace.setSelectedRandomPositionEnabled(True) is True
    assert workspace.setSelectedRandomPositionRange(33) is True
    assert workspace.setSelectedRandomScaleEnabled(True) is True
    assert workspace.setSelectedRandomScaleMinPercent(75) is True
    assert workspace.setSelectedRandomScaleMaxPercent(135) is True
    assert workspace.setSelectedRandomRotationEnabled(True) is True
    assert workspace.setSelectedRandomRotationRange(17.5) is True

    project = tmp_path / "locked-random.cmp"
    assert workspace.saveDocumentTo(str(project)) is True

    loaded = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded.openDocument(str(project)) is True
    loaded.selectLayer(0)
    assert loaded.selectedAspectRatioLocked is True
    assert loaded.selectedRandomPositionEnabled is True
    assert loaded.selectedRandomPositionRange == 33
    assert loaded.selectedRandomScaleEnabled is True
    assert loaded.selectedRandomScaleMinPercent == 75
    assert loaded.selectedRandomScaleMaxPercent == 135
    assert loaded.selectedRandomRotationEnabled is True
    assert loaded.selectedRandomRotationRange == pytest.approx(17.5)


@pytest.mark.unit
def test_shaped_layer_supports_locked_and_random_transforms(tmp_path: Path):
    workspace, source = _workspace(tmp_path)
    shaped = ShapedLayer(
        name="异形产品图",
        width=160,
        height=80,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
        current_image_path=str(source),
    )
    workspace.document.add_shaped_layer(shaped)
    workspace.layerModel.reset_from_document()
    workspace.selectLayer(2)

    assert workspace.selectedSupportsAspectRatioLock is True
    assert workspace.selectedSupportsRandomTransform is True
    assert workspace.setSelectedAspectRatioLocked(True) is True
    assert workspace.setSelectedWidth(200) is True
    assert (shaped.width, shaped.height) == (200, 100)
    assert workspace.setSelectedRandomRotationEnabled(True) is True
    assert shaped.random_rotation_enabled is True


@pytest.mark.unit
def test_random_scale_changes_real_layer_pixels():
    layer = Layer(name="随机缩放", width=40, height=40, is_folder=False)
    layer.random_scale_enabled = True
    layer._current_random_scale = 0.5
    source = Image.new("RGBA", (40, 40), (230, 70, 60, 255))

    result = layer.apply_effects(source)

    assert result.size == (40, 40)
    assert result.getpixel((2, 2))[3] == 0
    assert result.getpixel((20, 20))[:3] == (230, 70, 60)


@pytest.mark.unit
def test_random_rotation_changes_real_layer_pixels():
    layer = Layer(name="随机旋转", width=48, height=48, is_folder=False)
    layer.random_rotation_enabled = True
    layer._current_random_rotation = 90.0
    source = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((0, 0, 19, 19), fill=(60, 180, 110, 255))

    result = layer.apply_effects(source)

    assert result.size == (48, 48)
    assert result.getpixel((10, 10))[3] == 0
    assert result.getpixel((37, 10))[:3] == (60, 180, 110)
