"""图层矢量轮廓几何：圆角矩形、贝塞尔采样、与导出/画布共用的路径点。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import copy
import math
from typing import Any, Dict, List, Sequence, Tuple


def clamp_rounded_rect_radii(
    w: float, h: float, tl: float, tr: float, br: float, bl: float
) -> Tuple[float, float, float, float]:
    w = max(1.0, float(w))
    h = max(1.0, float(h))
    max_r = min(w, h) / 2.0
    tl = max(0.0, min(float(tl), max_r))
    tr = max(0.0, min(float(tr), max_r))
    br = max(0.0, min(float(br), max_r))
    bl = max(0.0, min(float(bl), max_r))

    def _pair(a: float, b: float, dim: float) -> Tuple[float, float]:
        if a + b > dim and (a + b) > 1e-9:
            s = a + b
            return a * dim / s, b * dim / s
        return a, b

    tl, tr = _pair(tl, tr, w)
    tr, br = _pair(tr, br, h)
    br, bl = _pair(br, bl, w)
    bl, tl = _pair(bl, tl, h)
    return tl, tr, br, bl


def _append_pt(out: List[Tuple[float, float]], x: float, y: float, eps: float = 1e-6) -> None:
    if not out:
        out.append((x, y))
        return
    lx, ly = out[-1]
    if abs(lx - x) > eps or abs(ly - y) > eps:
        out.append((x, y))


def _arc_append(
    out: List[Tuple[float, float]],
    cx: float,
    cy: float,
    r: float,
    deg_start: float,
    deg_end: float,
    seg: int,
) -> None:
    if r <= 0:
        return
    step = (deg_end - deg_start) / float(max(1, seg))
    for i in range(seg + 1):
        a = math.radians(deg_start + step * i)
        _append_pt(out, cx + math.cos(a) * r, cy + math.sin(a) * r)


def build_rounded_rect_outline_points(
    width: float,
    height: float,
    corner_radius: float,
    v_tl: float,
    v_tr: float,
    v_br: float,
    v_bl: float,
    arc_segments: int = 24,
) -> List[Tuple[float, float]]:
    w = max(1.0, float(width))
    h = max(1.0, float(height))
    base_r = max(0.0, float(corner_radius))
    tl = max(0.0, float(v_tl))
    tr = max(0.0, float(v_tr))
    br = max(0.0, float(v_br))
    bl = max(0.0, float(v_bl))
    if max(tl, tr, br, bl) <= 1e-9 and base_r > 1e-9:
        tl = tr = br = bl = base_r

    tl, tr, br, bl = clamp_rounded_rect_radii(w, h, tl, tr, br, bl)
    seg = max(4, int(arc_segments))

    if max(tl, tr, br, bl) <= 1e-9:
        return [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]

    pts: List[Tuple[float, float]] = []

    if tl > 0:
        _append_pt(pts, 0.0, tl)
        _arc_append(pts, tl, tl, tl, 180.0, 270.0, seg)
    else:
        _append_pt(pts, 0.0, 0.0)

    _append_pt(pts, w - tr, 0.0)
    if tr > 0:
        _arc_append(pts, w - tr, tr, tr, 270.0, 360.0, seg)
    else:
        _append_pt(pts, w, 0.0)

    _append_pt(pts, w, h - br)
    if br > 0:
        _arc_append(pts, w - br, h - br, br, 0.0, 90.0, seg)
    else:
        _append_pt(pts, w, h)

    _append_pt(pts, bl, h)
    if bl > 0:
        _arc_append(pts, bl, h - bl, bl, 90.0, 180.0, seg)
    else:
        _append_pt(pts, 0.0, h)

    _append_pt(pts, 0.0, tl if tl > 0 else 0.0)
    return pts


def normalize_vector_path_points(points: Any) -> List[List[float]]:
    normalized: List[List[float]] = []
    if not isinstance(points, (list, tuple)):
        return normalized
    for pt in points:
        if isinstance(pt, dict):
            x = pt.get("x")
            y = pt.get("y")
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            x, y = pt[0], pt[1]
        else:
            continue
        try:
            normalized.append([float(x), float(y)])
        except (TypeError, ValueError):
            logger.debug("静默异常已忽略: except in utils/vector_layer_geometry.py")
            continue
    return normalized


def normalize_vector_bezier_nodes(nodes: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(nodes, (list, tuple)):
        return normalized
    for n in nodes:
        if not isinstance(n, dict):
            continue
        try:
            x = float(n.get("x", 0.0))
            y = float(n.get("y", 0.0))
            in_x = float(n.get("in_x", x))
            in_y = float(n.get("in_y", y))
            out_x = float(n.get("out_x", x))
            out_y = float(n.get("out_y", y))
        except (TypeError, ValueError):
            logger.debug("静默异常已忽略: except in utils/vector_layer_geometry.py")
            continue
        nt = str(n.get("node_type", "corner")).lower()
        if nt not in {"corner", "smooth", "symmetric"}:
            nt = "corner"
        normalized.append(
            {
                "x": x,
                "y": y,
                "in_x": in_x,
                "in_y": in_y,
                "out_x": out_x,
                "out_y": out_y,
                "node_type": nt,
            }
        )
    return normalized


def sample_cubic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    segments: int = 20,
) -> List[Tuple[float, float]]:
    sampled: List[Tuple[float, float]] = []
    for i in range(segments + 1):
        t = i / float(segments)
        u = 1.0 - t
        x = (
            u * u * u * p0[0]
            + 3 * u * u * t * p1[0]
            + 3 * u * t * t * p2[0]
            + t * t * t * p3[0]
        )
        y = (
            u * u * u * p0[1]
            + 3 * u * u * t * p1[1]
            + 3 * u * t * t * p2[1]
            + t * t * t * p3[1]
        )
        sampled.append((x, y))
    return sampled


def build_vector_path_points_px(
    width: int,
    height: int,
    path_points: Sequence,
) -> List[Tuple[float, float]]:
    points = normalize_vector_path_points(path_points)
    if len(points) < 3:
        points = [
            [0.0, 0.0],
            [float(width), 0.0],
            [float(width), float(height)],
            [0.0, float(height)],
        ]
    return [(float(x), float(y)) for x, y in points]


def _build_regular_polygon_points(
    width: float,
    height: float,
    sides: int,
    rotation_deg: float = 0.0,
) -> List[Tuple[float, float]]:
    w = max(1.0, float(width))
    h = max(1.0, float(height))
    n = max(3, int(sides))
    cx = w / 2.0
    cy = h / 2.0
    margin = 5.0
    r = max(1.0, min(w, h) / 2.0 - margin)
    rot = math.radians(float(rotation_deg))
    points: List[Tuple[float, float]] = []
    for i in range(n):
        angle = 2.0 * math.pi * i / float(n) + rot
        x = cx + r * math.cos(angle - math.pi / 2.0)
        y = cy + r * math.sin(angle - math.pi / 2.0)
        points.append((x, y))
    return points


def _build_circle_points(
    width: float,
    height: float,
    segments: int = 72,
) -> List[Tuple[float, float]]:
    w = max(1.0, float(width))
    h = max(1.0, float(height))
    n = max(12, int(segments))
    cx = w / 2.0
    cy = h / 2.0
    margin = 2.0
    r = max(1.0, min(w, h) / 2.0 - margin)
    points: List[Tuple[float, float]] = []
    for i in range(n):
        a = 2.0 * math.pi * i / float(n)
        points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return points


def _polygon_signed_area(points: Sequence[Tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area2 = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        area2 += x1 * y2 - x2 * y1
    return area2 * 0.5


def _build_rounded_polygon_points(
    points: Sequence[Tuple[float, float]],
    corner_radius: float,
    arc_segments: int = 12,
) -> List[Tuple[float, float]]:
    if len(points) < 3:
        return list(points)
    radius = max(0.0, float(corner_radius))
    if radius <= 1e-6:
        return [(float(x), float(y)) for x, y in points]

    pts = [(float(x), float(y)) for x, y in points]
    winding_ccw = _polygon_signed_area(pts) >= 0.0
    seg = max(4, int(arc_segments))
    rounded: List[Tuple[float, float]] = []

    for i in range(len(pts)):
        ax, ay = pts[(i - 1) % len(pts)]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % len(pts)]

        v1x, v1y = ax - bx, ay - by
        v2x, v2y = cx - bx, cy - by
        len1 = math.hypot(v1x, v1y)
        len2 = math.hypot(v2x, v2y)
        if len1 <= 1e-6 or len2 <= 1e-6:
            _append_pt(rounded, bx, by)
            continue

        u1x, u1y = v1x / len1, v1y / len1
        u2x, u2y = v2x / len2, v2y / len2
        dot = max(-1.0, min(1.0, u1x * u2x + u1y * u2y))
        theta = math.acos(dot)
        if theta <= 1e-5 or abs(math.pi - theta) <= 1e-5:
            _append_pt(rounded, bx, by)
            continue

        tan_half = math.tan(theta / 2.0)
        if abs(tan_half) <= 1e-6:
            _append_pt(rounded, bx, by)
            continue
        max_t = max(0.0, min(len1, len2) * 0.49)
        t = min(radius / tan_half, max_t)
        if t <= 1e-6:
            _append_pt(rounded, bx, by)
            continue

        effective_r = t * tan_half
        bisx, bisy = u1x + u2x, u1y + u2y
        bis_len = math.hypot(bisx, bisy)
        if bis_len <= 1e-6:
            _append_pt(rounded, bx, by)
            continue
        bisx /= bis_len
        bisy /= bis_len

        to_center = effective_r / max(1e-6, math.sin(theta / 2.0))
        ox = bx + bisx * to_center
        oy = by + bisy * to_center

        sx = bx + u1x * t
        sy = by + u1y * t
        ex = bx + u2x * t
        ey = by + u2y * t

        start_ang = math.atan2(sy - oy, sx - ox)
        end_ang = math.atan2(ey - oy, ex - ox)

        if winding_ccw:
            while end_ang < start_ang:
                end_ang += 2.0 * math.pi
        else:
            while end_ang > start_ang:
                end_ang -= 2.0 * math.pi

        _append_pt(rounded, sx, sy)
        step = (end_ang - start_ang) / float(seg)
        for j in range(1, seg):
            ang = start_ang + step * j
            _append_pt(rounded, ox + math.cos(ang) * effective_r, oy + math.sin(ang) * effective_r)
        _append_pt(rounded, ex, ey)

    return rounded


def _build_parametric_shape_outline_points(
    width: int,
    height: int,
    shape_type: str,
    trapezoid_top_width: int,
    trapezoid_bottom_width: int,
    trapezoid_slope_side: str,
    polygon_rotation: float,
    polygon_corner_radius: int,
) -> List[Tuple[float, float]]:
    w = max(1.0, float(width))
    h = max(1.0, float(height))
    st = str(shape_type or "rectangle").lower()
    if st == "right_trapezoid":
        top_ratio = max(0.01, min(1.0, float(trapezoid_top_width) / 100.0))
        bottom_ratio = max(0.01, min(1.0, float(trapezoid_bottom_width) / 100.0))
        top_w = w * top_ratio
        bottom_w = w * bottom_ratio
        side = str(trapezoid_slope_side or "right").lower()
        base_pts: List[Tuple[float, float]]
        if side == "left":
            base_pts = [
                (w - top_w, 0.0),
                (w, 0.0),
                (w, h),
                (w - bottom_w, h),
            ]
        else:
            base_pts = [
                (0.0, 0.0),
                (top_w, 0.0),
                (bottom_w, h),
                (0.0, h),
            ]
        return _build_rounded_polygon_points(base_pts, float(polygon_corner_radius))
    if st == "circle":
        return _build_circle_points(w, h)
    if st == "pentagon":
        base_pts = _build_regular_polygon_points(w, h, 5, rotation_deg=float(polygon_rotation))
        return _build_rounded_polygon_points(base_pts, float(polygon_corner_radius))
    if st == "hexagon":
        base_pts = _build_regular_polygon_points(w, h, 6, rotation_deg=float(polygon_rotation))
        return _build_rounded_polygon_points(base_pts, float(polygon_corner_radius))
    return [
        (0.0, 0.0),
        (w, 0.0),
        (w, h),
        (0.0, h),
    ]


def build_vector_outline_points_px(
    width: int,
    height: int,
    corner_radius: int,
    vector_tl: int,
    vector_tr: int,
    vector_br: int,
    vector_bl: int,
    vector_path_enabled: bool,
    vector_path_mode: str,
    vector_path_points: Any,
    vector_bezier_nodes: Any,
    vector_path_closed: bool,
    shape_type: str = "rectangle",
    trapezoid_top_width: int = 100,
    trapezoid_bottom_width: int = 80,
    trapezoid_slope_side: str = "right",
    polygon_rotation: float = 0.0,
    polygon_corner_radius: int = 0,
) -> Tuple[List[Tuple[float, float]], bool]:
    if not bool(vector_path_enabled):
        st = str(shape_type or "rectangle").lower()
        if st == "rectangle":
            pts = build_rounded_rect_outline_points(
                float(width),
                float(height),
                float(corner_radius),
                float(vector_tl),
                float(vector_tr),
                float(vector_br),
                float(vector_bl),
            )
            return pts, True
        return (
            _build_parametric_shape_outline_points(
                width=width,
                height=height,
                shape_type=st,
                trapezoid_top_width=trapezoid_top_width,
                trapezoid_bottom_width=trapezoid_bottom_width,
                trapezoid_slope_side=trapezoid_slope_side,
                polygon_rotation=polygon_rotation,
                polygon_corner_radius=polygon_corner_radius,
            ),
            True,
        )
    mode = str(vector_path_mode or "polygon").lower()
    closed = bool(vector_path_closed)
    if mode != "bezier":
        return build_vector_path_points_px(width, height, vector_path_points), closed
    nodes = normalize_vector_bezier_nodes(vector_bezier_nodes)
    if len(nodes) < 3:
        return build_vector_path_points_px(width, height, vector_path_points), closed
    outline: List[Tuple[float, float]] = []
    n = len(nodes)
    seg_count = n if closed else n - 1
    for i in range(seg_count):
        cur = nodes[i]
        nxt = nodes[(i + 1) % n]
        p0 = (cur["x"], cur["y"])
        p1 = (cur["out_x"], cur["out_y"])
        p2 = (nxt["in_x"], nxt["in_y"])
        p3 = (nxt["x"], nxt["y"])
        seg = sample_cubic_bezier(p0, p1, p2, p3, segments=28)
        if outline:
            outline.extend(seg[1:])
        else:
            outline.extend(seg)
    return outline, closed


def deep_copy_bezier_nodes(nodes: Any) -> Any:
    return copy.deepcopy(nodes)
