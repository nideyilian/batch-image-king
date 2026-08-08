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
    layer.set_text_lines(["EFFECT"])
    layer.set_current_text("EFFECT", force=True)
    layer.font_size = 58
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
def test_text_shadow_and_glow_commands_are_mapped_and_validated():
    workspace, layer = _workspace()

    assert workspace.selectedTextShadowEnabled is False
    assert workspace.selectedTextShadowOffsetX == 2
    assert workspace.selectedTextShadowOffsetY == 2
    assert workspace.selectedTextShadowBlur == 4
    assert workspace.selectedTextShadowColor == "#00000080"
    assert workspace.selectedTextShadowOpacity == 50
    assert workspace.selectedTextGlowEnabled is False
    assert workspace.selectedTextGlowStrength == 5
    assert workspace.selectedTextGlowRadius == 10
    assert workspace.selectedTextGlowColor == "#FFFFFF"
    assert workspace.selectedTextGlowOpacity == 100

    assert workspace.setSelectedTextShadowEnabled(True) is True
    assert workspace.setSelectedTextShadowOffset(-80, 90) is True
    assert workspace.setSelectedTextShadowBlur(99) is True
    assert workspace.setSelectedTextShadowColor("#173B32CC") is True
    assert workspace.setSelectedTextShadowOpacity(37) is True
    assert workspace.setSelectedTextGlowEnabled(True) is True
    assert workspace.setSelectedTextGlowStrength(90) is True
    assert workspace.setSelectedTextGlowRadius(-2) is True
    assert workspace.setSelectedTextGlowColor("#173B32CC") is True
    assert workspace.setSelectedTextGlowOpacity(37) is True

    assert layer.shadow_enabled is True
    assert (layer.shadow_offset_x, layer.shadow_offset_y) == (-50, 50)
    assert layer.shadow_blur == 20
    assert layer.shadow_color == (23, 59, 50, 94)
    assert layer.glow_enabled is True
    assert layer.glow_strength == 20
    assert layer.glow_radius == 1
    assert layer.glow_color == (23, 59, 50, 94)

    assert workspace.setSelectedTextShadowColor("bad") is False
    layer.locked = True
    workspace.selectionChanged.emit()
    assert workspace.setSelectedTextShadowEnabled(False) is False
    assert workspace.setSelectedTextGlowEnabled(False) is False


@pytest.mark.unit
def test_text_effects_undo_redo_and_save_round_trip(tmp_path):
    workspace, _layer = _workspace()

    assert workspace.setSelectedTextShadowEnabled(True) is True
    assert workspace.setSelectedTextShadowOffset(9, -7) is True
    assert workspace.setSelectedTextShadowBlur(12) is True
    assert workspace.setSelectedTextShadowColor("#11223399") is True
    assert workspace.setSelectedTextGlowEnabled(True) is True
    assert workspace.setSelectedTextGlowColor("#F7BD6380") is True
    assert workspace.setSelectedTextGlowOpacity(42) is True
    assert workspace.setSelectedTextGlowStrength(14) is True
    assert workspace.setSelectedTextGlowRadius(18) is True

    assert workspace.undo() is True
    assert workspace.selectedTextGlowRadius == 10
    assert workspace.redo() is True
    assert workspace.selectedTextGlowRadius == 18

    project = tmp_path / "text-effects.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    loaded = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded.openDocument(str(project)) is True
    assert loaded.selectedTextShadowEnabled is True
    assert loaded.selectedTextShadowOffsetX == 9
    assert loaded.selectedTextShadowOffsetY == -7
    assert loaded.selectedTextShadowBlur == 12
    assert loaded.selectedTextShadowColor == "#11223399"
    assert loaded.selectedTextGlowEnabled is True
    assert loaded.selectedTextGlowStrength == 14
    assert loaded.selectedTextGlowRadius == 18
    assert loaded.selectedTextGlowColor == "#F7BD636B"
    assert loaded.selectedTextGlowOpacity == 42


@pytest.mark.integration
def test_text_shadow_glow_and_vertical_background_change_real_pixels():
    workspace, layer = _workspace()
    layer.text_color = (255, 255, 255, 255)
    base = layer.render_text().copy()

    assert workspace.setSelectedTextShadowEnabled(True) is True
    assert workspace.setSelectedTextShadowOffset(10, 8) is True
    assert workspace.setSelectedTextShadowBlur(0) is True
    assert workspace.setSelectedTextShadowColor("#FF0000") is True
    shadow = layer.render_text().copy()
    shadow_only = [
        shadow.getpixel((x, y))
        for y in range(shadow.height)
        for x in range(shadow.width)
        if base.getpixel((x, y))[3] == 0 and shadow.getpixel((x, y))[3] > 32
    ]
    assert any(pixel[0] > 200 and pixel[1] < 40 and pixel[2] < 40 for pixel in shadow_only)

    assert workspace.setSelectedTextShadowEnabled(False) is True
    layer.text_color = (70, 215, 173, 255)
    base = layer.render_text().copy()
    assert workspace.setSelectedTextGlowEnabled(True) is True
    assert workspace.setSelectedTextGlowStrength(16) is True
    assert workspace.setSelectedTextGlowRadius(10) is True
    assert workspace.setSelectedTextGlowColor("#FF0000") is True
    glow = layer.render_text().copy()
    assert sum(pixel[3] > 5 for pixel in glow.getdata()) > sum(
        pixel[3] > 5 for pixel in base.getdata()
    )
    glow_only = [
        glow.getpixel((x, y))
        for y in range(glow.height)
        for x in range(glow.width)
        if base.getpixel((x, y))[3] == 0 and glow.getpixel((x, y))[3] > 5
    ]
    assert any(pixel[0] > pixel[1] * 2 and pixel[0] > pixel[2] * 2 for pixel in glow_only)

    assert workspace.setSelectedTextGlowEnabled(False) is True
    layer.vertical_layout = True
    vertical = layer.render_text().copy()
    assert workspace.setSelectedTextBackgroundEnabled(True) is True
    assert workspace.setSelectedTextBackgroundColor("#0000FFFF") is True
    assert workspace.setSelectedTextBackgroundPadding(10) is True
    vertical_background = layer.render_text().copy()
    assert sum(pixel[3] > 32 for pixel in vertical_background.getdata()) > sum(
        pixel[3] > 32 for pixel in vertical.getdata()
    )


@pytest.mark.integration
def test_auto_fit_text_box_preserves_effect_padding_on_every_edge():
    layer = TextLayer(width=120, height=60)
    layer.text_binding_enabled = False
    layer.set_text_lines(["Glow"])
    layer.set_current_text("Glow", force=True)
    layer.font_size = 48
    layer.shadow_enabled = True
    layer.shadow_offset_x = -12
    layer.shadow_offset_y = -9
    layer.shadow_blur = 8
    layer.glow_enabled = True
    layer.glow_strength = 12
    layer.glow_radius = 14

    image = layer.render_text()
    left, top, right, bottom = image.getbbox()
    assert left >= layer.text_box_padding
    assert top >= layer.text_box_padding
    assert image.width - right >= layer.text_box_padding
    assert image.height - bottom >= layer.text_box_padding


@pytest.mark.unit
def test_text_style_clipboard_preserves_content_and_geometry_and_is_undoable():
    workspace, source = _workspace()
    source.font_size = 42
    source.text_color = (241, 120, 109, 255)
    source.shadow_enabled = True
    source.shadow_offset_x = 7
    source.shadow_offset_y = -4
    source.glow_enabled = True
    source.glow_strength = 12

    assert workspace.hasLayerStyleClipboard is False
    assert workspace.copySelectedLayerStyle() is True
    assert workspace.hasLayerStyleClipboard is True

    target = TextLayer(name="正文", x=140, y=150, width=210, height=70)
    target.text_binding_enabled = False
    target.set_text_lines(["KEEP ME"])
    target.set_current_text("KEEP ME", force=True)
    target.auto_fit_text_box = False
    workspace.document.add_text_layer(target)
    workspace.layerModel.reset_from_document()
    workspace.selectLayer(1)
    original_geometry = (target.x, target.y, target.width, target.height)

    assert workspace.pasteSelectedLayerStyle() is True
    assert target.current_text == "KEEP ME"
    assert (target.x, target.y, target.width, target.height) == original_geometry
    assert target.font_size == 42
    assert target.text_color == (241, 120, 109, 255)
    assert target.shadow_enabled is True
    assert (target.shadow_offset_x, target.shadow_offset_y) == (7, -4)
    assert target.glow_enabled is True
    assert target.glow_strength == 12
    assert target.glow_color == source.glow_color

    assert workspace.undo() is True
    restored = workspace.document.layers[1]
    assert restored.current_text == "KEEP ME"
    assert restored.font_size == 24
    assert restored.shadow_enabled is False
