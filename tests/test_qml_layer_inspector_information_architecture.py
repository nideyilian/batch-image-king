from __future__ import annotations

from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_qml_inspector_uses_basic_and_more_parameter_tabs():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert 'model: ["基本参数", "更多参数"]' in source
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
        r"id: textFillSection.*?visible: inspectorTab === 0 && workspace\.selectedIsTextLayer",
        source,
        re.S,
    )


@pytest.mark.unit
def test_qml_color_picker_has_photoshop_style_controls():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    for marker in (
        "id: saturationValueField",
        "id: hueStrip",
        "function setHsv",
        "function setRgb",
        'BodyLabel { text: "新的"',
        'BodyLabel { text: "当前"',
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
