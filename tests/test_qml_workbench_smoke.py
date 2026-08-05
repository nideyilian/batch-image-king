from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


@pytest.mark.integration
def test_qml_workbench_can_render_offscreen(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    launcher = repo_root / "app" / "qml" / "qml_main.py"
    screenshot = tmp_path / "qml-workbench.png"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    result = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--screenshot",
            str(screenshot),
            "--width",
            "1280",
            "--height",
            "760",
            "--show-batch-export",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert screenshot.exists() and screenshot.stat().st_size > 20_000
    with Image.open(screenshot) as image:
        assert image.size == (1280, 760)
        assert image.getbbox() is not None

    qml_source = (repo_root / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")
    assert 'objectName: "batchExportDrawer"' in qml_source
    assert 'text: batchExport.running ? "查看进度" : "批量导出"' in qml_source
    assert 'title: "内容源"' in qml_source
    assert 'title: "文字内容"' in qml_source
    assert 'tooltip: "添加素材文件夹"' in qml_source
    assert 'tooltip: "复制图层 · Ctrl+D"' in qml_source
    assert 'workspace.moveSelectedLayer("forward")' in qml_source
    assert 'sequence: "Ctrl+D"' in qml_source
    assert 'id: effectColorDialog' in qml_source
    assert 'workspace.setSelectedBlendMode(currentValue)' in qml_source
    assert 'workspace.setSelectedStrokeEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedStrokeColor(modelData)' in qml_source
    assert 'workspace.setSelectedCornerRadius(modelData)' in qml_source
    assert 'window.hexToColor(workspace.selectedStrokeColor)' in qml_source
    assert 'workspace.setSelectedColorOverlayEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedColorOverlayOpacity(parsed)' in qml_source
    assert 'workspace.setSelectedGradientOverlayEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedGradientOverlayColor(colorIndex, hexValue)' in qml_source
    assert 'workspace.setSelectedGradientOverlayAngle(modelData)' in qml_source
    assert 'model: workspaceSessions' in qml_source
    assert 'workspaceSessions.activateDocument(documentTab.index)' in qml_source
    assert 'workspaceSessions.requestClose(documentTab.index)' in qml_source
    assert 'id: newCanvasDialog' in qml_source
    assert 'workspaceSessions.newDocument(widthValue, heightValue)' in qml_source
    assert 'id: closeConfirmDialog' in qml_source
    assert 'workspaceSessions.saveAndClose(workspaceSessions.pendingCloseIndex' in qml_source
    assert 'id: shapedImageDialog' in qml_source
    assert 'id: addShapeMenu' in qml_source
    assert 'workspace.addShapedLayer(selectedFile.toString(), pendingShapeType)' in qml_source
    assert 'visible: workspace.selectedHasImageSource' in qml_source
    assert 'visible: workspace.selectedIsShapedLayer' in qml_source
    assert 'workspace.setSelectedShapeType(modelData.value)' in qml_source
    assert 'workspace.setSelectedTrapezoidSlopeSide(modelData.value)' in qml_source
    assert 'workspace.setSelectedPolygonCornerRadius(parsed)' in qml_source
    assert 'title: "图片布局"' in qml_source
    assert 'model: window.imageFitOptions' in qml_source
    assert 'workspace.setSelectedFitMode(currentValue)' in qml_source
    assert 'workspace.setSelectedCropDirection(modelData.value)' in qml_source
    assert 'workspace.setSelectedFlipHorizontal(!workspace.selectedFlipHorizontal)' in qml_source
    assert 'workspace.setSelectedFlipVertical(!workspace.selectedFlipVertical)' in qml_source
    assert 'workspace.setSelectedAspectRatioLocked(!workspace.selectedAspectRatioLocked)' in qml_source
    assert 'visible: workspace.selectedSupportsRandomTransform' in qml_source
    assert 'workspace.setSelectedRandomPositionEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedRandomScaleMinPercent(parsed)' in qml_source
    assert 'workspace.setSelectedRandomRotationRange(parsed)' in qml_source
    assert 'workspace.regenerateSelectedRandomTransform()' in qml_source
    assert 'property bool randomTransformEnabled' not in qml_source
    assert 'enabled: index === 0' not in qml_source


@pytest.mark.integration
def test_qml_canvas_drag_updates_real_layer_geometry():
    repo_root = Path(__file__).resolve().parents[1]
    probe = repo_root / "tests" / "helpers" / "qml_canvas_interaction_probe.py"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    result = subprocess.run(
        [sys.executable, str(probe)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dragged layer to" in result.stdout
    assert "locked image ratio" in result.stdout
