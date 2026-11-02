# -*- coding: utf-8 -*-
"""探针：单击选中是否产生副作用（位移/吸附），以及手柄命中区形状。

对照 Photoshop 移动工具：
- 单击图层 = 选中，位置不动
- 拖动图层内部 = 移动
- 只在 8 个离散手柄上拖动 = 缩放，边框线本身不可缩放
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

        def click(cx, cy):
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, scene_of(cx, cy))
            QTest.qWait(160)

        def check(label, got, expect):
            nonlocal ok, fail
            good = got == expect
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
            print(f"  {'OK  ' if good else 'FAIL'} {label}: {got!r} 期望={expect!r}")

        def setup(layer_x=200, layer_y=200, layer_w=400, layer_h=300):
            ws.newDocument(900, 600)
            ws.document.layers.clear()
            ws.document.add_layer("图层", layer_x, layer_y, layer_w, layer_h, is_folder=False)
            ws.layerModel.reset_from_document()
            ws.selectionChanged.emit()
            ws.requestPreview(force=True)
            QTest.qWait(200)

        print("=== 1. 单击选中不应改变图层几何 ===")
        setup()
        ws.setZoomFactor(1.0)
        QTest.qWait(150)
        layer = ws.document.layers[0]
        before = (layer.x, layer.y, layer.width, layer.height)
        click(400, 350)   # 图层内部
        layer = ws.document.layers[0]
        after = (layer.x, layer.y, layer.width, layer.height)
        check("单击后几何", after, before)
        check("单击后选中", ws.selectedLayerIndex, 0)

        print("\n=== 2. 连续单击同一处 5 次，几何应稳定 ===")
        setup()
        ws.setZoomFactor(1.0)
        QTest.qWait(150)
        for i in range(5):
            click(400, 350)
        layer = ws.document.layers[0]
        check("5 次单击后几何", (layer.x, layer.y, layer.width, layer.height), (200, 200, 400, 300))

        print("\n=== 3. 手柄命中区：应是 8 个离散点，不是整条边 ===")
        setup()
        ws.setZoomFactor(1.0)
        ws.selectLayer(0)
        QTest.qWait(150)
        # 图层 x=200..600 y=200..500
        cases = [
            ("左上角手柄", 200, 200, True),
            ("上边中点手柄", 400, 200, True),
            ("右边中点手柄", 600, 350, True),
            ("右边框 y=1/4 处", 600, 275, False),
            ("右边框 y=3/4 处", 600, 425, False),
            ("下边框 x=1/4 处", 300, 500, False),
            ("右边框延长线下方", 600, 900, False),
            ("图层中心", 400, 350, False),
        ]
        for label, cx, cy, expect_handle in cases:
            got = canvas.handleAt(cx, cy)
            is_handle = got != ""
            check(f"{label} ({cx},{cy})", is_handle, expect_handle)

        print("\n=== 4. 边框线非手柄处点击应穿透到下层图层 ===")
        ws.newDocument(900, 600)
        ws.document.layers.clear()
        ws.document.add_layer("下层", 550, 300, 300, 250, is_folder=False)
        ws.document.add_layer("上层", 200, 200, 400, 300, is_folder=False)
        ws.layerModel.reset_from_document()
        ws.selectionChanged.emit()
        ws.requestPreview(force=True)
        QTest.qWait(200)
        upper = next(i for i, l in enumerate(ws.document.layers) if l.name == "上层")
        lower = next(i for i, l in enumerate(ws.document.layers) if l.name == "下层")
        ws.setZoomFactor(1.0)
        ws.selectLayer(upper)
        QTest.qWait(150)
        # 上层右边框 x=600，在下层覆盖范围内（下层 x=550..850 y=300..550）
        # 点 (600, 400)：在上层右边框上，但那里不是手柄（手柄在 y=350）
        click(600, 400)
        got = ws.selectedLayerIndex
        name = ws.document.layers[got].name if got >= 0 else None
        check(f"点上层右边框非手柄处 -> 应选下层", (got, name), (lower, "下层"))

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
