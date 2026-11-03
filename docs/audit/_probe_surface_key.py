"""验证：拖动时图层 surface 缓存是否每帧失效。

_build_layer_surface_key 含 f"size:{width}x{height}"。
移动模式下 width/height 不变，理论上应命中；
但 previewLiveGeometry 每帧无条件写入 x/y/width/height 四个属性。
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.utils.fast_renderer import get_global_fast_renderer
from app.services.preview_render_service import render_preview_to_image

tmp = tempfile.mkdtemp()
doc = Document()
doc.create_new(1080, 1350)
for i in range(8):
    path = os.path.join(tmp, f"img_{i}.png")
    Image.new("RGBA", (760, 560), (25 * i % 255, 90, 160, 255)).save(path)
    doc.add_layer(f"L{i}", 30 + i * 10, 40 + i * 10, 760, 560, image_source=path)

r = get_global_fast_renderer()
active = doc.layers[-1]

print("=== 场景 1：移动图层（只改 x/y，width/height 不变）===")
render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True, active_layer_index=7)
k0 = r._build_layer_surface_key(active, doc)
for step in range(5):
    active.x = 30 + step * 10
    k = r._build_layer_surface_key(active, doc)
    print(f"  step{step} x={active.x:<4} surface_key 变化={k != k0}  ({k[:8]})")
    k0 = k

print("\n=== 场景 2：每帧无条件重写 width/height 为同值（previewLiveGeometry 的写法）===")
k0 = r._build_layer_surface_key(active, doc)
for step in range(5):
    # 模拟 previewLiveGeometry: layer.width = max(1, int(round(target_w)))
    active.width = 760
    active.height = 560
    k = r._build_layer_surface_key(active, doc)
    print(f"  step{step} width={active.width} surface_key 变化={k != k0}  ({k[:8]})")
    k0 = k

print("\n=== 场景 3：真的每帧缩放（拖角手柄）===")
render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True, active_layer_index=7)
k0 = r._build_layer_surface_key(active, doc)
total = 0.0
for step in range(5):
    active.width = 760 + step * 8
    active.height = 560 + step * 6
    t = time.perf_counter()
    render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True, active_layer_index=7)
    dt = (time.perf_counter() - t) * 1000
    total += dt
    k = r._build_layer_surface_key(active, doc)
    print(f"  step{step} {active.width}x{active.height}  key变化={k != k0}  渲染={dt:7.1f}ms")
    k0 = k
print(f"  平均 {total/5:.1f} ms/帧")

print("\n=== 场景 4：拖角时若用固定 surface（不随尺寸变）===")
active.width = 760
active.height = 560
render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True, active_layer_index=7)
total = 0.0
for step in range(5):
    t = time.perf_counter()
    render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True, active_layer_index=7)
    total += (time.perf_counter() - t) * 1000
print(f"  同尺寸重复渲染平均 {total/5:.1f} ms/帧（surface 命中）")
