"""High precision RGBA resampling helpers.

Pillow resizes straight-alpha RGBA in 8-bit space. That can leak hidden RGB
from transparent pixels, and premultiplying to an 8-bit image before resizing
can amplify low-alpha quantization into speckles. These helpers keep the
premultiplied channels in float until the final conversion back to RGBA.
"""

from typing import Tuple

import numpy as np
from PIL import Image


def _as_target_size(size: Tuple[int, int]) -> Tuple[int, int]:
    width, height = size
    return max(1, int(width)), max(1, int(height))


def _float_channel_to_image(channel: np.ndarray) -> Image.Image:
    return Image.fromarray(np.asarray(channel, dtype=np.float32))


def _resize_float_channel(channel: np.ndarray, size: Tuple[int, int], resample) -> np.ndarray:
    resized = _float_channel_to_image(channel).resize(size, resample)
    return np.asarray(resized, dtype=np.float32)


def _rotate_float_channel(
    channel: np.ndarray,
    angle: float,
    *,
    resample,
    expand: bool,
    fill: float,
) -> np.ndarray:
    rotated = _float_channel_to_image(channel).rotate(
        angle,
        resample=resample,
        expand=expand,
        fillcolor=float(fill),
    )
    return np.asarray(rotated, dtype=np.float32)


def _to_uint8_rgba(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    out = np.dstack((np.clip(rgb, 0.0, 1.0), np.clip(alpha, 0.0, 1.0)))
    return Image.fromarray(np.round(out * 255.0).astype(np.uint8), "RGBA")


def resize_rgba_premultiplied(
    image: Image.Image,
    size: Tuple[int, int],
    resample=Image.Resampling.LANCZOS,
) -> Image.Image:
    """Resize an image with float premultiplied alpha."""
    size = _as_target_size(size)
    if image is None:
        return None
    if image.size == size:
        return image
    if image.mode != "RGBA":
        return image.resize(size, resample)

    info = dict(getattr(image, "info", {}) or {})
    rgba = np.asarray(image, dtype=np.float32) / 255.0
    alpha = rgba[:, :, 3]

    if alpha.size and alpha.min() >= 1.0:
        result = image.resize(size, resample)
        if info:
            result.info.update(info)
        return result

    premul = rgba[:, :, :3] * alpha[:, :, None]
    resized_alpha = np.clip(_resize_float_channel(alpha, size, resample), 0.0, 1.0)
    resized_premul = np.dstack([
        _resize_float_channel(premul[:, :, channel], size, resample)
        for channel in range(3)
    ])

    rgb = np.zeros_like(resized_premul)
    mask = resized_alpha > 1e-6
    rgb[mask] = resized_premul[mask] / resized_alpha[mask, None]

    result = _to_uint8_rgba(rgb, resized_alpha)
    if info:
        result.info.update(info)
    return result


def rotate_rgba_premultiplied(
    image: Image.Image,
    angle: float,
    *,
    resample=Image.Resampling.BICUBIC,
    expand: bool = True,
    fillcolor=(0, 0, 0, 0),
) -> Image.Image:
    """Rotate an image with float premultiplied alpha."""
    if image is None:
        return None
    if image.mode != "RGBA":
        return image.rotate(angle, resample=resample, expand=expand, fillcolor=fillcolor)

    info = dict(getattr(image, "info", {}) or {})
    rgba = np.asarray(image, dtype=np.float32) / 255.0
    alpha = rgba[:, :, 3]
    premul = rgba[:, :, :3] * alpha[:, :, None]

    fill = tuple(fillcolor or (0, 0, 0, 0))
    fill_alpha = float(fill[3] if len(fill) > 3 else 255) / 255.0
    fill_rgb = np.array(fill[:3], dtype=np.float32) / 255.0
    fill_premul = fill_rgb * fill_alpha

    rotated_alpha = np.clip(
        _rotate_float_channel(
            alpha,
            angle,
            resample=resample,
            expand=expand,
            fill=fill_alpha,
        ),
        0.0,
        1.0,
    )
    rotated_premul = np.dstack([
        _rotate_float_channel(
            premul[:, :, channel],
            angle,
            resample=resample,
            expand=expand,
            fill=float(fill_premul[channel]),
        )
        for channel in range(3)
    ])

    rgb = np.zeros_like(rotated_premul)
    mask = rotated_alpha > 1e-6
    rgb[mask] = rotated_premul[mask] / rotated_alpha[mask, None]

    result = _to_uint8_rgba(rgb, rotated_alpha)
    if info:
        result.info.update(info)
    return result
