"""临时基准 2：定位 interactive 比 final 慢 2 倍的根因 + 拖动真实路径开销。"""
import os
import statistics
import sys
import time
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document


def build_doc(layer_count=12, canvas=(1080, 1350)):
    doc = Document()
    doc.create_new(*canvas)
    tmp = tempfile.mkdtemp()
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        Image.new("RGBA", (600 + i * 10, 400 + i * 10), (30 * i % 255, 90, 160, 255)).save(path)
        doc.add_layer(f"图层{i}", 40 + i * 8, 60 + i * 6, 600 + i * 10, 400 + i * 10, image_source=path)
    return doc


def timeit(fn, n=15):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        r = fn()
        out.append((time.perf_counter() - t) * 1000)
    return out, r


def report(name, samples):
    s = sorted(samples)
    print(f"{name:<52} median={statistics.median(s):7.2f}ms  max={s[-1]:7.2f}ms")


doc = build_doc()
from app.services.preview_render_service import render_preview_to_image

print(f"图层={len(doc.layers)} 画布={doc.canvas_width}x{doc.canvas_height}\n")

# 预热：把智能缓存和图层 surface 都填上
render_preview_to_image(doc, force_refresh=True)
render_preview_to_image(doc, force_refresh=False)

print("=== 稳态（不强制刷新，模拟连续操作）===")
s, _ = timeit(lambda: render_preview_to_image(doc, force_refresh=False))
report("final  (force=False)", s)
s, _ = timeit(lambda: render_preview_to_image(doc, force_refresh=False, interactive_low_quality=True))
report("interactive, active=-1 (force=False)", s)
s, _ = timeit(lambda: render_preview_to_image(doc, force_refresh=False, interactive_low_quality=True, active_layer_index=0))
report("interactive, active=0  (force=False)  <- 拖动走这条", s)
s, _ = timeit(lambda: render_preview_to_image(doc, force_refresh=False, interactive_low_quality=False, active_layer_index=0))
report("final, active=0 (force=False)", s)
s, _ = timeit(lambda: render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True, active_layer_index=0))
report("interactive, active=0  (force=True)", s)

print("\n=== low_quality_preview 到底降到多少分辨率 ===")
from app.utils.fast_renderer import get_global_fast_renderer
r = get_global_fast_renderer()
for mode in (("final", False), ("interactive", True)):
    img = r._fast_render(doc, preview_mode=True, was_just_loaded=False, low_quality_preview=mode[1])
    print(f"  low_quality={mode[0]:<12} -> {img.size if img else None}")

print("\n=== 拖动一帧的完整主线程开销（含 PIL->QImage + 发布）===")
from app.qml.viewmodels.workspace_vm_shared import _pil_to_qimage
img = r._fast_render(doc, preview_mode=True, was_just_loaded=False, low_quality_preview=True)
s, _ = timeit(lambda: _pil_to_qimage(img), 20)
report("_pil_to_qimage", s)

print("\n=== 预览串行锁：导出/缩略图是否会阻塞拖动 ===")
print("  _preview_render_lock:", type(r._preview_render_lock).__name__,
      "已上锁方式:", "全局唯一实例" if True else "")
