"""修复后总复测：四项指标一次性对比。"""
import os
import statistics
import sys
import tempfile
import threading
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


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def build(layer_count=8, canvas=(1080, 1350), with_alpha=True):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(*canvas)
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        img = Image.new("RGBA", (760, 560), (25 * i % 255, 90, 160, 255))
        if with_alpha:
            for x in range(0, 760, 32):
                for y in range(0, 560, 32):
                    img.putpixel((x, y), (0, 0, 0, 0))
        img.save(path)
        doc.add_layer(f"L{i}", 30 + i * 10, 40 + i * 10, 760, 560, image_source=path)
    return doc


print("=" * 72)
print("修复后四项指标（基线为 2026-11-02 修复前实测）")
print("=" * 72)

# --- 指标 1：真实拖动落地帧数
doc = build()
provider = PreviewImageProvider()
vm = WorkspaceViewModel(document=doc, preview_provider=provider, auto_render=True)
vm.selectLayer(len(doc.layers) - 1)
pump(1500)

stamps = []
vm.previewChanged.connect(lambda: stamps.append(time.perf_counter()))
frames = 30
t0 = time.perf_counter()
for i in range(frames):
    vm.previewLiveGeometry(30 + i * 5, 40, 760, 560)
    pump(16)
pump(1200)
gaps = [(stamps[i] - stamps[i - 1]) * 1000 for i in range(1, len(stamps))]
med_gap = statistics.median(gaps) if gaps else 0
print(f"\n[1] 拖动流畅度（8 层 1080×1350，请求 30 帧）")
print(f"    修复前: 落地  4 帧 / 帧间隔 55ms ≈ 18fps")
print(f"    修复后: 落地 {len(stamps):2d} 帧 / 帧间隔 {med_gap:.0f}ms ≈ {1000/med_gap:.0f}fps" if med_gap else "")

# --- 指标 2：纹理分辨率是否跳变
sizes = []
provider2 = PreviewImageProvider()
doc2 = build(layer_count=4)
vm2 = WorkspaceViewModel(document=doc2, preview_provider=provider2, auto_render=True)
vm2.selectLayer(len(doc2.layers) - 1)
pump(1500)
vm2.previewChanged.connect(lambda: sizes.append((provider2._image.width(), provider2._image.height())))
for i in range(6):
    vm2.previewLiveGeometry(30 + i * 6, 40, 760, 560)
    pump(16)
vm2.applySelectedGeometry(66, 40, 760, 560)
pump(1200)
uniq = []
for s in sizes:
    if not uniq or uniq[-1] != s:
        uniq.append(s)
print(f"\n[2] 一次拖动内纹理尺寸变化")
print(f"    修复前: [(960, 1200), (1080, 1350)]  → 变 1 次（闪一下）")
print(f"    修复后: {uniq}  → 变 {len(uniq)-1} 次")

# --- 指标 3：图层面板 reset 轮数
doc3 = build(layer_count=6)
vm3 = WorkspaceViewModel(document=doc3, preview_provider=PreviewImageProvider(), auto_render=False)
model = vm3._layer_model
cnt = {"reset": 0}
model.modelAboutToBeReset.connect(lambda: cnt.__setitem__("reset", cnt["reset"] + 1))
vm3.selectLayer(2)
cnt["reset"] = 0
vm3.moveSelectedLayer("forward")
print(f"\n[3] 一次图层排序的整表重建轮数")
print(f"    修复前: 2 轮（layer_changed + 显式 reset_from_document）")
print(f"    修复后: {cnt['reset']} 轮")

# --- 指标 4：导出期间主线程取锁等待
doc4 = build(layer_count=8)
ws4 = WorkspaceViewModel(document=doc4, preview_provider=PreviewImageProvider(), auto_render=False)
lock = ws4.documentLock
waits = []
stop = threading.Event()


def probe():
    while not stop.is_set():
        t = time.perf_counter()
        ok = lock.acquire(timeout=5.0)
        waits.append((time.perf_counter() - t) * 1000)
        if ok:
            lock.release()
        time.sleep(0.005)


def runner(clone, **kw):
    th = threading.Thread(target=probe, daemon=True)
    th.start()
    time.sleep(0.5)
    stop.set()
    th.join(3)
    return True


from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel

out = tempfile.mkdtemp()
bvm = BatchExportViewModel(workspace=ws4, runner=runner)
bvm.outputDirectory = out
bvm.count = 1
bvm.startExport()
deadline = time.monotonic() + 30
while bvm.running and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
app.processEvents()

print(f"\n[4] 导出期间主线程取文档锁")
print(f"    修复前: 持锁 1003ms，主线程阻塞 980ms（完全冻结）")
print(f"    修复后: {len(waits)} 次采样，最长等待 {max(waits):.1f}ms")

print("\n" + "=" * 72)
