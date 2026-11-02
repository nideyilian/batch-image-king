# -*- coding: utf-8 -*-
"""探针：拖动时的真实出帧节奏（不含任何会干扰渲染循环的调用）。

之前两次测量自相矛盾，原因记下来避免重踩：
  1. ``grabWindow()`` 会同步阻塞 QML 渲染循环，测出来的 120ms 主要是它自己。
  2. 在循环里用 lambda 捕获 ``ws.previewRevision``，读到的是调用时刻的值，
     导致「帧间隔」算成了 0 或负数。

这次只用「记录时间戳」这一件事，不读属性、不抓窗口。
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QGuiApplication

app = QGuiApplication.instance() or QGuiApplication([])

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def measure(canvas: int, layers: int, frames: int = 20, wait_ms: int = 10):
    document = Document()
    document.create_new(canvas, canvas)
    for i in range(layers):
        document.add_layer(
            f"L{i}", 150 + i * 50, 150 + i * 30, canvas // 2, canvas // 3, is_folder=False
        )
    vm = WorkspaceViewModel(
        document=document, preview_provider=PreviewImageProvider(), auto_render=True
    )
    vm.selectLayer(layers - 1)
    pump(600)

    stamps = []
    # 只记录时间戳，不在回调里读任何属性
    vm.previewChanged.connect(lambda: stamps.append(time.perf_counter()))

    t_start = time.perf_counter()
    for i in range(frames):
        vm.previewLiveGeometry(150 + i * 6, 150, canvas // 2, canvas // 3)
        pump(wait_ms)
    pump(500)
    total = (time.perf_counter() - t_start) * 1000

    # 去掉最后 wait 阶段补出来的帧，只统计拖动期间
    during = [t for t in stamps if t <= t_start + frames * wait_ms / 1000 + 0.05]
    gaps = [(during[i] - during[i - 1]) * 1000 for i in range(1, len(during))] if len(during) > 1 else []
    return {
        "requested": frames,
        "produced": len(during),
        "total_ms": total,
        "median_gap": sorted(gaps)[len(gaps) // 2] if gaps else None,
        "max_gap": max(gaps) if gaps else None,
    }


print(f"{'画布':<12}{'图层':<6}{'请求帧':<8}{'出图':<6}{'帧间隔中位':<12}{'最大':<10}")
print("-" * 60)
ok = True
for canvas, layers in ((1200, 1), (1600, 3), (2400, 6), (3000, 10)):
    r = measure(canvas, layers)
    med = f"{r['median_gap']:.1f} ms" if r["median_gap"] else "n/a"
    mx = f"{r['max_gap']:.1f} ms" if r["max_gap"] else "n/a"
    print(f"{canvas}x{canvas:<6}{layers:<6}{r['requested']:<8}{r['produced']:<6}{med:<12}{mx:<10}")
    # 判定：出图数应接近请求数；帧间隔应远小于 100ms
    if r["produced"] < r["requested"] * 0.6:
        print(f"    !! 出图率过低 {r['produced']}/{r['requested']}")
        ok = False
    if r["median_gap"] and r["median_gap"] > 50:
        print(f"    !! 帧间隔过大 {r['median_gap']:.1f} ms")
        ok = False

print()
print("结论:", "通过" if ok else "存在问题")
os._exit(0 if ok else 1)
