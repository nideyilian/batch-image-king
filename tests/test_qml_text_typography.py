from __future__ import annotations

from pathlib import Path

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace() -> tuple[WorkspaceViewModel, TextLayer]:
    document = Document()
    document.create_new(420, 320)
    text_layer = TextLayer(name="标题", x=30, y=40, width=280, height=120)
    text_layer.text_binding_enabled = False
    text_layer.set_text_lines(["新品上市\n限时特惠"])
    text_layer.set_current_text("新品上市\n限时特惠", force=True)
    text_layer.auto_fit_text_box = False
    document.add_text_layer(text_layer)
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    return workspace, text_layer


@pytest.mark.unit
def test_text_font_options_and_style_combinations(monkeypatch):
    workspace, layer = _workspace()
    monkeypatch.setattr(
        layer,
        "get_categorized_fonts",
        lambda: {
            "chinese": ["Microsoft YaHei", "Source Han Sans SC"],
            "english": ["Arial"],
        },
    )
    monkeypatch.setattr(layer, "get_font_faces", lambda: {})
    workspace._text_font_options_cache = None
    workspace._text_font_tree_options_cache = None

    assert workspace.selectedTextFontFamily == layer.font_family
    assert [item["value"] for item in workspace.selectedTextFontOptions] == [
        "Microsoft YaHei",
        "Source Han Sans SC",
    ]

    assert workspace.setSelectedTextFontFamily("  Source Han Sans SC  ") is True
    assert layer.font_family == "Source Han Sans SC"
    assert workspace.setSelectedTextBold(True) is True
    assert layer.font_style == "BOLD"
    assert workspace.selectedTextBold is True
    assert workspace.selectedTextItalic is False
    assert workspace.setSelectedTextItalic(True) is True
    assert layer.font_style == "BOLD_ITALIC"
    assert workspace.setSelectedTextBold(False) is True
    assert layer.font_style == "ITALIC"
    assert workspace.setSelectedTextItalic(False) is True
    assert layer.font_style == "NORMAL"
    assert workspace.setSelectedTextFontFamily("   ") is False


@pytest.mark.unit
def test_local_font_catalog_uses_canonical_family_names_and_chinese_labels(monkeypatch):
    workspace, layer = _workspace()
    monkeypatch.setattr(
        layer,
        "get_categorized_fonts",
        lambda: {
            "chinese": ["Microsoft YaHei", "Local Poster Font", "Microsoft YaHei"],
            "english": ["Arial"],
        },
    )
    monkeypatch.setattr(
        layer,
        "get_font_cn_names",
        lambda: {"Microsoft YaHei": "微软雅黑", "Local Poster Font": "本地海报体"},
    )
    workspace._text_font_options_cache = None

    assert workspace.textFontOptions == [
        {"label": "微软雅黑 (Microsoft YaHei)", "value": "Microsoft YaHei"},
        {"label": "本地海报体 (Local Poster Font)", "value": "Local Poster Font"},
    ]
    assert workspace.selectedTextFontOptions[0] == {
        "label": "微软雅黑 (Microsoft YaHei)",
        "value": "Microsoft YaHei",
    }

    assert workspace.setSelectedTextFontFamily("本地海报体") is True
    assert layer.font_family == "Local Poster Font"


@pytest.mark.unit
def test_non_chinese_current_font_is_not_added_to_the_visible_catalog(monkeypatch):
    workspace, layer = _workspace()
    layer.font_family = "Arial"
    monkeypatch.setattr(
        layer,
        "get_categorized_fonts",
        lambda: {
            "chinese": ["Microsoft YaHei", "SimSun"],
            "english": ["Arial", "Segoe UI"],
        },
    )
    workspace._text_font_options_cache = None

    assert workspace.selectedTextFontFamily == "Arial"
    assert [item["value"] for item in workspace.textFontOptions] == [
        "Microsoft YaHei",
        "SimSun",
    ]
    assert workspace.selectedTextFontOptions == workspace.textFontOptions


@pytest.mark.unit
def test_font_tree_groups_faces_and_maps_bold_italic_to_real_faces(monkeypatch):
    workspace, layer = _workspace()
    layer.font_face = "Regular"
    monkeypatch.setattr(
        layer,
        "get_categorized_fonts",
        lambda: {"chinese": ["Demo Sans SC"], "english": []},
    )
    monkeypatch.setattr(
        layer,
        "get_font_faces",
        lambda: {
            "Demo Sans SC": [
                {"style": "Regular", "path": "regular.ttf", "weight": 400, "italic": False},
                {"style": "Light", "path": "light.ttf", "weight": 300, "italic": False},
                {"style": "Bold", "path": "bold.ttf", "weight": 700, "italic": False},
                {"style": "Italic", "path": "italic.ttf", "weight": 400, "italic": True},
                {"style": "Bold Italic", "path": "bold-italic.ttf", "weight": 700, "italic": True},
            ]
        },
    )
    workspace._text_font_options_cache = None
    workspace._text_font_tree_options_cache = None

    tree = workspace.textFontTreeOptions
    assert tree[0]["value"] == "Demo Sans SC"
    assert [face["value"] for face in tree[0]["children"]] == [
        "Light",
        "Regular",
        "Italic",
        "Bold",
        "Bold Italic",
    ]

    assert workspace.setSelectedTextFontFace("Demo Sans SC", "Bold") is True
    assert layer.font_family == "Demo Sans SC"
    assert layer.font_face == "Bold"
    assert layer.font_style == "NORMAL"
    assert workspace.selectedTextBold is True
    assert workspace.selectedTextItalic is False

    assert workspace.setSelectedTextItalic(True) is True
    assert layer.font_face == "Bold Italic"
    assert workspace.selectedTextBold is True
    assert workspace.selectedTextItalic is True

    assert workspace.setSelectedTextBold(False) is True
    assert layer.font_face == "Italic"
    assert layer.font_style == "NORMAL"


@pytest.mark.unit
def test_new_text_dialog_uses_local_font_catalog():
    qml_source = (Path(__file__).resolve().parents[1] / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")

    assert "options: workspace.textFontTreeOptions" in qml_source
    assert '{ label: "Microsoft YaHei", value: "Microsoft YaHei" }' not in qml_source


@pytest.mark.unit
def test_text_layout_properties_and_commands_are_mapped():
    workspace, layer = _workspace()

    assert workspace.selectedTextAlignmentId == "left"
    assert workspace.setSelectedTextAlignment("center") is True
    assert layer.text_align == "CENTER"
    assert workspace.selectedTextAlignmentId == "center"
    assert workspace.setSelectedTextAlignment("right") is True
    assert layer.text_align == "RIGHT"
    assert workspace.setSelectedTextAlignment("unknown") is False

    assert workspace.setSelectedTextLineSpacingPercent(360) is True
    assert workspace.selectedTextLineSpacingPercent == 300
    assert layer.line_spacing == pytest.approx(3.0)
    assert workspace.setSelectedTextLineSpacingPercent(20) is True
    assert workspace.selectedTextLineSpacingPercent == 50

    assert workspace.setSelectedTextLetterSpacing(-99) is True
    assert workspace.selectedTextLetterSpacing == -20
    assert workspace.setSelectedTextLetterSpacing(180) is True
    assert workspace.selectedTextLetterSpacing == 100

    assert workspace.setSelectedTextBoxPadding(-8) is True
    assert workspace.selectedTextBoxPadding == 0
    assert workspace.setSelectedTextBoxPadding(500) is True
    assert workspace.selectedTextBoxPadding == 200

    assert workspace.setSelectedTextVerticalLayout(True) is True
    assert workspace.selectedTextVerticalLayout is True
    assert workspace.setSelectedTextAutoFitTextBox(True) is True
    assert workspace.selectedTextAutoFitTextBox is True


@pytest.mark.unit
def test_text_typography_commands_reject_wrong_or_locked_layers():
    workspace, layer = _workspace()
    layer.locked = True
    workspace.selectionChanged.emit()

    assert workspace.setSelectedTextFontFamily("Arial") is False
    assert workspace.setSelectedTextBold(True) is False
    assert workspace.setSelectedTextAlignment("center") is False
    assert workspace.setSelectedTextVerticalLayout(True) is False
    assert workspace.setSelectedTextLineSpacingPercent(140) is False

    layer.locked = False
    workspace.document.add_layer("图片", 0, 0, 100, 100, is_folder=False)
    workspace.layerModel.reset_from_document()
    workspace.selectLayer(1)
    assert workspace.selectedIsTextLayer is False
    assert workspace.setSelectedTextFontFamily("Arial") is False
    assert workspace.setSelectedTextAutoFitTextBox(True) is False


@pytest.mark.unit
def test_text_typography_undo_redo_and_save_round_trip(tmp_path: Path):
    workspace, _layer = _workspace()

    assert workspace.setSelectedTextFontFamily("Arial") is True
    assert workspace.setSelectedTextBold(True) is True
    assert workspace.setSelectedTextItalic(True) is True
    assert workspace.setSelectedTextAlignment("center") is True
    assert workspace.setSelectedTextLineSpacingPercent(145) is True
    assert workspace.setSelectedTextLetterSpacing(8) is True
    assert workspace.setSelectedTextBoxPadding(18) is True
    assert workspace.setSelectedTextVerticalLayout(True) is True

    assert workspace.undo() is True
    assert workspace.document.layers[0].vertical_layout is False
    assert workspace.redo() is True
    assert workspace.document.layers[0].vertical_layout is True

    project = tmp_path / "text-typography.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    loaded = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
    assert loaded.openDocument(str(project)) is True
    loaded.selectLayer(0)
    layer = loaded.document.layers[0]
    assert layer.font_family == "Arial"
    assert layer.font_style == "BOLD_ITALIC"
    assert layer.text_align == "CENTER"
    assert layer.line_spacing == pytest.approx(1.45)
    assert layer.letter_spacing == 8
    assert layer.text_box_padding == 18
    assert layer.vertical_layout is True


@pytest.mark.unit
def test_text_spacing_and_vertical_layout_change_real_rendering():
    layer = TextLayer(name="排版渲染", width=260, height=180)
    layer.text_binding_enabled = False
    layer.set_text_lines(["AB\nCD"])
    layer.set_current_text("AB\nCD", force=True)
    layer.auto_fit_text_box = False
    layer.font_size = 42
    layer._supersample_enabled = False

    base = layer.render_text().copy()
    base_box = base.getbbox()
    assert base_box is not None

    layer.letter_spacing = 18
    spaced = layer.render_text().copy()
    spaced_box = spaced.getbbox()
    assert spaced_box is not None
    assert spaced.tobytes() != base.tobytes()

    layer.vertical_layout = True
    vertical = layer.render_text()
    vertical_box = vertical.getbbox()
    assert vertical_box is not None
    assert vertical.tobytes() != base.tobytes()
    assert vertical_box != spaced_box
