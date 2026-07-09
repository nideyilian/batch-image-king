"""Small helpers for render cache key construction."""

from __future__ import annotations

import hashlib
from typing import Iterable


def stable_md5(parts: Iterable[object]) -> str:
    """Return an md5 digest for a pipe-joined sequence of key parts."""
    return hashlib.md5("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def build_layer_positions_key(layer: object, document: object) -> str:
    """Build the cache key for clone/fill position calculations."""
    parts = [
        f"canvas:{getattr(document, 'canvas_width', 0)}x{getattr(document, 'canvas_height', 0)}",
        f"base:{getattr(layer, 'x', 0)},{getattr(layer, 'y', 0)}",
        f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
        f"clone:{int(bool(getattr(layer, 'clone_enabled', False)))}",
        f"fill:{int(bool(getattr(layer, 'clone_fill_enabled', False)))}",
        f"fill_spacing:{getattr(layer, 'clone_fill_spacing', 0)}",
        f"fill_angle:{float(getattr(layer, 'clone_fill_angle', 0.0)):.3f}",
        f"fill_mode:{getattr(layer, 'clone_fill_mode', 'grid')}",
        f"fill_margin:{getattr(layer, 'clone_fill_margin', 0)}",
        f"mirror:{getattr(layer, 'clone_mirror_mode', 'none')}",
        f"rnd_dx:{getattr(layer, '_current_random_offset_x', 0)}",
        f"rnd_dy:{getattr(layer, '_current_random_offset_y', 0)}",
        f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
        f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
    ]
    return stable_md5(parts)
