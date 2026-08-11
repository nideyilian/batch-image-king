from __future__ import annotations

from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = REPO_ROOT / "app" / "qml"


def _qml_component_blocks(source: str, component_name: str) -> list[str]:
    blocks: list[str] = []
    pattern = re.compile(rf"\b{re.escape(component_name)}\s*\{{")
    for match in pattern.finditer(source):
        depth = 0
        for index in range(match.end() - 1, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(source[match.start():index + 1])
                    break
    return blocks


@pytest.mark.unit
def test_qml_theme_exposes_the_production_console_tokens():
    source = (QML_ROOT / "components" / "Theme.qml").read_text(encoding="utf-8")

    for token in (
        "bgApp",
        "bgBar",
        "bgPanel",
        "bgRaised",
        "bgControl",
        "bgHover",
        "bgSelected",
        "borderStrong",
        "focusRing",
        "textPrimary",
        "textSecondary",
        "textMuted",
        "textDisabled",
        "accent",
        "accentHover",
        "accentPressed",
        "accentSoft",
        "accentForeground",
        "info",
        "warning",
        "danger",
        "success",
        "overlayModal",
        "errorSurface",
        "errorBorder",
        "errorText",
        "successSurface",
        "successBorder",
        "progressTrack",
        "controlHeight",
        "commandHeight",
        "toolButtonSize",
    ):
        assert f"property color {token}" in source or f"property int {token}" in source


@pytest.mark.unit
def test_qml_component_library_covers_core_controls():
    component_names = {
        path.stem for path in (QML_ROOT / "components").glob("*.qml")
    }

    assert {
        "AppButton",
        "AppDialog",
        "AppDrawer",
        "AppIcon",
        "AppMenu",
        "AppProgressBar",
        "AppTextArea",
        "AppTextField",
        "FontSelectBox",
        "IconButton",
        "OptionTile",
        "AppIcons",
        "PropertySection",
        "SegmentedControl",
        "SelectBox",
        "StatusBanner",
        "Theme",
        "ToggleSwitch",
        "ValueBox",
    } <= component_names


@pytest.mark.unit
def test_qml_uses_semantic_lucide_icons_instead_of_raw_codepoints():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")
    icon_source = (QML_ROOT / "components" / "AppIcon.qml").read_text(encoding="utf-8")
    registry_source = (QML_ROOT / "components" / "AppIcons.qml").read_text(encoding="utf-8")

    assert "property string iconName" in icon_source
    assert "import QtQuick.Controls.impl" in icon_source
    assert "IconImage" in icon_source
    assert "MultiEffect" not in icon_source
    assert "function source(iconName)" in registry_source
    assert 'property string circleDot: "circle-dot"' in registry_source
    assert (QML_ROOT / "icons" / "circle-dot.svg").exists()
    assert "iconName:" in main_source
    assert not re.search(r"glyph\s*:\s*[\"']\\u[0-9A-Fa-f]{4}", main_source)


@pytest.mark.unit
def test_main_qml_uses_shared_controls_for_inputs_and_overlays():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")

    assert not re.search(
        r"^\s*(TextField|TextArea|Dialog|Drawer|Menu)\s*\{",
        main_source,
        flags=re.MULTILINE,
    )
    for component in (
        "AppDialog",
        "AppDrawer",
        "AppMenu",
        "AppProgressBar",
        "AppTextArea",
        "AppTextField",
        "StatusBanner",
    ):
        assert f"{component} {{" in main_source


@pytest.mark.unit
def test_layer_model_exposes_semantic_icon_name_and_keeps_legacy_glyph():
    source = (QML_ROOT / "viewmodels" / "layer_list_model.py").read_text(encoding="utf-8")

    assert 'QByteArray(b"iconName")' in source
    assert "def layer_icon_name" in source
    assert 'QByteArray(b"glyph")' in source


@pytest.mark.unit
def test_qml_icon_assets_are_included_in_both_packaging_paths():
    build_source = (REPO_ROOT / "build.py").read_text(encoding="utf-8")
    spec_source = (REPO_ROOT / "批图王.spec").read_text(encoding="utf-8")

    assert "app/qml/icons" in build_source
    assert "app/qml/icons" in spec_source
    assert any((QML_ROOT / "icons").glob("*.svg"))


@pytest.mark.unit
def test_all_toggle_switches_have_accessible_names():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")
    toggle_blocks = _qml_component_blocks(main_source, "ToggleSwitch")
    trailing_toggle_blocks = _qml_component_blocks(main_source, "TrailingToggle")

    assert toggle_blocks
    assert len(trailing_toggle_blocks) == 8
    assert all("accessibleName:" in block for block in toggle_blocks + trailing_toggle_blocks)


@pytest.mark.unit
def test_option_tile_supports_compact_and_accessible_selection_modes():
    source = (QML_ROOT / "components" / "OptionTile.qml").read_text(encoding="utf-8")

    for declaration in (
        "property string title",
        "property string detail",
        "property bool selected",
        "property bool compact",
        "property bool exclusive",
        "signal activated()",
    ):
        assert declaration in source
    assert "Keys.onSpacePressed: activated()" in source
    assert "Keys.onReturnPressed: activated()" in source
    assert "exclusive ? Accessible.RadioButton : Accessible.CheckBox" in source
    assert "Accessible.checked: selected" in source


@pytest.mark.unit
def test_new_canvas_dialog_offers_editable_quick_presets():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")

    for preset in (
        '{ name: "方形图", width: 800, height: 800 }',
        '{ name: "横版 16:9", width: 1280, height: 720 }',
        '{ name: "竖版 9:16", width: 1080, height: 1920 }',
    ):
        assert preset in main_source
    assert 'property string quickPresetsJson: ""' in main_source
    assert "function replaceQuickCanvasPreset(" in main_source
    assert 'objectName: "quickCanvasPresetDialog"' in main_source
    assert 'tooltip: "编辑常用尺寸"' in main_source
    assert "buttonSize: 32" in main_source


@pytest.mark.unit
def test_canvas_quick_actions_and_image_drop_contract():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")

    assert 'iconName: AppIcons.fileNew; tooltip: "新建画布 · Ctrl+N"' in main_source
    assert 'tooltip: "添加素材文件夹"' not in main_source
    assert "DropArea {" in main_source
    assert "drag.hasUrls && window.hasSupportedImageUrl(drag.urls)" in main_source
    assert "window.addDroppedImages(drop.urls)" in main_source
    assert "workspace.addImageLayer(String(urlValue))" in main_source


@pytest.mark.unit
def test_binding_drawer_keeps_empty_state_and_creation_footer_accessible():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")

    assert 'objectName: "bindingEmptyState"' in main_source
    assert 'text: "请先选择至少 2 个图层"' in main_source
    assert 'text: "返回选择图层"' in main_source
    assert 'objectName: "bindingCreationFooter"' in main_source
    assert "Layout.preferredHeight: Math.max(140, dataRelationsDrawer.height - 470)" in main_source


@pytest.mark.unit
def test_compact_inspector_fields_keep_readable_layout_widths():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")
    value_box_source = (QML_ROOT / "components" / "ValueBox.qml").read_text(encoding="utf-8")

    assert "import QtQuick.Layouts" in value_box_source
    assert "Layout.minimumWidth: 64" in value_box_source
    assert "Layout.preferredWidth: 52" in main_source
    assert "Layout.minimumWidth: 52" in main_source
    assert "Layout.maximumWidth: 52" in main_source


@pytest.mark.unit
def test_inspector_tab_switch_keeps_a_stable_single_axis_layout():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")
    scroll_block = next(
        block
        for block in _qml_component_blocks(main_source, "ScrollView")
        if 'objectName: "inspectorScroll"' in block
    )
    grid_block = next(
        block
        for block in _qml_component_blocks(main_source, "GridLayout")
        if "id: propertyInspectorColumn" in block
    )
    ordered_sections = [
        block
        for block in _qml_component_blocks(grid_block, "PropertySection")
        if "Layout.row:" in block
    ]

    assert "contentWidth: availableWidth" in scroll_block
    assert "width: inspectorScroll.contentWidth" in grid_block
    assert len(ordered_sections) >= 10
    assert all("Layout.fillWidth: true" in block for block in ordered_sections)
    assert "contentItem.contentX = 0" in main_source
    assert "contentItem.contentY = 0" in main_source
