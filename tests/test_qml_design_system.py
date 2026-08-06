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

    assert len(toggle_blocks) == 33
    assert all("accessibleName:" in block for block in toggle_blocks)


@pytest.mark.unit
def test_new_canvas_dialog_offers_ecommerce_presets():
    main_source = (QML_ROOT / "Main.qml").read_text(encoding="utf-8")

    for preset in (
        '{ name: "商品主图", width: 800, height: 800 }',
        '{ name: "高清方图", width: 1080, height: 1080 }',
        '{ name: "商品竖图 4:5", width: 1080, height: 1350 }',
        '{ name: "详情页切片", width: 750, height: 1000 }',
    ):
        assert preset in main_source


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
