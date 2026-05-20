"""Unified export/encoding service.

Quality policy is centralized here so single-image export and batch export do
not silently diverge. The default profile is quality-first; destructive size
reduction such as PNG quantization only happens in the explicit ``size`` mode.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import os
import time
from typing import Optional

from PIL import Image

from app.services.render_quality import (
    get_quality_policy,
    normalize_export_format,
    normalize_quality_profile,
    prepare_image_for_export,
)


@dataclass(frozen=True)
class ExportJob:
    file_path: str
    file_format: str = ""
    quality_profile: str = "quality"  # quality | balanced | speed | size
    max_file_size_kb: int = 0
    jpeg_quality: int = 0
    png_compress_level: int = -1
    backend: str = "pillow"  # pillow | pyvips | auto
    allow_lossy_size_reduction: bool = False


@dataclass
class ExportReport:
    success: bool
    file_path: str
    elapsed: float = 0.0
    written_bytes: int = 0
    backend_used: str = "pillow"
    quality_profile: str = "quality"
    error: str = ""


class ExportService:
    """Image encoding and write-to-disk policy."""

    def save_image(self, image: Image.Image, job: ExportJob) -> ExportReport:
        start = time.time()
        file_format = normalize_export_format(job.file_format or os.path.splitext(job.file_path)[1].lstrip("."))
        quality_profile = normalize_quality_profile(job.quality_profile)
        policy = get_quality_policy(
            quality_profile,
            allow_lossy_png_size_reduction=job.allow_lossy_size_reduction,
        )
        out_dir = os.path.dirname(job.file_path) or "."
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        try:
            prepared = prepare_image_for_export(image, file_format, policy)

            if self._should_try_vips(job, file_format):
                try:
                    from app.utils.vips_export_engine import VipsExportEngine

                    if VipsExportEngine.save_image(
                        image=prepared,
                        file_path=job.file_path,
                        file_format=file_format,
                        io_profile=self._io_profile_for_quality(quality_profile),
                        jpeg_quality=self._jpeg_quality(job),
                        png_compress_level=self._png_level(job),
                        max_file_size_kb=job.max_file_size_kb,
                    ):
                        if int(job.max_file_size_kb or 0) > 0:
                            self._enforce_size_limit(prepared, job.file_path, file_format, job)
                        written = self._written_bytes(job.file_path)
                        return ExportReport(True, job.file_path, time.time() - start, written, "pyvips", quality_profile)
                except Exception:
                    pass

            self._save_with_pillow(prepared, job.file_path, file_format, job)

            if int(job.max_file_size_kb or 0) > 0:
                self._enforce_size_limit(prepared, job.file_path, file_format, job)

            written = self._written_bytes(job.file_path)
            return ExportReport(True, job.file_path, time.time() - start, written, "pillow", quality_profile)
        except Exception as e:
            return ExportReport(False, job.file_path, time.time() - start, 0, "pillow", quality_profile, str(e))

    def _save_with_pillow(self, image: Image.Image, file_path: str, file_format: str, job: ExportJob) -> None:
        profile = normalize_quality_profile(job.quality_profile)
        if file_format in ("jpg", "jpeg"):
            image.save(
                file_path,
                format="JPEG",
                quality=self._jpeg_quality(job),
                optimize=(profile != "speed"),
                progressive=(profile == "size"),
                subsampling=0 if profile == "quality" else -1,
            )
            return

        if file_format == "png":
            image.save(
                file_path,
                format="PNG",
                compress_level=self._png_level(job),
                optimize=(profile in ("quality", "balanced", "size")),
            )
            return

        if file_format == "bmp":
            image.save(file_path, format="BMP")
            return

        image.save(file_path)

    def _should_try_vips(self, job: ExportJob, file_format: str) -> bool:
        backend = str(job.backend or "pillow").lower()
        if backend not in ("auto", "pyvips", "vips"):
            return False
        if file_format not in ("jpg", "jpeg", "png", "webp"):
            return False
        return True

    def _jpeg_quality(self, job: ExportJob) -> int:
        if int(job.jpeg_quality or 0) > 0:
            return max(60, min(98, int(job.jpeg_quality)))
        profile = normalize_quality_profile(job.quality_profile)
        if profile == "speed":
            return 90
        if profile == "balanced":
            return 94
        if profile == "size":
            return 92
        return 96

    def _png_level(self, job: ExportJob) -> int:
        png_level = -1 if job.png_compress_level is None else int(job.png_compress_level)
        if png_level >= 0:
            return max(0, min(9, png_level))
        profile = normalize_quality_profile(job.quality_profile)
        if profile == "speed":
            return 1
        if profile == "size":
            return 9
        if profile == "balanced":
            return 4
        return 6

    def _io_profile_for_quality(self, quality_profile: str) -> str:
        if quality_profile == "speed":
            return "speed"
        if quality_profile == "size":
            return "size"
        return "balanced"

    def _enforce_size_limit(self, image: Image.Image, file_path: str, file_format: str, job: ExportJob) -> None:
        target = int(job.max_file_size_kb or 0) * 1024
        if target <= 0 or self._written_bytes(file_path) <= target:
            return

        if file_format in ("jpg", "jpeg"):
            low, high = 35, min(95, self._jpeg_quality(job))
            best = None
            for _ in range(7):
                q = (low + high) // 2
                buf = io.BytesIO()
                image.save(buf, format="JPEG", quality=q, optimize=True)
                if buf.tell() <= target:
                    best = buf.getvalue()
                    low = q + 1
                else:
                    high = q - 1
            if best is not None:
                with open(file_path, "wb") as f:
                    f.write(best)
            return

        if file_format == "png":
            best = None
            for colors in (256, 128, 64, 32):
                buf = io.BytesIO()
                quant = image.convert("P", palette=Image.ADAPTIVE, colors=colors)
                quant.save(buf, format="PNG", optimize=True)
                data = buf.getvalue()
                if best is None or len(data) < len(best):
                    best = data
                if len(data) <= target:
                    break
            if best is not None:
                with open(file_path, "wb") as f:
                    f.write(best)

    def _written_bytes(self, file_path: str) -> int:
        try:
            return int(os.path.getsize(file_path))
        except Exception:
            return 0


_export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service
