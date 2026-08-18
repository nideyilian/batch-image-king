from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, QPointF, QTimer, Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
    from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    provider = PreviewImageProvider()
    workspace = WorkspaceViewModel(
        preview_provider=provider,
        auto_render=True,
        parent=engine,
    )
    engine.addImageProvider("documentPreview", provider)
    engine.rootContext().setContextProperty("workspace", workspace)
    engine.rootContext().setContextProperty("layerModel", workspace.layerModel)
    workspace.createDemoDocument(str(repo_root / "app" / "qml" / "assets" / "watch-product.jpg"))
    workspace.setZoomFactor(0.4)
    batch_export = BatchExportViewModel(workspace=workspace, parent=engine)
    workspace_sessions = WorkspaceSessionViewModel(workspace=workspace, parent=engine)
    engine.rootContext().setContextProperty("batchExport", batch_export)
    engine.rootContext().setContextProperty("workspaceSessions", workspace_sessions)
    engine.load(QUrl.fromLocalFile(str(repo_root / "app" / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 2

    window = engine.rootObjects()[0]
    window.setProperty("width", 1280)
    window.setProperty("height", 760)

    def run_drag() -> None:
        artboard = window.findChild(QQuickItem, "artboard")
        if artboard is None:
            app.exit(3)
            return
        start = artboard.mapToScene(QPointF(120, 1100))
        end = artboard.mapToScene(QPointF(160, 1130))
        start_point = QPoint(round(start.x()), round(start.y()))
        end_point = QPoint(round(end.x()), round(end.y()))
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start_point)
        QTest.mouseMove(window, end_point, 30)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end_point)

        layer = workspace.document.layers[1]
        moved_x = int(layer.x)
        moved_y = int(layer.y)
        if workspace.selectedLayerIndex != 1 or not (107 <= moved_x <= 109 and 1069 <= moved_y <= 1071):
            print(
                f"interaction mismatch: selected={workspace.selectedLayerIndex}, "
                f"position=({moved_x}, {moved_y})",
                file=sys.stderr,
            )
            app.exit(4)
            return

        original_width = int(layer.width)
        original_height = int(layer.height)
        resize_start = artboard.mapToScene(
            QPointF(layer.x + layer.width, layer.y + layer.height)
        )
        resize_end = artboard.mapToScene(
            QPointF(layer.x + layer.width + 40, layer.y + layer.height + 30)
        )
        resize_start_point = QPoint(round(resize_start.x()), round(resize_start.y()))
        resize_end_point = QPoint(round(resize_end.x()), round(resize_end.y()))
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, resize_start_point)
        QTest.mouseMove(window, resize_end_point, 30)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, resize_end_point)

        resized_width = int(layer.width)
        resized_height = int(layer.height)
        if not (
            original_width + 39 <= resized_width <= original_width + 41
            and original_height + 29 <= resized_height <= original_height + 31
        ):
            print(
                f"resize mismatch: before=({original_width}, {original_height}), "
                f"after=({resized_width}, {resized_height})",
                file=sys.stderr,
            )
            app.exit(5)
            return

        image_layer = workspace.document.layers[0]
        image_layer.x = 200
        image_layer.y = 200
        image_layer.width = 400
        image_layer.height = 200
        image_layer.aspect_ratio_locked = True
        workspace.selectLayer(0)
        workspace.selectionChanged.emit()

        locked_ratio = image_layer.width / image_layer.height
        locked_start = artboard.mapToScene(
            QPointF(image_layer.x + image_layer.width, image_layer.y + image_layer.height)
        )
        locked_end = artboard.mapToScene(
            QPointF(image_layer.x + image_layer.width + 80, image_layer.y + image_layer.height + 50)
        )
        locked_start_point = QPoint(round(locked_start.x()), round(locked_start.y()))
        locked_end_point = QPoint(round(locked_end.x()), round(locked_end.y()))
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, locked_start_point)
        QTest.mouseMove(window, locked_end_point, 30)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, locked_end_point)

        resized_ratio = image_layer.width / image_layer.height
        if image_layer.width <= 400 or abs(resized_ratio - locked_ratio) > 0.01:
            print(
                f"locked resize mismatch: size=({image_layer.width}, {image_layer.height}), "
                f"ratio={resized_ratio:.4f}",
                file=sys.stderr,
            )
            app.exit(6)
            return

        image_layer.locked = False
        workspace.selectLayer(0)
        workspace.selectionChanged.emit()
        app.processEvents()

        opacity_slider = window.findChild(QQuickItem, "opacitySlider")
        if opacity_slider is None:
            print("opacity slider not found", file=sys.stderr)
            app.exit(7)
            return

        inspector_scroll = window.findChild(QQuickItem, "inspectorScroll")
        inspector_flickable = (
            inspector_scroll.property("contentItem")
            if inspector_scroll is not None
            else None
        )
        if inspector_flickable is None:
            print("inspector scroll content not found", file=sys.stderr)
            app.exit(7)
            return

        slider_origin = opacity_slider.mapToScene(QPointF(0, 0))
        viewport_origin = inspector_flickable.mapToScene(QPointF(0, 0))
        current_content_y = float(inspector_flickable.property("contentY") or 0)
        viewport_height = float(inspector_flickable.property("height") or 0)
        target_content_y = (
            current_content_y
            + slider_origin.y()
            - viewport_origin.y()
            - viewport_height / 2
        )
        inspector_flickable.setProperty("contentY", max(0, target_content_y))
        app.processEvents()

        slider_width = float(opacity_slider.property("width"))
        slider_height = float(opacity_slider.property("height"))
        opacity_start = opacity_slider.mapToScene(
            QPointF(slider_width - 7, slider_height / 2)
        )
        opacity_end = opacity_slider.mapToScene(
            QPointF(slider_width * 0.35, slider_height / 2)
        )
        opacity_start_point = QPoint(round(opacity_start.x()), round(opacity_start.y()))
        opacity_end_point = QPoint(round(opacity_end.x()), round(opacity_end.y()))
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, opacity_start_point)
        QTest.mouseMove(window, opacity_end_point, 30)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, opacity_end_point)

        opacity_percent = round(float(image_layer.opacity) * 100)
        if not 32 <= opacity_percent <= 38:
            print(
                f"opacity slider mismatch: expected about 35%, got {opacity_percent}%; "
                f"size=({slider_width:.1f}, {slider_height:.1f}), "
                f"enabled={opacity_slider.property('enabled')}, "
                f"visible={opacity_slider.property('visible')}, "
                f"scene=({opacity_start.x():.1f}, {opacity_start.y():.1f})"
                f"->({opacity_end.x():.1f}, {opacity_end.y():.1f})",
                file=sys.stderr,
            )
            app.exit(8)
            return

        layer_panel = window.findChild(QQuickItem, "layerPanel")
        inspector_panel = window.findChild(QQuickItem, "inspectorPanel")
        layer_handle = window.findChild(QQuickItem, "layerPanelResizeHandle")
        inspector_handle = window.findChild(QQuickItem, "inspectorResizeHandle")
        sidebar_settings = window.findChild(QObject, "sidebarSettings")
        if None in (layer_panel, inspector_panel, layer_handle, sidebar_settings):
            print("layer sidebar resize controls not found", file=sys.stderr)
            app.exit(9)
            return
        if inspector_handle is not None:
            print("fixed inspector unexpectedly has a resize handle", file=sys.stderr)
            app.exit(10)
            return

        initial_layer_width = float(layer_panel.property("width"))
        initial_inspector_width = float(inspector_panel.property("width"))
        if round(initial_inspector_width) != 320:
            print(f"fixed inspector width mismatch: {initial_inspector_width}", file=sys.stderr)
            app.exit(11)
            return

        if not QMetaObject.invokeMethod(
            layer_handle,
            "dragMoved",
            Q_ARG(float, 64.0),
        ):
            print("layer sidebar resize signal could not be invoked", file=sys.stderr)
            app.exit(12)
            return
        QTest.qWait(40)
        resized_layer_width = float(layer_panel.property("width"))
        if not resized_layer_width >= initial_layer_width + 60:
            print(
                f"layer sidebar resize mismatch: before={initial_layer_width}, after={resized_layer_width}",
                file=sys.stderr,
            )
            app.exit(13)
            return

        fixed_inspector_width = float(inspector_panel.property("width"))
        if round(fixed_inspector_width) != 320:
            print(
                "inspector width changed while resizing layer sidebar: "
                f"before={initial_inspector_width}, after={fixed_inspector_width}",
                file=sys.stderr,
            )
            app.exit(14)
            return

        if not QMetaObject.invokeMethod(layer_handle, "resetRequested"):
            print("layer sidebar reset signal could not be invoked", file=sys.stderr)
            app.exit(15)
            return
        QTest.qWait(40)
        if round(float(layer_panel.property("width"))) != 246:
            print(
                "layer sidebar reset mismatch: "
                f"item={layer_panel.property('width')}, "
                f"window={window.property('layerPanelWidth')}, "
                f"width={window.property('width')}, "
                f"saved={sidebar_settings.property('layerPanelWidth')}",
                file=sys.stderr,
            )
            app.exit(16)
            return
        if round(float(inspector_panel.property("width"))) != 320:
            print(f"fixed inspector width mismatch: {inspector_panel.property('width')}", file=sys.stderr)
            app.exit(17)
            return
        if round(float(sidebar_settings.property("layerPanelWidth"))) != 246:
            print("layer sidebar width setting was not persisted", file=sys.stderr)
            app.exit(18)
            return

        print(
            f"dragged layer to ({moved_x}, {moved_y}); "
            f"resized to ({resized_width}, {resized_height}); "
            f"locked image ratio {resized_ratio:.4f}; "
            f"opacity {opacity_percent}%; "
            f"layer sidebar resized to {resized_layer_width:.0f}; "
            f"inspector fixed at {fixed_inspector_width:.0f}"
        )
        app.exit(0)

    QTimer.singleShot(250, run_drag)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
