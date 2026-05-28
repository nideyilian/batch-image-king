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

            if file_format in ("jpg", "jpeg") and int(job.max_file_size_kb or 0) > 0:
                written = self._save_size_limited_jpeg(prepared, job.file_path, job, source_image=image)
                return ExportReport(True, job.file_path, time.time() - start, written, "pillow", quality_profile)

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
                subsampling=0 if profile in ("quality", "balanced") else -1,
                **self._jpeg_metadata_save_kwargs(image),
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

    def _jpeg_metadata_save_kwargs(self, image: Image.Image, source_image: Optional[Image.Image] = None) -> dict:
        """Keep color profile metadata when Pillow provides one."""
        icc_profile = None
        try:
            icc_profile = (getattr(image, "info", {}) or {}).get("icc_profile")
        except Exception:
            icc_profile = None
        if icc_profile is None and source_image is not None:
            try:
                icc_profile = (getattr(source_image, "info", {}) or {}).get("icc_profile")
            except Exception:
                icc_profile = None
        return {"icc_profile": icc_profile} if icc_profile else {}

    def _encode_jpeg_to_bytes(
        self,
        image: Image.Image,
        quality: int,
        *,
        source_image: Optional[Image.Image] = None,
    ) -> bytes:
        """Encode JPEG in memory using color-preserving 4:4:4 sampling."""
        buf = io.BytesIO()
        image.save(
            buf,
            format="JPEG",
            quality=max(1, min(98, int(quality))),
            optimize=True,
            progressive=False,
            subsampling=0,
            **self._jpeg_metadata_save_kwargs(image, source_image),
        )
        return buf.getvalue()

    def _save_size_limited_jpeg(
        self,
        image: Image.Image,
        file_path: str,
        job: ExportJob,
        *,
        source_image: Optional[Image.Image] = None,
    ) -> int:
        """Find the highest 4:4:4 JPEG quality that fits, then write once."""
        target = int(job.max_file_size_kb or 0) * 1024
        high = min(98, max(1, self._jpeg_quality(job)))
        low = 35

        best_data = self._encode_jpeg_to_bytes(image, high, source_image=source_image)
        if target <= 0 or len(best_data) <= target:
            with open(file_path, "wb") as f:
                f.write(best_data)
            return len(best_data)

        best_under_target = None
        search_low = low
        search_high = high - 1
        while search_low <= search_high:
            q = (search_low + search_high) // 2
            data = self._encode_jpeg_to_bytes(image, q, source_image=source_image)
            if len(data) <= target:
                best_under_target = data
                search_low = q + 1
            else:
                search_high = q - 1

        if best_under_target is None:
            # Keep 4:4:4 sampling even in the fallback. Lowering quality hurts less
            # than silently switching chroma subsampling for text and saturated colors.
            best_under_target = self._encode_jpeg_to_bytes(image, 25, source_image=source_image)

        with open(file_path, "wb") as f:
            f.write(best_under_target)
        return len(best_under_target)

    def _enforce_size_limit(self, image: Image.Image, file_path: str, file_format: str, job: ExportJob) -> None:
        target = int(job.max_file_size_kb or 0) * 1024
        if target <= 0 or self._written_bytes(file_path) <= target:
            return

        if file_format in ("jpg", "jpeg"):
            self._save_size_limited_jpeg(image, file_path, job)
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
