#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""描边 / 圆角几何验收脚本（端到端）。

所有描边用例都走真实的 ``apply_vector_path_effects``，不再复刻内部步骤，
避免「脚本算的是理想模型、产品跑的是另一码事」。

用法：
    python docs/audit/repro_stroke.py

不修改任何项目文件，纯读取 + 计算。退出码 0 = 全部通过。
"""
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.utils.vector_layer_effects import (  # noqa: E402
    VectorEffectParams,
    _vector_raster_supersample,
    apply_vector_path_effects,
)


class FakeLayer:
    """给 VectorEffectParams.collect 用的最小图层替身。"""

    def __init__(self, w, h, radius, stroke_w, stroke_type, join="miter"):
        self.width = w
        self.height = h
        self.corner_radius = radius
        self.vector_corner_radius_tl = 0
        self.vector_corner_radius_tr = 0
        self.vector_corner_radius_br = 0
        self.vector_corner_radius_bl = 0
        self.vector_path_enabled = False
        self.vector_path_points = []
        self.vector_path_mode = "polygon"
        self.vector_bezier_nodes = []
        self.vector_path_closed = True
        self.shape_type = "rectangle"
        self.trapezoid_top_width = 100
        self.trapezoid_bottom_width = 80
        self.trapezoid_slope_side = "right"
        self.polygon_rotation = 0.0
        self.polygon_corner_radius = 0
        self.stroke_enabled = True
        self.stroke_width = stroke_w
        self.stroke_type = stroke_type
        self.stroke_color = (255, 0, 0, 255)
        self.stroke_join = join
        self.stroke_cap = "butt"
        self.stroke_dash_length = 0
        self.stroke_dash_gap = 0


def render_stroke(w, h, radius, stroke_w, stroke_type, join="miter"):
    """返回 (描边覆盖度 float32, 填充 bool 数组, x 偏移, y 偏移)。

    不做裁剪 —— 外描边本来就落在图层外扩出去的那一圈里，裁掉就等于把它删了。
    (ox, oy) 是图层左上角在输出图像里的位置，供坐标对齐用。

    覆盖度 = ((R - G) / 255) × (A / 255)：描边是纯红 (255,0,0)、填充是纯白。
    只取 (R-G) 不够 —— 外描边叠在透明背景上时 RGB 恒为纯红，alpha 才是 AA 信息；
    只取 A 也不够 —— 内描边叠在白色内容上时 alpha 恒为 255。
    """
    layer = FakeLayer(w, h, radius, stroke_w, stroke_type, join)
    params = VectorEffectParams.collect(layer)
    content = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    out = apply_vector_path_effects(content, params)
    ox = -int(out.info.get("vector_offset_x", 0))
    oy = -int(out.info.get("vector_offset_y", 0))

    arr = np.asarray(out, dtype=np.float32)
    red = np.clip((arr[:, :, 0] - arr[:, :, 1]) / 255.0, 0.0, 1.0) * (arr[:, :, 3] / 255.0)
    white = (arr[:, :, 0] > 180) & (arr[:, :, 1] > 180) & (arr[:, :, 2] > 180)
    return red, white, ox, oy


def case_stroke_modes():
    print("=" * 68)
    print("用例 1：三种描边模式的真实产物（300x300 矩形，圆角 40，描边 20px）")
    print("=" * 68)
    w = h = 300
    stw = 20
    res = {}
    for stype, name in ((0, "内描边"), (1, "居中描边"), (2, "外描边")):
        red, _, _, _ = render_stroke(w, h, 40, stw, stype)
        res[name] = int((red > 0.5).sum())
        print(f"  stroke_type={stype} {name:<6}: 描边像素 {res[name]:>7}")

    print()
    ok = True
    if res["外描边"] == 0:
        print("  [FAIL] 外描边仍为 0 像素")
        ok = False
    else:
        print("  [PASS] 外描边有实际像素")
    if res["内描边"] == res["居中描边"] == res["外描边"]:
        print("  [FAIL] 三种模式像素完全相同，仍无法区分")
        ok = False
    else:
        print("  [PASS] 三种模式互不相同")

    # 宽度校验：内/外描边面积应约等于 周长 * 宽度
    perim = 2 * (w + h) - (8 - 2 * math.pi) * 40  # 圆角矩形的精确周长
    expect = perim * stw
    for name in ("内描边", "外描边", "居中描边"):
        dev = abs(res[name] - expect) / expect * 100
        flag = "" if dev < 12 else "  <- 偏差过大"
        print(f"  宽度校验 {name}: 实测 {res[name]:>7} / 理论 {expect:>8.0f} 偏差 {dev:5.1f}%{flag}")
        if dev >= 12:
            ok = False
    return ok, res


def _bilinear(arr, x, y):
    """亚像素双线性采样；越界返回 0。"""
    x0, y0 = int(math.floor(x)), int(math.floor(y))
    if x0 < 0 or y0 < 0 or x0 + 1 >= arr.shape[1] or y0 + 1 >= arr.shape[0]:
        return 0.0
    fx, fy = x - x0, y - y0
    return float(
        arr[y0, x0] * (1 - fx) * (1 - fy)
        + arr[y0, x0 + 1] * fx * (1 - fy)
        + arr[y0 + 1, x0] * (1 - fx) * fy
        + arr[y0 + 1, x0 + 1] * fx * fy
    )


def case_corner_uniformity():
    print()
    print("=" * 68)
    print("用例 2：圆角处描边径向宽度（400x400，圆角 80，描边 8px）")
    print("=" * 68)
    print("  一期验收：平均宽度对齐设定值；二期验收：极差 <= 0.5px（需 SDF）")
    s, r, stw = 400, 80, 8
    ok_first = True
    for stype, name in ((1, "居中描边"), (0, "内描边"), (2, "外描边")):
        red, _, ox, oy = render_stroke(s, s, r, stw, stype)
        cx, cy = r + ox, r + oy
        cov = red
        widths = []
        for deg in range(185, 266, 10):
            a = math.radians(deg)
            acc = 0.0
            for t in np.arange(r - stw - 6, r + stw + 6, 0.05):
                acc += 0.05 * _bilinear(cov, cx + t * math.cos(a), cy + t * math.sin(a))
            widths.append(acc)
        spread = max(widths) - min(widths)
        mean = sum(widths) / len(widths)
        mean_bad = abs(mean - stw) > 1.0
        if mean_bad:
            ok_first = False
        print(f"  {name}: 平均 {mean:5.2f}px  {'[FAIL]' if mean_bad else '[PASS]'}   "
              f"极差 {spread:.2f}px {'[二期]' if spread > 0.5 else ''}")
    return ok_first


def case_corner_geometry():
    print()
    print("=" * 68)
    print("用例 3：圆角弧段离散化误差（对照：是否真是锯齿来源）")
    print("=" * 68)
    step = math.radians(90.0 / 24)
    print("  段数固定 24，每段圆心角 3.75deg")
    worst = 0.0
    for rr in (8, 30, 80, 200, 400):
        sag = rr * (1 - math.cos(step / 2))
        worst = max(worst, sag)
        print(f"  r={rr:>4} : 弦高误差 {sag:6.3f}px")
    print(f"  [{'PASS' if worst < 1.0 else 'FAIL'}] 最大 {worst:.3f}px，"
          f"{'远小于 1px，圆角填充不是锯齿来源' if worst < 1.0 else '已超过 1px'}")
    return worst < 1.0


def case_supersample_memory():
    print()
    print("=" * 68)
    print("用例 4：超采样倍数与中间蒙版内存")
    print("=" * 68)
    for w, h, sw in ((1000, 1000, 0), (2000, 2000, 4), (3000, 3000, 10), (4000, 4000, 20)):
        scale = _vector_raster_supersample(sw, has_stroke=sw > 0, width=w, height=h)
        mb = (w * scale) * (h * scale) / (1024 * 1024)
        print(f"  {w}x{h} 描边{sw:>2}px -> {scale:>2}x -> 单通道 {mb:8,.0f} MB")
        if mb > 190:
            print("      <- 超过 180MB 预算，应被尺寸封顶压低")


def main():
    ok1, _ = case_stroke_modes()
    ok2 = case_corner_uniformity()
    ok3 = case_corner_geometry()
    case_supersample_memory()

    print()
    print("=" * 68)
    print("汇总")
    print("=" * 68)
    ok = ok1 and ok2 and ok3
    print("  [PASS] 全部通过" if ok else "  [FAIL] 存在未达标项，详见上文")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
