"""WorkspaceViewModel 视图/缩放/参考线/选区辅助/撤销重做方法组 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的 30 个方法，语义不变。
依赖主类实例方法（``_layer_model``、``_set_status`` 等）与下列模块级名字。
"""

from __future__ import annotations

import re
import threading

from PySide6.QtCore import Slot

from app.constants import DEFAULT_TEXT_FONT_FAMILY
from app.models.document import Document
from app.utils.layer_tree import expand_group_indices
from app.utils.text_rich_format import build_editor_html

from .workspace_vm_shared import _COMMON_STYLE_ATTRIBUTES, _TEXT_STYLE_ATTRIBUTES


class WorkspaceViewMixin:
    @Slot(bool)
    def setAutoRender(self, enabled: bool) -> None:
        """切换自动预览；启动阶段可先关闭，完成文档初始化后再开启。"""
        enabled = bool(enabled)
        if enabled == self._auto_render:
            return
        self._auto_render = enabled
        if not enabled:
            self._preview_timer.stop()
            self._final_preview_timer.stop()
            self._preview_token_source.cancel()

    @Slot()
    def renderInitialPreview(self) -> None:
        """在启动文档准备完成后提交首个预览请求。"""
        if self._auto_render:
            self.requestPreview(force=True)

    @property
    def document(self) -> Document:
        return self._document

    @property
    def documentLock(self) -> threading.RLock:
        return self._document_lock

    @Slot(float, result=bool)
    def setZoomFactor(self, value: float) -> bool:
        value = round(max(0.1, min(10.0, float(value))), 3)
        if self._document.view_settings.get("zoom_factor", 1.0) == value:
            return True
        self._document.view_settings["zoom_factor"] = value
        self.viewSettingsChanged.emit()
        return True

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

    @Slot(result=bool)
    def toggleRulers(self) -> bool:
        return self.setShowRulers(not self.showRulers)

    @Slot(bool, result=bool)
    def setShowGuides(self, enabled: bool) -> bool:
        return self._set_view_setting("show_guides", bool(enabled), "切换参考线显示")

    @Slot(result=bool)
    def toggleGuides(self) -> bool:
        return self.setShowGuides(not self.showGuides)

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

    def _selected_layer(self):
        return self._layer_model.layer_at(self.selectedLayerIndex)

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

    def _selected_gradient_colors(self):
        colors = getattr(self._selected_layer(), "gradient_overlay_colors", None)
        if not isinstance(colors, (list, tuple)) or len(colors) < 2:
            return [(0, 0, 0, 255), (255, 255, 255, 255)]
        normalized = []
        for color in colors[:2]:
            parsed = self._parse_hex_color(self._rgba_to_hex(color))
            normalized.append(parsed or (0, 0, 0, 255))
        return normalized

    def _text_editor_html_for_layer(self, layer) -> str:
        if layer is None:
            return ""
        binding_enabled = bool(getattr(layer, "text_binding_enabled", False))
        text = str(getattr(layer, "text_content", "") or "")
        requested_family = str(
            getattr(layer, "font_family", DEFAULT_TEXT_FONT_FAMILY)
            or DEFAULT_TEXT_FONT_FAMILY
        )
        resolver = getattr(layer, "resolve_font_family", None)
        if callable(resolver):
            try:
                font_family = str(resolver(requested_family).get("resolved_family") or requested_family)
            except Exception:
                font_family = requested_family
        else:
            resolver = getattr(layer, "_resolve_font_family", None)
            font_family = str(resolver(requested_family) if callable(resolver) else requested_family)
        return build_editor_html(
            text,
            font_family=font_family,
            font_size=max(1, int(getattr(layer, "font_size", 24) or 24)),
            text_color=getattr(layer, "text_color", (0, 0, 0, 255)),
            font_weight=int(
                getattr(self, "selectedTextFontWeight", 700 if self.selectedTextBold else 400)
            ),
            italic=self.selectedTextItalic,
            letter_spacing=int(getattr(layer, "letter_spacing", 0) or 0),
            line_spacing=float(getattr(layer, "line_spacing", 1.0) or 1.0),
            color_ranges=[] if binding_enabled else layer.get_text_color_ranges(),
            font_size_ranges=[] if binding_enabled else layer.get_font_size_ranges(),
        )

    def _style_attributes_for_layer(self, layer) -> tuple:
        attrs = list(_COMMON_STYLE_ATTRIBUTES)
        if self._layer_model.layer_type_name(layer) == "文字":
            attrs.extend(_TEXT_STYLE_ATTRIBUTES)
        return tuple(attrs)

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
