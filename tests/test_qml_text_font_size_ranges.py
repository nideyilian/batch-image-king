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
    layer.font_size = 48
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
def test_font_size_range_getter_and_slots():
    workspace, layer = _workspace()

    assert workspace.selectedTextFontSizeRangeCount == 0
    assert workspace.setSelectedTextFontSizeRange(1, 3, 72) is True
    assert workspace.selectedTextFontSizeRangeCount == 1
    assert layer.get_font_size_ranges() == [{"start": 1, "end": 3, "size": 72}]

    assert workspace.clearSelectedTextFontSizeRange(1, 3) is True
    assert workspace.selectedTextFontSizeRangeCount == 0


@pytest.mark.unit
def test_font_size_range_rejects_binding_mode():
    workspace, layer = _workspace()
    workspace.setSelectedTextBindingEnabled(True)

    assert workspace.setSelectedTextFontSizeRange(1, 3, 72) is False
    assert layer.get_font_size_ranges() == []


@pytest.mark.unit
def test_font_size_range_rejects_invalid_selection():
    workspace, layer = _workspace()

    assert workspace.setSelectedTextFontSizeRange(2, 2, 72) is False
    assert layer.get_font_size_ranges() == []


@pytest.mark.unit
def test_font_size_range_clamps_value():
    workspace, layer = _workspace()

    assert workspace.setSelectedTextFontSizeRange(1, 3, 5000) is True
    assert layer.get_font_size_ranges() == [{"start": 1, "end": 3, "size": 1000}]


@pytest.mark.unit
def test_text_edit_overlay_state_lifecycle():
    workspace, layer = _workspace()

    assert workspace.textEditOverlayVisible is False
    assert workspace.startTextEditOverlay() is True
    assert workspace.textEditOverlayVisible is True

    assert workspace.commitTextEditOverlay("HELLO") is True
    assert workspace.textEditOverlayVisible is False
    assert layer.current_text == "HELLO"

    assert workspace.startTextEditOverlay() is True
    assert workspace.cancelTextEditOverlay() is True
    assert workspace.textEditOverlayVisible is False
    assert layer.current_text == "HELLO"


@pytest.mark.unit
def test_text_edit_overlay_start_rejects_locked_layer():
    workspace, layer = _workspace()
    layer.locked = True

    assert workspace.startTextEditOverlay() is False
    assert workspace.textEditOverlayVisible is False


@pytest.mark.unit
def test_text_edit_overlay_properties_have_valid_notify_signals():
    workspace, layer = _workspace()
    meta = workspace.metaObject()

    def notify_signal(property_name):
        for i in range(meta.propertyCount()):
            prop = meta.property(i)
            if prop.name() == property_name:
                return prop.notifySignal()
        return None

    overlay_notify = notify_signal("textEditOverlayVisible")
    assert overlay_notify is not None
    assert overlay_notify.isValid() is True
    assert overlay_notify.name() == bytes(b"textEditingChanged")


@pytest.mark.unit
def test_text_edit_overlay_auto_dismisses_on_selection_change():
    workspace, layer = _workspace()
    other = TextLayer(name="其他", x=120, y=160, width=160, height=80)
    workspace.document.add_text_layer(other)
    workspace.document._history_manager.clear()
    workspace.layerModel.reset_from_document()
    workspace.selectLayer(0)

    assert workspace.startTextEditOverlay() is True
    assert workspace.textEditOverlayVisible is True

    workspace.selectLayer(1)
    assert workspace.textEditOverlayVisible is False
