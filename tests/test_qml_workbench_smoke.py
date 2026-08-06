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
    launcher = repo_root / "start_qml.py"
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
    assert 'Text { text: "批量导出"' in qml_source
    assert 'title: "图像源"' in qml_source
    assert 'title: "文字内容"' in qml_source
    assert 'tooltip: "添加素材文件夹"' in qml_source
    assert '"复制图层 · Ctrl+D"' not in qml_source
    assert 'workspace.moveSelectedLayer("forward")' in qml_source
    assert 'sequence: "Ctrl+D"' in qml_source
    assert 'id: effectColorDialog' in qml_source
    assert 'objectName: "opacitySlider"' in qml_source
    assert 'onMoved: workspace.setSelectedOpacity(Math.round(value))' in qml_source
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
    assert 'id: textLayerDialog' in qml_source
    assert 'id: shapedLayerDialog' in qml_source
    assert 'workspace.addConfiguredTextLayer(' in qml_source
    assert 'workspace.addConfiguredShapedLayer(' in qml_source
    assert 'visible: inspectorTab === 0 && workspace.selectedHasImageSource' in qml_source
    assert 'visible: inspectorTab === 0 && workspace.selectedIsShapedLayer' in qml_source
    assert 'workspace.setSelectedShapeType(modelData.value)' in qml_source
    assert 'workspace.setSelectedTrapezoidSlopeSide(modelData.value)' in qml_source
    assert 'workspace.setSelectedPolygonCornerRadius(parsed)' in qml_source
    assert 'title: "高级设置"' in qml_source
    assert 'model: window.imageFitOptions' in qml_source
    assert 'workspace.setSelectedFitMode(currentValue)' in qml_source
    assert 'workspace.setSelectedCropDirection(modelData.value)' in qml_source
    assert 'workspace.startCropEdit()' in qml_source
    assert 'workspace.confirmCropEdit()' in qml_source
    assert 'workspace.cancelCropEdit()' in qml_source
    assert 'workspace.updateCropRect(left, top, right, bottom)' in qml_source
    assert 'model: workspace.selectedVectorPathEnabled && !workspace.cropEditing' in qml_source
    assert 'workspace.convertSelectedToVectorPath()' in qml_source
    assert 'workspace.moveSelectedVectorNode(' in qml_source
    assert 'workspace.moveSelectedVectorHandle(' in qml_source
    assert 'workspace.cycleSelectedVectorNodeType()' in qml_source
    assert 'workspace.selectLayerWithModifiers(' in qml_source
    assert 'workspace.selectLayersInRect(' in qml_source
    assert 'workspace.transformSelectedLayers(' in qml_source
    assert 'workspace.moveSelectedLayersTo(targetItem.layerIndex)' in qml_source
    assert 'workspace.groupSelectedLayers()' in qml_source
    assert 'workspace.ungroupSelectedGroups()' in qml_source
    assert 'workspace.alignSelectedLayers("left")' in qml_source
    assert 'workspace.distributeSelectedLayers("horizontal")' in qml_source
    assert 'workspace.setSelectedFlipHorizontal(!workspace.selectedFlipHorizontal)' in qml_source
    assert 'workspace.setSelectedFlipVertical(!workspace.selectedFlipVertical)' in qml_source
    assert 'workspace.setSelectedAspectRatioLocked(!workspace.selectedAspectRatioLocked)' in qml_source
    assert 'visible: inspectorTab === 1 && workspace.selectedSupportsRandomTransform' in qml_source
    assert 'workspace.setSelectedRandomPositionEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedRandomScaleMinPercent(parsed)' in qml_source
    assert 'workspace.setSelectedRandomRotationRange(parsed)' in qml_source
    assert 'workspace.regenerateSelectedRandomTransform()' in qml_source
    assert 'FontSelectBox {' in qml_source
    assert 'options: workspace.selectedTextFontOptions' in qml_source
    assert 'workspace.setSelectedTextFontFamily(value)' in qml_source
    assert 'workspace.setSelectedTextBold(!workspace.selectedTextBold)' in qml_source
    assert 'workspace.setSelectedTextItalic(!workspace.selectedTextItalic)' in qml_source
    assert 'workspace.setSelectedTextAlignment(parent.modelData.value)' in qml_source
    assert 'workspace.setSelectedTextVerticalLayout(checkedValue)' in qml_source
    assert 'workspace.setSelectedTextLineSpacingPercent(parsed)' in qml_source
    assert 'workspace.setSelectedTextLetterSpacing(parsed)' in qml_source
    assert 'workspace.setSelectedTextAutoFitTextBox(checkedValue)' in qml_source
    assert 'workspace.setSelectedTextBoxPadding(parsed)' in qml_source
    assert 'objectName: "textTypographySection"' in qml_source
    assert 'function revealTextTypography()' in qml_source
    assert 'title: "文字填充"' in qml_source
    assert 'workspace.setSelectedTextFillMode(parent.modelData.value)' in qml_source
    assert 'workspace.setSelectedTextColor(value)' in qml_source
    assert 'workspace.setSelectedTextGradientType(currentValue)' in qml_source
    assert 'workspace.setSelectedTextGradientDirection(currentValue)' in qml_source
    assert 'workspace.setSelectedTextGradientCenter(xValue, yValue)' in qml_source
    assert 'workspace.setSelectedTextGradientColor(colorIndex, hexValue)' in qml_source
    assert 'title: "文字背景"' in qml_source
    assert 'workspace.setSelectedTextBackgroundEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedTextBackgroundColor(value)' in qml_source
    assert 'workspace.setSelectedTextBackgroundOpacity(parsed)' in qml_source
    assert 'workspace.setSelectedTextBackgroundPadding(parsed)' in qml_source
    assert 'title: "文字阴影"' in qml_source
    assert 'workspace.setSelectedTextShadowEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedTextShadowOffset(xValue, yValue)' in qml_source
    assert 'workspace.setSelectedTextShadowBlur(parsed)' in qml_source
    assert 'workspace.setSelectedTextShadowColor(value)' in qml_source
    assert 'workspace.setSelectedTextShadowOpacity(parsed)' in qml_source
    assert 'title: "文字发光"' in qml_source
    assert 'workspace.setSelectedTextGlowEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedTextGlowStrength(parsed)' in qml_source
    assert 'workspace.setSelectedTextGlowRadius(parsed)' in qml_source
    assert 'workspace.copySelectedLayerStyle()' in qml_source
    assert 'workspace.pasteSelectedLayerStyle()' in qml_source
    assert 'workspace.setSelectedTextColorRange(rangeStart, rangeEnd, hexValue)' in qml_source
    assert 'workspace.clearSelectedTextColorRange(' in qml_source
    assert 'property bool randomTransformEnabled' not in qml_source
    assert 'enabled: index === 0' not in qml_source
    assert 'id: fileMenu' in qml_source
    assert 'legacyTools.open' not in qml_source
    assert 'legacyTools.openAdvancedLayerProperties()' not in qml_source
    assert 'function revealAdvancedProperties()' in qml_source
    assert 'objectName: "clonePropertiesSection"' in qml_source
    assert 'objectName: "advancedStrokeSection"' in qml_source
    assert 'function openDataRelations(tab)' in qml_source
    assert 'function openCanvasPresetDrawer()' in qml_source
    assert 'function openProjectPresetDrawer()' in qml_source
    assert 'function openNewCanvasDialog()' in qml_source
    assert 'legacyTools.openAddTextLayer()' not in qml_source
    assert 'legacyTools.openAddShapedLayer()' not in qml_source
    assert 'legacyTools.renameSelectedLayer()' not in qml_source
    assert 'function revealLayerNameEditor()' in qml_source
    assert 'workspace.addEmptyImageLayer()' in qml_source
    assert 'workspace.setSelectedImageSourceMode(false)' in qml_source
    assert 'workspace.resetView()' in qml_source
    assert 'workspaceSessions.requestApplicationClose()' in qml_source
    assert 'workspaceSessions.duplicateDocument(contextDocumentIndex)' in qml_source
    assert 'workspaceSessions.closeOtherDocuments(contextDocumentIndex)' in qml_source
    assert 'property real zoomValue' not in qml_source
    assert 'workspace.zoomFactor' in qml_source
    assert '{ label: "明度", value: "luminosity" }' in qml_source


@pytest.mark.unit
def test_main_defaults_to_qml_and_packaging_includes_qml_assets():
    repo_root = Path(__file__).resolve().parents[1]
    main_source = (repo_root / "main.py").read_text(encoding="utf-8")
    qml_launcher_source = (repo_root / "start_qml.py").read_text(encoding="utf-8")
    build_source = (repo_root / "build.py").read_text(encoding="utf-8")
    spec_source = (repo_root / "批图王.spec").read_text(encoding="utf-8")

    assert 'if "--classic" in sys.argv:' in main_source
    assert "from app.qml.qml_main import main as qml_main" in main_source
    assert "sys.exit(qml_main())" in main_source
    assert "from app.qml.qml_main import main" in qml_launcher_source
    assert "raise SystemExit(main())" in qml_launcher_source
    for source in (build_source, spec_source):
        assert "app/qml/Main.qml" in source
        assert "app/qml/components" in source
        assert "app/qml/assets" in source
        assert "PySide6.QtQml" in source
        assert "PySide6.QtQuick" in source


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
