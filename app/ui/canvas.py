# -*- coding: utf-8 -*-
"""Canvas widget components."""

from collections import OrderedDict
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QMenu
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPixmap, QCursor, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, QTimer, QRunnable, QThreadPool
from app.ui.dark_theme import CursorDarkTheme
from app.utils.layer_tree import (
    child_indices_for_group,
    expand_group_indices,
    group_bounds,
    is_layer_group,
    is_effectively_locked,
    is_effectively_visible,
)
from app.ui.canvas_view import CanvasWidgetCanvasView
from app.ui.canvas_render import CanvasWidgetCanvasRender
from app.ui.canvas_draw import CanvasWidgetCanvasDraw
from app.ui.canvas_hit import CanvasWidgetCanvasHit
from app.ui.canvas_events import CanvasWidgetCanvasEvents
from app.ui.preview_interaction_overlay import (
    InteractionOverlayState,
    _LayerSurface,
    make_pixmap_from_image,
)
import time
import threading

class _CanvasPreviewRenderTask(QRunnable):
    """Small QRunnable wrapper for preview renders; results are installed by CanvasWidget polling."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self.setAutoDelete(True)

    def run(self):
        self._callback()

class CanvasWidget(QWidget, CanvasWidgetCanvasView, CanvasWidgetCanvasRender, CanvasWidgetCanvasDraw, CanvasWidgetCanvasHit, CanvasWidgetCanvasEvents):
    """画布控件，用于显示和编辑图像"""
    position_changed = Signal(int, int)  # 鼠标位置变化
    def __init__(self, document):
        super().__init__()
        self.document = document
        self.zoom_factor = 1.0
        self.offset = QPoint(0, 0)
        self.drag_start = None
        self.is_dragging = False
        self.is_dragging_layer = False
        self.dragging_layer_index = -1
        self.layer_drag_start = None

        # 调整大小状态变量
        self.is_resizing = False
        self.resize_handle_index = -1  # 表示当前拖动的控制点索引
        self.resize_start_rect = None  # 记录调整大小开始时的图层矩形
        self.resize_start_point = None  # 记录调整大小开始时的鼠标位置
        self.resize_start_group_child_rects = {}
        self.is_dragging_vector_node = False
        self.vector_node_index = -1
        self.is_dragging_vector_handle = False
        self.vector_handle_node_index = -1
        self.vector_handle_type = None
        self.selected_vector_node_index = -1
        self._context_vector_segment_index = -1
        self.is_dragging_corner_radius = False
        self.corner_radius_start_point = None
        self.corner_radius_start_value = 0

        # Space键临时抓手工具状态
        self.space_pressed = False
        self.temp_hand_mode = False
        self.original_cursor = Qt.ArrowCursor

        # 拖拽交互增强状态
        self.drag_preview_enabled = True  # 拖拽预览开关
        self.drag_preview_opacity = 0.6   # 拖拽预览透明度
        self.show_drag_bounds = True      # 显示拖拽边界
        self.drag_ghost_layer = None      # 拖拽时的幽灵图层预览

        # 拖拽手势识别增强
        self.drag_threshold = 5           # 拖拽检测阈值（像素）
        self.drag_start_pos = None        # 拖拽开始位置
        self.potential_drag = False       # 是否可能开始拖拽
        self.dragging_layer_indices = []
        self.dragging_layer_start_positions = {}
        self.dragging_group_start_bounds = None

        # 设置焦点策略以便接收键盘事件
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)

        # 设置右键菜单策略
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # 设置工具提示
        self.setToolTip("提示: 按住Alt键点击图层可以在不改变当前选中图层的情况下操作图层")

        # 就地文字编辑器（Photoshop 风格，双击文字图层打开）
        self._text_editor = None

        # 连接文档变化信号（启用防抖更新，避免界面抽动）
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self.update)

        def _schedule_update_delayed():
            if self._is_export_preview_frozen():
                return
            # 约16~33ms的防抖窗口，减少连续参数调整导致的频繁重绘
            delay_ms = 20
            if self._update_timer.isActive():
                # 重置计时，实现“最后一次触发后再更新”
                self._update_timer.stop()
            self._update_timer.start(delay_ms)

        self.document.document_changed.connect(_schedule_update_delayed)
        self.document.layer_changed.connect(_schedule_update_delayed)
        self.document.document_changed.connect(self._invalidate_composition_cache)
        self.document.layer_changed.connect(self._invalidate_composition_cache)

        # 性能埋点：监控 document/layer_changed 频率。
        try:
            from app.utils.preview_perf import is_perf_enabled
            if is_perf_enabled():
                from app.utils.preview_perf import PreviewPerfMonitor
                _perf_monitor = PreviewPerfMonitor.instance()
                self.document.document_changed.connect(_perf_monitor.record_document_changed)
                self.document.layer_changed.connect(_perf_monitor.record_layer_changed)
        except Exception:
            pass

        # 交互过程（拖拽/缩放）刷新节流，避免高频事件导致掉帧
        self._interactive_frame_interval_ms = 16  # 约60FPS，交互期间优先保障鼠标跟手
        self._last_interactive_update_ms = 0.0
        self._interactive_update_pending = False
        self._interactive_requires_recompose = False
        self._interactive_low_quality_active = False
        self._force_high_quality_refresh = False
        self._panel_interaction_active = False
        self._panel_interaction_layer_index = -1
        self._panel_interaction_fields = {
            "position",
            "size",
            "rotation",
            "opacity",
            "visibility",
            "random_position_range",
            "random_scale_min",
            "random_scale_max",
            "random_rotation_range",
            "trapezoid_params",
            "polygon_params",
            "vector_corner_radius",
            "vector_corner_radius_detail",
            "vector_path",
            "stroke_enabled",
            "stroke_width",
            "stroke_type",
            "stroke_color",
            "stroke_join",
            "stroke_cap",
            "stroke_dash",
            "fill_solid_enabled",
            "fill_solid_color",
            "fill_gradient_enabled",
            "fill_gradient_colors",
            "fill_gradient_angle",
            "fill_gradient_opacity",
            "clone_grid",
            "clone_custom_size",
            "fill_spacing",
            "fill_margin",
            "fill_angle",
        }
        self._interactive_update_timer = QTimer(self)
        self._interactive_update_timer.setSingleShot(True)
        self._interactive_update_timer.timeout.connect(self._flush_interactive_update)
        self._panel_interaction_idle_timer = QTimer(self)
        self._panel_interaction_idle_timer.setSingleShot(True)
        self._panel_interaction_idle_timer.timeout.connect(self._on_panel_interaction_idle)
        self._hover_hit_test_interval_ms = 35
        self._last_hover_hit_test_ms = 0.0
        self._last_hover_pos = QPoint(-100000, -100000)
        self._zoom_interaction_active = False
        self._zoom_idle_timer = QTimer(self)
        self._zoom_idle_timer.setSingleShot(True)
        self._zoom_idle_timer.timeout.connect(self._on_zoom_interaction_idle)

        # 棋盘格背景缓存，避免每帧逐格填充
        self._checkerboard_cache = None
        self._checkerboard_cache_size = QSize()
        self._checkerboard_cell_size = 10

        # 合成结果的QPixmap缓存，避免重复 PIL -> QImage -> QPixmap 转换
        self._composition_pixmap_cache = None
        self._composition_cache_valid = False
        self._async_render_lock = threading.RLock()
        self._async_render_pending = False
        self._async_render_result = None
        self._async_render_error = None
        self._async_render_generation = 0
        self._async_render_request_key = None
        self._async_render_restart_args = None
        self._async_render_restart_requested = False
        self._async_render_timer = QTimer(self)
        self._async_render_timer.setInterval(16)
        self._async_render_timer.timeout.connect(self._poll_async_render_result)
        self._pending_quick_frame_completion = False
        self._composition_invalidation_generation = 0
        # 按当前缩放尺寸缓存缩放后的QPixmap，减少平移阶段重复缩放
        self._scaled_composition_cache_key = None
        self._scaled_composition_pixmap_cache = OrderedDict()
        self._max_scaled_composition_cache_entries = 8
        self._composition_mipmap_cache_key = None
        self._composition_mipmap_cache = []

        # 阶段 2：交互 Overlay 状态
        self._interaction_overlay = InteractionOverlayState()
        # 阶段 4：后台预览渲染取消 token
        from app.utils.preview_render_token import PreviewRenderTokenSource
        self._preview_render_token_source = PreviewRenderTokenSource()

        # 阶段 6：hit-test 缓存
        self._hit_cache_generation = 0
        self._hit_cache_built_generation = -1
        self._hit_cache_zoom = -1.0
        self._hit_cache_offset_x = 0
        self._hit_cache_offset_y = 0
        self._hit_cache_layers_version = -1
        self._hit_cache_hit_version = -1
        self._hit_rect_cache = {}  # layer_index -> QRect
        self._hit_path_cache = {}  # layer_index -> QPainterPath
        self._hit_clone_positions_cache = {}  # layer_index -> [positions]
        self._hit_visible_layers_cache = []  # [layer_index, ...]
        self._hit_cache_locked_states = {}  # layer_index -> bool

        # 阶段 7：选中覆盖层几何缓存（key=layer_index, zoom, offset_x, offset_y）
        self._selection_overlay_cache = None
        self._selection_overlay_cache_key = None
        self._selection_overlay_cache_geom = None  # {'display_rects': [...], 'handles': [...], ...}

        # Photoshop风格标尺与参考线
        self.show_rulers = True
        self.show_guides = True
        self._ruler_size = 20
        self.horizontal_guides = []  # 画布坐标系 y
        self.vertical_guides = []    # 画布坐标系 x
        self._guide_hit_tolerance = 4
        self._is_dragging_guide = False
        self._dragging_guide_orientation = None  # "horizontal" | "vertical"
        self._dragging_guide_index = -1
        self._pending_new_guide = False
        self._selected_guide_orientation = None
        self._selected_guide_index = -1
        self._guide_overlay_text = ""
        self._guide_overlay_pos = QPoint(0, 0)
        self.snap_to_guides = True
        self._snap_tolerance_px = 6
        self._snap_feedback_active = False
        self._snap_feedback_vertical = None
        self._snap_feedback_horizontal = None
        self._snap_feedback_text = ""
        self._snap_feedback_pos = QPoint(0, 0)
        self._load_view_settings_from_document()

        # 初始化窗口背景
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor(CursorDarkTheme.BACKGROUND_CANVAS))
        self.setPalette(p)

    # ------------------------------------------------------------------
    # Qt 事件方法转发
    #
    # 这些方法的实现分散在多个 mixin（CanvasWidgetCanvasRender /
    # CanvasWidgetCanvasView / CanvasWidgetCanvasEvents）中，但它们与
    # QWidget / QObject 自带的同名空方法冲突。由于 MRO 中 QWidget 排在
    # 各 mixin 之前，若不在本类显式定义，QWidget 的空实现会遮蔽 mixin
    # 的真实实现，导致画布无法渲染（paintEvent）且鼠标/滚轮/键盘交互
    # 全部失效。这里统一转发到对应的 mixin 实现。
    # -----------------------------------------------------------------

    def paintEvent(self, event):
        CanvasWidgetCanvasRender.paintEvent(self, event)

    def wheelEvent(self, event):
        CanvasWidgetCanvasView.wheelEvent(self, event)

    def mousePressEvent(self, event):
        CanvasWidgetCanvasEvents.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        CanvasWidgetCanvasEvents.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        CanvasWidgetCanvasEvents.mouseReleaseEvent(self, event)

    def mouseDoubleClickEvent(self, event):
        CanvasWidgetCanvasEvents.mouseDoubleClickEvent(self, event)

    def keyPressEvent(self, event):
        CanvasWidgetCanvasEvents.keyPressEvent(self, event)

    def keyReleaseEvent(self, event):
        CanvasWidgetCanvasEvents.keyReleaseEvent(self, event)
