from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
                               QGroupBox, QGridLayout, QSlider, QCheckBox,
                               QDialog, QDialogButtonBox)
from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
try:
    from app.models.shaped_layer_new import ShapedLayer, ShapeType
except ImportError:
    from app.models.shaped_layer_new import ShapedLayer, ShapeType


class ShapedLayerPanel(QWidget):
    """异形图层控制面板"""

    # 信号定义
    shape_changed = Signal()
    parameter_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layer = None
        self._updating = False

        # 先初始化UI元素引用
        self.shape_combo = None
        self.shape_preview = None
        self.params_layout = None
        self.trapezoid_widget = None
        self.polygon_widget = None
        self.trapezoid_top_width_spin = None
        self.trapezoid_bottom_width_spin = None
        self.trapezoid_side_combo = None
        self.polygon_rotation_spin = None
        self.polygon_corner_radius_spin = None

        self.init_ui()

    def init_ui(self):
        """初始化UI界面"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 形状预览组（保留独有功能）
        # preview_group = QGroupBox("形状预览")
        # preview_layout = QVBoxLayout()

        # 形状预览
        # self.shape_preview = ShapePreviewWidget()
        # self.shape_preview.setFixedSize(80, 80)
        # self.shape_preview.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # preview_layout.setContentsMargins(8, 8, 8, 8)
        # preview_layout.setSpacing(6)
        # preview_layout.addWidget(self.shape_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        # preview_layout.addStretch()

        # preview_group.setLayout(preview_layout)
        # layout.addWidget(preview_group)  # 移除重复的预览组，已在基本属性面板中整合


        # 快速旋转控制组（保留独有功能）
        rotation_group = QGroupBox("快速旋转")
        rotation_layout = QVBoxLayout()

        # 创建快速旋转按钮
        self.create_quick_rotation_controls(rotation_layout)

        rotation_group.setLayout(rotation_layout)
        layout.addWidget(rotation_group)

        # 参数控制组 - 仅显示当前形状信息，不再提供编辑功能
        self.params_group = QGroupBox("形状信息")
        self.params_layout = QVBoxLayout()
        self.current_shape_label = QLabel("当前形状: 矩形")
        self.current_shape_label.setStyleSheet("color: #8E8E93; font-weight: bold;")
        self.params_layout.addWidget(self.current_shape_label)

        # 创建参数信息显示（只读）
        self.create_parameter_info_display()

        self.params_group.setLayout(self.params_layout)
        # layout.addWidget(self.params_group)  # 移除重复的参数信息，已在基本属性面板中整合


        # 添加弹簧
        layout.addStretch()

        self.setLayout(layout)
        # self.setMaximumWidth(300)  # 移除固定宽度限制，使其能自适应父容器宽度

        # 初始显示矩形信息
        self.update_parameter_info_display(ShapeType.RECTANGLE)

        # 连接信号（在所有方法定义完成后）
        self.connect_signals()

    def create_quick_rotation_controls(self, parent_layout):
        """创建快速旋转控制按钮"""
        # 快速旋转按钮布局
        button_layout = QHBoxLayout()

        self.rotate_0_btn = QPushButton("0°")
        self.rotate_0_btn.setFixedSize(40, 25)
        button_layout.addWidget(self.rotate_0_btn)

        self.rotate_90_btn = QPushButton("90°")
        self.rotate_90_btn.setFixedSize(40, 25)
        button_layout.addWidget(self.rotate_90_btn)

        self.rotate_180_btn = QPushButton("180°")
        self.rotate_180_btn.setFixedSize(40, 25)
        button_layout.addWidget(self.rotate_180_btn)

        self.rotate_270_btn = QPushButton("270°")
        self.rotate_270_btn.setFixedSize(40, 25)
        button_layout.addWidget(self.rotate_270_btn)

        parent_layout.addLayout(button_layout)

        # 添加当前角度显示
        self.current_rotation_label = QLabel("当前角度: 0°")
        self.current_rotation_label.setStyleSheet("color: #888; font-size: 9pt;")
        parent_layout.addWidget(self.current_rotation_label, alignment=Qt.AlignmentFlag.AlignCenter)

    def create_parameter_info_display(self):
        """创建参数信息显示（只读）"""
        self.trapezoid_info_widget = QWidget()
        trapezoid_layout = QVBoxLayout()
        trapezoid_layout.setSpacing(5)

        self.trapezoid_top_label = QLabel("上底宽度: 100")
        self.trapezoid_bottom_label = QLabel("下底宽度: 80")
        self.trapezoid_side_label = QLabel("斜边方向: 左侧")

        for label in [self.trapezoid_top_label, self.trapezoid_bottom_label, self.trapezoid_side_label]:
            label.setStyleSheet("color: #8E8E93; font-size: 9pt;")
            trapezoid_layout.addWidget(label)

        self.trapezoid_info_widget.setLayout(trapezoid_layout)

        # 多边形信息显示
        self.polygon_info_widget = QWidget()
        polygon_layout = QVBoxLayout()
        polygon_layout.setSpacing(5)

        self.polygon_rotation_label = QLabel("旋转角度: 0°")
        self.polygon_radius_label = QLabel("圆角半径: 0")

        for label in [self.polygon_rotation_label, self.polygon_radius_label]:
            label.setStyleSheet("color: #8E8E93; font-size: 9pt;")
            polygon_layout.addWidget(label)

        self.polygon_info_widget.setLayout(polygon_layout)

    def create_polygon_controls(self):
        """创建多边形参数控件 - 已废弃，参数已合并到基本属性面板"""
        # 此方法已废弃，保留空实现以保持兼容性
        pass

    def update_parameter_info_display(self, shape_type: ShapeType):
        """更新参数信息显示"""
        # 清除当前参数控件
        for i in reversed(range(self.params_layout.count())):
            item = self.params_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        # 更新当前形状标签
        shape_names = {
            ShapeType.RECTANGLE: "矩形",
            ShapeType.RIGHT_TRAPEZOID: "直角梯形",
            ShapeType.CIRCLE: "圆形",
            ShapeType.PENTAGON: "正五边形",
            ShapeType.HEXAGON: "正六边形"
        }
        shape_name = shape_names.get(shape_type, "矩形")
        self.current_shape_label.setText(f"当前形状: {shape_name}")

        # 根据形状类型添加相应信息
        if shape_type == ShapeType.RIGHT_TRAPEZOID:
            self.params_layout.addWidget(self.current_shape_label)
            self.params_layout.addWidget(self.trapezoid_info_widget)
        elif shape_type in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
            self.params_layout.addWidget(self.current_shape_label)
            self.params_layout.addWidget(self.polygon_info_widget)
        else:
            # 矩形和圆形不需要额外参数
            self.params_layout.addWidget(self.current_shape_label)
            label = QLabel("该形状无额外参数")
            label.setStyleSheet("color: #8E8E93; font-style: italic;")
            self.params_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)

    def on_shape_changed(self, index):
        """形状选择改变事件"""
        if self._updating or not self._layer:
            return

        shape_types = [
            ShapeType.RECTANGLE,
            ShapeType.RIGHT_TRAPEZOID,
            ShapeType.CIRCLE,
            ShapeType.PENTAGON,
            ShapeType.HEXAGON
        ]

        if index < len(shape_types):
            new_shape = shape_types[index]
            self._layer.shape_type = new_shape
            self.show_shape_parameters(new_shape)
            if self.shape_preview:
                self.shape_preview.set_shape_type(new_shape)
                self.shape_preview.update()
            self.shape_changed.emit()

    def on_trapezoid_param_changed(self):
        """梯形参数改变事件"""
        if self._updating or not self._layer:
            return

        self._layer.trapezoid_top_width = self.trapezoid_top_width_spin.value()
        self._layer.trapezoid_bottom_width = self.trapezoid_bottom_width_spin.value()
        self._layer.trapezoid_slope_side = "right" if self.trapezoid_side_combo.currentIndex() == 0 else "left"

        if self.shape_preview:
            self.shape_preview.update()
        self.parameter_changed.emit()

    def on_polygon_param_changed(self):
        """多边形参数改变事件"""
        if self._updating or not self._layer:
            return

        self._layer.polygon_rotation = self.polygon_rotation_spin.value()
        self._layer.polygon_corner_radius = self.polygon_corner_radius_spin.value()

        self.shape_preview.update()
        self.parameter_changed.emit()

    def set_polygon_rotation(self, angle):
        """设置多边形旋转角度 - 通过基本属性面板更新"""
        if self._layer and not self._updating:
            # 直接更新图层属性
            self._layer.polygon_rotation = angle

            # 更新显示
            if hasattr(self, 'current_rotation_label'):
                self.current_rotation_label.setText(f"当前角度: {angle}°")
            if hasattr(self, 'polygon_rotation_label'):
                self.polygon_rotation_label.setText(f"旋转角度: {angle}°")

            # 更新形状预览
            if self.shape_preview:
                self.shape_preview.set_polygon_params(angle, 5 if self._layer.shape_type == ShapeType.PENTAGON else 6)
                self.shape_preview.update()

            # 触发参数变更信号
            self.parameter_changed.emit()

    def connect_signals(self):
        """连接所有信号"""
        # 快速旋转按钮信号（保留独有功能）
        if self.rotate_0_btn:
            self.rotate_0_btn.clicked.connect(lambda: self.set_polygon_rotation(0))
        if self.rotate_90_btn:
            self.rotate_90_btn.clicked.connect(lambda: self.set_polygon_rotation(90))
        if self.rotate_180_btn:
            self.rotate_180_btn.clicked.connect(lambda: self.set_polygon_rotation(180))
        if self.rotate_270_btn:
            self.rotate_270_btn.clicked.connect(lambda: self.set_polygon_rotation(270))

    def set_layer(self, layer: ShapedLayer):
        """设置当前编辑的图层"""
        self._layer = layer
        self.update_ui_from_layer()

    def update_ui_from_layer(self):
        """从图层更新UI显示"""
        if not self._layer or self._updating:
            return

        self._updating = True
        try:
            # 更新形状信息显示（不再更新形状选择下拉框）
            self.update_parameter_info_display(self._layer.shape_type)

            # 更新梯形参数信息（只读显示）
            if hasattr(self._layer, 'trapezoid_top_width'):
                self.trapezoid_top_label.setText(f"上底宽度: {self._layer.trapezoid_top_width}")
            if hasattr(self._layer, 'trapezoid_bottom_width'):
                self.trapezoid_bottom_label.setText(f"下底宽度: {self._layer.trapezoid_bottom_width}")
            if hasattr(self._layer, 'trapezoid_slope_side'):
                side_text = "右侧" if self._layer.trapezoid_slope_side == "right" else "左侧"
                self.trapezoid_side_label.setText(f"斜边方向: {side_text}")

            # 更新多边形参数信息（只读显示）
            if hasattr(self._layer, 'polygon_rotation'):
                self.polygon_rotation_label.setText(f"旋转角度: {self._layer.polygon_rotation}°")
                self.current_rotation_label.setText(f"当前角度: {self._layer.polygon_rotation}°")
            if hasattr(self._layer, 'polygon_corner_radius'):
                self.polygon_radius_label.setText(f"圆角半径: {self._layer.polygon_corner_radius}")

            # 更新形状预览
            if self.shape_preview:
                self.shape_preview.set_shape_type(self._layer.shape_type)
                if hasattr(self._layer, 'trapezoid_top_width') and hasattr(self._layer, 'trapezoid_bottom_width') and hasattr(self._layer, 'trapezoid_slope_side'):
                    self.shape_preview.set_trapezoid_params(
                        self._layer.trapezoid_top_width,
                        self._layer.trapezoid_bottom_width,
                        self._layer.trapezoid_slope_side
                    )
                if hasattr(self._layer, 'polygon_rotation'):
                    self.shape_preview.set_polygon_params(
                        self._layer.polygon_rotation,
                        5 if self._layer.shape_type == ShapeType.PENTAGON else 6
                    )
                self.shape_preview.update()

        finally:
            self._updating = False


class ShapedLayerDialog(QDialog):
    """异形图层编辑对话框"""

    def __init__(self, layer=None, parent=None):
        super().__init__(parent)
        self._layer = layer
        self.setWindowTitle("编辑异形图层")
        self.setModal(True)
        self.resize(400, 500)
        self.init_ui()

        if layer:
            self.panel.set_layer(layer)

    def init_ui(self):
        """初始化UI界面"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 创建面板
        self.panel = ShapedLayerPanel()
        layout.addWidget(self.panel)

        # 按钮框
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def set_layer(self, layer):
        """设置图层"""
        self._layer = layer
        self.panel.set_layer(layer)

    def get_layer(self):
        """获取图层"""
        return self._layer


class ShapePreviewWidget(QWidget):
    """形状预览控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shape_type = ShapeType.RECTANGLE
        self._trapezoid_top_width = 60
        self._trapezoid_bottom_width = 48
        self._trapezoid_slope_side = "right"
        self._polygon_rotation = 0
        self._polygon_sides = 5
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("ShapePreviewWidget { background-color: #1F1F1F; border: 1px solid #303033; border-radius: 4px; }")
        self.setMinimumSize(80, 80)

    def set_shape_type(self, shape_type: ShapeType):
        """设置形状类型"""
        self._shape_type = shape_type
        if shape_type == ShapeType.PENTAGON:
            self._polygon_sides = 5
        elif shape_type == ShapeType.HEXAGON:
            self._polygon_sides = 6

    def set_trapezoid_params(self, top_width, bottom_width, slope_side):
        """设置梯形参数"""
        self._trapezoid_top_width = top_width
        self._trapezoid_bottom_width = bottom_width
        self._trapezoid_slope_side = slope_side

    def set_polygon_params(self, rotation, sides):
        """设置多边形参数"""
        self._polygon_rotation = rotation
        self._polygon_sides = sides

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.rect())
        painter.fillRect(self.rect(), QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.setPen(QPen(QColor(74, 144, 226), 2))
        painter.setBrush(QColor(74, 144, 226, 100))
        size = min(self.width(), self.height()) - 10
        x_offset = (self.width() - size) // 2
        y_offset = (self.height() - size) // 2
        if self._shape_type == ShapeType.RECTANGLE:
            painter.drawRect(x_offset, y_offset, size, size)
        elif self._shape_type == ShapeType.RIGHT_TRAPEZOID:
            top_width = int(size * (self._trapezoid_top_width / 100.0))
            bottom_width = int(size * (self._trapezoid_bottom_width / 100.0))
            if self._trapezoid_slope_side == "right":
                points = [
                    QPoint(x_offset, y_offset),
                    QPoint(x_offset + top_width, y_offset),
                    QPoint(x_offset + bottom_width, y_offset + size),
                    QPoint(x_offset, y_offset + size)
                ]
            else:
                points = [
                    QPoint(x_offset + size - top_width, y_offset),
                    QPoint(x_offset + size, y_offset),
                    QPoint(x_offset + size, y_offset + size),
                    QPoint(x_offset + size - bottom_width, y_offset + size)
                ]
            painter.drawPolygon(points)
        elif self._shape_type == ShapeType.CIRCLE:
            painter.drawEllipse(x_offset, y_offset, size, size)
        elif self._shape_type in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
            import math
            center_x = self.width() // 2
            center_y = self.height() // 2
            radius = size // 2
            points = []
            for i in range(self._polygon_sides):
                angle = 2 * math.pi * i / self._polygon_sides + math.radians(self._polygon_rotation)
                x = center_x + radius * math.cos(angle - math.pi / 2)
                y = center_y + radius * math.sin(angle - math.pi / 2)
                points.append(QPoint(int(x), int(y)))
            painter.drawPolygon(points)

    def sizeHint(self):
        return QSize(80, 80)

    def minimumSizeHint(self):
        return QSize(80, 80)


# 测试函数
def test_shaped_layer_panel():
    """测试异形图层面板"""
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

    app = QApplication(sys.argv)

    # 创建测试窗口
    window = QMainWindow()
    window.setWindowTitle("异形图层面板测试")
    window.resize(400, 600)

    # 创建测试图层
    from app.models.shaped_layer_new import ShapedLayer, ShapeType
    test_layer = ShapedLayer("测试异形图层", shape_type=ShapeType.HEXAGON)

    # 创建面板
    panel = ShapedLayerPanel()
    panel.set_layer(test_layer)

    # 连接信号
    def on_shape_changed():
        print(f"形状改变: {test_layer.get_shape_description()}")

    def on_param_changed():
        print(f"参数改变: {test_layer.get_shape_description()}")

    panel.shape_changed.connect(on_shape_changed)
    panel.parameter_changed.connect(on_param_changed)

    # 设置窗口内容
    central_widget = QWidget()
    layout = QVBoxLayout()
    layout.addWidget(panel)
    central_widget.setLayout(layout)
    window.setCentralWidget(central_widget)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    test_shaped_layer_panel()
