from __future__ import annotations

import copy
import logging
import math
import os
from pathlib import Path
import re
import threading
from typing import Optional
import uuid

from PySide6.QtCore import QObject, QPointF, Property, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage, QPainterPath

from app.models.document import Document
from app.models.layer_group import LayerGroup
from app.models.layer_new import Layer
from app.models.layer_properties import ShapeType
from app.models.shaped_layer_new import ShapedLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.layer_list_model import LayerListModel
from app.utils.preview_render_token import PreviewRenderTokenSource
from app.utils.layer_tree import (
    child_indices_for_group,
    expand_group_indices,
    get_parent_group_id,
    group_bounds,
    is_effectively_locked,
    is_effectively_visible,
    is_layer_group,
    set_parent_group_id,
)


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
        cancel_token,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.generation = generation
        self.document = document
        self.snapshot_data = snapshot_data
        self.interactive_low_quality = bool(interactive_low_quality)
        self.active_layer_index = int(active_layer_index)
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
                cancel_token=self.cancel_token,
            )
            if result.cancelled or getattr(self.cancel_token, "cancelled", False):
                self._emit_finished(None, "", float(result.elapsed))
                return
            qimage = _pil_to_qimage(result.image) if result.image is not None else None
            self._emit_finished(qimage, str(result.error or ""), float(result.elapsed))
        except Exception as error:
            self._emit_finished(None, str(error), 0.0)


class WorkspaceViewModel(QObject):
    documentObjectChanged = Signal(object)
    documentInfoChanged = Signal()
    layerCountChanged = Signal()
    selectionChanged = Signal()
    previewChanged = Signal()
    statusChanged = Signal()
    busyChanged = Signal()
    historyStateChanged = Signal()
    exportStateChanged = Signal()
    styleClipboardChanged = Signal()
    cropEditChanged = Signal()
    vectorEditChanged = Signal()
    viewSettingsChanged = Signal()
    layerAppearanceChanged = Signal()
    fontCatalogChanged = Signal()
    _fontCatalogLoaded = Signal(object, object)
    toastRequested = Signal(str)
    textEditingChanged = Signal()

    def __init__(
        self,
        document: Optional[Document] = None,
        preview_provider: Optional[PreviewImageProvider] = None,
        *,
        auto_render: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._document: Optional[Document] = None
        self._preview_provider = preview_provider or PreviewImageProvider()
        self._layer_model = LayerListModel(parent=self)
        self._layer_model.modelReset.connect(self.layerCountChanged.emit)
        self._preview_revision = 0
        self._status_message = "就绪"
        self._busy = False
        self._export_running = False
        self._auto_render = bool(auto_render)
        self._document_lock = threading.RLock()
        self._render_request_id = 0
        self._preview_generation = 0
        self._render_running = False
        self._render_pending = False
        self._active_render_task = None
        self._pending_preview_quality = None
        self._pending_preview_generation = 0
        self._preview_token_source = PreviewRenderTokenSource()
        self._text_font_names_cache = None
        self._text_font_options_cache = None
        self._text_font_tree_options_cache = None
        self._font_catalog_loading = False
        self._text_edit_overlay_visible = False
        self._text_edit_layer_index = -1
        self._layer_style_clipboard = None
        self._crop_edit_index = -1
        self._crop_edit_original = None
        self._crop_edit_was_modified = False
        self._selected_vector_node_index = -1
        self._selection_anchor_index = -1
        self._corner_edit_modes = {}
        self._suppress_document_selection_notify = 0
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(20)
        self._preview_timer.timeout.connect(self._start_preview_render)
        self._final_preview_timer = QTimer(self)
        self._final_preview_timer.setSingleShot(True)
        self._final_preview_timer.setInterval(220)
        self._final_preview_timer.timeout.connect(self._queue_final_preview)
        self.selectionChanged.connect(self.layerAppearanceChanged.emit)
        self.selectionChanged.connect(self.fontCatalogChanged.emit)
        self._fontCatalogLoaded.connect(self._on_font_catalog_loaded)
        self._set_document(document or Document())
        if self._auto_render:
            self.requestPreview()

    @property
    def document(self) -> Document:
        return self._document

    @property
    def documentLock(self) -> threading.RLock:
        return self._document_lock

    @Property(QObject, constant=True)
    def layerModel(self):
        return self._layer_model

    @Property(int, notify=layerCountChanged)
    def layerCount(self) -> int:
        return len(getattr(self._document, "layers", []) or [])

    @Property(str, notify=documentInfoChanged)
    def documentTitle(self) -> str:
        path = getattr(self._document, "current_file_path", None)
        return os.path.basename(path) if path else "未命名项目.cmp"

    @Property(str, notify=documentInfoChanged)
    def documentPath(self) -> str:
        return str(getattr(self._document, "current_file_path", None) or "")

    @Property(bool, notify=documentInfoChanged)
    def hasFilePath(self) -> bool:
        return bool(self.documentPath)

    @Property(bool, notify=documentInfoChanged)
    def isModified(self) -> bool:
        return bool(getattr(self._document, "is_modified", False))

    @Property(int, notify=documentInfoChanged)
    def canvasWidth(self) -> int:
        return int(getattr(self._document, "canvas_width", 0))

    @Property(int, notify=documentInfoChanged)
    def canvasHeight(self) -> int:
        return int(getattr(self._document, "canvas_height", 0))

    @Property(float, notify=viewSettingsChanged)
    def zoomFactor(self) -> float:
        return float(self._document.view_settings.get("zoom_factor", 1.0))

    @Slot(float, result=bool)
    def setZoomFactor(self, value: float) -> bool:
        value = round(max(0.1, min(10.0, float(value))), 3)
        if self._document.view_settings.get("zoom_factor", 1.0) == value:
            return True
        self._document.view_settings["zoom_factor"] = value
        self.viewSettingsChanged.emit()
        return True

    @Property(int, notify=viewSettingsChanged)
    def viewOffsetX(self) -> int:
        return int(self._document.view_settings.get("offset_x", 0))

    @Property(int, notify=viewSettingsChanged)
    def viewOffsetY(self) -> int:
        return int(self._document.view_settings.get("offset_y", 0))

    @Slot(int, int, result=bool)
    def setViewOffset(self, x: int, y: int) -> bool:
        x, y = int(x), int(y)
        settings = self._document.view_settings
        if settings.get("offset_x", 0) == x and settings.get("offset_y", 0) == y:
            return True
        settings["offset_x"] = x
        settings["offset_y"] = y
        self.viewSettingsChanged.emit()
        return True

    @Slot(result=bool)
    def resetView(self) -> bool:
        changed = self.setZoomFactor(1.0)
        return self.setViewOffset(0, 0) and changed

    @Property(bool, notify=viewSettingsChanged)
    def showRulers(self) -> bool:
        return bool(self._document.view_settings.get("show_rulers", True))

    @Property(bool, notify=viewSettingsChanged)
    def showGuides(self) -> bool:
        return bool(self._document.view_settings.get("show_guides", True))

    @Property(bool, notify=viewSettingsChanged)
    def snapToGuides(self) -> bool:
        return bool(self._document.view_settings.get("snap_to_guides", True))

    @Property("QVariantList", notify=viewSettingsChanged)
    def horizontalGuides(self):
        return [float(value) for value in self._document.view_settings.get("horizontal_guides", [])]

    @Property("QVariantList", notify=viewSettingsChanged)
    def verticalGuides(self):
        return [float(value) for value in self._document.view_settings.get("vertical_guides", [])]

    def _set_view_setting(self, key: str, value, action: str) -> bool:
        if not self._ensure_operations_available():
            return False
        if self._document.view_settings.get(key) == value:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            self._document.view_settings[key] = value
            self._document.is_modified = True
            self._document.save_state(action)
            self._document.document_changed.emit()
        self.viewSettingsChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        return True

    @Slot(bool, result=bool)
    def setShowRulers(self, enabled: bool) -> bool:
        return self._set_view_setting("show_rulers", bool(enabled), "切换标尺显示")

    @Slot(bool, result=bool)
    def setShowGuides(self, enabled: bool) -> bool:
        return self._set_view_setting("show_guides", bool(enabled), "切换参考线显示")

    @Slot(bool, result=bool)
    def setSnapToGuides(self, enabled: bool) -> bool:
        return self._set_view_setting("snap_to_guides", bool(enabled), "切换参考线吸附")

    @staticmethod
    def _guide_key(orientation: str):
        normalized = str(orientation or "").strip().lower()
        if normalized in {"horizontal", "h"}:
            return "horizontal_guides"
        if normalized in {"vertical", "v"}:
            return "vertical_guides"
        return None

    @Slot(str, float, result=bool)
    def addGuide(self, orientation: str, position: float) -> bool:
        key = self._guide_key(orientation)
        limit = self.canvasHeight if key == "horizontal_guides" else self.canvasWidth
        if key is None or not 0 <= float(position) <= limit:
            return False
        guides = list(self._document.view_settings.get(key, []))
        guides.append(round(float(position), 2))
        guides.sort()
        return self._set_view_setting(key, guides, "添加参考线")

    @Slot(str, int, float, result=bool)
    def moveGuide(self, orientation: str, index: int, position: float) -> bool:
        key = self._guide_key(orientation)
        limit = self.canvasHeight if key == "horizontal_guides" else self.canvasWidth
        guides = list(self._document.view_settings.get(key, [])) if key else []
        if key is None or not 0 <= int(index) < len(guides) or not 0 <= float(position) <= limit:
            return False
        guides[int(index)] = round(float(position), 2)
        return self._set_view_setting(key, guides, "移动参考线")

    @Slot(str, int, result=bool)
    def removeGuide(self, orientation: str, index: int) -> bool:
        key = self._guide_key(orientation)
        guides = list(self._document.view_settings.get(key, [])) if key else []
        if key is None or not 0 <= int(index) < len(guides):
            return False
        guides.pop(int(index))
        return self._set_view_setting(key, guides, "删除参考线")

    @Slot(result=bool)
    def clearGuides(self) -> bool:
        horizontal = self._document.view_settings.get("horizontal_guides", [])
        vertical = self._document.view_settings.get("vertical_guides", [])
        if not horizontal and not vertical:
            return True
        if not self._ensure_operations_available():
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            self._document.view_settings["horizontal_guides"] = []
            self._document.view_settings["vertical_guides"] = []
            self._document.is_modified = True
            self._document.save_state("清空参考线")
            self._document.document_changed.emit()
        self.viewSettingsChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        return True

    @Slot(float, float, float, float, float, result="QVariantMap")
    def snapPosition(self, x: float, y: float, width: float, height: float, tolerance: float = 6.0):
        result = {"x": float(x), "y": float(y), "snappedX": False, "snappedY": False}
        if not self.snapToGuides or not self.showGuides:
            return result

        def best_offset(origin, size, guides):
            candidates = (origin, origin + size / 2.0, origin + size)
            matches = [
                (abs(float(guide) - edge), float(guide) - edge)
                for guide in guides
                for edge in candidates
                if abs(float(guide) - edge) <= max(0.0, float(tolerance))
            ]
            return min(matches, default=None, key=lambda item: item[0])

        x_match = best_offset(float(x), float(width), self.verticalGuides)
        y_match = best_offset(float(y), float(height), self.horizontalGuides)
        if x_match is not None:
            result["x"] = float(x) + x_match[1]
            result["snappedX"] = True
        if y_match is not None:
            result["y"] = float(y) + y_match[1]
            result["snappedY"] = True
        return result

    @Slot(int, int, result=bool)
    @Slot(int, int, int, result=bool)
    def resizeCanvas(self, width: int, height: int, mode: int = 3) -> bool:
        width, height = int(width), int(height)
        mode = int(mode)
        if width < 16 or height < 16 or width > 32768 or height > 32768:
            self._set_status("画布尺寸必须在 16 到 32768 像素之间", toast=True)
            return False
        if mode not in (0, 1, 2, 3):
            self._set_status("不支持的画布调整方式", toast=True)
            return False
        if width == self.canvasWidth and height == self.canvasHeight:
            return True
        if not self._ensure_operations_available():
            return False
        old_width = max(1, self.canvasWidth)
        old_height = max(1, self.canvasHeight)
        layers_adjusted = mode in (0, 1, 2)
        with self._document_lock:
            self._ensure_history_baseline()
            width_scale = width / old_width
            height_scale = height / old_height
            for layer in self._document.layers:
                if not layers_adjusted or not all(
                    hasattr(layer, attr) for attr in ("x", "y", "width", "height")
                ):
                    continue
                if mode == 0:
                    layer.x = int(round(layer.x * width_scale))
                    layer.y = int(round(layer.y * height_scale))
                    layer.width = max(1, int(round(layer.width * width_scale)))
                    layer.height = max(1, int(round(layer.height * height_scale)))
                elif mode == 1:
                    layer.x = int(round((width - layer.width) / 2))
                    layer.y = int(round((height - layer.height) / 2))
                else:
                    layer.x = 0
                    layer.y = 0
                for cache_name in ("_cached_image", "cached_image"):
                    if hasattr(layer, cache_name):
                        setattr(layer, cache_name, None)
            self._document.canvas_width = width
            self._document.canvas_height = height
            self._document.is_modified = True
            self._document._invalidate_render_cache()
            self._document.bump_hit_test_version()
            self._document.save_state("调整画布尺寸")
            self._document.document_changed.emit()
        if layers_adjusted:
            self._layer_model.reset_from_document()
            self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"画布已调整为 {width} x {height}", toast=True)
        return True

    @Property(int, notify=selectionChanged)
    def selectedLayerIndex(self) -> int:
        return int(getattr(self._document, "selected_layer_index", -1))

    @Property("QVariantList", notify=selectionChanged)
    def selectedLayerIndices(self):
        return [
            int(index)
            for index in list(getattr(self._document, "selected_layer_indices", []) or [])
            if 0 <= int(index) < len(getattr(self._document, "layers", []))
        ]

    @Property(int, notify=selectionChanged)
    def selectedLayerCount(self) -> int:
        return len(self.selectedLayerIndices)

    @Property(bool, notify=selectionChanged)
    def selectedIsLayerGroup(self) -> bool:
        return isinstance(self._selected_layer(), LayerGroup)

    @Property(int, notify=selectionChanged)
    def selectedGroupChildCount(self) -> int:
        group = self._selected_layer()
        if not isinstance(group, LayerGroup):
            return 0
        return len(child_indices_for_group(self._document.layers, group.group_id))

    @Property(bool, notify=selectionChanged)
    def selectedGroupExpanded(self) -> bool:
        group = self._selected_layer()
        return bool(getattr(group, "expanded", False)) if isinstance(group, LayerGroup) else False

    @Property(bool, notify=selectionChanged)
    def canGroupSelectedLayers(self) -> bool:
        movable = [
            index
            for index in self.selectedLayerIndices
            if not is_layer_group(self._document.layers[index])
            and not get_parent_group_id(self._document.layers[index])
            and not is_effectively_locked(self._document.layers[index], self._document.layers)
        ]
        return len(movable) >= 2 and not self._export_running

    @Property(bool, notify=selectionChanged)
    def canUngroupSelectedLayers(self) -> bool:
        return any(
            isinstance(self._document.layers[index], LayerGroup)
            for index in self.selectedLayerIndices
        ) and not self._export_running

    def _selected_content_indices(self):
        return expand_group_indices(
            self._document.layers,
            self.selectedLayerIndices,
            include_groups=False,
        )

    def _selection_bounds(self):
        bounds = []
        for index in self._selected_content_indices():
            layer = self._document.layers[index]
            if not all(hasattr(layer, attr) for attr in ("x", "y", "width", "height")):
                continue
            x = int(layer.x)
            y = int(layer.y)
            bounds.append((x, y, x + int(layer.width), y + int(layer.height)))
        if not bounds:
            return 0, 0, 0, 0
        left = min(item[0] for item in bounds)
        top = min(item[1] for item in bounds)
        right = max(item[2] for item in bounds)
        bottom = max(item[3] for item in bounds)
        return left, top, right - left, bottom - top

    @Property(int, notify=selectionChanged)
    def selectionBoundsX(self) -> int:
        return self._selection_bounds()[0]

    @Property(int, notify=selectionChanged)
    def selectionBoundsY(self) -> int:
        return self._selection_bounds()[1]

    @Property(int, notify=selectionChanged)
    def selectionBoundsWidth(self) -> int:
        return self._selection_bounds()[2]

    @Property(int, notify=selectionChanged)
    def selectionBoundsHeight(self) -> int:
        return self._selection_bounds()[3]

    def _selected_layer(self):
        return self._layer_model.layer_at(self.selectedLayerIndex)

    @Property(str, notify=selectionChanged)
    def selectedLayerName(self) -> str:
        layer = self._selected_layer()
        return str(getattr(layer, "name", "未选择图层"))

    @Property(str, notify=selectionChanged)
    def selectedLayerType(self) -> str:
        layer = self._selected_layer()
        return self._layer_model.layer_type_name(layer) if layer is not None else ""

    @Property(int, notify=selectionChanged)
    def selectedX(self) -> int:
        return int(getattr(self._selected_layer(), "x", 0))

    @Property(int, notify=selectionChanged)
    def selectedY(self) -> int:
        return int(getattr(self._selected_layer(), "y", 0))

    @Property(int, notify=selectionChanged)
    def selectedWidth(self) -> int:
        return int(getattr(self._selected_layer(), "width", 0))

    @Property(int, notify=selectionChanged)
    def selectedHeight(self) -> int:
        return int(getattr(self._selected_layer(), "height", 0))

    @Property(int, notify=layerAppearanceChanged)
    def selectedOpacity(self) -> int:
        return round(float(getattr(self._selected_layer(), "opacity", 1.0)) * 100)

    @Property(bool, notify=selectionChanged)
    def selectedSupportsBlendMode(self) -> bool:
        return hasattr(self._selected_layer(), "blend_mode")

    @Property(str, notify=selectionChanged)
    def selectedBlendModeId(self) -> str:
        layer = self._selected_layer()
        value = getattr(layer, "blend_mode", 0)
        if isinstance(value, int):
            return _BLEND_MODE_IDS.get(value, "normal")
        mode_id = str(value or "normal").strip().lower()
        return mode_id if mode_id in _BLEND_MODES else "normal"

    @Property(str, notify=selectionChanged)
    def selectedBlendModeName(self) -> str:
        return _BLEND_MODES[self.selectedBlendModeId][1]

    @Property(bool, notify=selectionChanged)
    def selectedSupportsStroke(self) -> bool:
        layer = self._selected_layer()
        return all(hasattr(layer, attr) for attr in ("stroke_enabled", "stroke_width", "stroke_color"))

    @Property(bool, notify=selectionChanged)
    def selectedStrokeEnabled(self) -> bool:
        return self.selectedSupportsStroke and bool(getattr(self._selected_layer(), "stroke_enabled", False))

    @Property(int, notify=selectionChanged)
    def selectedStrokeWidth(self) -> int:
        if not self.selectedSupportsStroke:
            return 1
        return max(1, int(getattr(self._selected_layer(), "stroke_width", 1)))

    @staticmethod
    def _rgba_to_hex(value) -> str:
        try:
            channels = tuple(max(0, min(255, int(channel))) for channel in value)
        except (TypeError, ValueError):
            channels = (0, 0, 0, 255)
        if len(channels) < 3:
            channels = (0, 0, 0, 255)
        alpha = channels[3] if len(channels) > 3 else 255
        result = "#{:02X}{:02X}{:02X}".format(*channels[:3])
        return result if alpha == 255 else f"{result}{alpha:02X}"

    @staticmethod
    def _parse_hex_color(value: str):
        match = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", str(value or "").strip())
        if match is None:
            return None
        rgb, alpha = match.groups()
        channels = tuple(int(rgb[index:index + 2], 16) for index in range(0, 6, 2))
        return channels + (int(alpha, 16) if alpha else 255,)

    @Property(str, notify=selectionChanged)
    def selectedStrokeColor(self) -> str:
        if not self.selectedSupportsStroke:
            return "#000000"
        return self._rgba_to_hex(getattr(self._selected_layer(), "stroke_color", (0, 0, 0, 255)))

    @Property(bool, notify=selectionChanged)
    def selectedSupportsAdvancedStroke(self) -> bool:
        layer = self._selected_layer()
        return self.selectedSupportsStroke and all(
            hasattr(layer, attr)
            for attr in (
                "stroke_type",
                "stroke_join",
                "stroke_cap",
                "stroke_dash_length",
                "stroke_dash_gap",
            )
        )

    @Property(int, notify=selectionChanged)
    def selectedStrokeType(self) -> int:
        if not self.selectedSupportsAdvancedStroke:
            return 0
        return max(0, min(2, int(getattr(self._selected_layer(), "stroke_type", 0))))

    @Property(str, notify=selectionChanged)
    def selectedStrokeJoin(self) -> str:
        if not self.selectedSupportsAdvancedStroke:
            return "miter"
        value = str(getattr(self._selected_layer(), "stroke_join", "miter"))
        return value if value in {"miter", "round", "bevel"} else "miter"

    @Property(str, notify=selectionChanged)
    def selectedStrokeCap(self) -> str:
        if not self.selectedSupportsAdvancedStroke:
            return "butt"
        value = str(getattr(self._selected_layer(), "stroke_cap", "butt"))
        return value if value in {"butt", "round", "square"} else "butt"

    @Property(int, notify=selectionChanged)
    def selectedStrokeDashLength(self) -> int:
        if not self.selectedSupportsAdvancedStroke:
            return 0
        return max(0, int(getattr(self._selected_layer(), "stroke_dash_length", 0)))

    @Property(int, notify=selectionChanged)
    def selectedStrokeDashGap(self) -> int:
        if not self.selectedSupportsAdvancedStroke:
            return 0
        return max(0, int(getattr(self._selected_layer(), "stroke_dash_gap", 0)))

    @Property(str, notify=selectionChanged)
    def selectedCornerControlKind(self) -> str:
        layer = self._selected_layer()
        if layer is None or not hasattr(layer, "corner_radius"):
            return "none"
        if bool(getattr(layer, "vector_path_enabled", False)):
            return "none"
        if self.selectedIsShapedLayer:
            shape_id = self.selectedShapeTypeId
            if shape_id == "rectangle":
                return "rectangle"
            if shape_id in {"right_trapezoid", "pentagon", "hexagon"}:
                return "shape"
            return "none"
        return "rectangle"

    @Property(bool, notify=selectionChanged)
    def selectedSupportsCornerRadius(self) -> bool:
        return self.selectedCornerControlKind == "rectangle"

    @Property(bool, notify=selectionChanged)
    def selectedSupportsShapeCornerRadius(self) -> bool:
        layer = self._selected_layer()
        return self.selectedCornerControlKind == "shape" and hasattr(
            layer, "polygon_corner_radius"
        )

    @Property(str, notify=selectionChanged)
    def selectedCornerMode(self) -> str:
        if not self.selectedSupportsCornerRadius:
            return "uniform"
        layer = self._selected_layer()
        override = self._corner_edit_modes.get(id(layer))
        if override in {"uniform", "independent"}:
            return override
        return "independent" if any(self.selectedVectorCornerRadii) else "uniform"

    @Property(int, notify=selectionChanged)
    def selectedCornerRadius(self) -> int:
        if not self.selectedSupportsCornerRadius:
            return 0
        if self.selectedCornerMode == "independent":
            return max(self.selectedVectorCornerRadii)
        return max(0, int(getattr(self._selected_layer(), "corner_radius", 0)))

    @Property(int, notify=selectionChanged)
    def selectedCornerRadiusMax(self) -> int:
        if not self.selectedSupportsCornerRadius:
            return 0
        layer = self._selected_layer()
        return max(0, min(int(getattr(layer, "width", 0)), int(getattr(layer, "height", 0))) // 2)

    @Property(bool, notify=selectionChanged)
    def selectedSupportsColorOverlay(self) -> bool:
        layer = self._selected_layer()
        return all(
            hasattr(layer, attr)
            for attr in ("color_overlay_enabled", "color_overlay_color", "color_overlay_opacity")
        )

    @Property(bool, notify=selectionChanged)
    def selectedColorOverlayEnabled(self) -> bool:
        return self.selectedSupportsColorOverlay and bool(
            getattr(self._selected_layer(), "color_overlay_enabled", False)
        )

    @Property(str, notify=selectionChanged)
    def selectedColorOverlayColor(self) -> str:
        if not self.selectedSupportsColorOverlay:
            return "#000000"
        return self._rgba_to_hex(
            getattr(self._selected_layer(), "color_overlay_color", (255, 0, 0, 255))
        )

    @Property(int, notify=selectionChanged)
    def selectedColorOverlayOpacity(self) -> int:
        if not self.selectedSupportsColorOverlay:
            return 100
        return round(float(getattr(self._selected_layer(), "color_overlay_opacity", 1.0)) * 100)

    @Property(bool, notify=selectionChanged)
    def selectedSupportsGradientOverlay(self) -> bool:
        layer = self._selected_layer()
        return all(
            hasattr(layer, attr)
            for attr in (
                "gradient_overlay_enabled",
                "gradient_overlay_colors",
                "gradient_overlay_opacity",
                "gradient_overlay_angle",
            )
        )

    def _selected_gradient_colors(self):
        colors = getattr(self._selected_layer(), "gradient_overlay_colors", None)
        if not isinstance(colors, (list, tuple)) or len(colors) < 2:
            return [(0, 0, 0, 255), (255, 255, 255, 255)]
        normalized = []
        for color in colors[:2]:
            parsed = self._parse_hex_color(self._rgba_to_hex(color))
            normalized.append(parsed or (0, 0, 0, 255))
        return normalized

    @Property(bool, notify=selectionChanged)
    def selectedGradientOverlayEnabled(self) -> bool:
        return self.selectedSupportsGradientOverlay and bool(
            getattr(self._selected_layer(), "gradient_overlay_enabled", False)
        )

    @Property(str, notify=selectionChanged)
    def selectedGradientStartColor(self) -> str:
        return self._rgba_to_hex(self._selected_gradient_colors()[0])

    @Property(str, notify=selectionChanged)
    def selectedGradientEndColor(self) -> str:
        return self._rgba_to_hex(self._selected_gradient_colors()[1])

    @Property(int, notify=selectionChanged)
    def selectedGradientOverlayOpacity(self) -> int:
        if not self.selectedSupportsGradientOverlay:
            return 100
        return round(float(getattr(self._selected_layer(), "gradient_overlay_opacity", 1.0)) * 100)

    @Property(float, notify=selectionChanged)
    def selectedGradientOverlayAngle(self) -> float:
        if not self.selectedSupportsGradientOverlay:
            return 0.0
        return float(getattr(self._selected_layer(), "gradient_overlay_angle", 0.0)) % 360.0

    @Property(str, notify=selectionChanged)
    def selectedOverlayMode(self) -> str:
        if self.selectedGradientOverlayEnabled:
            return "gradient"
        if self.selectedColorOverlayEnabled:
            return "color"
        return "none"

    @Property(bool, notify=selectionChanged)
    def selectedVisible(self) -> bool:
        return bool(getattr(self._selected_layer(), "visible", False))

    @Property(bool, notify=selectionChanged)
    def selectedLocked(self) -> bool:
        return bool(getattr(self._selected_layer(), "locked", False))

    @Property(float, notify=selectionChanged)
    def selectedRotation(self) -> float:
        layer = self._selected_layer()
        return float(getattr(layer, "rotation", 0.0) or 0.0)

    @Property(bool, notify=selectionChanged)
    def selectedCanRotate(self) -> bool:
        layer = self._selected_layer()
        return layer is not None and hasattr(layer, "rotation")

    @Property(bool, notify=selectionChanged)
    def selectedIsImageLayer(self) -> bool:
        return self.selectedLayerType == "图片"

    @Property(bool, notify=selectionChanged)
    def selectedIsShapedLayer(self) -> bool:
        return isinstance(self._selected_layer(), ShapedLayer)

    @Property(bool, notify=selectionChanged)
    def selectedHasImageSource(self) -> bool:
        return self.selectedIsImageLayer or self.selectedIsShapedLayer

    @Property(bool, notify=selectionChanged)
    def selectedSupportsAspectRatioLock(self) -> bool:
        layer = self._selected_layer()
        return self.selectedHasImageSource and hasattr(layer, "aspect_ratio_locked")

    @Property(bool, notify=selectionChanged)
    def selectedAspectRatioLocked(self) -> bool:
        return self.selectedSupportsAspectRatioLock and bool(
            getattr(self._selected_layer(), "aspect_ratio_locked", False)
        )

    @Property(bool, notify=selectionChanged)
    def selectedSupportsRandomTransform(self) -> bool:
        layer = self._selected_layer()
        return self.selectedHasImageSource and all(
            hasattr(layer, attr)
            for attr in (
                "random_position_enabled",
                "random_position_range",
                "random_scale_enabled",
                "random_scale_min",
                "random_scale_max",
                "random_rotation_enabled",
                "random_rotation_range",
            )
        ) and callable(getattr(layer, "generate_random_transform_params", None))

    @Property(bool, notify=selectionChanged)
    def selectedRandomPositionEnabled(self) -> bool:
        return self.selectedSupportsRandomTransform and bool(
            getattr(self._selected_layer(), "random_position_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedRandomPositionRange(self) -> int:
        if not self.selectedSupportsRandomTransform:
            return 0
        return int(getattr(self._selected_layer(), "random_position_range", 10))

    @Property(bool, notify=selectionChanged)
    def selectedRandomScaleEnabled(self) -> bool:
        return self.selectedSupportsRandomTransform and bool(
            getattr(self._selected_layer(), "random_scale_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedRandomScaleMinPercent(self) -> int:
        if not self.selectedSupportsRandomTransform:
            return 100
        return round(float(getattr(self._selected_layer(), "random_scale_min", 0.9)) * 100)

    @Property(int, notify=selectionChanged)
    def selectedRandomScaleMaxPercent(self) -> int:
        if not self.selectedSupportsRandomTransform:
            return 100
        return round(float(getattr(self._selected_layer(), "random_scale_max", 1.1)) * 100)

    @Property(bool, notify=selectionChanged)
    def selectedRandomRotationEnabled(self) -> bool:
        return self.selectedSupportsRandomTransform and bool(
            getattr(self._selected_layer(), "random_rotation_enabled", False)
        )

    @Property(float, notify=selectionChanged)
    def selectedRandomRotationRange(self) -> float:
        if not self.selectedSupportsRandomTransform:
            return 0.0
        return float(getattr(self._selected_layer(), "random_rotation_range", 5.0))

    @Property(int, notify=selectionChanged)
    def selectedRandomTransformEnabledCount(self) -> int:
        return sum(
            (
                self.selectedRandomPositionEnabled,
                self.selectedRandomScaleEnabled,
                self.selectedRandomRotationEnabled,
            )
        )

    @Property(int, notify=selectionChanged)
    def selectedRandomOffsetX(self) -> int:
        return int(getattr(self._selected_layer(), "_current_random_offset_x", 0))

    @Property(int, notify=selectionChanged)
    def selectedRandomOffsetY(self) -> int:
        return int(getattr(self._selected_layer(), "_current_random_offset_y", 0))

    @Property(int, notify=selectionChanged)
    def selectedRandomScalePercent(self) -> int:
        return round(float(getattr(self._selected_layer(), "_current_random_scale", 1.0)) * 100)

    @Property(float, notify=selectionChanged)
    def selectedRandomRotation(self) -> float:
        return float(getattr(self._selected_layer(), "_current_random_rotation", 0.0))

    @Property(str, notify=selectionChanged)
    def selectedRandomPreviewSummary(self) -> str:
        if self.selectedRandomTransformEnabledCount == 0:
            return "尚未启用随机变换"
        parts = []
        if self.selectedRandomPositionEnabled:
            parts.append(f"位置 {self.selectedRandomOffsetX:+d}/{self.selectedRandomOffsetY:+d} px")
        if self.selectedRandomScaleEnabled:
            parts.append(f"缩放 {self.selectedRandomScalePercent}%")
        if self.selectedRandomRotationEnabled:
            parts.append(f"旋转 {self.selectedRandomRotation:+.1f}°")
        return " · ".join(parts)

    @Property(bool, notify=selectionChanged)
    def selectedSupportsClone(self) -> bool:
        layer = self._selected_layer()
        return self.selectedHasImageSource and all(
            hasattr(layer, attr)
            for attr in (
                "clone_enabled",
                "clone_rows",
                "clone_columns",
                "clone_row_spacing",
                "clone_column_spacing",
                "clone_mirror_mode",
                "clone_fill_enabled",
                "clone_fill_mode",
                "clone_fill_spacing",
                "clone_fill_margin",
                "clone_fill_angle",
                "clone_custom_size_enabled",
                "clone_custom_width",
                "clone_custom_height",
            )
        )

    @Property(bool, notify=selectionChanged)
    def selectedCloneEnabled(self) -> bool:
        return self.selectedSupportsClone and bool(
            getattr(self._selected_layer(), "clone_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedCloneRows(self) -> int:
        return max(1, int(getattr(self._selected_layer(), "clone_rows", 1)))

    @Property(int, notify=selectionChanged)
    def selectedCloneColumns(self) -> int:
        return max(1, int(getattr(self._selected_layer(), "clone_columns", 1)))

    @Property(int, notify=selectionChanged)
    def selectedCloneRowSpacing(self) -> int:
        return max(0, int(getattr(self._selected_layer(), "clone_row_spacing", 0)))

    @Property(int, notify=selectionChanged)
    def selectedCloneColumnSpacing(self) -> int:
        return max(0, int(getattr(self._selected_layer(), "clone_column_spacing", 0)))

    @Property(str, notify=selectionChanged)
    def selectedCloneMirrorMode(self) -> str:
        value = str(getattr(self._selected_layer(), "clone_mirror_mode", "none"))
        return value if value in {"none", "horizontal", "vertical"} else "none"

    @Property(bool, notify=selectionChanged)
    def selectedCloneCustomSizeEnabled(self) -> bool:
        return self.selectedSupportsClone and bool(
            getattr(self._selected_layer(), "clone_custom_size_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedCloneCustomWidth(self) -> int:
        layer = self._selected_layer()
        value = int(getattr(layer, "clone_custom_width", 0) or 0)
        return max(1, value or int(getattr(layer, "width", 1)))

    @Property(int, notify=selectionChanged)
    def selectedCloneCustomHeight(self) -> int:
        layer = self._selected_layer()
        value = int(getattr(layer, "clone_custom_height", 0) or 0)
        return max(1, value or int(getattr(layer, "height", 1)))

    @Property(bool, notify=selectionChanged)
    def selectedCloneFillEnabled(self) -> bool:
        return self.selectedSupportsClone and bool(
            getattr(self._selected_layer(), "clone_fill_enabled", False)
        )

    @Property(str, notify=selectionChanged)
    def selectedCloneLayoutMode(self) -> str:
        return "fill" if self.selectedCloneFillEnabled else "fixed"

    @Property(str, notify=selectionChanged)
    def selectedCloneFillMode(self) -> str:
        value = str(getattr(self._selected_layer(), "clone_fill_mode", "grid"))
        return value if value in {"grid", "staggered", "border"} else "grid"

    @Property(int, notify=selectionChanged)
    def selectedCloneFillSpacing(self) -> int:
        return max(0, int(getattr(self._selected_layer(), "clone_fill_spacing", 0)))

    @Property(int, notify=selectionChanged)
    def selectedCloneFillMargin(self) -> int:
        return max(0, int(getattr(self._selected_layer(), "clone_fill_margin", 0)))

    @Property(float, notify=selectionChanged)
    def selectedCloneFillAngle(self) -> float:
        return float(getattr(self._selected_layer(), "clone_fill_angle", 0.0)) % 360.0

    @Property(bool, notify=selectionChanged)
    def selectedSupportsImageFit(self) -> bool:
        layer = self._selected_layer()
        return self.selectedHasImageSource and all(
            hasattr(layer, attr)
            for attr in ("fit_mode", "crop_direction", "flip_horizontal", "flip_vertical")
        )

    @Property(bool, notify=selectionChanged)
    def selectedUseOriginalSize(self) -> bool:
        layer = self._selected_layer()
        return self.selectedHasImageSource and bool(
            getattr(layer, "use_original_size", False)
        )

    @Property(bool, notify=selectionChanged)
    def selectedTrimTransparentBoundsEnabled(self) -> bool:
        return self.selectedUseOriginalSize

    @Property(str, notify=selectionChanged)
    def selectedFitModeId(self) -> str:
        if not self.selectedSupportsImageFit:
            return "crop"
        value = int(getattr(self._selected_layer(), "fit_mode", Layer.FIT_SMART_CROP))
        return _FIT_MODE_IDS.get(value, "crop")

    @Property(str, notify=selectionChanged)
    def selectedFitModeName(self) -> str:
        return _FIT_MODES[self.selectedFitModeId][1]

    @Property(str, notify=selectionChanged)
    def selectedCropDirectionId(self) -> str:
        if not self.selectedSupportsImageFit:
            return "center"
        value = int(getattr(self._selected_layer(), "crop_direction", Layer.CROP_CENTER))
        return _CROP_DIRECTION_IDS.get(value, "center")

    @Property(str, notify=selectionChanged)
    def selectedCropDirectionName(self) -> str:
        return _CROP_DIRECTIONS[self.selectedCropDirectionId][1]

    @Property(bool, notify=selectionChanged)
    def selectedSupportsFreeCrop(self) -> bool:
        layer = self._selected_layer()
        return self.selectedSupportsImageFit and hasattr(layer, "crop_rect")

    @Property("QVariantList", notify=cropEditChanged)
    def selectedCropRect(self):
        if not self.selectedSupportsFreeCrop:
            return [0.0, 0.0, 1.0, 1.0]
        return [float(value) for value in self._selected_layer().crop_rect]

    @Property(bool, notify=cropEditChanged)
    def cropEditing(self) -> bool:
        return self._crop_edit_index == self.selectedLayerIndex and self._crop_edit_original is not None

    @Property(bool, notify=selectionChanged)
    def selectedSupportsVectorPath(self) -> bool:
        layer = self._selected_layer()
        return layer is not None and all(
            hasattr(layer, attr)
            for attr in (
                "vector_path_enabled",
                "vector_path_mode",
                "vector_bezier_nodes",
                "vector_path_closed",
            )
        )

    @Property(bool, notify=selectionChanged)
    def selectedSupportsVectorCorners(self) -> bool:
        layer = self._selected_layer()
        return self.selectedSupportsCornerRadius and all(
            hasattr(layer, attr)
            for attr in (
                "vector_corner_radius_tl",
                "vector_corner_radius_tr",
                "vector_corner_radius_br",
                "vector_corner_radius_bl",
            )
        )

    @Property("QVariantList", notify=selectionChanged)
    def selectedVectorCornerRadii(self):
        if not self.selectedSupportsVectorCorners:
            return [0, 0, 0, 0]
        layer = self._selected_layer()
        return [
            max(0, int(getattr(layer, "vector_corner_radius_tl", 0))),
            max(0, int(getattr(layer, "vector_corner_radius_tr", 0))),
            max(0, int(getattr(layer, "vector_corner_radius_br", 0))),
            max(0, int(getattr(layer, "vector_corner_radius_bl", 0))),
        ]

    @Property(bool, notify=selectionChanged)
    def selectedVectorPathEnabled(self) -> bool:
        return self.selectedSupportsVectorPath and bool(
            getattr(self._selected_layer(), "vector_path_enabled", False)
        )

    @Property(str, notify=selectionChanged)
    def selectedVectorPathMode(self) -> str:
        if not self.selectedSupportsVectorPath:
            return "polygon"
        return str(getattr(self._selected_layer(), "vector_path_mode", "polygon"))

    @Property(bool, notify=selectionChanged)
    def selectedVectorPathClosed(self) -> bool:
        return self.selectedSupportsVectorPath and bool(
            getattr(self._selected_layer(), "vector_path_closed", True)
        )

    @Property(str, notify=selectionChanged)
    def selectedVectorHandleLinkMode(self) -> str:
        if not self.selectedSupportsVectorPath:
            return "mirror"
        return str(getattr(self._selected_layer(), "vector_handle_link_mode", "mirror"))

    @Property("QVariantList", notify=selectionChanged)
    def selectedVectorNodes(self):
        if not self.selectedVectorPathEnabled:
            return []
        return copy.deepcopy(getattr(self._selected_layer(), "vector_bezier_nodes", []))

    @Property(int, notify=vectorEditChanged)
    def selectedVectorNodeIndex(self) -> int:
        return int(self._selected_vector_node_index)

    @Property(str, notify=vectorEditChanged)
    def selectedVectorNodeType(self) -> str:
        index = self._selected_vector_node_index
        nodes = self.selectedVectorNodes
        if index < 0 or index >= len(nodes):
            return "corner"
        return str(nodes[index].get("node_type", "corner"))

    @Property(bool, notify=selectionChanged)
    def selectedFlipHorizontal(self) -> bool:
        return self.selectedSupportsImageFit and bool(
            getattr(self._selected_layer(), "flip_horizontal", False)
        )

    @Property(bool, notify=selectionChanged)
    def selectedFlipVertical(self) -> bool:
        return self.selectedSupportsImageFit and bool(
            getattr(self._selected_layer(), "flip_vertical", False)
        )

    @Property(bool, notify=selectionChanged)
    def selectedIsTextLayer(self) -> bool:
        return self.selectedLayerType == "文字"

    @Property(str, notify=selectionChanged)
    def selectedImageSource(self) -> str:
        if not self.selectedHasImageSource:
            return ""
        return str(getattr(self._selected_layer(), "image_source", "") or "")

    @Property(bool, notify=selectionChanged)
    def selectedImageSourceIsFolder(self) -> bool:
        return self.selectedHasImageSource and bool(
            getattr(self._selected_layer(), "is_folder", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedImageSourceCount(self) -> int:
        if not self.selectedImageSourceIsFolder:
            return 1 if self.selectedImageSource else 0
        return len(self._image_files(self.selectedImageSource))

    @Property(str, notify=selectionChanged)
    def selectedImageCurrentFile(self) -> str:
        if not self.selectedHasImageSource:
            return ""
        layer = self._selected_layer()
        path = getattr(layer, "current_image_path", None) or getattr(layer, "image_source", None)
        return os.path.basename(str(path)) if path else ""

    @Property(str, notify=selectionChanged)
    def selectedShapeTypeId(self) -> str:
        if not self.selectedIsShapedLayer:
            return ""
        value = getattr(self._selected_layer(), "shape_type", ShapeType.RECTANGLE)
        if isinstance(value, ShapeType):
            return value.value
        value = str(value or "").strip().lower()
        return value if value in _SHAPE_TYPES else "rectangle"

    @Property(str, notify=selectionChanged)
    def selectedShapeTypeName(self) -> str:
        return _SHAPE_TYPES.get(self.selectedShapeTypeId, (None, ""))[1]

    @Property(int, notify=selectionChanged)
    def selectedTrapezoidTopWidth(self) -> int:
        if not self.selectedIsShapedLayer:
            return 0
        return int(getattr(self._selected_layer(), "trapezoid_top_width", 0))

    @Property(int, notify=selectionChanged)
    def selectedTrapezoidBottomWidth(self) -> int:
        if not self.selectedIsShapedLayer:
            return 0
        return int(getattr(self._selected_layer(), "trapezoid_bottom_width", 0))

    @Property(str, notify=selectionChanged)
    def selectedTrapezoidSlopeSide(self) -> str:
        if not self.selectedIsShapedLayer:
            return "right"
        return str(getattr(self._selected_layer(), "trapezoid_slope_side", "right"))

    @Property(float, notify=selectionChanged)
    def selectedPolygonRotation(self) -> float:
        if not self.selectedIsShapedLayer:
            return 0.0
        return float(getattr(self._selected_layer(), "polygon_rotation", 0.0)) % 360.0

    @Property(int, notify=selectionChanged)
    def selectedPolygonCornerRadius(self) -> int:
        if not self.selectedSupportsShapeCornerRadius:
            return 0
        return max(0, int(getattr(self._selected_layer(), "polygon_corner_radius", 0)))

    @Property(int, notify=selectionChanged)
    def selectedPolygonCornerRadiusMax(self) -> int:
        if not self.selectedSupportsShapeCornerRadius:
            return 0
        layer = self._selected_layer()
        return max(0, min(int(layer.width), int(layer.height)) // 8)

    @Property(str, notify=selectionChanged)
    def selectedTextContent(self) -> str:
        if not self.selectedIsTextLayer:
            return ""
        return str(getattr(self._selected_layer(), "text_content", "") or "")

    @Property(bool, notify=selectionChanged)
    def selectedTextBindingEnabled(self) -> bool:
        return self.selectedIsTextLayer and bool(
            getattr(self._selected_layer(), "text_binding_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedTextCandidateCount(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        layer = self._selected_layer()
        if self.selectedTextBindingEnabled:
            return len(layer.get_text_lines())
        return 1 if self.selectedTextContent else 0

    @Property(int, notify=selectionChanged)
    def selectedTextFontSize(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        return int(getattr(self._selected_layer(), "font_size", 0) or 0)

    @Property(str, notify=selectionChanged)
    def selectedTextFontFamily(self) -> str:
        if not self.selectedIsTextLayer:
            return ""
        return str(getattr(self._selected_layer(), "font_family", "") or "")

    def _load_text_font_names(self, layer):
        try:
            categories = layer.get_categorized_fonts()
            font_names = categories.get("chinese", [])
            if font_names:
                return font_names
        except Exception:
            logger.debug("加载文字图层中文字体目录失败，回退 Qt 字体库", exc_info=True)
        if QGuiApplication.instance() is not None:
            try:
                writing_system = QFontDatabase.WritingSystem
                font_names = []
                seen = set()
                for system in (
                    writing_system.SimplifiedChinese,
                    writing_system.TraditionalChinese,
                ):
                    for name in QFontDatabase.families(system):
                        key = str(name or "").strip().casefold()
                        if key and key not in seen:
                            seen.add(key)
                            font_names.append(name)
                return font_names
            except Exception:
                logger.debug("从 Qt 字体库加载中文字体失败", exc_info=True)
        return []

    def _font_catalog_layer(self):
        if self.selectedIsTextLayer:
            return self._selected_layer()
        from app.models.text_layer import TextLayer

        return TextLayer()

    def _load_text_font_options(self, layer=None):
        if layer is None:
            layer = self._font_catalog_layer()
        try:
            font_names = self._load_text_font_names(layer)
        except Exception:
            logger.debug("构建本地字体选项失败", exc_info=True)
            font_names = []
        try:
            chinese_names = layer.get_font_cn_names()
        except Exception:
            logger.debug("读取本地字体中文名映射失败", exc_info=True)
            chinese_names = {}
        fallbacks = [
            "Microsoft YaHei",
            "SimHei",
            "SimSun",
            "KaiTi",
            "FangSong",
        ]
        options = []
        seen = set()
        for name in list(font_names or []) or fallbacks:
            family = str(name or "").strip()
            key = family.casefold()
            if not family or key in seen:
                continue
            seen.add(key)
            chinese_name = str(chinese_names.get(family, "") or "").strip()
            label = f"{chinese_name} ({family})" if chinese_name and chinese_name != family else family
            options.append({"label": label, "value": family})
        return options

    @staticmethod
    def _font_face_label(style: str) -> str:
        normalized = str(style or "Regular").strip()
        key = normalized.casefold().replace("-", " ").replace("_", " ")
        italic = "italic" in key or "oblique" in key or "slanted" in key
        if "extra light" in key or "extralight" in key or "ultra light" in key:
            label = "特细"
        elif "thin" in key or "hairline" in key:
            label = "极细"
        elif "light" in key:
            label = "细体"
        elif "medium" in key:
            label = "中等"
        elif "semi bold" in key or "semibold" in key or "demi bold" in key:
            label = "半粗体"
        elif "extra bold" in key or "extrabold" in key or "ultra bold" in key:
            label = "特粗"
        elif "black" in key or "heavy" in key:
            label = "黑体"
        elif "bold" in key:
            label = "粗体"
        else:
            label = "常规"
        return f"{label} 斜体" if italic and "italic" not in label else label

    def _load_text_font_tree_options(self, layer=None):
        if layer is None:
            layer = self._font_catalog_layer()
        try:
            faces_by_family = layer.get_font_faces()
        except Exception:
            logger.debug("构建字体字重目录失败", exc_info=True)
            faces_by_family = {}
        chinese_names = {}
        try:
            chinese_names = layer.get_font_cn_names()
        except Exception:
            logger.debug("读取字体中文名失败", exc_info=True)

        options = self._load_text_font_options(layer)
        groups = []
        for family_option in options:
            family = str(family_option.get("value", "") or "").strip()
            if not family:
                continue
            faces = []
            for face in faces_by_family.get(family, []) or []:
                style = str(face.get("style", "Regular") or "Regular").strip()
                faces.append({
                    "label": self._font_face_label(style),
                    "value": style,
                    "face": style,
                    "family": family,
                    "weight": int(face.get("weight", 400) or 400),
                    "italic": bool(face.get("italic", False)),
                    "synthetic": False,
                })
            if not faces:
                faces = [{
                    "label": "常规",
                    "value": "Regular",
                    "face": "Regular",
                    "family": family,
                    "weight": 400,
                    "italic": False,
                    "synthetic": True,
                }]
            faces.sort(key=lambda item: (item["weight"], item["italic"], item["value"].casefold()))
            groups.append({
                "label": str(chinese_names.get(family, "") or family),
                "value": family,
                "family": family,
                "children": faces,
            })
        return groups

    def _font_catalog_fallback_options(self):
        current = str(getattr(self._selected_layer(), "font_family", "") or "").strip()
        families = [
            current,
            "Microsoft YaHei",
            "SimHei",
            "SimSun",
            "KaiTi",
            "FangSong",
        ]
        options = []
        seen = set()
        for family in families:
            family = str(family or "").strip()
            key = family.casefold()
            if not family or key in seen:
                continue
            seen.add(key)
            options.append({"label": family, "value": family})
        return options

    def _font_catalog_fallback_tree(self):
        current_family = str(getattr(self._selected_layer(), "font_family", "") or "").strip()
        current_face = str(getattr(self._selected_layer(), "font_face", "") or "Regular").strip()
        groups = []
        for option in self._font_catalog_fallback_options():
            family = option["value"]
            face = current_face if family.casefold() == current_family.casefold() else "Regular"
            groups.append(
                {
                    "label": option["label"],
                    "value": family,
                    "family": family,
                    "children": [
                        {
                            "label": self._font_face_label(face),
                            "value": face,
                            "face": face,
                            "family": family,
                            "weight": 400,
                            "italic": False,
                            "synthetic": True,
                        }
                    ],
                }
            )
        return groups

    @Property("QVariantList", notify=fontCatalogChanged)
    def textFontOptions(self):
        if self._text_font_options_cache is None:
            self.startFontCatalogPreload()
            return self._font_catalog_fallback_options()
        return list(self._text_font_options_cache)

    @Property("QVariantList", notify=fontCatalogChanged)
    def textFontTreeOptions(self):
        if self._text_font_tree_options_cache is None:
            self.startFontCatalogPreload()
            return self._font_catalog_fallback_tree()
        return list(self._text_font_tree_options_cache)

    def startFontCatalogPreload(self):
        if self._font_catalog_loading or self._text_font_tree_options_cache is not None:
            return
        self._font_catalog_loading = True
        threading.Thread(
            target=self._font_catalog_worker,
            name="QmlFontCatalog",
            daemon=True,
        ).start()

    def _font_catalog_worker(self):
        options = []
        tree = []
        try:
            from app.models.text_layer_font import TextLayerFontMixin, get_fonts_cache_file

            class _Scanner(TextLayerFontMixin):
                _fonts_cache_file = get_fonts_cache_file()

            scanner = _Scanner()
            options = self._load_text_font_options(scanner)
            tree = self._load_text_font_tree_options(scanner)
        except Exception:
            logger.debug("后台预加载字体目录失败", exc_info=True)
        self._fontCatalogLoaded.emit(options, tree)

    @Slot(object, object)
    def _on_font_catalog_loaded(self, options, tree):
        self._font_catalog_loading = False
        if options:
            self._text_font_options_cache = list(options)
        if tree:
            self._text_font_tree_options_cache = list(tree)
        self.fontCatalogChanged.emit()

    @Property("QVariantList", notify=fontCatalogChanged)
    def selectedTextFontOptions(self):
        if not self.selectedIsTextLayer:
            return []
        current = self.selectedTextFontFamily
        options = self.textFontOptions
        if not current:
            return options
        current_key = current.casefold()
        current_option = next(
            (option for option in options if str(option.get("value", "")).casefold() == current_key),
            None,
        )
        if current_option is None:
            return options
        return [current_option] + [
            option for option in options
            if str(option.get("value", "")).casefold() != current_key
        ]

    @Property("QVariantList", notify=fontCatalogChanged)
    def selectedTextFontTreeOptions(self):
        return self.textFontTreeOptions if self.selectedIsTextLayer else []

    @Property(str, notify=selectionChanged)
    def selectedTextFontFace(self) -> str:
        if not self.selectedIsTextLayer:
            return ""
        return str(getattr(self._selected_layer(), "font_face", "") or "")

    def _selected_font_face(self, family: str = "", face: str = ""):
        family = family or self.selectedTextFontFamily
        face = face or self.selectedTextFontFace
        for group in self.textFontTreeOptions:
            if str(group.get("family", "")).casefold() != str(family).casefold():
                continue
            for item in group.get("children", []) or []:
                if str(item.get("face", "")).casefold() == str(face).casefold():
                    return item
        return None

    def _nearest_font_face(self, bold: bool, italic: bool):
        family = self.selectedTextFontFamily
        candidates = []
        for group in self.textFontTreeOptions:
            if str(group.get("family", "")).casefold() == family.casefold():
                candidates = [
                    item for item in (group.get("children", []) or [])
                    if not bool(item.get("synthetic", False))
                ]
                break
        if not candidates:
            return None
        same_italic = [item for item in candidates if bool(item.get("italic")) == bool(italic)]
        if same_italic:
            candidates = same_italic
        target_weight = 700 if bold else 400
        return min(candidates, key=lambda item: abs(int(item.get("weight", 400)) - target_weight))

    def _canonical_text_font_family(self, family: str) -> str:
        requested = str(family or "").strip()
        requested_key = requested.casefold()
        for option in self.textFontOptions:
            value = str(option.get("value", "") or "").strip()
            label = str(option.get("label", value) or value).strip()
            aliases = {value.casefold(), label.casefold()}
            suffix = f" ({value})"
            if value and label.endswith(suffix):
                aliases.add(label[:-len(suffix)].strip().casefold())
            if requested_key in aliases:
                return value
        return requested

    def _selected_text_style_name(self) -> str:
        if not self.selectedIsTextLayer:
            return "NORMAL"
        return str(getattr(self._selected_layer(), "font_style", "NORMAL") or "NORMAL").upper()

    @Property(bool, notify=selectionChanged)
    def selectedTextBold(self) -> bool:
        face = self._selected_font_face()
        if face is not None:
            return int(face.get("weight", 400)) >= 600
        return self._selected_text_style_name() in ("BOLD", "BOLD_ITALIC")

    @Property(bool, notify=selectionChanged)
    def selectedTextItalic(self) -> bool:
        face = self._selected_font_face()
        if face is not None:
            return bool(face.get("italic", False))
        return self._selected_text_style_name() in ("ITALIC", "BOLD_ITALIC")

    @Property(str, notify=selectionChanged)
    def selectedTextAlignmentId(self) -> str:
        if not self.selectedIsTextLayer:
            return "left"
        value = str(getattr(self._selected_layer(), "text_align", "LEFT") or "LEFT").upper()
        return _TEXT_ALIGNMENT_IDS.get(value, "left")

    @Property(str, notify=selectionChanged)
    def selectedTextAlignmentName(self) -> str:
        return _TEXT_ALIGNMENTS[self.selectedTextAlignmentId][1]

    @Property(int, notify=selectionChanged)
    def selectedTextLineSpacingPercent(self) -> int:
        if not self.selectedIsTextLayer:
            return 120
        return round(float(getattr(self._selected_layer(), "line_spacing", 1.2)) * 100)

    @Property(int, notify=selectionChanged)
    def selectedTextLetterSpacing(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        return int(getattr(self._selected_layer(), "letter_spacing", 0))

    @Property(int, notify=selectionChanged)
    def selectedTextBoxPadding(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        return int(getattr(self._selected_layer(), "text_box_padding", 0))

    @Property(bool, notify=selectionChanged)
    def selectedTextAutoFitTextBox(self) -> bool:
        return self.selectedIsTextLayer and bool(
            getattr(self._selected_layer(), "auto_fit_text_box", False)
        )

    @Property(bool, notify=selectionChanged)
    def selectedTextVerticalLayout(self) -> bool:
        return self.selectedIsTextLayer and bool(
            getattr(self._selected_layer(), "vertical_layout", False)
        )

    @Property(str, notify=selectionChanged)
    def selectedTextTypographySummary(self) -> str:
        direction = "竖排" if self.selectedTextVerticalLayout else "横排"
        box_mode = "自动文本框" if self.selectedTextAutoFitTextBox else "手动文本框"
        return f"{self.selectedTextAlignmentName} · {direction} · {box_mode}"

    @Property(str, notify=selectionChanged)
    def selectedTextColor(self) -> str:
        if not self.selectedIsTextLayer:
            return "#000000"
        return self._rgba_to_hex(getattr(self._selected_layer(), "text_color", (0, 0, 0, 255)))

    @Property(str, notify=selectionChanged)
    def selectedTextFillModeId(self) -> str:
        if not self.selectedIsTextLayer:
            return "solid"
        return "gradient" if bool(getattr(self._selected_layer(), "gradient_enabled", False)) else "solid"

    @Property(str, notify=selectionChanged)
    def selectedTextFillModeName(self) -> str:
        return "渐变" if self.selectedTextFillModeId == "gradient" else "纯色"

    @Property(str, notify=selectionChanged)
    def selectedTextGradientTypeId(self) -> str:
        if not self.selectedIsTextLayer:
            return "linear"
        value = str(getattr(self._selected_layer(), "gradient_type", "LINEAR") or "LINEAR").upper()
        return _TEXT_GRADIENT_TYPE_IDS.get(value, "linear")

    @Property(str, notify=selectionChanged)
    def selectedTextGradientTypeName(self) -> str:
        return _TEXT_GRADIENT_TYPES[self.selectedTextGradientTypeId][1]

    @Property(str, notify=selectionChanged)
    def selectedTextGradientDirectionId(self) -> str:
        if not self.selectedIsTextLayer:
            return "horizontal"
        value = str(getattr(self._selected_layer(), "gradient_direction", "HORIZONTAL") or "HORIZONTAL").upper()
        return _TEXT_GRADIENT_DIRECTION_IDS.get(value, "horizontal")

    @Property(str, notify=selectionChanged)
    def selectedTextGradientDirectionName(self) -> str:
        return _TEXT_GRADIENT_DIRECTIONS[self.selectedTextGradientDirectionId][1]

    @Property(str, notify=selectionChanged)
    def selectedTextGradientStartColor(self) -> str:
        if not self.selectedIsTextLayer:
            return "#000000"
        return self._rgba_to_hex(
            getattr(self._selected_layer(), "gradient_start_color", (255, 0, 0, 255))
        )

    @Property(str, notify=selectionChanged)
    def selectedTextGradientEndColor(self) -> str:
        if not self.selectedIsTextLayer:
            return "#FFFFFF"
        return self._rgba_to_hex(
            getattr(self._selected_layer(), "gradient_end_color", (0, 0, 255, 255))
        )

    @Property(int, notify=selectionChanged)
    def selectedTextGradientCenterXPercent(self) -> int:
        if not self.selectedIsTextLayer:
            return 50
        return round(float(getattr(self._selected_layer(), "gradient_center_x", 0.5)) * 100)

    @Property(int, notify=selectionChanged)
    def selectedTextGradientCenterYPercent(self) -> int:
        if not self.selectedIsTextLayer:
            return 50
        return round(float(getattr(self._selected_layer(), "gradient_center_y", 0.5)) * 100)

    @Property(str, notify=selectionChanged)
    def selectedTextFillSummary(self) -> str:
        if self.selectedTextFillModeId == "solid":
            return self.selectedTextColor
        return f"{self.selectedTextGradientTypeName} · {self.selectedTextGradientDirectionName}"

    @Property(bool, notify=selectionChanged)
    def selectedTextBackgroundEnabled(self) -> bool:
        return self.selectedIsTextLayer and bool(
            getattr(self._selected_layer(), "background_enabled", False)
        )

    @Property(str, notify=selectionChanged)
    def selectedTextBackgroundColor(self) -> str:
        if not self.selectedIsTextLayer:
            return "#FFFFFF80"
        return self._rgba_to_hex(
            getattr(self._selected_layer(), "background_color", (255, 255, 255, 128))
        )

    @Property(int, notify=selectionChanged)
    def selectedTextBackgroundOpacity(self) -> int:
        if not self.selectedIsTextLayer:
            return 50
        color = getattr(self._selected_layer(), "background_color", (255, 255, 255, 128))
        alpha = color[3] if isinstance(color, (tuple, list)) and len(color) > 3 else 255
        return round(max(0, min(255, int(alpha))) / 255.0 * 100)

    @Property(int, notify=selectionChanged)
    def selectedTextBackgroundPadding(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        return int(getattr(self._selected_layer(), "background_padding", 0))

    @Property(str, notify=selectionChanged)
    def selectedTextBackgroundSummary(self) -> str:
        if not self.selectedTextBackgroundEnabled:
            return "关闭"
        return f"{self.selectedTextBackgroundOpacity}% · {self.selectedTextBackgroundPadding:+d} px"

    @Property(int, notify=selectionChanged)
    def selectedTextColorRangeCount(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        getter = getattr(self._selected_layer(), "get_text_color_ranges", None)
        return len(getter()) if callable(getter) else 0

    @Property(int, notify=selectionChanged)
    def selectedTextFontSizeRangeCount(self) -> int:
        if not self.selectedIsTextLayer:
            return 0
        getter = getattr(self._selected_layer(), "get_font_size_ranges", None)
        return len(getter()) if callable(getter) else 0

    @Property(bool, notify=selectionChanged)
    def selectedTextShadowEnabled(self) -> bool:
        return self.selectedIsTextLayer and bool(
            getattr(self._selected_layer(), "shadow_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedTextShadowOffsetX(self) -> int:
        return int(getattr(self._selected_layer(), "shadow_offset_x", 2))

    @Property(int, notify=selectionChanged)
    def selectedTextShadowOffsetY(self) -> int:
        return int(getattr(self._selected_layer(), "shadow_offset_y", 2))

    @Property(int, notify=selectionChanged)
    def selectedTextShadowBlur(self) -> int:
        return int(getattr(self._selected_layer(), "shadow_blur", 4))

    @Property(str, notify=selectionChanged)
    def selectedTextShadowColor(self) -> str:
        return self._rgba_to_hex(
            getattr(self._selected_layer(), "shadow_color", (0, 0, 0, 128))
        )

    @Property(int, notify=selectionChanged)
    def selectedTextShadowOpacity(self) -> int:
        color = getattr(self._selected_layer(), "shadow_color", (0, 0, 0, 128))
        alpha = color[3] if isinstance(color, (tuple, list)) and len(color) > 3 else 255
        return round(max(0, min(255, int(alpha))) / 255.0 * 100)

    @Property(str, notify=selectionChanged)
    def selectedTextShadowSummary(self) -> str:
        if not self.selectedTextShadowEnabled:
            return "关闭"
        return (
            f"{self.selectedTextShadowOffsetX:+d} / {self.selectedTextShadowOffsetY:+d} px"
            f" · 模糊 {self.selectedTextShadowBlur}"
        )

    @Property(bool, notify=selectionChanged)
    def selectedTextGlowEnabled(self) -> bool:
        return self.selectedIsTextLayer and bool(
            getattr(self._selected_layer(), "glow_enabled", False)
        )

    @Property(int, notify=selectionChanged)
    def selectedTextGlowStrength(self) -> int:
        return int(getattr(self._selected_layer(), "glow_strength", 5))

    @Property(int, notify=selectionChanged)
    def selectedTextGlowRadius(self) -> int:
        return int(getattr(self._selected_layer(), "glow_radius", 10))

    @Property(str, notify=selectionChanged)
    def selectedTextGlowColor(self) -> str:
        return self._rgba_to_hex(
            getattr(self._selected_layer(), "glow_color", (255, 255, 255, 255))
        )

    @Property(int, notify=selectionChanged)
    def selectedTextGlowOpacity(self) -> int:
        color = getattr(self._selected_layer(), "glow_color", (255, 255, 255, 255))
        alpha = color[3] if isinstance(color, (tuple, list)) and len(color) > 3 else 255
        return round(max(0, min(255, int(alpha))) / 255.0 * 100)

    @Property(str, notify=selectionChanged)
    def selectedTextGlowSummary(self) -> str:
        if not self.selectedTextGlowEnabled:
            return "关闭"
        return (
            f"强度 {self.selectedTextGlowStrength}"
            f" · 半径 {self.selectedTextGlowRadius} px"
            f" · {self._rgba_to_hex(getattr(self._selected_layer(), 'glow_color', (255, 255, 255, 255)))}"
        )

    @Property(bool, notify=styleClipboardChanged)
    def hasLayerStyleClipboard(self) -> bool:
        return bool(self._layer_style_clipboard)

    @Property(str, notify=styleClipboardChanged)
    def layerStyleClipboardSummary(self) -> str:
        if not self._layer_style_clipboard:
            return "尚未复制样式"
        return str(self._layer_style_clipboard.get("summary", "已复制图层样式"))

    @Property(bool, notify=selectionChanged)
    def canDuplicateLayer(self) -> bool:
        layer = self._selected_layer()
        return bool(
            layer is not None
            and not self._export_running
            and not bool(getattr(layer, "locked", False))
            and callable(getattr(layer, "duplicate", None))
        )

    @Property(bool, notify=selectionChanged)
    def canMoveLayerForward(self) -> bool:
        index = self.selectedLayerIndex
        layer = self._selected_layer()
        neighbor = self._layer_model.layer_at(index + 1)
        return bool(
            layer is not None
            and neighbor is not None
            and not self._export_running
            and not bool(getattr(layer, "locked", False))
            and not bool(getattr(neighbor, "locked", False))
        )

    @Property(bool, notify=selectionChanged)
    def canMoveLayerBackward(self) -> bool:
        index = self.selectedLayerIndex
        layer = self._selected_layer()
        neighbor = self._layer_model.layer_at(index - 1)
        return bool(
            layer is not None
            and neighbor is not None
            and not self._export_running
            and not bool(getattr(layer, "locked", False))
            and not bool(getattr(neighbor, "locked", False))
        )

    @Property(int, notify=previewChanged)
    def previewRevision(self) -> int:
        return self._preview_revision

    @Property(str, notify=previewChanged)
    def previewSource(self) -> str:
        return f"image://documentPreview/current?revision={self._preview_revision}"

    @Property(str, notify=statusChanged)
    def statusMessage(self) -> str:
        return self._status_message

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=historyStateChanged)
    def canUndo(self) -> bool:
        return bool(self._document and self._document.can_undo())

    @Property(bool, notify=historyStateChanged)
    def canRedo(self) -> bool:
        return bool(self._document and self._document.can_redo())

    @Property(bool, notify=exportStateChanged)
    def exportRunning(self) -> bool:
        return self._export_running

    @Property(bool, notify=exportStateChanged)
    def operationsBlocked(self) -> bool:
        return self._export_running

    @Slot(bool)
    def setExportRunning(self, running: bool) -> None:
        running = bool(running)
        if running != self._export_running:
            self._export_running = running
            self.exportStateChanged.emit()

    def _ensure_operations_available(self) -> bool:
        if not self._export_running:
            return True
        self._set_status("批量导出期间无法修改或切换文档", toast=True)
        return False

    def _set_busy(self, busy: bool) -> None:
        busy = bool(busy)
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit()

    def _set_status(self, message: str, *, toast: bool = False) -> None:
        self._status_message = str(message)
        self.statusChanged.emit()
        if toast:
            self.toastRequested.emit(self._status_message)

    def _set_document(self, document: Document) -> None:
        with self._document_lock:
            if self._crop_edit_original is not None and self._document is not None:
                old_layer = self._layer_model.layer_at(self._crop_edit_index)
                if old_layer is not None:
                    old_layer.crop_rect = list(self._crop_edit_original)
                self._document.is_modified = self._crop_edit_was_modified
            self._crop_edit_index = -1
            self._crop_edit_original = None
            self._selected_vector_node_index = -1
            self._selection_anchor_index = -1
            self._corner_edit_modes.clear()
            self._disconnect_document()
            self._document = document
            self._layer_model.set_document(document)
            self._connect_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.cropEditChanged.emit()
        self.vectorEditChanged.emit()
        self.viewSettingsChanged.emit()
        self.documentObjectChanged.emit(document)

    @Slot(object, result=bool)
    def activateDocument(self, document) -> bool:
        if not self._ensure_operations_available():
            return False
        if not isinstance(document, Document):
            self._set_status("无法切换到无效文档", toast=True)
            return False
        if document is self._document:
            return True

        self._preview_timer.stop()
        self._render_request_id += 1
        self._render_pending = False
        self._preview_provider.clear()
        self._preview_revision += 1
        self._set_document(document)
        self.previewChanged.emit()
        self._set_status(f"已切换到 {self.documentTitle}")
        self.requestPreview(force=True)
        return True

    def _connect_document(self) -> None:
        if self._document is None:
            return
        self._document.document_changed.connect(self._on_document_changed)
        self._document.layer_selected.connect(self._on_layer_selected)
        self._document.layers_selection_changed.connect(self._on_layers_selected)
        self._document.history_changed.connect(self.historyStateChanged.emit)

    def _disconnect_document(self) -> None:
        if self._document is None:
            return
        connections = (
            (self._document.document_changed, self._on_document_changed),
            (self._document.layer_selected, self._on_layer_selected),
            (self._document.layers_selection_changed, self._on_layers_selected),
            (self._document.history_changed, self.historyStateChanged.emit),
        )
        for signal, slot in connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    @Slot()
    def _on_document_changed(self) -> None:
        self.documentInfoChanged.emit()
        if self._suppress_document_selection_notify <= 0:
            self.selectionChanged.emit()

    @Slot(int)
    def _on_layer_selected(self, index: int) -> None:
        del index
        self.selectionChanged.emit()

    @Slot(list)
    def _on_layers_selected(self, indices) -> None:
        del indices
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()

    @staticmethod
    def _local_path(path_or_url: str) -> str:
        text = str(path_or_url or "")
        url = QUrl(text)
        if url.isLocalFile():
            return url.toLocalFile()
        return text

    @staticmethod
    def _image_files(directory: str):
        if not directory or not os.path.isdir(directory):
            return []
        extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
        try:
            return sorted(
                str(path)
                for path in Path(directory).iterdir()
                if path.is_file() and path.suffix.lower() in extensions
            )
        except OSError:
            return []

    @staticmethod
    def _clear_image_layer_cache(layer) -> None:
        for attr in ("_cached_image", "_cached_image_path", "_cached_source_image", "_cached_source_path"):
            if hasattr(layer, attr):
                setattr(layer, attr, None)
        if hasattr(layer, "cached_image"):
            layer.cached_image = None

    def _publish_content_change(self, index: int, status: str) -> None:
        self._layer_model.notify_row(index)
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(status, toast=True)

    def _validated_image_source(self, source_path: str):
        source_path = self._local_path(source_path)
        if os.path.isdir(source_path):
            files = self._image_files(source_path)
            if not files:
                self._set_status("素材文件夹没有可用图片", toast=True)
                return None
            return source_path, True, files[0], files
        if os.path.isfile(source_path):
            try:
                from PIL import Image

                with Image.open(source_path) as image:
                    image.verify()
            except Exception:
                self._set_status("所选文件不是可读取的图片", toast=True)
                return None
            return source_path, False, source_path, [source_path]
        self._set_status("图片源不存在或无法访问", toast=True)
        return None

    def _add_image_source(self, source_path: str, *, require_folder: bool) -> bool:
        if not self._ensure_operations_available():
            return False
        validated = self._validated_image_source(source_path)
        if validated is None:
            return False
        source_path, is_folder, preview_path, files = validated
        if require_folder and not is_folder:
            self._set_status("请选择素材文件夹", toast=True)
            return False
        if not require_folder and is_folder:
            self._set_status("请选择单张图片文件", toast=True)
            return False

        try:
            from PIL import Image

            with Image.open(preview_path) as image:
                source_width, source_height = image.size
            if source_width <= 0 or source_height <= 0:
                raise ValueError("图片尺寸无效")

            max_width = max(1, round(self.canvasWidth * 0.6))
            max_height = max(1, round(self.canvasHeight * 0.6))
            scale = min(max_width / source_width, max_height / source_height, 1.0)
            width = max(1, round(source_width * scale))
            height = max(1, round(source_height * scale))
            x = (self.canvasWidth - width) // 2
            y = (self.canvasHeight - height) // 2

            with self._document_lock:
                self._ensure_history_baseline()
                layer = self._document.add_layer(
                    os.path.basename(source_path),
                    x,
                    y,
                    width,
                    height,
                    image_source=source_path,
                    use_original_size=False,
                    is_folder=is_folder,
                )
                layer.current_image_path = preview_path
                self._clear_image_layer_cache(layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加图片源失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        if is_folder:
            self._set_status(f"已添加素材文件夹 · {len(files)} 张", toast=True)
        else:
            self._set_status(f"已添加图片 {os.path.basename(source_path)}", toast=True)
        return True

    @Slot(int, int, result=bool)
    def newDocument(self, width: int = 1080, height: int = 1350) -> bool:
        if not self._ensure_operations_available():
            return False
        if width <= 0 or height <= 0:
            self._set_status("新建失败：画布尺寸无效", toast=True)
            return False
        document = Document()
        document.create_new(int(width), int(height))
        document._history_manager.clear()
        document.save_state("初始状态")
        self._preview_provider.clear()
        self._preview_revision += 1
        self._set_document(document)
        self.previewChanged.emit()
        self._set_status("已新建空白文档", toast=True)
        self.requestPreview(force=True)
        return True

    @Slot(str, result=bool)
    def createDemoDocument(self, image_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        image_path = self._local_path(image_path)
        if not os.path.isfile(image_path):
            self._set_status("示例文档创建失败：素材不存在", toast=True)
            return False
        from app.models.text_layer import TextLayer

        document = Document()
        document.create_new(1080, 1350)
        document.add_layer(
            "产品底图",
            0,
            0,
            1080,
            1350,
            image_source=image_path,
            use_original_size=False,
            is_folder=False,
        )
        title = TextLayer(name="限量腕表", x=68, y=1040, width=860, height=160)
        title.text_content = "限量腕表"
        title.current_text = "限量腕表"
        title.font_size = 86
        title.text_color = (245, 244, 238, 255)
        title.background_enabled = True
        title.background_color = (17, 24, 22, 238)
        title.background_padding = 24
        title.auto_fit_text_box = False
        document.add_text_layer(title)
        subtitle = TextLayer(name="曜石黑 · 2026", x=76, y=1210, width=680, height=70)
        subtitle.text_content = "曜石黑 · 2026 EDITION"
        subtitle.current_text = "曜石黑 · 2026 EDITION"
        subtitle.font_size = 34
        subtitle.text_color = (70, 215, 173, 255)
        subtitle.auto_fit_text_box = False
        document.add_text_layer(subtitle)
        document.selected_layer_index = 1
        document.selected_layer_indices = [1]
        document.current_file_path = None
        document.is_modified = False
        document._history_manager.clear()
        document.save_state("初始状态")
        self._set_document(document)
        self._set_status("已载入真实模型示例", toast=True)
        self.requestPreview(force=True)
        return True

    @Slot(str, result=bool)
    def openDocument(self, file_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        file_path = self._local_path(file_path)
        candidate = Document()
        if not file_path or not candidate.load_document(file_path):
            self._set_status("打开失败：无法读取项目文件", toast=True)
            return False
        candidate._history_manager.clear()
        candidate.save_state("打开文档")
        self._set_document(candidate)
        self._set_status(f"已打开 {os.path.basename(file_path)}", toast=True)
        self.requestPreview(force=True)
        return True

    @Slot(result=bool)
    def saveDocument(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self.documentPath:
            self._set_status("请先选择项目保存位置", toast=True)
            return False
        return self.saveDocumentTo(self.documentPath)

    @Slot(str, result=bool)
    def saveDocumentTo(self, file_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        file_path = self._local_path(file_path)
        if not file_path:
            self._set_status("保存失败：文件路径为空", toast=True)
            return False
        if not file_path.lower().endswith(".cmp"):
            file_path += ".cmp"
        with self._document_lock:
            success = bool(self._document.save_document(file_path))
        if success:
            self.documentInfoChanged.emit()
            self._set_status(f"已保存 {os.path.basename(file_path)}", toast=True)
        else:
            self._set_status("保存失败：请检查文件路径和权限", toast=True)
        return success

    @Slot(str, result=bool)
    def exportImageTo(self, file_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        file_path = self._local_path(file_path)
        if not file_path:
            self._set_status("导出失败：文件路径为空", toast=True)
            return False
        self._set_busy(True)
        try:
            with self._document_lock:
                success = bool(self._document.export_image(file_path))
        finally:
            self._set_busy(False)
        if success:
            self._set_status(f"已导出 {os.path.basename(file_path)}", toast=True)
        else:
            error = getattr(self._document, "_last_export_error", None) or "未知错误"
            self._set_status(f"导出失败：{error}", toast=True)
        return success

    @Slot(str, result=bool)
    def addImageLayer(self, file_path: str) -> bool:
        return self._add_image_source(file_path, require_folder=False)

    @Slot(result=bool)
    def addEmptyImageLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        try:
            with self._document_lock:
                layer_name = f"图层 {len(self._document.layers) + 1}"
                self._document.add_layer(
                    name=layer_name,
                    x=0,
                    y=0,
                    width=200,
                    height=200,
                    image_source=None,
                    use_original_size=False,
                    is_folder=True,
                )
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加图层失败：{error}", toast=True)
            return False
        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"成功添加图层：{layer_name}", toast=True)
        return True

    @Slot(str, result=bool)
    def addImageFolder(self, folder_path: str) -> bool:
        return self._add_image_source(folder_path, require_folder=True)

    @Slot(str, str, result=bool)
    def addShapedLayer(self, file_path: str, shape_id: str) -> bool:
        if not self._ensure_operations_available():
            return False
        shape_id = str(shape_id or "").strip().lower()
        shape_entry = _SHAPE_TYPES.get(shape_id)
        if shape_entry is None:
            self._set_status("不支持的异形类型", toast=True)
            return False
        validated = self._validated_image_source(file_path)
        if validated is None:
            return False
        source_path, is_folder, preview_path, _files = validated
        if is_folder:
            self._set_status("异形图层创建请选择单张图片", toast=True)
            return False

        try:
            from PIL import Image

            with Image.open(preview_path) as image:
                source_width, source_height = image.size
            if source_width <= 0 or source_height <= 0:
                raise ValueError("图片尺寸无效")
            max_width = max(1, round(self.canvasWidth * 0.6))
            max_height = max(1, round(self.canvasHeight * 0.6))
            scale = min(max_width / source_width, max_height / source_height, 1.0)
            width = max(1, round(source_width * scale))
            height = max(1, round(source_height * scale))
            x = (self.canvasWidth - width) // 2
            y = (self.canvasHeight - height) // 2
            layer = ShapedLayer(
                name=f"{shape_entry[1]} · {os.path.basename(source_path)}",
                x=x,
                y=y,
                width=width,
                height=height,
                image_source=source_path,
                use_original_size=False,
                is_folder=False,
                current_image_path=preview_path,
                shape_type=shape_entry[0],
            )
            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_shaped_layer(layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加异形图层失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"已添加{shape_entry[1]}异形图层", toast=True)
        return True

    @Slot("QVariantMap", result=bool)
    def addConfiguredShapedLayer(self, config) -> bool:
        if not self._ensure_operations_available():
            return False
        config = dict(config or {})
        name = str(config.get("name", "") or "").strip()[:120]
        shape_id = str(config.get("shapeType", "rectangle") or "rectangle").strip().lower()
        shape_entry = _SHAPE_TYPES.get(shape_id)
        if not name:
            self._set_status("图层名称不能为空", toast=True)
            return False
        if shape_entry is None:
            self._set_status("不支持的异形类型", toast=True)
            return False
        try:
            x = int(float(config.get("x", 0)))
            y = int(float(config.get("y", 0)))
            width = int(float(config.get("width", 200)))
            height = int(float(config.get("height", 200)))
        except (TypeError, ValueError):
            self._set_status("异形图层的位置或尺寸无效", toast=True)
            return False
        if not 10 <= width <= 32768 or not 10 <= height <= 32768:
            self._set_status("异形图层尺寸必须在 10 到 32768 像素之间", toast=True)
            return False

        source = str(config.get("source", "") or "").strip()
        source_is_folder = bool(config.get("sourceIsFolder", True))
        source_path = None
        current_image_path = None
        if source:
            validated = self._validated_image_source(source)
            if validated is None:
                return False
            source_path, actual_is_folder, current_image_path, _files = validated
            if actual_is_folder != source_is_folder:
                expected = "素材文件夹" if source_is_folder else "单张图片"
                self._set_status(f"当前内容源模式需要选择{expected}", toast=True)
                return False
            source_is_folder = actual_is_folder

        try:
            layer = ShapedLayer(
                name=name,
                x=x,
                y=y,
                width=width,
                height=height,
                image_source=source_path,
                use_original_size=bool(config.get("useOriginalSize", False)) and not source_is_folder,
                is_folder=source_is_folder,
                current_image_path=current_image_path,
                shape_type=shape_entry[0],
            )
            if shape_id == "right_trapezoid":
                top_ratio = max(30, min(100, int(float(config.get("trapezoidTopRatio", 100)))))
                bottom_ratio = max(30, min(100, int(float(config.get("trapezoidBottomRatio", 80)))))
                slope_side = str(config.get("trapezoidSlopeSide", "right") or "right").lower()
                layer.trapezoid_top_width = round(width * top_ratio / 100)
                layer.trapezoid_bottom_width = round(width * bottom_ratio / 100)
                layer.trapezoid_slope_side = slope_side if slope_side in ("left", "right") else "right"
            elif shape_id in ("pentagon", "hexagon"):
                layer.polygon_rotation = float(config.get("polygonRotation", 0)) % 360.0
                layer.polygon_corner_radius = max(0, int(float(config.get("polygonCornerRadius", 0))))

            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_shaped_layer(layer)
                self._document.is_modified = True
        except (TypeError, ValueError) as error:
            self._set_status(f"异形图层参数无效：{error}", toast=True)
            return False
        except Exception as error:
            self._set_status(f"添加异形图层失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"已添加{shape_entry[1]}异形图层", toast=True)
        return True

    @Slot(str, result=bool)
    def setSelectedImageSource(self, source_path: str) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if not self.selectedHasImageSource or layer is None:
            self._set_status("当前图层没有图片内容源", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        validated = self._validated_image_source(source_path)
        if validated is None:
            return False
        source_path, is_folder, preview_path, files = validated
        index = self.selectedLayerIndex

        with self._document_lock:
            self._ensure_history_baseline()
            layer.image_source = source_path
            layer.is_folder = is_folder
            layer.current_image_path = preview_path
            self._clear_image_layer_cache(layer)
            self._document.is_modified = True
            self._document.bump_hit_test_version()
            self._document._invalidate_render_cache()
            self._document.save_state("更改图片内容源")

        description = f"素材文件夹 · {len(files)} 张" if is_folder else os.path.basename(source_path)
        self._publish_content_change(index, f"已更新图片源 · {description}")
        return True

    @Slot(result=bool)
    def showNextSelectedImage(self) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if not self.selectedImageSourceIsFolder or layer is None:
            self._set_status("当前图片源不是素材文件夹", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        files = self._image_files(self.selectedImageSource)
        if not files:
            self._set_status("素材文件夹没有可用图片", toast=True)
            return False
        current = os.path.normcase(str(getattr(layer, "current_image_path", "") or ""))
        normalized = [os.path.normcase(path) for path in files]
        next_index = (normalized.index(current) + 1) % len(files) if current in normalized else 0
        preview_path = files[next_index]
        index = self.selectedLayerIndex

        with self._document_lock:
            self._ensure_history_baseline()
            layer.current_image_path = preview_path
            self._clear_image_layer_cache(layer)
            self._document.is_modified = True
            self._document._invalidate_render_cache()
            self._document.save_state("切换素材预览")

        self._publish_content_change(index, f"当前素材 · {os.path.basename(preview_path)}")
        return True

    @Slot(result=bool)
    def addTextLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        from app.models.text_layer import TextLayer

        width = max(120, min(round(self.canvasWidth * 0.6), 600))
        height = max(64, min(round(self.canvasHeight * 0.12), 180))
        x = (self.canvasWidth - width) // 2
        y = (self.canvasHeight - height) // 2
        text_layer = TextLayer(name="新建文字", x=x, y=y, width=width, height=height)
        text_layer.current_text = "新建文字"
        text_layer.font_size = max(24, min(round(height * 0.45), 72))
        text_layer.auto_fit_text_box = False

        try:
            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_text_layer(text_layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加文字失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已添加文字图层", toast=True)
        return True

    @Slot("QVariantMap", result=bool)
    def addConfiguredTextLayer(self, config) -> bool:
        if not self._ensure_operations_available():
            return False
        from app.models.text_layer import TextLayer

        config = dict(config or {})
        name = str(config.get("name", "") or "").strip()[:120]
        content = str(config.get("content", "") or "")
        font_family = str(config.get("fontFamily", "Microsoft YaHei") or "").strip()
        alignment = str(config.get("alignment", "left") or "left").strip().lower()
        color = self._parse_hex_color(str(config.get("color", "#000000") or "#000000"))
        try:
            font_size = int(float(config.get("fontSize", 24)))
        except (TypeError, ValueError):
            font_size = 0

        if not name:
            self._set_status("图层名称不能为空", toast=True)
            return False
        if not content.strip():
            self._set_status("文字内容不能为空", toast=True)
            return False
        if not font_family:
            self._set_status("字体名称不能为空", toast=True)
            return False
        if not 6 <= font_size <= 240:
            self._set_status("字号必须在 6 到 240 像素之间", toast=True)
            return False
        if alignment not in _TEXT_ALIGNMENTS:
            self._set_status("不支持的文字对齐方式", toast=True)
            return False
        if color is None:
            self._set_status("文字颜色格式无效", toast=True)
            return False

        try:
            text_layer = TextLayer(name=name, x=50, y=50, width=300, height=100)
            text_layer.auto_fit_text_box = False
            text_layer.text_binding_enabled = bool(config.get("bindingEnabled", True))
            text_layer.font_family = font_family
            text_layer.font_face = str(config.get("fontFace", "") or "").strip()
            text_layer.font_size = font_size
            text_layer.text_color = color
            text_layer.text_align = _TEXT_ALIGNMENTS[alignment][0]
            lines = text_layer.parse_text_input_to_lines(content)
            text_layer.set_text_lines(lines)
            text_layer.set_current_text(lines[0], force=True)

            with self._document_lock:
                self._ensure_history_baseline()
                self._document.add_text_layer(text_layer)
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"添加文字失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已添加文字图层", toast=True)
        return True

    def _change_text_layer(self, index: int, action: str, mutator, status: str) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._layer_model.layer_at(int(index))
        if layer is None or self._layer_model.layer_type_name(layer) != "文字":
            self._set_status("当前图层不是文字图层", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            mutator(layer)
            self._document.is_modified = True
            self._document.bump_hit_test_version()
            self._document._invalidate_render_cache()
            self._document.save_state(action)
        self._publish_content_change(index, status)
        return True

    def _change_selected_text(self, action: str, mutator, status: str) -> bool:
        return self._change_text_layer(self.selectedLayerIndex, action, mutator, status)

    @Slot(int, str, result=bool)
    def setTextContentForLayer(self, index: int, content: str) -> bool:
        content = str(content or "")

        def apply(layer) -> None:
            lines = layer.parse_text_input_to_lines(content)
            layer.set_text_lines(lines)
            layer.set_current_text(lines[0] if lines else "", force=True)

        return self._change_text_layer(
            int(index),
            "修改文字内容",
            apply,
            "文字内容已更新",
        )

    @Slot(str, result=bool)
    def setSelectedTextContent(self, content: str) -> bool:
        return self.setTextContentForLayer(self.selectedLayerIndex, content)

    @Slot(bool, result=bool)
    def setSelectedTextBindingEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)

        def apply(layer) -> None:
            layer.text_binding_enabled = enabled
            lines = layer.get_text_lines()
            layer.set_current_text(lines[0] if lines else "", force=True)

        mode = "按行随机" if enabled else "整段排版"
        return self._change_selected_text("切换文字内容模式", apply, f"文字模式 · {mode}")

    @Slot(int, result=bool)
    def setSelectedTextFontSize(self, value: int) -> bool:
        value = int(value)
        if not 1 <= value <= 1000:
            self._set_status("字号必须在 1 到 1000 之间", toast=True)
            return False
        return self._change_selected_text(
            "修改文字字号",
            lambda layer: setattr(layer, "font_size", value),
            f"文字字号 · {value} px",
        )

    @Slot(str, result=bool)
    def setSelectedTextFontFamily(self, family: str) -> bool:
        family = self._canonical_text_font_family(family)
        if not family:
            self._set_status("字体名称不能为空", toast=True)
            return False
        return self._change_selected_text(
            "修改文字字体",
            lambda layer: (setattr(layer, "font_family", family), setattr(layer, "font_face", "")),
            f"文字字体 · {family}",
        )

    @Slot(str, str, result=bool)
    def setSelectedTextFontFace(self, family: str, face: str) -> bool:
        family = self._canonical_text_font_family(family)
        face = str(face or "").strip()
        if not family or not face:
            self._set_status("字体字重不能为空", toast=True)
            return False
        if self._selected_font_face(family, face) is None:
            self._set_status("未找到所选字体字重", toast=True)
            return False

        def apply(layer) -> None:
            layer.font_family = family
            layer.font_face = face
            layer.font_style = "NORMAL"

        return self._change_selected_text(
            "修改文字字体字重",
            apply,
            f"文字字重 · {family} · {self._font_face_label(face)}",
        )

    @staticmethod
    def _font_style_name(bold: bool, italic: bool) -> str:
        if bold and italic:
            return "BOLD_ITALIC"
        if bold:
            return "BOLD"
        if italic:
            return "ITALIC"
        return "NORMAL"

    @Slot(bool, result=bool)
    def setSelectedTextBold(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        face = self._nearest_font_face(enabled, self.selectedTextItalic)
        if face is not None:
            return self.setSelectedTextFontFace(self.selectedTextFontFamily, face["face"])
        style = self._font_style_name(enabled, self.selectedTextItalic)
        return self._change_selected_text(
            "切换文字粗体",
            lambda layer: setattr(layer, "font_style", style),
            "文字粗体已开启" if enabled else "文字粗体已关闭",
        )

    @Slot(bool, result=bool)
    def setSelectedTextItalic(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        face = self._nearest_font_face(self.selectedTextBold, enabled)
        if face is not None:
            return self.setSelectedTextFontFace(self.selectedTextFontFamily, face["face"])
        style = self._font_style_name(self.selectedTextBold, enabled)
        return self._change_selected_text(
            "切换文字斜体",
            lambda layer: setattr(layer, "font_style", style),
            "文字斜体已开启" if enabled else "文字斜体已关闭",
        )

    @Slot(str, result=bool)
    def setSelectedTextAlignment(self, alignment_id: str) -> bool:
        alignment = _TEXT_ALIGNMENTS.get(str(alignment_id or "").strip().lower())
        if alignment is None:
            self._set_status("未知的文字对齐方式", toast=True)
            return False
        return self._change_selected_text(
            "修改文字对齐",
            lambda layer: setattr(layer, "text_align", alignment[0]),
            f"文字对齐 · {alignment[1]}",
        )

    @Slot(int, result=bool)
    def setSelectedTextLineSpacingPercent(self, value: int) -> bool:
        value = max(50, min(300, int(value)))
        return self._change_selected_text(
            "修改文字行距",
            lambda layer: setattr(layer, "line_spacing", value / 100.0),
            f"文字行距 · {value}%",
        )

    @Slot(int, result=bool)
    def setSelectedTextLetterSpacing(self, value: int) -> bool:
        value = max(-20, min(100, int(value)))
        return self._change_selected_text(
            "修改文字字距",
            lambda layer: setattr(layer, "letter_spacing", value),
            f"文字字距 · {value} px",
        )

    @Slot(int, result=bool)
    def setSelectedTextBoxPadding(self, value: int) -> bool:
        value = max(0, min(200, int(value)))
        return self._change_selected_text(
            "修改文字内边距",
            lambda layer: setattr(layer, "text_box_padding", value),
            f"文字内边距 · {value} px",
        )

    @Slot(bool, result=bool)
    def setSelectedTextAutoFitTextBox(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换自动文本框",
            lambda layer: setattr(layer, "auto_fit_text_box", enabled),
            "自动文本框已开启" if enabled else "自动文本框已关闭",
        )

    @Slot(bool, result=bool)
    def setSelectedTextVerticalLayout(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字排版方向",
            lambda layer: setattr(layer, "vertical_layout", enabled),
            "文字已切换为竖排" if enabled else "文字已切换为横排",
        )

    @Slot(str, result=bool)
    def setSelectedTextColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字颜色",
            lambda layer: setattr(layer, "text_color", color),
            f"文字颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(str, result=bool)
    def setSelectedTextFillMode(self, mode_id: str) -> bool:
        mode_id = str(mode_id or "").strip().lower()
        if mode_id not in ("solid", "gradient"):
            self._set_status("未知的文字填充模式", toast=True)
            return False
        enabled = mode_id == "gradient"
        return self._change_selected_text(
            "切换文字填充模式",
            lambda layer: setattr(layer, "gradient_enabled", enabled),
            "文字填充 · 渐变" if enabled else "文字填充 · 纯色",
        )

    @Slot(str, result=bool)
    def setSelectedTextGradientType(self, type_id: str) -> bool:
        gradient = _TEXT_GRADIENT_TYPES.get(str(type_id or "").strip().lower())
        if gradient is None:
            self._set_status("未知的文字渐变类型", toast=True)
            return False
        return self._change_selected_text(
            "修改文字渐变类型",
            lambda layer: setattr(layer, "gradient_type", gradient[0]),
            f"文字渐变 · {gradient[1]}",
        )

    @Slot(str, result=bool)
    def setSelectedTextGradientDirection(self, direction_id: str) -> bool:
        direction = _TEXT_GRADIENT_DIRECTIONS.get(
            str(direction_id or "").strip().lower()
        )
        if direction is None:
            self._set_status("未知的文字渐变方向", toast=True)
            return False
        return self._change_selected_text(
            "修改文字渐变方向",
            lambda layer: setattr(layer, "gradient_direction", direction[0]),
            f"文字渐变方向 · {direction[1]}",
        )

    @Slot(int, str, result=bool)
    def setSelectedTextGradientColor(self, index: int, value: str) -> bool:
        if index not in (0, 1):
            self._set_status("文字渐变颜色端点无效", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字渐变颜色格式无效", toast=True)
            return False
        attr = "gradient_start_color" if index == 0 else "gradient_end_color"
        return self._change_selected_text(
            "修改文字渐变颜色",
            lambda layer: setattr(layer, attr, color),
            f"文字渐变颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, int, result=bool)
    def setSelectedTextGradientCenter(self, x_percent: int, y_percent: int) -> bool:
        x_percent = max(0, min(100, int(x_percent)))
        y_percent = max(0, min(100, int(y_percent)))

        def apply(layer) -> None:
            layer.gradient_center_x = x_percent / 100.0
            layer.gradient_center_y = y_percent / 100.0

        return self._change_selected_text(
            "修改文字渐变中心",
            apply,
            f"文字渐变中心 · {x_percent}% / {y_percent}%",
        )

    @Slot(bool, result=bool)
    def setSelectedTextBackgroundEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字背景",
            lambda layer: setattr(layer, "background_enabled", enabled),
            "文字背景已开启" if enabled else "文字背景已关闭",
        )

    @Slot(str, result=bool)
    def setSelectedTextBackgroundColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字背景颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字背景颜色",
            lambda layer: setattr(layer, "background_color", color),
            f"文字背景颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, result=bool)
    def setSelectedTextBackgroundOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))

        def apply(layer) -> None:
            color = tuple(getattr(layer, "background_color", (255, 255, 255, 128)))
            rgb = color[:3] if len(color) >= 3 else (255, 255, 255)
            layer.background_color = rgb + (round(value / 100.0 * 255),)

        return self._change_selected_text(
            "修改文字背景透明度",
            apply,
            f"文字背景透明度 · {value}%",
        )

    @Slot(int, result=bool)
    def setSelectedTextBackgroundPadding(self, value: int) -> bool:
        value = max(-50, min(50, int(value)))
        return self._change_selected_text(
            "修改文字背景扩展",
            lambda layer: setattr(layer, "background_padding", value),
            f"文字背景扩展 · {value:+d} px",
        )

    @Slot(bool, result=bool)
    def setSelectedTextShadowEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字阴影",
            lambda layer: setattr(layer, "shadow_enabled", enabled),
            "文字阴影已开启" if enabled else "文字阴影已关闭",
        )

    @Slot(int, int, result=bool)
    def setSelectedTextShadowOffset(self, x: int, y: int) -> bool:
        x = max(-50, min(50, int(x)))
        y = max(-50, min(50, int(y)))

        def apply(layer) -> None:
            layer.shadow_offset_x = x
            layer.shadow_offset_y = y

        return self._change_selected_text(
            "修改文字阴影偏移",
            apply,
            f"文字阴影偏移 · {x:+d} / {y:+d} px",
        )

    @Slot(int, result=bool)
    def setSelectedTextShadowBlur(self, value: int) -> bool:
        value = max(0, min(20, int(value)))
        return self._change_selected_text(
            "修改文字阴影模糊",
            lambda layer: setattr(layer, "shadow_blur", value),
            f"文字阴影模糊 · {value} px",
        )

    @Slot(str, result=bool)
    def setSelectedTextShadowColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字阴影颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字阴影颜色",
            lambda layer: setattr(layer, "shadow_color", color),
            f"文字阴影颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, result=bool)
    def setSelectedTextShadowOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))

        def apply(layer) -> None:
            color = tuple(getattr(layer, "shadow_color", (0, 0, 0, 128)))
            rgb = color[:3] if len(color) >= 3 else (0, 0, 0)
            layer.shadow_color = rgb + (round(value / 100.0 * 255),)

        return self._change_selected_text(
            "修改文字阴影透明度",
            apply,
            f"文字阴影透明度 · {value}%",
        )

    @Slot(bool, result=bool)
    def setSelectedTextGlowEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字发光",
            lambda layer: setattr(layer, "glow_enabled", enabled),
            "文字发光已开启" if enabled else "文字发光已关闭",
        )

    @Slot(int, result=bool)
    def setSelectedTextGlowStrength(self, value: int) -> bool:
        value = max(0, min(20, int(value)))
        return self._change_selected_text(
            "修改文字发光强度",
            lambda layer: setattr(layer, "glow_strength", value),
            f"文字发光强度 · {value}",
        )

    @Slot(int, result=bool)
    def setSelectedTextGlowRadius(self, value: int) -> bool:
        value = max(1, min(50, int(value)))
        return self._change_selected_text(
            "修改文字发光半径",
            lambda layer: setattr(layer, "glow_radius", value),
            f"文字发光半径 · {value} px",
        )

    @Slot(str, result=bool)
    def setSelectedTextGlowColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字发光颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字发光颜色",
            lambda layer: setattr(layer, "glow_color", color),
            f"文字发光颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, result=bool)
    def setSelectedTextGlowOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))

        def apply(layer) -> None:
            color = tuple(getattr(layer, "glow_color", (255, 255, 255, 255)))
            rgb = color[:3] if len(color) >= 3 else (255, 255, 255)
            layer.glow_color = rgb + (round(value / 100.0 * 255),)

        return self._change_selected_text(
            "修改文字发光透明度",
            apply,
            f"文字发光透明度 · {value}%",
        )

    def _validated_selected_text_range(self, start: int, end: int, label: str = "局部颜色"):
        if not self.selectedIsTextLayer:
            self._set_status("当前图层不是文字图层", toast=True)
            return None
        if self.selectedTextBindingEnabled:
            self._set_status(f"{label}仅支持整段排版模式", toast=True)
            return None
        text = str(getattr(self._selected_layer(), "current_text", "") or "")
        start = max(0, min(len(text), int(start)))
        end = max(0, min(len(text), int(end)))
        if start > end:
            start, end = end, start
        if start >= end:
            self._set_status(f"请先选择需要设置的文字", toast=True)
            return None
        return start, end

    @Slot(int, int, str, result=bool)
    def setSelectedTextColorRange(self, start: int, end: int, value: str) -> bool:
        selected_range = self._validated_selected_text_range(start, end)
        if selected_range is None:
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("局部文字颜色格式无效", toast=True)
            return False
        start, end = selected_range
        return self._change_selected_text(
            "修改局部文字颜色",
            lambda layer: layer.set_text_color_range(start, end, color),
            f"已设置 {end - start} 个字符的局部颜色",
        )

    @Slot(int, int, result=bool)
    def clearSelectedTextColorRange(self, start: int, end: int) -> bool:
        selected_range = self._validated_selected_text_range(start, end)
        if selected_range is None:
            return False
        start, end = selected_range
        layer = self._selected_layer()
        ranges = layer.get_text_color_ranges()
        if not any(item["end"] > start and item["start"] < end for item in ranges):
            self._set_status("当前选区没有局部颜色", toast=True)
            return False
        return self._change_selected_text(
            "清除局部文字颜色",
            lambda selected: selected.clear_text_color_range(start, end),
            f"已清除 {end - start} 个字符的局部颜色",
        )

    @Slot(int, int, int, result=bool)
    def setSelectedTextFontSizeRange(self, start: int, end: int, value: int) -> bool:
        selected_range = self._validated_selected_text_range(start, end, label="局部字号")
        if selected_range is None:
            return False
        value = max(1, min(1000, int(value)))
        start, end = selected_range
        return self._change_selected_text(
            "修改局部文字字号",
            lambda layer: layer.set_font_size_range(start, end, value),
            f"已设置 {end - start} 个字符为 {value} px",
        )

    @Slot(int, int, result=bool)
    def clearSelectedTextFontSizeRange(self, start: int, end: int) -> bool:
        selected_range = self._validated_selected_text_range(start, end, label="局部字号")
        if selected_range is None:
            return False
        start, end = selected_range
        layer = self._selected_layer()
        ranges = layer.get_font_size_ranges() if hasattr(layer, "get_font_size_ranges") else []
        if not any(item["end"] > start and item["start"] < end for item in ranges):
            self._set_status("当前选区没有局部字号", toast=True)
            return False
        return self._change_selected_text(
            "清除局部文字字号",
            lambda selected: selected.clear_font_size_range(start, end),
            f"已清除 {end - start} 个字符的局部字号",
        )

    def _style_attributes_for_layer(self, layer) -> tuple:
        attrs = list(_COMMON_STYLE_ATTRIBUTES)
        if self._layer_model.layer_type_name(layer) == "文字":
            attrs.extend(_TEXT_STYLE_ATTRIBUTES)
        return tuple(attrs)

    @Slot(result=bool)
    def copySelectedLayerStyle(self) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if layer is None:
            self._set_status("请先选择要复制样式的图层", toast=True)
            return False
        layer_type = self._layer_model.layer_type_name(layer)
        values = {
            attr: copy.deepcopy(getattr(layer, attr))
            for attr in self._style_attributes_for_layer(layer)
            if hasattr(layer, attr)
        }
        if not values:
            self._set_status("当前图层没有可复制的样式", toast=True)
            return False
        self._layer_style_clipboard = {
            "layer_type": layer_type,
            "values": values,
            "summary": f"{getattr(layer, 'name', '图层')} · {layer_type}样式",
        }
        self.styleClipboardChanged.emit()
        self._set_status(f"已复制“{getattr(layer, 'name', '图层')}”的样式", toast=True)
        return True

    @Slot(result=bool)
    def pasteSelectedLayerStyle(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self._layer_style_clipboard:
            self._set_status("尚未复制图层样式", toast=True)
            return False
        layer = self._selected_layer()
        if layer is None:
            self._set_status("请先选择要粘贴样式的图层", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定，无法粘贴样式", toast=True)
            return False

        source_type = self._layer_style_clipboard.get("layer_type", "")
        target_type = self._layer_model.layer_type_name(layer)
        allowed = set(_COMMON_STYLE_ATTRIBUTES)
        if source_type == target_type == "文字":
            allowed.update(_TEXT_STYLE_ATTRIBUTES)
        values = self._layer_style_clipboard.get("values", {})
        changes = {
            attr: copy.deepcopy(value)
            for attr, value in values.items()
            if attr in allowed and hasattr(layer, attr)
        }
        if not changes:
            self._set_status("复制的样式与当前图层不兼容", toast=True)
            return False

        index = self.selectedLayerIndex
        with self._document_lock:
            self._ensure_history_baseline()
            for attr, value in changes.items():
                setattr(layer, attr, value)
            self._document.is_modified = True
            self._document.bump_hit_test_version()
            self._document._invalidate_render_cache()
            self._document.save_state("粘贴图层样式")
        self._publish_content_change(index, f"已粘贴 {len(changes)} 项图层样式")
        return True

    @Slot(result=bool)
    def deleteSelectedLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        index = self.selectedLayerIndex
        layer = self._layer_model.layer_at(index)
        if layer is None:
            self._set_status("没有可删除的图层", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定，无法删除", toast=True)
            return False

        try:
            with self._document_lock:
                before_count = len(self._document.layers)
                self._ensure_history_baseline()
                self._document.remove_layer(index)
                if len(self._document.layers) == before_count:
                    return False
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"删除图层失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已删除图层", toast=True)
        return True

    def _duplicate_layer_name(self, original_name: str) -> str:
        original_name = str(original_name or "未命名图层")
        match = re.match(r"^(.*?)(?: 副本(?: \d+)?)?$", original_name)
        base_name = (match.group(1) if match else original_name).strip() or "未命名图层"
        existing_names = {str(getattr(layer, "name", "")) for layer in self._document.layers}
        candidate = f"{base_name} 副本"
        if candidate not in existing_names:
            return candidate
        number = 2
        while f"{base_name} 副本 {number}" in existing_names:
            number += 1
        return f"{base_name} 副本 {number}"

    @Slot(result=bool)
    def duplicateSelectedLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self.canDuplicateLayer:
            self._set_status("当前图层无法复制", toast=True)
            return False
        index = self.selectedLayerIndex
        original = self._selected_layer()

        try:
            with self._document_lock:
                self._ensure_history_baseline()
                try:
                    duplicate = original.duplicate(parent=self._document)
                except TypeError:
                    duplicate = original.duplicate()
                if duplicate is None:
                    raise RuntimeError("图层复制失败")

                if hasattr(duplicate, "_layer_id"):
                    duplicate._layer_id = str(uuid.uuid4())
                duplicate.name = self._duplicate_layer_name(getattr(original, "name", ""))

                if hasattr(duplicate, "x") and hasattr(duplicate, "width"):
                    max_x = max(0, self.canvasWidth - int(getattr(duplicate, "width", 0) or 0))
                    duplicate.x = min(max_x, max(0, int(getattr(original, "x", 0) or 0) + 12))
                if hasattr(duplicate, "y") and hasattr(duplicate, "height"):
                    max_y = max(0, self.canvasHeight - int(getattr(duplicate, "height", 0) or 0))
                    duplicate.y = min(max_y, max(0, int(getattr(original, "y", 0) or 0) + 12))

                changed_signal = getattr(duplicate, "changed", None)
                if changed_signal is not None:
                    changed_signal.connect(self._document.document_changed.emit)

                insert_index = index + 1
                self._document.layers.insert(insert_index, duplicate)
                self._document.selected_layer_index = insert_index
                self._document.selected_layer_indices = [insert_index]
                self._document.is_modified = True
                self._document._invalidate_render_cache()
                self._document.bump_hit_test_version()
                self._document.layer_changed.emit()
                self._document.layer_selected.emit(insert_index)
                self._document.layers_selection_changed.emit([insert_index])
                self._document.document_changed.emit()
                self._document.save_state("复制图层")
        except Exception as error:
            self._set_status(f"复制图层失败：{error}", toast=True)
            return False

        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"已创建 {duplicate.name}", toast=True)
        return True

    @Slot(str, result=bool)
    def moveSelectedLayer(self, direction: str) -> bool:
        if not self._ensure_operations_available():
            return False
        direction = str(direction or "").lower()
        allowed = self.canMoveLayerForward if direction == "forward" else self.canMoveLayerBackward
        if direction not in {"forward", "backward"} or not allowed:
            self._set_status("图层已在边界或相邻图层已锁定", toast=True)
            return False
        index = self.selectedLayerIndex
        selected_layer = self._selected_layer()

        with self._document_lock:
            self._ensure_history_baseline()
            if direction == "forward":
                self._document.move_layer_down(index)
                action_text = "前移一层"
            else:
                self._document.move_layer_up(index)
                action_text = "后移一层"
            try:
                new_index = self._document.layers.index(selected_layer)
            except ValueError:
                return False
            if new_index == index:
                return False
            self._document.is_modified = True
            self._document._invalidate_render_cache()
            self._document.document_changed.emit()

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"图层已{action_text}", toast=True)
        return True

    def _finish_arrangement(self, action: str, status: str, *, render: bool = True) -> None:
        self._document.is_modified = True
        self._document._invalidate_render_cache()
        self._document.bump_hit_test_version()
        self._document.save_state(action)
        self._document.layer_changed.emit()
        self._document.document_changed.emit()
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.viewSettingsChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        if render:
            self.requestPreview(force=True)
        self._set_status(status, toast=True)

    @Slot(int, bool, bool, result=bool)
    def selectLayerWithModifiers(self, index: int, ctrl: bool, shift: bool) -> bool:
        if self._layer_model.layer_at(index) is None:
            return False
        current = self.selectedLayerIndices
        if shift and self._selection_anchor_index >= 0:
            start = min(self._selection_anchor_index, index)
            end = max(self._selection_anchor_index, index)
            selection = list(range(start, end + 1))
            primary = index
        elif ctrl:
            selection = list(current)
            if index in selection:
                selection.remove(index)
                primary = selection[-1] if selection else -1
            else:
                selection.append(index)
                primary = index
            self._selection_anchor_index = index if primary >= 0 else -1
        else:
            selection = [index]
            primary = index
            self._selection_anchor_index = index
        self._dismiss_text_edit_overlay(primary)
        self._document.select_layers(selection, primary_index=primary)
        self._selected_vector_node_index = -1
        self.vectorEditChanged.emit()
        return True

    @Slot(float, float, float, float, bool, result=bool)
    def selectLayersInRect(self, left: float, top: float, right: float, bottom: float, additive: bool) -> bool:
        x1, x2 = sorted((float(left), float(right)))
        y1, y2 = sorted((float(top), float(bottom)))
        hits = []
        for index, layer in enumerate(self._document.layers):
            if is_layer_group(layer) or not bool(getattr(layer, "visible", True)):
                continue
            if not all(hasattr(layer, attr) for attr in ("x", "y", "width", "height")):
                continue
            layer_left = float(layer.x)
            layer_top = float(layer.y)
            layer_right = layer_left + float(layer.width)
            layer_bottom = layer_top + float(layer.height)
            if layer_right >= x1 and layer_left <= x2 and layer_bottom >= y1 and layer_top <= y2:
                hits.append(index)
        selection = list(self.selectedLayerIndices) if additive else []
        for index in hits:
            if index not in selection:
                selection.append(index)
        primary = hits[-1] if hits else (selection[-1] if selection else -1)
        self._dismiss_text_edit_overlay(primary)
        self._document.select_layers(selection, primary_index=primary)
        self._selection_anchor_index = primary
        return bool(hits)

    @Slot(float, float, result=int)
    def hitTestLayerAt(self, x: float, y: float) -> int:
        hits = []
        for index in range(len(self._document.layers) - 1, -1, -1):
            layer = self._document.layers[index]
            if is_layer_group(layer):
                continue
            if not is_effectively_visible(layer, self._document.layers):
                continue
            for position in self._layer_hit_positions(layer):
                if self._layer_contains_point(layer, x, y, position):
                    hits.append(index)
                    break
        if hits:
            return hits[0]

        selected = self._selected_layer()
        if is_layer_group(selected):
            bounds = group_bounds(self._document.layers, selected, include_hidden=False)
            if bounds and bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]:
                return self.selectedLayerIndex
        for index in range(len(self._document.layers) - 1, -1, -1):
            layer = self._document.layers[index]
            if not is_layer_group(layer) or not is_effectively_visible(layer, self._document.layers):
                continue
            bounds = group_bounds(self._document.layers, layer, include_hidden=False)
            if bounds and bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]:
                return index
        return -1

    @Slot(float, float, result="QVariantList")
    def hitTestLayersAt(self, x: float, y: float):
        hits = []
        for index in range(len(self._document.layers) - 1, -1, -1):
            layer = self._document.layers[index]
            if is_layer_group(layer) or not is_effectively_visible(layer, self._document.layers):
                continue
            if any(
                self._layer_contains_point(layer, x, y, position)
                for position in self._layer_hit_positions(layer)
            ):
                hits.append(index)
        return hits

    def _layer_hit_positions(self, layer):
        positions = [(float(getattr(layer, "x", 0)), float(getattr(layer, "y", 0)))]
        if bool(getattr(layer, "clone_enabled", False)):
            getter = getattr(layer, "get_effective_clone_positions", None)
            if not callable(getter):
                getter = getattr(layer, "get_clone_positions", None)
            if callable(getter):
                try:
                    clone_positions = list(getter() or [])
                    if clone_positions:
                        positions = [(float(px), float(py)) for px, py in clone_positions]
                except Exception:
                    pass
        mirror_mode = str(getattr(layer, "clone_mirror_mode", "none") or "none")
        if mirror_mode not in ("horizontal", "vertical") or not positions:
            return positions
        min_x = min(px for px, _py in positions)
        max_x = max(px + float(layer.width) for px, _py in positions)
        min_y = min(py for _px, py in positions)
        max_y = max(py + float(layer.height) for _px, py in positions)
        mirrored = []
        if mirror_mode == "horizontal":
            mirrored_left = self.canvasWidth - (min_x + max_x - min_x)
            mirrored = [(mirrored_left + px - min_x, py) for px, py in positions]
        else:
            mirrored_top = self.canvasHeight - (min_y + max_y - min_y)
            mirrored = [(px, mirrored_top + py - min_y) for px, py in positions]
        return positions + mirrored

    @Slot(float, float, bool, bool, result=int)
    def selectLayerAtWithModifiers(self, x: float, y: float, ctrl: bool, shift: bool) -> int:
        hits = self.hitTestLayersAt(x, y)
        index = hits[0] if hits else self.hitTestLayerAt(x, y)
        if ctrl and hits:
            current = self.selectedLayerIndex
            index = hits[(hits.index(current) + 1) % len(hits)] if current in hits else hits[0]
            self.selectLayer(index)
        elif index >= 0:
            self.selectLayerWithModifiers(index, False, shift)
        elif not ctrl and not shift:
            self.clearSelection()
        return index

    @Slot(int, int, result=bool)
    def moveSelectedLayersBy(self, delta_x: int, delta_y: int) -> bool:
        indices = self._selected_content_indices()
        movable = [
            index for index in indices
            if not is_effectively_locked(self._document.layers[index], self._document.layers)
            and all(hasattr(self._document.layers[index], attr) for attr in ("x", "y", "width", "height"))
        ]
        if not movable:
            return False
        dx = int(delta_x)
        dy = int(delta_y)
        if dx == 0 and dy == 0:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            for index in movable:
                layer = self._document.layers[index]
                layer.x = int(layer.x) + dx
                layer.y = int(layer.y) + dy
            self._finish_arrangement("移动多个图层", f"已移动 {len(movable)} 个图层")
        return True

    @Slot(result=bool)
    def groupSelectedLayers(self) -> bool:
        if not self.canGroupSelectedLayers:
            self._set_status("请选择至少两个未分组且未锁定的图层", toast=True)
            return False
        movable = sorted(
            index for index in self.selectedLayerIndices
            if not is_layer_group(self._document.layers[index])
            and not get_parent_group_id(self._document.layers[index])
            and not is_effectively_locked(self._document.layers[index], self._document.layers)
        )
        with self._document_lock:
            self._ensure_history_baseline()
            group_count = sum(is_layer_group(layer) for layer in self._document.layers)
            group = LayerGroup(name=f"图层组 {group_count + 1}", parent=self._document)
            selected_layers = [self._document.layers[index] for index in movable]
            selected_set = set(movable)
            insert_at = min(movable)
            remaining = [
                layer for index, layer in enumerate(self._document.layers)
                if index not in selected_set
            ]
            for layer in selected_layers:
                set_parent_group_id(layer, group.group_id)
            self._document.layers = remaining[:insert_at] + [group] + selected_layers + remaining[insert_at:]
            group_index = self._document.layers.index(group)
            self._document.select_layers([group_index], primary_index=group_index)
            self._selection_anchor_index = group_index
            self._finish_arrangement("建立图层组", f"已建立包含 {len(selected_layers)} 个图层的组")
        return True

    @Slot(result=bool)
    def ungroupSelectedGroups(self) -> bool:
        group_indices = [
            index for index in self.selectedLayerIndices
            if isinstance(self._document.layers[index], LayerGroup)
        ]
        if not group_indices:
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            group_ids = {
                str(self._document.layers[index].group_id)
                for index in group_indices
            }
            self._document.layers = [
                layer for index, layer in enumerate(self._document.layers)
                if index not in set(group_indices)
            ]
            child_indices = []
            for index, layer in enumerate(self._document.layers):
                if get_parent_group_id(layer) in group_ids:
                    set_parent_group_id(layer, None)
                    child_indices.append(index)
            primary = child_indices[0] if child_indices else -1
            self._document.select_layers(child_indices, primary_index=primary)
            self._selection_anchor_index = primary
            self._finish_arrangement("解散图层组", f"已解散 {len(group_indices)} 个图层组")
        return True

    @Slot(int, result=bool)
    def toggleLayerGroupExpanded(self, index: int) -> bool:
        group = self._layer_model.layer_at(index)
        if not isinstance(group, LayerGroup):
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            group.expanded = not group.expanded
            self._document.is_modified = True
            self._document.save_state("切换图层组展开")
        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        return True

    @Slot(bool, result=bool)
    def setSelectedLayersVisible(self, visible: bool) -> bool:
        indices = self.selectedLayerIndices
        changes = {
            index: self._document.layers[index]
            for index in indices
            if bool(getattr(self._document.layers[index], "visible", True)) != bool(visible)
        }
        if not changes:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            for layer in changes.values():
                layer.visible = bool(visible)
            action = "批量显示图层" if visible else "批量隐藏图层"
            self._finish_arrangement(action, f"已{action[2:4]} {len(changes)} 个图层")
        return True

    @Slot(bool, result=bool)
    def setSelectedLayersLocked(self, locked: bool) -> bool:
        indices = self.selectedLayerIndices
        changes = [
            self._document.layers[index]
            for index in indices
            if bool(getattr(self._document.layers[index], "locked", False)) != bool(locked)
        ]
        if not changes:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            for layer in changes:
                layer.locked = bool(locked)
            action = "批量锁定图层" if locked else "批量解锁图层"
            self._finish_arrangement(action, f"已{action[2:4]} {len(changes)} 个图层", render=False)
        return True

    @Slot(result=bool)
    def duplicateSelectedLayers(self) -> bool:
        indices = self._selected_content_indices()
        originals = [
            self._document.layers[index]
            for index in indices
            if callable(getattr(self._document.layers[index], "duplicate", None))
            and not is_effectively_locked(self._document.layers[index], self._document.layers)
        ]
        if not originals:
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            insert_at = max(indices) + 1
            duplicates = []
            for original in originals:
                try:
                    duplicate = original.duplicate(parent=self._document)
                except TypeError:
                    duplicate = original.duplicate()
                if hasattr(duplicate, "_layer_id"):
                    duplicate._layer_id = str(uuid.uuid4())
                duplicate.name = self._duplicate_layer_name(getattr(original, "name", ""))
                if hasattr(duplicate, "x"):
                    duplicate.x = min(max(0, self.canvasWidth - int(duplicate.width)), int(original.x) + 12)
                    duplicate.y = min(max(0, self.canvasHeight - int(duplicate.height)), int(original.y) + 12)
                set_parent_group_id(duplicate, get_parent_group_id(original))
                duplicates.append(duplicate)
            self._document.layers[insert_at:insert_at] = duplicates
            duplicate_indices = list(range(insert_at, insert_at + len(duplicates)))
            self._document.select_layers(duplicate_indices, primary_index=duplicate_indices[0])
            self._selection_anchor_index = duplicate_indices[0]
            self._finish_arrangement("复制多个图层", f"已复制 {len(duplicates)} 个图层")
        return True

    @Slot(result=bool)
    def deleteSelectedLayers(self) -> bool:
        indices = expand_group_indices(
            self._document.layers,
            self.selectedLayerIndices,
            include_groups=True,
        )
        deletable = sorted({
            index for index in indices
            if not is_effectively_locked(self._document.layers[index], self._document.layers)
        })
        if not deletable:
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            for index in reversed(deletable):
                layer = self._document.layers[index]
                if hasattr(self._document, "binding_manager") and self._document.binding_manager:
                    self._document.binding_manager.remove_layer_from_group(layer)
                del self._document.layers[index]
            fallback = min(deletable[0], len(self._document.layers) - 1) if self._document.layers else -1
            self._document.select_layers([fallback] if fallback >= 0 else [], primary_index=fallback)
            self._selection_anchor_index = fallback
            self._finish_arrangement("删除多个图层", f"已删除 {len(deletable)} 个图层")
        return True

    @Slot(int, result=bool)
    def moveSelectedLayersTo(self, target_index: int) -> bool:
        indices = sorted(expand_group_indices(
            self._document.layers,
            self.selectedLayerIndices,
            include_groups=True,
        ))
        if not indices:
            return False
        target_index = max(0, min(int(target_index), len(self._document.layers) - 1))
        if target_index in indices:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            selected_objects = [self._document.layers[index] for index in indices]
            remaining = [
                layer for index, layer in enumerate(self._document.layers)
                if index not in set(indices)
            ]
            insert_at = target_index - sum(index < target_index for index in indices)
            if min(indices) < target_index:
                insert_at += 1
            insert_at = max(0, min(insert_at, len(remaining)))
            self._document.layers = remaining[:insert_at] + selected_objects + remaining[insert_at:]
            new_indices = [self._document.layers.index(layer) for layer in selected_objects]
            self._document.select_layers(new_indices, primary_index=new_indices[0])
            self._selection_anchor_index = new_indices[0]
            self._finish_arrangement("重新排序图层", f"已移动 {len(selected_objects)} 个图层", render=False)
        return True

    @Slot(str, result=bool)
    def alignSelectedLayers(self, mode: str) -> bool:
        indices = self._selected_content_indices()
        if len(indices) < 2:
            return False
        primary = self.selectedLayerIndex if self.selectedLayerIndex in indices else indices[0]
        reference = self._document.layers[primary]
        mode = str(mode or "").lower()
        changed = []
        with self._document_lock:
            self._ensure_history_baseline()
            for index in indices:
                if index == primary:
                    continue
                layer = self._document.layers[index]
                if is_effectively_locked(layer, self._document.layers):
                    continue
                before = (layer.x, layer.y, layer.width, layer.height)
                if mode == "left":
                    layer.x = reference.x
                elif mode == "hcenter":
                    layer.x = round(reference.x + reference.width / 2 - layer.width / 2)
                elif mode == "right":
                    layer.x = reference.x + reference.width - layer.width
                elif mode == "top":
                    layer.y = reference.y
                elif mode == "vcenter":
                    layer.y = round(reference.y + reference.height / 2 - layer.height / 2)
                elif mode == "bottom":
                    layer.y = reference.y + reference.height - layer.height
                elif mode == "center":
                    layer.x = round(reference.x + reference.width / 2 - layer.width / 2)
                    layer.y = round(reference.y + reference.height / 2 - layer.height / 2)
                elif mode == "same_size":
                    layer.width = reference.width
                    layer.height = reference.height
                else:
                    return False
                if before != (layer.x, layer.y, layer.width, layer.height):
                    changed.append(layer)
            if not changed:
                return True
            self._finish_arrangement("对齐多个图层", f"已对齐 {len(changed)} 个图层")
        return True

    @Slot(str, result=bool)
    def distributeSelectedLayers(self, axis: str) -> bool:
        indices = self._selected_content_indices()
        if len(indices) < 3:
            self._set_status("等距分布至少需要三个图层", toast=True)
            return False
        horizontal = str(axis or "").lower() == "horizontal"
        if not horizontal and str(axis or "").lower() != "vertical":
            return False
        position_attr = "x" if horizontal else "y"
        size_attr = "width" if horizontal else "height"
        indices = sorted(indices, key=lambda index: getattr(self._document.layers[index], position_attr))
        layers = [self._document.layers[index] for index in indices]
        start = float(getattr(layers[0], position_attr))
        end = float(getattr(layers[-1], position_attr) + getattr(layers[-1], size_attr))
        total_size = sum(float(getattr(layer, size_attr)) for layer in layers)
        gap = (end - start - total_size) / (len(layers) - 1)
        cursor = start
        changed = []
        with self._document_lock:
            self._ensure_history_baseline()
            for offset, layer in enumerate(layers):
                target = round(cursor)
                if offset not in (0, len(layers) - 1) and not is_effectively_locked(layer, self._document.layers):
                    if int(getattr(layer, position_attr)) != target:
                        setattr(layer, position_attr, target)
                        changed.append(layer)
                cursor += float(getattr(layer, size_attr)) + gap
            if not changed:
                return True
            direction = "水平" if horizontal else "垂直"
            self._finish_arrangement(f"{direction}等距分布图层", f"已{direction}等距分布")
        return True

    @Slot(int, result=bool)
    def selectLayer(self, index: int) -> bool:
        if self._layer_model.layer_at(index) is None:
            return False
        if self._crop_edit_original is not None and index != self._crop_edit_index:
            self.cancelCropEdit()
        self._dismiss_text_edit_overlay(index)
        self._document.select_layers([int(index)], primary_index=int(index))
        self._selection_anchor_index = int(index)
        self._selected_vector_node_index = -1
        self.selectionChanged.emit()
        self.vectorEditChanged.emit()
        return True

    @Slot(result=bool)
    def clearSelection(self) -> bool:
        if self.selectedLayerIndex < 0:
            return True
        if self._crop_edit_original is not None:
            self.cancelCropEdit()
        self._dismiss_text_edit_overlay(-1)
        self._document.select_layers([], primary_index=-1)
        self._selection_anchor_index = -1
        self._selected_vector_node_index = -1
        self.selectionChanged.emit()
        self.vectorEditChanged.emit()
        return True

    @staticmethod
    def _layer_local_point(layer, x: float, y: float, position=None):
        width = float(getattr(layer, "width", 0) or 0)
        height = float(getattr(layer, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return None
        left, top = position or (
            float(getattr(layer, "x", 0) or 0),
            float(getattr(layer, "y", 0) or 0),
        )
        center_x = left + width / 2.0
        center_y = top + height / 2.0
        offset_x = float(x) - center_x
        offset_y = float(y) - center_y
        angle = math.radians(float(getattr(layer, "rotation", 0.0) or 0.0))
        cosine = math.cos(angle)
        sine = math.sin(angle)
        local_x = cosine * offset_x + sine * offset_y + width / 2.0
        local_y = -sine * offset_x + cosine * offset_y + height / 2.0
        return local_x, local_y

    @staticmethod
    def _layer_alpha_image(layer):
        image = getattr(layer, "cached_image", None)
        if image is None or not hasattr(image, "getpixel"):
            getter = getattr(layer, "get_image", None)
            if callable(getter):
                try:
                    image = getter()
                except Exception:
                    image = None
        if image is None or not hasattr(image, "getpixel"):
            return None
        try:
            return image if image.mode == "RGBA" else image.convert("RGBA")
        except Exception:
            return None

    @classmethod
    def _layer_contains_point(cls, layer, x: float, y: float, position=None) -> bool:
        local = cls._layer_local_point(layer, x, y, position)
        if local is None:
            return False
        local_x, local_y = local
        width = float(getattr(layer, "width", 0) or 0)
        height = float(getattr(layer, "height", 0) or 0)
        if not (0.0 <= local_x <= width and 0.0 <= local_y <= height):
            return False

        shape = getattr(layer, "shape_type", ShapeType.RECTANGLE)
        shape_value = str(getattr(shape, "value", shape or "rectangle"))
        if shape_value != "rectangle" or bool(getattr(layer, "vector_path_enabled", False)):
            try:
                from app.utils.vector_layer_geometry import build_vector_outline_points_px

                points, _ = build_vector_outline_points_px(
                    max(1, int(width)),
                    max(1, int(height)),
                    int(getattr(layer, "corner_radius", 0)),
                    int(getattr(layer, "vector_corner_radius_tl", 0)),
                    int(getattr(layer, "vector_corner_radius_tr", 0)),
                    int(getattr(layer, "vector_corner_radius_br", 0)),
                    int(getattr(layer, "vector_corner_radius_bl", 0)),
                    bool(getattr(layer, "vector_path_enabled", False)),
                    str(getattr(layer, "vector_path_mode", "polygon")),
                    getattr(layer, "vector_path_points", []),
                    getattr(layer, "vector_bezier_nodes", []),
                    bool(getattr(layer, "vector_path_closed", True)),
                    shape_value,
                    int(getattr(layer, "trapezoid_top_width", 100)),
                    int(getattr(layer, "trapezoid_bottom_width", 80)),
                    str(getattr(layer, "trapezoid_slope_side", "right")),
                    float(getattr(layer, "polygon_rotation", 0.0)),
                    int(getattr(layer, "polygon_corner_radius", 0)),
                )
                if len(points) >= 3:
                    path = QPainterPath(QPointF(*points[0]))
                    for point in points[1:]:
                        path.lineTo(QPointF(*point))
                    path.closeSubpath()
                    if not path.contains(QPointF(local_x, local_y)):
                        return False
            except Exception:
                pass

        from app.models.text_layer import TextLayer

        if isinstance(layer, TextLayer):
            return True
        image = cls._layer_alpha_image(layer)
        if image is None or image.mode != "RGBA":
            return True
        pixel_x = min(image.width - 1, max(0, round(local_x / max(1.0, width) * (image.width - 1))))
        pixel_y = min(image.height - 1, max(0, round(local_y / max(1.0, height) * (image.height - 1))))
        try:
            return int(image.getpixel((pixel_x, pixel_y))[-1]) >= 8
        except Exception:
            return True

    @Slot(float, float, result=int)
    def selectLayerAt(self, x: float, y: float) -> int:
        for index in range(self._layer_model.rowCount() - 1, -1, -1):
            layer = self._layer_model.layer_at(index)
            if layer is None:
                continue
            if not bool(getattr(layer, "visible", True)) or bool(getattr(layer, "locked", False)):
                continue
            if self._layer_contains_point(layer, x, y):
                self.selectLayer(index)
                return index
        self.clearSelection()
        return -1

    @Slot(float, float, result=bool)
    def beginTextEditAt(self, x: float, y: float) -> bool:
        if self.cropEditing or self._export_running:
            return False
        hits = self.hitTestLayersAt(x, y)
        if not hits:
            return False
        index = int(hits[0])
        layer = self._document.layers[index]
        if self._layer_model.layer_type_name(layer) != "文字":
            return False
        if is_effectively_locked(layer, self._document.layers):
            self._set_status("图层已锁定，无法编辑文字", toast=True)
            return False
        self.selectLayer(index)
        return True

    @Property(bool, notify=textEditingChanged)
    def textEditOverlayVisible(self) -> bool:
        return self._text_edit_overlay_visible

    @Slot(result=bool)
    def startTextEditOverlay(self) -> bool:
        """在画布上进入文字直接编辑状态（供 QML 双击文字图层后调用）。"""
        if self.cropEditing or self._export_running:
            return False
        if not self.selectedIsTextLayer:
            return False
        layer = self._selected_layer()
        if is_effectively_locked(layer, self._document.layers):
            self._set_status("图层已锁定，无法编辑文字", toast=True)
            return False
        self._text_edit_layer_index = self.selectedLayerIndex
        self._text_edit_overlay_visible = True
        self.textEditingChanged.emit()
        return True

    def _dismiss_text_edit_overlay(self, primary_index: int = -1):
        """选中图层发生变化时关闭画布文字编辑覆盖层（保留已编辑内容不保存）。"""
        if not self._text_edit_overlay_visible:
            return
        if primary_index >= 0 and primary_index == self._text_edit_layer_index:
            return
        self._text_edit_overlay_visible = False
        self._text_edit_layer_index = -1
        self.textEditingChanged.emit()

    @Slot(str, result=bool)
    def commitTextEditOverlay(self, value: str) -> bool:
        """提交画布文字编辑内容并退出编辑状态。"""
        index = self.selectedLayerIndex
        was_visible = self._text_edit_overlay_visible
        self._text_edit_overlay_visible = False
        if was_visible:
            self.textEditingChanged.emit()
        if index < 0:
            return False
        return self.setTextContentForLayer(index, value)

    @Slot(result=bool)
    def cancelTextEditOverlay(self) -> bool:
        """取消画布文字编辑，不保存内容。"""
        if not self._text_edit_overlay_visible:
            return False
        self._text_edit_overlay_visible = False
        self.textEditingChanged.emit()
        return True

    def _ensure_history_baseline(self) -> None:
        manager = self._document._history_manager
        if manager.get_history_count() == 0:
            self._document.save_state("初始状态")

    def _set_layer_attrs(self, index: int, changes: dict, action: str, *, render: bool = True) -> bool:
        if not self._ensure_operations_available():
            return False
        self._suppress_document_selection_notify += 1
        try:
            with self._document_lock:
                layer = self._layer_model.layer_at(index)
                if layer is None:
                    return False
                if any(attr not in ("visible", "locked") for attr in changes) and bool(
                    getattr(layer, "locked", False)
                ):
                    self._set_status("图层已锁定", toast=True)
                    return False
                effective_changes = {
                    attr: value
                    for attr, value in changes.items()
                    if getattr(layer, attr, None) != value
                }
                if not effective_changes:
                    return True
                self._ensure_history_baseline()
                for attr, value in effective_changes.items():
                    setattr(layer, attr, value)
                if any(
                    attr in ("fit_mode", "crop_direction", "use_original_size")
                    for attr in effective_changes
                ):
                    self._clear_image_layer_cache(layer)
                    if hasattr(layer, "_cache_valid"):
                        layer._cache_valid = False
                self._document.is_modified = True
                if any(
                    attr in ("x", "y", "width", "height", "rotation", "visible", "locked", "shape_type")
                    or attr.startswith("clone_")
                    or attr.startswith("vector_")
                    for attr in effective_changes
                ):
                    self._document.bump_hit_test_version()
                if any(attr not in ("name", "locked") for attr in effective_changes):
                    invalidate = getattr(self._document, "_invalidate_render_cache", None)
                    if callable(invalidate):
                        invalidate()
                self._document.save_state(action)
        finally:
            self._suppress_document_selection_notify -= 1
        self._layer_model.notify_row(index)
        if set(effective_changes) == {"opacity"}:
            self.layerAppearanceChanged.emit()
        else:
            self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        if render:
            self.requestPreview(force=True)
        return True

    def _set_layer_attr(self, index: int, attr: str, value, action: str, *, render: bool = True) -> bool:
        return self._set_layer_attrs(index, {attr: value}, action, render=render)

    def _invalidate_direct_layer_edit(self, index: int, *, save_action: str = "") -> None:
        layer = self._layer_model.layer_at(index)
        if layer is not None:
            layer.cached_image = None
            layer._cache_valid = False
        self._document.is_modified = True
        self._document.bump_hit_test_version()
        invalidate = getattr(self._document, "_invalidate_render_cache", None)
        if callable(invalidate):
            invalidate()
        if save_action:
            self._document.save_state(save_action)
        self._layer_model.notify_row(index)
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)

    def _run_vector_command(self, action: str, command) -> bool:
        if not self._ensure_operations_available() or not self.selectedSupportsVectorPath:
            self._set_status("当前图层不支持路径编辑", toast=True)
            return False
        layer = self._selected_layer()
        if layer is None or bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        index = self.selectedLayerIndex
        with self._document_lock:
            before = layer.serialize()
            self._ensure_history_baseline()
            command(layer)
            if layer.serialize() == before:
                return False
            self._invalidate_direct_layer_edit(index, save_action=action)
        self.vectorEditChanged.emit()
        return True

    def _refresh_random_transform_preview(self) -> bool:
        layer = self._selected_layer()
        if not self.selectedSupportsRandomTransform or layer is None:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        with self._document_lock:
            layer.generate_random_transform_params()
            layer.cached_image = None
            layer._cache_valid = False
            invalidate = getattr(self._document, "_invalidate_render_cache", None)
            if callable(invalidate):
                invalidate()
        self._layer_model.notify_row(self.selectedLayerIndex)
        self.selectionChanged.emit()
        self.requestPreview(force=True)
        return True

    @Slot(str, result=bool)
    def setSelectedFitMode(self, mode_id: str) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持图片适配", toast=True)
            return False
        mode_id = str(mode_id or "").strip().lower()
        mode = _FIT_MODES.get(mode_id)
        if mode is None:
            self._set_status("未知的图片适配模式", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "fit_mode",
            mode[0],
            "修改图片适配模式",
        )

    @Slot(bool, result=bool)
    def setSelectedUseOriginalSize(self, enabled: bool) -> bool:
        return self.setSelectedTrimTransparentBoundsEnabled(enabled)

    @Slot(bool, result=bool)
    def setSelectedTrimTransparentBoundsEnabled(self, enabled: bool) -> bool:
        layer = self._selected_layer()
        if not self.selectedHasImageSource or layer is None or not hasattr(layer, "use_original_size"):
            self._set_status("当前图层不支持去透明留白", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "use_original_size",
            bool(enabled),
            "切换去透明留白",
        )

    @Slot(str, result=bool)
    def setSelectedCropDirection(self, direction_id: str) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持裁剪方向", toast=True)
            return False
        direction_id = str(direction_id or "").strip().lower()
        direction = _CROP_DIRECTIONS.get(direction_id)
        if direction is None:
            self._set_status("未知的裁剪方向", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "crop_direction",
            direction[0],
            "修改裁剪方向",
        )

    @Slot(result=bool)
    def startCropEdit(self) -> bool:
        if not self._ensure_operations_available() or not self.selectedSupportsFreeCrop:
            self._set_status("当前图层不支持自由裁剪", toast=True)
            return False
        layer = self._selected_layer()
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        if self.cropEditing:
            return True
        if self._crop_edit_original is not None:
            self.cancelCropEdit()
        with self._document_lock:
            self._ensure_history_baseline()
            self._crop_edit_index = self.selectedLayerIndex
            self._crop_edit_original = list(layer.crop_rect)
            self._crop_edit_was_modified = bool(self._document.is_modified)
        self.cropEditChanged.emit()
        self._set_status("拖动裁剪框后确认应用", toast=True)
        return True

    @Slot(float, float, float, float, result=bool)
    def updateCropRect(self, left: float, top: float, right: float, bottom: float) -> bool:
        if not self.cropEditing:
            return False
        layer = self._layer_model.layer_at(self._crop_edit_index)
        if layer is None:
            return False
        with self._document_lock:
            layer.crop_rect = [left, top, right, bottom]
            self._invalidate_direct_layer_edit(self._crop_edit_index)
        self.cropEditChanged.emit()
        return True

    @Slot(result=bool)
    def confirmCropEdit(self) -> bool:
        if not self.cropEditing:
            return False
        index = self._crop_edit_index
        layer = self._layer_model.layer_at(index)
        original = list(self._crop_edit_original)
        changed = layer is not None and list(layer.crop_rect) != original
        with self._document_lock:
            if changed:
                self._invalidate_direct_layer_edit(index, save_action="自由裁剪图片")
            else:
                self._document.is_modified = self._crop_edit_was_modified
        self._crop_edit_index = -1
        self._crop_edit_original = None
        self.cropEditChanged.emit()
        if changed:
            self._set_status("已应用自由裁剪", toast=True)
        return True

    @Slot(result=bool)
    def cancelCropEdit(self) -> bool:
        if self._crop_edit_original is None:
            return False
        index = self._crop_edit_index
        layer = self._layer_model.layer_at(index)
        with self._document_lock:
            if layer is not None:
                layer.crop_rect = list(self._crop_edit_original)
                self._invalidate_direct_layer_edit(index)
            self._document.is_modified = self._crop_edit_was_modified
        self._crop_edit_index = -1
        self._crop_edit_original = None
        self.cropEditChanged.emit()
        self.documentInfoChanged.emit()
        self._set_status("已取消自由裁剪", toast=True)
        return True

    @Slot(result=bool)
    def resetSelectedCrop(self) -> bool:
        if self.cropEditing:
            self.cancelCropEdit()
        if not self.selectedSupportsFreeCrop:
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "crop_rect",
            [0.0, 0.0, 1.0, 1.0],
            "重置自由裁剪",
        )

    @Slot(result=bool)
    def convertSelectedToVectorPath(self) -> bool:
        changed = self._run_vector_command(
            "转换为矢量路径",
            lambda layer: layer.convert_rect_to_vector_path(),
        )
        if changed:
            self._selected_vector_node_index = 0
            self.vectorEditChanged.emit()
        return changed

    @Slot(int, result=bool)
    def selectVectorNode(self, node_index: int) -> bool:
        if node_index < 0 or node_index >= len(self.selectedVectorNodes):
            return False
        self._selected_vector_node_index = int(node_index)
        self.vectorEditChanged.emit()
        return True

    @Slot(int, float, float, result=bool)
    def moveSelectedVectorNode(self, node_index: int, x: float, y: float) -> bool:
        if node_index < 0 or node_index >= len(self.selectedVectorNodes):
            return False
        self._selected_vector_node_index = int(node_index)
        return self._run_vector_command(
            "移动路径节点",
            lambda layer: layer.update_vector_bezier_anchor(node_index, float(x), float(y)),
        )

    @Slot(int, str, float, float, result=bool)
    def moveSelectedVectorHandle(self, node_index: int, handle_type: str, x: float, y: float) -> bool:
        handle_type = str(handle_type or "").lower()
        if handle_type not in {"in", "out"}:
            return False
        return self._run_vector_command(
            "移动路径控制柄",
            lambda layer: layer.update_vector_bezier_handle(
                node_index, handle_type, float(x), float(y)
            ),
        )

    @Slot(str, result=bool)
    def setSelectedVectorNodeType(self, node_type: str) -> bool:
        if self._selected_vector_node_index < 0:
            return False
        node_type = str(node_type or "").lower()
        if node_type not in {"corner", "smooth", "symmetric"}:
            return False
        return self._run_vector_command(
            "修改路径节点类型",
            lambda layer: layer.set_vector_node_type(self._selected_vector_node_index, node_type),
        )

    @Slot(result=bool)
    def cycleSelectedVectorNodeType(self) -> bool:
        if self._selected_vector_node_index < 0:
            return False
        return self._run_vector_command(
            "切换路径节点类型",
            lambda layer: layer.cycle_vector_node_type(self._selected_vector_node_index),
        )

    @Slot(int, result=bool)
    def insertVectorNodeAfter(self, segment_index: int) -> bool:
        changed = self._run_vector_command(
            "插入路径节点",
            lambda layer: layer.insert_vector_node_after(int(segment_index)),
        )
        if changed:
            self._selected_vector_node_index = int(segment_index) + 1
            self.vectorEditChanged.emit()
        return changed

    @Slot(result=bool)
    def deleteSelectedVectorNode(self) -> bool:
        index = self._selected_vector_node_index
        if index < 0:
            return False
        changed = self._run_vector_command(
            "删除路径节点",
            lambda layer: layer.delete_vector_node(index),
        )
        if changed:
            self._selected_vector_node_index = min(index, len(self.selectedVectorNodes) - 1)
            self.vectorEditChanged.emit()
        return changed

    @Slot(bool, result=bool)
    def setSelectedVectorPathClosed(self, closed: bool) -> bool:
        return self._run_vector_command(
            "切换路径闭合",
            lambda layer: setattr(layer, "vector_path_closed", bool(closed)),
        )

    @Slot(str, result=bool)
    def setSelectedVectorHandleLinkMode(self, mode: str) -> bool:
        mode = str(mode or "").lower()
        if mode not in {"mirror", "collinear", "free"}:
            return False
        return self._run_vector_command(
            "修改控制柄联动",
            lambda layer: setattr(layer, "vector_handle_link_mode", mode),
        )

    @Slot(int, result=bool)
    def setSelectedVectorCornerRadiusAll(self, value: int) -> bool:
        value = max(0, min(1000, int(value)))
        return self.setSelectedVectorCornerRadii(value, value, value, value)

    @Slot(str, result=bool)
    def setSelectedCornerMode(self, mode: str) -> bool:
        if not self.selectedSupportsCornerRadius:
            self._set_status("当前图层不支持矩形圆角", toast=True)
            return False
        mode = str(mode or "").strip().lower()
        if mode not in {"uniform", "independent"}:
            self._set_status("未知的圆角编辑模式", toast=True)
            return False
        layer = self._selected_layer()
        if mode == "uniform":
            value = max(
                max(0, int(getattr(layer, "corner_radius", 0))),
                *self.selectedVectorCornerRadii,
            )
            self._corner_edit_modes[id(layer)] = "uniform"
            return self.setSelectedCornerRadius(value)
        self._corner_edit_modes[id(layer)] = "independent"
        self.selectionChanged.emit()
        return True

    @Slot(int, int, int, int, result=bool)
    def setSelectedVectorCornerRadii(self, top_left: int, top_right: int, bottom_right: int, bottom_left: int) -> bool:
        if not self.selectedSupportsVectorCorners:
            self._set_status("当前图层不支持四角圆角", toast=True)
            return False
        values = [
            max(0, min(1000, int(top_left))),
            max(0, min(1000, int(top_right))),
            max(0, min(1000, int(bottom_right))),
            max(0, min(1000, int(bottom_left))),
        ]
        changes = {
            "vector_corner_radius_tl": values[0],
            "vector_corner_radius_tr": values[1],
            "vector_corner_radius_br": values[2],
            "vector_corner_radius_bl": values[3],
            "corner_radius": max(values),
        }
        self._corner_edit_modes[id(self._selected_layer())] = "independent"
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "修改矢量四角圆角")

    @Slot(bool, result=bool)
    def setSelectedFlipHorizontal(self, enabled: bool) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持水平翻转", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "flip_horizontal",
            bool(enabled),
            "水平翻转图层",
        )

    @Slot(bool, result=bool)
    def setSelectedFlipVertical(self, enabled: bool) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持垂直翻转", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "flip_vertical",
            bool(enabled),
            "垂直翻转图层",
        )

    def _selected_shaped_layer(self):
        layer = self._selected_layer()
        if not isinstance(layer, ShapedLayer):
            self._set_status("当前图层不是异形图层", toast=True)
            return None
        return layer

    @Slot(str, result=bool)
    def setSelectedShapeType(self, shape_id: str) -> bool:
        layer = self._selected_shaped_layer()
        if layer is None:
            return False
        shape_id = str(shape_id or "").strip().lower()
        shape_entry = _SHAPE_TYPES.get(shape_id)
        if shape_entry is None:
            self._set_status("不支持的异形类型", toast=True)
            return False
        changes = {"shape_type": shape_entry[0]}
        if shape_entry[0] == ShapeType.RIGHT_TRAPEZOID:
            width = max(1, int(layer.width))
            changes.update(
                {
                    "trapezoid_top_width": width,
                    "trapezoid_bottom_width": max(1, round(width * 0.8)),
                    "trapezoid_slope_side": "right",
                }
            )
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            f"切换异形为{shape_entry[1]}",
        )

    @Slot(int, result=bool)
    def setSelectedTrapezoidTopWidth(self, value: int) -> bool:
        layer = self._selected_shaped_layer()
        if layer is None:
            return False
        value = max(1, min(int(layer.width), int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "trapezoid_top_width",
            value,
            "修改梯形上底",
        )

    @Slot(int, result=bool)
    def setSelectedTrapezoidBottomWidth(self, value: int) -> bool:
        layer = self._selected_shaped_layer()
        if layer is None:
            return False
        value = max(1, min(int(layer.width), int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "trapezoid_bottom_width",
            value,
            "修改梯形下底",
        )

    @Slot(str, result=bool)
    def setSelectedTrapezoidSlopeSide(self, value: str) -> bool:
        if self._selected_shaped_layer() is None:
            return False
        value = str(value or "").strip().lower()
        if value not in {"left", "right"}:
            self._set_status("梯形斜边方向无效", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "trapezoid_slope_side",
            value,
            "修改梯形斜边方向",
        )

    @Slot(float, result=bool)
    def setSelectedPolygonRotation(self, value: float) -> bool:
        if self._selected_shaped_layer() is None:
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "polygon_rotation",
            float(value) % 360.0,
            "旋转多边形内容",
        )

    @Slot(int, result=bool)
    def setSelectedPolygonCornerRadius(self, value: int) -> bool:
        if self._selected_shaped_layer() is None or not self.selectedSupportsShapeCornerRadius:
            self._set_status("当前形状不支持顶点圆角", toast=True)
            return False
        value = max(0, min(self.selectedPolygonCornerRadiusMax, int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "polygon_corner_radius",
            value,
            "修改多边形圆角",
        )

    @Slot(str, result=bool)
    def setSelectedName(self, value: str) -> bool:
        value = str(value or "").strip()
        if not value:
            self._set_status("图层名称不能为空", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "name",
            value[:120],
            "重命名图层",
            render=False,
        )

    @Slot(float, result=bool)
    def setSelectedRotation(self, value: float) -> bool:
        if not self.selectedCanRotate:
            self._set_status("当前图层不支持旋转", toast=True)
            return False
        value = float(value) % 360.0
        return self._set_layer_attr(self.selectedLayerIndex, "rotation", value, "旋转图层")

    @Slot(int, int, int, int, result=bool)
    def applySelectedGeometry(self, x: int, y: int, width: int, height: int) -> bool:
        if width <= 0 or height <= 0:
            self._set_status("图层尺寸必须大于零", toast=True)
            return False
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            {
                "x": int(x),
                "y": int(y),
                "width": int(width),
                "height": int(height),
            },
            "画布变换图层",
        )

    @Slot(int, int, int, int, result=bool)
    def transformSelectedLayers(self, x: int, y: int, width: int, height: int) -> bool:
        indices = self._selected_content_indices()
        if not indices or width < 1 or height < 1:
            return False
        old_x, old_y, old_width, old_height = self._selection_bounds()
        if old_width <= 0 or old_height <= 0:
            return False
        scale_x = float(width) / old_width
        scale_y = float(height) / old_height
        with self._document_lock:
            self._ensure_history_baseline()
            changed = 0
            for index in indices:
                layer = self._document.layers[index]
                if is_effectively_locked(layer, self._document.layers):
                    continue
                layer.x = round(int(x) + (float(layer.x) - old_x) * scale_x)
                layer.y = round(int(y) + (float(layer.y) - old_y) * scale_y)
                layer.width = max(1, round(float(layer.width) * scale_x))
                layer.height = max(1, round(float(layer.height) * scale_y))
                changed += 1
            if not changed:
                return False
            self._finish_arrangement("缩放多个图层", f"已缩放 {changed} 个图层")
        return True

    @Slot(str, result=bool)
    def alignSelected(self, mode: str) -> bool:
        layer = self._selected_layer()
        if layer is None:
            return False
        mode = str(mode or "").lower()
        width = int(getattr(layer, "width", 0))
        height = int(getattr(layer, "height", 0))
        if mode == "same_size" and bool(getattr(layer, "use_original_size", False)):
            self._set_status("原始尺寸模式下无法匹配画板大小", toast=True)
            return False
        alignments = {
            "left": {"x": 0},
            "hcenter": {"x": (self.canvasWidth - width) // 2},
            "right": {"x": self.canvasWidth - width},
            "top": {"y": 0},
            "vcenter": {"y": (self.canvasHeight - height) // 2},
            "bottom": {"y": self.canvasHeight - height},
            "center": {
                "x": (self.canvasWidth - width) // 2,
                "y": (self.canvasHeight - height) // 2,
            },
            "same_size": {
                "x": 0,
                "y": 0,
                "width": self.canvasWidth,
                "height": self.canvasHeight,
            },
        }
        changes = alignments.get(mode)
        if changes is None:
            return False
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "对齐图层")

    @Slot(result=bool)
    def randomizeAllLayers(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self._document.layers:
            self._set_status("没有可随机化的图层", toast=True)
            return False
        try:
            with self._document_lock:
                self._document.randomize_all_layers()
        except Exception as error:
            self._set_status(f"随机化图层失败：{error}", toast=True)
            return False
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已随机化所有图层", toast=True)
        return True

    @Slot(int, result=bool)
    def setSelectedX(self, value: int) -> bool:
        return self._set_layer_attr(self.selectedLayerIndex, "x", int(value), "修改 X 坐标")

    @Slot(int, result=bool)
    def setSelectedY(self, value: int) -> bool:
        return self._set_layer_attr(self.selectedLayerIndex, "y", int(value), "修改 Y 坐标")

    @Slot(bool, result=bool)
    def setSelectedAspectRatioLocked(self, enabled: bool) -> bool:
        if not self.selectedSupportsAspectRatioLock:
            self._set_status("当前图层不支持比例锁定", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "aspect_ratio_locked",
            bool(enabled),
            "切换比例锁定",
        )

    @Slot(int, result=bool)
    def setSelectedWidth(self, value: int) -> bool:
        if value <= 0:
            return False
        layer = self._selected_layer()
        if self.selectedAspectRatioLocked and layer is not None:
            current_width = max(1, int(getattr(layer, "width", 1)))
            current_height = max(1, int(getattr(layer, "height", 1)))
            return self._set_layer_attrs(
                self.selectedLayerIndex,
                {
                    "width": int(value),
                    "height": max(1, round(int(value) * current_height / current_width)),
                },
                "等比修改图层宽度",
            )
        return self._set_layer_attr(self.selectedLayerIndex, "width", int(value), "修改图层宽度")

    @Slot(int, result=bool)
    def setSelectedHeight(self, value: int) -> bool:
        if value <= 0:
            return False
        layer = self._selected_layer()
        if self.selectedAspectRatioLocked and layer is not None:
            current_width = max(1, int(getattr(layer, "width", 1)))
            current_height = max(1, int(getattr(layer, "height", 1)))
            return self._set_layer_attrs(
                self.selectedLayerIndex,
                {
                    "width": max(1, round(int(value) * current_width / current_height)),
                    "height": int(value),
                },
                "等比修改图层高度",
            )
        return self._set_layer_attr(self.selectedLayerIndex, "height", int(value), "修改图层高度")

    @Slot(bool, result=bool)
    def setSelectedRandomPositionEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        changed = self._set_layer_attr(
            self.selectedLayerIndex,
            "random_position_enabled",
            bool(enabled),
            "切换随机位置",
            render=False,
        )
        return changed and self._refresh_random_transform_preview()

    @Slot(int, result=bool)
    def setSelectedRandomPositionRange(self, value: int) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "random_position_range",
            max(0, min(10000, int(value))),
            "修改随机位置范围",
        )

    @Slot(bool, result=bool)
    def setSelectedRandomScaleEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        changed = self._set_layer_attr(
            self.selectedLayerIndex,
            "random_scale_enabled",
            bool(enabled),
            "切换随机缩放",
            render=False,
        )
        return changed and self._refresh_random_transform_preview()

    @Slot(int, result=bool)
    def setSelectedRandomScaleMinPercent(self, value: int) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        value = max(1, min(1000, int(value))) / 100.0
        layer = self._selected_layer()
        changes = {"random_scale_min": value}
        if float(getattr(layer, "random_scale_max", 1.0)) < value:
            changes["random_scale_max"] = value
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            "修改随机缩放下限",
        )

    @Slot(int, result=bool)
    def setSelectedRandomScaleMaxPercent(self, value: int) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        value = max(1, min(1000, int(value))) / 100.0
        layer = self._selected_layer()
        changes = {"random_scale_max": value}
        if float(getattr(layer, "random_scale_min", 1.0)) > value:
            changes["random_scale_min"] = value
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            "修改随机缩放上限",
        )

    @Slot(bool, result=bool)
    def setSelectedRandomRotationEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        changed = self._set_layer_attr(
            self.selectedLayerIndex,
            "random_rotation_enabled",
            bool(enabled),
            "切换随机旋转",
            render=False,
        )
        return changed and self._refresh_random_transform_preview()

    @Slot(float, result=bool)
    def setSelectedRandomRotationRange(self, value: float) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "random_rotation_range",
            max(0.0, min(180.0, float(value))),
            "修改随机旋转范围",
        )

    @Slot(result=bool)
    def regenerateSelectedRandomTransform(self) -> bool:
        return self._refresh_random_transform_preview()

    def _set_selected_clone_attr(self, attr: str, value, action: str) -> bool:
        if not self.selectedSupportsClone:
            self._set_status("当前图层不支持分身", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, attr, value, action)

    @Slot(bool, result=bool)
    def setSelectedCloneEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsClone:
            self._set_status("当前图层不支持分身", toast=True)
            return False
        layer = self._selected_layer()
        changes = {"clone_enabled": bool(enabled)}
        if enabled and int(layer.clone_rows) == 1 and int(layer.clone_columns) == 1:
            changes.update({"clone_rows": 2, "clone_columns": 2})
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "切换图层分身")

    @Slot(int, result=bool)
    def setSelectedCloneRows(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_rows", max(1, min(100, int(value))), "修改分身行数"
        )

    @Slot(int, result=bool)
    def setSelectedCloneColumns(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_columns", max(1, min(100, int(value))), "修改分身列数"
        )

    @Slot(int, result=bool)
    def setSelectedCloneRowSpacing(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_row_spacing", max(0, min(10000, int(value))), "修改分身行距"
        )

    @Slot(int, result=bool)
    def setSelectedCloneColumnSpacing(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_column_spacing", max(0, min(10000, int(value))), "修改分身列距"
        )

    @Slot(str, result=bool)
    def setSelectedCloneMirrorMode(self, value: str) -> bool:
        value = str(value or "none")
        if value not in {"none", "horizontal", "vertical"}:
            self._set_status("未知的分身镜像模式", toast=True)
            return False
        return self._set_selected_clone_attr("clone_mirror_mode", value, "修改分身镜像")

    @Slot(bool, result=bool)
    def setSelectedCloneCustomSizeEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsClone:
            self._set_status("当前图层不支持分身", toast=True)
            return False
        layer = self._selected_layer()
        changes = {"clone_custom_size_enabled": bool(enabled)}
        if enabled:
            changes.update(
                {
                    "clone_custom_width": max(1, int(getattr(layer, "width", 1))),
                    "clone_custom_height": max(1, int(getattr(layer, "height", 1))),
                }
            )
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "切换分身自定义尺寸")

    @Slot(int, result=bool)
    def setSelectedCloneCustomWidth(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_custom_width", max(1, min(10000, int(value))), "修改分身宽度"
        )

    @Slot(int, result=bool)
    def setSelectedCloneCustomHeight(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_custom_height", max(1, min(10000, int(value))), "修改分身高度"
        )

    @Slot(bool, result=bool)
    def setSelectedCloneFillEnabled(self, enabled: bool) -> bool:
        return self.setSelectedCloneLayoutMode("fill" if enabled else "fixed")

    @Slot(str, result=bool)
    def setSelectedCloneLayoutMode(self, mode: str) -> bool:
        mode = str(mode or "").strip().lower()
        if mode not in {"fixed", "fill"}:
            self._set_status("未知的分身布局模式", toast=True)
            return False
        return self._set_selected_clone_attr(
            "clone_fill_enabled",
            mode == "fill",
            "切换分身布局模式",
        )

    @Slot(str, result=bool)
    def setSelectedCloneFillMode(self, value: str) -> bool:
        value = str(value or "grid")
        if value not in {"grid", "staggered", "border"}:
            self._set_status("未知的元素铺排模式", toast=True)
            return False
        return self._set_selected_clone_attr("clone_fill_mode", value, "修改元素铺排模式")

    @Slot(int, result=bool)
    def setSelectedCloneFillSpacing(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_fill_spacing", max(0, min(10000, int(value))), "修改元素间距"
        )

    @Slot(int, result=bool)
    def setSelectedCloneFillMargin(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_fill_margin", max(0, min(1000, int(value))), "修改铺排边距"
        )

    @Slot(float, result=bool)
    def setSelectedCloneFillAngle(self, value: float) -> bool:
        return self._set_selected_clone_attr(
            "clone_fill_angle", float(value) % 360.0, "修改铺排角度"
        )

    @Slot(int, result=bool)
    def setSelectedOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))
        return self._set_layer_attr(self.selectedLayerIndex, "opacity", value / 100.0, "修改不透明度")

    @Slot(str, result=bool)
    def setSelectedBlendMode(self, mode_id: str) -> bool:
        mode_id = str(mode_id or "").strip().lower()
        if not self.selectedSupportsBlendMode:
            self._set_status("当前图层不支持混合模式", toast=True)
            return False
        if mode_id not in _BLEND_MODES:
            self._set_status("未知的混合模式", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "blend_mode",
            _BLEND_MODES[mode_id][0],
            "修改混合模式",
        )

    @Slot(bool, result=bool)
    def setSelectedStrokeEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsStroke:
            self._set_status("当前图层不支持描边", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "stroke_enabled",
            bool(enabled),
            "切换描边",
        )

    @Slot(int, result=bool)
    def setSelectedStrokeWidth(self, value: int) -> bool:
        if not self.selectedSupportsStroke:
            self._set_status("当前图层不支持描边", toast=True)
            return False
        value = max(1, min(128, int(value)))
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_width", value, "修改描边宽度")

    @Slot(str, result=bool)
    def setSelectedStrokeColor(self, value: str) -> bool:
        if not self.selectedSupportsStroke:
            self._set_status("当前图层不支持描边", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("描边颜色格式无效", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_color", color, "修改描边颜色")

    @Slot(int, result=bool)
    def setSelectedStrokeType(self, value: int) -> bool:
        if not self.selectedSupportsAdvancedStroke:
            self._set_status("当前图层不支持高级描边", toast=True)
            return False
        value = max(0, min(2, int(value)))
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_type", value, "修改描边对齐")

    @Slot(str, result=bool)
    def setSelectedStrokeJoin(self, value: str) -> bool:
        value = str(value or "miter")
        if not self.selectedSupportsAdvancedStroke or value not in {"miter", "round", "bevel"}:
            self._set_status("未知的描边连接类型", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_join", value, "修改描边连接")

    @Slot(str, result=bool)
    def setSelectedStrokeCap(self, value: str) -> bool:
        value = str(value or "butt")
        if not self.selectedSupportsAdvancedStroke or value not in {"butt", "round", "square"}:
            self._set_status("未知的描边端点类型", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_cap", value, "修改描边端点")

    @Slot(int, int, result=bool)
    def setSelectedStrokeDash(self, length: int, gap: int) -> bool:
        if not self.selectedSupportsAdvancedStroke:
            self._set_status("当前图层不支持高级描边", toast=True)
            return False
        changes = {
            "stroke_dash_length": max(0, min(1000, int(length))),
            "stroke_dash_gap": max(0, min(1000, int(gap))),
        }
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "修改描边虚线")

    @Slot(int, result=bool)
    def setSelectedCornerRadius(self, value: int) -> bool:
        if not self.selectedSupportsCornerRadius:
            self._set_status("当前图层不支持圆角", toast=True)
            return False
        value = max(0, min(self.selectedCornerRadiusMax, int(value)))
        layer = self._selected_layer()
        self._corner_edit_modes[id(layer)] = "uniform"
        changes = {
            "corner_radius": value,
            "vector_corner_radius_tl": 0,
            "vector_corner_radius_tr": 0,
            "vector_corner_radius_br": 0,
            "vector_corner_radius_bl": 0,
        }
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "修改统一圆角")

    @Slot(str, result=bool)
    def setSelectedOverlayMode(self, mode: str) -> bool:
        mode = str(mode or "").strip().lower()
        if mode not in {"none", "color", "gradient"}:
            self._set_status("未知的颜色叠加模式", toast=True)
            return False
        if mode == "color" and not self.selectedSupportsColorOverlay:
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        if mode == "gradient" and not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        if mode == "none" and not (
            self.selectedSupportsColorOverlay or self.selectedSupportsGradientOverlay
        ):
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        changes = {}
        if self.selectedSupportsColorOverlay:
            changes["color_overlay_enabled"] = mode == "color"
        if self.selectedSupportsGradientOverlay:
            changes["gradient_overlay_enabled"] = mode == "gradient"
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            "切换颜色叠加模式",
        )

    @Slot(bool, result=bool)
    def setSelectedColorOverlayEnabled(self, enabled: bool) -> bool:
        if enabled:
            return self.setSelectedOverlayMode("color")
        if self.selectedOverlayMode == "color":
            return self.setSelectedOverlayMode("none")
        return True

    @Slot(str, result=bool)
    def setSelectedColorOverlayColor(self, value: str) -> bool:
        if not self.selectedSupportsColorOverlay:
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("叠加颜色格式无效", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "color_overlay_color",
            color,
            "修改叠加颜色",
        )

    @Slot(int, result=bool)
    def setSelectedColorOverlayOpacity(self, value: int) -> bool:
        if not self.selectedSupportsColorOverlay:
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        value = max(0, min(100, int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "color_overlay_opacity",
            value / 100.0,
            "修改颜色叠加强度",
        )

    @Slot(bool, result=bool)
    def setSelectedGradientOverlayEnabled(self, enabled: bool) -> bool:
        if enabled:
            return self.setSelectedOverlayMode("gradient")
        if self.selectedOverlayMode == "gradient":
            return self.setSelectedOverlayMode("none")
        return True

    @Slot(int, str, result=bool)
    def setSelectedGradientOverlayColor(self, index: int, value: str) -> bool:
        if not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        if index not in (0, 1):
            self._set_status("渐变颜色端点无效", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("渐变颜色格式无效", toast=True)
            return False
        colors = self._selected_gradient_colors()
        colors[index] = color
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "gradient_overlay_colors",
            colors,
            "修改渐变颜色",
        )

    @Slot(int, result=bool)
    def setSelectedGradientOverlayOpacity(self, value: int) -> bool:
        if not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        value = max(0, min(100, int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "gradient_overlay_opacity",
            value / 100.0,
            "修改渐变叠加强度",
        )

    @Slot(float, result=bool)
    def setSelectedGradientOverlayAngle(self, value: float) -> bool:
        if not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "gradient_overlay_angle",
            float(value) % 360.0,
            "修改渐变角度",
        )

    @Slot(int, result=bool)
    def toggleLayerVisible(self, index: int) -> bool:
        layer = self._layer_model.layer_at(index)
        return bool(layer) and self._set_layer_attr(index, "visible", not bool(layer.visible), "切换图层可见性")

    @Slot(int, result=bool)
    def toggleLayerLocked(self, index: int) -> bool:
        layer = self._layer_model.layer_at(index)
        return bool(layer) and self._set_layer_attr(
            index,
            "locked",
            not bool(layer.locked),
            "切换图层锁定",
            render=False,
        )

    @Slot(result=bool)
    def undo(self) -> bool:
        if not self._ensure_operations_available():
            return False
        with self._document_lock:
            if not self._document.undo():
                return False
            self._document.is_modified = True
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.viewSettingsChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已撤销", toast=True)
        return True

    @Slot(result=bool)
    def redo(self) -> bool:
        if not self._ensure_operations_available():
            return False
        with self._document_lock:
            if not self._document.redo():
                return False
            self._document.is_modified = True
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已重做", toast=True)
        return True

    @Slot()
    @Slot(bool)
    def requestPreview(self, force: bool = False) -> None:
        del force
        if not self._auto_render:
            return
        self._preview_generation += 1
        self._pending_preview_generation = self._preview_generation
        self._pending_preview_quality = "interactive"
        self._preview_token_source.cancel()
        self._final_preview_timer.start()
        if self._render_running:
            self._render_pending = True
            return
        self._preview_timer.start()

    @Slot(result=bool)
    def renderPreviewNow(self) -> bool:
        if self._auto_render:
            self._final_preview_timer.stop()
            self._preview_timer.stop()
            self._pending_preview_generation = self._preview_generation
            self._pending_preview_quality = "final"
            self._preview_token_source.cancel()
            if self._render_running:
                self._render_pending = True
                return True
            self._start_preview_render()
            return True
        return self._render_preview_sync()

    @Slot()
    def _queue_final_preview(self) -> None:
        if not self._auto_render:
            return
        self._pending_preview_generation = self._preview_generation
        self._pending_preview_quality = "final"
        self._preview_token_source.cancel()
        if self._render_running:
            self._render_pending = True
            return
        self._preview_timer.start(0)

    def _build_preview_snapshot(self):
        from app.models.document_serializer import DocumentSerializer

        with self._document_lock:
            return DocumentSerializer.serialize_document_data(self._document)

    def _preview_active_layer_index(self) -> int:
        indices = [
            int(index)
            for index in list(getattr(self._document, "selected_layer_indices", []) or [])
            if 0 <= int(index) < len(getattr(self._document, "layers", []) or [])
        ]
        if len(indices) != 1:
            return -1
        layer = self._document.layers[indices[0]]
        return -1 if is_layer_group(layer) else indices[0]

    @Slot()
    def _start_preview_render(self) -> None:
        if self._render_running:
            self._render_pending = True
            return
        quality = self._pending_preview_quality or "interactive"
        generation = self._pending_preview_generation or self._preview_generation
        self._pending_preview_quality = None
        self._pending_preview_generation = generation
        snapshot_data = None
        if bool(getattr(self._document, "_is_batch_export_running", False)):
            try:
                snapshot_data = self._build_preview_snapshot()
            except Exception as error:
                self._set_status(f"预览快照失败：{error}", toast=True)
                return
        self._render_running = True
        self._render_pending = False
        self._render_request_id += 1
        token = self._preview_token_source.next()
        task = _PreviewTask(
            self._render_request_id,
            generation,
            self._document,
            snapshot_data=snapshot_data,
            interactive_low_quality=quality == "interactive",
            active_layer_index=self._preview_active_layer_index(),
            cancel_token=token,
        )
        task.signals.finished.connect(self._on_preview_rendered)
        self._active_render_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(int, int, bool, object, str, float)
    def _on_preview_rendered(
        self,
        request_id: int,
        generation: int,
        interactive_low_quality: bool,
        qimage,
        error: str,
        elapsed: float,
    ) -> None:
        self._render_running = False
        self._active_render_task = None
        current_result = (
            request_id == self._render_request_id
            and generation == self._preview_generation
        )
        if current_result and qimage is not None and not qimage.isNull():
            self._preview_provider.set_image(qimage)
            self._preview_revision += 1
            self.previewChanged.emit()
            if not interactive_low_quality:
                self._set_status(f"预览完成 · {elapsed * 1000:.0f} ms")
        elif current_result and error:
            self._set_status(f"预览失败：{error}", toast=True)
        if self._render_pending:
            self._render_pending = False
            self._preview_timer.start(0)

    def _render_preview_sync(self) -> bool:
        from app.services.preview_render_service import render_preview_to_image

        self._set_busy(True)
        try:
            with self._document_lock:
                result = render_preview_to_image(self._document, force_refresh=True)
            if result.image is None:
                self._set_status(f"预览失败：{result.error or '渲染器未返回图像'}", toast=True)
                return False
            qimage = _pil_to_qimage(result.image)
            self._preview_provider.set_image(qimage)
            self._preview_revision += 1
            self.previewChanged.emit()
            self._set_status(f"预览完成 · {result.elapsed * 1000:.0f} ms")
            return True
        except Exception as error:
            self._set_status(f"预览失败：{error}", toast=True)
            return False
        finally:
            self._set_busy(False)
