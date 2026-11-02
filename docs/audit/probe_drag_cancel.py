# -*- coding: utf-8 -*-
"""探针：拖动中取消（Esc / 鼠标离开）必须还原几何。

因为拖动中 previewLiveGeometry 会实时改图层几何，
取消时如果不还原，会留下半成品。
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

        def scene_of(cx, cy):
            rx = float(pointer.property("width")) / max(1, ws.canvasWidth)
            ry = float(pointer.property("height")) / max(1, ws.canvasHeight)
            p = pointer.mapToScene(QPointF(cx * rx, cy * ry))
            return QPoint(int(p.x()), int(p.y()))

        def geom():
            l = ws.document.layers[0]
            return (l.x, l.y, l.width, l.height)

        def setup():
            ws.newDocument(900, 600)
            ws.document.layers.clear()
            ws.document.add_layer("图层", 200, 200, 400, 300, is_folder=False)
            ws.layerModel.reset_from_document()
            ws.selectionChanged.emit()
            ws.requestPreview(True)
            QTest.qWait(400)
            ws.setZoomFactor(1.0)
            ws.selectLayer(0)
            QTest.qWait(300)

        def check(label, got, expect):
            nonlocal ok, fail
            good = got == expect
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
            print(f"  {'OK  ' if good else 'FAIL'} {label}: {got} 期望={expect}")

        print("=== 1. 拖动移动中取消，几何应还原 ===")
        setup()
        before = geom()
        print(f"  起始 {before}")
        start = scene_of(400, 350)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        for i in range(1, 7):
            QTest.mouseMove(window, QPoint(start.x() + i * 12, start.y() + i * 8))
            QTest.qWait(20)
        during = geom()
        print(f"  拖动中 {during} (应已变化)")
        check("拖动中几何已变", during != before, True)

        canvas.cancelTransform()
        QTest.qWait(300)
        after = geom()
        print(f"  取消后 {after}")
        check("取消后几何还原", after, before)

        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier,
                           QPoint(start.x() + 6 * 12, start.y() + 6 * 8))
        QTest.qWait(300)
        check("松手后仍是还原值", geom(), before)

        print("\n=== 2. 拖动缩放中取消，宽高也应还原 ===")
        setup()
        before = geom()
        # 右下角手柄 (600,500)
        s = scene_of(600, 500)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, s)
        for i in range(1, 7):
            QTest.mouseMove(window, QPoint(s.x() + i * 10, s.y() + i * 8))
            QTest.qWait(20)
        during = geom()
        check("缩放中尺寸已变", during[2] != before[2] or during[3] != before[3], True)

        canvas.cancelTransform()
        QTest.qWait(300)
        check("取消后尺寸还原", geom(), before)

        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier,
                           QPoint(s.x() + 60, s.y() + 48))
        QTest.qWait(300)

        print("\n=== 3. 正常拖动提交仍然生效（不要被还原逻辑拖累）===")
        setup()
        before = geom()
        start = scene_of(400, 350)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        for i in range(1, 7):
            QTest.mouseMove(window, QPoint(start.x() + i * 10, start.y() + i * 6))
            QTest.qWait(20)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier,
                           QPoint(start.x() + 60, start.y() + 36))
        QTest.qWait(400)
        after = geom()
        print(f"  {before} -> {after}")
        check("正常拖动提交后位置改变", (after[0], after[1]) != (before[0], before[1]), True)
        check("尺寸不变", (after[2], after[3]), (before[2], before[3]))

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
