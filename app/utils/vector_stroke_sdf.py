"""矢量描边：距离场（SDF）实现。

替代 ``draw_polygon_outline_mask`` 的「超采样 + PIL 画粗线 + 路径外移」方案。

旧方案的三个残留问题（均在 docs/audit/render-quality-audit-2026-10-29.html 有实测）：
  1. 圆弧处径向宽度随弧段离散步进波动 —— 8px 设定下实测 7.24~9.04px，极差 22%；
  2. 超采样 10~16 倍，3000x3000 图层单张 L 蒙版即 900MB~1.4GB；
  3. ``stroke_join`` 的 miter / bevel 在 PIL 里没有区别，设置项形同虚设。

本实现：
  - 在 S 倍空间光栅化形状 → ``cv2.distanceTransform`` 得到欧氏距离 →
    内部距离减外部距离得到带符号距离场（内部为正、外部为负）；
  - 覆盖度 = ``clip(带宽 - |距离| + 0.5, 0, 1)``，圆弧的等距线严格平行于边界，
    因此径向宽度恒定；线性过渡本身即抗锯齿，不需要靠超采样堆灰阶；
  - 分块计算（每块含四周 pad），内存与图层尺寸解耦；
  - 距离场天然给出 round join，miter / bevel 通过尖角补丁补回。

已知限制：虚线（``stroke_dash_length > 0``）仍走旧的逐段绘制路径。
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw
from PIL.Image import Resampling

# 距离场分块边长（S 倍空间）。越大重叠开销越小，但单块 float32 内存越高。
# 3072² * 4B ≈ 36MB，两张（内/外距离）≈ 72MB。
_TILE_HI = 3072

# 距离场超采样倍数的上限与分档。二值边界量化误差 0.5/S：
#   S=5 → 0.10px（400x400 实测等宽极差 0.37~0.52px）
#   S=3 → 0.17px（0.46~0.71px）
# 小图层用户最容易盯着看、计算又快，给高倍；大图层降档控制耗时与内存。
_MAX_SDF_SCALE = 5
_SDF_SCALE_TIERS = (
    (700_000, 5),
    (1_800_000, 4),
    (9_000_000, 3),
)


def _target_sdf_scale(out_w: int, out_h: int) -> int:
    px = max(1, int(out_w)) * max(1, int(out_h))
    for limit, scale in _SDF_SCALE_TIERS:
        if px <= limit:
            return scale
    return 2

def _edt(mask_u8: np.ndarray) -> np.ndarray:
    """欧氏距离变换：每个非零像素到最近零像素的距离（单位：像素中心距）。"""
    import cv2

    return cv2.distanceTransform(mask_u8, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)


def _alpha_lut(
    stroke_width: float, scale: int, stroke_type: int, closed: bool
) -> Tuple[np.ndarray, int]:
    """距离 → 覆盖度的查表，返回 (lut, factor)。

    索引 i 对应 S 空间距离 i / factor；``factor`` 按带宽自适应，
    保证过渡带至少占约 12 个索引（否则 1/S 像素的距离量化会把等宽精度拖回 1px 级）。

    距离 i 对应真实像素距离 (i/factor - 0.5) / scale —— 减 0.5 是把「像素中心距」
    换算成「到真实边界的距离」。覆盖度用 1px 线性过渡，即 2x2 超采样的 AA。
    """
    w = float(max(1.0, stroke_width))
    band = max(0.5, w * 0.5) if (not closed or stroke_type not in (0, 2)) else w
    need = max(1.0, (band + 1.5) * float(max(1, scale)))  # 需要覆盖的 S 空间距离
    factor = int(max(1, min(8, int(250.0 // need))))
    i = np.arange(256, dtype=np.float32)
    dist = (i / float(factor) - 0.5) / float(max(1, scale))
    a = np.clip(band + 0.5 - dist, 0.0, 1.0)
    lut = np.clip(a * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    # 距离 0 表示「落在描边不该出现的另一侧」（内描边的外部 / 外描边的内部），
    # distanceTransform 对该侧返回 0。置 0 后无需再做全图布尔筛选。
    lut[0] = 0
    return lut, factor


def _alpha_block_u8(
    sub: np.ndarray,
    scale: int,
    lut: np.ndarray,
    factor: int,
    stroke_type: int,
    closed: bool,
) -> np.ndarray:
    """由 S 倍空间二值蒙版直接产出覆盖度 uint8（避免 float32 全数组往返）。"""
    import cv2

    if closed and stroke_type in (0, 2):
        # 内/外描边只需要单侧距离：distanceTransform 对另一侧返回 0，
        # 而 LUT[0] 已置 0，因此不需要再做全图布尔筛选。
        side = sub if stroke_type == 0 else np.subtract(1, sub, dtype=np.uint8)
        d = _edt(side)
    else:
        # 居中：内部 din、外部 dout，两侧各自为零，取 max 即 |带符号距离|
        din = _edt(sub)
        dout = _edt(np.subtract(1, sub, dtype=np.uint8))
        np.maximum(din, dout, out=din)
        del dout
        d = din
    # 距离乘 factor 后再查表，把索引量化精度提到 1/(factor*scale) 像素
    np.multiply(d, float(max(1, factor)), out=d)
    np.minimum(d, 255.0, out=d)
    return cv2.LUT(d.astype(np.uint8), lut)


def _signed_area(points: Sequence[Tuple[float, float]]) -> float:
    n = len(points)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a * 0.5


def _corner_patches(
    points: Sequence[Tuple[float, float]],
    stroke_width: float,
    stroke_type: int,
    join: str,
    miter_limit: float,
) -> List[List[Tuple[float, float]]]:
    """为凸角生成 miter / bevel 补丁多边形（1x 坐标）。

    距离场在角点外侧的等距线是圆弧（round join）。若用户选了 miter / bevel，
    这里把圆弧之外的三角形 / 四边形补上，取并集后即为对应 join。
    凹角不补 —— 距离场在凹角处的拓扑本来就是正确的，补丁反而会画到外面。
    """
    if join == "round" or len(points) < 3:
        return []

    pts = [(float(x), float(y)) for x, y in points]
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-6:
        pts.pop()
    n = len(pts)
    if n < 3:
        return []
    area_sign = 1.0 if _signed_area(pts) > 0 else -1.0

    if stroke_type == 0:
        sides = [(-1.0, max(1.0, float(stroke_width)))]
    elif stroke_type == 2:
        sides = [(1.0, max(1.0, float(stroke_width)))]
    else:
        half = max(0.5, float(stroke_width) * 0.5)
        sides = [(-1.0, half), (1.0, half)]

    polys: List[List[Tuple[float, float]]] = []
    for i in range(n):
        px, py = pts[i - 1]
        cx, cy = pts[i]
        qx, qy = pts[(i + 1) % n]
        e1x, e1y = cx - px, cy - py
        e2x, e2y = qx - cx, qy - cy
        l1 = math.hypot(e1x, e1y)
        l2 = math.hypot(e2x, e2y)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        # 归一化叉积，符号与面积符号一致即凸角
        cross = (e1x * e2y - e1y * e2x) / (l1 * l2)
        if cross * area_sign <= 1e-6:
            continue  # 凹角或共线
        if abs(cross) < 0.17:
            # 转角 < 约 10°，属于圆弧离散点：miter 与 round 的差值是 d*(1/cos5°-1)≈0.004d，
            # 远小于 0.1px，不需要补。圆角矩形的弧段每段仅 3.75°。
            continue
        # 外法线：顺时针(st Area>0) 时 (e.y, -e.x)
        n1x, n1y = (e1y / l1) * area_sign, (-e1x / l1) * area_sign
        n2x, n2y = (e2y / l2) * area_sign, (-e2x / l2) * area_sign
        for side, d in sides:
            ax, ay = cx + n1x * d * side, cy + n1y * d * side
            bx, by = cx + n2x * d * side, cy + n2y * d * side
            mx, my = n1x * side + n2x * side, n1y * side + n2y * side
            ml = math.hypot(mx, my)
            if ml < 1e-9:
                continue
            mx /= ml
            my /= ml
            cos_half = mx * n1x * side + my * n1y * side
            if cos_half <= 1e-6:
                continue
            ratio = 1.0 / cos_half
            if join == "bevel" or ratio > miter_limit:
                polys.append([(cx, cy), (ax, ay), (bx, by)])
            else:
                k = d * ratio
                polys.append([(cx, cy), (ax, ay), (cx + mx * k, cy + my * k), (bx, by)])
    return polys


def _raster_patches(
    polys: Sequence[Sequence[Tuple[float, float]]],
    out_size: Tuple[int, int],
    ss: int = 4,
) -> Optional[np.ndarray]:
    """把补丁多边形局部光栅化到 1x 蒙版。补丁面积小，逐块 4x 超采样成本可忽略。"""
    if not polys:
        return None
    w, h = int(out_size[0]), int(out_size[1])
    acc = np.zeros((h, w), dtype=np.uint8)
    touched = False
    for poly in polys:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        x0 = max(0, int(math.floor(min(xs))) - 2)
        y0 = max(0, int(math.floor(min(ys))) - 2)
        x1 = min(w, int(math.ceil(max(xs))) + 2)
        y1 = min(h, int(math.ceil(max(ys))) + 2)
        bw, bh = x1 - x0, y1 - y0
        if bw <= 0 or bh <= 0:
            continue
        m = Image.new("L", (bw * ss, bh * ss), 0)
        ImageDraw.Draw(m).polygon(
            [((px - x0) * ss, (py - y0) * ss) for px, py in poly], fill=255
        )
        blk = np.asarray(m.resize((bw, bh), Resampling.BOX), dtype=np.uint8)
        np.maximum(acc[y0:y1, x0:x1], blk, out=acc[y0:y1, x0:x1])
        touched = True
    return acc if touched else None


def build_stroke_mask(
    fill_hi: Optional[Image.Image],
    scale: int,
    out_size: Tuple[int, int],
    *,
    stroke_width: float,
    stroke_type: int,
    closed: bool,
    join: str = "miter",
    miter_limit: float = 4.0,
    path_points: Optional[Sequence[Tuple[float, float]]] = None,
    centerline_hi: Optional[Image.Image] = None,
) -> Image.Image:
    """由 S 倍空间的填充蒙版生成 1x 描边蒙版（L，0..255）。

    Args:
        fill_hi: S 倍空间填充蒙版；闭合路径用。
        scale: 超采样倍数。
        out_size: 输出 1x 尺寸。
        stroke_width: 描边总宽度（1x 像素）。
        stroke_type: 0 内 / 1 居中 / 2 外。
        closed: 路径是否闭合。开放路径改用 centerline_hi 做距离源并一律居中。
        join: miter / bevel / round。
        path_points: 1x 路径顶点，用于生成尖角补丁。
        centerline_hi: S 倍空间中心线（开放路径用，1px 宽）。
    """
    out_w, out_h = int(out_size[0]), int(out_size[1])
    blank = Image.new("L", (out_w, out_h), 0)
    src = fill_hi if closed else centerline_hi
    if src is None or out_w <= 0 or out_h <= 0:
        return blank

    # 距离场精度只需 0.5px 量级（二值边界量化误差 = 0.5/S），而填充 AA 需要高倍。
    # 两者解耦：这里把蒙版降到 SDF 分辨率，面积按平方下降，是最大的一笔性能收益。
    scale = max(1, int(scale))
    target = _target_sdf_scale(out_w, out_h)
    if scale > target:
        tw = max(1, int(round(src.width * target / scale)))
        th = max(1, int(round(src.height * target / scale)))
        src = src.resize((tw, th), Resampling.BOX)
        scale = target

    src_arr = np.asarray(src, dtype=np.uint8)
    mask = (src_arr > 127).astype(np.uint8)
    del src_arr
    if not mask.any():
        return blank

    # 距离场需要「零像素」才能感知边界。形状贴图层边缘（甚至铺满整层）时，
    # 画布外没有零像素，整条边会被误判为内部深处（实测 sd 在边缘给出 113px）。
    # 只需补 2px 零即可表达「边界在此」—— 距离场只关心最近的零像素。
    pad_hi = int(math.ceil((float(stroke_width) + 2.0) * scale)) + 2  # 分块上下文半径
    edge_pad = 2
    mask = np.pad(mask, ((edge_pad, edge_pad), (edge_pad, edge_pad)), mode="constant")
    hi_h, hi_w = int(mask.shape[0]), int(mask.shape[1])
    off = edge_pad  # padded 坐标 = 原始 S 空间坐标 + off

    out = np.zeros((out_h, out_w), dtype=np.uint8)
    tile_out = max(64, _TILE_HI // max(1, int(scale)))
    lut, lut_factor = _alpha_lut(stroke_width, scale, stroke_type, closed)

    for ty in range(0, out_h, tile_out):
        for tx in range(0, out_w, tile_out):
            x0, y0 = tx, ty
            x1 = min(out_w, tx + tile_out)
            y1 = min(out_h, ty + tile_out)
            sx0 = max(0, x0 * scale - pad_hi + off)
            sy0 = max(0, y0 * scale - pad_hi + off)
            sx1 = min(hi_w, x1 * scale + pad_hi + off)
            sy1 = min(hi_h, y1 * scale + pad_hi + off)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            sub = np.ascontiguousarray(mask[sy0:sy1, sx0:sx1])
            if not sub.any():
                # pad 范围内完全没有填充 → 描边不可能落到本块
                continue
            a8 = _alpha_block_u8(sub, scale, lut, lut_factor, stroke_type, closed)

            cy0 = y0 * scale + off - sy0
            cx0 = x0 * scale + off - sx0
            cy1 = y1 * scale + off - sy0
            cx1 = x1 * scale + off - sx0
            blk_src = np.ascontiguousarray(a8[cy0:cy1, cx0:cx1])
            del a8
            img = Image.fromarray(blk_src, "L").resize((x1 - x0, y1 - y0), Resampling.BOX)
            blk = np.asarray(img, dtype=np.uint8)
            np.maximum(out[y0:y1, x0:x1], blk, out=out[y0:y1, x0:x1])

    if closed and path_points is not None and join in ("miter", "bevel"):
        patch = _raster_patches(
            _corner_patches(path_points, stroke_width, stroke_type, join, miter_limit),
            (out_w, out_h),
        )
        if patch is not None:
            np.maximum(out, patch, out=out)

    return Image.fromarray(out, "L")
