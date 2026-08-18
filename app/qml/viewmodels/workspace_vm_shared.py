"""WorkspaceViewModel 共享常量与辅助类（P1-4 拆分）。

从 ``workspace_view_model.py`` 迁出的模块级常量与辅助类，供主类与后续各 mixin
复用，避免循环导入。此处内容为原样搬迁，语义不变。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from app.models.document import Document
from app.models.layer_new import Layer
from app.models.layer_properties import ShapeType

logger = logging.getLogger(__name__)


_BLEND_MODES = {
    "normal": (0, "正常"),
    "multiply": (1, "正片叠底"),
    "screen": (2, "滤色"),
    "overlay": (3, "叠加"),
    "soft_light": (4, "柔光"),
    "hard_light": (5, "强光"),
    "color_dodge": (6, "颜色减淡"),
    "color_burn": (7, "颜色加深"),
    "darken": (8, "变暗"),
    "lighten": (9, "变亮"),
    "difference": (10, "差值"),
    "exclusion": (11, "排除"),
    "hue": (12, "色相"),
    "saturation": (13, "饱和度"),
    "color": (14, "颜色"),
    "luminosity": (15, "明度"),
}
_BLEND_MODE_IDS = {value: key for key, (value, _label) in _BLEND_MODES.items()}

_SHAPE_TYPES = {
    "rectangle": (ShapeType.RECTANGLE, "矩形"),
    "right_trapezoid": (ShapeType.RIGHT_TRAPEZOID, "直角梯形"),
    "circle": (ShapeType.CIRCLE, "圆形"),
    "pentagon": (ShapeType.PENTAGON, "正五边形"),
    "hexagon": (ShapeType.HEXAGON, "正六边形"),
}

_FIT_MODES = {
    "crop": (Layer.FIT_SMART_CROP, "填满裁剪"),
    "fit": (Layer.FIT_SMART_FIT, "完整显示"),
    "original": (Layer.FIT_NO_SCALE, "原始尺寸"),
}
_FIT_MODE_IDS = {value: key for key, (value, _label) in _FIT_MODES.items()}

_CROP_DIRECTIONS = {
    "center": (Layer.CROP_CENTER, "居中"),
    "top": (Layer.CROP_TOP, "顶部"),
    "bottom": (Layer.CROP_BOTTOM, "底部"),
    "left": (Layer.CROP_LEFT, "左侧"),
    "right": (Layer.CROP_RIGHT, "右侧"),
}
_CROP_DIRECTION_IDS = {
    value: key for key, (value, _label) in _CROP_DIRECTIONS.items()
}

_TEXT_ALIGNMENTS = {
    "left": ("LEFT", "左对齐"),
    "center": ("CENTER", "居中"),
    "right": ("RIGHT", "右对齐"),
}
_TEXT_ALIGNMENT_IDS = {
    value: key for key, (value, _label) in _TEXT_ALIGNMENTS.items()
}
_TEXT_GRADIENT_TYPES = {
    "linear": ("LINEAR", "线性"),
    "radial": ("RADIAL", "径向"),
    "angular": ("ANGULAR", "角度"),
}
_TEXT_GRADIENT_TYPE_IDS = {
    value: key for key, (value, _label) in _TEXT_GRADIENT_TYPES.items()
}
_TEXT_GRADIENT_DIRECTIONS = {
    "horizontal": ("HORIZONTAL", "水平"),
    "vertical": ("VERTICAL", "垂直"),
    "diagonal_lr": ("DIAGONAL_LR", "左上到右下"),
    "diagonal_rl": ("DIAGONAL_RL", "右上到左下"),
}
_TEXT_GRADIENT_DIRECTION_IDS = {
    value: key for key, (value, _label) in _TEXT_GRADIENT_DIRECTIONS.items()
}

_COMMON_STYLE_ATTRIBUTES = (
    "opacity",
    "blend_mode",
    "corner_radius",
    "stroke_enabled",
    "stroke_width",
    "stroke_color",
    "stroke_type",
    "rotation",
    "flip_horizontal",
    "flip_vertical",
    "color_overlay_enabled",
    "color_overlay_color",
    "color_overlay_opacity",
    "gradient_overlay_enabled",
    "gradient_overlay_colors",
    "gradient_overlay_opacity",
    "gradient_overlay_angle",
)

_TEXT_STYLE_ATTRIBUTES = (
    "font_family",
    "font_face",
    "font_size",
    "font_style",
    "text_color",
    "text_align",
    "line_spacing",
    "letter_spacing",
    "text_box_padding",
    "auto_fit_text_box",
    "vertical_layout",
    "gradient_enabled",
    "gradient_type",
    "gradient_direction",
    "gradient_start_color",
    "gradient_end_color",
    "gradient_center_x",
    "gradient_center_y",
    "background_enabled",
    "background_color",
    "background_padding",
    "shadow_enabled",
    "shadow_offset_x",
    "shadow_offset_y",
    "shadow_blur",
    "shadow_color",
    "glow_enabled",
    "glow_strength",
    "glow_radius",
    "glow_color",
)


def _pil_to_qimage(image) -> QImage:
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format_RGBA8888,
    ).copy()


class _PreviewTaskSignals(QObject):
    finished = Signal(int, int, bool, object, str, float)


class _PreviewTask(QRunnable):
    def __init__(
        self,
        request_id: int,
        generation: int,
        document: Document,
        *,
        snapshot_data=None,
        interactive_low_quality: bool,
        active_layer_index: int,
        omit_active_layer: bool,
        cancel_token,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.generation = generation
        self.document = document
        self.snapshot_data = snapshot_data
        self.interactive_low_quality = bool(interactive_low_quality)
        self.active_layer_index = int(active_layer_index)
        self.omit_active_layer = bool(omit_active_layer)
        self.cancel_token = cancel_token
        self.signals = _PreviewTaskSignals()

    def _emit_finished(self, qimage, error: str, elapsed: float) -> None:
        try:
            self.signals.finished.emit(
                self.request_id,
                self.generation,
                self.interactive_low_quality,
                qimage,
                error,
                elapsed,
            )
        except RuntimeError:
            # 应用退出时 Workspace 可能先于线程池任务销毁。
            pass

    def run(self) -> None:
        from app.models.document_serializer import DocumentSerializer
        from app.services.preview_render_service import render_preview_to_image

        try:
            document = self.document
            if isinstance(self.snapshot_data, dict):
                document = Document(parent=None)
                if not DocumentSerializer.restore_document_data(document, self.snapshot_data):
                    raise RuntimeError("无法恢复预览文档快照")
                document._is_batch_export_running = False
                document._export_canceled = False
                document._needs_cache_refresh = True
            result = render_preview_to_image(
                document,
                force_refresh=not self.interactive_low_quality,
                interactive_low_quality=self.interactive_low_quality,
                active_layer_index=self.active_layer_index,
                omit_active_layer=self.omit_active_layer,
                cancel_token=self.cancel_token,
            )
            if result.cancelled or getattr(self.cancel_token, "cancelled", False):
                self._emit_finished(None, "", float(result.elapsed))
                return
            qimage = _pil_to_qimage(result.image) if result.image is not None else None
            self._emit_finished(qimage, str(result.error or ""), float(result.elapsed))
        except Exception as error:
            self._emit_finished(None, str(error), 0.0)
