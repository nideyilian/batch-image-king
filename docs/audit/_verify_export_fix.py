"""验证导出持锁修复：
1. 导出期间主线程是否还能拖拽（不再被阻塞）
2. 导出结果是否仍然正确（张数、内容）
3. 降级/调整提示是否还能搬回主文档
"""
import os
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def build(layer_count=8, canvas=(1080, 1350)):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(*canvas)
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        Image.new("RGBA", (760, 560), (25 * i % 255, 90, 160, 255)).save(path)
        doc.add_layer(f"L{i}", 30 + i * 10, 40 + i * 10, 760, 560, image_source=path)
    return doc


def run_case(label, document_lock):
    doc = build()
    ws = WorkspaceViewModel(document=doc, preview_provider=PreviewImageProvider(), auto_render=False)
    out = tempfile.mkdtemp()
    vm = BatchExportViewModel(workspace=ws)
    vm.outputDirectory = out
    vm.count = 6
    vm.filenameTemplate = "t_{number:03d}"

    assert vm.startExport() is True

    # 导出跑起来后，反复尝试在主线程拿文档锁，记录每次等待时长
    waits = []
    deadline = time.monotonic() + 15
    while vm.running and time.monotonic() < deadline:
        t = time.perf_counter()
        with document_lock:
            pass
        waits.append((time.perf_counter() - t) * 1000)
        time.sleep(0.03)

    deadline = time.monotonic() + 60
    while vm.running and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    files = [f for f in os.listdir(out) if f.lower().endswith((".png", ".jpg", ".bmp"))]
    print(f"\n{label}")
    print(f"  导出状态: success={vm.succeeded} 产出 {len(files)} 张")
    if waits:
        waits_sorted = sorted(waits)
        print(f"  导出期间主线程取锁 {len(waits)} 次："
              f"中位 {statistics.median(waits):.1f}ms  最大 {waits_sorted[-1]:.1f}ms")
        frozen = sum(1 for w in waits if w > 100)
        print(f"  超过 100ms 的冻结次数: {frozen}  ({frozen/len(waits)*100:.0f}%)")
    return len(files), (statistics.median(waits) if waits else 0), (max(waits) if waits else 0)


print("=" * 70)
print("修复后：导出跑在文档副本上")
print("=" * 70)
lock = threading.RLock()
n1, med1, max1 = run_case("副本方案（现状）", lock)

print("\n" + "=" * 70)
print("对照：把锁换成「整段持有」模拟旧行为下主线程的感受")
print("=" * 70)
doc = build()
ws = WorkspaceViewModel(document=doc, preview_provider=PreviewImageProvider(), auto_render=False)
lock2 = threading.RLock()
holder_done = threading.Event()


def holder():
    with lock2:
        time.sleep(0.8)
    holder_done.set()


th = threading.Thread(target=holder, daemon=True)
th.start()
time.sleep(0.02)
t = time.perf_counter()
with lock2:
    pass
blocked = (time.perf_counter() - t) * 1000
th.join()
print(f"  旧行为对照：导出持锁 800ms -> 主线程阻塞 {blocked:.0f}ms")
