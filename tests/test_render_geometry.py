import pytest

from app.utils.render_geometry import (
    normalize_angle_180,
    pick_min_delta_rotation,
    to_small_tilt_by_axis,
)


@pytest.mark.unit
def test_normalize_angle_180_bounds():
    assert normalize_angle_180(181) == -179
    assert normalize_angle_180(-181) == 179
    assert normalize_angle_180(540) == 180


@pytest.mark.unit
def test_pick_min_delta_rotation_prefers_equivalent_small_rotation():
    assert pick_min_delta_rotation(170, 10) == -10
    assert pick_min_delta_rotation(-170, -10) == 10


@pytest.mark.unit
def test_to_small_tilt_by_axis_uses_bbox_orientation_for_ties():
    assert to_small_tilt_by_axis(45, bbox_w=100, bbox_h=20) == 45
    assert to_small_tilt_by_axis(45, bbox_w=20, bbox_h=100) == -45
