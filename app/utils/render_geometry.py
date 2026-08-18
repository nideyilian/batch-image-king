"""Pure geometry helpers for rendering."""

from __future__ import annotations


def normalize_angle_180(angle: float) -> float:
    """Normalize an angle to (-180, 180]."""
    value = float(angle)
    while value <= -180.0:
        value += 360.0
    while value > 180.0:
        value -= 360.0
    return value


def pick_min_delta_rotation(target_angle: float, reference_angle: float) -> float:
    """Pick an equivalent target angle with the smallest delta to reference."""
    ref = normalize_angle_180(reference_angle)
    best_delta = None
    best_abs = None
    for k in (-2, -1, 0, 1, 2):
        candidate = float(target_angle) + 180.0 * float(k)
        delta = normalize_angle_180(candidate - ref)
        if delta > 90.0:
            delta -= 180.0
        elif delta < -90.0:
            delta += 180.0
        abs_delta = abs(delta)
        if best_delta is None or abs_delta < best_abs:
            best_delta = delta
            best_abs = abs_delta
    if best_delta is None:
        return normalize_angle_180(ref)
    return normalize_angle_180(ref + best_delta)


def to_small_tilt_by_axis(raw_angle_deg: float, bbox_w: int, bbox_h: int) -> float:
    """Convert a principal-axis angle to a small tilt relative to the dominant axis."""
    angle = normalize_angle_180(raw_angle_deg)
    tilt_h = normalize_angle_180(angle)
    if tilt_h > 90.0:
        tilt_h -= 180.0
    elif tilt_h < -90.0:
        tilt_h += 180.0

    tilt_v = normalize_angle_180(angle - 90.0)
    if tilt_v > 90.0:
        tilt_v -= 180.0
    elif tilt_v < -90.0:
        tilt_v += 180.0

    abs_h = abs(float(tilt_h))
    abs_v = abs(float(tilt_v))
    if abs(abs_h - abs_v) <= 3.0:
        tilt = float(tilt_v if int(bbox_h) >= int(bbox_w) else tilt_h)
    else:
        tilt = float(tilt_h if abs_h < abs_v else tilt_v)

    if tilt > 90.0:
        tilt -= 180.0
    elif tilt < -90.0:
        tilt += 180.0
    return tilt
