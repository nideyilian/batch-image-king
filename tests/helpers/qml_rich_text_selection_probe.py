from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=760)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPointF, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem

    from app.models.text_layer import TextLayer
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
    workspace.document.create_new(720, 480)
    layer = TextLayer(name="选区文字", x=80, y=120, width=500, height=150)
    layer.text_binding_enabled = False
    layer.auto_fit_text_box = False
    layer.width = 500
    layer.height = 150
    layer.font_size = 44
    layer.text_color = (24, 30, 32, 255)
    layer.set_text_lines(["主标题 😀 局部样式\n颜色与字号实时预览"])
    layer.set_current_text("主标题 😀 局部样式\n颜色与字号实时预览", force=True)
    layer.set_text_color_range(4, 10, (220, 62, 76, 255))
    layer.set_font_size_range(4, 10, 58)
    workspace.document.add_text_layer(layer)
    workspace.layerModel.reset_from_document()
    workspace.selectLayer(0)
    workspace.setZoomFactor(0.8)

    engine.addImageProvider("documentPreview", provider)
    engine.rootContext().setContextProperty("workspace", workspace)
    engine.rootContext().setContextProperty("layerModel", workspace.layerModel)
    batch_export = BatchExportViewModel(workspace=workspace, parent=engine)
    workspace_sessions = WorkspaceSessionViewModel(workspace=workspace, parent=engine)
    engine.rootContext().setContextProperty("batchExport", batch_export)
    engine.rootContext().setContextProperty("workspaceSessions", workspace_sessions)
    engine.load(QUrl.fromLocalFile(str(repo_root / "app" / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 2

    window = engine.rootObjects()[0]
    window.setProperty("width", max(1180, args.width))
    window.setProperty("height", max(720, args.height))
    window.show()

    def enter_editing() -> None:
        if not workspace.startTextEditOverlay():
            app.exit(3)
            return
        text_edit = window.findChild(QQuickItem, "canvasTextEditInput")
        if text_edit is None:
            app.exit(4)
            return
        text_edit.forceActiveFocus()
        QMetaObject.invokeMethod(text_edit, "select", Q_ARG(int, 4), Q_ARG(int, 11))

        def capture() -> None:
            toolbar = window.findChild(QQuickItem, "canvasTextSelectionToolbar")
            if toolbar is None or not bool(toolbar.property("visible")):
                visibility_chain = []
                item = text_edit
                while item is not None and len(visibility_chain) < 12:
                    visibility_chain.append(
                        f"{item.metaObject().className()}[{item.objectName() or '-'}]="
                        f"{item.property('visible')}"
                    )
                    item = item.parentItem()
                print(
                    "selection toolbar is not visible: "
                    f"overlay={workspace.textEditOverlayVisible}, "
                    f"selectedText={workspace.selectedIsTextLayer}, "
                    f"selectedIndex={workspace.selectedLayerIndex}, "
                    f"selectedCount={workspace.selectedLayerCount}, "
                    f"binding={workspace.selectedTextBindingEnabled}, "
                    f"selection=({text_edit.property('selectionStart')}, "
                    f"{text_edit.property('selectionEnd')}), "
                    f"editorVisible={text_edit.property('visible')}, "
                    f"visibilityChain={' > '.join(visibility_chain)}",
                    file=sys.stderr,
                )
                app.exit(5)
                return
            toolbar_origin = toolbar.mapToScene(QPointF(0, 0))
            toolbar_width = float(toolbar.property("width")) * float(toolbar.property("scale"))
            toolbar_height = float(toolbar.property("height")) * float(toolbar.property("scale"))
            if (
                toolbar_origin.x() < 0
                or toolbar_origin.y() < 0
                or toolbar_origin.x() + toolbar_width > window.width()
                or toolbar_origin.y() + toolbar_height > window.height()
            ):
                print(
                    f"toolbar outside window: origin={toolbar_origin}, "
                    f"size=({toolbar_width}, {toolbar_height})",
                    file=sys.stderr,
                )
                app.exit(6)
                return
            image = window.grabWindow()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if image.isNull() or not image.save(str(args.output), "PNG"):
                app.exit(7)
                return
            print(
                f"selection toolbar visible at "
                f"({toolbar_origin.x():.1f}, {toolbar_origin.y():.1f}), "
                f"layer=({layer.width}x{layer.height}), "
                f"editor=({text_edit.property('width')}x{text_edit.property('height')}), "
                f"painted=({text_edit.property('paintedWidth')}x{text_edit.property('paintedHeight')}), "
                f"screenshot={args.output}"
            )
            app.exit(0)

        QTimer.singleShot(350, capture)

    QTimer.singleShot(300, enter_editing)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
