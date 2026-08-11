from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _batch_drawer_block(qml_source: str) -> str:
    start = qml_source.index('objectName: "batchExportDrawer"')
    end = qml_source.index('objectName: "multiTabExportDrawer"', start)
    return qml_source[start:end]


@pytest.mark.unit
def test_batch_export_drawer_uses_fixed_compact_layout():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    drawer_block = _batch_drawer_block(qml_source)

    assert "width: Math.min(480, Math.max(450, window.width * 0.39))" in drawer_block
    assert "Flickable {" not in drawer_block
    assert "ScrollIndicator" not in drawer_block
    assert 'id: batchFormatControl' in drawer_block
    assert drawer_block.count('{ label: "PNG", value: "png" }') == 1
    assert drawer_block.count('{ label: "JPG", value: "jpg" }') == 1
    assert 'value: "bmp"' not in drawer_block
    assert 'value: "webp"' not in drawer_block
    assert 'text: "大小 KB"' in drawer_block
    assert 'id: compactStrategyBar' in drawer_block
    assert 'Layout.preferredHeight: 46' in drawer_block
    export_form = drawer_block[
        drawer_block.index("id: exportForm"):drawer_block.index('title: "导出任务"')
    ]
    assert "spacing: window.height < 800 ? 6 : 16" in export_form


@pytest.mark.unit
def test_batch_export_drawer_keeps_only_primary_parameters():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    drawer_block = _batch_drawer_block(qml_source)

    assert "使用当前日期替换路径" not in drawer_block
    assert 'text: "使用图层文件名"' not in drawer_block
    assert 'text: "预览  " + batchExport.filenamePreview' not in drawer_block
    assert 'onClicked: batchExportAdvancedDialog.open()' in drawer_block
    assert 'label: "保存配置"' in drawer_block
    assert 'label: "打开目录"' in drawer_block
    assert '"开始导出"' in drawer_block


@pytest.mark.unit
def test_unique_use_exposes_layer_parameters_in_main_drawer():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    drawer_block = _batch_drawer_block(qml_source)
    advanced_start = qml_source.index('objectName: "batchExportAdvancedDialog"')
    advanced_end = qml_source.index('objectName: "batchExportDrawer"', advanced_start)
    advanced_block = qml_source[advanced_start:advanced_end]

    assert 'id: uniqueLayerPicker' in drawer_block
    assert 'enabled: batchExport.uniqueUseEnabled' in drawer_block
    assert 'text: !batchExport.uniqueUseEnabled' in drawer_block
    assert 'text: "限制图层"' in drawer_block
    assert 'objectName: "uniqueLayerMenu"' in drawer_block
    assert 'model: uniqueLayerMenu.visible ? batchExport.uniqueLayerOptions : []' in drawer_block
    assert 'onClicked: batchExport.setUniqueLayerSelected(modelData.index, !modelData.selected)' in drawer_block
    assert 'batchExport.uniqueLayerOptions' not in advanced_block


@pytest.mark.unit
def test_batch_export_advanced_settings_remain_available_in_dialog():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    start = qml_source.index('objectName: "batchExportAdvancedDialog"')
    end = qml_source.index('objectName: "batchExportDrawer"', start)
    advanced_block = qml_source[start:end]

    for binding in (
        "batchExport.qualityProfile",
        "batchExport.useHighPerformance",
        "batchExport.preloadEnabled",
        "batchExport.externalWorkerEnabled",
        "batchExport.memoryGuardMode",
        "batchExport.memoryLimitMB",
        "batchExport.memoryReserveMB",
        "batchExport.maxConsecutiveFailures",
        "batchExport.failureRateLimit",
        "batchExport.stallTimeoutSeconds",
    ):
        assert binding in advanced_block


@pytest.mark.integration
@pytest.mark.parametrize(("width", "height"), [(1180, 720), (1600, 960)])
def test_compact_batch_export_drawer_renders_at_target_sizes(tmp_path: Path, width: int, height: int):
    screenshot = tmp_path / f"batch-export-{width}x{height}.png"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "start_qml.py"),
            "--screenshot",
            str(screenshot),
            "--width",
            str(width),
            "--height",
            str(height),
            "--show-batch-export",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert screenshot.exists() and screenshot.stat().st_size > 20_000
    with Image.open(screenshot) as image:
        assert image.size == (width, height)
        drawer_crop = image.crop((width - 480, 0, width, height)).convert("RGB")
        assert drawer_crop.getbbox() is not None
        assert len(drawer_crop.getcolors(maxcolors=1_000_000) or []) > 20


@pytest.mark.integration
def test_unique_use_layer_can_be_selected_with_mouse():
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests/helpers/qml_batch_unique_interaction_probe.py")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "single-use image layer selected through the compact drawer" in result.stdout
