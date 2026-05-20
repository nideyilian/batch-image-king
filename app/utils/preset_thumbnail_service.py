"""Thumbnail generation and caching for preset cards."""

import os
import pickle
from PIL import Image, ImageDraw, ImageFont

from app.utils.preset_document_loader import documents_from_preset_data


class PresetThumbnailService:
    """Generate square thumbnails for preset store cards."""

    def __init__(self, preset_manager, size=320):
        self.preset_manager = preset_manager
        self.size = int(size)
        self.thumbnail_dir = os.path.join(self.preset_manager.get_presets_dir(), "thumbnails")
        os.makedirs(self.thumbnail_dir, exist_ok=True)

    def get_thumbnail_path(self, preset_id):
        preset_path = os.path.join(self.preset_manager.get_presets_dir(), f"{preset_id}.cmp")
        thumb_path = os.path.join(self.thumbnail_dir, f"{preset_id}.png")
        if not os.path.exists(preset_path):
            return self._placeholder(preset_id, "预设文件不存在")

        try:
            if os.path.exists(thumb_path) and os.path.getmtime(thumb_path) >= os.path.getmtime(preset_path):
                return thumb_path
        except OSError:
            pass

        try:
            image = self._render_preset_preview(preset_path)
            if image is None:
                summary = self.preset_manager.get_preset_summary(preset_id) or {}
                image = self._build_placeholder(
                    summary.get('name', '预设'),
                    self._format_summary(summary)
                )
            image = self._to_square(image)
            image.save(thumb_path, "PNG")
            self._save_thumbnail_meta(preset_id, thumb_path)
            return thumb_path
        except Exception as exc:
            return self._placeholder(preset_id, f"缩略图生成失败\n{exc}")

    def _render_preset_preview(self, preset_path):
        with open(preset_path, "rb") as preset_file:
            preset_data = pickle.load(preset_file)

        documents = documents_from_preset_data(preset_data)
        if not documents:
            return None

        try:
            from app.utils.fast_renderer import get_global_fast_renderer
            preview = get_global_fast_renderer().render_preview(documents[0], force_refresh=True)
        except Exception:
            preview = documents[0].render_document() if hasattr(documents[0], "render_document") else None

        if preview is None:
            return None
        return preview.convert("RGBA")

    def _to_square(self, image):
        image = image.convert("RGBA")
        image.thumbnail((self.size, self.size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (self.size, self.size), (30, 35, 42, 255))
        x = (self.size - image.width) // 2
        y = (self.size - image.height) // 2
        canvas.alpha_composite(image, (x, y))
        return canvas.convert("RGB")

    def _placeholder(self, preset_id, message):
        thumb_path = os.path.join(self.thumbnail_dir, f"{preset_id}.png")
        image = self._build_placeholder("预设", message)
        image.save(thumb_path, "PNG")
        return thumb_path

    def _build_placeholder(self, title, subtitle):
        image = Image.new("RGB", (self.size, self.size), (28, 32, 39))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("msyh.ttc", 18)
            small_font = ImageFont.truetype("msyh.ttc", 13)
        except Exception:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        draw.rectangle((0, 0, self.size - 1, self.size - 1), outline=(66, 76, 88), width=2)
        draw.text((18, 22), str(title)[:18], fill=(232, 236, 241), font=font)
        y = 72
        for line in str(subtitle).splitlines()[:5]:
            draw.text((18, y), line[:26], fill=(156, 168, 181), font=small_font)
            y += 24
        return image

    def _format_summary(self, summary):
        doc_count = summary.get('document_count', 0)
        sizes = " / ".join(summary.get('canvas_sizes', [])[:2]) or "未知尺寸"
        layers = summary.get('total_layers', 0)
        return f"{doc_count} 个标签页\n{sizes}\n{layers} 个图层"

    def _save_thumbnail_meta(self, preset_id, thumb_path):
        try:
            if preset_id in self.preset_manager.presets_index:
                self.preset_manager.presets_index[preset_id]['thumbnail_path'] = thumb_path
                self.preset_manager._save_index()
        except Exception:
            pass
