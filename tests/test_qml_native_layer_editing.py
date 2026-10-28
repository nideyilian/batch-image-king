from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from app.models.document import Document
from app.models.layer_properties import ShapeType
from app.models.shaped_layer_new import ShapedLayer
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


REPO_ROOT = Path(__file__).resolve().parents[1]


def _workspace() -> WorkspaceViewModel:
    document = Document()
    document.create_new(640, 480)
    document._history_manager.clear()
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


@pytest.mark.unit
def test_focus_sensitive_qml_editors_preserve_the_current_value():
    value_box = (REPO_ROOT / "app/qml/components/ValueBox.qml").read_text(encoding="utf-8")
    font_box = (REPO_ROOT / "app/qml/components/FontSelectBox.qml").read_text(encoding="utf-8")
    content_editor = (REPO_ROOT / "app/qml/components/ContentTextEditor.qml").read_text(encoding="utf-8")
    main_qml = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    for source in (value_box, font_box):
        assert "restoreMode: Binding.RestoreNone" in source
        assert "selectAll()" in source
        assert "function beginEdit()" in source
    # P1-5 拆分：ContentTextEditor 内联 component 迁入 components/（无 selectAll 语义）
    assert "restoreMode: Binding.RestoreNone" in content_editor
    assert "function beginEdit()" in content_editor

    assert "if (root.bindValue)" in value_box
    assert "input.text = String(root.value)" in value_box
    assert value_box.count("if (root.bindValue)") >= 3

    assert "contentEditor.text = textEditorRoot.value" in content_editor


@pytest.mark.unit
def test_font_selector_opens_full_catalog_before_the_user_types():
    font_box = (REPO_ROOT / "app/qml/components/FontSelectBox.qml").read_text(
        encoding="utf-8"
    )

    focus_handler = font_box.split("onActiveFocusChanged:", 1)[1].split(
        "onTextEdited:", 1
    )[0]
    assert font_box.count('root.query = ""') >= 2
    assert "root.query = fontInput.text" not in font_box
    assert 'root.query = ""' in focus_handler
    assert "root.query = text" not in focus_handler
    assert "root.query = text" in font_box
    assert "fontInput.focus = false" in font_box


@pytest.mark.unit
def test_font_selector_supports_family_rows_and_face_leaf_selection():
    font_box = (REPO_ROOT / "app/qml/components/FontSelectBox.qml").read_text(
        encoding="utf-8"
    )

    assert "property string face" in font_box
    assert "property var expandedFamilies" in font_box
    assert "children" in font_box
    assert "kind: \"family\"" in font_box
    assert "kind: \"face\"" in font_box
    assert "signal activated(string value, string face)" in font_box
    assert "root.activated(row.family, row.face)" in font_box


@pytest.mark.unit
def test_layer_ui_uses_native_qml_dialogs_and_inline_rename():
    main_qml = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    bridge = (REPO_ROOT / "app/qml/legacy_feature_bridge.py").read_text(encoding="utf-8")

    assert 'id: textLayerDialog' in main_qml
    assert 'id: shapedLayerDialog' in main_qml
    assert 'objectName: "effectColorDialog"' in main_qml
    assert "ColorDialog {" not in main_qml
    assert "workspace.addConfiguredTextLayer(" in main_qml
    assert "workspace.addConfiguredShapedLayer(" in main_qml
    assert "function revealLayerNameEditor()" in main_qml
    assert "window.revealLayerNameEditor()" in main_qml

    for old_call in (
        "legacyTools.openAddTextLayer()",
        "legacyTools.openAddShapedLayer()",
        "legacyTools.renameSelectedLayer()",
    ):
        assert old_call not in main_qml

    assert "def openAddTextLayer" not in bridge
    assert "def openAddShapedLayer" not in bridge
    assert "def renameSelectedLayer" not in bridge


@pytest.mark.unit
def test_configured_text_layer_matches_the_classic_creation_contract():
    workspace = _workspace()

    assert workspace.addConfiguredTextLayer(
        {
            "name": "促销标题",
            "content": "新品上市\n限时特惠",
            "bindingEnabled": True,
            "fontFamily": "Arial",
            "fontFace": "Bold",
            "fontSize": 36,
            "color": "#123456CC",
            "alignment": "center",
        }
    ) is True

    layer = workspace.document.layers[0]
    assert isinstance(layer, TextLayer)
    assert layer.name == "促销标题"
    # 位置固定 50,50；尺寸**由 auto_fit_text_box 按内容撑开**。
    #
    # 2026-10-28：原来这里断言 (300, 100)。那个值只有关掉自动适配时才成立，
    # 而关掉自动适配会把大字号文字直接裁掉（旧版 layer_controller 对此有专门注释：
    # 72px 的「限时特惠 5折」只渲染出「限时特惠」）。旧版契约是 auto_fit=True，
    # 所以正确断言是「位置不变 + 自动适配开启 + 尺寸按内容算出来」，不是写死 300x100。
    assert (layer.x, layer.y) == (50, 50)
    assert layer.auto_fit_text_box is True
    assert layer.width > 0 and layer.height > 0
    assert (layer.width, layer.height) != (300, 100), (
        "尺寸仍是未自适应的 300x100，说明 auto_fit_text_box 没生效"
    )
    assert layer.get_text_lines() == ["新品上市", "限时特惠"]
    assert layer.current_text == "新品上市"
    assert layer.text_binding_enabled is True
    assert layer.font_family == "Arial"
    assert layer.font_face == "Bold"
    assert layer.font_size == 36
    assert layer.text_color == (0x12, 0x34, 0x56, 0xCC)
    assert str(layer.text_align).upper().endswith("CENTER")
    assert workspace.selectedLayerIndex == 0

    assert workspace.undo() is True
    assert workspace.document.layers == []


@pytest.mark.unit
def test_configured_shaped_layer_allows_empty_source_and_shape_parameters():
    workspace = _workspace()

    assert workspace.addConfiguredShapedLayer(
        {
            "name": "留空梯形",
            "shapeType": "right_trapezoid",
            "x": -20,
            "y": 35,
            "width": 240,
            "height": 180,
            "source": "",
            "sourceIsFolder": True,
            "useOriginalSize": False,
            "trapezoidTopRatio": 75,
            "trapezoidBottomRatio": 50,
            "trapezoidSlopeSide": "left",
        }
    ) is True

    layer = workspace.document.layers[0]
    assert isinstance(layer, ShapedLayer)
    assert layer.name == "留空梯形"
    assert layer.shape_type == ShapeType.RIGHT_TRAPEZOID
    assert (layer.x, layer.y, layer.width, layer.height) == (-20, 35, 240, 180)
    assert layer.image_source is None
    assert layer.current_image_path is None
    assert layer.is_folder is True
    assert layer.trapezoid_top_width == 180
    assert layer.trapezoid_bottom_width == 120
    assert layer.trapezoid_slope_side == "left"


@pytest.mark.unit
def test_configured_shaped_layer_accepts_a_folder_source(tmp_path: Path):
    source = tmp_path / "素材"
    source.mkdir()
    image_path = source / "01.png"
    Image.new("RGBA", (30, 20), (20, 180, 120, 255)).save(image_path)
    workspace = _workspace()

    assert workspace.addConfiguredShapedLayer(
        {
            "name": "文件夹圆形",
            "shapeType": "circle",
            "x": 10,
            "y": 12,
            "width": 200,
            "height": 160,
            "source": str(source),
            "sourceIsFolder": True,
            "useOriginalSize": False,
        }
    ) is True

    layer = workspace.document.layers[0]
    assert layer.shape_type == ShapeType.CIRCLE
    assert layer.is_folder is True
    assert Path(layer.image_source) == source
    assert Path(layer.current_image_path) == image_path
