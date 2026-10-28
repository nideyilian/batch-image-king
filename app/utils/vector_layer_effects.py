"""矢量路径裁剪与描边渲染（导出与 Layer/LayerNew 共用）。"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw
from PIL.Image import Resampling

from app.utils.vector_layer_geometry import build_vector_outline_points_px


def _vector_raster_supersample(stroke_width_px: int, *, has_stroke: bool) -> int:
    """矢量容器在较高分辨率光栅化再降采样，减轻锯齿与描边含糊感。"""
    if not has_stroke or stroke_width_px <= 0:
        return 10
    return int(min(16, max(10, 8 + stroke_width_px // 2)))


def _downsample_mask(mask: Image.Image, out_size: Tuple[int, int]) -> Image.Image:
    """面积平均降采样，比 LANCZOS 更少晕边，边缘更干净。"""
    return mask.resize(out_size, Resampling.BOX)


def _sharp_alpha_composite(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """矢量描边合成：不走质量修复器的柔化/修边，避免二次模糊。"""
    if base.size != overlay.size:
        raise ValueError("alpha composite size mismatch")
    if base.mode != "RGBA":
        base = base.convert("RGBA")
    if overlay.mode != "RGBA":
        overlay = overlay.convert("RGBA")
    return Image.alpha_composite(base, overlay)


def _draw_fill_mask_hi(
    size: Tuple[int, int],
    points: List[Tuple[float, float]],
    closed: bool,
    scale: int,
    *,
    open_line_width_px: int = 1,
) -> Image.Image:
    w, h = size[0], size[1]
    lw, lh = int(w * scale), int(h * scale)
    lp = [(float(p[0]) * scale, float(p[1]) * scale) for p in points]
    m = Image.new("L", (lw, lh), 0)
    dr = ImageDraw.Draw(m)
    if closed:
        dr.polygon(lp, fill=255)
    else:
        dr.line(lp, fill=255, width=max(1, int(open_line_width_px * scale)))
    return m


def _binary_morph(mask_bool, radius: int, mode: str):
    """对布尔蒙版做半径为 radius 的形态学运算（3x3 结构）。"""
    r = max(0, int(radius))
    if r <= 0:
        return mask_bool.copy()
    import numpy as np

    from app.utils.image import ndops

    structure = np.ones((3, 3), dtype=bool)
    operation = "dilation" if mode == "dilate" else "erosion"
    return ndops.binary_morphology(mask_bool, structure, iterations=r, operation=operation)


def _build_closed_stroke_mask_by_morph(base_hi: Image.Image, stroke_px_hi: int, stroke_type: int) -> Image.Image:
    import numpy as np

    b = (np.array(base_hi, dtype=np.uint8) > 127)
    sw = max(1, int(stroke_px_hi))
    if stroke_type == 0:
        er = _binary_morph(b, sw, "erode")
        ring = b & (~er)
    elif stroke_type == 2:
        di = _binary_morph(b, sw, "dilate")
        ring = di & (~b)
    else:
        out_r = max(1, (sw + 1) // 2)
        in_r = max(0, sw // 2)
        di = _binary_morph(b, out_r, "dilate")
        er = _binary_morph(b, in_r, "erode") if in_r > 0 else b
        ring = di & (~er)
    return Image.fromarray((ring.astype(np.uint8) * 255), mode="L")


def _offset_points(points: List[Tuple[float, float]], dx: float, dy: float) -> List[Tuple[float, float]]:
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return list(points)
    return [(float(x) + float(dx), float(y) + float(dy)) for x, y in points]


def _interior_core_mask(base_mask: Image.Image, shrink_px: int) -> Image.Image:
    """
    将填充蒙版向内收缩若干像素，得到“严格内部”区域。
    外描边不能与 invert(填充) 直接相乘：贴边像元在填充里为 255，会把整段直边上的外描边乘没，
    仅圆角弧段残留；此处用腐蚀后的核取补后再裁描边。
    """
    if shrink_px <= 0:
        return base_mask.copy()
    import numpy as np

    from app.utils.image import ndops

    filled = np.array(base_mask, dtype=np.uint8) > 127
    core = ndops.binary_morphology(
        filled,
        np.ones((3, 3), dtype=bool),
        iterations=int(shrink_px),
        operation="erosion",
    )
    return Image.fromarray((core.astype(np.uint8) * 255))


def alpha_composite_layers(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """合成底层与顶层 RGBA（与旧版 Layer._safe_alpha_composite 行为一致）。"""
    return _default_alpha_composite(base, overlay)


def _default_alpha_composite(base: Image.Image, overlay: Image.Image) -> Image.Image:
    try:
        from app.utils.image_quality_fixer import get_image_quality_fixer

        qf = get_image_quality_fixer()
        return qf.composite_with_quality(
            background=base,
            foreground=overlay,
            position=(0, 0),
            opacity=1.0,
            fix_edges=True,
            enhance_aa=True,
        )
    except Exception:
        if base.mode != "RGBA":
            base = base.convert("RGBA")
        if overlay.mode != "RGBA":
            overlay = overlay.convert("RGBA")
        result = base.copy()
        result.paste(overlay, (0, 0), overlay)
        return result


@dataclass
class VectorEffectParams:
    width: int
    height: int
    corner_radius: int
    vector_corner_radius_tl: int
    vector_corner_radius_tr: int
    vector_corner_radius_br: int
    vector_corner_radius_bl: int
    vector_path_enabled: bool
    vector_path_points: Any
    vector_path_mode: str
    vector_bezier_nodes: Any
    vector_path_closed: bool
    shape_type: str
    trapezoid_top_width: int
    trapezoid_bottom_width: int
    trapezoid_slope_side: str
    polygon_rotation: float
    polygon_corner_radius: int
    stroke_enabled: bool
    stroke_width: int
    stroke_type: int
    stroke_color: Tuple[int, int, int, int]
    stroke_join: str
    stroke_cap: str
    stroke_dash_length: int
    stroke_dash_gap: int

    @classmethod
    def collect(cls, layer: Any) -> "VectorEffectParams":
        return cls(
            width=int(getattr(layer, "width")),
            height=int(getattr(layer, "height")),
            corner_radius=int(getattr(layer, "corner_radius", 0)),
            vector_corner_radius_tl=int(getattr(layer, "vector_corner_radius_tl", 0)),
            vector_corner_radius_tr=int(getattr(layer, "vector_corner_radius_tr", 0)),
            vector_corner_radius_br=int(getattr(layer, "vector_corner_radius_br", 0)),
            vector_corner_radius_bl=int(getattr(layer, "vector_corner_radius_bl", 0)),
            vector_path_enabled=bool(getattr(layer, "vector_path_enabled", False)),
            vector_path_points=getattr(layer, "vector_path_points", []),
            vector_path_mode=str(getattr(layer, "vector_path_mode", "polygon")),
            vector_bezier_nodes=getattr(layer, "vector_bezier_nodes", []),
            vector_path_closed=bool(getattr(layer, "vector_path_closed", True)),
            shape_type=str(getattr(getattr(layer, "shape_type", "rectangle"), "value", getattr(layer, "shape_type", "rectangle"))),
            trapezoid_top_width=int(getattr(layer, "trapezoid_top_width", 100)),
            trapezoid_bottom_width=int(getattr(layer, "trapezoid_bottom_width", 80)),
            trapezoid_slope_side=str(getattr(layer, "trapezoid_slope_side", "right")),
            polygon_rotation=float(getattr(layer, "polygon_rotation", 0.0)),
            polygon_corner_radius=int(getattr(layer, "polygon_corner_radius", 0)),
            stroke_enabled=bool(getattr(layer, "stroke_enabled", False))
            and int(getattr(layer, "stroke_width", 0)) > 0,
            stroke_width=int(getattr(layer, "stroke_width", 1)),
            stroke_type=int(getattr(layer, "stroke_type", 0)),
            stroke_color=tuple(getattr(layer, "stroke_color", (0, 0, 0, 255))),
            stroke_join=str(getattr(layer, "stroke_join", "miter")),
            stroke_cap=str(getattr(layer, "stroke_cap", "butt")),
            stroke_dash_length=int(getattr(layer, "stroke_dash_length", 0)),
            stroke_dash_gap=int(getattr(layer, "stroke_dash_gap", 0)),
        )


def _closed_polyline_for_stroke(large_points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """闭合折线：Pillow line 需要首尾闭合；去除重复尾点避免零长折返。"""
    if len(large_points) < 2:
        return list(large_points)
    seq = list(large_points)
    ax, ay = seq[0]
    bx, by = seq[-1]
    if math.hypot(ax - bx, ay - by) < 1e-3:
        seq.pop()
    seq.append(seq[0])
    return seq


def draw_polygon_outline_mask(
    size: Tuple[int, int],
    points: List[Tuple[float, float]],
    width: int,
    closed: bool,
    stroke_join: str,
    stroke_cap: str,
    dash_length: int,
    dash_gap: int,
) -> Image.Image:
    scale = _vector_raster_supersample(max(1, int(width)), has_stroke=True)
    large_size = (int(size[0] * scale), int(size[1] * scale))
    large_points = [(p[0] * scale, p[1] * scale) for p in points]
    mask = Image.new("L", large_size, 0)
    draw = ImageDraw.Draw(mask)
    stroke_w = max(1, int(width * scale))
    dash_len = int(dash_length)
    d_gap = int(dash_gap)
    if dash_len <= 0:
        if closed and len(large_points) >= 2:
            if stroke_join == "round":
                seq = _closed_polyline_for_stroke(large_points)
                draw.line(seq, fill=255, width=stroke_w, joint="curve")
            else:
                draw.polygon(large_points, outline=255, width=stroke_w)
        else:
            draw.line(large_points, fill=255, width=stroke_w)
            if stroke_cap == "round" and len(large_points) >= 2:
                r = max(1, stroke_w // 2)
                for p in (large_points[0], large_points[-1]):
                    draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=255)
            elif stroke_cap == "square" and len(large_points) >= 2:
                half = stroke_w / 2.0
                sx1, sy1 = large_points[0]
                sx2, sy2 = large_points[1]
                svx, svy = sx1 - sx2, sy1 - sy2
                sl = max(1e-6, math.hypot(svx, svy))
                sux, suy = svx / sl, svy / sl
                draw.line([(sx1, sy1), (sx1 + sux * half, sy1 + suy * half)], fill=255, width=stroke_w)
                ex1, ey1 = large_points[-1]
                ex2, ey2 = large_points[-2]
                evx, evy = ex1 - ex2, ey1 - ey2
                el = max(1e-6, math.hypot(evx, evy))
                eux, euy = evx / el, evy / el
                draw.line([(ex1, ey1), (ex1 + eux * half, ey1 + euy * half)], fill=255, width=stroke_w)
    else:
        all_points = large_points + ([large_points[0]] if closed else [])
        seg_draw = len(large_points) if closed else max(0, len(large_points) - 1)
        for i in range(seg_draw):
            x1, y1 = all_points[i]
            x2, y2 = all_points[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            seg_len = max(1e-6, math.hypot(dx, dy))
            ux = dx / seg_len
            uy = dy / seg_len
            pos = 0.0
            while pos < seg_len:
                seg_draw_len = min(float(dash_len * scale), seg_len - pos)
                sx = x1 + ux * pos
                sy = y1 + uy * pos
                ex = x1 + ux * (pos + seg_draw_len)
                ey = y1 + uy * (pos + seg_draw_len)
                draw.line([(sx, sy), (ex, ey)], fill=255, width=stroke_w)
                pos += float((dash_len + max(1, d_gap)) * scale)

    return _downsample_mask(mask, size)


def apply_vector_path_effects(
    image: Image.Image,
    params: VectorEffectParams,
    *,
    alpha_composite: Optional[Callable[[Image.Image, Image.Image], Image.Image]] = None,
) -> Image.Image:
    _ = alpha_composite  # 兼容 Layer 传入；此处固定 Image.alpha_composite，避免修边柔化
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    points, closed = build_vector_outline_points_px(
        params.width,
        params.height,
        params.corner_radius,
        params.vector_corner_radius_tl,
        params.vector_corner_radius_tr,
        params.vector_corner_radius_br,
        params.vector_corner_radius_bl,
        params.vector_path_enabled,
        params.vector_path_mode,
        params.vector_path_points,
        params.vector_bezier_nodes,
        params.vector_path_closed,
        params.shape_type,
        params.trapezoid_top_width,
        params.trapezoid_bottom_width,
        params.trapezoid_slope_side,
        params.polygon_rotation,
        params.polygon_corner_radius,
    )
    base_size = image.size
    stroke_w = max(1, int(params.stroke_width))
    outside_expand = 0
    if params.stroke_enabled:
        if params.stroke_type == 2:
            outside_expand = stroke_w
        elif params.stroke_type == 1:
            outside_expand = (stroke_w + 1) // 2
    size = (base_size[0] + outside_expand * 2, base_size[1] + outside_expand * 2)
    shifted_points = _offset_points(points, outside_expand, outside_expand)

    if params.stroke_enabled:
        superscale = _vector_raster_supersample(stroke_w, has_stroke=True)
    else:
        superscale = _vector_raster_supersample(0, has_stroke=False)
    base_hi = _draw_fill_mask_hi(
        size,
        shifted_points,
        closed,
        superscale,
        open_line_width_px=max(1, int(params.stroke_width)) if not closed else 1,
    )
    base_mask = _downsample_mask(base_hi, size)

    content = Image.new("RGBA", size, (0, 0, 0, 0))
    content.paste(image, (outside_expand, outside_expand), image)
    if closed:
        content.putalpha(ImageChops.multiply(content.split()[3], base_mask))

    if not params.stroke_enabled:
        content.info["vector_offset_x"] = int(-outside_expand)
        content.info["vector_offset_y"] = int(-outside_expand)
        return content

    # 统一使用几何等宽描边，避免闭合形状在形态学描边下出现圆角处比直边更粗的问题
    stroke_mask = draw_polygon_outline_mask(
        size,
        shifted_points,
        stroke_w,
        closed,
        params.stroke_join,
        params.stroke_cap,
        params.stroke_dash_length,
        params.stroke_dash_gap,
    )
    if params.stroke_type == 0:
        stroke_mask = ImageChops.multiply(stroke_mask, base_mask)
    elif params.stroke_type == 2:
        stroke_mask = ImageChops.multiply(stroke_mask, ImageChops.invert(base_mask))

    stroke_layer = Image.new("RGBA", size, params.stroke_color)
    stroke_layer.putalpha(stroke_mask)
    # 描边叠在内容之上；矢量结果使用精确 alpha 合成，避免质量修复器二次柔化
    merged = _sharp_alpha_composite(content, stroke_layer)
    merged.info["vector_offset_x"] = int(-outside_expand)
    merged.info["vector_offset_y"] = int(-outside_expand)
    return merged
