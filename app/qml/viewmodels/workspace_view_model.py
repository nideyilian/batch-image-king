from __future__ import annotations

import copy
import json
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
from app.constants import DEFAULT_TEXT_FONT_FAMILY
from app.models.layer_group import LayerGroup
from app.models.layer_new import Layer
from app.models.layer_properties import ShapeType
from app.models.shaped_layer_new import ShapedLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.layer_list_model import LayerListModel
from app.utils.preview_render_token import PreviewRenderTokenSource
from app.utils.text_rich_format import (
    apply_editor_style,
    build_editor_html,
    inspect_editor_selection,
    parse_editor_html,
    qt_index_to_python,
)
from app.utils.text_style_ranges import remap_text_style_ranges
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


from .workspace_vm_shared import (
    _BLEND_MODES,
    _BLEND_MODE_IDS,
    _SHAPE_TYPES,
    _FIT_MODES,
    _FIT_MODE_IDS,
    _CROP_DIRECTIONS,
    _CROP_DIRECTION_IDS,
    _TEXT_ALIGNMENTS,
    _TEXT_ALIGNMENT_IDS,
    _TEXT_GRADIENT_TYPES,
    _TEXT_GRADIENT_TYPE_IDS,
    _TEXT_GRADIENT_DIRECTIONS,
    _TEXT_GRADIENT_DIRECTION_IDS,
    _COMMON_STYLE_ATTRIBUTES,
    _TEXT_STYLE_ATTRIBUTES,
    _pil_to_qimage,
    _PreviewTaskSignals,
    _PreviewTask,
)

logger = logging.getLogger(__name__)


from .workspace_vm_preview import WorkspacePreviewMixin
from .workspace_vm_text_setters import WorkspaceTextSettersMixin
from .workspace_vm_font_catalog import WorkspaceFontCatalogMixin
from .workspace_vm_effects import WorkspaceEffectsMixin
from .workspace_vm_layer_ops import WorkspaceLayerOpsMixin
from .workspace_vm_edit_ops import WorkspaceEditOpsMixin
from .workspace_vm_document_ops import WorkspaceDocumentOpsMixin

_MIXIN_SOURCES = (
    WorkspacePreviewMixin,
    WorkspaceTextSettersMixin,
    WorkspaceFontCatalogMixin,
    WorkspaceEffectsMixin,
    WorkspaceLayerOpsMixin,
    WorkspaceEditOpsMixin,
    WorkspaceDocumentOpsMixin,
)


class _WorkspaceMixinsMeta(type(QObject)):
    """PySide6 metaobject 在类创建时构建，@Slot/@Property 仅在类创建前并入
    namespace 才会被注册（QML 才能调用）；事后 setattr 注入的方法对 QML 不可见。

    多继承（mixin 基类）会破坏 shiboken metaobject 导致段错误，故用元类把
    mixin 方法并入单一继承 QObject 的 namespace。类体内同名方法优先
    （namespace.setdefault），与现有方法名无冲突。
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        for _mixin in _MIXIN_SOURCES:
            for _method_name, _method in vars(_mixin).items():
                if not _method_name.startswith("__"):
                    namespace.setdefault(_method_name, _method)
        return super().__new__(mcs, name, bases, namespace, **kwargs)


class WorkspaceViewModel(QObject, metaclass=_WorkspaceMixinsMeta):
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
    recentTextFontsChanged = Signal()
    _fontCatalogLoaded = Signal(object, object)
    toastRequested = Signal(str)
    textEditingChanged = Signal()

    def __init__(
        self,
        document: Optional[Document] = None,
        preview_provider: Optional[PreviewImageProvider] = None,
        *,
        auto_render: bool = True,
        defer_font_catalog_preload: bool = False,
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
        self._defer_font_catalog_preload = bool(defer_font_catalog_preload)
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
        self._text_font_tree_with_recent_cache_token = None
        self._font_catalog_loading = False
        self._recent_text_fonts_cache = None
        self._recent_text_font_limit = 8
        self._text_edit_overlay_visible = False
        self._text_edit_layer_index = -1
        self._text_edit_draft_html = None
        self._layer_style_clipboard = None
        self._opacity_edit_context = None
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

    @Property(str, notify=selectionChanged)
    def selectedTextEditorHtml(self) -> str:
        if not self.selectedIsTextLayer:
            return ""
        if (
            self._text_edit_overlay_visible
            and self._text_edit_layer_index == self.selectedLayerIndex
            and self._text_edit_draft_html is not None
        ):
            return self._text_edit_draft_html
        return self._text_editor_html_for_layer(self._selected_layer())

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

    @Property(str, notify=selectionChanged)
    def selectedTextResolvedFontFamily(self) -> str:
        if not self.selectedIsTextLayer:
            return ""
        layer = self._selected_layer()
        family = str(getattr(layer, "font_family", DEFAULT_TEXT_FONT_FAMILY) or DEFAULT_TEXT_FONT_FAMILY)
        resolver = getattr(layer, "resolve_font_family", None)
        if callable(resolver):
            try:
                return str(resolver(family).get("resolved_family") or family)
            except Exception:
                pass
        resolver = getattr(layer, "_resolve_font_family", None)
        return str(resolver(family) if callable(resolver) else family)

    @Property(bool, notify=selectionChanged)
    def selectedTextFontAvailable(self) -> bool:
        if not self.selectedIsTextLayer:
            return False
        layer = self._selected_layer()
        resolver = getattr(layer, "resolve_font_family", None)
        if callable(resolver):
            try:
                return bool(resolver(getattr(layer, "font_family", "")).get("available"))
            except Exception:
                logger.debug("检查当前文字字体失败", exc_info=True)
        return True

    @Property(str, notify=selectionChanged)
    def selectedTextFontWarning(self) -> str:
        if self.selectedIsTextLayer and not self.selectedTextFontAvailable:
            return "字体不可用，当前使用回退字体"
        return ""








    @Property("QVariantList", notify=fontCatalogChanged)
    def textFontOptions(self):
        if self._text_font_options_cache is None:
            if not self._defer_font_catalog_preload:
                self.startFontCatalogPreload()
            return self._font_catalog_fallback_options()
        return list(self._text_font_options_cache)

    @Property("QVariantList", notify=fontCatalogChanged)
    def textFontTreeOptions(self):
        if self._text_font_tree_options_cache is None:
            if not self._defer_font_catalog_preload:
                self.startFontCatalogPreload()
            return self._font_catalog_fallback_tree()
        recent_group = self._build_recent_font_tree_group()
        if not recent_group:
            return list(self._text_font_tree_options_cache)
        # 用 (recent 是否等于上次, 基础 tree 是否相等) 做 token 缓存拼接结果，避免每次 Property 访问都重建
        try:
            base_token = len(self._text_font_tree_options_cache)
            recent_token = (len(recent_group), hash(tuple(
                (str(it.get("family", "")), str(it.get("face", "")))
                for entry in recent_group
                for it in (entry.get("children") or [entry])
            )))
            combined_token = (base_token, recent_token)
        except Exception:
            combined_token = None
        if combined_token is None or self._text_font_tree_with_recent_cache_token != combined_token:
            combined = list(recent_group) + [
                g for g in list(self._text_font_tree_options_cache)
                if not isinstance(g.get("__recent_block__"), bool)
            ]
            self._text_font_tree_with_recent_cache_combined = combined
            self._text_font_tree_with_recent_cache_token = combined_token
        return list(getattr(self, "_text_font_tree_with_recent_cache_combined", None) or
                    (list(recent_group) + list(self._text_font_tree_options_cache)))









    @Property("QVariantList", notify=recentTextFontsChanged)
    def recentTextFonts(self):
        entries = self._load_recent_text_fonts()
        options = []
        for entry in entries:
            family = entry.get("family", "") or ""
            face = entry.get("face", "") or ""
            entry_dict = {
                "family": family,
                "face": face,
                "label": family + (" · " + face if face else ""),
                "value": family,
            }
            options.append(entry_dict)
        return options


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

    @Property(int, notify=selectionChanged)
    def selectedTextFontWeight(self) -> int:
        if not self.selectedIsTextLayer:
            return 400
        face = self._selected_font_face()
        if face is not None:
            return int(face.get("weight", 400) or 400)
        return 700 if self.selectedTextBold else 400

    @Property("QVariantList", notify=selectionChanged)
    def selectedTextFontWeightOptions(self):
        if not self.selectedIsTextLayer:
            return []
        family = self.selectedTextFontFamily.casefold()
        candidates = []
        for group in self.textFontTreeOptions:
            # 跳过最近使用区块：其 children 列表只是真实字体族的子集（用户最近用的 face），
            # 不能代表当前字体族的完整字重列表。
            if bool(group.get("__recent_block__")) or group.get("group") in ("recent", "__recent_header__"):
                continue
            if str(group.get("family", "")).casefold() != family:
                continue
            candidates = [
                item for item in (group.get("children", []) or [])
                if not bool(item.get("synthetic", False))
                and bool(item.get("italic", False)) == self.selectedTextItalic
            ]
            break
        if not candidates:
            return [
                {"label": "400 · 常规", "value": 400},
                {"label": "700 · 粗体", "value": 700},
            ]
        options = []
        seen = set()
        for face in sorted(candidates, key=lambda item: int(item.get("weight", 400))):
            weight = int(face.get("weight", 400) or 400)
            if weight in seen:
                continue
            seen.add(weight)
            options.append({
                "label": f"{weight} · {self._font_face_label(face.get('face', 'Regular'))}",
                "value": weight,
            })
        return options

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





































    def _style_attributes_for_layer(self, layer) -> tuple:
        attrs = list(_COMMON_STYLE_ATTRIBUTES)
        if self._layer_model.layer_type_name(layer) == "文字":
            attrs.extend(_TEXT_STYLE_ATTRIBUTES)
        return tuple(attrs)



































    @Property(bool, notify=textEditingChanged)
    def textEditOverlayVisible(self) -> bool:
        return self._text_edit_overlay_visible
























































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