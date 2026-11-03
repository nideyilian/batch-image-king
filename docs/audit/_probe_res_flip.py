"""验证闪烁：拖动过程中发布的画面分辨率是否在「交互档」和「全质量档」之间跳变。

如果每次暂停 >220ms 就补一帧 1080x1350 全质量，
下一次移动又回到 960x1200，画布纹理就在两个分辨率之间来回换 —— 视觉上就是「闪」。
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


def build(layer_count=8, canvas=(1080, 1350)):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(*canvas)
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        img = Image.new("RGBA", (760, 560), (25 * i % 255, 90, 160, 255))
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


doc = build()
provider = PreviewImageProvider()
vm = WorkspaceViewModel(document=doc, preview_provider=provider, auto_render=True)
vm.selectLayer(len(doc.layers) - 1)
pump(2000)
print(f"画布 {doc.canvas_width}x{doc.canvas_height}，{len(doc.layers)} 层\n")

published = []


def on_preview():
    img = provider._image
    published.append((img.width(), img.height()))


vm.previewChanged.connect(on_preview)

print("=== 模拟真实手感：拖动中带停顿（用户拖动不会匀速）===")
print("  节奏：移动 5 帧 -> 停顿 260ms -> 再移动 5 帧 -> 停顿 260ms ...\n")

for round_index in range(3):
    for i in range(5):
        vm.previewLiveGeometry(30 + round_index * 40 + i * 5, 40, 760, 560)
        pump(16)
    pump(260)  # 停顿超过 220ms 的 final 定时器

pump(1500)

print(f"共发布 {len(published)} 帧，分辨率序列：")
for i, size in enumerate(published):
    print(f"  #{i}: {size[0]}x{size[1]}")

sizes = {s for s in published}
print(f"\n出现了 {len(sizes)} 种分辨率: {sorted(sizes)}")
if len(sizes) > 1:
    seq = [s[0] for s in published]
    flips = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
    print(f"--> 分辨率切换 {flips} 次。画布纹理在两个尺寸间来回换 = 视觉上的「闪」")
else:
    print("--> 分辨率稳定")
