"""
PyVips 导出引擎（可选依赖）。

目标：
- 在不改变现有渲染流程的前提下，加速图片编码/写盘阶段；
- 依赖不存在时自动回退，不影响功能可用性。
"""

from __future__ import annotations

from typing import Optional
import os
import numpy as np
from PIL import Image


class VipsExportEngine:
    """使用 pyvips 保存 PIL 图像。"""

    _pyvips = None
    _available: Optional[bool] = None

    @classmethod
    def is_available(cls) -> bool:
        if cls._available is not None:
            return bool(cls._available)
        try:
            import pyvips  # type: ignore
            cls._pyvips = pyvips
            cls._available = True
        except Exception:
            cls._pyvips = None
            cls._available = False
        return bool(cls._available)

    @classmethod
    def _pil_to_vips(cls, image: Image.Image):
        if not cls.is_available():
            raise RuntimeError("pyvips 不可用")

        img = image
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGBA")

        arr = np.array(img)
        if arr.ndim == 2:
            height, width = arr.shape
            bands = 1
        else:
            height, width, bands = arr.shape
        return cls._pyvips.Image.new_from_memory(
            arr.tobytes(),
            int(width),
            int(height),
            int(bands),
            "uchar",
        )

    @classmethod
    def save_image(
        cls,
        image: Image.Image,
        file_path: str,
        file_format: str,
        io_profile: str = "balanced",
        jpeg_quality: int = 0,
        png_compress_level: int = -1,
        max_file_size_kb: int = 0,
    ) -> bool:
        if not cls.is_available():
            return False

        fmt = str(file_format or "").lower()
        if fmt == "jpg":
            fmt = "jpeg"
        if fmt not in {"jpeg", "png", "webp"}:
            return False

        src = image
        try:
            from app.services.render_quality import get_quality_policy, prepare_image_for_export

            profile = "speed" if io_profile == "speed" else ("size" if io_profile == "size" else "quality")
            src = prepare_image_for_export(src, fmt, get_quality_policy(profile))
        except Exception:
            # pyvips 对 jpeg 不支持 alpha，统一提前处理
            if fmt == "jpeg" and src.mode == "RGBA":
                bg = Image.new("RGB", src.size, (255, 255, 255))
                bg.paste(src, mask=src.split()[-1])
                src = bg

        vip = cls._pil_to_vips(src)

        save_args = {}
        if fmt == "jpeg":
            q = jpeg_quality if jpeg_quality > 0 else (90 if io_profile == "speed" else 95)
            save_args["Q"] = max(60, min(98, int(q)))
            save_args["strip"] = True
            save_args["interlace"] = (io_profile != "speed")
        elif fmt == "png":
            level = png_compress_level if png_compress_level >= 0 else (1 if io_profile == "speed" else 6)
            save_args["compression"] = max(0, min(9, int(level)))
            save_args["strip"] = True
        elif fmt == "webp":
            q = jpeg_quality if jpeg_quality > 0 else (90 if io_profile == "speed" else 92)
            save_args["Q"] = max(60, min(98, int(q)))

        # 确保目录存在
        out_dir = os.path.dirname(file_path) or "."
        if out_dir and (not os.path.isdir(out_dir)):
            os.makedirs(out_dir, exist_ok=True)

        # JPEG 在有体积上限时，优先使用 vips 质量回退，避免“先vips再Pillow”双重编码
        if fmt == "jpeg" and int(max_file_size_kb or 0) > 0:
            target_bytes = int(max_file_size_kb) * 1024
            q_start = int(save_args.get("Q", 90))
            q_candidates = [q_start, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40]
            seen = set()
            best_buffer = None
            best_size = None
            for q in q_candidates:
                q_int = max(35, min(98, int(q)))
                if q_int in seen:
                    continue
                seen.add(q_int)
                trial_args = dict(save_args)
                trial_args["Q"] = q_int
                data = vip.write_to_buffer(".jpg", **trial_args)
                size = len(data)
                if size <= target_bytes:
                    if best_buffer is None or size > (best_size or 0):
                        best_buffer = data
                        best_size = size
                else:
                    # 若没有命中目标，保留最小体积结果作为兜底
                    if best_buffer is None and (best_size is None or size < best_size):
                        best_buffer = data
                        best_size = size
            if best_buffer is None:
                return False
            with open(file_path, "wb") as f:
                f.write(best_buffer)
            return True

        vip.write_to_file(file_path, **save_args)
        return True

