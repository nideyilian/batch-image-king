#!/usr/bin/env python3
"""Standalone launcher for the next-generation Batch Image King QML UI."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动批图王 QML 工作台")
    parser.add_argument("--screenshot", type=Path, help="启动后将窗口保存为 PNG 并退出")
    parser.add_argument("--width", type=int, default=1600, help="窗口宽度")
    parser.add_argument("--height", type=int, default=960, help="窗口高度")
    parser.add_argument("--open", dest="open_path", type=Path, help="启动后打开指定 .cmp 项目")
    parser.add_argument("--blank", action="store_true", help="启动为空白文档，不载入内置示例")
    parser.add_argument("--demo", action="store_true", help="启动内置演示文档")
    parser.add_argument("--show-batch-export", action="store_true", help="启动后打开批量导出面板")
    parser.add_argument("--show-batch-advanced", action="store_true", help="展示批量导出高级策略")
    parser.add_argument("--show-multi-tab-export", action="store_true", help="展示多标签批量导出")
    parser.add_argument("--show-effects", action="store_true", help="启动后打开图层效果面板")
    parser.add_argument("--show-new-canvas", action="store_true", help="启动后打开新建画布弹窗")
    parser.add_argument("--show-close-confirm", action="store_true", help="启动后打开未保存文档关闭确认")
    parser.add_argument("--demo-effects", action="store_true", help="为选中图片图层应用演示效果")
    parser.add_argument("--select-layer", type=int, help="启动后选中指定图层索引")
    parser.add_argument("--duplicate-selected", action="store_true", help="启动后复制当前选中图层")
    parser.add_argument("--demo-tabs", action="store_true", help="启动后创建多个文档标签用于验收")
    parser.add_argument("--demo-shaped", action="store_true", help="启动后创建真实异形图层用于验收")
    parser.add_argument("--show-advanced-properties", action="store_true", help="展示内嵌高级图层属性")
    parser.add_argument("--show-random-transform", action="store_true", help="展示图片图层随机变换配置")
    parser.add_argument("--show-text-typography", action="store_true", help="展示文字字体与核心排版配置")
    parser.add_argument("--show-text-appearance", action="store_true", help="展示文字填充、背景与局部颜色")
    parser.add_argument("--show-text-effects", action="store_true", help="展示文字阴影、发光与样式工具")
    parser.add_argument("--show-crop-tools", action="store_true", help="展示图片自由裁剪工具")
    parser.add_argument("--show-vector-path", action="store_true", help="展示矢量路径节点编辑")
    parser.add_argument("--show-multi-select", action="store_true", help="展示多图层选择与编排")
    parser.add_argument("--show-grouped-layers", action="store_true", help="展示图层组层级与属性")
    parser.add_argument("--show-guides", action="store_true", help="展示标尺与参考线")
    parser.add_argument("--show-canvas-presets", action="store_true", help="展示画布预设管理")
    parser.add_argument("--show-project-presets", action="store_true", help="展示项目预设管理")
    parser.add_argument("--show-data-relations", action="store_true", help="展示绑定组管理")
    parser.add_argument("--show-size-match", action="store_true", help="展示尺寸匹配管理")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    debug_enabled = os.environ.get("BTPW_QML_DEBUG") == "1"
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    def debug(message: str) -> None:
        if debug_enabled:
            output = f"[qml] {message}"
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            output = output.encode(encoding, errors="backslashreplace").decode(encoding)
            print(output, flush=True)

    if args.screenshot:
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        os.environ.setdefault("QT_QPA_FONTDIR", str(windows_dir / "Fonts"))

    qml_dir = Path(__file__).resolve().parent
    repo_root = qml_dir.parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    debug("importing Qt modules")
    from PySide6.QtCore import QMetaObject, QObject, QThreadPool, QTimer, QUrl
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtWidgets import QApplication
    from app.qml.legacy_feature_bridge import LegacyFeatureBridge
    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
    from app.qml.viewmodels.binding_manager_view_model import BindingManagerViewModel
    from app.qml.viewmodels.canvas_preset_view_model import CanvasPresetViewModel
    from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
    from app.qml.viewmodels.multi_tab_export_view_model import MultiTabExportViewModel
    from app.qml.viewmodels.size_match_view_model import SizeMatchViewModel
    from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    debug("creating QApplication")
    app = QApplication(sys.argv)
    app.setApplicationName("批图王 QML")
    app.setOrganizationName("BatchImageKing")

    def cleanup_runtime() -> None:
        QThreadPool.globalInstance().waitForDone(5000)
        try:
            from app.utils.intelligent_thread_pool_manager import shutdown_thread_pools

            shutdown_thread_pools(wait=True)
        except Exception as error:
            debug(f"thread pool cleanup failed: {error}")
        try:
            from app.utils.advanced_task_queue import shutdown_task_queue

            shutdown_task_queue()
        except Exception as error:
            debug(f"task queue cleanup failed: {error}")

    app.aboutToQuit.connect(cleanup_runtime)
    icon_path = repo_root / "app" / "resources" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    debug("creating QML engine")
    engine = QQmlApplicationEngine()
    if debug_enabled:
        engine.warnings.connect(lambda warnings: [debug(str(warning)) for warning in warnings])
    preview_provider = PreviewImageProvider()
    auto_render = os.environ.get("BTPW_QML_DISABLE_AUTO_RENDER") != "1"
    workspace = WorkspaceViewModel(
        preview_provider=preview_provider,
        auto_render=auto_render,
        parent=engine,
    )
    batch_export = BatchExportViewModel(workspace=workspace, parent=engine)
    canvas_presets = CanvasPresetViewModel(workspace=workspace, parent=engine)
    binding_manager = BindingManagerViewModel(workspace=workspace, parent=engine)
    size_match = SizeMatchViewModel(workspace=workspace, parent=engine)
    engine.addImageProvider("documentPreview", preview_provider)

    demo_requested = bool(
        args.demo
        or args.demo_effects
        or args.demo_tabs
        or args.demo_shaped
        or args.show_advanced_properties
        or args.show_random_transform
        or args.show_text_typography
        or args.show_text_appearance
        or args.show_text_effects
        or args.show_crop_tools
        or args.show_vector_path
        or args.show_multi_select
        or args.show_grouped_layers
    )
    if args.open_path:
        workspace.openDocument(str(args.open_path.expanduser().resolve()))
    elif demo_requested and not args.blank:
        workspace.createDemoDocument(str(qml_dir / "assets" / "watch-product.jpg"))
    else:
        workspace.newDocument(1080, 1350)

    if args.select_layer is not None:
        workspace.selectLayer(args.select_layer)
    elif args.show_random_transform:
        workspace.selectLayer(0)
    elif args.show_text_typography:
        workspace.selectLayer(1)
    elif args.show_text_appearance:
        workspace.selectLayer(1)
    elif args.show_text_effects:
        workspace.selectLayer(1)
    elif args.show_crop_tools or args.show_vector_path or args.show_multi_select or args.show_grouped_layers:
        workspace.selectLayer(0)
    elif args.demo_effects:
        workspace.selectLayer(0)
    if args.demo_effects:
        workspace.setSelectedStrokeEnabled(True)
        workspace.setSelectedStrokeWidth(8)
        workspace.setSelectedStrokeColor("#46D7AD")
        workspace.setSelectedCornerRadius(48)
        workspace.setSelectedGradientOverlayEnabled(True)
        workspace.setSelectedGradientOverlayColor(0, "#173B32")
        workspace.setSelectedGradientOverlayColor(1, "#46D7AD")
        workspace.setSelectedGradientOverlayOpacity(38)
        workspace.setSelectedGradientOverlayAngle(45.0)
    if args.duplicate_selected:
        workspace.duplicateSelectedLayer()
    if args.demo_shaped:
        workspace.addShapedLayer(str(qml_dir / "assets" / "watch-product.jpg"), "hexagon")
        workspace.setSelectedPolygonRotation(18.0)
        workspace.setSelectedPolygonCornerRadius(24)
    if args.show_random_transform:
        layer = workspace.document.layers[workspace.selectedLayerIndex]
        layer.aspect_ratio_locked = True
        layer.random_position_enabled = True
        layer.random_position_range = 24
        layer.random_scale_enabled = True
        layer.random_scale_min = 0.85
        layer.random_scale_max = 1.15
        layer.random_rotation_enabled = True
        layer.random_rotation_range = 8.0
        layer.generate_random_transform_params()
        workspace.selectionChanged.emit()
    if args.show_text_typography:
        workspace.setSelectedTextFontFamily("Microsoft YaHei")
        workspace.setSelectedTextFontSize(72)
        workspace.setSelectedTextBold(True)
        workspace.setSelectedTextAlignment("center")
        workspace.setSelectedTextLineSpacingPercent(130)
        workspace.setSelectedTextLetterSpacing(2)
        workspace.setSelectedTextBoxPadding(18)
    if args.show_text_appearance:
        workspace.setSelectedTextBindingEnabled(False)
        workspace.setSelectedTextFillMode("gradient")
        workspace.setSelectedTextGradientType("linear")
        workspace.setSelectedTextGradientDirection("diagonal_lr")
        workspace.setSelectedTextGradientColor(0, "#F7BD63")
        workspace.setSelectedTextGradientColor(1, "#46D7AD")
        workspace.setSelectedTextColorRange(0, 2, "#F1786D")
        workspace.setSelectedTextBackgroundEnabled(True)
        workspace.setSelectedTextBackgroundColor("#101715CC")
        workspace.setSelectedTextBackgroundPadding(14)
        workspace.setSelectedStrokeEnabled(True)
        workspace.setSelectedStrokeWidth(3)
        workspace.setSelectedStrokeColor("#F2F4F3")
    if args.show_text_effects:
        workspace.setSelectedTextBindingEnabled(False)
        workspace.setSelectedTextFillMode("solid")
        workspace.setSelectedTextColor("#F7BD63")
        workspace.setSelectedTextBackgroundEnabled(False)
        workspace.setSelectedStrokeEnabled(True)
        workspace.setSelectedStrokeWidth(2)
        workspace.setSelectedStrokeColor("#F2F4F3")
        workspace.setSelectedTextShadowEnabled(True)
        workspace.setSelectedTextShadowOffset(12, 10)
        workspace.setSelectedTextShadowBlur(9)
        workspace.setSelectedTextShadowColor("#101715B8")
        workspace.setSelectedTextGlowEnabled(True)
        workspace.setSelectedTextGlowStrength(7)
        workspace.setSelectedTextGlowRadius(14)
        workspace.copySelectedLayerStyle()
    if args.show_crop_tools:
        workspace.startCropEdit()
        workspace.updateCropRect(0.12, 0.1, 0.88, 0.9)
    if args.show_vector_path:
        workspace.convertSelectedToVectorPath()
        workspace.selectVectorNode(1)
        workspace.setSelectedVectorNodeType("smooth")
    if args.show_multi_select:
        workspace.document.select_layers([0, 1, 2], primary_index=0)
        workspace.layerModel.reset_from_document()
        workspace.selectionChanged.emit()
    if args.show_grouped_layers:
        workspace.document.select_layers([0, 1], primary_index=0)
        workspace.groupSelectedLayers()
    if args.show_guides:
        workspace.addGuide("vertical", workspace.canvasWidth * 0.25)
        workspace.addGuide("vertical", workspace.canvasWidth * 0.75)
        workspace.addGuide("horizontal", workspace.canvasHeight * 0.33)
        workspace.addGuide("horizontal", workspace.canvasHeight * 0.67)

    workspace_sessions = WorkspaceSessionViewModel(workspace=workspace, parent=engine)
    project_presets = PresetManagerViewModel(
        workspace=workspace,
        sessions=workspace_sessions,
        parent=engine,
    )
    multi_tab_export = MultiTabExportViewModel(
        workspace=workspace,
        sessions=workspace_sessions,
        parent=engine,
    )
    legacy_tools = LegacyFeatureBridge(
        workspace=workspace,
        sessions=workspace_sessions,
        preset_view_model=project_presets,
        parent=engine,
    )
    if args.demo_tabs:
        workspace_sessions.newDocument(1080, 1080)
        workspace_sessions.newDocument(1920, 1080)
        workspace_sessions.activateDocument(0)

    engine.rootContext().setContextProperty("workspace", workspace)
    engine.rootContext().setContextProperty("workspaceSessions", workspace_sessions)
    engine.rootContext().setContextProperty("layerModel", workspace.layerModel)
    engine.rootContext().setContextProperty("batchExport", batch_export)
    engine.rootContext().setContextProperty("canvasPresets", canvas_presets)
    engine.rootContext().setContextProperty("projectPresets", project_presets)
    engine.rootContext().setContextProperty("bindingManager", binding_manager)
    engine.rootContext().setContextProperty("sizeMatch", size_match)
    engine.rootContext().setContextProperty("multiTabExport", multi_tab_export)
    engine.rootContext().setContextProperty("legacyTools", legacy_tools)

    qml_path = qml_dir / "Main.qml"
    debug(f"loading {qml_path}")
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    debug("QML load returned")
    if not engine.rootObjects():
        print(f"QML 工作台加载失败：{qml_path}", file=sys.stderr)
        return 2

    window = engine.rootObjects()[0]
    debug(
        f"root window created: type={type(window).__name__}, "
        f"visible={window.property('visible')}"
    )
    window.setProperty("width", max(1180, args.width))
    window.setProperty("height", max(720, args.height))
    if args.show_effects:
        window.setProperty("inspectorTab", 1)

    if args.show_advanced_properties:
        def reveal_advanced_properties() -> None:
            workspace.setSelectedCloneEnabled(True)
            workspace.setSelectedCloneFillEnabled(True)
            if not QMetaObject.invokeMethod(window, "revealAdvancedProperties"):
                debug("advanced properties section could not be revealed")

        QTimer.singleShot(120, reveal_advanced_properties)

    if args.show_random_transform:
        def reveal_random_transform() -> None:
            scroll_view = window.findChild(QObject, "inspectorScroll")
            flickable = scroll_view.property("contentItem") if scroll_view is not None else None
            debug(f"random transform scroller: view={scroll_view}, content={flickable}")
            if flickable is not None:
                content_height = float(scroll_view.property("contentHeight") or 0)
                viewport_height = float(flickable.property("height") or 0)
                debug(f"random transform scroll metrics: content={content_height}, viewport={viewport_height}")
                flickable.setProperty("contentY", max(0, content_height - viewport_height))

        QTimer.singleShot(900, reveal_random_transform)

    if args.show_text_typography:
        def reveal_text_typography() -> None:
            if not QMetaObject.invokeMethod(window, "revealTextTypography"):
                debug("text typography section could not be revealed")

        QTimer.singleShot(120, reveal_text_typography)

    if args.show_text_appearance:
        def reveal_text_appearance() -> None:
            if not QMetaObject.invokeMethod(window, "revealTextAppearance"):
                debug("text appearance section could not be revealed")

        QTimer.singleShot(120, reveal_text_appearance)

    if args.show_text_effects:
        def reveal_text_effects() -> None:
            if not QMetaObject.invokeMethod(window, "revealTextEffects"):
                debug("text effects section could not be revealed")

        QTimer.singleShot(120, reveal_text_effects)

    if args.show_batch_export or args.show_batch_advanced:
        def open_batch_export() -> None:
            drawer = window.findChild(QObject, "batchExportDrawer")
            if drawer is not None and args.show_batch_advanced:
                drawer.setProperty("advancedOpen", True)
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("batch export drawer could not be opened")

        QTimer.singleShot(80, open_batch_export)

    if args.show_multi_tab_export:
        def open_multi_tab_export() -> None:
            drawer = window.findChild(QObject, "multiTabExportDrawer")
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("multi-tab export drawer could not be opened")

        QTimer.singleShot(80, open_multi_tab_export)

    if args.show_canvas_presets:
        def open_canvas_presets() -> None:
            drawer = window.findChild(QObject, "canvasPresetDrawer")
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("canvas preset drawer could not be opened")

        QTimer.singleShot(80, open_canvas_presets)

    if args.show_project_presets:
        def open_project_presets() -> None:
            drawer = window.findChild(QObject, "projectPresetDrawer")
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("project preset drawer could not be opened")

        QTimer.singleShot(80, open_project_presets)

    if args.show_data_relations or args.show_size_match:
        def open_data_relations() -> None:
            drawer = window.findChild(QObject, "dataRelationsDrawer")
            if drawer is None:
                debug("data relations drawer could not be found")
                return
            drawer.setProperty("activeTab", 1 if args.show_size_match else 0)
            if not QMetaObject.invokeMethod(drawer, "open"):
                debug("data relations drawer could not be opened")

        QTimer.singleShot(80, open_data_relations)

    if args.show_new_canvas:
        def open_new_canvas() -> None:
            dialog = window.findChild(QObject, "newCanvasDialog")
            if dialog is None or not QMetaObject.invokeMethod(dialog, "open"):
                debug("new canvas dialog could not be opened")

        QTimer.singleShot(80, open_new_canvas)

    if args.show_close_confirm:
        def open_close_confirmation() -> None:
            workspace.document.is_modified = True
            workspace.documentInfoChanged.emit()
            workspace_sessions.requestClose(workspace_sessions.activeIndex)

        QTimer.singleShot(80, open_close_confirmation)

    if args.screenshot:
        output_path = args.screenshot.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            debug("capturing root window")
            try:
                if (
                    args.show_batch_export
                    or args.show_batch_advanced
                    or args.show_multi_tab_export
                    or args.show_new_canvas
                    or args.show_close_confirm
                    or args.show_canvas_presets
                    or args.show_project_presets
                    or args.show_data_relations
                    or args.show_size_match
                ):
                    image = window.grabWindow()
                    saved = not image.isNull() and image.save(str(output_path), "PNG")
                    if saved:
                        print(f"截图已保存：{output_path}")
                        app.exit(0)
                    else:
                        print(f"截图保存失败：{output_path}", file=sys.stderr)
                        app.exit(3)
                    return
                capture_item = window.findChild(QQuickItem, "captureRoot")
                if capture_item is None:
                    raise RuntimeError("未找到 QML 截图根节点")
                grab_value = capture_item.grabToImage()
                grab_result = grab_value[0] if isinstance(grab_value, tuple) else grab_value
                window._qml_grab_result = grab_result

                def save_capture() -> None:
                    image = grab_result.image()
                    saved = not image.isNull() and image.save(str(output_path), "PNG")
                    if saved:
                        print(f"截图已保存：{output_path}")
                        app.exit(0)
                    else:
                        print(f"截图保存失败：{output_path}", file=sys.stderr)
                        app.exit(3)

                grab_result.ready.connect(save_capture)
            except Exception as error:
                print(f"截图保存失败：{error}", file=sys.stderr)
                app.exit(3)

        QTimer.singleShot(1800, capture)

    exit_code = app.exec()
    debug(f"event loop exited with code {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
