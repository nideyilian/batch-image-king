from __future__ import annotations

from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_qml_inspector_uses_basic_and_more_parameter_tabs():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert 'items: ["基本参数", "更多参数"]' in source
    assert "HermesPageTabs {" in source
    for section_id in (
        "basicPropertiesSection",
        "imageSourceSection",
        "advancedSettingsSection",
        "shapeSection",
        "appearanceSection",
        "overlaySection",
        "cornerSection",
        "clonePropertiesSection",
        "layerTransformSection",
        "randomTransformSection",
    ):
        assert f"id: {section_id}" in source

    assert 'title: "内容源"' not in source
    assert 'title: "渐变叠加"' not in source
    assert 'model: ["属性", "效果"]' not in source


@pytest.mark.unit
def test_qml_text_background_shadow_and_glow_live_in_more_parameters():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    for section_id in ("textBackgroundSection", "textShadowSection", "textGlowSection"):
        match = re.search(
            rf"id: {section_id}.*?visible: inspectorTab === 1 && workspace\.selectedIsTextLayer",
            source,
            re.S,
        )
        assert match is not None, section_id

    assert re.search(
        r"id: textFillSection.*?visible: inspectorTab === 1 && workspace\.selectedIsTextLayer",
        source,
        re.S,
    )


@pytest.mark.unit
def test_qml_parameter_tabs_isolate_basic_and_more_sections():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert "InspectorModuleHeader" not in source

    basic_sections = (
        "basicPropertiesSection",
        "imageSourceSection",
        "advancedSettingsSection",
        "shapeSection",
        "textContentSection",
        "textFontSection",
        "textTypographySection",
        "appearanceSection",
    )
    advanced_sections = (
        "vectorPathSection",
        "layerTransformSection",
        "randomTransformSection",
        "clonePropertiesSection",
        "textFillSection",
        "textBackgroundSection",
        "textShadowSection",
        "textGlowSection",
        "advancedStrokeSection",
        "overlaySection",
        "cornerSection",
    )

    for section_id in basic_sections:
        block = re.search(rf"id: {section_id}.*?(?=\n\s*PropertySection|\n\s*Column)", source, re.S)
        assert block is not None, section_id
        assert "inspectorTab === 0" in block.group(0), section_id

    for section_id in advanced_sections:
        block = re.search(rf"id: {section_id}.*?(?=\n\s*PropertySection|\n\s*Column)", source, re.S)
        assert block is not None, section_id
        assert "inspectorTab === 1" in block.group(0), section_id


@pytest.mark.unit
def test_qml_random_transform_and_text_editor_adapt_to_inspector_width():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    grid_source = (REPO_ROOT / "app/qml/components/HermesAdaptiveFieldGrid.qml").read_text(encoding="utf-8")

    for grid_id in (
        "randomPositionCompactGrid",
        "randomScaleCompactGrid",
        "randomRotationCompactGrid",
    ):
        assert f"id: {grid_id}" in source
    # P1-5 拆分：AdaptiveInspectorGrid 内联 component 迁入 components/
    adaptive_grid_source = (REPO_ROOT / "app/qml/components/AdaptiveInspectorGrid.qml").read_text(encoding="utf-8")
    assert "HermesAdaptiveFieldGrid {" in adaptive_grid_source
    assert "columns: width >= pairBreakpoint ? 2 : 1" in grid_source
    assert "implicitWidth: 0" in source
    assert "width: Math.min(" in source
    assert "Theme.inspectorTextEditorMaxWidth" in source
    assert "Layout.maximumWidth: Theme.inspectorTextEditorMaxWidth" in source
    assert "Layout.minimumWidth: 0" in source


@pytest.mark.unit
def test_qml_color_picker_has_photoshop_style_controls():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    for marker in (
        "id: saturationValueField",
        "id: hueStrip",
        "function setHsv",
        "function setRgb",
        'text: "新颜色"',
        'text: "原颜色"',
        'accessibleName: "十六进制颜色"',
    ):
        assert marker in source


@pytest.mark.unit
def test_qml_export_directory_fields_accept_direct_paths_without_replacing_pickers():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert "pathInputDialog" not in source
    for picker_call in (
        "openDialog.open()",
        "imageDialog.open()",
        "imageFolderDialog.open()",
        "replaceImageDialog.open()",
        "replaceImageFolderDialog.open()",
        "outputFolderDialog.open()",
        "multiOutputFolderDialog.open()",
    ):
        assert picker_call in source

    batch_output = re.search(
        r"ExportField \{.*?text: batchExport\.outputDirectory.*?"
        r"onCommitted: value => batchExport\.outputDirectory = value.*?\}",
        source,
        re.S,
    )
    assert batch_output is not None
    assert "readOnly: true" not in batch_output.group(0)

    multi_output = re.search(
        r"ExportField \{.*?text: multiTabExport\.outputDirectory.*?"
        r"onCommitted: value => multiTabExport\.outputDirectory = value.*?\}",
        source,
        re.S,
    )
    assert multi_output is not None
