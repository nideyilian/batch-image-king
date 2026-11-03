"""验证「拖动一下就闪一下」：起手与松手瞬间画布纹理分辨率发生跳变。

拖动中只发 interactive 帧 (960x1200)，
松手后 applySelectedGeometry -> requestPreview(force=True) -> 220ms 后 final 帧 (1080x1350)。
每拖一下，纹理就在两个分辨率之间切换一次。
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


def build(layer_count=4, canvas=(1080, 1350)):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(*canvas)
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        Image.new("RGBA", (760, 560), (25 * i % 255, 90, 160, 255)).save(path)
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

sizes = []
vm.previewChanged.connect(lambda: sizes.append((provider._image.width(), provider._image.height())))

print(f"画布 {doc.canvas_width}x{doc.canvas_height}\n")
print("=== 走一次完整拖动手势：起手 -> 移动 -> 松手 ===")

# 起手
sizes.clear()
for i in range(6):
    vm.previewLiveGeometry(30 + i * 6, 40, 760, 560)
    pump(16)
pump(100)

# 松手：完全走 QML commitTransform 的路径
vm.applySelectedGeometry(66, 40, 760, 560)
pump(1200)

print("发布的帧序列（拖动中 -> 松手后）：")
for i, s in enumerate(sizes):
    tag = "  <- 松手后补的全质量帧" if i == len(sizes) - 1 and i > 0 else ""
    print(f"  #{i}: {s[0]}x{s[1]}{tag}")

uniq = []
for s in sizes:
    if not uniq or uniq[-1] != s:
        uniq.append(s)
print(f"\n按顺序去重后的尺寸变化: {uniq}")
if len(uniq) > 1:
    ratio = uniq[-1][1] / uniq[0][1]
    print(f"--> 一次拖动内纹理尺寸变了 {len(uniq)-1} 次（{uniq[0][1]}px -> {uniq[-1][1]}px，{ratio:.2f}x）")
    print("    QML Image 会重新上传纹理并按新尺寸重采样 -> 视觉上就是「闪一下」")

print("\n=== 连拖 3 次，数一共闪几下 ===")
flashes = 0
for k in range(3):
    before = sizes[-1] if sizes else None
    vm.previewLiveGeometry(70 + k * 20, 40, 760, 560)
    pump(16)
    vm.applySelectedGeometry(70 + k * 20, 40, 760, 560)
    pump(1000)
    if sizes and before and sizes[-1] != before:
        flashes += 1
        print(f"  第 {k+1} 次拖动：尺寸 {before} -> {sizes[-1]}  闪")
    elif sizes:
        print(f"  第 {k+1} 次拖动：尺寸 {sizes[-1]} 未变")
print(f"\n--> 3 次拖动共闪 {flashes} 次")
