"""模拟真实拖动：真实素材 + 真实事件循环，数一数 30 次请求落地了几帧。

对照两组：
  A. 现状（interactive 帧把每层做 float 预乘重采样）
  B. 跳过该重采样（render_scale 直接当 1.0）
"""
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

LOADED_IMAGES = True


def build(layer_count=8, canvas=(1080, 1350)):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(*canvas)
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        img = Image.new("RGBA", (760, 560), (25 * i % 255, 90, 160, 255))
        # 真实素材有透明边缘
        for x in range(0, 760, 32):
            for y in range(0, 560, 32):
                img.putpixel((x, y), (0, 0, 0, 0))
        img.save(path)
        doc.add_layer(f"L{i}", 30 + i * 10, 40 + i * 10, 760, 560, image_source=path)
    return doc


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def drag_probe(label, frames=30):
    doc = build()
    vm = WorkspaceViewModel(document=doc, preview_provider=PreviewImageProvider(), auto_render=True)
    vm.selectLayer(len(doc.layers) - 1)
    pump(1500)  # 等首帧

    stamps = []
    vm.previewChanged.connect(lambda: stamps.append(time.perf_counter()))

    t0 = time.perf_counter()
    for i in range(frames):
        vm.previewLiveGeometry(30 + i * 5, 40, 760, 560)
        pump(16)  # 60fps 的鼠标节奏
    during = time.perf_counter() - t0
    pump(1500)  # 松手后补全
    total = len(stamps)
    gaps = [(stamps[i] - stamps[i - 1]) * 1000 for i in range(1, total)]

    print(f"\n{label}")
    print(f"  拖动时长 {during*1000:.0f}ms，请求 {frames} 帧，实际落地 {total} 帧")
    if gaps:
        print(f"  帧间隔 中位={statistics.median(gaps):7.0f}ms  最大={max(gaps):7.0f}ms"
              f"  -> 约 {1000/statistics.median(gaps):.1f} fps")
    print(f"  --> {'画面跟不上手（感知为卡顿/跳帧）' if total < frames * 0.6 else '跟上手了'}")
    return total, (statistics.median(gaps) if gaps else None)


# A. 现状
a_total, a_gap = drag_probe("A. 现状：拖 30 帧（8 层真实素材，1080x1350）")

# B. 旁路掉每层 float 预乘重采样
from app.utils import fast_renderer_preview as frp
original = frp.FastRendererPreview._scale_layer_for_interactive_preview


def patched(self, image, render_scale):
    # 模拟修复：交互帧直接复用原尺寸 surface，不再逐层重采样
    return image


frp.FastRendererPreview._scale_layer_for_interactive_preview = patched
b_total, b_gap = drag_probe("B. 跳过逐层 float 预乘重采样后")

frp.FastRendererPreview._scale_layer_for_interactive_preview = original

print("\n=== 对比 ===")
print(f"  落地帧数：{a_total} -> {b_total}")
if a_gap and b_gap:
    print(f"  帧间隔中位：{a_gap:.0f}ms -> {b_gap:.0f}ms（{a_gap/b_gap:.1f}x）")
