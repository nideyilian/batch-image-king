from __future__ import annotations

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace() -> tuple[WorkspaceViewModel, TextLayer]:
    document = Document()
    document.create_new(420, 240)
    layer = TextLayer(name="标题", x=30, y=40, width=320, height=130)
    layer.text_binding_enabled = False
    layer.set_text_lines(["ABCD"])
    layer.set_current_text("ABCD", force=True)
    layer.font_size = 64
    layer.auto_fit_text_box = False
    document.add_text_layer(layer)
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    return workspace, layer


@pytest.mark.unit
def test_text_fill_gradient_and_background_commands_are_mapped():
    workspace, layer = _workspace()

    assert workspace.selectedTextColor == "#000000"
    assert workspace.selectedTextFillModeId == "solid"
    assert workspace.selectedTextGradientTypeId == "linear"
    assert workspace.selectedTextGradientDirectionId == "horizontal"
    assert workspace.selectedTextGradientCenterXPercent == 50
    assert workspace.selectedTextGradientCenterYPercent == 50
    assert workspace.selectedTextBackgroundEnabled is False
    assert workspace.selectedTextBackgroundColor == "#FFFFFF80"
    assert workspace.selectedTextBackgroundOpacity == 50
    assert workspace.selectedTextBackgroundPadding == 5

    assert workspace.setSelectedTextColor("#F1786DCC") is True
    assert layer.text_color == (241, 120, 109, 204)
    assert workspace.setSelectedTextFillMode("gradient") is True
    assert layer.gradient_enabled is True
    assert workspace.setSelectedTextGradientType("radial") is True
    assert layer.gradient_type == "RADIAL"
    assert workspace.setSelectedTextGradientDirection("diagonal_rl") is True
    assert layer.gradient_direction == "DIAGONAL_RL"
    assert workspace.setSelectedTextGradientColor(0, "#173B32") is True
    assert workspace.setSelectedTextGradientColor(1, "#46D7AD80") is True
    assert layer.gradient_start_color == (23, 59, 50, 255)
    assert layer.gradient_end_color == (70, 215, 173, 128)
    assert workspace.setSelectedTextGradientCenter(35, 68) is True
    assert layer.gradient_center_x == pytest.approx(0.35)
    assert layer.gradient_center_y == pytest.approx(0.68)

    assert workspace.setSelectedTextBackgroundEnabled(True) is True
    assert workspace.setSelectedTextBackgroundColor("#10231FCC") is True
    assert workspace.setSelectedTextBackgroundOpacity(37) is True
    assert workspace.setSelectedTextBackgroundPadding(-80) is True
    assert layer.background_enabled is True
    assert layer.background_color == (16, 35, 31, 94)
    assert layer.background_padding == -50


@pytest.mark.unit
def test_text_appearance_commands_validate_inputs_and_locking():
    workspace, layer = _workspace()

    assert workspace.setSelectedTextColor("bad") is False
    assert workspace.setSelectedTextFillMode("unknown") is False
    assert workspace.setSelectedTextGradientType("mesh") is False
    assert workspace.setSelectedTextGradientDirection("clockwise") is False
    assert workspace.setSelectedTextGradientColor(-1, "#000000") is False
    assert workspace.setSelectedTextGradientColor(2, "#FFFFFF") is False
    assert workspace.setSelectedTextGradientCenter(-20, 140) is True
    assert workspace.selectedTextGradientCenterXPercent == 0
    assert workspace.selectedTextGradientCenterYPercent == 100
    assert workspace.setSelectedTextBackgroundColor("nope") is False

    layer.locked = True
    workspace.selectionChanged.emit()
    assert workspace.setSelectedTextColor("#FFFFFF") is False
    assert workspace.setSelectedTextFillMode("gradient") is False
    assert workspace.setSelectedTextBackgroundEnabled(True) is False
    assert workspace.setSelectedTextColorRange(0, 2, "#FF0000") is False
    assert layer.text_color == (0, 0, 0, 255)
    assert layer.gradient_enabled is False
    assert layer.background_enabled is False

    document = Document()
    document.create_new(100, 100)
    wrong = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert wrong.setSelectedTextColor("#FFFFFF") is False
    assert wrong.setSelectedTextBackgroundEnabled(True) is False


@pytest.mark.unit
def test_text_range_color_requires_whole_text_mode_and_valid_selection():
    workspace, layer = _workspace()

    assert workspace.selectedTextColorRangeCount == 0
    assert workspace.setSelectedTextColorRange(1, 3, "#FF0000") is True
    assert workspace.selectedTextColorRangeCount == 1
    assert layer.get_text_color_ranges() == [
        {"start": 1, "end": 3, "color": (255, 0, 0, 255)}
    ]
    assert workspace.clearSelectedTextColorRange(2, 4) is True
    assert layer.get_text_color_ranges() == [
        {"start": 1, "end": 2, "color": (255, 0, 0, 255)}
    ]
    assert workspace.setSelectedTextColorRange(2, 2, "#FFFFFF") is False
    assert workspace.setSelectedTextColorRange(0, 2, "bad") is False

    assert workspace.setSelectedTextBindingEnabled(True) is True
    assert workspace.setSelectedTextColorRange(0, 2, "#00FF00") is False
    assert workspace.clearSelectedTextColorRange(0, 2) is False


@pytest.mark.unit
def test_text_appearance_undo_redo_and_save_round_trip(tmp_path):
    workspace, _layer = _workspace()

    assert workspace.setSelectedTextColor("#F1786D") is True
    assert workspace.setSelectedTextFillMode("gradient") is True
    assert workspace.setSelectedTextGradientType("linear") is True
    assert workspace.setSelectedTextGradientDirection("vertical") is True
    assert workspace.setSelectedTextGradientColor(0, "#173B32") is True
    assert workspace.setSelectedTextGradientColor(1, "#46D7AD") is True
    assert workspace.setSelectedTextBackgroundEnabled(True) is True
    assert workspace.setSelectedTextBackgroundColor("#101715CC") is True
    assert workspace.setSelectedTextBackgroundPadding(14) is True
    assert workspace.setSelectedTextColorRange(1, 3, "#F7BD63") is True

    assert workspace.undo() is True
    assert workspace.document.layers[0].get_text_color_ranges() == []
    assert workspace.redo() is True
    assert workspace.document.layers[0].get_text_color_ranges()[0]["color"] == (
        247,
        189,
        99,
        255,
    )

    project = tmp_path / "text-appearance.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    loaded = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded.openDocument(str(project)) is True
    assert loaded.selectedTextColor == "#F1786D"
    assert loaded.selectedTextFillModeId == "gradient"
    assert loaded.selectedTextGradientTypeId == "linear"
    assert loaded.selectedTextGradientDirectionId == "vertical"
    assert loaded.selectedTextGradientStartColor == "#173B32"
    assert loaded.selectedTextGradientEndColor == "#46D7AD"
    assert loaded.selectedTextBackgroundEnabled is True
    assert loaded.selectedTextBackgroundColor == "#101715CC"
    assert loaded.selectedTextBackgroundPadding == 14
    assert loaded.selectedTextColorRangeCount == 1


@pytest.mark.integration
def test_text_appearance_changes_real_rendered_pixels():
    workspace, layer = _workspace()
    layer.text_color = (0, 0, 0, 255)
    solid = layer.render_text().copy()

    assert workspace.setSelectedTextFillMode("gradient") is True
    assert workspace.setSelectedTextGradientType("linear") is True
    assert workspace.setSelectedTextGradientDirection("horizontal") is True
    assert workspace.setSelectedTextGradientColor(0, "#FF0000") is True
    assert workspace.setSelectedTextGradientColor(1, "#0000FF") is True
    gradient = layer.render_text().copy()
    assert solid.tobytes() != gradient.tobytes()
    gradient_pixels = [pixel for pixel in gradient.getdata() if pixel[3] > 64]
    assert any(pixel[0] > pixel[2] + 40 for pixel in gradient_pixels)
    assert any(pixel[2] > pixel[0] + 40 for pixel in gradient_pixels)

    assert workspace.setSelectedTextFillMode("solid") is True
    assert workspace.setSelectedTextBackgroundEnabled(True) is True
    assert workspace.setSelectedTextBackgroundColor("#00FF00FF") is True
    assert workspace.setSelectedTextBackgroundPadding(16) is True
    background = layer.render_text().copy()
    assert sum(pixel[3] > 32 for pixel in background.getdata()) > sum(
        pixel[3] > 32 for pixel in solid.getdata()
    )

    assert workspace.setSelectedTextBackgroundEnabled(False) is True
    assert workspace.setSelectedTextColorRange(1, 3, "#FF0000") is True
    ranged = layer.render_text().copy()
    red_pixels = [
        pixel
        for pixel in ranged.getdata()
        if pixel[3] > 64 and pixel[0] > 180 and pixel[1] < 80 and pixel[2] < 80
    ]
    assert len(red_pixels) > 10
