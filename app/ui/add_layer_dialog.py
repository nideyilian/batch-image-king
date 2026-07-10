from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSpinBox, QLineEdit, QFormLayout,
                           QFileDialog, QDialogButtonBox, QCheckBox, QRadioButton, QButtonGroup, QComboBox)
from PySide6.QtCore import Qt
import os
from app.models.layer_new import Layer

class AddLayerDialog(QDialog):
    """添加图层对话框"""

    def __init__(self, document, parent=None):
        super().__init__(parent)

        self.document = document
        self.image_source = None
        self.is_folder = True  # 默认选择文件夹模式

        # 使用文档模型中的图层适配模式常量
        self.fit_mode = Layer.FIT_SMART_CROP  # 默认智能缩放裁剪模式

        self.setWindowTitle("添加图层")
        self.setMinimumWidth(350)

        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)

        # 创建表单布局
        form_layout = QFormLayout()

        # 图层名称
        self.name_edit = QLineEdit()
        self.name_edit.setText(f"图层 {len(self.document.layers) + 1}")
        form_layout.addRow("名称:", self.name_edit)

        # 图层尺寸
        size_layout = QHBoxLayout()
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(1, 10000)
        self.width_spinbox.setValue(200)

        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(1, 10000)
        self.height_spinbox.setValue(200)

        size_layout.addWidget(self.width_spinbox)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self.height_spinbox)

        form_layout.addRow("尺寸:", size_layout)

        # 图层位置
        position_layout = QHBoxLayout()
        self.x_spinbox = QSpinBox()
        self.x_spinbox.setRange(-10000, 10000)
        self.x_spinbox.setValue((self.document.canvas_width - 200) // 2)

        self.y_spinbox = QSpinBox()
        self.y_spinbox.setRange(-10000, 10000)
        self.y_spinbox.setValue((self.document.canvas_height - 200) // 2)

        position_layout.addWidget(self.x_spinbox)
        position_layout.addWidget(QLabel("x"))
        position_layout.addWidget(self.y_spinbox)

        form_layout.addRow("位置:", position_layout)

        # 使用原始尺寸
        self.use_original_size = QCheckBox("使用图像原始尺寸")
        form_layout.addRow("", self.use_original_size)

        # 适配模式
        # 索引定义（与 Layer.FIT_* 保持一致）：
        #   0 = 智能缩放裁剪 (FIT_SMART_CROP)
        #   1 = 智能缩放不裁剪 (FIT_SMART_FIT)
        #   2 = 智能适配不缩放 (FIT_NO_SCALE) - 保持原图尺寸，避免拉伸变形
        fit_layout = QHBoxLayout()
        self.fit_mode_combo = QComboBox()
        self.fit_mode_combo.addItem("智能缩放裁剪")
        self.fit_mode_combo.addItem("智能缩放不裁剪")
        self.fit_mode_combo.addItem("智能适配不缩放")
        fit_layout.addWidget(self.fit_mode_combo)
        form_layout.addRow("适配模式:", fit_layout)

        # 图像来源类型
        self.source_type_layout = QHBoxLayout()
        self.folder_radio = QRadioButton("文件夹（随机图像）")
        self.folder_radio.setChecked(True)
        self.file_radio = QRadioButton("单个文件")

        self.source_type_layout.addWidget(self.folder_radio)
        self.source_type_layout.addWidget(self.file_radio)

        form_layout.addRow("图像来源:", self.source_type_layout)

        # 图像来源路径
        source_path_layout = QHBoxLayout()
        self.source_path_edit = QLineEdit()
        self.source_path_edit.setReadOnly(True)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self.browse_source)

        source_path_layout.addWidget(self.source_path_edit)
        source_path_layout.addWidget(self.browse_btn)

        form_layout.addRow("路径:", source_path_layout)

        # 添加到主布局
        layout.addLayout(form_layout)

        # 添加按钮
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # 设置按钮中文文本
        self.button_box.button(QDialogButtonBox.Ok).setText("确定")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")

        layout.addWidget(self.button_box)

    def browse_source(self):
        """浏览图像来源"""
        if self.folder_radio.isChecked():
            # 选择文件夹
            folder_path = QFileDialog.getExistingDirectory(self, "选择图像文件夹")
            if folder_path:
                self.source_path_edit.setText(folder_path)
        else:
            # 选择单个文件
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择图像文件", "",
                "图像文件 (*.png *.jpg *.jpeg *.gif *.bmp);;所有文件 (*.*)"
            )
            if file_path:
                self.source_path_edit.setText(file_path)

    def accept(self):
        """确认添加图层"""
        name = self.name_edit.text().strip()
        if not name:
            from PySide6.QtWidgets import QMessageBox

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        safe_print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            safe_print(f"[DEBUG] {ascii_message}")
        except Exception:
            # 最后的备选方案
            safe_print("[DEBUG] Message encoding failed")

            QMessageBox.warning(self, "验证错误", "请输入图层名称")
            return

        # 获取设置
        x = self.x_spinbox.value()
        y = self.y_spinbox.value()
        width = self.width_spinbox.value()
        height = self.height_spinbox.value()
        use_original_size = self.use_original_size.isChecked()
        is_folder = self.folder_radio.isChecked()
        source_path = self.source_path_edit.text()
        fit_mode = self.fit_mode_combo.currentIndex()

        # 添加图层
        layer = self.document.add_layer(name, x, y, width, height,
                               source_path if source_path else None,
                               use_original_size, is_folder)

        # 设置适配模式
        if layer:
            layer.fit_mode = fit_mode

        super().accept()

    def toggle_original_size(self, state):
        """处理使用原始尺寸复选框状态变化"""
        use_original_size = (state == Qt.Checked)
        safe_print(f"切换智能裁剪模式: {use_original_size}（注意：不会改变用户设置的尺寸）")

        # 智能裁剪模式下依然保留用户设置的尺寸
        # 仅根据适应画布选项状态恢复尺寸设置
        self.toggle_full_canvas(self.full_canvas_checkbox.checkState()) 