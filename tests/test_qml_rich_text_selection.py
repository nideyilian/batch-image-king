from __future__ import annotations

from pathlib import Path

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.utils.text_rich_format import parse_editor_html


pytestmark = pytest.mark.unit
REPO_ROOT = Path(__file__).resolve().parents[1]


def _workspace() -> tuple[WorkspaceViewModel, TextLayer]:
    document = Document()
    document.create_new(480, 320)
    layer = TextLayer(name="标题", x=20, y=30, width=320, height=120)
    layer.text_binding_enabled = False
    layer.auto_fit_text_box = False
    layer.font_size = 24
    layer.text_color = (10, 20, 30, 255)
    layer.set_text_lines(["A😀BC"])
    layer.set_current_text("A😀BC", force=True)
    document.add_text_layer(layer)
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    return workspace, layer


def test_view_model_editor_style_is_draft_until_rich_text_commit():
    workspace, layer = _workspace()
    original_html = workspace.selectedTextEditorHtml

    styled_html = workspace.applyTextEditorFontSize(original_html, 1, 3, 60)
    styled_html = workspace.applyTextEditorColor(styled_html, 3, 5, "#32A0F0")
    info = workspace.inspectTextEditorSelection(styled_html, 1, 3)

    assert info["characterCount"] == 1
    assert info["fontSize"] == 60
    assert layer.get_font_size_ranges() == []
    assert layer.get_text_color_ranges() == []

    assert workspace.startTextEditOverlay() is True
    assert workspace.commitTextEditOverlayRichText(styled_html) is True
    assert layer.current_text == "A😀BC"
    assert layer.get_font_size_ranges() == [{"start": 1, "end": 2, "size": 60}]
    assert layer.get_text_color_ranges() == [
        {"start": 2, "end": 4, "color": (50, 160, 240, 255)}
    ]


def test_rich_text_commit_supports_undo_redo_and_project_round_trip(tmp_path):
    workspace, _layer = _workspace()
    assert workspace.startTextEditOverlay() is True
    html = workspace.applyTextEditorFontSize(workspace.selectedTextEditorHtml, 1, 3, 60)
    html = workspace.applyTextEditorColor(html, 3, 5, "#32A0F0")
    assert workspace.commitTextEditOverlayRichText(html) is True

    assert workspace.undo() is True
    restored = workspace.document.layers[0]
    assert restored.get_font_size_ranges() == []
    assert restored.get_text_color_ranges() == []

    assert workspace.redo() is True
    restored = workspace.document.layers[0]
    assert restored.get_font_size_ranges() == [{"start": 1, "end": 2, "size": 60}]
    assert restored.get_text_color_ranges() == [
        {"start": 2, "end": 4, "color": (50, 160, 240, 255)}
    ]

    project = tmp_path / "rich-text-selection.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    loaded = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert loaded.openDocument(str(project)) is True
    loaded_layer = loaded.document.layers[0]
    assert loaded_layer.get_font_size_ranges() == [{"start": 1, "end": 2, "size": 60}]
    assert loaded_layer.get_text_color_ranges() == [
        {"start": 2, "end": 4, "color": (50, 160, 240, 255)}
    ]


def test_cancel_discards_staged_rich_text_draft():
    workspace, layer = _workspace()
    draft = workspace.selectedTextEditorHtml.replace("A😀BC", "已修改")

    assert workspace.startTextEditOverlay() is True
    assert workspace.stageTextEditOverlayDraft(draft) is True
    assert workspace.cancelTextEditOverlay() is True
    assert layer.current_text == "A😀BC"


def test_switching_layers_commits_last_staged_rich_text_draft():
    workspace, layer = _workspace()
    draft = workspace.selectedTextEditorHtml.replace("A😀BC", "新标题")
    other = TextLayer(name="其他", x=10, y=180, width=160, height=80)
    workspace.document.add_text_layer(other)
    workspace.layerModel.reset_from_document()
    workspace.selectLayer(0)

    assert workspace.startTextEditOverlay() is True
    assert workspace.stageTextEditOverlayDraft(draft) is True
    assert workspace.selectLayer(1) is True
    assert layer.current_text == "新标题"
    assert workspace.textEditOverlayVisible is False


def test_clear_editor_style_restores_layer_base_style():
    workspace, layer = _workspace()
    html = workspace.applyTextEditorFontSize(workspace.selectedTextEditorHtml, 0, 5, 48)
    html = workspace.applyTextEditorColor(html, 0, 5, "#FF0000")
    cleared = workspace.clearTextEditorStyle(html, 1, 3)
    state = parse_editor_html(
        cleared,
        base_font_size=layer.font_size,
        base_text_color=layer.text_color,
    )

    assert state.font_size_ranges == [
        {"start": 0, "end": 1, "size": 48},
        {"start": 2, "end": 4, "size": 48},
    ]
    assert state.color_ranges == [
        {"start": 0, "end": 1, "color": (255, 0, 0, 255)},
        {"start": 2, "end": 4, "color": (255, 0, 0, 255)},
    ]


def test_qml_canvas_editor_declares_rich_text_selection_contract():
    source = (REPO_ROOT / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")

    assert "textFormat: TextEdit.RichText" in source
    assert "id: canvasTextSelectionToolbar" in source
    assert "workspace.inspectTextEditorSelection(" in source
    assert "workspace.applyTextEditorFontSize(" in source
    assert "workspace.commitTextEditOverlayRichText(" in source
    assert "workspace.stageTextEditOverlayDraft(" in source
