from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                           QPushButton, QGroupBox, QRadioButton,
                           QButtonGroup)
from PySide6.QtCore import Qt
from .canvas_size_widget import CanvasSizeWidget

class ResizeCanvasDialog(QDialog):
    """画布尺寸调整对话框"""

    def __init__(self, current_width, current_height, parent=None):
        super().__init__(parent)

        self.setWindowTitle("修改画布尺寸")
        self.setMinimumWidth(400)

        # 保存当前尺寸
        self.current_width = current_width
        self.current_height = current_height

        # 创建布局
        main_layout = QVBoxLayout(self)

        # 尺寸设置组件（启用比例锁定）
        self.size_widget = CanvasSizeWidget(current_width, current_height, True, self)
        main_layout.addWidget(self.size_widget)

        # 图层调整选项组
        adjustment_group = QGroupBox("图层调整")
        adjustment_layout = QVBoxLayout()

        # 创建单选按钮组
        self.button_group = QButtonGroup(self)

        # 按比例缩放选项
        self.scale_radio = QRadioButton("按比例缩放位置 (保持相对位置)")
        self.scale_radio.setChecked(True)
        self.button_group.addButton(self.scale_radio, 0)
        adjustment_layout.addWidget(self.scale_radio)

        # 居中选项
        self.center_radio = QRadioButton("居中所有图层")
        self.button_group.addButton(self.center_radio, 1)
        adjustment_layout.addWidget(self.center_radio)

        # 左上角对齐选项
        self.top_left_radio = QRadioButton("左上角对齐所有图层")
        self.button_group.addButton(self.top_left_radio, 2)
        adjustment_layout.addWidget(self.top_left_radio)

        # 保持绝对位置选项
        self.keep_pos_radio = QRadioButton("保持图层绝对位置不变")
        self.button_group.addButton(self.keep_pos_radio, 3)
        adjustment_layout.addWidget(self.keep_pos_radio)

        adjustment_group.setLayout(adjustment_layout)
        main_layout.addWidget(adjustment_group)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 取消按钮
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        # 确定按钮
        ok_button = QPushButton("确定")
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)

        main_layout.addLayout(button_layout)

    def get_adjustment_mode(self):
        """获取选择的图层调整模式"""
        return self.button_group.checkedId()

    def get_canvas_size(self):
        """获取设置的画布尺寸"""
        return self.size_widget.get_size() 