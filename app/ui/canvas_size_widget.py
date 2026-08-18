from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QSpinBox, QComboBox, QCheckBox, QFormLayout, QPushButton)
from PySide6.QtCore import Qt, Signal, Slot

from app.utils.canvas_preset_manager import CanvasPresetManager

class CanvasSizeWidget(QWidget):
    """
    画布尺寸设置组件
    提供宽度、高度输入和预设尺寸选择功能
    """

    # 尺寸改变信号
    size_changed = Signal(int, int)  # 宽度, 高度

    def __init__(self, initial_width=800, initial_height=600,
                 maintain_ratio=False, show_preset_manager=False, parent=None):
        super().__init__(parent)

        self.initial_width = initial_width
        self.initial_height = initial_height
        self.aspect_ratio = initial_width / initial_height if initial_height != 0 else 1.0

        # 创建预设管理器
        self.preset_manager = CanvasPresetManager()

        self.setup_ui(maintain_ratio, show_preset_manager)

    def setup_ui(self, enable_ratio_lock=False, show_preset_manager=False):
        """设置UI组件"""
        layout = QFormLayout(self)

        # 宽度设置
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 20000)
        self.width_spin.setValue(self.initial_width)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(self.on_width_changed)
        layout.addRow("宽度:", self.width_spin)

        # 高度设置
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 20000)
        self.height_spin.setValue(self.initial_height)
        self.height_spin.setSuffix(" px")
        self.height_spin.valueChanged.connect(self.on_height_changed)
        layout.addRow("高度:", self.height_spin)

        # 锁定比例选项（可选）
        if enable_ratio_lock:
            self.maintain_ratio = QCheckBox("保持宽高比")
            self.maintain_ratio.setChecked(False)
            layout.addRow("", self.maintain_ratio)
        else:
            self.maintain_ratio = None

        # 预设尺寸选择
        preset_layout = QHBoxLayout()

        self.preset_combo = QComboBox()
        self.refresh_presets()
        self.preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        preset_layout.addWidget(self.preset_combo)

        # 预设管理按钮（可选）
        if show_preset_manager:
            self.manage_presets_btn = QPushButton("管理")
            self.manage_presets_btn.clicked.connect(self.manage_presets)
            preset_layout.addWidget(self.manage_presets_btn)

        layout.addRow("预设尺寸:", preset_layout)

    def refresh_presets(self):
        """刷新预设列表"""
        current_index = self.preset_combo.currentIndex()
        self.preset_combo.clear()

        preset_names = self.preset_manager.get_preset_names()
        self.preset_combo.addItems(preset_names)

        # 尝试恢复之前的选择
        if current_index < len(preset_names):
            self.preset_combo.setCurrentIndex(current_index)

    def manage_presets(self):
        """打开预设管理对话框"""
        from app.ui.canvas_preset_dialog import CanvasPresetManagerDialog
        dialog = CanvasPresetManagerDialog(self)
        dialog.presets_changed.connect(self.refresh_presets)
        dialog.exec()

    def on_width_changed(self, value):
        """当宽度改变时处理"""
        # 设置为自定义
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

        # 如果启用了锁定比例且选中
        if self.maintain_ratio and self.maintain_ratio.isChecked():
            # 根据宽度调整高度
            new_height = int(value / self.aspect_ratio)
            self.height_spin.blockSignals(True)
            self.height_spin.setValue(new_height)
            self.height_spin.blockSignals(False)

        # 发出尺寸改变信号
        self.size_changed.emit(value, self.height_spin.value())

    def on_height_changed(self, value):
        """当高度改变时处理"""
        # 设置为自定义
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

        # 如果启用了锁定比例且选中
        if self.maintain_ratio and self.maintain_ratio.isChecked():
            # 根据高度调整宽度
            new_width = int(value * self.aspect_ratio)
            self.width_spin.blockSignals(True)
            self.width_spin.setValue(new_width)
            self.width_spin.blockSignals(False)

        # 发出尺寸改变信号
        self.size_changed.emit(self.width_spin.value(), value)

    @Slot(int)
    def on_preset_selected(self, index):
        """选择预设尺寸"""
        if index == 0:  # 自定义
            return

        # 阻止信号循环
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)

        # 从预设中获取尺寸
        size = self.preset_manager.get_preset_size(index)
        if size:
            width, height = size
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)

            # 更新宽高比
            if self.maintain_ratio and self.maintain_ratio.isChecked():
                self.aspect_ratio = width / height if height != 0 else 1.0

        # 恢复信号
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)

        # 发出尺寸改变信号
        self.size_changed.emit(self.width_spin.value(), self.height_spin.value())

    def get_size(self):
        """获取当前设置的尺寸"""
        return (self.width_spin.value(), self.height_spin.value())

    def set_size(self, width, height):
        """设置尺寸"""
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)

        self.width_spin.setValue(width)
        self.height_spin.setValue(height)

        if self.maintain_ratio and self.maintain_ratio.isChecked():
            self.aspect_ratio = width / height if height != 0 else 1.0

        # 设置为自定义
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)

        # 发出尺寸改变信号
        self.size_changed.emit(width, height) 