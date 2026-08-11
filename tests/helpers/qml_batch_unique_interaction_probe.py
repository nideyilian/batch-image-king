from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, QTimer, Qt, QUrl
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
    workspace = WorkspaceViewModel(preview_provider=provider, auto_render=True, parent=engine)
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
    window.setProperty("width", 1180)
    window.setProperty("height", 720)

    def click_item(item: QQuickItem) -> None:
        scene_point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(scene_point.x()), round(scene_point.y())),
        )

    def verify_interaction() -> None:
        drawer = window.findChild(QObject, "batchExportDrawer")
        if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
            print("batch export drawer not found", file=sys.stderr)
            app.exit(3)
            return

        QTest.qWait(250)
        strategy_options = window.findChild(QQuickItem, "batchStrategyOptions")
        if strategy_options is None:
            print("strategy control not found", file=sys.stderr)
            app.exit(4)
            return
        scene_point = strategy_options.mapToScene(
            QPointF(strategy_options.width() / 2, strategy_options.height() / 2)
        )
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(scene_point.x()), round(scene_point.y())),
        )
        app.processEvents()
        if not batch_export.uniqueUseEnabled:
            print("unique strategy click did not enable the option", file=sys.stderr)
            app.exit(5)
            return

        picker = window.findChild(QQuickItem, "uniqueLayerPicker")
        menu = window.findChild(QQuickItem, "uniqueLayerMenu")
        if picker is None or menu is None:
            print("unique layer controls not found", file=sys.stderr)
            app.exit(6)
            return
        click_item(picker)
        app.processEvents()
        if not menu.property("visible"):
            print("unique layer menu did not open", file=sys.stderr)
            app.exit(7)
            return

        first_option = menu.mapToScene(QPointF(20, 20))
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(first_option.x()), round(first_option.y())),
        )
        app.processEvents()
        selected_layers = [
            option["index"]
            for option in batch_export.uniqueLayerOptions
            if option["eligible"] and option["selected"]
        ]
        if selected_layers != [0]:
            print(f"unexpected selected unique layers: {selected_layers}", file=sys.stderr)
            app.exit(8)
            return
        if not drawer.property("opened"):
            print("batch export drawer closed during unique layer selection", file=sys.stderr)
            app.exit(9)
            return

        print("single-use image layer selected through the compact drawer")
        app.exit(0)

    QTimer.singleShot(100, verify_interaction)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
