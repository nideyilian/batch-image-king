from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QSpinBox,
                            QDialogButtonBox, QLabel, QComboBox, QCheckBox,
                            QHBoxLayout, QLineEdit, QPushButton, QMessageBox)
from PySide6.QtCore import Qt

from app.utils.canvas_preset_manager import CanvasPresetManager
from app.ui.canvas_preset_dialog import CanvasPresetManagerDialog

class NewCanvasDialog(QDialog):
    """新建画布对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建画布")
        self.setMinimumWidth(400)

        # 创建预设管理器
        self.preset_manager = CanvasPresetManager()

        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)

        # 创建表单布局
        form_layout = QFormLayout()

        # 文档名称
        self.name_edit = QLineEdit()
        self.name_edit.setText("未命名文档")
        self.name_edit.setPlaceholderText("输入文档名称...")
        form_layout.addRow("文档名称:", self.name_edit)

        # 预设尺寸选择和管理
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("尺寸预设:"))

        self.preset_combo = QComboBox()
        self.refresh_presets()
        self.preset_combo.currentIndexChanged.connect(self.apply_preset)
        preset_layout.addWidget(self.preset_combo)

        # 预设管理按钮
        self.manage_presets_btn = QPushButton("管理预设")
        self.manage_presets_btn.clicked.connect(self.manage_presets)
        preset_layout.addWidget(self.manage_presets_btn)

        form_layout.addRow("", preset_layout)

        # 宽度输入
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(1, 20000)
        self.width_spinbox.setValue(1920)
        self.width_spinbox.setSuffix(" px")
        self.width_spinbox.valueChanged.connect(self.on_size_changed)
        form_layout.addRow("宽度:", self.width_spinbox)

        # 高度输入
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(1, 20000)
        self.height_spinbox.setValue(1080)
        self.height_spinbox.setSuffix(" px")
        self.height_spinbox.valueChanged.connect(self.on_size_changed)
        form_layout.addRow("高度:", self.height_spinbox)

        # 快速操作按钮
        quick_layout = QHBoxLayout()

        # 交换宽高按钮
        swap_btn = QPushButton("交换宽高")
        swap_btn.clicked.connect(self.swap_dimensions)
        quick_layout.addWidget(swap_btn)

        # 比例设置按钮
        ratio_16_9_btn = QPushButton("16:9")
        ratio_16_9_btn.clicked.connect(lambda: self.set_ratio(16, 9))
        quick_layout.addWidget(ratio_16_9_btn)

        ratio_4_3_btn = QPushButton("4:3")
        ratio_4_3_btn.clicked.connect(lambda: self.set_ratio(4, 3))
        quick_layout.addWidget(ratio_4_3_btn)

        square_btn = QPushButton("正方形")
        square_btn.clicked.connect(lambda: self.set_ratio(1, 1))
        quick_layout.addWidget(square_btn)

        form_layout.addRow("快速设置:", quick_layout)

        # 保存为预设选项
        self.save_as_preset = QCheckBox("将此尺寸保存为新预设")
        form_layout.addRow("", self.save_as_preset)

        # 添加到主布局
        layout.addLayout(form_layout)

        # 尺寸预览
        self.size_info_label = QLabel()
        self.update_size_info()
        layout.addWidget(self.size_info_label)

        # 创建按钮
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept_with_preset_save)
        self.button_box.rejected.connect(self.reject)

        # 设置按钮中文文本
        self.button_box.button(QDialogButtonBox.Ok).setText("确定")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")

        layout.addWidget(self.button_box)

    def refresh_presets(self):
        """刷新预设列表"""
        self.preset_combo.clear()
        preset_names = self.preset_manager.get_preset_names()
        self.preset_combo.addItems(preset_names)

    def apply_preset(self, index):
        """应用预设尺寸"""
        if index == 0:  # 自定义，不做任何改变
            return

        size = self.preset_manager.get_preset_size(index)
        if size:
            width, height = size
            self.width_spinbox.blockSignals(True)
            self.height_spinbox.blockSignals(True)

            self.width_spinbox.setValue(width)
            self.height_spinbox.setValue(height)

            self.width_spinbox.blockSignals(False)
            self.height_spinbox.blockSignals(False)

            self.update_size_info()

    def on_size_changed(self):
        """尺寸改变时更新信息"""
        # 设置为自定义
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

        self.update_size_info()

    def update_size_info(self):
        """更新尺寸信息显示"""
        width = self.width_spinbox.value()
        height = self.height_spinbox.value()

        # 计算宽高比
        ratio = width / height if height != 0 else 1

        # 判断常见比例
        if abs(ratio - 16/9) < 0.01:
            ratio_text = "16:9"
        elif abs(ratio - 4/3) < 0.01:
            ratio_text = "4:3"
        elif abs(ratio - 1) < 0.01:
            ratio_text = "1:1 (正方形)"
        else:
            ratio_text = f"{ratio:.2f}:1"

        # 计算像素总数
        total_pixels = width * height
        if total_pixels >= 1000000:
            pixels_text = f"{total_pixels/1000000:.1f}M 像素"
        else:
            pixels_text = f"{total_pixels//1000}K 像素"

        info_text = f"尺寸: {width} × {height} 像素  |  比例: {ratio_text}  |  {pixels_text}"
        self.size_info_label.setText(info_text)

    def swap_dimensions(self):
        """交换宽高"""
        width = self.width_spinbox.value()
        height = self.height_spinbox.value()

        self.width_spinbox.setValue(height)
        self.height_spinbox.setValue(width)

    def set_ratio(self, width_ratio, height_ratio):
        """设置特定比例"""
        current_width = self.width_spinbox.value()

        # 基于当前宽度计算新高度
        new_height = int(current_width * height_ratio / width_ratio)
        self.height_spinbox.setValue(new_height)

    def manage_presets(self):
        """打开预设管理对话框"""
        dialog = CanvasPresetManagerDialog(self)
        dialog.presets_changed.connect(self.refresh_presets)
        dialog.exec()

    def accept_with_preset_save(self):
        """确认时检查是否需要保存预设"""
        if self.save_as_preset.isChecked():
            self.save_current_as_preset()

        self.accept()

    def save_current_as_preset(self):
        """将当前尺寸保存为预设"""
        width = self.width_spinbox.value()
        height = self.height_spinbox.value()

        # 自动生成预设名称
        ratio = width / height if height != 0 else 1
        if abs(ratio - 16/9) < 0.01:
            aspect = " (16:9)"
        elif abs(ratio - 4/3) < 0.01:
            aspect = " (4:3)"
        elif abs(ratio - 1) < 0.01:
            aspect = " (正方形)"
        else:
            aspect = ""

        default_name = f"自定义 {width}x{height}{aspect}"

        # 询问预设名称
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self,
            "保存预设",
            "请输入预设名称:",
            text=default_name
        )

        if ok and name.strip():
            success = self.preset_manager.add_custom_preset(
                name.strip(), width, height, "自定义"
            )

            if success:
                QMessageBox.information(self, "成功", f"预设 '{name}' 保存成功！")
                self.refresh_presets()
            else:
                QMessageBox.warning(self, "错误", "预设名称已存在或保存失败")

    def get_canvas_settings(self):
        """获取画布设置"""
        return {
            "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(),
            "name": self.name_edit.text().strip() or "未命名文档"
        } 