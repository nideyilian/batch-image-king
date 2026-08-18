"""Pure layout helpers for text rendering."""

from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image


def normalize_auto_fit_padding(
    image: Image.Image,
    padding: int,
) -> Tuple[Image.Image, Optional[Tuple[int, int]]]:
    """Crop non-transparent content and restore uniform padding around it."""
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        return image, None

    pad = max(0, int(padding))
    left, top, right, bottom = bbox
    content_width = max(1, right - left)
    content_height = max(1, bottom - top)
    target_width = max(1, content_width + pad * 2)
    target_height = max(1, content_height + pad * 2)

    already_normalized = (
        image.width == target_width
        and image.height == target_height
        and left == pad
        and top == pad
    )
    if already_normalized:
        return image, (target_width, target_height)

    cropped = image.crop(bbox)
    normalized = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    normalized.paste(cropped, (pad, pad))
    return normalized, (target_width, target_height)
