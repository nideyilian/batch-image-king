# -*- coding: utf-8 -*-
"""探针：真实操作序列下的画布选择（单击/双击编辑/点空白/再选）。"""

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

        def setup():
            ws.newDocument(900, 600)
            ws.document.layers.clear()
            ws.document.add_layer("图片层", 520, 380, 220, 180, is_folder=False)
            from app.models.text_layer import TextLayer

            t = TextLayer()
            t.set_current_text("测试文字", force=True)
            t.font_size = 40
            ws.document.add_text_layer(t)
            t.x = 120
            t.y = 140
            ws.layerModel.reset_from_document()
            ws.selectionChanged.emit()
            ws.requestPreview(force=True)
            QTest.qWait(150)
            ti = next(i for i, l in enumerate(ws.document.layers) if "文字" in l.name)
            pi = next(i for i, l in enumerate(ws.document.layers) if "图片" in l.name)
            return ti, pi

        def scene_of(cx, cy):
            rx = float(pointer.property("width")) / max(1, ws.canvasWidth)
            ry = float(pointer.property("height")) / max(1, ws.canvasHeight)
            p = pointer.mapToScene(QPointF(cx * rx, cy * ry))
            return QPoint(int(p.x()), int(p.y()))

        def click(cx, cy):
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, scene_of(cx, cy))
            QTest.qWait(160)

        def dclick(cx, cy):
            QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, scene_of(cx, cy))
            QTest.qWait(220)

        def check(label, expect, extra=""):
            nonlocal ok, fail
            got = ws.selectedLayerIndex
            good = got == expect
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
            print(f"  {'OK  ' if good else 'FAIL'} {label}: selected={got} 期望={expect}"
                  f" overlay={ws.textEditOverlayVisible} {extra}")

        print("=== 1. 单击选中文字层（不进入编辑），再点图片层 ===")
        ti, pi = setup()
        click(160, 160)
        check("单击文字层", ti)
        click(620, 450)
        check("点图片层", pi)

        print("\n=== 2. 单击选中文字层，点图片层，再点回文字层 ===")
        ti, pi = setup()
        click(160, 160)
        click(620, 450)
        click(160, 160)
        check("回到文字层", ti)

        print("\n=== 3. 双击文字层进入编辑，再点图片层（一次点击）===")
        ti, pi = setup()
        dclick(160, 160)
        print(f"       双击后 overlay={ws.textEditOverlayVisible} selected={ws.selectedLayerIndex}")
        click(620, 450)
        check("一次点击切到图片层", pi)

        print("\n=== 4. 双击编辑 -> 点空白 -> 再点图片层 ===")
        ti, pi = setup()
        dclick(160, 160)
        click(800, 120)
        check("点空白清选择", -1)
        click(620, 450)
        check("点图片层", pi)

        print("\n=== 5. 编辑状态点图片层后，图片层能被拖动/缩放（变换未被吞）===")
        ti, pi = setup()
        dclick(160, 160)
        click(620, 450)
        before = (ws.document.layers[pi].x, ws.document.layers[pi].y)
        start = scene_of(620, 450)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, QPoint(start.x() + 30, start.y() + 20))
        QTest.qWait(60)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(start.x() + 30, start.y() + 20))
        QTest.qWait(150)
        after = (ws.document.layers[pi].x, ws.document.layers[pi].y)
        moved = abs(after[0] - before[0]) > 0 or abs(after[1] - before[1]) > 0
        print(f"  {'OK  ' if moved else 'FAIL'} 拖动图片层: {before} -> {after}")
        ok, fail = (ok + 1, fail) if moved else (ok, fail + 1)

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
