from app.ui.design_spec import Space as _Space
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QSpinBox, QPushButton, QGroupBox,
                               QGridLayout, QLineEdit, QFileDialog, QCheckBox,
                               QDialogButtonBox, QTextEdit, QWidget)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
try:
    from app.models.shaped_layer_new import ShapedLayer, ShapeType
except ImportError:
    from app.models.shaped_layer_new import ShapedLayer, ShapeType
from app.ui.shaped_layer_panel import ShapePreviewWidget


class AddShapedLayerDialog(QDialog):
    """添加异形图层对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加异形图层")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)
        self.init_ui()

    def init_ui(self):
        """初始化UI界面"""
        layout = QVBoxLayout()
        layout.setSpacing(_Space.LG)
        layout.setContentsMargins(20, 20, 20, 20)

        # 基本信息组
        basic_group = QGroupBox("基本信息")
        basic_layout = QGridLayout()
        basic_layout.setSpacing(_Space.SM)

        # 图层名称
        basic_layout.addWidget(QLabel("图层名称:"), 0, 0)
        self.name_edit = QLineEdit("异形图层")
        self.name_edit.setPlaceholderText("请输入图层名称")
        basic_layout.addWidget(self.name_edit, 0, 1)

        # 形状类型
        basic_layout.addWidget(QLabel("形状类型:"), 1, 0)
        self.shape_combo = QComboBox()
        self.shape_combo.addItems([
            "矩形",
            "直角梯形",
            "圆形",
            "正五边形",
            "正六边形"
        ])
        self.shape_combo.currentIndexChanged.connect(self.on_shape_changed)
        basic_layout.addWidget(self.shape_combo, 1, 1)

        # 位置设置
        basic_layout.addWidget(QLabel("X坐标:"), 2, 0)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(-1000, 2000)
        self.x_spin.setValue(0)
        basic_layout.addWidget(self.x_spin, 2, 1)

        basic_layout.addWidget(QLabel("Y坐标:"), 3, 0)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(-1000, 2000)
        self.y_spin.setValue(0)
        basic_layout.addWidget(self.y_spin, 3, 1)

        # 尺寸设置
        basic_layout.addWidget(QLabel("宽度:"), 2, 2)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(10, 2000)
        self.width_spin.setValue(200)
        self.width_spin.valueChanged.connect(self.update_preview)
        basic_layout.addWidget(self.width_spin, 2, 3)

        basic_layout.addWidget(QLabel("高度:"), 3, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(10, 2000)
        self.height_spin.setValue(200)
        self.height_spin.valueChanged.connect(self.update_preview)
        basic_layout.addWidget(self.height_spin, 3, 3)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # 形状预览组
        preview_group = QGroupBox("形状预览")
        preview_layout = QHBoxLayout()

        self.shape_preview = ShapePreviewWidget()
        self.shape_preview.setFixedSize(120, 120)
        self.shape_preview.setStyleSheet("""
            ShapePreviewWidget {
                border: 2px solid #ccc;
                border-radius: 5px;
                background-color: #f8f8f8;
            }
        """)
        preview_layout.addWidget(self.shape_preview, alignment=Qt.AlignmentFlag.AlignCenter)

        # 形状参数控制
        self.params_widget = QWidget()
        self.params_layout = QVBoxLayout()
        self.params_widget.setLayout(self.params_layout)
        preview_layout.addWidget(self.params_widget)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # 图像源设置组
        source_group = QGroupBox("图像源设置")
        source_layout = QVBoxLayout()
        source_layout.setSpacing(_Space.SM)

        # 图像路径
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("图像路径:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("请选择图像文件或文件夹")
        path_layout.addWidget(self.path_edit)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.browse_image)
        path_layout.addWidget(browse_btn)

        source_layout.addLayout(path_layout)

        # 选项
        options_layout = QHBoxLayout()
        self.is_folder_check = QCheckBox("图像源为文件夹")
        self.is_folder_check.stateChanged.connect(self.on_folder_check_changed)
        options_layout.addWidget(self.is_folder_check)

        self.use_original_size_check = QCheckBox("使用原始尺寸")
        self.use_original_size_check.stateChanged.connect(self.update_preview)
        options_layout.addWidget(self.use_original_size_check)

        source_layout.addLayout(options_layout)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # 对话框按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # 初始化形状参数控件
        self.create_shape_parameter_controls()
        self.show_shape_parameters(ShapeType.RECTANGLE)
        self.update_preview()

    def create_shape_parameter_controls(self):
        """创建形状参数控件"""
        # 梯形参数
        self.trapezoid_widget = QWidget()
        trapezoid_layout = QGridLayout()

        trapezoid_layout.addWidget(QLabel("上底宽度比例:"), 0, 0)
        self.trapezoid_top_ratio_spin = QSpinBox()
        self.trapezoid_top_ratio_spin.setRange(30, 100)
        self.trapezoid_top_ratio_spin.setValue(100)
        self.trapezoid_top_ratio_spin.setSuffix("%")
        self.trapezoid_top_ratio_spin.valueChanged.connect(self.update_preview)
        trapezoid_layout.addWidget(self.trapezoid_top_ratio_spin, 0, 1)

        trapezoid_layout.addWidget(QLabel("下底宽度比例:"), 1, 0)
        self.trapezoid_bottom_ratio_spin = QSpinBox()
        self.trapezoid_bottom_ratio_spin.setRange(30, 100)
        self.trapezoid_bottom_ratio_spin.setValue(80)
        self.trapezoid_bottom_ratio_spin.setSuffix("%")
        self.trapezoid_bottom_ratio_spin.valueChanged.connect(self.update_preview)
        trapezoid_layout.addWidget(self.trapezoid_bottom_ratio_spin, 1, 1)

        trapezoid_layout.addWidget(QLabel("斜边方向:"), 2, 0)
        self.trapezoid_side_combo = QComboBox()
        self.trapezoid_side_combo.addItems(["右侧", "左侧"])
        self.trapezoid_side_combo.currentIndexChanged.connect(self.update_preview)
        trapezoid_layout.addWidget(self.trapezoid_side_combo, 2, 1)

        self.trapezoid_widget.setLayout(trapezoid_layout)

        # 多边形参数
        self.polygon_widget = QWidget()
        polygon_layout = QGridLayout()

        polygon_layout.addWidget(QLabel("旋转角度:"), 0, 0)
        self.polygon_rotation_spin = QSpinBox()
        self.polygon_rotation_spin.setRange(0, 360)
        self.polygon_rotation_spin.setValue(0)
        self.polygon_rotation_spin.setSuffix("°")
        self.polygon_rotation_spin.setSingleStep(15)
        self.polygon_rotation_spin.valueChanged.connect(self.update_preview)
        polygon_layout.addWidget(self.polygon_rotation_spin, 0, 1)

        polygon_layout.addWidget(QLabel("圆角半径:"), 1, 0)
        self.polygon_corner_radius_spin = QSpinBox()
        self.polygon_corner_radius_spin.setRange(0, 30)
        self.polygon_corner_radius_spin.setValue(0)
        self.polygon_corner_radius_spin.setSuffix("px")
        self.polygon_corner_radius_spin.valueChanged.connect(self.update_preview)
        polygon_layout.addWidget(self.polygon_corner_radius_spin, 1, 1)

        self.polygon_widget.setLayout(polygon_layout)

    def show_shape_parameters(self, shape_type: ShapeType):
        """显示对应形状的参数控件"""
        # 清除当前参数控件
        for i in reversed(range(self.params_layout.count())):
            widget = self.params_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # 根据形状类型添加相应控件
        if shape_type == ShapeType.RIGHT_TRAPEZOID:
            self.params_layout.addWidget(self.trapezoid_widget)
        elif shape_type in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
            self.params_layout.addWidget(self.polygon_widget)
        else:
            # 矩形和圆形不需要额外参数
            label = QLabel("该形状无额外参数")
            label.setStyleSheet("color: #8E8E93; font-style: italic;")
            self.params_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)

    def on_shape_changed(self, index):
        """形状选择改变"""
        shape_types = [
            ShapeType.RECTANGLE,
            ShapeType.RIGHT_TRAPEZOID,
            ShapeType.CIRCLE,
            ShapeType.PENTAGON,
            ShapeType.HEXAGON
        ]

        if index < len(shape_types):
            shape_type = shape_types[index]
            self.show_shape_parameters(shape_type)
            self.update_preview()

    def on_folder_check_changed(self, state):
        """文件夹选项改变"""
        if state == Qt.CheckState.Checked:
            self.use_original_size_check.setEnabled(False)
        else:
            self.use_original_size_check.setEnabled(True)

    def browse_image(self):
        """浏览图像文件"""
        if self.is_folder_check.isChecked():
            # 选择文件夹
            folder = QFileDialog.getExistingDirectory(
                self,
                "选择图像文件夹",
                "",
                QFileDialog.Option.ShowDirsOnly
            )
            if folder:
                self.path_edit.setText(folder)
        else:
            # 选择文件
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择图像文件",
                "",
                "图像文件 (*.png *.jpg *.jpeg *.gif *.bmp *.tiff);;所有文件 (*.*)"
            )
            if file_path:
                self.path_edit.setText(file_path)

    def update_preview(self):
        """更新形状预览"""
        # 获取当前形状类型
        shape_types = [
            ShapeType.RECTANGLE,
            ShapeType.RIGHT_TRAPEZOID,
            ShapeType.CIRCLE,
            ShapeType.PENTAGON,
            ShapeType.HEXAGON
        ]

        current_index = self.shape_combo.currentIndex()
        if current_index < len(shape_types):
            shape_type = shape_types[current_index]

            # 设置预览形状类型
            self.shape_preview.set_shape_type(shape_type)

            # 设置梯形参数
            if shape_type == ShapeType.RIGHT_TRAPEZOID:
                top_ratio = self.trapezoid_top_ratio_spin.value()
                bottom_ratio = self.trapezoid_bottom_ratio_spin.value()
                slope_side = "right" if self.trapezoid_side_combo.currentIndex() == 0 else "left"

                # 计算实际尺寸
                width = self.width_spin.value()
                top_width = int(width * top_ratio / 100)
                bottom_width = int(width * bottom_ratio / 100)

                self.shape_preview.set_trapezoid_params(top_width, bottom_width, slope_side)

            # 设置多边形参数
            elif shape_type in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
                rotation = self.polygon_rotation_spin.value()
                sides = 5 if shape_type == ShapeType.PENTAGON else 6
                self.shape_preview.set_polygon_params(rotation, sides)

            self.shape_preview.update()

    def get_created_layer(self):
        """获取创建的异形图层"""
        # 获取基本参数
        name = self.name_edit.text() or "异形图层"
        x = self.x_spin.value()
        y = self.y_spin.value()
        width = self.width_spin.value()
        height = self.height_spin.value()
        image_source = self.path_edit.text() if self.path_edit.text() else None
        use_original_size = self.use_original_size_check.isChecked()
        is_folder = self.is_folder_check.isChecked()

        # 获取形状类型
        shape_types = [
            ShapeType.RECTANGLE,
            ShapeType.RIGHT_TRAPEZOID,
            ShapeType.CIRCLE,
            ShapeType.PENTAGON,
            ShapeType.HEXAGON
        ]

        current_index = self.shape_combo.currentIndex()
        shape_type = shape_types[current_index] if current_index < len(shape_types) else ShapeType.RECTANGLE

        # 创建异形图层
        layer = ShapedLayer(
            name=name,
            x=x,
            y=y,
            width=width,
            height=height,
            image_source=image_source,
            use_original_size=use_original_size,
            is_folder=is_folder,
            shape_type=shape_type
        )

        # 设置形状特有参数
        if shape_type == ShapeType.RIGHT_TRAPEZOID:
            top_ratio = self.trapezoid_top_ratio_spin.value()
            bottom_ratio = self.trapezoid_bottom_ratio_spin.value()
            slope_side = "right" if self.trapezoid_side_combo.currentIndex() == 0 else "left"

            layer.trapezoid_top_width = int(width * top_ratio / 100)
            layer.trapezoid_bottom_width = int(width * bottom_ratio / 100)
            layer.trapezoid_slope_side = slope_side

        elif shape_type in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
            layer.polygon_rotation = self.polygon_rotation_spin.value()
            layer.polygon_corner_radius = self.polygon_corner_radius_spin.value()

        return layer

    def accept(self):
        """确认创建图层"""
        # 验证输入
        if not self.name_edit.text().strip():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "警告", "请输入图层名称")
            return

        super().accept()


# 测试函数
def test_add_shaped_layer_dialog():
    """测试添加异形图层对话框"""
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel

    app = QApplication(sys.argv)

    # 创建测试窗口
    window = QMainWindow()
    window.setWindowTitle("添加异形图层对话框测试")
    window.resize(800, 700)

    # 显示对话框
    dialog = AddShapedLayerDialog(window)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        # 获取创建的图层
        layer = dialog.get_created_layer()

        # 显示结果
        result_widget = QWidget()
        result_layout = QVBoxLayout()

        result_label = QLabel(f"创建图层成功！\n\n"
                            f"名称: {layer.name}\n"
                            f"形状: {layer.get_shape_description()}\n"
                            f"位置: ({layer.x}, {layer.y})\n"
                            f"尺寸: {layer.width}x{layer.height}\n"
                            f"图像源: {layer.image_source or '无'}")
        result_layout.addWidget(result_label)

        result_widget.setLayout(result_layout)
        window.setCentralWidget(result_widget)

        window.show()
        sys.exit(app.exec())
    else:
        print("用户取消了创建")


if __name__ == "__main__":
    test_add_shaped_layer_dialog()