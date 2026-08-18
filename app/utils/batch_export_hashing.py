"""Hash helpers for batch export planning."""

from __future__ import annotations

import hashlib
import os
from typing import Mapping


def generate_deterministic_hash(layer_states: Mapping[int, str]) -> str:
    """Generate a stable combination hash from sorted layer indexes and basenames."""
    parts = []
    for layer_idx in sorted(layer_states.keys()):
        file_path = layer_states[layer_idx]
        parts.append(f"L{layer_idx}:{os.path.basename(file_path)}")
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]
