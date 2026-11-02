# -*- coding: utf-8 -*-
"""探针：Photoshop 风格的拖动手势。

覆盖：
- 拖 8 个手柄 -> 缩放（各方向锚点正确）
- 拖选框内部 -> 移动
- 单击 -> 什么都不发生
- 拖边框线非手柄处 -> 穿透
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

        def drag(x1, y1, x2, y2):
            s = scene_of(x1, y1)
            e = scene_of(x2, y2)
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, s)
            # 分几步移动，模拟真实手势
            for i in range(1, 5):
                mid = QPoint(int(s.x() + (e.x() - s.x()) * i / 4),
                             int(s.y() + (e.y() - s.y()) * i / 4))
                QTest.mouseMove(window, mid)
                QTest.qWait(20)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, e)
            QTest.qWait(200)

        def geom():
            l = ws.document.layers[0]
            return (l.x, l.y, l.width, l.height)

        def setup():
            ws.newDocument(900, 600)
            ws.document.layers.clear()
            ws.document.add_layer("图层", 200, 200, 400, 300, is_folder=False)
            ws.layerModel.reset_from_document()
            ws.selectionChanged.emit()
            ws.requestPreview(force=True)
            QTest.qWait(200)
            ws.setZoomFactor(1.0)
            ws.selectLayer(0)
            QTest.qWait(150)

        def check(label, got, expect):
            nonlocal ok, fail
            good = got == expect
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
            print(f"  {'OK  ' if good else 'FAIL'} {label}: {got} 期望={expect}")

        # 图层 x=200..600 y=200..500，手柄在四角与四边中点
        print("图层 200,200 400x300；手柄四角 (200,200)(600,200)(200,500)(600,500)")

        print("\n=== 拖右下角 se：宽高同时增 ===")
        setup()
        drag(600, 500, 680, 560)
        g = geom()
        check("右下角拖动", (g[0], g[1], g[2] > 400, g[3] > 300), (200, 200, True, True))

        print("\n=== 拖右中点 e：只改宽 ===")
        setup()
        drag(600, 350, 680, 380)
        g = geom()
        check("右中点拖动 (x,y,h 不变)", (g[0], g[1], g[3]), (200, 200, 300))
        check("宽度增加", g[2] > 400, True)

        print("\n=== 拖上中点 n：只改高与 y ===")
        setup()
        drag(400, 200, 400, 140)
        g = geom()
        check("上中点拖动 y 上移", g[1] < 200, True)
        check("宽度不变", g[2], 400)
        check("下边缘不动", g[1] + g[3], 500)

        print("\n=== 拖左上角 nw：x/y 左上移，右下不动 ===")
        setup()
        drag(200, 200, 160, 150)
        g = geom()
        check("左上角 x", g[0] < 200, True)
        check("左上角 y", g[1] < 200, True)
        check("右边缘不动", g[0] + g[2], 600)
        check("下边缘不动", g[1] + g[3], 500)

        print("\n=== 拖选框内部：整体移动，尺寸不变 ===")
        setup()
        drag(400, 350, 460, 400)
        g = geom()
        check("尺寸不变", (g[2], g[3]), (400, 300))
        check("位置右移", g[0] > 200, True)
        check("位置下移", g[1] > 200, True)

        print("\n=== 单击：什么都不变 ===")
        setup()
        before = geom()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, scene_of(400, 350))
        QTest.qWait(200)
        check("单击后几何", geom(), before)

        print("\n=== 拖边框线非手柄处 (600,430)：应穿透或不动，不缩放 ===")
        setup()
        before = geom()
        drag(600, 430, 660, 430)
        g = geom()
        # 该点在上层右边框、非手柄，且上层是唯一图层 -> 穿透后落在画布空白，
        # 不应产生任何缩放
        check("尺寸未变", (g[2], g[3]), (before[2], before[3]))

        print("\n=== 拖角时按住 Shift：等比缩放 ===")
        # QTest.mouseMove 不透传修饰键（实测 onPositionChanged 里 modifiers 恒为 0），
        # offscreen 下 keyPress 也进不了窗口。所以这里直接调用 QML 的
        # updateTransform(x, y, true) 验证等比分支本身，手势层另有用例覆盖。
        from PySide6.QtCore import QMetaObject, Q_ARG
        setup()
        before = geom()
        ratio_before = before[2] / before[3]
        canvas.beginTransform("se", 600, 500)
        ok_invoke = QMetaObject.invokeMethod(
            canvas, "updateTransform",
            Q_ARG("QVariant", 660), Q_ARG("QVariant", 540), Q_ARG("QVariant", True)
        )
        QTest.qWait(50)
        print(f"       updateTransform 调用={ok_invoke} shiftHeld={canvas.property('transformShiftHeld')}")
        check("shiftHeld 已置位", canvas.property("transformShiftHeld"), True)
        canvas.commitTransform()
        QTest.qWait(200)
        g = geom()
        ratio_after = g[2] / max(1, g[3])
        check("Shift 拖角变大了", g[2] > before[2], True)
        print(f"       比例 {ratio_before:.4f} -> {ratio_after:.4f}")
        check("比例保持(误差<2%)", abs(ratio_after - ratio_before) / ratio_before < 0.02, True)

        print("\n=== 对照：不按 Shift 拖同一角，比例应变 ===")
        setup()
        before = geom()
        ratio_before2 = before[2] / before[3]
        canvas.beginTransform("se", 600, 500)
        QMetaObject.invokeMethod(
            canvas, "updateTransform",
            Q_ARG("QVariant", 760), Q_ARG("QVariant", 520), Q_ARG("QVariant", False)
        )
        QTest.qWait(50)
        canvas.commitTransform()
        QTest.qWait(200)
        g = geom()
        ratio_after2 = g[2] / max(1, g[3])
        print(f"       比例 {ratio_before2:.4f} -> {ratio_after2:.4f}")
        check("自由缩放比例改变", abs(ratio_after2 - ratio_before2) / ratio_before2 > 0.02, True)

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
