# -*- coding: utf-8 -*-
"""探针：拖动过程中画面是否跟随。

这是「卡顿感」最可能的来源：如果拖动时预览图不刷新、只有选框在动，
松手才一次性跳到位，主观感受就是卡。真正的耗时数字反而看不出来。
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

        def check(label, got, expect):
            nonlocal ok, fail
            good = got == expect
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
            print(f"  {'OK  ' if good else 'FAIL'} {label}: {got!r} 期望={expect!r}")

        ws.newDocument(900, 600)
        ws.document.layers.clear()
        ws.document.add_layer("图层", 200, 200, 400, 300, is_folder=False)
        ws.layerModel.reset_from_document()
        ws.selectionChanged.emit()
        ws.setZoomFactor(1.0)
        ws.selectLayer(0)
        QTest.qWait(400)

        rev_log = []
        ws.previewChanged.connect(lambda: rev_log.append(ws.property("previewRevision")))
        print("=== 拖动过程中：预览修订号是否在变（画面是否跟随）===")
        rev0 = ws.previewRevision if hasattr(ws, "previewRevision") else None
        if rev0 is None:
            # 找属性名
            for name in ("previewRevision", "previewRevisionNumber"):
                v = ws.property(name)
                if v is not None:
                    rev0 = v
                    break
        print(f"  拖动前 previewRevision={rev0}")

        start = scene_of(400, 350)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        revs = []
        for i in range(1, 9):
            mid = QPoint(start.x() + i * 12, start.y() + i * 9)
            QTest.mouseMove(window, mid)
            QTest.qWait(60)
            revs.append(ws.property("previewRevision"))
        print(f"  拖动中 previewRevision 序列: {revs}")
        moved_during = len(set(revs)) > 1
        check("拖动中画面有更新", moved_during, True)

        # 拖动中 transient 是否跟随
        tx = canvas.property("transientX")
        sx = ws.selectedX
        print(f"  拖动中 transientX={tx} selectedX={sx}")
        # 拖动中实时把几何写进了图层，所以两者应当一致（选框和画面都跟手）。
        # 若两者相差很大，说明实时预览没接上。
        check("拖动中 选框与图层同步", abs(float(tx) - float(sx)) <= 2, True)

        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier,
                           QPoint(start.x() + 8 * 12, start.y() + 8 * 9))
        QTest.qWait(500)
        rev_after = ws.property("previewRevision")
        print(f"  松开后 previewRevision={rev_after}")
        print(f"  previewChanged 触发记录: {rev_log}")
        print(f"  (_render_running={getattr(ws,'_render_running',None)}"
              f" pending={getattr(ws,'_render_pending',None)})")
        check("松开后画面更新", rev_after != rev0, True)

        print("\n=== 拖动中图层属性是否已变（还是等松手才变）===")
        layer = ws.document.layers[0]
        print(f"  松开后图层位置: ({layer.x}, {layer.y})")
        print(f"  auto_render={ws.property('autoRender') if ws.property('autoRender') is not None else 'n/a'}")
        print(f"  _auto_render={getattr(ws, '_auto_render', 'n/a')}")
        print(f"  _render_running={getattr(ws, '_render_running', 'n/a')}"
              f"  _render_pending={getattr(ws, '_render_pending', 'n/a')}"
              f"  _preview_generation={getattr(ws, '_preview_generation', 'n/a')}"
              f"  _render_request_id={getattr(ws, '_render_request_id', 'n/a')}")
        print(f"  previewSource={ws.property('previewSource')!r}")
        # 手动触发一次，看能不能刷新
        rev_before_manual = ws.property("previewRevision")
        ws.renderPreviewNow()
        QTest.qWait(900)
        print(f"  手动 renderPreviewNow: {rev_before_manual} -> {ws.property('previewRevision')}")

        from PySide6.QtCore import QThreadPool
        pool = QThreadPool.globalInstance()
        print(f"  线程池: max={pool.maxThreadCount()} active={pool.activeThreadCount()}"
              f" (这个任务还在排队的可能性)")
        print(f"  _active_render_task={getattr(ws, '_active_render_task', None)}")
        task = getattr(ws, "_active_render_task", None)
        if task is not None:
            tok = getattr(task, "cancel_token", None)
            print(f"    任务 cancel_token.cancelled={getattr(tok, 'cancelled', 'n/a')}")

        # 卡住时把所有线程的栈打出来，看后台渲染线程在哪
        import traceback, sys as _sys, threading
        frames = _sys._current_frames()
        names = {t.ident: t.name for t in threading.enumerate()}
        print("\n  === 卡住时的线程栈 ===")
        for ident, frame in frames.items():
            name = names.get(ident, str(ident))
            stack = traceback.format_stack(frame)
            joined = "".join(stack)
            interesting = any(k in joined for k in ("app/", "app\\", "fast_renderer", "PIL/", "PIL\\"))
            if interesting or name in ("Dummy-1", "MainThread"):
                print(f"  --- {name} ---")
                print("".join(stack[-14:]))

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
