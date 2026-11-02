"""选中框变换手柄的命中几何（与 ``Main.qml`` 的 ``handleAt`` 一一对应）。

**按 Photoshop 移动工具的规则**：缩放手柄只有 8 个离散方块，
不在边框线上。点击边框线或边框外侧一律穿透到下层图层。

这条规则和视觉强相关：界面上画的就是 8 个小方块，
如果命中区是「整条边」，用户看到的热区和实际能拖的区域就是两套东西——
表现为「以为能选中下层图层，结果却在缩放」。

为什么抽成 Python：QML 内联函数只能起界面点鼠标验证，边界（缩放变化、
小图层、旋转）一改就不知道有没有踩坏。这里可测，QML 侧仍是执行者，
两边的关键取值由 ``tests/test_selection_handle_geometry.py`` 直接读源码断言。
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

# 手柄方块的视觉尺寸（屏幕像素）
HANDLE_SCREEN_SIZE = 8.0
# 手柄的命中尺寸（屏幕像素）。略大于视觉尺寸以便点中，
# 但**只在手柄周围扩展**，不会扩展成整条边。
HANDLE_HIT_SCREEN_SIZE = 14.0

# 8 个手柄在选中框局部坐标中的比例位置，顺序与 QML 的 handleAnchors 一致
HANDLE_ANCHORS: Tuple[Tuple[str, float, float], ...] = (
    ("nw", 0.0, 0.0),
    ("n", 0.5, 0.0),
    ("ne", 1.0, 0.0),
    ("e", 1.0, 0.5),
    ("se", 1.0, 1.0),
    ("s", 0.5, 1.0),
    ("sw", 0.0, 1.0),
    ("w", 0.0, 0.5),
)

_CURSORS = {
    "nw": "size_fdiag",
    "se": "size_fdiag",
    "ne": "size_bdiag",
    "sw": "size_bdiag",
    "n": "size_ver",
    "s": "size_ver",
    "e": "size_hor",
    "w": "size_hor",
}


def handle_hit_radius(actual_scale: float) -> float:
    """手柄命中半径（画布单位），按缩放换算以维持固定屏幕像素。"""
    scale = max(1e-3, float(actual_scale))
    return (HANDLE_HIT_SCREEN_SIZE / 2.0) / scale


def selected_local_point(
    canvas_x: float,
    canvas_y: float,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    rotation_degrees: float = 0.0,
) -> Tuple[float, float]:
    """把画布坐标换算成选中框局部坐标（左上为 0,0）。"""
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    center_x = float(x) + width / 2.0
    center_y = float(y) + height / 2.0
    radians = float(rotation_degrees) * math.pi / 180.0
    offset_x = float(canvas_x) - center_x
    offset_y = float(canvas_y) - center_y
    return (
        math.cos(radians) * offset_x + math.sin(radians) * offset_y + width / 2.0,
        -math.sin(radians) * offset_x + math.cos(radians) * offset_y + height / 2.0,
    )


def handles_suppressed(width: float, height: float, actual_scale: float) -> bool:
    """选框小到手柄会盖住整个选框时，是否整体隐藏手柄。

    Photoshop 的行为：选框在屏幕上小到一定程度，就不再画缩放手柄，
    此时拖选框内部即可移动。否则 4 个角手柄各自的命中圆会把中心也吃掉，
    用户既缩放不了（太挤）又移动不了（中心被占）。
    """
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    radius = handle_hit_radius(actual_scale)
    # 对角线的一半 = 中心到角的距离。小于半径说明角手柄盖住了中心。
    half_diagonal = math.hypot(width, height) / 2.0
    return half_diagonal <= radius


def edge_handles_dropped(width: float, height: float, actual_scale: float) -> bool:
    """选框较小时是否要隐藏边中点手柄（保留 4 角）。

    缩放过低时 8 个手柄会叠在一起，Photoshop 优先保留 4 角、隐藏边中点。
    这里只在「确实会重叠」时才隐藏。
    """
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    radius = handle_hit_radius(actual_scale)
    return (width / 2.0 < radius * 2.0) or (height / 2.0 < radius * 2.0)


def visible_handles(
    width: float, height: float, actual_scale: float
) -> Tuple[Tuple[str, float, float], ...]:
    """当前应当显示（且可命中）的手柄集合。视觉与命中都用它。"""
    if handles_suppressed(width, height, actual_scale):
        return ()
    if edge_handles_dropped(width, height, actual_scale):
        return tuple(a for a in HANDLE_ANCHORS if len(a[0]) == 2)
    return HANDLE_ANCHORS


def handle_hit_test(
    local_x: float,
    local_y: float,
    width: float,
    height: float,
    actual_scale: float,
) -> Optional[str]:
    """返回命中的手柄名，未命中返回 None。

    命中区 = 以手柄中心为圆心、半径 ``HANDLE_HIT_SCREEN_SIZE/2`` 的圆。
    多个手柄同时命中时取最近的一个（小选框上相邻手柄会重叠，取近的才符合直觉）。
    """
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    radius = handle_hit_radius(actual_scale)

    best: Optional[str] = None
    best_dist = radius * radius
    for name, fx, fy in visible_handles(width, height, actual_scale):
        hx = fx * width
        hy = fy * height
        dx = local_x - hx
        dy = local_y - hy
        dist = dx * dx + dy * dy
        if dist <= best_dist:
            best_dist = dist
            best = name
    return best


def handle_cursor(handle: Optional[str]) -> Optional[str]:
    """手柄对应的光标形态（供 QML 映射成 Qt 枚举）。"""
    if not handle:
        return None
    return _CURSORS.get(handle)


def inside_selection(
    local_x: float,
    local_y: float,
    width: float,
    height: float,
    actual_scale: float,
) -> bool:
    """点是否落在选中框内（用于决定「拖内部=移动」还是「穿透」）。"""
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    # 内缩半个命中半径，避免和手柄区争抢
    slack = handle_hit_radius(actual_scale)
    return -slack <= local_x <= width + slack and -slack <= local_y <= height + slack
