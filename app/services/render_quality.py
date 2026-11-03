"""Shared render and export quality policy.

This module is intentionally small: it centralizes the decisions that must stay
identical across preview, single export, and batch export without forcing a
large renderer rewrite in one step.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Tuple

from PIL import Image


logger = logging.getLogger(__name__)

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
    """Composite transparent pixels over a solid background using the shared alpha path.

    性能：以前统一走 UnifiedAlphaCompositor.blend_normal，那是一条**整图 float64
    线性空间混合 + 抖动**的路径，专为「图层叠加要保色准」设计。但这里的需求只是
    「把透明区压到指定的纯色底上」，底是不透明的常量色，Source-Over 在这种前提下
    退化成一次普通 alpha 混合 —— Pillow 的 C 实现就够了。

    实测（1080x1350 RGBA → 白底 RGB）：
      线性 float64 路径 418 ms  →  Image.alpha_composite 9 ms（46×）
      像素差异：平均 0.01/255，最大 7/255，仅 0.10% 的像素差 >2（全在半透明边缘）。
    导出只做一次，9ms 与 418ms 的差别直接体现在批量导出的单张耗时上。

    若需要严格复现旧的线性空间结果，设环境变量 BTPW_LINEAR_FLATTEN=1。
    """
    if image.mode != "RGBA":
        return image.convert("RGB") if image.mode != "RGB" else image

    use_linear = str(os.environ.get("BTPW_LINEAR_FLATTEN", "0")).strip() == "1"
    if use_linear:
        bg_rgba = Image.new("RGBA", image.size, tuple(background) + (255,))
        try:
            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor

            return UnifiedAlphaCompositor.blend_normal(bg_rgba, image, 1.0).convert("RGB")
        except Exception:
            logger.warning("线性空间压平失败，回退 PIL 合成", exc_info=True)

    bg_rgba = Image.new("RGBA", image.size, tuple(background) + (255,))
    try:
        return Image.alpha_composite(bg_rgba, image).convert("RGB")
    except Exception:
        logger.warning("alpha_composite 压平失败，回退 paste", exc_info=True)
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
