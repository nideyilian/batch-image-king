# -*- coding: utf-8 -*-
"""探针：拖动一帧的主线程开销拆解。

拖动时每帧会依次发生：
  1. QML updateTransform（纯算术，应该 <0.1ms）
  2. workspace.selectLayer / applySelectedGeometry -> _set_layer_attrs -> save_state
  3. requestPreview -> 定时器
  4. 后台渲染完成 -> _on_preview_rendered -> set_image + previewChanged

如果卡顿，要么是主线程某段同步耗时，要么是后台渲染频率高于渲染能力（排队积压）。
本探针把这几段分别计时。
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def build(layer_count: int, canvas: int = 2400, layer_w: int = 1600, layer_h: int = 1200):
    document = Document()
    document.create_new(canvas, canvas)
    for i in range(layer_count):
        document.add_layer(f"图层{i}", 40 + i * 20, 40 + i * 20, layer_w, layer_h, is_folder=False)
    vm = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,          # 关掉预览，先测纯几何/历史开销
    )
    vm.selectLayer(0)
    return document, vm


def timeit(label: str, fn, n: int = 60) -> float:
    # 预热
    for _ in range(3):
        fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    dt = (time.perf_counter() - t0) / n * 1000
    print(f"  {label:<46} {dt:8.3f} ms")
    return dt


print("=" * 70)
print("A. 单图层移动：每帧主线程开销（auto_render=False，排除预览）")
print("=" * 70)
for count in (1, 10, 40):
    document, vm = build(count)
    print(f"\n{count} 个图层（每个 {1600}x{1200}，画布 2400x2400）")
    i = [0]

    def move():
        i[0] += 1
        vm.applySelectedGeometry(40 + i[0] % 50, 40, 1600, 1200)

    timeit("applySelectedGeometry（含序列化快照）", move)


print()
print("=" * 70)
print("B. 拆开：serialize 快照 vs 属性写入")
print("=" * 70)
for count in (1, 10, 40):
    document, vm = build(count)
    print(f"\n{count} 个图层")
    timeit("document.save_state（整文档序列化）", lambda d=document: d.save_state("t"), n=40)
    timeit(
        "DocumentSerializer.serialize_document_data",
        lambda d=document: __import__(
            "app.models.document_serializer", fromlist=["x"]
        ).DocumentSerializer.serialize_document_data(d),
        n=40,
    )


print()
print("=" * 70)
print("C. 预览请求本身（auto_render=True，只测入队开销）")
print("=" * 70)
document, vm = build(10)
vm._auto_render = True
timeit("requestPreview 入队", lambda v=vm: v.requestPreview(True), n=200)


print()
print("=" * 70)
print("D. 真实同步预览渲染耗时（决定后台是否跟得上）")
print("=" * 70)
from app.services.preview_render_service import render_preview_to_image

for count in (1, 10):
    document, vm = build(count)
    for quality in ("interactive", "final"):
        if quality == "interactive":
            t0 = time.perf_counter()
            r = render_preview_to_image(
                document, force_refresh=False, interactive_low_quality=True
            )
            dt = (time.perf_counter() - t0) * 1000
        else:
            t0 = time.perf_counter()
            r = render_preview_to_image(document, force_refresh=True, interactive_low_quality=False)
            dt = (time.perf_counter() - t0) * 1000
        size = r.image.size if r.image else None
        print(f"  {count} 图层 {quality:<12} {dt:8.1f} ms  输出={size}")
