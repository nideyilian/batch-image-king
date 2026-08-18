"""Shared render and export quality policy.

This module is intentionally small: it centralizes the decisions that must stay
identical across preview, single export, and batch export without forcing a
large renderer rewrite in one step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PIL import Image


SUPPORTED_QUALITY_PROFILES = {"quality", "balanced", "speed", "size"}


@dataclass(frozen=True)
class QualityPolicy:
    profile: str = "quality"
    resample_filter: Image.Resampling = Image.Resampling.LANCZOS
    jpeg_background: Tuple[int, int, int] = (255, 255, 255)
    preserve_png_alpha: bool = True
    allow_lossy_png_size_reduction: bool = False


def normalize_quality_profile(profile: object, default: str = "quality") -> str:
    value = str(profile or default).strip().lower()
    if value in SUPPORTED_QUALITY_PROFILES:
        return value
    return default


def get_quality_policy(profile: object = "quality", *, allow_lossy_png_size_reduction: bool = False) -> QualityPolicy:
    normalized = normalize_quality_profile(profile)
    if normalized == "speed":
        resample_filter = Image.Resampling.BICUBIC
    else:
        resample_filter = Image.Resampling.LANCZOS
    return QualityPolicy(
        profile=normalized,
        resample_filter=resample_filter,
        allow_lossy_png_size_reduction=bool(allow_lossy_png_size_reduction),
    )


def normalize_export_format(file_format: object, default: str = "png") -> str:
    fmt = str(file_format or default).lower().lstrip(".")
    return "jpeg" if fmt == "jpg" else fmt


def composite_over_background(image: Image.Image, background: Tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """Composite transparent pixels over a solid background using the shared alpha path."""
    if image.mode != "RGBA":
        return image.convert("RGB") if image.mode != "RGB" else image

    bg_rgba = Image.new("RGBA", image.size, tuple(background) + (255,))
    try:
        from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor

        return UnifiedAlphaCompositor.blend_normal(bg_rgba, image.convert("RGBA"), 1.0).convert("RGB")
    except Exception:
        rgb = Image.new("RGB", image.size, background)
        rgb.paste(image, mask=image.split()[-1])
        return rgb


def prepare_image_for_export(image: Image.Image, file_format: str, policy: QualityPolicy) -> Image.Image:
    """Apply the common output-mode policy before encoding."""
    if image is None:
        raise ValueError("图像对象为空")

    fmt = normalize_export_format(file_format)
    if fmt in ("jpg", "jpeg"):
        return composite_over_background(image, policy.jpeg_background)

    if fmt == "png" and policy.preserve_png_alpha and image.mode != "RGBA":
        return image.convert("RGBA")

    return image
