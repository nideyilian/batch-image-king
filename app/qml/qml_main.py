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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    debug_enabled = os.environ.get("BTPW_QML_DEBUG") == "1"

    def debug(message: str) -> None:
        if debug_enabled:
            print(f"[qml] {message}", flush=True)

    if args.screenshot:
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        os.environ.setdefault("QT_QPA_FONTDIR", str(windows_dir / "Fonts"))

    qml_dir = Path(__file__).resolve().parent
    repo_root = qml_dir.parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    debug("importing Qt modules")
    from PySide6.QtCore import QThreadPool, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from app.qml.preview_image_provider import PreviewImageProvider
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
    engine.addImageProvider("documentPreview", preview_provider)
    engine.rootContext().setContextProperty("workspace", workspace)
    engine.rootContext().setContextProperty("layerModel", workspace.layerModel)

    if args.open_path:
        workspace.openDocument(str(args.open_path.expanduser().resolve()))
    elif args.blank:
        workspace.newDocument(1080, 1350)
    else:
        workspace.createDemoDocument(str(qml_dir / "assets" / "watch-product.jpg"))

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

    if args.screenshot:
        output_path = args.screenshot.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            debug("capturing root window")
            try:
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
