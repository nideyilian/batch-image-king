from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QMenu
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPixmap, QCursor, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, QTimer
from app.ui.dark_theme import CursorDarkTheme
import time

class CanvasWidget(QWidget):
    """画布控件，用于显示和编辑图像"""

    # 信号定义
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

        # 设置焦点策略以便接收键盘事件
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)

        # 设置右键菜单策略
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # 设置工具提示
        self.setToolTip("提示: 按住Alt键点击图层可以在不改变当前选中图层的情况下操作图层")

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

        # 交互过程（拖拽/缩放）刷新节流，避免高频事件导致掉帧
        self._interactive_frame_interval_ms = 33  # 约30FPS，优先保障交互流畅
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
            "random_position_range",
            "random_scale_min",
            "random_scale_max",
            "random_rotation_range",
            "trapezoid_params",
            "polygon_params",
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

        # 棋盘格背景缓存，避免每帧逐格填充
        self._checkerboard_cache = None
        self._checkerboard_cache_size = QSize()
        self._checkerboard_cell_size = 10

        # 合成结果的QPixmap缓存，避免重复 PIL -> QImage -> QPixmap 转换
        self._composition_pixmap_cache = None
        self._composition_cache_valid = False
        # 按当前缩放尺寸缓存缩放后的QPixmap，减少平移阶段重复缩放
        self._scaled_composition_pixmap_cache = None
        self._scaled_composition_cache_key = None

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

    def _load_view_settings_from_document(self):
        """从文档恢复画布视图参数"""
        if not hasattr(self.document, 'get_view_settings'):
            return
        settings = self.document.get_view_settings()
        self.show_rulers = bool(settings.get('show_rulers', self.show_rulers))
        self.show_guides = bool(settings.get('show_guides', self.show_guides))
        self.snap_to_guides = bool(settings.get('snap_to_guides', self.snap_to_guides))
        self._ruler_size = int(settings.get('ruler_size', self._ruler_size))
        self.horizontal_guides = [int(v) for v in (settings.get('horizontal_guides', []) or [])]
        self.vertical_guides = [int(v) for v in (settings.get('vertical_guides', []) or [])]
        self.zoom_factor = float(settings.get('zoom_factor', self.zoom_factor))
        self.zoom_factor = max(0.1, min(10.0, self.zoom_factor))
        offset_x = int(settings.get('offset_x', self.offset.x()))
        offset_y = int(settings.get('offset_y', self.offset.y()))
        self.offset = QPoint(offset_x, offset_y)

    def _persist_view_settings_to_document(self):
        """将画布视图参数回写到文档，确保保存/预设为全量参数"""
        if not hasattr(self.document, 'set_view_settings'):
            return
        self.document.set_view_settings({
            'show_rulers': self.show_rulers,
            'show_guides': self.show_guides,
            'snap_to_guides': self.snap_to_guides,
            'ruler_size': self._ruler_size,
            'horizontal_guides': list(self.horizontal_guides),
            'vertical_guides': list(self.vertical_guides),
            'zoom_factor': float(self.zoom_factor),
            'offset_x': int(self.offset.x()),
            'offset_y': int(self.offset.y()),
        })

    def _is_export_preview_frozen(self) -> bool:
        """导出期间是否冻结预览重渲染（性能策略）"""
        if not bool(getattr(self.document, '_is_batch_export_running', False)):
            return False
        try:
            settings = getattr(self.document, 'export_settings', {}) or {}
            return bool(settings.get('freeze_preview_during_export', False))
        except Exception:
            return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 绘制画布背景（棋盘格背景表示透明区域）
        self.draw_transparency_checkerboard(painter)

        # 如果文档没有设置尺寸，显示提示信息
        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            painter.setPen(QColor(CursorDarkTheme.TEXT_SECONDARY))
            painter.drawText(self.rect(), Qt.AlignCenter, "请创建新画布或打开现有文档")
            return

        pixmap = self._get_cached_composition_pixmap()
        if pixmap:
            canvas_rect = self.get_canvas_rect()
            if not canvas_rect:
                return
            canvas_width = canvas_rect.width()
            canvas_height = canvas_rect.height()
            center_x = canvas_rect.x()
            center_y = canvas_rect.y()

            # 绘制缩放后的图像（优先使用缩放缓存）
            scaled_pixmap = self._get_scaled_composition_pixmap(pixmap, canvas_width, canvas_height)
            if scaled_pixmap:
                painter.drawPixmap(center_x, center_y, scaled_pixmap)

            # 绘制画布边框
            painter.setPen(QPen(QColor(CursorDarkTheme.BORDER_SECONDARY), 1, Qt.SolidLine))
            painter.drawRect(center_x, center_y, canvas_width, canvas_height)
            self._draw_guides(painter, canvas_rect)

            # 如果有选中的图层，绘制图层边框和控制点
            if self.document.selected_layer_index >= 0 and self.document.selected_layer_index < len(self.document.layers):
                layer = self.document.layers[self.document.selected_layer_index]

                # 判断是否启用了分身效果（安全地检查属性是否存在）
                is_clone_enabled = (hasattr(layer, 'clone_enabled') and layer.clone_enabled)

                if is_clone_enabled:
                    try:
                        # 获取所有分身位置
                        if hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                            clone_positions = layer.get_clone_positions()
                        else:
                            # 如果方法不存在，则回退到单图层渲染
                            is_clone_enabled = False
                            clone_positions = [(layer.x, layer.y)]

                        fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
                        if fill_enabled:
                            spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                            angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                            mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                            dx = max(1, int(layer.width + spacing))
                            dy = max(1, int(layer.height + spacing))
                            positions = []
                            cx = self.document.canvas_width / 2.0
                            cy = self.document.canvas_height / 2.0
                            base_x = layer.x
                            base_y = layer.y
                            import math
                            angle = math.radians(angle_deg % 360.0)
                            start_y = -layer.height
                            end_y = self.document.canvas_height + layer.height
                            if mode == 'border':
                                # 边框排列：确保四角有元素，行距列距统一
                                positions = []

                                # 获取边距参数
                                margin = int(getattr(layer, 'clone_fill_margin', 0))
                                effective_width = self.document.canvas_width - 2 * margin
                                effective_height = self.document.canvas_height - 2 * margin

                                # 计算每边的元素数量，确保四角都有元素
                                # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                                top_bottom_count = max(2, (effective_width + dx) // dx)  # 至少2个（两角）
                                # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                                left_right_count = max(2, (effective_height + dy) // dy)  # 至少2个（两角）

                                # 计算统一的间距，确保元素均匀分布
                                if top_bottom_count > 1:
                                    top_bottom_spacing = (effective_width - layer.width) / (top_bottom_count - 1)
                                else:
                                    top_bottom_spacing = 0

                                if left_right_count > 1:
                                    left_right_spacing = (effective_height - layer.height) / (left_right_count - 1)
                                else:
                                    left_right_spacing = 0

                                # 顶部边缘（包括左上角和右上角）
                                for i in range(top_bottom_count):
                                    x = margin + int(i * top_bottom_spacing)
                                    if x <= self.document.canvas_width - layer.width - margin:  # 确保不超出画布边距范围
                                        positions.append((x, margin))

                                # 底部边缘（包括左下角和右下角）
                                for i in range(top_bottom_count):
                                    x = margin + int(i * top_bottom_spacing)
                                    if x <= self.document.canvas_width - layer.width - margin:  # 确保不超出画布边距范围
                                        positions.append((x, self.document.canvas_height - layer.height - margin))

                                # 左侧边缘（不包括已经放置的角落元素）
                                for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                    y = margin + int(i * left_right_spacing)
                                    if margin < y < self.document.canvas_height - layer.height - margin:  # 确保有效位置
                                        positions.append((margin, y))

                                # 右侧边缘（不包括已经放置的角落元素）
                                for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                    y = margin + int(i * left_right_spacing)
                                    if margin < y < self.document.canvas_height - layer.height - margin:  # 确保有效位置
                                        positions.append((self.document.canvas_width - layer.width - margin, y))
                            else:
                                step_y = dy
                                i_row = 0
                                for row_y in range(start_y, end_y + 1, step_y):
                                    offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                                    for col_x in range(-layer.width, self.document.canvas_width + layer.width + 1, dx):
                                        x0 = base_x + col_x + offset
                                        y0 = base_y + row_y
                                        if angle != 0.0:
                                            rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                                            ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                                            x = int(rx)
                                            y = int(ry)
                                        else:
                                            x = x0
                                            y = y0
                                        positions.append((x, y))
                                    i_row += 1
                            clone_positions = positions if positions else clone_positions

                        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                        if mirror_mode and mirror_mode != 'none':
                            positions = clone_positions[:]
                            min_x = min([x for x, _ in positions])
                            max_x = max([x + layer.width for x, _ in positions])
                            min_y = min([y for _, y in positions])
                            max_y = max([y + layer.height for _, y in positions])
                            group_width = max_x - min_x
                            group_height = max_y - min_y
                            mirrored_positions = []
                            if mirror_mode == 'horizontal':
                                mirrored_left = self.document.canvas_width - (min_x + group_width)
                                for cx, cy in positions:
                                    offset_x = cx - min_x
                                    mirrored_positions.append((mirrored_left + offset_x, cy))
                            elif mirror_mode == 'vertical':
                                mirrored_top = self.document.canvas_height - (min_y + group_height)
                                for cx, cy in positions:
                                    offset_y = cy - min_y
                                    mirrored_positions.append((cx, mirrored_top + offset_y))
                            clone_positions = clone_positions + mirrored_positions

                        # 绘制每个分身的边框和控制点
                        for clone_pos in clone_positions:
                            clone_x, clone_y = clone_pos
                            display_rect = self._get_display_rect_for_layer_position(layer, clone_x, clone_y, canvas_rect)
                            display_x = display_rect.x()
                            display_y = display_rect.y()
                            layer_width = display_rect.width()
                            layer_height = display_rect.height()

                            # 绘制分身边框 - 使用更明显的样式和颜色
                            is_primary = (clone_x == layer.x and clone_y == layer.y)

                            # 清除画刷以防止填充
                            painter.setBrush(Qt.NoBrush)

                            # 根据图层形状绘制对应轮廓，避免双重轮廓问题
                            # 获取图层形状类型
                            if hasattr(layer, 'shape_type'):
                                # 异形图层使用shape_type属性
                                try:
                                    from app.models.layer_properties import ShapeType
                                except ImportError:
                                    from app.models.shaped_layer import ShapeType
                                shape_type = layer.shape_type
                                # 将ShapeType映射到对应的绘制逻辑
                                if shape_type == ShapeType.RECTANGLE:
                                    shape = "rectangle"
                                elif shape_type == ShapeType.CIRCLE:
                                    shape = "circle"
                                elif shape_type == ShapeType.RIGHT_TRAPEZOID:
                                    shape = "right_trapezoid"
                                elif shape_type == ShapeType.PENTAGON:
                                    shape = "pentagon"
                                elif shape_type == ShapeType.HEXAGON:
                                    shape = "hexagon"
                                else:
                                    shape = "rectangle"
                            else:
                                # 普通图层默认为矩形
                                shape = "rectangle"

                            if is_primary:
                                # 主图层（原始位置）使用蓝色边框
                                painter.setPen(QPen(QColor(0, 160, 230), 2, Qt.DashLine))
                            else:
                                # 分身使用淡色边框
                                painter.setPen(QPen(QColor(0, 160, 230, 70), 1, Qt.DotLine))

                            # 根据形状类型绘制对应轮廓
                            if shape == "rectangle":
                                painter.drawPath(self._build_rect_path(layer, display_rect))
                            elif shape == "circle":
                                r = int(min(layer_width, layer_height) / 2)
                                cx = display_x + layer_width // 2
                                cy = display_y + layer_height // 2
                                painter.drawEllipse(QRect(cx - r, cy - r, r * 2, r * 2))
                            elif shape == "right_trapezoid":
                                # 使用图层实际的梯形参数
                                top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                                bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                                slope_side = getattr(layer, 'trapezoid_slope_side', 'right')

                                top_width = layer_width * top_width_percent
                                bottom_width = layer_width * bottom_width_percent

                                if slope_side == "right":
                                    # 斜边在右侧
                                    points = [
                                        QPoint(int(display_x), display_y),  # 左上
                                        QPoint(int(display_x + top_width), display_y),  # 右上
                                        QPoint(int(display_x + bottom_width), display_y + layer_height),  # 右下
                                        QPoint(int(display_x), display_y + layer_height)  # 左下
                                    ]
                                else:
                                    # 斜边在左侧
                                    points = [
                                        QPoint(int(display_x + layer_width - top_width), display_y),  # 左上
                                        QPoint(int(display_x + layer_width), display_y),  # 右上
                                        QPoint(int(display_x + layer_width), display_y + layer_height),  # 右下
                                        QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height)  # 左下
                                    ]
                                painter.drawPolygon(points)
                            elif shape == "pentagon":
                                import math
                                cx = display_x + layer_width / 2
                                cy = display_y + layer_height / 2
                                r = min(layer_width, layer_height) / 2 * 0.9
                                pts = []
                                for i in range(5):
                                    a = 2 * math.pi * i / 5 - math.pi / 2
                                    x = int(cx + r * math.cos(a))
                                    y = int(cy + r * math.sin(a))
                                    pts.append(QPoint(x, y))
                                painter.drawPolygon(pts)
                            elif shape == "hexagon":
                                import math
                                cx = display_x + layer_width / 2
                                cy = display_y + layer_height / 2
                                r = min(layer_width, layer_height) / 2 * 0.9
                                pts = []
                                for i in range(6):
                                    a = 2 * math.pi * i / 6
                                    x = int(cx + r * math.cos(a))
                                    y = int(cy + r * math.sin(a))
                                    pts.append(QPoint(x, y))
                                painter.drawPolygon(pts)

                            # 为主分身绘制控制点
                            if is_primary and not layer.locked and not layer.use_original_size:
                                # 绘制图层控制点
                                painter.setBrush(QBrush(QColor(0, 160, 230)))
                                handle_size = 8
                                handle_points = []

                                # 根据形状类型绘制对应的控制点
                                if shape == "rectangle":
                                    # 矩形：四角和四边中点
                                    handle_points = [
                                        QPoint(display_x, display_y),  # 左上
                                        QPoint(display_x + layer_width // 2, display_y),  # 上中
                                        QPoint(display_x + layer_width, display_y),  # 右上
                                        QPoint(display_x + layer_width, display_y + layer_height // 2),  # 右中
                                        QPoint(display_x + layer_width, display_y + layer_height),  # 右下
                                        QPoint(display_x + layer_width // 2, display_y + layer_height),  # 下中
                                        QPoint(display_x, display_y + layer_height),  # 左下
                                        QPoint(display_x, display_y + layer_height // 2),  # 左中
                                    ]
                                elif shape == "circle":
                                    # 圆形：四个方向点
                                    r = int(min(layer_width, layer_height) / 2)
                                    cx = display_x + layer_width // 2
                                    cy = display_y + layer_height // 2
                                    handle_points = [
                                        QPoint(cx, display_y),  # 上
                                        QPoint(display_x + layer_width, cy),  # 右
                                        QPoint(cx, display_y + layer_height),  # 下
                                        QPoint(display_x, cy),  # 左
                                    ]
                                elif shape == "right_trapezoid":
                                    # 直角梯形：使用图层真实参数
                                    top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                                    bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                                    slope_side = getattr(layer, 'trapezoid_slope_side', 'right')

                                    top_width = layer_width * top_width_percent
                                    bottom_width = layer_width * bottom_width_percent

                                    if slope_side == "right":
                                        handle_points = [
                                            QPoint(int(display_x), display_y),  # 左上
                                            QPoint(int(display_x + top_width), display_y),  # 右上
                                            QPoint(int(display_x + bottom_width), display_y + layer_height),  # 右下
                                            QPoint(int(display_x), display_y + layer_height),  # 左下
                                        ]
                                    else:
                                        handle_points = [
                                            QPoint(int(display_x + layer_width - top_width), display_y),  # 左上
                                            QPoint(int(display_x + layer_width), display_y),  # 右上
                                            QPoint(int(display_x + layer_width), display_y + layer_height),  # 右下
                                            QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height),  # 左下
                                        ]
                                elif shape == "pentagon":
                                    # 正五边形：五个顶点
                                    import math
                                    cx = display_x + layer_width / 2
                                    cy = display_y + layer_height / 2
                                    r = min(layer_width, layer_height) / 2 * 0.9
                                    for i in range(5):
                                        a = 2 * math.pi * i / 5 - math.pi / 2
                                        x = int(cx + r * math.cos(a))
                                        y = int(cy + r * math.sin(a))
                                        handle_points.append(QPoint(x, y))
                                elif shape == "hexagon":
                                    # 正六边形：六个顶点
                                    import math
                                    cx = display_x + layer_width / 2
                                    cy = display_y + layer_height / 2
                                    r = min(layer_width, layer_height) / 2 * 0.9
                                    for i in range(6):
                                        a = 2 * math.pi * i / 6
                                        x = int(cx + r * math.cos(a))
                                        y = int(cy + r * math.sin(a))
                                        handle_points.append(QPoint(x, y))

                                for point in handle_points:
                                    painter.drawRect(point.x() - handle_size // 2, point.y() - handle_size // 2,
                                                       handle_size, handle_size)
                                self._draw_corner_radius_handle(painter, layer, display_rect)
                    except Exception as e:
                        print(f"绘制分身出错: {e}")
                        is_clone_enabled = False

                if not is_clone_enabled:
                    painter.setBrush(Qt.NoBrush)
                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    positions = [(layer.x, layer.y)]
                    if mirror_mode and mirror_mode != 'none':
                        if mirror_mode == 'horizontal':
                            mx = self.document.canvas_width - (layer.x + layer.width)
                            my = layer.y
                            positions.append((mx, my))
                        elif mirror_mode == 'vertical':
                            mx = layer.x
                            my = self.document.canvas_height - (layer.y + layer.height)
                            positions.append((mx, my))

                    for px, py in positions:
                        display_rect = self._get_display_rect_for_layer_position(layer, px, py, canvas_rect)
                        display_x = display_rect.x()
                        display_y = display_rect.y()
                        layer_width = display_rect.width()
                        layer_height = display_rect.height()

                        if hasattr(layer, 'shape_type'):
                            shape_type = layer.shape_type
                            from app.models.layer_properties import ShapeType
                            if shape_type == ShapeType.RECTANGLE:
                                shape = "rectangle"
                            elif shape_type == ShapeType.CIRCLE:
                                shape = "circle"
                            elif shape_type == ShapeType.RIGHT_TRAPEZOID:
                                shape = "right_trapezoid"
                            elif shape_type == ShapeType.PENTAGON:
                                shape = "pentagon"
                            elif shape_type == ShapeType.HEXAGON:
                                shape = "hexagon"
                            else:
                                shape = "rectangle"
                        else:
                            shape = "rectangle"

                        is_primary = (px == layer.x and py == layer.y)
                        if is_primary:
                            painter.setPen(QPen(QColor(0, 160, 230), 2, Qt.DashLine))
                        else:
                            painter.setPen(QPen(QColor(0, 160, 230, 70), 1, Qt.DotLine))

                        if shape == "rectangle":
                            painter.drawPath(self._build_rect_path(layer, display_rect))
                        elif shape == "circle":
                            r = int(min(layer_width, layer_height) / 2)
                            cx = display_x + layer_width // 2
                            cy = display_y + layer_height // 2
                            painter.drawEllipse(QRect(cx - r, cy - r, r * 2, r * 2))
                        elif shape == "right_trapezoid":
                            top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                            bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                            slope_side = getattr(layer, 'trapezoid_slope_side', 'right')
                            top_width = layer_width * top_width_percent
                            bottom_width = layer_width * bottom_width_percent
                            if slope_side == "right":
                                points = [
                                    QPoint(int(display_x), display_y),
                                    QPoint(int(display_x + top_width), display_y),
                                    QPoint(int(display_x + bottom_width), display_y + layer_height),
                                    QPoint(int(display_x), display_y + layer_height)
                                ]
                            else:
                                points = [
                                    QPoint(int(display_x + layer_width - top_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y + layer_height),
                                    QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height)
                                ]
                            painter.drawPolygon(points)
                        elif shape == "pentagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            pts = []
                            for i in range(5):
                                a = 2 * math.pi * i / 5 - math.pi / 2
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                pts.append(QPoint(x, y))
                            painter.drawPolygon(pts)
                        elif shape == "hexagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            pts = []
                            for i in range(6):
                                a = 2 * math.pi * i / 6
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                pts.append(QPoint(x, y))
                            painter.drawPolygon(pts)

                    if is_primary and not layer.locked and not layer.use_original_size:
                        painter.setBrush(QBrush(QColor(0, 160, 230)))
                        handle_size = 8
                        handle_points = []
                        if shape == "rectangle":
                            handle_points = [
                                QPoint(display_x, display_y),
                                QPoint(display_x + layer_width // 2, display_y),
                                QPoint(display_x + layer_width, display_y),
                                QPoint(display_x + layer_width, display_y + layer_height // 2),
                                QPoint(display_x + layer_width, display_y + layer_height),
                                QPoint(display_x + layer_width // 2, display_y + layer_height),
                                QPoint(display_x, display_y + layer_height),
                                QPoint(display_x, display_y + layer_height // 2),
                            ]
                        elif shape == "circle":
                            r = int(min(layer_width, layer_height) / 2)
                            cx = display_x + layer_width // 2
                            cy = display_y + layer_height // 2
                            handle_points = [
                                QPoint(cx, display_y),
                                QPoint(display_x + layer_width, cy),
                                QPoint(cx, display_y + layer_height),
                                QPoint(display_x, cy),
                            ]
                        elif shape == "right_trapezoid":
                            top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
                            bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
                            slope_side = getattr(layer, 'trapezoid_slope_side', 'right')
                            top_width = layer_width * top_width_percent
                            bottom_width = layer_width * bottom_width_percent
                            if slope_side == "right":
                                handle_points = [
                                    QPoint(int(display_x), display_y),
                                    QPoint(int(display_x + top_width), display_y),
                                    QPoint(int(display_x + bottom_width), display_y + layer_height),
                                    QPoint(int(display_x), display_y + layer_height),
                                ]
                            else:
                                handle_points = [
                                    QPoint(int(display_x + layer_width - top_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y),
                                    QPoint(int(display_x + layer_width), display_y + layer_height),
                                    QPoint(int(display_x + layer_width - bottom_width), display_y + layer_height),
                                ]
                        elif shape == "pentagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            for i in range(5):
                                a = 2 * math.pi * i / 5 - math.pi / 2
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                handle_points.append(QPoint(x, y))
                        elif shape == "hexagon":
                            import math
                            cx = display_x + layer_width / 2
                            cy = display_y + layer_height / 2
                            r = min(layer_width, layer_height) / 2 * 0.9
                            for i in range(6):
                                a = 2 * math.pi * i / 6
                                x = int(cx + r * math.cos(a))
                                y = int(cy + r * math.sin(a))
                                handle_points.append(QPoint(x, y))
                        for point in handle_points:
                            painter.drawRect(point.x() - handle_size // 2, point.y() - handle_size // 2, handle_size, handle_size)
                        self._draw_corner_radius_handle(painter, layer, display_rect)

                        if bool(getattr(layer, 'vector_path_enabled', False)):
                            mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
                            if mode == 'bezier':
                                bez_nodes = self._get_vector_bezier_nodes_screen(layer, display_rect)
                                painter.setPen(QPen(QColor(255, 210, 120), 1, Qt.SolidLine))
                                for n in bez_nodes:
                                    painter.drawLine(n['anchor'], n['in'])
                                    painter.drawLine(n['anchor'], n['out'])
                                    painter.setBrush(QBrush(QColor(255, 220, 120)))
                                    painter.drawRect(n['in'].x() - 4, n['in'].y() - 4, 8, 8)
                                    painter.drawRect(n['out'].x() - 4, n['out'].y() - 4, 8, 8)
                                    painter.setBrush(QBrush(QColor(255, 170, 0)))
                                    painter.drawEllipse(n['anchor'].x() - 5, n['anchor'].y() - 5, 10, 10)
                            else:
                                node_points = self._get_vector_node_points(layer, display_rect)
                                painter.setBrush(QBrush(QColor(255, 170, 0)))
                                painter.setPen(QPen(QColor(255, 210, 120), 1, Qt.SolidLine))
                                node_size = 10
                                for np in node_points:
                                    painter.drawEllipse(np.x() - node_size // 2, np.y() - node_size // 2, node_size, node_size)

        # 绘制拖拽交互增强效果
        self._draw_drag_enhancements(painter)
        self._draw_rulers(painter)

    def _invalidate_composition_cache(self):
        """文档发生变化时使合成图缓存失效"""
        # 导出高负载模式下允许冻结预览，避免导出线程与预览线程争用
        if self._is_export_preview_frozen():
            if self._composition_pixmap_cache is None:
                self._composition_cache_valid = False
            self._invalidate_scaled_pixmap_cache()
            return

        # 优先基于变更上下文判断是否需要失效合成缓存
        # 非视觉字段（如名称、锁定）不触发合成图重建，只更新覆盖层即可
        context = None
        if hasattr(self.document, "get_change_context"):
            try:
                context = self.document.get_change_context(max_age_ms=1200)
            except Exception:
                context = None

        if context:
            fields = set(context.get("fields", []) or [])
            non_visual_fields = {"name", "lock", "selection"}
            if fields and fields.issubset(non_visual_fields):
                self._invalidate_scaled_pixmap_cache()
                return

        self._composition_cache_valid = False
        self._composition_pixmap_cache = None
        self._invalidate_scaled_pixmap_cache()

    def _invalidate_scaled_pixmap_cache(self):
        """使缩放后的QPixmap缓存失效"""
        self._scaled_composition_pixmap_cache = None
        self._scaled_composition_cache_key = None

    def _get_scaled_composition_pixmap(self, source_pixmap, target_width, target_height):
        """获取按当前缩放尺寸缓存的QPixmap"""
        if source_pixmap is None:
            return None

        if target_width <= 0 or target_height <= 0:
            return source_pixmap

        cache_key = (
            int(source_pixmap.cacheKey()),
            int(target_width),
            int(target_height),
        )
        if self._scaled_composition_pixmap_cache is not None and self._scaled_composition_cache_key == cache_key:
            return self._scaled_composition_pixmap_cache

        scaled = source_pixmap.scaled(
            target_width,
            target_height,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation
        )
        self._scaled_composition_pixmap_cache = scaled
        self._scaled_composition_cache_key = cache_key
        return scaled

    def _get_cached_composition_pixmap(self):
        """获取合成图QPixmap缓存，必要时重新生成"""
        self._sync_panel_interaction_state()
        force_refresh = bool(getattr(self.document, '_needs_cache_refresh', False) or self._force_high_quality_refresh)
        if self._composition_cache_valid and self._composition_pixmap_cache is not None and not force_refresh:
            return self._composition_pixmap_cache
        if self._is_export_preview_frozen() and self._composition_pixmap_cache is not None:
            return self._composition_pixmap_cache

        # 绘制合成图像 - 使用真正的快速渲染器
        try:
            from app.utils.fast_renderer import get_global_fast_renderer
            fast_renderer = get_global_fast_renderer()
            interactive_low_quality = bool(
                self._interactive_low_quality_active
                and not self._force_high_quality_refresh
                and (
                    self.is_dragging_layer
                    or self.is_resizing
                    or self.is_dragging_corner_radius
                    or self._panel_interaction_active
                )
            )
            active_layer_index = self._get_interaction_active_layer_index()
            if force_refresh:
                self.document._needs_cache_refresh = False
            if interactive_low_quality and active_layer_index >= 0:
                composition = fast_renderer.render_preview_incremental(
                    self.document,
                    active_layer_index=active_layer_index,
                    force_refresh=force_refresh,
                    interactive_low_quality=True
                )
            else:
                composition = fast_renderer.render_preview(
                    self.document,
                    force_refresh=force_refresh,
                    interactive_low_quality=interactive_low_quality
                )
            if self._force_high_quality_refresh:
                self._force_high_quality_refresh = False
        except Exception as e:
            # 后备方案：使用快速预览模式渲染
            print(f"[画布] 快速渲染失败，使用预览模式回退: {e}")
            composition = self.document.render_composition()

        if not composition:
            return None

        # 将PIL图像转换为QImage
        qimage = None
        try:
            from PIL import ImageQt
            qimage = ImageQt.toqimage(composition)
        except Exception as e:
            print(f"ImageQt转换失败，尝试手动转换: {e}")
            try:
                img_data = composition.convert("RGBA").tobytes("raw", "RGBA")
                qimage = QImage(img_data, composition.width, composition.height,
                               composition.width * 4, QImage.Format_RGBA8888)
            except Exception as e:
                print(f"图像转换失败: {e}")
                img_data = composition.tobytes("raw", "RGBA")
                qimage = QImage(img_data, composition.width, composition.height,
                              QImage.Format_RGBA8888)

        self._composition_pixmap_cache = QPixmap.fromImage(qimage)
        self._composition_cache_valid = True
        return self._composition_pixmap_cache

    def _get_interaction_active_layer_index(self) -> int:
        """获取当前交互中的活动图层索引；无活动图层返回 -1。"""
        if self.is_dragging_layer and self.dragging_layer_index >= 0:
            return int(self.dragging_layer_index)
        if self.is_resizing and self.document.selected_layer_index >= 0:
            return int(self.document.selected_layer_index)
        if self.is_dragging_corner_radius and self.document.selected_layer_index >= 0:
            return int(self.document.selected_layer_index)
        if self._panel_interaction_active and self._panel_interaction_layer_index >= 0:
            return int(self._panel_interaction_layer_index)
        return -1

    def _sync_panel_interaction_state(self):
        """根据属性面板高频参数变更上下文，驱动增量渲染会话。"""
        if not hasattr(self.document, "get_change_context"):
            return
        try:
            ctx = self.document.get_change_context(max_age_ms=220)
        except Exception:
            ctx = None
        if not ctx or ctx.get("source") != "layer_properties_panel":
            return

        layer_index = int(ctx.get("layer_index", -1))
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        fields = set(ctx.get("fields", []) or [])
        if fields and fields.isdisjoint(self._panel_interaction_fields):
            return

        self._panel_interaction_active = True
        self._panel_interaction_layer_index = layer_index
        self._interactive_low_quality_active = True
        # 持续收到高频参数变化时会不断重置计时，停止后自动回填高质量
        self._panel_interaction_idle_timer.start(160)

    def _on_panel_interaction_idle(self):
        """属性面板高频交互停止，触发高质量回填。"""
        if not self._panel_interaction_active:
            return
        self._panel_interaction_active = False
        self._panel_interaction_layer_index = -1
        self._request_high_quality_refresh()

    def _draw_guides(self, painter, canvas_rect):
        """绘制参考线"""
        if not self.show_guides:
            return

        for i, gx in enumerate(self.vertical_guides):
            is_active = (
                (self._is_dragging_guide and self._dragging_guide_orientation == "vertical" and self._dragging_guide_index == i) or
                (not self._is_dragging_guide and self._selected_guide_orientation == "vertical" and self._selected_guide_index == i)
            )
            painter.setPen(QPen(QColor(255, 160, 60, 230) if is_active else QColor(0, 170, 255, 220), 1, Qt.SolidLine if is_active else Qt.DashLine))
            x = canvas_rect.x() + int(gx * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())

        for i, gy in enumerate(self.horizontal_guides):
            is_active = (
                (self._is_dragging_guide and self._dragging_guide_orientation == "horizontal" and self._dragging_guide_index == i) or
                (not self._is_dragging_guide and self._selected_guide_orientation == "horizontal" and self._selected_guide_index == i)
            )
            painter.setPen(QPen(QColor(255, 160, 60, 230) if is_active else QColor(0, 170, 255, 220), 1, Qt.SolidLine if is_active else Qt.DashLine))
            y = canvas_rect.y() + int(gy * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        if self._is_dragging_guide and self._guide_overlay_text:
            self._draw_guide_overlay(painter, self._guide_overlay_text, self._guide_overlay_pos)
        if self._snap_feedback_active:
            self._draw_snap_feedback(painter, canvas_rect)

    def _draw_guide_overlay(self, painter, text, pos):
        """拖拽参考线时显示当前位置参数"""
        metrics = painter.fontMetrics()
        w = metrics.horizontalAdvance(text) + 12
        h = metrics.height() + 8
        x = min(max(0, pos.x() + 12), max(0, self.width() - w))
        y = min(max(0, pos.y() + 12), max(0, self.height() - h))
        rect = QRect(x, y, w, h)
        painter.fillRect(rect, QColor(32, 32, 32, 220))
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawRect(rect)
        painter.drawText(rect.adjusted(6, 4, -6, -4), Qt.AlignLeft | Qt.AlignVCenter, text)

    def _draw_snap_feedback(self, painter, canvas_rect):
        """绘制吸附成功反馈：高亮参考线 + SNAP 文本"""
        highlight_pen = QPen(QColor(255, 180, 40, 255), 2, Qt.SolidLine)
        painter.setPen(highlight_pen)
        if self._snap_feedback_vertical is not None:
            x = canvas_rect.x() + int(self._snap_feedback_vertical * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())
        if self._snap_feedback_horizontal is not None:
            y = canvas_rect.y() + int(self._snap_feedback_horizontal * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        if self._snap_feedback_text:
            self._draw_guide_overlay(painter, self._snap_feedback_text, self._snap_feedback_pos)

    def _draw_rulers(self, painter):
        """绘制标尺"""
        if not self.show_rulers:
            return

        ruler = self._get_ruler_thickness()
        rect = self.rect()
        canvas_rect = self.get_canvas_rect()

        painter.fillRect(0, 0, rect.width(), ruler, QColor(CursorDarkTheme.BACKGROUND_TITLEBAR))
        painter.fillRect(0, 0, ruler, rect.height(), QColor(CursorDarkTheme.BACKGROUND_TITLEBAR))
        painter.fillRect(0, 0, ruler, ruler, QColor(CursorDarkTheme.BACKGROUND_SECONDARY))
        painter.setPen(QPen(QColor(CursorDarkTheme.BORDER_PRIMARY), 1))
        painter.drawLine(ruler, 0, rect.width(), 0)
        painter.drawLine(0, ruler, 0, rect.height())

        if not canvas_rect:
            return

        # 动态刻度步进：尽量保证大刻度约 80~120 像素
        base_steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
        unit_per_big = 100
        for s in base_steps:
            if s * self.zoom_factor >= 80:
                unit_per_big = s
                break
        unit_per_minor = max(1, unit_per_big // 10)

        # 顶部水平标尺
        painter.setPen(QPen(QColor(CursorDarkTheme.TEXT_MUTED), 1))
        start_x = -canvas_rect.x() / self.zoom_factor
        end_x = (self.width() - canvas_rect.x()) / self.zoom_factor
        minor_start = int(start_x // unit_per_minor) * unit_per_minor
        x_val = minor_start
        while x_val <= end_x:
            x = canvas_rect.x() + int(x_val * self.zoom_factor)
            if x_val % unit_per_big == 0:
                painter.drawLine(x, ruler - 12, x, ruler)
                painter.drawText(x + 2, 11, f"{int(x_val)}")
            elif x_val % (unit_per_big // 2 if unit_per_big >= 2 else 1) == 0:
                painter.drawLine(x, ruler - 8, x, ruler)
            else:
                painter.drawLine(x, ruler - 5, x, ruler)
            x_val += unit_per_minor

        # 左侧垂直标尺
        start_y = -canvas_rect.y() / self.zoom_factor
        end_y = (self.height() - canvas_rect.y()) / self.zoom_factor
        minor_start = int(start_y // unit_per_minor) * unit_per_minor
        y_val = minor_start
        while y_val <= end_y:
            y = canvas_rect.y() + int(y_val * self.zoom_factor)
            if y_val % unit_per_big == 0:
                painter.drawLine(ruler - 12, y, ruler, y)
                painter.drawText(2, y - 2, f"{int(y_val)}")
            elif y_val % (unit_per_big // 2 if unit_per_big >= 2 else 1) == 0:
                painter.drawLine(ruler - 8, y, ruler, y)
            else:
                painter.drawLine(ruler - 5, y, ruler, y)
            y_val += unit_per_minor

    def _draw_drag_enhancements(self, painter):
        """绘制拖拽交互增强效果"""
        if not self.is_dragging_layer or self.dragging_layer_index < 0:
            return

        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return

        layer = self.document.layers[self.dragging_layer_index]

        # 1. 绘制拖拽边界提示
        if self.show_drag_bounds:
            self._draw_drag_bounds(painter, canvas_rect, layer)

        # 2. 绘制拖拽预览（幽灵图层）
        if self.drag_preview_enabled:
            self._draw_drag_preview(painter, canvas_rect, layer)

    def _draw_drag_bounds(self, painter, canvas_rect, layer):
        """绘制拖拽边界提示"""
        # 计算图层在画布中的边界
        layer_right = layer.x + layer.width
        layer_bottom = layer.y + layer.height

        # 保存当前画笔
        original_pen = painter.pen()

        # 设置边界提示样式
        bound_pen = QPen(QColor(255, 100, 100, 150), 2, Qt.DashLine)
        painter.setPen(bound_pen)

        # 绘制边界警告线
        margin = 10  # 边界警告距离

        # 左边界警告
        if layer.x < margin:
            x = canvas_rect.x() + int(margin * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())

        # 右边界警告
        if layer_right > self.document.canvas_width - margin:
            x = canvas_rect.right() - int(margin * self.zoom_factor)
            painter.drawLine(x, canvas_rect.y(), x, canvas_rect.bottom())

        # 上边界警告
        if layer.y < margin:
            y = canvas_rect.y() + int(margin * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        # 下边界警告
        if layer_bottom > self.document.canvas_height - margin:
            y = canvas_rect.bottom() - int(margin * self.zoom_factor)
            painter.drawLine(canvas_rect.x(), y, canvas_rect.right(), y)

        # 恢复原始画笔
        painter.setPen(original_pen)

    def _draw_drag_preview(self, painter, canvas_rect, layer):
        """绘制拖拽预览（幽灵图层）"""
        # 计算图层当前位置
        layer_x = canvas_rect.x() + int(layer.x * self.zoom_factor)
        layer_y = canvas_rect.y() + int(layer.y * self.zoom_factor)
        layer_width = int(layer.width * self.zoom_factor)
        layer_height = int(layer.height * self.zoom_factor)

        # 保存当前状态
        original_pen = painter.pen()
        original_brush = painter.brush()

        # 设置预览样式
        preview_color = QColor(0, 160, 230, int(255 * self.drag_preview_opacity))
        painter.setPen(QPen(preview_color, 2, Qt.SolidLine))
        painter.setBrush(QBrush(QColor(0, 160, 230, int(100 * self.drag_preview_opacity))))

        # 获取图层形状类型
        if hasattr(layer, 'shape_type'):
            # 异形图层使用shape_type属性
            try:
                from app.models.layer_properties import ShapeType
            except ImportError:
                from app.models.shaped_layer import ShapeType
            shape_type = layer.shape_type
            # 将ShapeType映射到对应的绘制逻辑
            if shape_type == ShapeType.RECTANGLE:
                shape = "rectangle"
            elif shape_type == ShapeType.CIRCLE:
                shape = "circle"
            elif shape_type == ShapeType.RIGHT_TRAPEZOID:
                shape = "right_trapezoid"
            elif shape_type == ShapeType.PENTAGON:
                shape = "pentagon"
            elif shape_type == ShapeType.HEXAGON:
                shape = "hexagon"
            else:
                shape = "rectangle"
        else:
            # 普通图层默认为矩形
            shape = "rectangle"

        if shape == "rectangle":
            painter.drawRect(layer_x, layer_y, layer_width, layer_height)
        elif shape == "circle":
            r = int(min(layer_width, layer_height) / 2)
            cx = layer_x + layer_width // 2
            cy = layer_y + layer_height // 2
            painter.drawEllipse(QRect(cx - r, cy - r, r * 2, r * 2))
        elif shape == "right_trapezoid":
            # 使用图层实际的梯形参数
            top_width_percent = getattr(layer, 'trapezoid_top_width', 100) / 100
            bottom_width_percent = getattr(layer, 'trapezoid_bottom_width', 100) / 100
            slope_side = getattr(layer, 'trapezoid_slope_side', 'right')

            top_width = int(layer_width * top_width_percent)
            bottom_width = int(layer_width * bottom_width_percent)

            if slope_side == "right":
                # 斜边在右侧
                points = [
                    QPoint(int(layer_x), int(layer_y)),  # 左上
                    QPoint(int(layer_x + top_width), int(layer_y)),  # 右上
                    QPoint(int(layer_x + bottom_width), int(layer_y + layer_height)),  # 右下
                    QPoint(int(layer_x), int(layer_y + layer_height))  # 左下
                ]
            else:
                # 斜边在左侧
                points = [
                    QPoint(int(layer_x + layer_width - top_width), int(layer_y)),  # 左上
                    QPoint(int(layer_x + layer_width), int(layer_y)),  # 右上
                    QPoint(int(layer_x + layer_width), int(layer_y + layer_height)),  # 右下
                    QPoint(int(layer_x + layer_width - bottom_width), int(layer_y + layer_height))  # 左下
                ]
            painter.drawPolygon(points)
        elif shape == "pentagon" or shape == "hexagon":
            import math
            n = 5 if shape == "pentagon" else 6
            cx = layer_x + layer_width / 2
            cy = layer_y + layer_height / 2
            r = min(layer_width, layer_height) / 2 * 0.9
            pts = []
            for i in range(n):
                a = 2 * math.pi * i / n - (math.pi / 2 if shape == "pentagon" else 0)
                x = int(cx + r * math.cos(a))
                y = int(cy + r * math.sin(a))
                pts.append(QPoint(x, y))
            painter.drawPolygon(pts)

        # 绘制拖拽方向指示器
        self._draw_drag_direction_indicator(painter, layer_x, layer_y, layer_width, layer_height)

        # 恢复原始状态
        painter.setPen(original_pen)
        painter.setBrush(original_brush)

    def _draw_drag_direction_indicator(self, painter, x, y, width, height):
        """绘制拖拽方向指示器"""
        if not hasattr(self, 'layer_drag_start') or not self.layer_drag_start:
            return

        # 计算拖拽方向
        if hasattr(self, '_last_mouse_pos'):
            current_pos = self._last_mouse_pos
        else:
            return

        drag_start = self.layer_drag_start
        delta_x = current_pos.x() - drag_start.x()
        delta_y = current_pos.y() - drag_start.y()

        # 如果移动距离太小，不显示方向指示器
        if abs(delta_x) < 5 and abs(delta_y) < 5:
            return

        # 计算图层中心点
        center_x = x + width // 2
        center_y = y + height // 2

        # 绘制方向箭头
        arrow_length = 30
        arrow_color = QColor(255, 255, 0, 200)
        painter.setPen(QPen(arrow_color, 3, Qt.SolidLine))

        # 计算箭头方向
        import math
        angle = math.atan2(delta_y, delta_x)
        end_x = center_x + int(arrow_length * math.cos(angle))
        end_y = center_y + int(arrow_length * math.sin(angle))

        # 绘制箭头主线
        painter.drawLine(center_x, center_y, end_x, end_y)

        # 绘制箭头头部
        arrow_head_length = 10
        arrow_head_angle = math.pi / 6  # 30度

        # 左侧箭头线
        left_x = end_x - int(arrow_head_length * math.cos(angle - arrow_head_angle))
        left_y = end_y - int(arrow_head_length * math.sin(angle - arrow_head_angle))
        painter.drawLine(end_x, end_y, left_x, left_y)

        # 右侧箭头线
        right_x = end_x - int(arrow_head_length * math.cos(angle + arrow_head_angle))
        right_y = end_y - int(arrow_head_length * math.sin(angle + arrow_head_angle))
        painter.drawLine(end_x, end_y, right_x, right_y)

    def _clear_drag_state(self):
        """清理所有拖拽相关状态"""
        self.drag_ghost_layer = None
        self._last_mouse_pos = None
        self.potential_drag = False
        self.drag_start_pos = None
        self._interactive_low_quality_active = False

        # 恢复正常光标
        if not self.temp_hand_mode:
            self.setCursor(Qt.ArrowCursor)

    def draw_transparency_checkerboard(self, painter):
        """绘制表示透明区域的棋盘格背景"""

        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            return

        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return

        # 使用缓存图案平铺，避免每帧双层循环 fillRect
        self._ensure_checkerboard_cache()
        if self._checkerboard_cache:
            painter.drawTiledPixmap(canvas_rect, self._checkerboard_cache)

    def _get_ruler_thickness(self):
        return self._ruler_size if self.show_rulers else 0

    def _ensure_checkerboard_cache(self):
        """确保棋盘格缓存已创建"""
        cache_size = QSize(self._checkerboard_cell_size * 2, self._checkerboard_cell_size * 2)
        if self._checkerboard_cache and self._checkerboard_cache_size == cache_size:
            return

        pixmap = QPixmap(cache_size)
        pixmap.fill(Qt.transparent)
        cache_painter = QPainter(pixmap)
        dark = QColor(180, 180, 180)
        light = QColor(220, 220, 220)
        cell = self._checkerboard_cell_size
        cache_painter.fillRect(0, 0, cell, cell, light)
        cache_painter.fillRect(cell, 0, cell, cell, dark)
        cache_painter.fillRect(0, cell, cell, cell, dark)
        cache_painter.fillRect(cell, cell, cell, cell, light)
        cache_painter.end()

        self._checkerboard_cache = pixmap
        self._checkerboard_cache_size = cache_size

    def _schedule_interactive_update(self, require_recompose: bool = False):
        """交互过程按固定帧率触发刷新。
        require_recompose=True: 需要重建合成图（图层几何变化）
        require_recompose=False: 仅视图变化（平移等），不重算合成图
        """
        now_ms = time.time() * 1000.0
        elapsed_ms = now_ms - self._last_interactive_update_ms
        if require_recompose:
            self._interactive_requires_recompose = True
            self._interactive_low_quality_active = True

        if elapsed_ms >= self._interactive_frame_interval_ms:
            self._flush_interactive_update()
            return

        if self._interactive_update_pending:
            return

        self._interactive_update_pending = True
        wait_ms = max(1, int(self._interactive_frame_interval_ms - elapsed_ms))
        self._interactive_update_timer.start(wait_ms)

    def _flush_interactive_update(self):
        """执行一次节流后的交互刷新"""
        self._interactive_update_pending = False
        self._last_interactive_update_ms = time.time() * 1000.0
        if self._is_export_preview_frozen():
            self._interactive_requires_recompose = False
            self._interactive_low_quality_active = False
            self._panel_interaction_active = False
            self._panel_interaction_layer_index = -1
            return
        if self._interactive_requires_recompose:
            # 交互期间只做渲染缓存失效，避免高频 document_changed 触发全局UI负担
            self._invalidate_composition_cache()
        self._interactive_requires_recompose = False
        self.update()

    def _request_high_quality_refresh(self):
        """交互结束后强制回填一帧高质量预览。"""
        self._interactive_low_quality_active = False
        self._force_high_quality_refresh = True
        self._invalidate_composition_cache()
        self.update()

    def get_canvas_rect(self):
        """获取画布在屏幕上的矩形区域"""
        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            return None

        # 计算缩放后的尺寸
        canvas_width = int(self.document.canvas_width * self.zoom_factor)
        canvas_height = int(self.document.canvas_height * self.zoom_factor)
        ruler = self._get_ruler_thickness()

        # 计算画布居中位置
        content_width = max(1, self.width() - ruler)
        content_height = max(1, self.height() - ruler)
        center_x = ruler + max(0, (content_width - canvas_width) // 2) + self.offset.x()
        center_y = ruler + max(0, (content_height - canvas_height) // 2) + self.offset.y()

        return QRect(center_x, center_y, canvas_width, canvas_height)

    def wheelEvent(self, event):
        """处理鼠标滚轮事件实现缩放"""
        delta = event.angleDelta().y()

        # 计算放大或缩小的新缩放因子
        if delta > 0:
            self.zoom_factor *= 1.1  # 放大
        else:
            self.zoom_factor /= 1.1  # 缩小

        # 限制缩放范围
        self.zoom_factor = max(0.1, min(10.0, self.zoom_factor))
        self._invalidate_scaled_pixmap_cache()
        self._persist_view_settings_to_document()

        self.update()

    def get_layer_rect(self, layer_index):
        """获取指定图层在视图中的矩形区域"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return None

        layer = self.document.layers[layer_index]
        if layer is None:
            return None

        # 获取画布矩形
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return None

        expand = self._get_vector_stroke_expand_px(layer)
        # 以图层几何为“矢量容器”，边框按有效渲染边界显示，而不是旧矩形框
        offset_x = int(getattr(layer, "_render_offset_x", -expand))
        offset_y = int(getattr(layer, "_render_offset_y", -expand))
        layer_x = canvas_rect.x() + int((layer.x + offset_x) * self.zoom_factor)
        layer_y = canvas_rect.y() + int((layer.y + offset_y) * self.zoom_factor)
        layer_width = int((layer.width + expand * 2) * self.zoom_factor)
        layer_height = int((layer.height + expand * 2) * self.zoom_factor)

        return QRect(layer_x, layer_y, layer_width, layer_height)

    def _is_vector_container_active(self, layer) -> bool:
        if layer is None:
            return False
        shape_type = getattr(layer, 'shape_type', None)
        if shape_type is not None and hasattr(shape_type, 'value'):
            if str(shape_type.value) != "rectangle":
                return False
        elif shape_type is not None and str(shape_type) != "rectangle":
            return False
        stroke_enabled = bool(getattr(layer, 'stroke_enabled', False)) and int(getattr(layer, 'stroke_width', 0)) > 0
        return bool(
            getattr(layer, 'vector_path_enabled', False)
            or stroke_enabled
            or int(getattr(layer, 'corner_radius', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_tl', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_tr', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_br', 0)) > 0
            or int(getattr(layer, 'vector_corner_radius_bl', 0)) > 0
            or int(getattr(layer, 'stroke_dash_length', 0)) > 0
            or int(getattr(layer, 'stroke_dash_gap', 0)) > 0
            or str(getattr(layer, 'stroke_join', 'miter')) != "miter"
            or str(getattr(layer, 'stroke_cap', 'butt')) != "butt"
        )

    def _get_vector_stroke_expand_px(self, layer) -> int:
        if not self._is_vector_container_active(layer):
            return 0
        if not (bool(getattr(layer, 'stroke_enabled', False)) and int(getattr(layer, 'stroke_width', 0)) > 0):
            return 0
        stroke_w = max(1, int(getattr(layer, 'stroke_width', 1)))
        stroke_type = int(getattr(layer, 'stroke_type', 0))
        if stroke_type == 2:
            return stroke_w
        if stroke_type == 1:
            return (stroke_w + 1) // 2
        return 0

    def _get_display_rect_for_layer_position(self, layer, px: int, py: int, canvas_rect: QRect) -> QRect:
        """给定逻辑位置，返回实际绘制边界矩形（含矢量外扩与偏移）。"""
        expand = self._get_vector_stroke_expand_px(layer)
        default_off_x = -expand if expand > 0 else 0
        default_off_y = -expand if expand > 0 else 0
        off_x = int(getattr(layer, "_render_offset_x", default_off_x))
        off_y = int(getattr(layer, "_render_offset_y", default_off_y))
        w = int(getattr(layer, "width", 0)) + expand * 2
        h = int(getattr(layer, "height", 0)) + expand * 2
        x = canvas_rect.x() + int((int(px) + off_x) * self.zoom_factor)
        y = canvas_rect.y() + int((int(py) + off_y) * self.zoom_factor)
        return QRect(x, y, int(w * self.zoom_factor), int(h * self.zoom_factor))

    def _is_rectangle_shape(self, layer) -> bool:
        """判断图层是否为矩形形状（兼容枚举和值字符串）"""
        shape_type = getattr(layer, 'shape_type', None)
        if shape_type is None:
            return True
        if hasattr(shape_type, 'value'):
            return str(shape_type.value) == "rectangle"
        return str(shape_type) == "rectangle"

    def _build_rect_path(self, layer, rect: QRect) -> QPainterPath:
        """构建矩形图层的矢量路径（支持圆角）"""
        path = QPainterPath()
        if rect.width() <= 0 or rect.height() <= 0:
            return path
        ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
        if bool(getattr(layer, 'vector_path_enabled', False)):
            bezier_nodes = getattr(layer, 'vector_bezier_nodes', []) or []
            mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
            if mode == 'bezier' and len(bezier_nodes) >= 3:
                nodes = self._get_vector_bezier_nodes_screen(layer, rect)
                path.moveTo(nodes[0]['anchor'])
                for i in range(len(nodes)):
                    cur = nodes[i]
                    nxt = nodes[(i + 1) % len(nodes)]
                    path.cubicTo(cur['out'], nxt['in'], nxt['anchor'])
                path.closeSubpath()
                return path
            node_points = self._get_vector_node_points(layer, rect)
            if len(node_points) >= 3:
                path.moveTo(node_points[0])
                for pt in node_points[1:]:
                    path.lineTo(pt)
                path.closeSubpath()
                return path
        from app.utils.vector_layer_geometry import build_vector_outline_points_px

        shape_type_value = str(
            getattr(
                getattr(layer, "shape_type", "rectangle"),
                "value",
                getattr(layer, "shape_type", "rectangle"),
            )
        )
        pts, _ = build_vector_outline_points_px(
            int(getattr(layer, "width", 0) or 1),
            int(getattr(layer, "height", 0) or 1),
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
            shape_type_value,
            int(getattr(layer, "trapezoid_top_width", 100)),
            int(getattr(layer, "trapezoid_bottom_width", 80)),
            str(getattr(layer, "trapezoid_slope_side", "right")),
            float(getattr(layer, "polygon_rotation", 0.0)),
            int(getattr(layer, "polygon_corner_radius", 0)),
        )
        if len(pts) >= 3:
            z = float(self.zoom_factor)
            path.moveTo(
                QPoint(int(ox + pts[0][0] * z), int(oy + pts[0][1] * z))
            )
            for px, py in pts[1:]:
                path.lineTo(QPoint(int(ox + px * z), int(oy + py * z)))
            path.closeSubpath()
        else:
            path.addRect(QRect(int(ox), int(oy), int(getattr(layer, 'width', 0) * self.zoom_factor), int(getattr(layer, 'height', 0) * self.zoom_factor)))
        return path

    def _get_vector_node_points(self, layer, rect: QRect):
        points = getattr(layer, 'vector_path_points', []) or []
        if not points:
            return []
        ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
        result = []
        for pt in points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                px = int(ox + float(pt[0]) * self.zoom_factor)
                py = int(oy + float(pt[1]) * self.zoom_factor)
                result.append(QPoint(px, py))
        return result

    def _get_vector_bezier_nodes_screen(self, layer, rect: QRect):
        nodes = getattr(layer, 'vector_bezier_nodes', []) or []
        ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
        result = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            ax = int(ox + float(n.get('x', 0.0)) * self.zoom_factor)
            ay = int(oy + float(n.get('y', 0.0)) * self.zoom_factor)
            ix = int(ox + float(n.get('in_x', n.get('x', 0.0))) * self.zoom_factor)
            iy = int(oy + float(n.get('in_y', n.get('y', 0.0))) * self.zoom_factor)
            hx = int(ox + float(n.get('out_x', n.get('x', 0.0))) * self.zoom_factor)
            hy = int(oy + float(n.get('out_y', n.get('y', 0.0))) * self.zoom_factor)
            result.append({
                'anchor': QPoint(ax, ay),
                'in': QPoint(ix, iy),
                'out': QPoint(hx, hy),
            })
        return result

    def _get_layer_local_origin_in_rect(self, layer, rect: QRect):
        """把 layer 本地坐标 (0,0) 映射到屏幕坐标；兼容外扩描边偏移。"""
        off_x = float(getattr(layer, '_render_offset_x', 0))
        off_y = float(getattr(layer, '_render_offset_y', 0))
        ox = int(round(rect.x() - off_x * self.zoom_factor))
        oy = int(round(rect.y() - off_y * self.zoom_factor))
        return ox, oy

    def get_vector_node_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1
        layer = self.document.layers[layer_index]
        if layer is None or layer.locked:
            return -1
        if not bool(getattr(layer, 'vector_path_enabled', False)):
            return -1
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1
        handle_size = 10
        half = handle_size // 2
        mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
        if mode == 'bezier':
            anchor_points = [n['anchor'] for n in self._get_vector_bezier_nodes_screen(layer, rect)]
        else:
            anchor_points = self._get_vector_node_points(layer, rect)
        for i, p in enumerate(anchor_points):
            if QRect(p.x() - half, p.y() - half, handle_size, handle_size).contains(pos):
                return i
        return -1

    def get_vector_handle_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1, None
        layer = self.document.layers[layer_index]
        if layer is None or layer.locked:
            return -1, None
        if not bool(getattr(layer, 'vector_path_enabled', False)):
            return -1, None
        if str(getattr(layer, 'vector_path_mode', 'polygon')) != 'bezier':
            return -1, None
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1, None
        nodes = self._get_vector_bezier_nodes_screen(layer, rect)
        handle_size = 8
        half = handle_size // 2
        for i, n in enumerate(nodes):
            for t in ('in', 'out'):
                p = n[t]
                if QRect(p.x() - half, p.y() - half, handle_size, handle_size).contains(pos):
                    return i, t
        return -1, None

    def _distance_point_to_segment(self, p: QPoint, a: QPoint, b: QPoint) -> float:
        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        px, py = p.x(), p.y()
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        seg_len2 = float(vx * vx + vy * vy)
        if seg_len2 <= 1e-6:
            return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / seg_len2))
        proj_x = ax + t * vx
        proj_y = ay + t * vy
        dx = px - proj_x
        dy = py - proj_y
        return (dx * dx + dy * dy) ** 0.5

    def get_vector_segment_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1
        layer = self.document.layers[layer_index]
        if layer is None or not bool(getattr(layer, 'vector_path_enabled', False)):
            return -1
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1
        mode = str(getattr(layer, 'vector_path_mode', 'polygon'))
        closed = bool(getattr(layer, 'vector_path_closed', True))
        if mode == 'bezier':
            nodes = self._get_vector_bezier_nodes_screen(layer, rect)
            anchors = [n['anchor'] for n in nodes]
        else:
            anchors = self._get_vector_node_points(layer, rect)
        if len(anchors) < 2:
            return -1
        seg_count = len(anchors) if closed else len(anchors) - 1
        best_idx = -1
        best_dist = 1e9
        for i in range(seg_count):
            a = anchors[i]
            b = anchors[(i + 1) % len(anchors)]
            d = self._distance_point_to_segment(pos, a, b)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx if best_dist <= 14.0 else -1

    def get_layer_at_position(self, pos):
        """获取鼠标位置所在的图层索引"""
        # 从上到下（从顶层到底层）检查图层
        for i in range(len(self.document.layers) - 1, -1, -1):
            layer = self.document.layers[i]
            if layer is None:
                continue
            if not layer.visible or layer.locked:  # 忽略不可见或锁定的图层
                continue

            # 判断是否启用了分身效果
            is_clone_enabled = (hasattr(layer, 'clone_enabled') and layer.clone_enabled)

            if is_clone_enabled:
                # 先检查原始位置
                rect = self.get_layer_rect(i)
                if rect and self._build_rect_path(layer, rect).contains(pos):
                    return i

                # 如果有分身功能，还需要检查所有分身位置
                try:
                    if hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                        clone_positions = layer.get_clone_positions()

                        # 获取画布矩形
                        canvas_rect = self.get_canvas_rect()
                        if not canvas_rect:
                            continue

                        # 检查每个分身位置
                        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                        positions = clone_positions
                        if mirror_mode and mirror_mode != 'none':
                            base = positions[:]
                            min_x = min([x for x, _ in base])
                            max_x = max([x + layer.width for x, _ in base])
                            min_y = min([y for _, y in base])
                            max_y = max([y + layer.height for _, y in base])
                            group_width = max_x - min_x
                            group_height = max_y - min_y
                            mirrored_positions = []
                            if mirror_mode == 'horizontal':
                                mirrored_left = self.document.canvas_width - (min_x + group_width)
                                for cx, cy in base:
                                    offset_x = cx - min_x
                                    mirrored_positions.append((mirrored_left + offset_x, cy))
                            elif mirror_mode == 'vertical':
                                mirrored_top = self.document.canvas_height - (min_y + group_height)
                                for cx, cy in base:
                                    offset_y = cy - min_y
                                    mirrored_positions.append((cx, mirrored_top + offset_y))
                            positions = positions + mirrored_positions
                        for clone_pos in positions:
                            clone_x, clone_y = clone_pos
                            clone_rect = self._get_display_rect_for_layer_position(layer, clone_x, clone_y, canvas_rect)
                            if self._build_rect_path(layer, clone_rect).contains(pos):
                                return i
                except Exception as e:
                    print(f"检查分身图层点击失败: {e}")
            else:
                # 常规图层
                rect = self.get_layer_rect(i)
                if rect and self._build_rect_path(layer, rect).contains(pos):
                    return i

        return -1  # 没有找到图层

    def get_handle_at_position(self, pos, layer_index):
        """获取鼠标位置所在的控制点索引"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return -1

        layer = self.document.layers[layer_index]
        if layer is None:
            return -1
        if layer.locked or layer.use_original_size:
            return -1  # 锁定的图层或使用原始尺寸的图层不能调整大小
        if self._is_vector_container_active(layer):
            # 矢量容器模式下禁用旧矩形缩放控制点，避免和路径锚点编辑冲突
            return -1

        rect = self.get_layer_rect(layer_index)
        if not rect:
            return -1

        handle_size = 8
        half_handle = handle_size // 2

        # 获取图层形状类型
        if hasattr(layer, 'shape_type'):
            # 异形图层使用shape_type属性
            try:
                from app.models.layer_properties import ShapeType
            except ImportError:
                from app.models.shaped_layer import ShapeType
            shape_type = layer.shape_type
            # 将ShapeType映射到对应的绘制逻辑
            if shape_type == ShapeType.RECTANGLE:
                shape = "rectangle"
            elif shape_type == ShapeType.CIRCLE:
                shape = "circle"
            elif shape_type == ShapeType.RIGHT_TRAPEZOID:
                shape = "right_trapezoid"
            elif shape_type == ShapeType.PENTAGON:
                shape = "pentagon"
            elif shape_type == ShapeType.HEXAGON:
                shape = "hexagon"
            else:
                shape = "rectangle"
        else:
            # 普通图层默认为矩形
            shape = "rectangle"

        if shape == "rectangle":
            handle_points = [
                QPoint(rect.left(), rect.top()),
                QPoint(rect.left() + rect.width() // 2, rect.top()),
                QPoint(rect.right(), rect.top()),
                QPoint(rect.right(), rect.top() + rect.height() // 2),
                QPoint(rect.right(), rect.bottom()),
                QPoint(rect.left() + rect.width() // 2, rect.bottom()),
                QPoint(rect.left(), rect.bottom()),
                QPoint(rect.left(), rect.top() + rect.height() // 2),
            ]
            index_map = list(range(8))
        elif shape == "circle":
            cx = rect.left() + rect.width() // 2
            cy = rect.top() + rect.height() // 2
            handle_points = [
                QPoint(cx, rect.top()),
                QPoint(rect.right(), cy),
                QPoint(cx, rect.bottom()),
                QPoint(rect.left(), cy),
            ]
            index_map = [1, 3, 5, 7]
        elif shape == "right_trapezoid":
            layer_width = rect.width()
            layer_height = rect.height()
            top_width = int(layer_width * 0.7)
            bottom_width = layer_width
            offset = int((bottom_width - top_width) * 0.3)
            handle_points = [
                QPoint(rect.left() + offset, rect.top()),
                QPoint(rect.left() + offset + top_width, rect.top()),
                QPoint(rect.right(), rect.bottom()),
                QPoint(rect.left(), rect.bottom()),
            ]
            index_map = [0, 2, 4, 6]
        elif shape == "pentagon" or shape == "hexagon":
            import math
            n = 5 if shape == "pentagon" else 6
            cx = rect.left() + rect.width() / 2
            cy = rect.top() + rect.height() / 2
            r = min(rect.width(), rect.height()) / 2 * 0.9
            pts = []
            for i in range(n):
                a = 2 * math.pi * i / n - (math.pi / 2 if shape == "pentagon" else 0)
                x = int(cx + r * math.cos(a))
                y = int(cy + r * math.sin(a))
                pts.append(QPoint(x, y))
            handle_points = pts
            index_map = [0, 2, 4, 6][:len(handle_points)]
        else:
            handle_points = []
            index_map = []

        for i, point in enumerate(handle_points):
            handle_rect = QRect(point.x() - half_handle, point.y() - half_handle, handle_size, handle_size)
            if handle_rect.contains(pos):
                if index_map:
                    return index_map[i]
                return i

        return -1  # 没有找到控制点

    def _get_shape_value(self, layer) -> str:
        shape_type = getattr(layer, "shape_type", None)
        if shape_type is None:
            return "rectangle"
        if hasattr(shape_type, "value"):
            return str(shape_type.value)
        return str(shape_type)

    def _is_corner_radius_draggable(self, layer) -> bool:
        if layer is None:
            return False
        if bool(getattr(layer, "vector_path_enabled", False)):
            return False
        shape = self._get_shape_value(layer)
        return shape in {"rectangle", "right_trapezoid", "pentagon", "hexagon"}

    def _get_corner_radius_value_and_limit(self, layer):
        shape = self._get_shape_value(layer)
        width = max(1, int(getattr(layer, "width", 1)))
        height = max(1, int(getattr(layer, "height", 1)))
        if shape == "rectangle":
            value = int(getattr(layer, "corner_radius", 0))
            max_value = max(0, min(width, height) // 2)
            return value, max_value, "rectangle"
        value = int(getattr(layer, "polygon_corner_radius", 0))
        max_value = max(0, min(width, height) // 4)
        return value, max_value, "polygon"

    def _set_corner_radius_value(self, layer, value: int):
        clamped = max(0, int(value))
        _, max_value, radius_kind = self._get_corner_radius_value_and_limit(layer)
        clamped = min(clamped, max_value)
        if radius_kind == "rectangle":
            layer.corner_radius = clamped
            if hasattr(layer, "vector_corner_radius_tl"):
                layer.vector_corner_radius_tl = clamped
            if hasattr(layer, "vector_corner_radius_tr"):
                layer.vector_corner_radius_tr = clamped
            if hasattr(layer, "vector_corner_radius_br"):
                layer.vector_corner_radius_br = clamped
            if hasattr(layer, "vector_corner_radius_bl"):
                layer.vector_corner_radius_bl = clamped
        else:
            if hasattr(layer, "polygon_corner_radius"):
                layer.polygon_corner_radius = clamped

    def _get_corner_radius_handle_point(self, layer, rect: QRect):
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return None
        if not self._is_corner_radius_draggable(layer):
            return None
        radius_value, _, _ = self._get_corner_radius_value_and_limit(layer)
        inset_px = int(radius_value * self.zoom_factor)
        base_y = rect.top() + 14
        handle_y = base_y + max(0, inset_px)
        max_y = rect.top() + max(16, rect.height() // 2)
        handle_y = min(handle_y, max_y)
        handle_x = rect.left() + rect.width() // 2
        return QPoint(handle_x, handle_y)

    def get_corner_radius_handle_at_position(self, pos, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return False
        layer = self.document.layers[layer_index]
        if layer is None or layer.locked:
            return False
        rect = self.get_layer_rect(layer_index)
        if not rect:
            return False
        handle_pt = self._get_corner_radius_handle_point(layer, rect)
        if handle_pt is None:
            return False
        size = 12
        half = size // 2
        return QRect(handle_pt.x() - half, handle_pt.y() - half, size, size).contains(pos)

    def _draw_corner_radius_handle(self, painter: QPainter, layer, rect: QRect):
        handle_pt = self._get_corner_radius_handle_point(layer, rect)
        if handle_pt is None:
            return
        anchor_x = rect.left() + rect.width() // 2
        anchor_y = rect.top() + 6
        painter.setPen(QPen(QColor(255, 196, 72), 1, Qt.SolidLine))
        painter.drawLine(anchor_x, anchor_y, handle_pt.x(), handle_pt.y())
        painter.setBrush(QBrush(QColor(255, 136, 0)))
        painter.drawEllipse(handle_pt.x() - 6, handle_pt.y() - 6, 12, 12)

    def get_cursor_for_handle(self, handle_index):
        """根据控制点索引返回相应的光标"""
        # 0: 左上, 1: 上中, 2: 右上, 3: 右中, 4: 右下, 5: 下中, 6: 左下, 7: 左中
        cursors = [
            Qt.SizeFDiagCursor,  # 左上
            Qt.SizeVerCursor,    # 上中
            Qt.SizeBDiagCursor,  # 右上
            Qt.SizeHorCursor,    # 右中
            Qt.SizeFDiagCursor,  # 右下
            Qt.SizeVerCursor,    # 下中
            Qt.SizeBDiagCursor,  # 左下
            Qt.SizeHorCursor,    # 左中
        ]

        if 0 <= handle_index < len(cursors):
            return cursors[handle_index]

        return Qt.ArrowCursor

    def _is_in_top_ruler(self, pos):
        if not self.show_rulers:
            return False
        ruler = self._get_ruler_thickness()
        canvas_rect = self.get_canvas_rect()
        return canvas_rect is not None and 0 <= pos.y() < ruler and pos.x() >= canvas_rect.x()

    def _is_in_left_ruler(self, pos):
        if not self.show_rulers:
            return False
        ruler = self._get_ruler_thickness()
        canvas_rect = self.get_canvas_rect()
        return canvas_rect is not None and 0 <= pos.x() < ruler and pos.y() >= canvas_rect.y()

    def _hit_test_guide(self, pos):
        """命中测试参考线，返回 (orientation, index) 或 (None, -1)"""
        if not self.show_guides:
            return None, -1
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return None, -1

        for i, gx in enumerate(self.vertical_guides):
            x = canvas_rect.x() + int(gx * self.zoom_factor)
            if abs(pos.x() - x) <= self._guide_hit_tolerance and canvas_rect.top() <= pos.y() <= canvas_rect.bottom():
                return "vertical", i

        for i, gy in enumerate(self.horizontal_guides):
            y = canvas_rect.y() + int(gy * self.zoom_factor)
            if abs(pos.y() - y) <= self._guide_hit_tolerance and canvas_rect.left() <= pos.x() <= canvas_rect.right():
                return "horizontal", i
        return None, -1

    def _clear_guide_selection(self):
        self._selected_guide_orientation = None
        self._selected_guide_index = -1

    def _set_selected_guide(self, orientation, index):
        self._selected_guide_orientation = orientation
        self._selected_guide_index = index

    def _should_delete_dragging_guide(self, pos):
        """是否应删除当前拖拽参考线（拖回标尺或拖出工作区）"""
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return False
        ruler = self._get_ruler_thickness()
        if self._dragging_guide_orientation == "vertical":
            # Photoshop语义：垂直参考线拖回左侧标尺删除
            if self.show_rulers and pos.x() <= ruler:
                return True
            return pos.x() < canvas_rect.x() - 30 or pos.x() > canvas_rect.right() + 30
        if self._dragging_guide_orientation == "horizontal":
            # Photoshop语义：水平参考线拖回顶部标尺删除
            if self.show_rulers and pos.y() <= ruler:
                return True
            return pos.y() < canvas_rect.y() - 30 or pos.y() > canvas_rect.bottom() + 30
        return False

    def _start_drag_new_guide(self, orientation, pos):
        """从标尺开始拖拽新参考线"""
        self._is_dragging_guide = True
        self._pending_new_guide = True
        self._dragging_guide_orientation = orientation
        self._clear_guide_selection()
        if orientation == "vertical":
            self.vertical_guides.append(0)
            self._dragging_guide_index = len(self.vertical_guides) - 1
        else:
            self.horizontal_guides.append(0)
            self._dragging_guide_index = len(self.horizontal_guides) - 1
        self._update_dragging_guide_from_pos(pos, Qt.NoModifier)
        self.setCursor(Qt.SplitHCursor if orientation == "vertical" else Qt.SplitVCursor)

    def _update_dragging_guide_from_pos(self, pos, modifiers=Qt.NoModifier):
        if not self._is_dragging_guide or self._dragging_guide_index < 0:
            return
        canvas_rect = self.get_canvas_rect()
        if not canvas_rect:
            return

        if self._dragging_guide_orientation == "vertical":
            gx = int((pos.x() - canvas_rect.x()) / self.zoom_factor)
            if modifiers & Qt.ShiftModifier:
                gx = int(round(gx / 10.0) * 10)
            if 0 <= self._dragging_guide_index < len(self.vertical_guides):
                self.vertical_guides[self._dragging_guide_index] = gx
            self._guide_overlay_text = f"X: {gx}px"
        elif self._dragging_guide_orientation == "horizontal":
            gy = int((pos.y() - canvas_rect.y()) / self.zoom_factor)
            if modifiers & Qt.ShiftModifier:
                gy = int(round(gy / 10.0) * 10)
            if 0 <= self._dragging_guide_index < len(self.horizontal_guides):
                self.horizontal_guides[self._dragging_guide_index] = gy
            self._guide_overlay_text = f"Y: {gy}px"
        self._guide_overlay_pos = QPoint(pos.x(), pos.y())

    def _apply_guide_snap_for_layer(self, layer, new_x, new_y):
        """对图层位置应用参考线吸附（边缘/中心）"""
        self._snap_feedback_active = False
        self._snap_feedback_vertical = None
        self._snap_feedback_horizontal = None
        self._snap_feedback_text = ""
        if not self.snap_to_guides or not self.show_guides:
            return new_x, new_y
        if self.zoom_factor <= 0:
            return new_x, new_y

        tolerance_doc = self._snap_tolerance_px / self.zoom_factor
        width = int(getattr(layer, "width", 0))
        height = int(getattr(layer, "height", 0))

        # 垂直参考线吸附：左边/中心/右边
        x_points = [
            ("left", float(new_x)),
            ("center", float(new_x) + width / 2.0),
            ("right", float(new_x) + width),
        ]
        best_dx = None
        best_snap_x = None
        for gx in self.vertical_guides:
            gx_f = float(gx)
            for _, px in x_points:
                d = gx_f - px
                if abs(d) <= tolerance_doc and (best_dx is None or abs(d) < abs(best_dx)):
                    best_dx = d
                    best_snap_x = gx
        if best_dx is not None:
            new_x = int(round(float(new_x) + best_dx))

        # 水平参考线吸附：上边/中心/下边
        y_points = [
            ("top", float(new_y)),
            ("center", float(new_y) + height / 2.0),
            ("bottom", float(new_y) + height),
        ]
        best_dy = None
        best_snap_y = None
        for gy in self.horizontal_guides:
            gy_f = float(gy)
            for _, py in y_points:
                d = gy_f - py
                if abs(d) <= tolerance_doc and (best_dy is None or abs(d) < abs(best_dy)):
                    best_dy = d
                    best_snap_y = gy
        if best_dy is not None:
            new_y = int(round(float(new_y) + best_dy))

        if best_dx is not None or best_dy is not None:
            self._snap_feedback_active = True
            self._snap_feedback_vertical = best_snap_x
            self._snap_feedback_horizontal = best_snap_y
            label_parts = ["SNAP"]
            if best_snap_x is not None:
                label_parts.append(f"X:{int(best_snap_x)}")
            if best_snap_y is not None:
                label_parts.append(f"Y:{int(best_snap_y)}")
            self._snap_feedback_text = " ".join(label_parts)
            canvas_rect = self.get_canvas_rect()
            if canvas_rect:
                self._snap_feedback_pos = QPoint(
                    canvas_rect.x() + int((new_x + width / 2.0) * self.zoom_factor),
                    canvas_rect.y() + int((new_y + height / 2.0) * self.zoom_factor),
                )

        return new_x, new_y

    def mousePressEvent(self, event):
        """鼠标按下事件处理"""
        if event.button() == Qt.LeftButton:
            # 参考线优先：命中已有参考线后可拖拽
            orientation, guide_index = self._hit_test_guide(event.pos())
            if orientation:
                self._is_dragging_guide = True
                self._pending_new_guide = False
                self._dragging_guide_orientation = orientation
                self._dragging_guide_index = guide_index
                self._set_selected_guide(orientation, guide_index)
                self._guide_overlay_text = ""
                self.setCursor(Qt.SplitHCursor if orientation == "vertical" else Qt.SplitVCursor)
                event.accept()
                return

            # 从标尺拖拽创建参考线
            if self._is_in_top_ruler(event.pos()):
                self._start_drag_new_guide("horizontal", event.pos())
                event.accept()
                return
            if self._is_in_left_ruler(event.pos()):
                self._start_drag_new_guide("vertical", event.pos())
                event.accept()
                return

            # 点击非参考线区域时取消参考线选中
            self._clear_guide_selection()

            # 如果Space键按下，优先启用画布拖拽模式
            if self.temp_hand_mode:
                self.drag_start = event.pos()
                self.is_dragging = True
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return

            # 尝试获取点击位置的调整控制点
            if self.document.selected_layer_index >= 0:
                handle_node_index, handle_type = self.get_vector_handle_at_position(event.pos(), self.document.selected_layer_index)
                if handle_node_index >= 0:
                    self.is_dragging_vector_handle = True
                    self.vector_handle_node_index = handle_node_index
                    self.vector_handle_type = handle_type
                    self.selected_vector_node_index = handle_node_index
                    self.resize_start_point = event.pos()
                    event.accept()
                    return

                node_index = self.get_vector_node_at_position(event.pos(), self.document.selected_layer_index)
                if node_index >= 0:
                    self.is_dragging_vector_node = True
                    self.vector_node_index = node_index
                    self.selected_vector_node_index = node_index
                    self.resize_start_point = event.pos()
                    event.accept()
                    return

                if self.get_corner_radius_handle_at_position(event.pos(), self.document.selected_layer_index):
                    layer = self.document.layers[self.document.selected_layer_index]
                    if not layer.locked:
                        radius_value, _, _ = self._get_corner_radius_value_and_limit(layer)
                        self.is_dragging_corner_radius = True
                        self.corner_radius_start_point = event.pos()
                        self.corner_radius_start_value = int(radius_value)
                        event.accept()
                        return

                handle_index = self.get_handle_at_position(event.pos(), self.document.selected_layer_index)

                if handle_index >= 0:
                    # 记录开始调整大小的状态
                    self.is_resizing = True
                    self.resize_handle_index = handle_index
                    self.resize_start_point = event.pos()

                    # 记录图层的原始矩形
                    layer = self.document.layers[self.document.selected_layer_index]
                    if bool(getattr(layer, 'auto_fit_text_box', False)):
                        layer.auto_fit_text_box = False
                    self.resize_start_rect = QRect(layer.x, layer.y, layer.width, layer.height)

                    event.accept()
                    return

            # 检查点击的位置是否在图层上
            layer_index = self.get_layer_at_position(event.pos())

            if layer_index >= 0:
                # 立即选中图层（点击选中）
                if not event.modifiers() & Qt.AltModifier:
                    selected_indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
                    if layer_index not in selected_indices:
                        if hasattr(self.document, 'select_layers'):
                            self.document.select_layers([layer_index], primary_index=layer_index)
                        else:
                            self.document.select_layer(layer_index)
                    elif layer_index != self.document.selected_layer_index and hasattr(self.document, 'select_layers'):
                        # 点击已选图层时保留多选，只把点击项设为主选/拖拽基准
                        reordered = [layer_index] + [idx for idx in selected_indices if idx != layer_index]
                        self.document.select_layers(reordered, primary_index=layer_index)

                # 记录鼠标按下状态，为可能的拖拽做准备（按住拖拽）
                self.potential_drag = True
                self.dragging_layer_index = layer_index
                self.drag_start_pos = event.pos()
                self.layer_drag_start = event.pos()
                active_selection = list(getattr(self.document, 'selected_layer_indices', []) or [layer_index])
                if layer_index not in active_selection:
                    active_selection = [layer_index]
                self.dragging_layer_indices = [
                    idx for idx in active_selection
                    if 0 <= idx < len(self.document.layers) and not getattr(self.document.layers[idx], 'locked', False)
                ]
                self.dragging_layer_start_positions = {
                    idx: (int(self.document.layers[idx].x), int(self.document.layers[idx].y))
                    for idx in self.dragging_layer_indices
                }

                # 获取画布矩形
                canvas_rect = self.get_canvas_rect()
                if canvas_rect:
                    # 记录鼠标位置与图层左上角的偏移，以便拖动时保持这个偏移
                    layer = self.document.layers[layer_index]
                    layer_rect = self.get_layer_rect(layer_index)
                    if layer_rect:
                        layer_x = layer_rect.x()
                        layer_y = layer_rect.y()
                    else:
                        layer_x = canvas_rect.x() + int(layer.x * self.zoom_factor)
                        layer_y = canvas_rect.y() + int(layer.y * self.zoom_factor)

                    self.drag_offset_x = event.pos().x() - layer_x
                    self.drag_offset_y = event.pos().y() - layer_y

                event.accept()
                return

            # 如果点击不在图层上，取消选中，并准备画布拖拽
            if self.document.selected_layer_index >= 0:
                self.document.select_layer(-1)
                self.selected_vector_node_index = -1

            # 启动画布拖动模式
            self.drag_start = event.pos()
            self.is_dragging = True
            self.setCursor(Qt.ClosedHandCursor)

        event.accept()

    def mouseDoubleClickEvent(self, event):
        """双击文字图层时打开文案编辑器。"""
        if event.button() == Qt.LeftButton:
            layer_index = self.get_layer_at_position(event.pos())
            if layer_index >= 0:
                layer = self.document.layers[layer_index]
                try:
                    from app.models.text_layer import TextLayer
                    if isinstance(layer, TextLayer):
                        main_window = self._get_main_window()
                        if main_window and hasattr(main_window, 'edit_text_layer'):
                            main_window.edit_text_layer(layer_index)
                            event.accept()
                            return
                except Exception as e:
                    print(f"双击编辑文字图层时出错: {e}")

        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件处理"""
        # 跟踪鼠标位置用于拖拽方向指示器
        self._last_mouse_pos = event.pos()

        if self._is_dragging_guide:
            self._update_dragging_guide_from_pos(event.pos(), event.modifiers())
            # 参考线是视图辅助元素，不触发文档变更，仅刷新当前画布
            self.update()
            event.accept()
            return

        # 发送鼠标位置变化信号
        canvas_rect = self.get_canvas_rect()
        if canvas_rect and canvas_rect.contains(event.pos()):
            # 计算相对于画布的坐标
            relative_x = int((event.pos().x() - canvas_rect.x()) / self.zoom_factor)
            relative_y = int((event.pos().y() - canvas_rect.y()) / self.zoom_factor)
            self.position_changed.emit(relative_x, relative_y)

        if self.is_resizing and self.document.selected_layer_index >= 0:
            # 处理图层调整大小
            layer = self.document.layers[self.document.selected_layer_index]

            # 如果图层被锁定，取消调整大小
            if layer.locked:
                self.is_resizing = False
                self.resize_handle_index = -1
                self.resize_start_rect = None
                self.resize_start_point = None
                return

            # 计算鼠标移动的距离
            dx = event.pos().x() - self.resize_start_point.x()
            dy = event.pos().y() - self.resize_start_point.y()

            # 转换为图层坐标系中的距离
            dx = int(dx / self.zoom_factor)
            dy = int(dy / self.zoom_factor)

            # 根据控制点索引调整图层的位置和尺寸
            new_x = self.resize_start_rect.x()
            new_y = self.resize_start_rect.y()
            new_width = self.resize_start_rect.width()
            new_height = self.resize_start_rect.height()

            # 0: 左上, 1: 上中, 2: 右上, 3: 右中, 4: 右下, 5: 下中, 6: 左下, 7: 左中
            if self.resize_handle_index in [0, 6, 7]:  # 左侧控制点
                new_x += dx
                new_width -= dx
            if self.resize_handle_index in [2, 3, 4]:  # 右侧控制点
                new_width += dx
            if self.resize_handle_index in [0, 1, 2]:  # 上侧控制点
                new_y += dy
                new_height -= dy
            if self.resize_handle_index in [4, 5, 6]:  # 下侧控制点
                new_height += dy

            # 确保图层尺寸不会太小
            min_size = 10
            if new_width < min_size:
                # 如果从左侧调整，需要相应调整x坐标
                if self.resize_handle_index in [0, 6, 7]:
                    new_x = self.resize_start_rect.right() - min_size
                new_width = min_size

            if new_height < min_size:
                # 如果从上侧调整，需要相应调整y坐标
                if self.resize_handle_index in [0, 1, 2]:
                    new_y = self.resize_start_rect.bottom() - min_size
                new_height = min_size

            # 更新图层属性
            layer.x = new_x
            layer.y = new_y
            layer.width = new_width
            layer.height = new_height

            # 交互过程采用节流刷新，避免每个鼠标事件都触发完整重绘
            self._schedule_interactive_update(require_recompose=True)

            event.accept()
            return

        if self.is_dragging_corner_radius and self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if layer.locked:
                self.is_dragging_corner_radius = False
                self.corner_radius_start_point = None
                return
            if self.corner_radius_start_point is not None:
                dy = event.pos().y() - self.corner_radius_start_point.y()
                delta = int(round(dy / max(0.001, self.zoom_factor)))
                new_radius = self.corner_radius_start_value + delta
                self._set_corner_radius_value(layer, new_radius)
                self._schedule_interactive_update(require_recompose=True)
                event.accept()
                return

        if self.is_dragging_vector_handle and self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if layer.locked:
                self.is_dragging_vector_handle = False
                self.vector_handle_node_index = -1
                self.vector_handle_type = None
                return
            if hasattr(layer, 'update_vector_bezier_handle'):
                rect = self.get_layer_rect(self.document.selected_layer_index)
                if rect:
                    ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
                    local_x = (event.pos().x() - ox) / self.zoom_factor
                    local_y = (event.pos().y() - oy) / self.zoom_factor
                    layer.update_vector_bezier_handle(self.vector_handle_node_index, self.vector_handle_type, local_x, local_y)
                    self._schedule_interactive_update(require_recompose=True)
                    event.accept()
                    return

        if self.is_dragging_vector_node and self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if layer.locked:
                self.is_dragging_vector_node = False
                self.vector_node_index = -1
                return
            if hasattr(layer, 'update_vector_bezier_anchor'):
                rect = self.get_layer_rect(self.document.selected_layer_index)
                if rect:
                    ox, oy = self._get_layer_local_origin_in_rect(layer, rect)
                    local_x = (event.pos().x() - ox) / self.zoom_factor
                    local_y = (event.pos().y() - oy) / self.zoom_factor
                    layer.update_vector_bezier_anchor(self.vector_node_index, local_x, local_y)
                    self._schedule_interactive_update(require_recompose=True)
                    event.accept()
                    return

        elif self.potential_drag and not self.is_dragging_layer:
            # 检查是否超过拖拽阈值且鼠标仍在按下状态
            if self.drag_start_pos:
                distance = (event.pos() - self.drag_start_pos).manhattanLength()
                if distance > self.drag_threshold:
                    # 只有在潜在拖拽状态下才开始实际拖拽
                    layer = self.document.layers[self.dragging_layer_index]
                    drag_indices = getattr(self, 'dragging_layer_indices', [self.dragging_layer_index])
                    if drag_indices and not layer.locked:  # 确保图层未锁定
                        self.potential_drag = False
                        self.is_dragging_layer = True
                        self.document.save_state("批量移动图层前" if len(drag_indices) > 1 else "移动图层前")
                        self.setCursor(Qt.ClosedHandCursor)
                    else:
                        # 图层锁定，取消拖拽
                        self.potential_drag = False
                        self.drag_start_pos = None

        elif self.is_dragging_layer and self.dragging_layer_index >= 0:
            # 处理图层拖动
            layer = self.document.layers[self.dragging_layer_index]

            # 如果图层被锁定，取消拖动
            if layer.locked:
                self.is_dragging_layer = False
                self.dragging_layer_index = -1
                self.layer_drag_start = None
                self._interactive_low_quality_active = False
                return

            # 计算新位置
            canvas_rect = self.get_canvas_rect()
            if canvas_rect:
                # 考虑拖动偏移
                new_x = int((event.pos().x() - canvas_rect.x() - self.drag_offset_x) / self.zoom_factor)
                new_y = int((event.pos().y() - canvas_rect.y() - self.drag_offset_y) / self.zoom_factor)
                new_x, new_y = self._apply_guide_snap_for_layer(layer, new_x, new_y)
                start_positions = getattr(self, 'dragging_layer_start_positions', {})
                base_start_x, base_start_y = start_positions.get(
                    self.dragging_layer_index,
                    (int(layer.x), int(layer.y)),
                )
                delta_x = new_x - base_start_x
                delta_y = new_y - base_start_y

                # 更新图层位置。多选时保持各图层相对位置。
                drag_indices = getattr(self, 'dragging_layer_indices', [self.dragging_layer_index])
                for idx in drag_indices:
                    if not (0 <= idx < len(self.document.layers)):
                        continue
                    target_layer = self.document.layers[idx]
                    if getattr(target_layer, 'locked', False):
                        continue
                    start_x, start_y = start_positions.get(idx, (int(target_layer.x), int(target_layer.y)))
                    target_layer.x = start_x + delta_x
                    target_layer.y = start_y + delta_y

                # 交互过程采用节流刷新，避免每个鼠标事件都触发完整重绘
                self._schedule_interactive_update(require_recompose=True)

            event.accept()
            return

        elif self.is_dragging:
            # 处理画布拖动
            if self.drag_start:
                self.offset += event.pos() - self.drag_start
                self.drag_start = event.pos()
                self._schedule_interactive_update(require_recompose=False)

            event.accept()
            return

        # 根据鼠标位置更新光标
        # 检查是否在控制点上
        if self.document.selected_layer_index >= 0:
            handle_node_index, _ = self.get_vector_handle_at_position(event.pos(), self.document.selected_layer_index)
            if handle_node_index >= 0:
                self.setCursor(Qt.PointingHandCursor)
                event.accept()
                return
            node_index = self.get_vector_node_at_position(event.pos(), self.document.selected_layer_index)
            if node_index >= 0:
                self.setCursor(Qt.CrossCursor)
                event.accept()
                return
            if self.get_corner_radius_handle_at_position(event.pos(), self.document.selected_layer_index):
                self.setCursor(Qt.SizeVerCursor)
                event.accept()
                return
            handle_index = self.get_handle_at_position(event.pos(), self.document.selected_layer_index)

            if handle_index >= 0:
                self.setCursor(self.get_cursor_for_handle(handle_index))
                event.accept()
                return

        # 检查是否在图层上
        layer_index = self.get_layer_at_position(event.pos())

        if layer_index >= 0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            orientation, _ = self._hit_test_guide(event.pos())
            if orientation == "vertical":
                self.setCursor(Qt.SplitHCursor)
            elif orientation == "horizontal":
                self.setCursor(Qt.SplitVCursor)
            elif self._is_in_top_ruler(event.pos()) or self._is_in_left_ruler(event.pos()):
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

        event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件处理"""
        if event.button() == Qt.LeftButton:
            if self._is_dragging_guide:
                if self._should_delete_dragging_guide(event.pos()):
                    if self._dragging_guide_orientation == "vertical" and 0 <= self._dragging_guide_index < len(self.vertical_guides):
                        self.vertical_guides.pop(self._dragging_guide_index)
                    if self._dragging_guide_orientation == "horizontal" and 0 <= self._dragging_guide_index < len(self.horizontal_guides):
                        self.horizontal_guides.pop(self._dragging_guide_index)
                    self._clear_guide_selection()
                else:
                    self._set_selected_guide(self._dragging_guide_orientation, self._dragging_guide_index)

                self._is_dragging_guide = False
                self._pending_new_guide = False
                self._dragging_guide_orientation = None
                self._dragging_guide_index = -1
                self._guide_overlay_text = ""
                self._persist_view_settings_to_document()
                if not self.temp_hand_mode:
                    self.setCursor(Qt.ArrowCursor)
                self.update()
                event.accept()
                return

            # 确保交互结束时立即落地最终一帧
            if self._interactive_update_pending:
                self._interactive_update_timer.stop()
                self._flush_interactive_update()

            if self.is_resizing:
                # 结束图层大小调整
                self.is_resizing = False

                # 如果大小有变化，保存历史记录
                if self.document.selected_layer_index >= 0 and self.resize_start_rect:
                    layer = self.document.layers[self.document.selected_layer_index]
                    if (layer.x != self.resize_start_rect.x() or
                        layer.y != self.resize_start_rect.y() or
                        layer.width != self.resize_start_rect.width() or
                        layer.height != self.resize_start_rect.height()):
                        self.document.save_state("调整图层大小")
                        self._request_high_quality_refresh()

                self.resize_handle_index = -1
                self.resize_start_rect = None
                self.resize_start_point = None

            elif self.is_dragging_corner_radius:
                self.is_dragging_corner_radius = False
                self.corner_radius_start_point = None
                self.document.save_state("调整圆角")
                self._request_high_quality_refresh()

            elif self.is_dragging_vector_node:
                self.is_dragging_vector_node = False
                self.vector_node_index = -1
                self.document.save_state("编辑路径节点")
                self._request_high_quality_refresh()

            elif self.is_dragging_vector_handle:
                self.is_dragging_vector_handle = False
                self.vector_handle_node_index = -1
                self.vector_handle_type = None
                self.document.save_state("编辑贝塞尔手柄")
                self._request_high_quality_refresh()

            elif self.is_dragging_layer:
                # 结束图层拖动
                self.is_dragging_layer = False
                self._snap_feedback_active = False

                # 如果位置有变化，保存历史记录
                if self.dragging_layer_index >= 0:
                    drag_count = len(getattr(self, 'dragging_layer_indices', []) or [self.dragging_layer_index])
                    self.document.save_state("批量移动图层" if drag_count > 1 else "移动图层")
                    self._request_high_quality_refresh()

                self.dragging_layer_index = -1
                self.layer_drag_start = None
                self.dragging_layer_indices = []
                self.dragging_layer_start_positions = {}

                # 清理拖拽相关状态
                self._clear_drag_state()

            elif self.potential_drag:
                # 如果只是点击没有拖拽，重置潜在拖拽状态
                self.potential_drag = False
                self.dragging_layer_index = -1
                self.drag_start_pos = None
                self.layer_drag_start = None

            elif self.is_dragging:
                # 结束画布拖动
                self.is_dragging = False
                self.drag_start = None
                self._persist_view_settings_to_document()
                # 如果在临时抓手模式，恢复抓手光标，否则恢复箭头光标
                if self.temp_hand_mode:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)

            # 统一恢复默认光标（除非在特殊模式）
            if not self.temp_hand_mode and not self.is_resizing and not self.is_dragging_layer and not self.is_dragging:
                self.setCursor(Qt.ArrowCursor)

        event.accept()

    def keyPressEvent(self, event):
        """键盘事件处理"""
        # 视图快捷键（Photoshop风格）
        if event.modifiers() & Qt.ControlModifier and not event.isAutoRepeat():
            if event.key() == Qt.Key_R:
                self.show_rulers = not self.show_rulers
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return

        # 路径节点快捷键（AI风格）：1=尖角 2=平滑 3=对称
        if self.document.selected_layer_index >= 0 and self.selected_vector_node_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if bool(getattr(layer, 'vector_path_enabled', False)) and hasattr(layer, 'set_vector_node_type'):
                if event.key() == Qt.Key_1:
                    layer.set_vector_node_type(self.selected_vector_node_index, "corner")
                    self.document.save_state("节点类型:尖角")
                    self.document.document_changed.emit()
                    event.accept()
                    return

        # 路径联动与闭合快捷键：Q/W/E 切手柄模式，C 切闭合
        if self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            if bool(getattr(layer, 'vector_path_enabled', False)):
                if event.key() == Qt.Key_Q:
                    layer.vector_handle_link_mode = "mirror"
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_W:
                    layer.vector_handle_link_mode = "collinear"
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_E:
                    layer.vector_handle_link_mode = "free"
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_C:
                    layer.vector_path_closed = not bool(getattr(layer, 'vector_path_closed', True))
                    self.document.save_state("切换路径闭合")
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_2:
                    layer.set_vector_node_type(self.selected_vector_node_index, "smooth")
                    self.document.save_state("节点类型:平滑")
                    self.document.document_changed.emit()
                    event.accept()
                    return
                if event.key() == Qt.Key_3:
                    layer.set_vector_node_type(self.selected_vector_node_index, "symmetric")
                    self.document.save_state("节点类型:对称")
                    self.document.document_changed.emit()
                    event.accept()
                    return
            if event.key() == Qt.Key_Semicolon:
                self.show_guides = not self.show_guides
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return

        # 删除当前选中的参考线
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.document.selected_layer_index >= 0 and self.selected_vector_node_index >= 0:
                layer = self.document.layers[self.document.selected_layer_index]
                if bool(getattr(layer, 'vector_path_enabled', False)) and hasattr(layer, 'delete_vector_node'):
                    layer.delete_vector_node(self.selected_vector_node_index)
                    self.selected_vector_node_index = -1
                    self.document.save_state("删除路径节点")
                    self.document.document_changed.emit()
                    event.accept()
                    return
            if self._selected_guide_orientation == "vertical" and 0 <= self._selected_guide_index < len(self.vertical_guides):
                self.vertical_guides.pop(self._selected_guide_index)
                self._clear_guide_selection()
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return
            if self._selected_guide_orientation == "horizontal" and 0 <= self._selected_guide_index < len(self.horizontal_guides):
                self.horizontal_guides.pop(self._selected_guide_index)
                self._clear_guide_selection()
                self._persist_view_settings_to_document()
                self.update()
                event.accept()
                return

        # 处理Space键启用临时抓手工具
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if not self.space_pressed:
                self.space_pressed = True
                self.temp_hand_mode = True
                # 保存当前光标
                self.original_cursor = self.cursor()
                # 设置抓手光标
                self.setCursor(Qt.OpenHandCursor)
                event.accept()
                return

        # 处理方向键移动选中的图层
        selected_indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
        if not selected_indices and self.document.selected_layer_index >= 0:
            selected_indices = [self.document.selected_layer_index]
        if selected_indices:
            move_step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            dx = dy = 0
            if event.key() == Qt.Key_Left:
                dx = -move_step
            elif event.key() == Qt.Key_Right:
                dx = move_step
            elif event.key() == Qt.Key_Up:
                dy = -move_step
            elif event.key() == Qt.Key_Down:
                dy = move_step

            if dx or dy:
                movable_indices = [
                    idx for idx in selected_indices
                    if 0 <= idx < len(self.document.layers) and not getattr(self.document.layers[idx], 'locked', False)
                ]
                if not movable_indices:
                    event.accept()
                    return
                self.document.save_state("批量移动图层前" if len(movable_indices) > 1 else "移动图层前")
                for idx in movable_indices:
                    layer = self.document.layers[idx]
                    layer.x += dx
                    layer.y += dy
                self.document.save_state("批量移动图层" if len(movable_indices) > 1 else "移动图层")
                self.document.document_changed.emit()
                self.update()
                event.accept()
                return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """键盘松开事件处理"""
        # 处理Space键释放，禁用临时抓手工具
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if self.space_pressed:
                self.space_pressed = False
                self.temp_hand_mode = False
                # 恢复原来的光标
                self.setCursor(self.original_cursor)
                event.accept()
                return

        super().keyReleaseEvent(event)

    def sizeHint(self):
        """返回控件的建议大小"""
        return QSize(800, 600)

    def show_context_menu(self, pos):
        """显示画布右键菜单"""
        menu = QMenu()
        toggle_ruler_action = None
        toggle_guides_action = None
        clear_guides_action = None

        # 获取主窗口引用
        main_window = self._get_main_window()

        # 检查点击位置是否在图层上
        layer_index = self.get_layer_at_position(pos)

        if layer_index >= 0:
            # 点击在图层上 - 显示图层相关菜单
            if layer_index != self.document.selected_layer_index:
                self.document.select_layer(layer_index)

            layer = self.document.layers[layer_index]

            # 图层操作
            select_action = menu.addAction(f"已选中: {layer.name}")
            select_action.setEnabled(False)  # 仅作为信息显示

            menu.addSeparator()

            # 复制粘贴操作
            copy_action = menu.addAction("复制图层")

            paste_action = None
            if main_window and hasattr(main_window, 'layer_clipboard') and main_window.layer_clipboard:
                paste_action = menu.addAction("粘贴图层")

            menu.addSeparator()

            # 图层样式
            copy_style_action = menu.addAction("复制图层样式")

            paste_style_action = None
            if main_window and hasattr(main_window, 'layer_style_clipboard') and main_window.layer_style_clipboard:
                paste_style_action = menu.addAction("粘贴图层样式")

            menu.addSeparator()

            # 图层管理
            edit_text_action = None
            try:
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer):
                    edit_text_action = menu.addAction("编辑文案")
            except Exception:
                edit_text_action = None
            rename_action = menu.addAction("重命名图层")
            delete_action = menu.addAction("删除图层")

            menu.addSeparator()

            # 图层状态
            lock_action = menu.addAction("锁定图层" if not layer.locked else "解锁图层")

            # 路径编辑菜单
            vector_insert_action = None
            vector_delete_action = None
            vector_toggle_closed_action = None
            vector_cycle_type_action = None
            link_mirror_action = None
            link_collinear_action = None
            link_free_action = None
            if bool(getattr(layer, 'vector_path_enabled', False)):
                menu.addSeparator()
                node_index = self.get_vector_node_at_position(pos, layer_index)
                if node_index >= 0:
                    self.selected_vector_node_index = node_index
                self._context_vector_segment_index = self.get_vector_segment_at_position(pos, layer_index)
                vector_menu = menu.addMenu("路径编辑")
                vector_insert_action = vector_menu.addAction("插入节点")
                vector_delete_action = vector_menu.addAction("删除节点")
                vector_toggle_closed_action = vector_menu.addAction("切换路径闭合")
                vector_cycle_type_action = vector_menu.addAction("循环节点类型")
                vector_menu.addSeparator()
                link_mirror_action = vector_menu.addAction("手柄联动:镜像")
                link_collinear_action = vector_menu.addAction("手柄联动:共线")
                link_free_action = vector_menu.addAction("手柄联动:自由")
                if self.selected_vector_node_index < 0:
                    vector_delete_action.setEnabled(False)
                    vector_cycle_type_action.setEnabled(False)
                if self._context_vector_segment_index < 0:
                    vector_insert_action.setEnabled(False)

        else:
            # 点击在空白画布上 - 显示画布相关菜单
            # 粘贴操作
            paste_action = None
            if main_window and hasattr(main_window, 'layer_clipboard') and main_window.layer_clipboard:
                paste_action = menu.addAction("粘贴图层")

            # 添加图层
            add_layer_action = menu.addAction("添加图层")
            add_text_layer_action = menu.addAction("添加文本图层")

            menu.addSeparator()

            # 画布操作
            canvas_size_action = menu.addAction("修改画布尺寸")

            menu.addSeparator()

            # 视图操作
            zoom_in_action = menu.addAction("放大")
            zoom_out_action = menu.addAction("缩小")
            zoom_reset_action = menu.addAction("重置缩放")
            menu.addSeparator()
            toggle_ruler_action = menu.addAction("隐藏标尺" if self.show_rulers else "显示标尺")
            toggle_guides_action = menu.addAction("隐藏参考线" if self.show_guides else "显示参考线")
            clear_guides_action = menu.addAction("清空参考线")

            # 背景设置（如果有的话）
            # background_action = menu.addAction("背景设置")

        # 显示菜单并处理选择
        action = menu.exec(self.mapToGlobal(pos))

        if not action:
            return

        # 处理图层相关操作
        if layer_index >= 0:
            if 'edit_text_action' in locals() and edit_text_action and action == edit_text_action and main_window:
                main_window.edit_text_layer(layer_index)
            elif action.text() == "复制图层" and main_window:
                main_window.copy_layer()
            elif paste_action and action == paste_action and main_window:
                main_window.paste_layer()
            elif action.text() == "复制图层样式" and main_window:
                main_window.copy_layer_style()
            elif paste_style_action and action == paste_style_action and main_window:
                main_window.paste_layer_style()
            elif action.text() == "重命名图层" and main_window:
                main_window.rename_layer()
            elif action.text() == "删除图层" and main_window:
                main_window.delete_layer()
            elif action.text() in ["锁定图层", "解锁图层"]:
                layer.locked = not layer.locked
                self.document.document_changed.emit()
            elif 'vector_insert_action' in locals() and action == vector_insert_action:
                if hasattr(layer, 'insert_vector_node_after') and self._context_vector_segment_index >= 0:
                    layer.insert_vector_node_after(self._context_vector_segment_index)
                    self.document.save_state("插入路径节点")
                    self.document.document_changed.emit()
            elif 'vector_delete_action' in locals() and action == vector_delete_action:
                if hasattr(layer, 'delete_vector_node') and self.selected_vector_node_index >= 0:
                    layer.delete_vector_node(self.selected_vector_node_index)
                    self.selected_vector_node_index = -1
                    self.document.save_state("删除路径节点")
                    self.document.document_changed.emit()
            elif 'vector_toggle_closed_action' in locals() and action == vector_toggle_closed_action:
                layer.vector_path_closed = not bool(getattr(layer, 'vector_path_closed', True))
                self.document.save_state("切换路径闭合")
                self.document.document_changed.emit()
            elif 'vector_cycle_type_action' in locals() and action == vector_cycle_type_action:
                if hasattr(layer, 'cycle_vector_node_type') and self.selected_vector_node_index >= 0:
                    layer.cycle_vector_node_type(self.selected_vector_node_index)
                    self.document.save_state("循环节点类型")
                    self.document.document_changed.emit()
            elif 'link_mirror_action' in locals() and action == link_mirror_action:
                layer.vector_handle_link_mode = "mirror"
                self.document.save_state("手柄联动:镜像")
                self.document.document_changed.emit()
            elif 'link_collinear_action' in locals() and action == link_collinear_action:
                layer.vector_handle_link_mode = "collinear"
                self.document.save_state("手柄联动:共线")
                self.document.document_changed.emit()
            elif 'link_free_action' in locals() and action == link_free_action:
                layer.vector_handle_link_mode = "free"
                self.document.save_state("手柄联动:自由")
                self.document.document_changed.emit()

        else:
            # 处理画布相关操作
            if paste_action and action == paste_action and main_window:
                main_window.paste_layer()
            elif action.text() == "添加图层" and main_window:
                main_window.add_layer()
            elif action.text() == "添加文本图层" and main_window:
                main_window.add_text_layer()
            elif action.text() == "修改画布尺寸" and main_window:
                main_window.resize_canvas()
            elif action.text() == "放大" and main_window:
                main_window.zoom_in()
            elif action.text() == "缩小" and main_window:
                main_window.zoom_out()
            elif action.text() == "重置缩放" and main_window:
                main_window.zoom_reset()
            elif toggle_ruler_action and action == toggle_ruler_action:
                self.show_rulers = not self.show_rulers
                self._persist_view_settings_to_document()
                self.update()
            elif toggle_guides_action and action == toggle_guides_action:
                self.show_guides = not self.show_guides
                self._persist_view_settings_to_document()
                self.update()
            elif clear_guides_action and action == clear_guides_action:
                self.horizontal_guides.clear()
                self.vertical_guides.clear()
                self._persist_view_settings_to_document()
                self.update()

    def _get_main_window(self):
        """获取主窗口引用"""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'layer_clipboard'):  # 主窗口特征
                return parent
            parent = parent.parent()
        return None
