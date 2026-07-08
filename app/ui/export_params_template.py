import logging

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QDialogButtonBox, QLineEdit, QCheckBox, QSpinBox, QComboBox,
                              QFormLayout, QGroupBox, QMessageBox, QFileDialog)
from PySide6.QtCore import Qt, Signal
import os
import json

class ExportParamsTemplate:
    """导出参数模板类，用于保存和加载导出参数"""

    def __init__(self):
        self.name = "默认模板"
        # 输出设置
        self.output_format = "png"  # png, jpg, webp
        self.quality = 98  # 1-100，提高到最高质量
        self.resize_enabled = False
        self.resize_width = 1280
        self.resize_height = 720
        self.auto_crop_enabled = False
        self.maintain_aspect_ratio = True

        # 文件名设置
        self.filename_pattern = "{layer_name}_{index}"
        self.index_start = 1
        self.index_padding = 3

        # 处理设置
        self.apply_effects = True
        self.flatten_layers = False

    def to_dict(self):
        """转换为字典"""
        return {
            "name": self.name,
            "output_format": self.output_format,
            "quality": self.quality,
            "resize_enabled": self.resize_enabled,
            "resize_width": self.resize_width,
            "resize_height": self.resize_height,
            "auto_crop_enabled": self.auto_crop_enabled,
            "maintain_aspect_ratio": self.maintain_aspect_ratio,
            "filename_pattern": self.filename_pattern,
            "index_start": self.index_start,
            "index_padding": self.index_padding,
            "apply_effects": self.apply_effects,
            "flatten_layers": self.flatten_layers
        }

    def from_dict(self, data):
        """从字典加载"""
        self.name = data.get("name", "默认模板")
        self.output_format = data.get("output_format", "png")
        self.quality = data.get("quality", 90)
        self.resize_enabled = data.get("resize_enabled", False)
        self.resize_width = data.get("resize_width", 1280)
        self.resize_height = data.get("resize_height", 720)
        self.auto_crop_enabled = data.get("auto_crop_enabled", False)
        self.maintain_aspect_ratio = data.get("maintain_aspect_ratio", True)
        self.filename_pattern = data.get("filename_pattern", "{layer_name}_{index}")
        self.index_start = data.get("index_start", 1)
        self.index_padding = data.get("index_padding", 3)
        self.apply_effects = data.get("apply_effects", True)
        self.flatten_layers = data.get("flatten_layers", False)
        return self

    @staticmethod
    def save_template(template, file_path=None):
        """保存模板到文件"""
        if file_path is None:
            # 创建模板目录
            template_dir = os.path.join(os.path.expanduser('~'), '.config', '批图王', 'templates')
            os.makedirs(template_dir, exist_ok=True)
            file_path = os.path.join(template_dir, f"{template.name}.json")

        # 保存到JSON文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(template.to_dict(), f, ensure_ascii=False, indent=2)

        return file_path

    @staticmethod
    def load_template(file_path=None, template_name=None):
        """从文件加载模板"""
        if file_path is None and template_name is not None:
            # 根据模板名称加载
            template_dir = os.path.join(os.path.expanduser('~'), '.config', '批图王', 'templates')
            file_path = os.path.join(template_dir, f"{template_name}.json")

        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                template = ExportParamsTemplate()
                template.from_dict(data)
                return template
            except Exception as e:
                safe_print(f"加载模板失败: {str(e)}")

        return ExportParamsTemplate()  # 返回默认模板

    @staticmethod
    def get_all_templates():
        """获取所有模板列表"""
        templates = []
        template_dir = os.path.join(os.path.expanduser('~'), '.config', '批图王', 'templates')

        if not os.path.exists(template_dir):
            return templates

        for file_name in os.listdir(template_dir):
            if file_name.endswith('.json'):
                file_path = os.path.join(template_dir, file_name)
                try:
                    template = ExportParamsTemplate.load_template(file_path)
                    templates.append(template)
                except:
                    logger.debug("静默异常已忽略: except in ui/export_params_template.py")
                    pass

        return templates


class ExportParamsDialog(QDialog):
    """导出参数设置对话框"""

    def __init__(self, parent=None, template=None):
        super().__init__(parent)

        self.template = template if template else ExportParamsTemplate()

        self.setWindowTitle("批量导出参数设置")
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_template(self.template)

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # 模板名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("模板名称:"))
        self.name_edit = QLineEdit(self.template.name)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # 输出设置组
        output_group = QGroupBox("输出设置")
        output_layout = QFormLayout()

        # 输出格式
        self.format_combo = QComboBox()
        self.format_combo.addItems(["png", "jpg", "webp"])
        output_layout.addRow("输出格式:", self.format_combo)

        # 质量设置
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(98)  # 提高到最高质量
        output_layout.addRow("质量(1-100):", self.quality_spin)

        # 调整大小设置
        resize_layout = QHBoxLayout()
        self.resize_check = QCheckBox("调整大小")
        resize_layout.addWidget(self.resize_check)
        self.resize_width = QSpinBox()
        self.resize_width.setRange(1, 10000)
        self.resize_width.setValue(1280)
        resize_layout.addWidget(self.resize_width)
        resize_layout.addWidget(QLabel("x"))
        self.resize_height = QSpinBox()
        self.resize_height.setRange(1, 10000)
        self.resize_height.setValue(720)
        resize_layout.addWidget(self.resize_height)
        output_layout.addRow("", resize_layout)

        # 保持宽高比
        self.maintain_ratio_check = QCheckBox("保持宽高比")
        self.maintain_ratio_check.setChecked(True)
        output_layout.addRow("", self.maintain_ratio_check)

        # 自动裁剪
        self.auto_crop_check = QCheckBox("自动裁剪")
        output_layout.addRow("", self.auto_crop_check)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # 文件名设置组
        filename_group = QGroupBox("文件名设置")
        filename_layout = QFormLayout()

        # 文件名模式
        self.pattern_edit = QLineEdit("{layer_name}_{index}")
        filename_layout.addRow("命名模式:", self.pattern_edit)

        # 索引起始值
        self.index_start_spin = QSpinBox()
        self.index_start_spin.setRange(0, 10000)
        self.index_start_spin.setValue(1)
        filename_layout.addRow("索引起始值:", self.index_start_spin)

        # 索引填充
        self.index_padding_spin = QSpinBox()
        self.index_padding_spin.setRange(1, 10)
        self.index_padding_spin.setValue(3)
        filename_layout.addRow("索引填充位数:", self.index_padding_spin)

        filename_group.setLayout(filename_layout)
        layout.addWidget(filename_group)

        # 处理设置组
        process_group = QGroupBox("处理设置")
        process_layout = QFormLayout()

        # 应用效果
        self.apply_effects_check = QCheckBox("应用图层效果")
        self.apply_effects_check.setChecked(True)
        process_layout.addRow("", self.apply_effects_check)

        # 合并图层
        self.flatten_check = QCheckBox("合并所有图层")
        process_layout.addRow("", self.flatten_check)

        process_group.setLayout(process_layout)
        layout.addWidget(process_group)

        # 模板操作按钮
        template_layout = QHBoxLayout()
        self.save_template_btn = QPushButton("保存为模板")
        self.save_template_btn.clicked.connect(self.save_template)
        self.load_template_btn = QPushButton("加载模板")
        self.load_template_btn.clicked.connect(self.show_load_template)
        template_layout.addWidget(self.save_template_btn)
        template_layout.addWidget(self.load_template_btn)
        layout.addLayout(template_layout)

        # 对话框按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # 设置按钮中文文本
        button_box.button(QDialogButtonBox.Ok).setText("确定")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")

        layout.addWidget(button_box)

    def load_template(self, template):
        """加载模板到UI"""
        self.name_edit.setText(template.name)
        self.format_combo.setCurrentText(template.output_format)
        self.quality_spin.setValue(template.quality)
        self.resize_check.setChecked(template.resize_enabled)
        self.resize_width.setValue(template.resize_width)
        self.resize_height.setValue(template.resize_height)
        self.resize_width.setEnabled(template.resize_enabled)
        self.resize_height.setEnabled(template.resize_enabled)
        self.auto_crop_check.setChecked(template.auto_crop_enabled)
        self.maintain_ratio_check.setChecked(template.maintain_aspect_ratio)
        self.pattern_edit.setText(template.filename_pattern)
        self.index_start_spin.setValue(template.index_start)
        self.index_padding_spin.setValue(template.index_padding)
        self.apply_effects_check.setChecked(template.apply_effects)
        self.flatten_check.setChecked(template.flatten_layers)

    def get_template(self):
        """从UI获取模板"""
        template = ExportParamsTemplate()
        template.name = self.name_edit.text()
        template.output_format = self.format_combo.currentText()
        template.quality = self.quality_spin.value()
        template.resize_enabled = self.resize_check.isChecked()
        template.resize_width = self.resize_width.value()
        template.resize_height = self.resize_height.value()
        template.auto_crop_enabled = self.auto_crop_check.isChecked()
        template.maintain_aspect_ratio = self.maintain_ratio_check.isChecked()
        template.filename_pattern = self.pattern_edit.text()
        template.index_start = self.index_start_spin.value()
        template.index_padding = self.index_padding_spin.value()
        template.apply_effects = self.apply_effects_check.isChecked()
        template.flatten_layers = self.flatten_check.isChecked()
        return template

    def save_template(self):
        """保存模板"""
        template = self.get_template()
        try:
            file_path = ExportParamsTemplate.save_template(template)
            QMessageBox.information(self, "成功", f"已保存模板: {template.name}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存模板失败: {str(e)}")

    def show_load_template(self):
        """显示加载模板对话框"""
        templates = ExportParamsTemplate.get_all_templates()

        if not templates:
            QMessageBox.information(self, "提示", "没有找到保存的模板")
            return

        # 创建模板选择对话框
        from PySide6.QtWidgets import QListWidget, QVBoxLayout, QDialog, QPushButton
        dialog = QDialog(self)

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
            print("[DEBUG] Message encoding failed")

        dialog.setWindowTitle("选择模板")
        layout = QVBoxLayout(dialog)

        list_widget = QListWidget()
        for template in templates:
            list_widget.addItem(template.name)

        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)

        layout.addWidget(list_widget)

        button = QPushButton("加载")
        button.clicked.connect(dialog.accept)
        layout.addWidget(button)

        if dialog.exec() == QDialog.Accepted:
            current_row = list_widget.currentRow()
            if current_row >= 0 and current_row < len(templates):
                self.load_template(templates[current_row])
                QMessageBox.information(self, "成功", f"已加载模板: {templates[current_row].name}")

    def accept(self):
        self.template = self.get_template()
        super().accept() 