"""Preview interaction overlay.

When the user drags a layer on the canvas the new path now follows an
"overlay" model:

1. On drag start we capture a snapshot of the current composition pixmap
   *without* the active layers (or, for incremental renders, we just reuse the
   last full composition and remember the active layer indices).
2. While the mouse moves we only record a temporary ``QPoint`` delta.
3. ``paintEvent`` paints the static base pixmap first, then composites the
   active layers' surface caches on top using the temporary delta.  No
   document layer ``x/y`` is mutated, so no re-render is scheduled.
4. On release the delta is written back to the model in a single step,
   history is saved once and a single high-quality refresh is requested.

This isolates the visual feedback loop from the document model and the
preview render thread, so a 60 Hz mouse-move can no longer trigger a full
document re-render.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint
from PySide6.QtGui import QPixmap, QImage

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class _LayerSurface:
    """Lightweight snapshot of a layer's preview surface for the overlay."""

    layer_index: int
    base_x: int
    base_y: int
    width: int
    height: int
    image: Optional[Image.Image] = None  # RGBA premultiplied, full-resolution


@dataclass
class InteractionOverlayState:
    """Mutable state for the active drag/resize/rotate overlay session."""

    active: bool = False
    base_pixmap: Optional[QPixmap] = None
    base_composition_image: Optional[Image.Image] = None
    delta: QPoint = field(default_factory=lambda: QPoint(0, 0))
    surfaces: Dict[int, _LayerSurface] = field(default_factory=dict)
    layer_indices: List[int] = field(default_factory=list)
    kind: str = "move"  # "move" | "resize" | "rotate" | "corner_radius"
    started_at_ms: float = 0.0
    # 阶段 3：尺寸/节点/圆角临时态
    geometry_overrides: Dict[int, Dict[str, float]] = field(default_factory=dict)
    corner_radius_overrides: Dict[int, int] = field(default_factory=dict)
    vector_node_overrides: List = field(default_factory=list)  # 简单可 JSON 序列化的节点
    vector_handle_overrides: List = field(default_factory=list)

    def reset(self) -> None:
        self.active = False
        self.base_pixmap = None
        self.base_composition_image = None
        self.delta = QPoint(0, 0)
        self.surfaces.clear()
        self.layer_indices.clear()
        self.kind = "move"
        self.started_at_ms = 0.0
        self.geometry_overrides.clear()
        self.corner_radius_overrides.clear()
        self.vector_node_overrides = []
        self.vector_handle_overrides = []

    def is_active(self) -> bool:
        return self.active

    def apply_overrides_to_model(self):
        """阶段 3：释放时一次性把临时 geometry / 圆角 / 路径写回模型。

        不会触发额外的 history 快照；调用方负责在写回前/后控制
        ``Document.save_state`` 与重渲染。
        """
        if not self.active:
            return
        # geometry_overrides 通过调用方在写回时读取；这里只做必要的 round-trip
        return None


def pil_to_qimage(image: Image.Image) -> QImage:
    """Convert a PIL image to a QImage without going through ImageQt (we always have RGBA)."""
    if image is None:
        return QImage()
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        image.width,
        image.height,
        image.width * 4,
        QImage.Format_RGBA8888,
    )
    # ``data`` is a Python bytes object; QImage references it for its lifetime.
    # Qt copies the data internally for a QImage created from raw buffer so we
    # can let ``data`` be released after this call.
    return qimage.copy()


def make_pixmap_from_image(image: Image.Image) -> QPixmap:
    """Build a QPixmap from a PIL image (always RGBA)."""
    if image is None:
        return QPixmap()
    qimage = pil_to_qimage(image)
    return QPixmap.fromImage(qimage)
