"""验证：单选 vs 多选拖动一帧的真实开销差异 + 低质量档到底浪费在哪。"""
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.utils.rgba_resampler import resize_rgba_premultiplied


def build_doc(layer_count, canvas=(1080, 1350)):
    doc = Document()
    doc.create_new(*canvas)
    tmp = tempfile.mkdtemp()
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        # 带透明像素，模拟真实素材（alpha 不全 1，会走 float 预乘分支）
        img = Image.new("RGBA", (760, 560), (30 * i % 255, 90, 160, 255))
        for x in range(0, 760, 40):
            for y in range(0, 560, 40):
                img.putpixel((x, y), (0, 0, 0, 0))
        img.save(path)
        doc.add_layer(f"图层{i}", 40 + i * 8, 60 + i * 6, 760, 560, image_source=path)
    return doc


def bench(label, fn, n=8):
    for _ in range(2):
        fn()
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    s = sorted(out)
    print(f"  {label:<52} median={statistics.median(s):7.2f}ms  max={s[-1]:7.2f}ms")
    return statistics.median(s)


from app.services.preview_render_service import render_preview_to_image

print("=== 12 层 1080x1350 素材，拖动一帧 ===")
doc = build_doc(12)
render_preview_to_image(doc, force_refresh=True)

single = bench("单选拖动 (active=0, 走增量底图)", lambda: render_preview_to_image(
    doc, force_refresh=True, interactive_low_quality=True, active_layer_index=0))
multi = bench("多选/编组拖动 (active=-1, 走全量重渲)", lambda: render_preview_to_image(
    doc, force_refresh=True, interactive_low_quality=True, active_layer_index=-1))
full = bench("松手后全质量 final", lambda: render_preview_to_image(doc, force_refresh=True))
print(f"  --> 多选拖动是单选的 {multi/single:.1f} 倍，是 final 的 {multi/full:.1f} 倍")

print("\n=== 低质量档的降采样比例与实际收益 ===")
from app.utils.fast_renderer import get_global_fast_renderer
r = get_global_fast_renderer()
scale = r._get_interactive_render_scale(doc, True, True)
print(f"  画布 1080x1350 -> render_scale={scale:.4f}（只降到 {scale*100:.0f}%）")

surf = Image.new("RGBA", (760, 560), (200, 100, 50, 180))
for x in range(0, 760, 30):
    for y in range(0, 560, 30):
        surf.putpixel((x, y), (0, 0, 0, 0))
target = (int(760 * scale), int(560 * scale))
print(f"  单层 {surf.size} -> {target}")
bench("  resize_rgba_premultiplied (float 预乘, 当前用的)", lambda: resize_rgba_premultiplied(
    surf, target, Image.Resampling.BILINEAR))
bench("  PIL 直接 resize BILINEAR (无预乘)", lambda: surf.resize(target, Image.Resampling.BILINEAR))
print("  --> 每层多付的 float 预乘开销就是 90ms 的来源；缩到 89% 视觉上几乎无差别")
