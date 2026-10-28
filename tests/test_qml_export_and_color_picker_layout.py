from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_qml_export_sections_and_color_picker_debug_entry_exist():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    launcher_source = (REPO_ROOT / "app/qml/qml_main.py").read_text(encoding="utf-8")

    assert 'objectName: "effectColorDialog"' in qml_source
    assert "header: null" in qml_source
    assert 'text: "颜色区域"' in qml_source
    assert 'text: "HSV"' in qml_source
    assert 'text: "RGB"' in qml_source
    # P1-5 拆分：ExportSettingsSection/CompactExportSection 内联 component 迁入 components/
    assert (REPO_ROOT / "app/qml/components/ExportSettingsSection.qml").exists()
    assert (REPO_ROOT / "app/qml/components/CompactExportSection.qml").exists()
    for title in ("导出任务", "文件命名", "输出格式", "组合策略"):
        assert f'title: "{title}"' in qml_source
    assert 'objectName: "batchExportAdvancedDialog"' in qml_source
    assert 'BodyLabel { text: "高级策略"' in qml_source

    assert '"--show-color-picker"' in launcher_source
    assert 'window.findChild(QObject, "effectColorDialog")' in launcher_source


@pytest.mark.unit
def test_batch_export_count_and_start_columns_stay_top_aligned():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    start = qml_source.index('BodyLabel { text: "生成数量"')
    end = qml_source.index('title: "文件命名"', start)
    count_and_start_block = qml_source[start - 240 : end]

    assert count_and_start_block.count("Layout.preferredWidth: 1") == 2
    assert count_and_start_block.count("Layout.minimumWidth: 0") == 2
    assert count_and_start_block.count("Layout.alignment: Qt.AlignTop") == 2


@pytest.mark.unit
def test_batch_export_strategy_choices_use_compact_toggle_bar():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    strategy_start = qml_source.index('title: "组合策略"')
    strategy_end = qml_source.index('id: advancedStrategyEntry', strategy_start)
    strategy_block = qml_source[strategy_start:strategy_end]

    assert "id: compactStrategyBar" in strategy_block
    assert "height: 30" in strategy_block
    assert strategy_block.count('value: "sample"') == 1
    assert strategy_block.count('value: "unique"') == 1
    assert strategy_block.count('value: "traverse"') == 1
    assert "batchExport.avoidDuplicates = !batchExport.avoidDuplicates" in strategy_block
    assert "batchExport.uniqueUseEnabled = !batchExport.uniqueUseEnabled" in strategy_block
    assert "batchExport.traverseMode = !batchExport.traverseMode" in strategy_block


@pytest.mark.unit
def test_related_parameter_groups_use_compact_adaptive_controls():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    random_start = qml_source.index('title: "随机变换"')
    random_end = qml_source.index('title: "图层分身"', random_start)
    random_block = qml_source[random_start:random_end]
    for grid_id in (
        "randomPositionCompactGrid",
        "randomScaleCompactGrid",
        "randomRotationCompactGrid",
    ):
        assert f"id: {grid_id}" in random_block
    assert random_block.count("TrailingToggle {") == 3
    assert "workspace.setSelectedRandomPositionEnabled(checkedValue)" in random_block
    assert "workspace.setSelectedRandomScaleEnabled(checkedValue)" in random_block
    assert "workspace.setSelectedRandomRotationEnabled(checkedValue)" in random_block

    size_start = qml_source.index('visible: dataRelationsDrawer.activeTab === 1')
    size_end = qml_source.index('label: "添加尺寸匹配关系"', size_start)
    size_block = qml_source[size_start:size_end]
    assert size_block.count("OptionTile {") == 3
    assert "id: oneToManyOption" in size_block
    assert "id: autoRotateOption" in size_block
    assert "id: autoMaskOption" in size_block

    multi_start = qml_source.index('Text { text: "多标签批量导出"')
    multi_end = qml_source.index('TinyLabel { text: "标签页任务"', multi_start)
    multi_block = qml_source[multi_start:multi_end]
    assert multi_block.count("OptionTile {") == 2
    assert "selected: multiTabExport.avoidDuplicates" in multi_block
    assert "selected: multiTabExport.traverseMode" in multi_block

    advanced_start = qml_source.index('objectName: "batchExportAdvancedDialog"')
    advanced_end = qml_source.index('objectName: "batchExportDrawer"', advanced_start)
    advanced_block = qml_source[advanced_start:advanced_end]
    performance_start = advanced_block.index("id: performanceStrategyOptions")
    performance_end = advanced_block.index('BodyLabel { text: "内存保护"', performance_start)
    performance_block = advanced_block[performance_start:performance_end]
    assert performance_block.count("OptionTile {") == 3
    assert "selected: batchExport.useHighPerformance" in performance_block
    assert "selected: batchExport.preloadEnabled" in performance_block
    assert "selected: batchExport.externalWorkerEnabled" in performance_block


@pytest.mark.integration
def test_qml_color_picker_renders_without_native_white_header(tmp_path: Path):
    screenshot = tmp_path / "qml-color-picker.png"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    # 前置条件必须由测试自己建立。
    #
    # 原来这条测试直接读机器上持久化的主题设置 —— 本机恰好存着 dark 所以
    # 一直绿，换台机器（默认 light）就必然失败。测试不该依赖"上一次运行
    # 留下的状态"，否则它保护的就不是代码，而是这台机器的历史。
    from PySide6.QtCore import QSettings

    settings = QSettings("批图王", "批图王")
    previous_theme = settings.value("uiAppearance/themeMode")
    settings.setValue("uiAppearance/themeMode", "dark")
    settings.sync()

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "start_qml.py"),
                "--screenshot",
                str(screenshot),
                "--width",
                "1280",
                "--height",
                "760",
                "--show-color-picker",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        # 用完还原，不要把测试的前置条件留在用户配置里
        if previous_theme is None:
            settings.remove("uiAppearance/themeMode")
        else:
            settings.setValue("uiAppearance/themeMode", previous_theme)
        settings.sync()

    assert result.returncode == 0, result.stdout + result.stderr
    assert screenshot.exists() and screenshot.stat().st_size > 20_000
    with Image.open(screenshot) as image:
        assert image.size == (1280, 760)
        red, green, blue = image.convert("RGB").getpixel((image.width // 2, 90))
        assert max(red, green, blue) < 80
