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
    assert 'text: batchExport.effectiveCount + " 张 · " + batchExport.fileFormat.toUpperCase()' in qml_source
    assert 'title: "文件命名"' in qml_source
    assert '{ label: "PNG", value: "png" }' in qml_source
    assert '{ label: "JPG", value: "jpg" }' in qml_source
    assert '{ label: "单次用图", value: "unique" }' in qml_source
    assert 'label: "保存配置"' in qml_source
    assert 'title: "图像源"' in qml_source
    assert 'title: "文字内容"' in qml_source
    assert 'tooltip: "添加素材文件夹"' not in qml_source
    assert '"复制图层 · Ctrl+D"' not in qml_source
    assert 'workspace.moveSelectedLayer("forward")' in qml_source
    assert 'sequence: "Ctrl+J"' in qml_source
    assert 'id: effectColorDialog' in qml_source
    assert 'objectName: "opacitySlider"' in qml_source
    assert 'workspace.beginSelectedOpacityEdit()' in qml_source
    assert 'onMoved: workspace.updateSelectedOpacityEdit(Math.round(value))' in qml_source
    assert 'workspace.endSelectedOpacityEdit()' in qml_source
    assert 'workspace.setSelectedBlendMode(currentValue)' in qml_source
    assert 'workspace.setSelectedStrokeEnabled(true)' in qml_source
    assert 'workspace.setSelectedStrokeColor(modelData)' in qml_source
    assert 'workspace.setSelectedCornerRadius(parent.modelData)' in qml_source
    assert 'effectColorDialog.openFor("stroke", workspace.selectedStrokeColor)' in qml_source
    assert 'workspace.setSelectedOverlayMode(value)' in qml_source
    assert 'workspace.setSelectedColorOverlayOpacity(parsed)' in qml_source
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
    # 对齐走统一分发：单选→画板、多选→首选图层（旧版语义）。
    # 2026-10-28 之前右键菜单直接调 alignSelectedLayers，单选时它返回 False，
    # 导致单项选中时右键里的对齐项全是灰的。
    assert 'window.alignCurrentSelection("left")' in qml_source
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
    assert 'options: workspace.selectedTextFontTreeOptions' in qml_source
    assert 'workspace.setSelectedTextFontFace(value, face)' in qml_source
    assert 'workspace.setSelectedTextBold(!workspace.selectedTextBold)' in qml_source
    assert 'workspace.setSelectedTextItalic(!workspace.selectedTextItalic)' in qml_source
    assert 'workspace.setSelectedTextAlignment(parent.modelData.value)' in qml_source
    assert 'workspace.setSelectedTextVerticalLayout(value === "vertical")' in qml_source
    assert 'workspace.setSelectedTextLineSpacingPercent(parsed)' in qml_source
    assert 'workspace.setSelectedTextLetterSpacing(parsed)' in qml_source
    assert 'workspace.setSelectedTextAutoFitTextBox(value === "auto")' in qml_source
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
    assert 'workspace.setSelectedTextBackgroundEnabled(value === "solid")' in qml_source
    assert 'workspace.setSelectedTextBackgroundColor(value)' in qml_source
    assert 'workspace.setSelectedTextBackgroundOpacity(parsed)' in qml_source
    assert 'workspace.setSelectedTextBackgroundPadding(parsed)' in qml_source
    assert 'title: "文字阴影"' in qml_source
    assert 'workspace.setSelectedTextShadowEnabled(value === "on")' in qml_source
    assert 'workspace.setSelectedTextShadowOffset(xValue, yValue)' in qml_source
    assert 'workspace.setSelectedTextShadowBlur(parsed)' in qml_source
    assert 'workspace.setSelectedTextShadowColor(value)' in qml_source
    assert 'workspace.setSelectedTextShadowOpacity(parsed)' in qml_source
    assert 'title: "文字发光"' in qml_source
    assert 'workspace.setSelectedTextGlowEnabled(value === "on")' in qml_source
    assert 'workspace.setSelectedTextGlowStrength(parsed)' in qml_source
    assert 'workspace.setSelectedTextGlowRadius(parsed)' in qml_source
    assert 'workspace.copySelectedLayerStyle()' in qml_source
    assert 'workspace.pasteSelectedLayerStyle()' in qml_source
    assert 'workspace.setSelectedTextColorRangeQt(rangeStart, rangeEnd, hexValue)' in qml_source
    assert 'workspace.clearSelectedTextColorRangeQt(' in qml_source
    assert 'workspace.setSelectedTextFontSizeRangeQt(' in qml_source
    assert 'workspace.clearSelectedTextFontSizeRangeQt(' in qml_source
    assert 'text: workspace.selectedTextFontWarning' in qml_source
    assert 'property bool randomTransformEnabled' not in qml_source
    assert 'enabled: index === 0' not in qml_source
    assert 'id: fileMenu' in qml_source
    assert 'legacyTools.open' not in qml_source
    assert 'legacyTools.openAdvancedLayerProperties()' not in qml_source
    assert 'function revealAdvancedProperties()' in qml_source
    assert 'objectName: "clonePropertiesSection"' in qml_source
    assert 'objectName: "advancedStrokeSection"' in qml_source
    assert 'objectName: "overlaySection"' in qml_source
    assert 'objectName: "cornerSection"' in qml_source
    assert 'workspace.setSelectedCloneLayoutMode(value)' in qml_source
    assert 'workspace.setSelectedTrimTransparentBoundsEnabled(checkedValue)' in qml_source
    assert 'workspace.setSelectedCornerMode(value)' in qml_source
    assert 'title: "渐变叠加"' not in qml_source
    assert 'text: workspace.selectedTextBindingEnabled ? workspace.selectedTextCandidateCount + " 条文案" : "1 条文案"' not in qml_source
    assert 'text: workspace.selectedFlipHorizontal || workspace.selectedFlipVertical ? "已翻转" : "未翻转"' not in qml_source
    assert 'text: workspace.selectedTextBackgroundEnabled ? "背景已开启" : "无背景"' not in qml_source
    assert 'function openDataRelations(tab)' in qml_source
    assert 'function openCanvasPresetDrawer()' in qml_source
    assert 'function openProjectPresetDrawer()' in qml_source
    assert 'function openNewCanvasDialog()' in qml_source
    assert 'legacyTools.openAddTextLayer()' not in qml_source
    assert 'legacyTools.openAddShapedLayer()' not in qml_source
    assert 'legacyTools.renameSelectedLayer()' not in qml_source
    assert 'function revealLayerNameEditor()' in qml_source
    assert 'workspace.addEmptyImageLayer()' in qml_source
    assert 'workspace.setSelectedImageSourceMode(' not in qml_source
    assert 'workspace.resetView()' in qml_source
    assert 'workspaceSessions.requestApplicationClose()' in qml_source
    assert 'workspaceSessions.duplicateDocument(contextDocumentIndex)' in qml_source
    assert 'workspaceSessions.closeOtherDocuments(contextDocumentIndex)' in qml_source
    assert 'property real zoomValue' not in qml_source
    assert 'workspace.zoomFactor' in qml_source
    assert '{ label: "明度", value: "luminosity" }' in qml_source


@pytest.mark.unit
def test_main_entrypoint_is_qml_only():
    """入口只保留 QML 一条界面路径，经典版已下线。

    2026-10-28 决定下线经典 Widgets 界面。这条测试守两件事：

    1. **界面只有一条路**：main.py 里不能再出现经典版的窗口创建，
       也不能再有"根据参数进不同界面"的分支（双轨是功能漂移的源头）。
    2. **基础设施不能跟着丢**：日志、崩溃会话、依赖检查必须在 main()
       里 —— 它们与用哪套 UI 无关。上一轮把入口直接指向 qml_main 时，
       这整块被绕过，应用失去崩溃诊断能力且无人察觉。
    """
    repo_root = Path(__file__).resolve().parents[1]
    main_source = (repo_root / "main.py").read_text(encoding="utf-8")
    qml_launcher_source = (repo_root / "start_qml.py").read_text(encoding="utf-8")
    windows_launcher_source = (repo_root / "启动QML版.cmd").read_text(encoding="utf-8")
    build_source = (repo_root / "build.py").read_text(encoding="utf-8")
    spec_source = (repo_root / "批图王.spec").read_text(encoding="utf-8")

    # 界面唯一：不再创建经典主窗口
    assert "from app.main_window import MainWindow" not in main_source
    assert "MainWindow()" not in main_source

    # 只有一条启动路径，且走 main()（基础设施都在里面）
    assert "sys.exit(main())" in main_source
    assert "sys.exit(qml_main())" not in main_source, (
        "不能再直接调 qml_main —— 会绕过日志/崩溃会话/依赖检查"
    )

    # main() 内部把窗口创建交给 QML，并复用已建好的 QApplication
    assert "from app.qml.qml_main import main as qml_main" in main_source
    assert "qml_main(app=app" in main_source

    # --classic 只保留参数识别与提示，不再是界面开关
    assert '"--classic" in sys.argv' in main_source
    assert "经典界面已下线" in main_source

    # 基础设施必须在 main() 里，不能被"下线界面"顺手删掉
    for required in (
        "setup_logging()",
        "begin_crash_session(",
        "check_system_dependencies_fast()",
        "Image.MAX_IMAGE_PIXELS = None",
        "finish_crash_session(",
        "setup_fixed_theme(app)",
    ):
        assert required in main_source, (
            f"main.py 缺少启动基础设施 {required!r} —— 它和用哪套界面无关，不能随界面一起删"
        )

    # QML 专用启动器仍然直接进 QML（不受默认值影响）
    assert "from app.qml.qml_main import main" in qml_launcher_source
    assert "raise SystemExit(main())" in qml_launcher_source

    qml_main_source = (repo_root / "app" / "qml" / "qml_main.py").read_text(encoding="utf-8")
    assert "auto_render=False" in qml_main_source
    assert "defer_font_catalog_preload=True" in qml_main_source
    assert "workspace.renderInitialPreview()" in qml_main_source
    assert "workspace.enableDeferredFontCatalogPreload" in qml_main_source
    assert 'cd /d "%~dp0"' in windows_launcher_source
    assert '"%~dp0start_qml.py" %*' in windows_launcher_source
    assert "if not errorlevel 1" in windows_launcher_source
    # QML 资源与 Qt 模块由 spec 统一声明（build.py 只按模式调用 spec）
    for source in (spec_source,):
        assert "app/qml/Main.qml" in source
        assert "app/qml/components" in source
        assert "app/qml/assets" in source
        assert "PySide6.QtQml" in source
        assert "PySide6.QtQuick" in source
    assert "批图王.spec" in build_source, "build.py 必须调用 spec，避免资源清单双份维护"


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
