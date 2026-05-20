from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
                           QGroupBox, QSlider, QFormLayout)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor

class LayerRandomTransformWidget(QWidget):
    """图层随机变换控制组件"""

    # 信号定义
    random_position_enabled_changed = Signal(bool)
    random_position_range_changed = Signal(int)
    random_scale_enabled_changed = Signal(bool)
    random_scale_min_changed = Signal(float)
    random_scale_max_changed = Signal(float)
    random_rotation_enabled_changed = Signal(bool)
    random_rotation_range_changed = Signal(float)
    generate_random_params = Signal()  # 生成新的随机参数
    reset_random_params = Signal()     # 重置随机参数

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

        # 随机变换组
        random_group = QGroupBox("随机变换")
        random_layout = QVBoxLayout(random_group)
        random_layout.setContentsMargins(6, 6, 6, 6)
        random_layout.setSpacing(4)

        # 随机位置抖动
        position_layout = QFormLayout()
        position_layout.setHorizontalSpacing(5)
        position_layout.setVerticalSpacing(3)

        self.position_enabled_check = QCheckBox("启用随机位置抖动")
        self.position_enabled_check.setToolTip("启用后图层位置会在基础位置上随机偏移")
        self.position_enabled_check.toggled.connect(self.on_position_enabled_changed)
        position_layout.addRow(self.position_enabled_check)

        self.position_range_spin = QSpinBox()
        self.position_range_spin.setRange(0, 200)
        self.position_range_spin.setValue(10)
        self.position_range_spin.setSuffix(" 像素")
        self.position_range_spin.setToolTip("位置偏移的最大范围（±像素）")
        self.position_range_spin.valueChanged.connect(self.on_position_range_changed)
        position_layout.addRow("抖动范围:", self.position_range_spin)

        random_layout.addLayout(position_layout)

        # 分隔线
        random_layout.addWidget(self.create_separator())

        # 随机缩放
        scale_layout = QFormLayout()
        scale_layout.setHorizontalSpacing(5)
        scale_layout.setVerticalSpacing(3)

        self.scale_enabled_check = QCheckBox("启用随机缩放")
        self.scale_enabled_check.setToolTip("启用后图层会随机缩放")
        self.scale_enabled_check.toggled.connect(self.on_scale_enabled_changed)
        scale_layout.addRow(self.scale_enabled_check)

        scale_range_layout = QHBoxLayout()

        self.scale_min_spin = QDoubleSpinBox()
        self.scale_min_spin.setRange(0.1, 2.0)
        self.scale_min_spin.setValue(0.9)
        self.scale_min_spin.setSingleStep(0.05)
        self.scale_min_spin.setDecimals(2)
        self.scale_min_spin.setToolTip("最小缩放比例")
        self.scale_min_spin.valueChanged.connect(self.on_scale_min_changed)
        scale_range_layout.addWidget(QLabel("最小:"))
        scale_range_layout.addWidget(self.scale_min_spin)

        self.scale_max_spin = QDoubleSpinBox()
        self.scale_max_spin.setRange(0.1, 2.0)
        self.scale_max_spin.setValue(1.1)
        self.scale_max_spin.setSingleStep(0.05)
        self.scale_max_spin.setDecimals(2)
        self.scale_max_spin.setToolTip("最大缩放比例")
        self.scale_max_spin.valueChanged.connect(self.on_scale_max_changed)
        scale_range_layout.addWidget(QLabel("最大:"))
        scale_range_layout.addWidget(self.scale_max_spin)

        scale_layout.addRow("缩放范围:", scale_range_layout)

        random_layout.addLayout(scale_layout)

        # 分隔线
        random_layout.addWidget(self.create_separator())

        # 随机旋转
        rotation_layout = QFormLayout()
        rotation_layout.setHorizontalSpacing(5)
        rotation_layout.setVerticalSpacing(3)

        self.rotation_enabled_check = QCheckBox("启用随机旋转")
        self.rotation_enabled_check.setToolTip("启用后图层会随机旋转")
        self.rotation_enabled_check.toggled.connect(self.on_rotation_enabled_changed)
        rotation_layout.addRow(self.rotation_enabled_check)

        self.rotation_range_spin = QDoubleSpinBox()
        self.rotation_range_spin.setRange(0, 180)
        self.rotation_range_spin.setValue(5.0)
        self.rotation_range_spin.setSingleStep(1.0)
        self.rotation_range_spin.setDecimals(1)
        self.rotation_range_spin.setSuffix("°")
        self.rotation_range_spin.setToolTip("随机旋转的角度范围（±度），例如设置5度表示在-5度到+5度之间随机旋转")
        self.rotation_range_spin.valueChanged.connect(self.on_rotation_range_changed)
        rotation_layout.addRow("旋转范围(±):", self.rotation_range_spin)

        random_layout.addLayout(rotation_layout)

        # 分隔线
        random_layout.addWidget(self.create_separator())

        # 控制按钮
        button_layout = QHBoxLayout()

        # 使用图标管理器创建随机按钮
        from app.ui.icon_manager import IconManager

        self.generate_btn = QPushButton()
        icon_text = IconManager.get_icon_text('random')
        self.generate_btn.setText(f"{icon_text} 生成随机")
        self.generate_btn.setToolTip("为当前图层生成新的随机变换参数")
        self.generate_btn.clicked.connect(self.on_generate_random)
        button_layout.addWidget(self.generate_btn)

        self.reset_btn = QPushButton(f"{IconManager.get_icon_text('undo')} 重置随机")
        self.reset_btn.setToolTip("重置当前图层的随机变换参数")
        self.reset_btn.clicked.connect(self.on_reset_random)
        button_layout.addWidget(self.reset_btn)

        random_layout.addLayout(button_layout)

        # 当前状态显示
        self.status_label = QLabel("当前: 无随机变换")
        self.status_label.setStyleSheet("color: #606064; font-size: 10px; padding: 3px;")
        self.status_label.setWordWrap(True)
        random_layout.addWidget(self.status_label)

        layout.addWidget(random_group)
        layout.addStretch()

        # 初始状态设置为禁用
        self.set_controls_enabled(False)

    def create_separator(self):
        """创建分隔线"""
        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #303033; margin: 2px 0;")
        return separator

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
        self.position_enabled_check.setEnabled(enabled)
        self.position_range_spin.setEnabled(enabled)
        self.scale_enabled_check.setEnabled(enabled)
        self.scale_min_spin.setEnabled(enabled)
        self.scale_max_spin.setEnabled(enabled)
        self.rotation_enabled_check.setEnabled(enabled)
        self.rotation_range_spin.setEnabled(enabled)
        self.generate_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)

    def update_from_layer(self):
        """从图层更新控件值"""
        if not self.current_layer:
            return

        self._updating = True
        try:
            # 更新随机位置设置
            self.position_enabled_check.setChecked(getattr(self.current_layer, 'random_position_enabled', False))
            self.position_range_spin.setValue(getattr(self.current_layer, 'random_position_range', 10))

            # 更新随机缩放设置
            self.scale_enabled_check.setChecked(getattr(self.current_layer, 'random_scale_enabled', False))
            self.scale_min_spin.setValue(getattr(self.current_layer, 'random_scale_min', 0.9))
            self.scale_max_spin.setValue(getattr(self.current_layer, 'random_scale_max', 1.1))

            # 更新随机旋转设置
            self.rotation_enabled_check.setChecked(getattr(self.current_layer, 'random_rotation_enabled', False))
            self.rotation_range_spin.setValue(getattr(self.current_layer, 'random_rotation_range', 5.0))

            # 更新状态显示
            self.update_status_display()

        finally:
            self._updating = False

    def clear_values(self):
        """清空控件值"""
        self._updating = True
        try:
            self.position_enabled_check.setChecked(False)
            self.position_range_spin.setValue(10)
            self.scale_enabled_check.setChecked(False)
            self.scale_min_spin.setValue(0.9)
            self.scale_max_spin.setValue(1.1)
            self.rotation_enabled_check.setChecked(False)
            self.rotation_range_spin.setValue(5.0)
            self.status_label.setText("当前: 无图层")
        finally:
            self._updating = False

    def on_position_enabled_changed(self, checked):
        """随机位置启用状态改变"""
        if self._updating or not self.current_layer:
            return
        self.random_position_enabled_changed.emit(checked)
        self.update_status_display()

    def on_position_range_changed(self, value):
        """随机位置范围改变"""
        if self._updating or not self.current_layer:
            return
        self.random_position_range_changed.emit(value)
        self.update_status_display()

    def on_scale_enabled_changed(self, checked):
        """随机缩放启用状态改变"""
        if self._updating or not self.current_layer:
            return
        self.random_scale_enabled_changed.emit(checked)
        self.update_status_display()

    def on_scale_min_changed(self, value):
        """最小缩放比例改变"""
        if self._updating or not self.current_layer:
            return
        # 确保最小值不大于最大值
        if value > self.scale_max_spin.value():
            self._updating = True
            self.scale_max_spin.setValue(value)
            self._updating = False
        self.random_scale_min_changed.emit(value)
        self.update_status_display()

    def on_scale_max_changed(self, value):
        """最大缩放比例改变"""
        if self._updating or not self.current_layer:
            return
        # 确保最大值不小于最小值
        if value < self.scale_min_spin.value():
            self._updating = True
            self.scale_min_spin.setValue(value)
            self._updating = False
        self.random_scale_max_changed.emit(value)
        self.update_status_display()

    def on_rotation_enabled_changed(self, checked):
        """随机旋转启用状态改变"""
        if self._updating or not self.current_layer:
            return
        self.random_rotation_enabled_changed.emit(checked)
        self.update_status_display()

    def on_rotation_range_changed(self, value):
        """随机旋转范围改变"""
        if self._updating or not self.current_layer:
            return
        self.random_rotation_range_changed.emit(value)
        self.update_status_display()

    def on_generate_random(self):
        """生成随机参数"""
        if not self.current_layer:
            return
        self.generate_random_params.emit()
        self.update_status_display()

    def on_reset_random(self):
        """重置随机参数"""
        if not self.current_layer:
            return
        self.reset_random_params.emit()
        self.update_status_display()

    def update_status_display(self):
        """更新状态显示"""
        if not self.current_layer:
            self.status_label.setText("当前: 无图层")
            return

        status_parts = []

        # 位置抖动状态
        if self.position_enabled_check.isChecked():
            offset_x = getattr(self.current_layer, '_current_random_offset_x', 0)
            offset_y = getattr(self.current_layer, '_current_random_offset_y', 0)
            status_parts.append(f"位置偏移({offset_x}, {offset_y})")

        # 缩放状态
        if self.scale_enabled_check.isChecked():
            scale = getattr(self.current_layer, '_current_random_scale', 1.0)
            status_parts.append(f"缩放{scale:.2f}")

        # 旋转状态
        if self.rotation_enabled_check.isChecked():
            rotation = getattr(self.current_layer, '_current_random_rotation', 0.0)
            status_parts.append(f"旋转{rotation:.1f}°")

        if status_parts:
            status_text = "当前随机变换: " + ", ".join(status_parts)
        else:
            status_text = "当前: 无随机变换"

        self.status_label.setText(status_text)
        safe_print(f"更新随机变换状态显示: {status_text}")  # 添加调试信息


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")
