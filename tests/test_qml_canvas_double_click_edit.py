from __future__ import annotations

from pathlib import Path

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

REPO_ROOT = Path(__file__).resolve().parents[1]


def _workspace(width: int = 320, height: int = 240) -> WorkspaceViewModel:
    document = Document()
    document.create_new(width, height)
    document._history_manager.clear()
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


@pytest.mark.unit
def test_double_click_on_text_layer_selects_and_allows_text_edit():
    workspace = _workspace()
    text = TextLayer(name="标题", x=20, y=30, width=180, height=60)
    workspace.document.add_text_layer(text)

    assert workspace.beginTextEditAt(30, 40) is True
    assert workspace.selectedLayerIndex == 0
    assert workspace.selectedIsTextLayer is True


@pytest.mark.unit
def test_double_click_ignores_non_text_layers():
    workspace = _workspace()
    workspace.document.add_layer("图片", 10, 10, 100, 80)
    workspace.clearSelection()

    assert workspace.beginTextEditAt(50, 50) is False
    assert workspace.selectedLayerIndex < 0


@pytest.mark.unit
def test_double_click_ignores_empty_canvas_area():
    workspace = _workspace()
    text = TextLayer(name="标题", x=20, y=30, width=180, height=60)
    workspace.document.add_text_layer(text)

    assert workspace.beginTextEditAt(250, 200) is False


@pytest.mark.unit
def test_double_click_ignores_locked_text_layer():
    workspace = _workspace()
    text = TextLayer(name="标题", x=20, y=30, width=180, height=60)
    text.locked = True
    workspace.document.add_text_layer(text)

    assert workspace.beginTextEditAt(30, 40) is False


@pytest.mark.unit
def test_double_click_prefers_topmost_overlapping_text_layer():
    workspace = _workspace()
    workspace.document.add_layer("底层", 10, 10, 200, 120)
    text = TextLayer(name="标题", x=10, y=10, width=200, height=120)
    workspace.document.add_text_layer(text)

    assert workspace.beginTextEditAt(100, 60) is True
    assert workspace.selectedLayerIndex == 1


@pytest.mark.unit
def test_qml_canvas_pointer_has_double_click_text_edit_handler():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert "onDoubleClicked" in source
    assert "beginTextEditAt(mouse.x, mouse.y)" in source
    assert "window.revealTextContentEditing()" in source
    assert "function revealTextContentEditing()" in source


@pytest.mark.unit
def test_canvas_text_overlay_commits_and_cancels_through_view_model():
    workspace = _workspace()
    text = TextLayer(name="标题", x=20, y=30, width=180, height=60)
    text.text_binding_enabled = False
    text.set_text_lines(["原文字"])
    text.set_current_text("原文字", force=True)
    workspace.document.add_text_layer(text)

    assert workspace.beginTextEditAt(30, 40) is True
    assert workspace.startTextEditOverlay() is True
    assert workspace.textEditOverlayVisible is True
    assert workspace.commitTextEditOverlay("新文字") is True
    assert workspace.textEditOverlayVisible is False
    assert text.current_text == "新文字"

    assert workspace.startTextEditOverlay() is True
    assert workspace.cancelTextEditOverlay() is True
    assert workspace.textEditOverlayVisible is False


@pytest.mark.unit
def test_qml_canvas_pointer_double_click_starts_overlay_edit():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert "workspace.startTextEditOverlay()" in source
    assert "window.focusCanvasTextEditor()" in source
    assert "canvasWorkspace.cancelTransform()" in source
    assert "workspace.cropEditing || canvasWorkspace.transformActive" not in source
    assert "id: canvasTextEditOverlay" in source
    assert 'color: "transparent"' in source
    assert "readonly property real handleSize" in source
    assert "workspace.selectedTextAlignmentId === \"center\"" in source
    assert "font.letterSpacing: workspace.selectedTextLetterSpacing" in source
    assert "visible: workspace.selectedLayerIndex >= 0 && !workspace.textEditOverlayVisible" in source
    assert "canvasTextEditInput" in source
    assert "workspace.commitTextEditOverlay(" in source
    assert "workspace.cancelTextEditOverlay()" in source


@pytest.mark.unit
def test_qml_text_content_section_has_reveal_id():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert "id: textContentSection" in source
    assert "selectedTextEditor.beginEdit()" in source


@pytest.mark.unit
def test_vertical_text_double_click_falls_back_to_sidebar_editor():
    workspace = _workspace()
    text = TextLayer(name="竖排", x=20, y=30, width=180, height=60)
    text.vertical_layout = True
    workspace.document.add_text_layer(text)
    assert workspace.beginTextEditAt(30, 40) is True
    assert workspace.startTextEditOverlay() is False
    assert workspace.textEditOverlayVisible is False
