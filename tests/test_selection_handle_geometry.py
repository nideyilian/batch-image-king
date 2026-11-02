"""选中框手柄的命中几何，按 Photoshop 移动工具规则。

两条核心规则（都曾被违反）：
1. 手柄只有 8 个离散方块。边框线本身不可缩放，点击穿透到下层图层。
   旧实现按「距边框 10 屏幕像素内」判定，整条边都是热区，
   与画出来的 8 个方块对不上——看到的热区和实际能拖的区域是两套东西。
2. 选框过小时（缩放过低）8 个手柄会盖住中心，优先保留 4 个角，
   边中点隐藏；视觉与命中必须同时隐藏。
"""

from __future__ import annotations

import pytest

from app.utils.selection_handle_geometry import (
    HANDLE_ANCHORS,
    HANDLE_HIT_SCREEN_SIZE,
    edge_handles_dropped,
    handles_suppressed,
    visible_handles,
    handle_cursor,
    handle_hit_radius,
    handle_hit_test,
    inside_selection,
    selected_local_point,
)


W, H = 400.0, 300.0   # 常规图层尺寸
SCALE = 1.0


# ------------------------------------------------------------ 8 个离散手柄


def test_all_eight_handles_hit_at_their_centers():
    for name, fx, fy in HANDLE_ANCHORS:
        got = handle_hit_test(fx * W, fy * H, W, H, SCALE)
        assert got == name, f"{name} 手柄中心未命中"


def test_edge_line_between_handles_passes_through():
    """边框线上、但不在手柄方块内的点必须返回 None（穿透）。"""
    # 右边框：手柄只有 (400,150)，上下都不是手柄
    for y in (20.0, 60.0, 100.0, 200.0, 250.0, 280.0):
        assert handle_hit_test(W, y, W, H, SCALE) is None, f"y={y} 不该命中手柄"
    # 下边框：手柄只有 (200,300)
    for x in (20.0, 80.0, 150.0, 250.0, 320.0, 380.0):
        assert handle_hit_test(x, H, W, H, SCALE) is None, f"x={x} 不该命中手柄"


def test_inside_selection_is_not_a_handle():
    assert handle_hit_test(W / 2, H / 2, W, H, SCALE) is None


def test_outside_selection_is_not_a_handle():
    radius = handle_hit_radius(SCALE)
    assert handle_hit_test(W + radius * 3, H / 2, W, H, SCALE) is None
    assert handle_hit_test(W / 2, H + radius * 3, W, H, SCALE) is None


def test_handle_hit_area_is_small_not_a_band():
    """手柄命中区是小块，不是沿整条边延伸的带子。"""
    radius = handle_hit_radius(SCALE)
    diameter = radius * 2
    # 上边中点手柄中心 (200, 0)：横移一个半径内命中，超一个直径就不命中
    assert handle_hit_test(200 + radius * 0.9, 0, W, H, SCALE) == "n"
    assert handle_hit_test(200 + diameter, 0, W, H, SCALE) is None


def test_handle_hit_radius_scales_with_zoom():
    """命中半径随缩放反向变化，屏幕上始终约为 HANDLE_HIT_SCREEN_SIZE/2。"""
    for scale in (0.15, 0.3, 0.5, 1.0, 2.0):
        r = handle_hit_radius(scale)
        assert r * scale == pytest.approx(HANDLE_HIT_SCREEN_SIZE / 2.0)


def test_nearest_handle_wins_when_overlapping():
    """相邻手柄重叠时取最近的一个，而不是固定优先级。"""
    small = 10.0
    got = handle_hit_test(0.0, 0.0, small, small, 1.0)
    assert got == "nw"


# ------------------------------------------------------------ 小选框处理


@pytest.mark.parametrize("size,scale,expect_drop", [
    (400.0, 1.0, False),    # 屏幕 400px，不重叠
    (40.0, 0.3, True),      # 屏幕 12px，重叠
    (20.0, 0.2, True),      # 屏幕 4px，严重重叠
    (400.0, 0.1, False),    # 屏幕 40px，还够
])
def test_edge_handles_dropped_only_when_overlapping(size, scale, expect_drop):
    assert edge_handles_dropped(size, size, scale) is expect_drop


def test_small_selection_center_stays_free_of_handles():
    """选框被打得很小时，中心不能被手柄覆盖，否则拖不动。"""
    for size, scale in ((40.0, 0.3), (20.0, 0.2), (12.0, 0.15)):
        got = handle_hit_test(size / 2, size / 2, size, size, scale)
        assert got is None, f"{size}px @{scale} 中心被 {got} 覆盖"


def test_tiny_selection_suppresses_all_handles():
    """小到角手柄会盖住中心时，整体隐藏手柄（此时靠拖内部移动）。"""
    for size, scale in ((20.0, 0.2), (12.0, 0.15)):
        assert handles_suppressed(size, size, scale), f"{size}px @{scale} 应整体隐藏"
        assert visible_handles(size, size, scale) == ()


def test_normal_selection_keeps_all_eight_handles():
    assert visible_handles(W, H, SCALE) == list(HANDLE_ANCHORS) or len(
        visible_handles(W, H, SCALE)
    ) == 8


def test_small_selection_keeps_corner_handles():
    """变小后 4 个角仍然可缩放。"""
    size, scale = 40.0, 0.3
    assert edge_handles_dropped(size, size, scale)
    for name, fx, fy in HANDLE_ANCHORS:
        if len(name) != 2:
            continue
        assert handle_hit_test(fx * size, fy * size, size, size, scale) == name


# ------------------------------------------------------------ 光标


def test_cursor_mapping():
    assert handle_cursor("nw") == handle_cursor("se") == "size_fdiag"
    assert handle_cursor("ne") == handle_cursor("sw") == "size_bdiag"
    assert handle_cursor("n") == handle_cursor("s") == "size_ver"
    assert handle_cursor("e") == handle_cursor("w") == "size_hor"
    assert handle_cursor(None) is None
    assert handle_cursor("") is None


# ------------------------------------------------------------ 旋转


def test_rotation_maps_canvas_point_into_local_space():
    kwargs = {"x": 0.0, "y": 0.0, "width": W, "height": H}

    lx, ly = selected_local_point(200, 50, rotation_degrees=0, **kwargs)
    assert (lx, ly) == pytest.approx((200.0, 50.0))

    # 90° 是逆旋转：画布上方的点落到局部左侧，x 缩短为一半
    lx, ly = selected_local_point(200, 50, rotation_degrees=90, **kwargs)
    assert (lx, ly) == pytest.approx((100.0, 150.0), abs=1e-6)

    for rotation in (0, 90, 180, 270, 37.5):
        lx, ly = selected_local_point(200, 150, rotation_degrees=rotation, **kwargs)
        assert (lx, ly) == pytest.approx((200.0, 150.0), abs=1e-6)


def test_rotated_corner_handle_hits_after_rotation():
    """旋转 90° 后，各角在画布上的新位置仍命中对应手柄。

    400x300 的选框绕中心 (200,150) 逆时针转 90°：
    nw(0,0) -> (350,-50)、ne(400,0) -> (350,350)、
    sw(0,300) -> (50,-50)、se(400,300) -> (50,350)
    """
    def at(cx, cy, rotation):
        lx, ly = selected_local_point(
            cx, cy, x=0.0, y=0.0, width=W, height=H, rotation_degrees=rotation
        )
        return handle_hit_test(lx, ly, W, H, SCALE)

    assert at(200, 0, 0) == "n"
    assert at(0, 0, 0) == "nw"
    assert at(350, -50, 90) == "nw"
    assert at(50, 350, 90) == "se"
    assert at(350, 350, 90) == "ne"
    assert at(50, -50, 90) == "sw"


# ------------------------------------------------------------ 选框内判定


def test_inside_selection_bounds():
    assert inside_selection(W / 2, H / 2, W, H, SCALE)
    assert inside_selection(0, 0, W, H, SCALE)
    assert not inside_selection(-50, H / 2, W, H, SCALE)
    assert not inside_selection(W + 50, H / 2, W, H, SCALE)


# ------------------------------------------------- QML / Python 一致性


def _qml_source() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "app" / "qml" / "Main.qml").read_text(
        encoding="utf-8"
    )


def _qml_handle_body() -> str:
    source = _qml_source()
    start = source.index("function handleAt(")
    end = source.index("\n                }", start)
    return source[start:end]


def test_qml_uses_discrete_handles_not_edge_band():
    """QML 不能再退回「距边框 N 像素」的带式判定。"""
    body = _qml_handle_body()
    assert "handleAnchors" in body
    for band_marker in ("nearLeft", "nearRight", "nearTop", "nearBottom"):
        assert band_marker not in body


def test_qml_hit_size_matches_python_constant():
    source = _qml_source()
    assert f"handleHitScreenSize: {int(HANDLE_HIT_SCREEN_SIZE)}" in source


def test_qml_drops_edge_handles_when_overlapping():
    body = _qml_handle_body()
    assert "dropEdgeHandles" in body
    assert "anchor.edge.length === 1" in body


def test_qml_visual_hides_dropped_handles():
    """视觉绘制也必须隐藏被丢弃的边中点手柄。"""
    source = _qml_source()
    assert "edgeDropped" in source
    assert "&& !edgeDropped" in source


def test_qml_anchor_order_matches_python():
    """QML 的 handleAnchors 顺序与比例位置必须和 Python 的 HANDLE_ANCHORS 一致。"""
    import re

    source = _qml_source()
    start = source.index("readonly property var handleAnchors:")
    block = source[start:source.index("]", start)]
    found = re.findall(
        r'\{edge:\s*"(\w+)",\s*fx:\s*([\d.]+),\s*fy:\s*([\d.]+)\}', block
    )
    assert len(found) == 8
    qml_anchors = [(n, float(fx), float(fy)) for n, fx, fy in found]
    assert qml_anchors == list(HANDLE_ANCHORS)


# ------------------------------------------------- 单击不产生几何变化


def test_qml_commit_is_skipped_without_real_drag():
    """QML 的 commitTransform 必须在未真正拖动时跳过，否则单击会吸附移位。"""
    source = _qml_source()
    start = source.index("function commitTransform()")
    body = source[start:source.index("\n                }", start)]
    assert "transformDirty" in body
    assert "if (!wasDirty)" in body


def test_qml_update_transform_has_dead_zone():
    """updateTransform 需要死区，避免把单击抖动当成拖动。"""
    source = _qml_source()
    start = source.index("function updateTransform(")
    body = source[start:source.index("\n                }", start)]
    assert "transformDirty" in body
    assert "deadZone" in body
