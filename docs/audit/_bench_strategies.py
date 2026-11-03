"""对比三种交互帧策略的真实开销和质量，选定修复方案。

A. 现状：render_scale=0.8889 + 逐层 float 预乘重采样
B. 交互帧不做降采样（render_scale=1.0），层 surface 直接用缓存
C. 交互帧真正降采样（MAX_EDGE=720）+ PIL 快速重采样
"""
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageChops
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.utils import fast_renderer_preview as frp


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


def bench(label, fn, n=8):
    for _ in range(2):
        fn()
    out = []
    for _ in range(n):
        t = time.perf_counter()
        r = fn()
        out.append((time.perf_counter() - t) * 1000)
    s = sorted(out)
    print(f"  {label:<50} median={statistics.median(s):7.2f}ms")
    return r, statistics.median(s)


doc = build()
from app.services.preview_render_service import render_preview_to_image

print("=== 三种交互帧策略（8 层真实素材 1080x1350）===")
ref = render_preview_to_image(doc, force_refresh=True)
print(f"  参考 final 尺寸: {ref.image.size if ref.image else None}")

a_img, a_ms = bench("A 现状 (render_scale=0.889 + float 预乘)", lambda: render_preview_to_image(
    doc, force_refresh=True, interactive_low_quality=True))

# B: 交互帧不降采样
orig_scale = frp.FastRendererPreview._get_interactive_render_scale
frp.FastRendererPreview._get_interactive_render_scale = lambda self, d, p, l: 1.0
b_img, b_ms = bench("B 交互帧不降采样 (render_scale=1.0)", lambda: render_preview_to_image(
    doc, force_refresh=True, interactive_low_quality=True))
frp.FastRendererPreview._get_interactive_render_scale = orig_scale

# C: 真降采样 + PIL 快速重采样
orig_limit = frp._INTERACTIVE_PREVIEW_MAX_EDGE
frp._INTERACTIVE_PREVIEW_MAX_EDGE = 720
orig_fast = frp.FastRendererPreview._scale_layer_for_interactive_preview


def fast_resize(self, image, render_scale):
    if image is None or render_scale >= 0.999:
        return image
    target = (max(1, int(round(image.width * render_scale))),
              max(1, int(round(image.height * render_scale))))
    if target == image.size:
        return image
    return image.resize(target, Image.Resampling.BILINEAR)


frp.FastRendererPreview._scale_layer_for_interactive_preview = fast_resize
c_img, c_ms = bench("C 真降采样 720 + PIL BILINEAR", lambda: render_preview_to_image(
    doc, force_refresh=True, interactive_low_quality=True))
frp._INTERACTIVE_PREVIEW_MAX_EDGE = orig_limit
frp.FastRendererPreview._scale_layer_for_interactive_preview = orig_fast

print("\n=== 输出尺寸与相对 final 的视觉误差（越小越好）===")


def diff_vs_final(img):
    """把结果缩回 final 尺寸后对比平均像素差。"""
    if img is None or ref.image is None:
        return "n/a"
    up = img.convert("RGBA").resize(ref.image.size, Image.Resampling.BILINEAR)
    d = ImageChops.difference(up.convert("RGB"), ref.image.convert("RGB"))
    stat = d.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    return f"平均差 {sum(stat)/3:.1f}/255"


for name, img, ms in (("A 现状", a_img.image, a_ms),
                      ("B 不降采样", b_img.image, b_ms),
                      ("C 真降采样720", c_img.image, c_ms)):
    size = img.size if img is not None else None
    print(f"  {name:<14} 输出={str(size):<14} {ms:7.1f}ms  {diff_vs_final(img)}")
