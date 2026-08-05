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
    parser.add_argument("--show-batch-export", action="store_true", help="启动后打开批量导出面板")
    parser.add_argument("--show-effects", action="store_true", help="启动后打开图层效果面板")
    parser.add_argument("--show-new-canvas", action="store_true", help="启动后打开新建画布弹窗")
    parser.add_argument("--show-close-confirm", action="store_true", help="启动后打开未保存文档关闭确认")
    parser.add_argument("--demo-effects", action="store_true", help="为选中图片图层应用演示效果")
    parser.add_argument("--select-layer", type=int, help="启动后选中指定图层索引")
    parser.add_argument("--duplicate-selected", action="store_true", help="启动后复制当前选中图层")
    parser.add_argument("--demo-tabs", action="store_true", help="启动后创建多个文档标签用于验收")
    parser.add_argument("--demo-shaped", action="store_true", help="启动后创建真实异形图层用于验收")
    parser.add_argument("--show-random-transform", action="store_true", help="展示图片图层随机变换配置")
    parser.add_argument("--show-text-typography", action="store_true", help="展示文字字体与核心排版配置")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    debug_enabled = os.environ.get("BTPW_QML_DEBUG") == "1"

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
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
    from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    debug("creating QGuiApplication")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("批图王 QML")
    app.setOrganizationName("BatchImageKing")
    app.aboutToQuit.connect(lambda: QThreadPool.globalInstance().waitForDone(5000))
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
    engine.addImageProvider("documentPreview", preview_provider)

    if args.open_path:
        workspace.openDocument(str(args.open_path.expanduser().resolve()))
    elif args.blank:
        workspace.newDocument(1080, 1350)
    else:
        workspace.createDemoDocument(str(qml_dir / "assets" / "watch-product.jpg"))

    if args.select_layer is not None:
        workspace.selectLayer(args.select_layer)
    elif args.show_random_transform:
        workspace.selectLayer(0)
    elif args.show_text_typography:
        workspace.selectLayer(1)
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

    workspace_sessions = WorkspaceSessionViewModel(workspace=workspace, parent=engine)
    if args.demo_tabs:
        workspace_sessions.newDocument(1080, 1080)
        workspace_sessions.newDocument(1920, 1080)
        workspace_sessions.activateDocument(0)

    engine.rootContext().setContextProperty("workspace", workspace)
    engine.rootContext().setContextProperty("workspaceSessions", workspace_sessions)
    engine.rootContext().setContextProperty("layerModel", workspace.layerModel)
    engine.rootContext().setContextProperty("batchExport", batch_export)

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

    if args.show_batch_export:
        def open_batch_export() -> None:
            drawer = window.findChild(QObject, "batchExportDrawer")
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("batch export drawer could not be opened")

        QTimer.singleShot(80, open_batch_export)

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
                if args.show_batch_export or args.show_new_canvas or args.show_close_confirm:
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
