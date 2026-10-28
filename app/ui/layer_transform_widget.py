from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
                           QSlider, QFormLayout, QButtonGroup)
from PySide6.QtCore import Qt, Signal
from app.ui.design_tokens import Tokens
from app.ui.property_widgets import blank_field_label, field_label, property_form
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor

class LayerTransformWidget(QWidget):
    """图层变换控制组件"""

    # 信号定义
    rotation_changed = Signal(float)       # 旋转角度改变
    flip_horizontal_changed = Signal(bool)  # 水平翻转改变
    flip_vertical_changed = Signal(bool)    # 垂直翻转改变
    transform_reset = Signal()             # 重置变换

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_layer = None
        self._updating = False  # 防止递归更新

        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        transform_layout = layout

        # 旋转控制
        rotation_layout = property_form()

        # 旋转角度数值输入
        rotation_input_layout = QHBoxLayout()

        self.rotation_spinbox = QDoubleSpinBox()
        self.rotation_spinbox.setRange(-360.0, 360.0)
        self.rotation_spinbox.setValue(0.0)
        self.rotation_spinbox.setSuffix("°")
        self.rotation_spinbox.setDecimals(1)
        self.rotation_spinbox.setSingleStep(1.0)
        self.rotation_spinbox.valueChanged.connect(self.on_rotation_changed)
        rotation_input_layout.addWidget(self.rotation_spinbox)

        # 重置旋转按钮
        reset_rotation_btn = QPushButton("重置")
        reset_rotation_btn.setMaximumWidth(42)
        reset_rotation_btn.clicked.connect(self.reset_rotation)
        rotation_input_layout.addWidget(reset_rotation_btn)

        rotation_layout.addRow(field_label("旋转角度:"), rotation_input_layout)

        # 旋转滑条
        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(-360, 360)
        self.rotation_slider.setValue(0)
        self.rotation_slider.setTickPosition(QSlider.TicksBelow)
        self.rotation_slider.setTickInterval(90)
        self.rotation_slider.valueChanged.connect(self.on_rotation_slider_changed)
        rotation_layout.addRow(blank_field_label(), self.rotation_slider)

        transform_layout.addLayout(rotation_layout)

        # 翻转控制
        flip_layout = QHBoxLayout()
        flip_layout.addWidget(QLabel("翻转:"))

        self.flip_horizontal_check = QCheckBox("水平翻转")
        self.flip_horizontal_check.setToolTip("左右镜像翻转")
        self.flip_horizontal_check.toggled.connect(self.on_flip_horizontal_changed)
        flip_layout.addWidget(self.flip_horizontal_check)

        self.flip_vertical_check = QCheckBox("垂直翻转")
        self.flip_vertical_check.setToolTip("上下镜像翻转")
        self.flip_vertical_check.toggled.connect(self.on_flip_vertical_changed)
        flip_layout.addWidget(self.flip_vertical_check)

        flip_layout.addStretch()
        transform_layout.addLayout(flip_layout)

        # 全局控制按钮
        global_controls_layout = QHBoxLayout()

        # 重置所有变换按钮
        reset_all_btn = QPushButton("重置所有变换")
        reset_all_btn.setToolTip("将旋转和翻转都重置为初始状态")
        reset_all_btn.clicked.connect(self.reset_all_transforms)
        global_controls_layout.addWidget(reset_all_btn)

        global_controls_layout.addStretch()

        # 变换信息显示
        self.transform_info_label = QLabel("当前: 无变换")
        self.transform_info_label.setStyleSheet(f"color: {Tokens.TEXT_DISABLED}; font-size: {Tokens.FONT_SIZE_SMALL}px;")
        global_controls_layout.addWidget(self.transform_info_label)

        transform_layout.addLayout(global_controls_layout)

        # 初始状态设置为禁用
        self.set_controls_enabled(False)

    def set_layer(self, layer):
        """设置当前图层"""
        self.current_layer = layer

        if layer:
            self.set_controls_enabled(True)
            self.update_from_layer()
        else:
            self.set_controls_enabled(False)
            self.clear_values()

    def set_controls_enabled(self, enabled):
        """设置控件启用状态"""
        self.rotation_spinbox.setEnabled(enabled)
        self.rotation_slider.setEnabled(enabled)
        self.flip_horizontal_check.setEnabled(enabled)
        self.flip_vertical_check.setEnabled(enabled)

        # 获取组内所有按钮并设置状态
        for button in self.findChildren(QPushButton):
            button.setEnabled(enabled)

    def update_from_layer(self):
        """从图层更新控件值"""
        if not self.current_layer:
            return

        self._updating = True
        try:
            # 更新旋转值
            rotation = getattr(self.current_layer, 'rotation', 0.0)
            self.rotation_spinbox.setValue(rotation)
            self.rotation_slider.setValue(int(rotation))

            # 更新翻转状态
            flip_h = getattr(self.current_layer, 'flip_horizontal', False)
            flip_v = getattr(self.current_layer, 'flip_vertical', False)
            self.flip_horizontal_check.setChecked(flip_h)
            self.flip_vertical_check.setChecked(flip_v)

            # 更新信息显示
            self.update_transform_info()

        finally:
            self._updating = False

    def clear_values(self):
        """清空控件值"""
        self._updating = True
        try:
            self.rotation_spinbox.setValue(0.0)
            self.rotation_slider.setValue(0)
            self.flip_horizontal_check.setChecked(False)
            self.flip_vertical_check.setChecked(False)
            self.transform_info_label.setText("当前: 无图层")
        finally:
            self._updating = False

    def on_rotation_changed(self, value):
        """旋转角度改变处理"""
        if self._updating or not self.current_layer:
            return

        # 同步滑条
        self._updating = True
        self.rotation_slider.setValue(int(value))
        self._updating = False

        # 发出信号
        self.rotation_changed.emit(value)
        self.update_transform_info()

    def on_rotation_slider_changed(self, value):
        """旋转滑条改变处理"""
        if self._updating or not self.current_layer:
            return

        # 同步数值框
        self._updating = True
        self.rotation_spinbox.setValue(float(value))
        self._updating = False

        # 发出信号
        self.rotation_changed.emit(float(value))
        self.update_transform_info()

    def on_flip_horizontal_changed(self, checked):
        """水平翻转改变处理"""
        if self._updating or not self.current_layer:
            return

        self.flip_horizontal_changed.emit(checked)
        self.update_transform_info()

    def on_flip_vertical_changed(self, checked):
        """垂直翻转改变处理"""
        if self._updating or not self.current_layer:
            return

        self.flip_vertical_changed.emit(checked)
        self.update_transform_info()

    def reset_rotation(self):
        """重置旋转"""
        if not self.current_layer:
            return

        self._updating = True
        try:
            self.rotation_spinbox.setValue(0.0)
            self.rotation_slider.setValue(0)
        finally:
            self._updating = False

        self.rotation_changed.emit(0.0)
        self.update_transform_info()

    def reset_all_transforms(self):
        """重置所有变换"""
        if not self.current_layer:
            return

        self._updating = True
        try:
            self.rotation_spinbox.setValue(0.0)
            self.rotation_slider.setValue(0)
            self.flip_horizontal_check.setChecked(False)
            self.flip_vertical_check.setChecked(False)
        finally:
            self._updating = False

        self.transform_reset.emit()
        self.update_transform_info()

    def update_transform_info(self):
        """更新变换信息显示"""
        if not self.current_layer:
            self.transform_info_label.setText("当前: 无图层")
            return

        info_parts = []

        # 旋转信息
        rotation = self.rotation_spinbox.value()
        if abs(rotation) > 0.001:
            info_parts.append(f"旋转{rotation:.1f}°")

        # 翻转信息
        if self.flip_horizontal_check.isChecked():
            info_parts.append("水平翻转")

        if self.flip_vertical_check.isChecked():
            info_parts.append("垂直翻转")

        if info_parts:
            info_text = "当前: " + ", ".join(info_parts)
        else:
            info_text = "当前: 无变换"

        self.transform_info_label.setText(info_text) 
