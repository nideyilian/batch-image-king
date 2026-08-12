from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace():
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
    return WorkspaceViewModel(document=document, preview_provider=PreviewImageProvider(), auto_render=False), layer


def test_font_size_range_slots_use_qt_selection_indices():
    workspace, layer = _workspace()
    assert workspace.selectedTextFontSizeRangeCount == 0
    assert workspace.setSelectedTextFontSizeRangeQt(1, 3, 72) is True
    assert layer.get_font_size_ranges() == [{"start": 1, "end": 3, "size": 72}]
    assert workspace.clearSelectedTextFontSizeRangeQt(1, 3) is True
    assert workspace.selectedTextFontSizeRangeCount == 0


def test_font_size_range_rejects_binding_mode_and_invalid_qt_selection():
    workspace, layer = _workspace()
    assert workspace.setSelectedTextBindingEnabled(True) is True
    assert workspace.setSelectedTextFontSizeRangeQt(1, 3, 72) is False
    assert layer.get_font_size_ranges() == []
    assert workspace.setSelectedTextFontSizeRangeQt(-1, 2, 72) is False


def test_font_size_range_clamps_value():
    workspace, layer = _workspace()
    assert workspace.setSelectedTextFontSizeRangeQt(1, 3, 5000) is True
    assert layer.get_font_size_ranges() == [{"start": 1, "end": 3, "size": 1000}]
