# -*- coding: utf-8 -*-
"""探针：选中框手柄的作用域。

修复前 handleAt 只约束单轴距离，边线等于一条向两端无限延伸的带子：
选中框右边框那一整条竖线上的点击全被判成「拖右边缩放」，压在后面的图层永远选不中。
另外容差 10/scale 不做上限，小图层在低缩放下整个被手柄吃满，中心也拖不动。
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

sys.argv = ["probe", "--blank"]

from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest


def main() -> int:
    from app.qml.qml_main import main as qml_main

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    state = {}
    code = {"v": 0}

    def on_ready(window):
        state["window"] = window

    QTimer.singleShot(2500, lambda: _probe(state, app, code))
    qml_main(app=app, on_ready=on_ready)
    return code["v"]


def _probe(state, app, code):
    ok = fail = 0
    try:
        window = state["window"]
        ctx = QQmlEngine.contextForObject(window)
        ws = ctx.contextProperty("workspace")
        pointer = window.findChild(QObject, "canvasPointer")
        canvas = window.findChild(QObject, "canvasWorkspace")
        print(f"  画布对象: {canvas}")

        def scene_of(cx, cy):
            rx = float(pointer.property("width")) / max(1, ws.canvasWidth)
            ry = float(pointer.property("height")) / max(1, ws.canvasHeight)
            p = pointer.mapToScene(QPointF(cx * rx, cy * ry))
            return QPoint(int(p.x()), int(p.y()))

        def click(cx, cy):
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, scene_of(cx, cy))
            QTest.qWait(150)

        def handle_at(cx, cy):
            if canvas is None:
                return "?"
            return canvas.handleAt(cx, cy)

        def setup(shape_x=660):
            ws.newDocument(900, 600)
            ws.document.layers.clear()
            ws.document.add_layer("形状层", shape_x, 250, 180, 200, is_folder=False)
            from app.models.text_layer import TextLayer

            t = TextLayer()
            t.set_current_text("标题", force=True)
            t.font_size = 40
            t.auto_fit_text_box = False
            t.width = 500
            t.height = 400
            ws.document.add_text_layer(t)
            t.x = 150
            t.y = 150
            ws.layerModel.reset_from_document()
            ws.selectionChanged.emit()
            ws.requestPreview(force=True)
            QTest.qWait(150)
            ti = next(i for i, l in enumerate(ws.document.layers) if "文字" in l.name)
            si = next(i for i, l in enumerate(ws.document.layers) if "形状" in l.name)
            return ti, si

        def check(label, got, expect):
            nonlocal ok, fail
            good = got == expect
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
            print(f"  {'OK  ' if good else 'FAIL'} {label}: {got!r} 期望={expect!r}")

        print("=== 1. 手柄作用域：边线延长线上不应有手柄 ===")
        ti, si = setup()
        ws.selectLayer(ti)
        QTest.qWait(120)
        # 文字框 x=150..650, y=150..550
        check("框内中心 handle", handle_at(400, 350), "")
        check("右边框线上 handle", handle_at(650, 350), "e")
        check("右边框延长线下方 handle", handle_at(650, 900), "")
        check("右边框延长线上方 handle", handle_at(650, 10), "")
        check("下边框延长线右侧 handle", handle_at(880, 550), "")
        check("左上角 handle", handle_at(150, 150), "nw")

        print("\n=== 2. 边线延长线上的图层能被点中 ===")
        ti, si = setup(shape_x=620)
        ws.selectLayer(ti)
        QTest.qWait(150)
        # 形状层 y=250..450，右边框延长线 x=650 与之相交
        click(700, 350)
        got = ws.selectedLayerIndex
        name = ws.document.layers[got].name if got >= 0 else None
        check(f"点形状层(700,350)", (got, name), (si, "形状层"))

        print("\n=== 3. 小图层低缩放下中心仍可拖动 ===")
        ws.newDocument(900, 600)
        ws.document.layers.clear()
        ws.document.add_layer("小图层", 400, 300, 40, 30, is_folder=False)
        ws.layerModel.reset_from_document()
        ws.selectionChanged.emit()
        ws.requestPreview(force=True)
        QTest.qWait(150)
        ws.setZoomFactor(0.3)
        ws.selectLayer(0)
        QTest.qWait(150)
        # 图层画布坐标 x=400..440, y=300..330 -> 中心 (420,315)
        check("小图层中心 handle", handle_at(420, 315), "")
        before = (ws.document.layers[0].x, ws.document.layers[0].y)
        start = scene_of(420, 315)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, QPoint(start.x() + 25, start.y() + 15))
        QTest.qWait(60)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(start.x() + 25, start.y() + 15))
        QTest.qWait(150)
        after = (ws.document.layers[0].x, ws.document.layers[0].y)
        check("小图层被拖动", after != before, True)

        print("\n=== 4. 正常缩放/缩放下手柄仍可用 ===")
        ws.newDocument(900, 600)
        ws.document.layers.clear()
        ws.document.add_layer("图", 200, 200, 300, 200, is_folder=False)
        ws.layerModel.reset_from_document()
        ws.selectionChanged.emit()
        ws.requestPreview(force=True)
        QTest.qWait(150)
        ws.setZoomFactor(1.0)
        ws.selectLayer(0)
        QTest.qWait(150)
        check("右边框 handle", handle_at(500, 300), "e")
        check("右下角 handle", handle_at(500, 400), "se")
        check("中心 handle", handle_at(350, 300), "")

        print(f"\n结果: 通过 {ok} 项，失败 {fail} 项")
        if fail:
            code["v"] = 1

    except Exception:
        import traceback

        traceback.print_exc()
        code["v"] = 1
    finally:
        app.quit()


if __name__ == "__main__":
    raise SystemExit(main())
