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

    from PySide6.QtCore import QPoint, QPointF, QTimer, Qt, QUrl
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
        auto_render=False,
        parent=engine,
    )
    engine.addImageProvider("documentPreview", provider)
    engine.rootContext().setContextProperty("workspace", workspace)
    engine.rootContext().setContextProperty("layerModel", workspace.layerModel)
    workspace.createDemoDocument(str(repo_root / "app" / "qml" / "assets" / "watch-product.jpg"))
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
        print(
            f"dragged layer to ({moved_x}, {moved_y}); "
            f"resized to ({resized_width}, {resized_height}); "
            f"locked image ratio {resized_ratio:.4f}"
        )
        app.exit(0)

    QTimer.singleShot(250, run_drag)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
