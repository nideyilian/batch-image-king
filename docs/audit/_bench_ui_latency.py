"""临时基准：量化拖动/操作时主线程上的开销。只读，不改代码。"""
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
        doc.add_layer(f"图层{i}", 40 + i*8, 60 + i*6, 600 + i*10, 400 + i*10, image_source=path)
    return doc


def timeit(fn, n=30):
    samples = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    return samples


def report(name, samples):
    samples = sorted(samples)
    print(
        f"{name:<46} n={len(samples):<3} "
        f"median={statistics.median(samples):7.2f}ms  "
        f"p90={samples[int(len(samples)*0.9)]:7.2f}ms  "
        f"max={samples[-1]:7.2f}ms"
    )


doc = build_doc()
print(f"图层数={len(doc.layers)}  画布={doc.canvas_width}x{doc.canvas_height}")

# 1) 历史快照（_set_layer_attrs / _finish_arrangement 每次操作都会走）
report("document.save_state()", timeit(lambda: doc.save_state("基准")))

# 2) 历史快照带上 coalesce_key（拖滑块/拖拽路径）
report("document.save_state(coalesce)", timeit(lambda: doc.save_state("基准", coalesce_key="layer0:x,y")))

# 3) 文档序列化（预览快照路径）
from app.models.document_serializer import DocumentSerializer
report("DocumentSerializer.serialize_document_data", timeit(lambda: DocumentSerializer.serialize_document_data(doc), 5))

# 4) 预览渲染各档
from app.services.preview_render_service import render_preview_to_image
render_preview_to_image(doc, force_refresh=True)
report("render_preview_to_image(final, force)", timeit(lambda: render_preview_to_image(doc, force_refresh=True), 10))
report("render_preview_to_image(interactive, force)", timeit(
    lambda: render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True), 10))
report("render_preview_to_image(interactive, active=0)", timeit(
    lambda: render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True,
                                    active_layer_index=0), 10))

# 5) PIL -> QImage 转换
from app.qml.viewmodels.workspace_vm_shared import _pil_to_qimage
img = Image.new("RGBA", (1080, 1350), (10, 20, 30, 255))
report("_pil_to_qimage(1080x1350)", timeit(lambda: _pil_to_qimage(img), 20))

# 6) 视图模型：几何写入 + 请求预览（不真渲染，只测主线程路径）
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
vm = WorkspaceViewModel()
vm.setDocument(doc) if hasattr(vm, "setDocument") else None
print("vm.document layers:", len(getattr(vm._document, "layers", []) or []))
