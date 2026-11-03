"""验证：交互帧改用 PIL BILINEAR 直缩后，透明边缘是否渗色（与 float 预乘版对比）。
只在比例真正小的时候才需要缩，所以测 0.3 / 0.5 / 0.75 三档。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageChops, ImageDraw

from app.utils.rgba_resampler import resize_rgba_premultiplied


def make_asset(w=760, h=560):
    """模拟真实素材：白底图形 + 半透明边缘 + 完全透明的角。
    透明区的 RGB 故意填成刺眼的黑（0,0,0），这样渗色会很明显。"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([80, 60, w - 80, h - 60], fill=(220, 60, 60, 255))
    d.rectangle([40, 40, w - 40, h - 40], outline=(30, 120, 200, 255), width=8)
    # 半透明覆盖层
    for i in range(0, w, 7):
        d.line([(i, 0), (i, h)], fill=(0, 0, 0, 0))
    return img


def edge_bleed_score(original, resized, scale):
    """把缩小结果放大回原尺寸，只比较"原图 alpha>200 的实心像素"区域，
    看颜色是否被透明区的黑色污染。"""
    back = resized.resize(original.size, Image.Resampling.BILINEAR)
    a = original.getchannel("A")
    solid = a.point(lambda v: 255 if v > 200 else 0)
    diff = ImageChops.difference(back.convert("RGB"), original.convert("RGB"))
    # 只在实心区域统计
    masked = Image.composite(diff, Image.new("RGB", diff.size, (0, 0, 0)), solid)
    stat = masked.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    return sum(stat) / 3


src = make_asset()
print(f"测试素材 {src.size}，透明角 RGB=(0,0,0) alpha=0\n")
print(f"{'缩放比':<8}{'float 预乘(ms 级)':<22}{'PIL BILINEAR':<20}{'渗色差(PIL)':<14}")
print("-" * 66)

import time

for scale in (0.3, 0.5, 0.75, 0.889):
    target = (int(src.width * scale), int(src.height * scale))
    n = 12

    t = time.perf_counter()
    for _ in range(n):
        a = resize_rgba_premultiplied(src, target, Image.Resampling.BILINEAR)
    t_float = (time.perf_counter() - t) / n * 1000

    t = time.perf_counter()
    for _ in range(n):
        b = src.resize(target, Image.Resampling.BILINEAR)
    t_pil = (time.perf_counter() - t) / n * 1000

    bleed = edge_bleed_score(src, b, scale)
    print(f"{scale:<8.3f}{t_float:>16.1f} ms      {t_pil:>12.1f} ms      {bleed:>10.1f}/255")
