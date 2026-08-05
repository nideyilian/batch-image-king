from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import QSize
import pytest

from app.models.document import Document
from app.models.shaped_layer_new import ShapedLayer
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _quadrant_source(path: Path, size: tuple[int, int] = (80, 80)) -> Path:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    half_width = size[0] // 2
    half_height = size[1] // 2
    draw.rectangle((0, 0, half_width - 1, half_height - 1), fill=(230, 70, 60, 255))
    draw.rectangle((half_width, 0, size[0] - 1, half_height - 1), fill=(60, 190, 110, 255))
    draw.rectangle((0, half_height, half_width - 1, size[1] - 1), fill=(60, 110, 220, 255))
    draw.rectangle(
        (half_width, half_height, size[0] - 1, size[1] - 1),
        fill=(240, 190, 60, 255),
    )
    image.save(path)
    return path


def _image_workspace(tmp_path: Path) -> tuple[WorkspaceViewModel, Path]:
    source = _quadrant_source(tmp_path / "quadrants.png")
    document = Document()
    document.create_new(120, 120)
    document.add_layer(
        "产品图",
        20,
        20,
        80,
        80,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.selectLayer(0)
    return workspace, source


@pytest.mark.unit
def test_image_fit_properties_and_commands_are_atomic(tmp_path: Path):
    workspace, _source = _image_workspace(tmp_path)
    layer = workspace.document.layers[0]

    assert workspace.selectedSupportsImageFit is True
    assert workspace.selectedFitModeId == "crop"
    assert workspace.selectedFitModeName == "填满裁剪"
    assert workspace.selectedCropDirectionId == "center"
    assert workspace.selectedCropDirectionName == "居中"
    assert workspace.selectedFlipHorizontal is False
    assert workspace.selectedFlipVertical is False

    assert workspace.setSelectedFitMode("fit") is True
    assert layer.fit_mode == layer.FIT_SMART_FIT
    assert workspace.setSelectedCropDirection("top") is True
    assert layer.crop_direction == layer.CROP_TOP
    assert workspace.setSelectedFlipHorizontal(True) is True
    assert workspace.setSelectedFlipVertical(True) is True
    assert layer.flip_horizontal is True
    assert layer.flip_vertical is True

    assert workspace.undo() is True
    assert workspace.document.layers[0].flip_vertical is False
    assert workspace.redo() is True
    assert workspace.document.layers[0].flip_vertical is True


@pytest.mark.unit
def test_image_fit_supports_shaped_layers_and_rejects_wrong_inputs(tmp_path: Path):
    workspace, source = _image_workspace(tmp_path)
    history = workspace.document._history_manager
    history_count = history.get_history_count()

    assert workspace.setSelectedFitMode("stretch") is False
    assert workspace.setSelectedCropDirection("face") is False
    assert history.get_history_count() == history_count

    layer = workspace.document.layers[0]
    layer.locked = True
    workspace.selectionChanged.emit()
    assert workspace.setSelectedFitMode("fit") is False
    assert workspace.setSelectedFlipHorizontal(True) is False
    assert layer.fit_mode == layer.FIT_SMART_CROP
    assert layer.flip_horizontal is False

    document = Document()
    document.create_new(120, 120)
    shaped = ShapedLayer(
        name="异形产品图",
        x=20,
        y=20,
        width=80,
        height=80,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
        current_image_path=str(source),
    )
    document.add_shaped_layer(shaped)
    document.add_text_layer(TextLayer(name="标题", x=20, y=20, width=80, height=40))
    shaped_workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    shaped_workspace.selectLayer(0)
    assert shaped_workspace.selectedSupportsImageFit is True
    assert shaped_workspace.setSelectedFitMode("original") is True
    assert shaped.fit_mode == shaped.FIT_NO_SCALE

    shaped_workspace.selectLayer(1)
    assert shaped_workspace.selectedSupportsImageFit is False
    assert shaped_workspace.setSelectedFitMode("crop") is False
    assert shaped_workspace.setSelectedCropDirection("center") is False
    assert shaped_workspace.setSelectedFlipVertical(True) is False


@pytest.mark.unit
def test_image_fit_and_flip_survive_document_save_round_trip(tmp_path: Path):
    workspace, _source = _image_workspace(tmp_path)
    assert workspace.setSelectedFitMode("fit") is True
    assert workspace.setSelectedCropDirection("right") is True
    assert workspace.setSelectedFlipHorizontal(True) is True
    assert workspace.setSelectedFlipVertical(True) is True

    project = tmp_path / "image-layout.cmp"
    assert workspace.saveDocumentTo(str(project)) is True

    loaded = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded.openDocument(str(project)) is True
    loaded.selectLayer(0)
    assert loaded.selectedFitModeId == "fit"
    assert loaded.selectedCropDirectionId == "right"
    assert loaded.selectedFlipHorizontal is True
    assert loaded.selectedFlipVertical is True


@pytest.mark.integration
def test_crop_direction_changes_real_preview_pixels(tmp_path: Path):
    source = tmp_path / "vertical-halves.png"
    image = Image.new("RGBA", (80, 160), (230, 70, 60, 255))
    ImageDraw.Draw(image).rectangle((0, 80, 79, 159), fill=(60, 110, 220, 255))
    image.save(source)

    document = Document()
    document.create_new(120, 120)
    document.add_layer(
        "竖图",
        20,
        20,
        80,
        80,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.selectLayer(0)

    assert workspace.setSelectedCropDirection("top") is True
    assert workspace.renderPreviewNow() is True
    size = QSize()
    top_crop = workspace._preview_provider.requestImage("current", size, QSize())
    top_color = top_crop.pixelColor(60, 60)
    assert (top_color.red(), top_color.green(), top_color.blue()) == (230, 70, 60)

    assert workspace.setSelectedCropDirection("bottom") is True
    assert workspace.renderPreviewNow() is True
    bottom_crop = workspace._preview_provider.requestImage("current", size, QSize())
    bottom_color = bottom_crop.pixelColor(60, 60)
    assert (bottom_color.red(), bottom_color.green(), bottom_color.blue()) == (60, 110, 220)


@pytest.mark.integration
def test_horizontal_and_vertical_flip_change_real_preview_pixels(tmp_path: Path):
    workspace, _source = _image_workspace(tmp_path)
    size = QSize()

    assert workspace.renderPreviewNow() is True
    original = workspace._preview_provider.requestImage("current", size, QSize())
    assert (original.pixelColor(30, 30).red(), original.pixelColor(30, 30).green()) == (230, 70)

    assert workspace.setSelectedFlipHorizontal(True) is True
    assert workspace.renderPreviewNow() is True
    horizontal = workspace._preview_provider.requestImage("current", size, QSize())
    horizontal_color = horizontal.pixelColor(30, 30)
    assert (horizontal_color.red(), horizontal_color.green(), horizontal_color.blue()) == (60, 190, 110)

    assert workspace.setSelectedFlipVertical(True) is True
    assert workspace.renderPreviewNow() is True
    both = workspace._preview_provider.requestImage("current", size, QSize())
    both_color = both.pixelColor(30, 30)
    assert (both_color.red(), both_color.green(), both_color.blue()) == (240, 190, 60)
