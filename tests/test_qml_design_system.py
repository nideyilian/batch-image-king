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
        "HermesField",
        "HermesPageTabs",
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
    assert len(trailing_toggle_blocks) >= 4
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

    assert "iconName: AppIcons.fileNew" not in main_source
    assert 'tooltip: "新建文档"' in main_source
    assert 'label: "新建画布"' in main_source
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
    theme_source = (QML_ROOT / "components" / "Theme.qml").read_text(encoding="utf-8")

    assert "import QtQuick.Layouts" in value_box_source
    assert "Layout.minimumWidth: 64" in value_box_source
    assert "inspectorLabelColWidth: 64" in theme_source
    assert "inspectorCompactLabelColWidth: 48" in theme_source
    assert "inspectorColSpacing: 8" in theme_source
    assert "inspectorPairBreakpoint: 320" in theme_source
    assert "inspectorTextEditorMaxWidth: 400" in theme_source
    assert "inspectorRowHeight: compactControlHeight" in theme_source
    assert "Layout.fillWidth: true" in value_box_source


@pytest.mark.unit
def test_inspector_field_labels_never_elide_and_follow_the_four_pixel_grid():
    theme_source = (QML_ROOT / "components" / "Theme.qml").read_text(encoding="utf-8")
    field_source = (QML_ROOT / "components" / "HermesField.qml").read_text(encoding="utf-8")
    section_source = (QML_ROOT / "components" / "PropertySection.qml").read_text(encoding="utf-8")

    assert "elide: Text.ElideNone" in field_source
    assert "wrapMode: Text.NoWrap" in field_source
    assert "elide: Text.ElideRight" not in field_source
    assert "horizontalAlignment: Text.AlignLeft" in field_source
    assert "horizontalAlignment: root.compact && root.horizontal" not in field_source
    assert "GridLayout {" in field_source
    assert "Layout.preferredWidth: root.horizontal ? root.labelWidth : -1" in field_source

    for declaration in (
        "inspectorLabelColWidth: 64",
        "inspectorCompactLabelColWidth: 48",
        "inspectorColSpacing: 8",
        "inspectorRowSpacing: 4",
        "inspectorSectionGutter: 8",
    ):
        assert declaration in theme_source

    assert "anchors.leftMargin: Theme.inspectorSectionGutter" in section_source
    assert "anchors.rightMargin: Theme.inspectorSectionGutter" in section_source
    assert "anchors.topMargin: Theme.inspectorRowSpacing" in section_source
    assert "spacing: Theme.inspectorRowSpacing" in section_source
    assert "spacing: 3" not in section_source


@pytest.mark.unit
def test_inspector_uses_hermes_upstream_component_contracts():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")
    theme_source = (QML_ROOT / "components" / "Theme.qml").read_text(encoding="utf-8")
    field_source = (QML_ROOT / "components" / "HermesField.qml").read_text(encoding="utf-8")
    tabs_source = (QML_ROOT / "components" / "HermesPageTabs.qml").read_text(encoding="utf-8")
    button_source = (QML_ROOT / "components" / "AppButton.qml").read_text(encoding="utf-8")
    switch_source = (QML_ROOT / "components" / "ToggleSwitch.qml").read_text(encoding="utf-8")

    for token in (
        "space1",
        "space2",
        "buttonHeightXs",
        "buttonHeightSm",
        "buttonHeightMd",
        "buttonHeightLg",
        "inputHeightSm",
        "inputHeightMd",
        "inputHeightLg",
        "inputPaddingX",
        "tabHeight",
        "switchWidth",
        "switchHeight",
        "switchThumbSize",
    ):
        assert f"property int {token}" in theme_source

    for declaration in (
        'property string orientation: "vertical"',
        "property string label",
        "property string hint",
        "property string error",
        "property bool required",
        "default property alias controls",
    ):
        assert declaration in field_source
    assert "font.pixelSize: Theme.fieldLabelFontSize" in field_source
    assert "font.pixelSize: Theme.fieldHintFontSize" in field_source

    assert "Accessible.role: Accessible.PageTabList" in tabs_source
    assert "Keys.onLeftPressed" in tabs_source
    assert "Keys.onRightPressed" in tabs_source
    assert "height: Theme.tabHeight" in tabs_source

    for variant in ('"solid"', '"soft"', '"outline"', '"ghost"', '"plain"'):
        assert variant in button_source
    assert "property string tone" in button_source
    assert "property string size" in button_source

    assert "implicitWidth: Theme.switchWidth" in switch_source
    assert "implicitHeight: Theme.switchHeight" in switch_source
    assert "width: Theme.switchThumbSize" in switch_source

    assert "component InspectorRow: HermesField" in main_source
    assert "component CompactInspectorField: HermesField" in main_source
    assert "HermesPageTabs {" not in main_source
    assert 'items: ["基本参数", "更多参数"]' not in main_source


@pytest.mark.unit
def test_inspector_keeps_a_stable_single_axis_layout():
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
    assert "ScrollBar.horizontal.policy: ScrollBar.AlwaysOff" in scroll_block
    assert "contentItem.contentY = Math.max(0" in main_source


@pytest.mark.unit
def test_inspector_uses_one_section_title_layer_and_hairline_rules():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")

    assert "component InspectorModuleHeader" not in main_source
    assert "InspectorModuleHeader {" not in main_source
    assert "height: 1" in main_source
    assert "Layout.fillWidth: true" in main_source


@pytest.mark.unit
def test_field_controls_fill_the_flexible_column_by_default():
    component_sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in (QML_ROOT / "components").glob("*.qml")
    }

    for name in ("AppTextArea.qml", "FontSelectBox.qml",
                 "SegmentedControl.qml", "ValueBox.qml"):
        assert "Layout.fillWidth: true" in component_sources[name]
        assert "import QtQuick.Layouts" in component_sources[name]
    for name in ("AppTextField.qml", "SelectBox.qml"):
        assert "property bool fullWidth: true" in component_sources[name]
        assert "Layout.fillWidth: fullWidth" in component_sources[name]
        assert "import QtQuick.Layouts" in component_sources[name]
    for name in ("FontSelectBox.qml", "SelectBox.qml", "SegmentedControl.qml"):
        assert "Layout.minimumWidth: 0" in component_sources[name]


@pytest.mark.unit
def test_layer_sidebar_resizes_while_inspector_uses_a_fixed_compact_width():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")
    theme_source = (QML_ROOT / "components" / "Theme.qml").read_text(encoding="utf-8")

    for token in (
        "layerPanelMinWidth",
        "layerPanelMaxWidth",
        "inspectorPanelWidth",
        "canvasMinWidth",
        "sidebarResizeHandleWidth",
        "sidebarResizeStep",
    ):
        assert f"property int {token}" in theme_source

    for marker in (
        'category: "sidebarLayout"',
        "property real layerPanelWidth: -1",
        "function setLayerPanelWidth(value)",
        "function resetLayerPanelWidth()",
        "component SidebarResizeHandle",
        "id: layerPanelResizeHandle",
        "onDoubleClicked: resizeHandle.resetRequested()",
        "onPositionChanged: mouse =>",
        "previousX = resizeMouse.mapToItem(null, mouse.x, mouse.y).x",
        "var sceneX = resizeMouse.mapToItem(null, mouse.x, mouse.y).x",
        "var delta = sceneX - previousX",
        "resizeHandle.dragMoved(delta)",
        "Layout.preferredWidth: window.layerPanelWidth",
        "Layout.minimumWidth: Theme.inspectorPanelWidth",
        "Layout.preferredWidth: Theme.inspectorPanelWidth",
        "Layout.maximumWidth: Theme.inspectorPanelWidth",
    ):
        assert marker in main_source
    for obsolete_marker in (
        "property real inspectorPanelWidth",
        "function setInspectorPanelWidth(value)",
        "function resetInspectorPanelWidth()",
        "id: inspectorResizeHandle",
        "objectName: \"inspectorResizeHandle\"",
        "inspectorPanelMinWidth",
        "inspectorPanelMaxWidth",
    ):
        assert obsolete_marker not in main_source
        assert obsolete_marker not in theme_source
    assert "inspectorPanelWidth: 320" in theme_source
    assert "Layout.maximumWidth: Theme.inspectorTextEditorMaxWidth" in main_source


@pytest.mark.unit
def test_inspector_uses_adaptive_semantic_pair_grids_without_collapsed_sections():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")
    grid_source = (QML_ROOT / "components" / "HermesAdaptiveFieldGrid.qml").read_text(encoding="utf-8")

    assert "component AdaptiveInspectorGrid: HermesAdaptiveFieldGrid" in main_source
    assert "columns: width >= pairBreakpoint ? 2 : 1" in grid_source
    for grid_id in (
        "vectorPathCompactGrid",
        "layerTransformCompactGrid",
        "randomPositionCompactGrid",
        "randomScaleCompactGrid",
        "randomRotationCompactGrid",
        "overlayCompactGrid",
    ):
        assert f"id: {grid_id}" in main_source

    assert "expanded: false" not in main_source
