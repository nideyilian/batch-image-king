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
def test_qml_path_inputs_cover_all_file_and_folder_entry_points():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    for marker in (
        "id: pathInputDialog",
        "function openFor(nextMode, currentPath)",
        "function setPathFromBrowse(pathValue)",
        "function applyPath()",
        "可直接粘贴本地路径、UNC 地址或 file:/// 链接",
    ):
        assert marker in source

    expected_modes = (
        "openProject",
        "saveProject",
        "closeSave",
        "exportImage",
        "addImage",
        "shapeFile",
        "shapeFolder",
        "imageFolder",
        "replaceImage",
        "replaceImageFolder",
        "outputFolder",
        "multiOutputFolder",
    )
    for mode in expected_modes:
        assert f'pathInputDialog.openFor("{mode}"' in source

    # 原生选择器只应由“浏览…”按钮调用，所有业务入口统一先进入可编辑地址弹窗。
    browse_block = re.search(r"function browse\(\).*?\n        }", source, re.S)
    assert browse_block is not None
    source_without_browse = source.replace(browse_block.group(0), "")
    for dialog_id in (
        "openDialog",
        "saveDialog",
        "closeSaveDialog",
        "exportDialog",
        "imageDialog",
        "shapedLayerSourceFileDialog",
        "shapedLayerSourceFolderDialog",
        "imageFolderDialog",
        "replaceImageDialog",
        "replaceImageFolderDialog",
        "outputFolderDialog",
        "multiOutputFolderDialog",
    ):
        assert f"{dialog_id}.open()" not in source_without_browse
