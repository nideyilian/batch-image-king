from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QListWidget, QListWidgetItem, QMessageBox,
                           QLineEdit, QFormLayout, QSpinBox, QComboBox, QGroupBox,
                           QSplitter, QWidget, QDialogButtonBox, QInputDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon

from app.ui.tokens_v2 import Color
from app.utils.canvas_preset_manager import CanvasPresetManager

class AddCanvasPresetDialog(QDialog):
    """添加画布预设对话框"""

    def __init__(self, preset_manager, parent=None):
        super().__init__(parent)
        self.preset_manager = preset_manager
        self.setWindowTitle("添加画布尺寸预设")
        self.setMinimumWidth(350)

        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)

        # 创建表单布局
        form_layout = QFormLayout()

        # 预设名称
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入预设名称...")
        form_layout.addRow("预设名称:", self.name_edit)

        # 宽度输入
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(1, 20000)
        self.width_spinbox.setValue(1920)
        self.width_spinbox.setSuffix(" px")
        form_layout.addRow("宽度:", self.width_spinbox)

        # 高度输入
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(1, 20000)
        self.height_spinbox.setValue(1080)
        self.height_spinbox.setSuffix(" px")
        form_layout.addRow("高度:", self.height_spinbox)

        # 类别选择
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        categories = self.preset_manager.get_categories()
        categories.append("自定义")  # 默认添加一个自定义分类
        self.category_combo.addItems(categories)
        self.category_combo.setCurrentText("自定义")
        form_layout.addRow("类别:", self.category_combo)

        layout.addLayout(form_layout)

        # 快速设置按钮
        quick_group = QGroupBox("快速设置")
        quick_layout = QVBoxLayout(quick_group)

        button_layout1 = QHBoxLayout()

        # 16:9 按钮
        ratio_16_9_btn = QPushButton("16:9 比例")
        ratio_16_9_btn.clicked.connect(lambda: self.set_ratio(16, 9))
        button_layout1.addWidget(ratio_16_9_btn)

        # 4:3 按钮
        ratio_4_3_btn = QPushButton("4:3 比例")
        ratio_4_3_btn.clicked.connect(lambda: self.set_ratio(4, 3))
        button_layout1.addWidget(ratio_4_3_btn)

        # 1:1 按钮
        ratio_1_1_btn = QPushButton("1:1 正方形")
        ratio_1_1_btn.clicked.connect(lambda: self.set_ratio(1, 1))
        button_layout1.addWidget(ratio_1_1_btn)

        quick_layout.addLayout(button_layout1)

        button_layout2 = QHBoxLayout()

        # 交换宽高按钮
        swap_btn = QPushButton("交换宽高")
        swap_btn.clicked.connect(self.swap_dimensions)
        button_layout2.addWidget(swap_btn)

        # 使用当前画布尺寸按钮
        current_size_btn = QPushButton("使用当前画布")
        current_size_btn.clicked.connect(self.use_current_canvas_size)
        button_layout2.addWidget(current_size_btn)

        quick_layout.addLayout(button_layout2)

        layout.addWidget(quick_group)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # 设置按钮中文文本
        button_box.button(QDialogButtonBox.Ok).setText("确定")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")

        layout.addWidget(button_box)

        # 设置默认名称
        self.auto_generate_name()

        # 连接尺寸变化信号
        self.width_spinbox.valueChanged.connect(self.auto_generate_name)
        self.height_spinbox.valueChanged.connect(self.auto_generate_name)

    def set_ratio(self, width_ratio, height_ratio):
        """设置特定比例"""
        current_width = self.width_spinbox.value()

        # 基于当前宽度计算新高度
        new_height = int(current_width * height_ratio / width_ratio)
        self.height_spinbox.setValue(new_height)

    def swap_dimensions(self):
        """交换宽高"""
        width = self.width_spinbox.value()
        height = self.height_spinbox.value()

        self.width_spinbox.setValue(height)
        self.height_spinbox.setValue(width)

    def use_current_canvas_size(self):
        """使用当前画布尺寸（如果有的话）"""
        # 这个功能需要从主窗口获取当前画布尺寸
        # 暂时设置一个默认值
        QMessageBox.information(self, "提示", "此功能需要与主窗口集成才能使用")

    def auto_generate_name(self):
        """自动生成预设名称"""
        if not self.name_edit.text() or self.name_edit.text().startswith("自定义"):
            width = self.width_spinbox.value()
            height = self.height_spinbox.value()

            # 检查是否是常见比例
            ratio = width / height if height != 0 else 1
            if abs(ratio - 16/9) < 0.01:
                aspect = " (16:9)"
            elif abs(ratio - 4/3) < 0.01:
                aspect = " (4:3)"
            elif abs(ratio - 1) < 0.01:
                aspect = " (正方形)"
            else:
                aspect = ""

            name = f"自定义 {width}x{height}{aspect}"
            self.name_edit.setText(name)

    def get_preset_data(self):
        """获取预设数据"""
        return {
            "name": self.name_edit.text().strip(),
            "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(),
            "category": self.category_combo.currentText().strip()
        }


class EditCanvasPresetDialog(AddCanvasPresetDialog):
    """编辑画布预设对话框"""

    def __init__(self, preset_manager, preset_data, parent=None):
        self.preset_data = preset_data
        super().__init__(preset_manager, parent)
        self.setWindowTitle("编辑画布尺寸预设")

        # 填充现有数据
        self.name_edit.setText(preset_data.get("name", ""))
        self.width_spinbox.setValue(preset_data.get("width", 1920))
        self.height_spinbox.setValue(preset_data.get("height", 1080))
        self.category_combo.setCurrentText(preset_data.get("category", "自定义"))


class CanvasPresetManagerDialog(QDialog):
    """画布预设管理对话框"""

    # 信号定义
    presets_changed = Signal()  # 预设发生变化时发出

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("画布尺寸预设管理")
        self.setMinimumSize(800, 600)

        # 创建预设管理器
        self.preset_manager = CanvasPresetManager()

        self.setup_ui()
        self.load_presets()

    def setup_ui(self):
        """设置UI界面"""
        layout = QHBoxLayout(self)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：预设列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 预设列表标题
        list_label = QLabel("画布尺寸预设")
        list_label.setFont(QFont("", 12, QFont.Bold))
        left_layout.addWidget(list_label)

        # 预设列表
        self.preset_list = QListWidget()
        self.preset_list.itemSelectionChanged.connect(self.on_preset_selected)
        left_layout.addWidget(self.preset_list)

        # 列表操作按钮
        list_button_layout = QHBoxLayout()

        self.add_button = QPushButton("添加")
        self.add_button.clicked.connect(self.add_preset)
        list_button_layout.addWidget(self.add_button)

        self.edit_button = QPushButton("编辑")
        self.edit_button.clicked.connect(self.edit_preset)
        self.edit_button.setEnabled(False)
        list_button_layout.addWidget(self.edit_button)

        self.delete_button = QPushButton("删除")
        self.delete_button.clicked.connect(self.delete_preset)
        self.delete_button.setEnabled(False)
        list_button_layout.addWidget(self.delete_button)

        left_layout.addLayout(list_button_layout)

        splitter.addWidget(left_widget)

        # 右侧：预设详情
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 详情标题
        detail_label = QLabel("预设详情")
        detail_label.setFont(QFont("", 12, QFont.Bold))
        right_layout.addWidget(detail_label)

        # 预设详情
        detail_group = QGroupBox()
        detail_form = QFormLayout(detail_group)

        self.detail_name = QLabel("-")
        detail_form.addRow("名称:", self.detail_name)

        self.detail_size = QLabel("-")
        detail_form.addRow("尺寸:", self.detail_size)

        self.detail_category = QLabel("-")
        detail_form.addRow("类别:", self.detail_category)

        self.detail_type = QLabel("-")
        detail_form.addRow("类型:", self.detail_type)

        right_layout.addWidget(detail_group)

        # 预览区域
        preview_group = QGroupBox("尺寸预览")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_label = QLabel("未选择预设")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"""
            QLabel {{
                border: 2px dashed {Color.border_strong};
                padding: 20px;
                color: {Color.text_muted};
                font-size: 14px;
            }}
        """)
        preview_layout.addWidget(self.preview_label)

        right_layout.addWidget(preview_group)

        right_layout.addStretch()

        splitter.addWidget(right_widget)

        # 设置分割器比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def load_presets(self):
        """加载所有预设到列表"""
        self.preset_list.clear()

        all_presets = self.preset_manager.get_all_presets()

        for preset in all_presets:
            item = QListWidgetItem()

            # 设置显示文本
            name = preset["name"]
            size_text = f"{preset['width']}×{preset['height']}"

            if preset["is_builtin"]:
                display_text = f"{name}\n{size_text}"
                item.setToolTip("内置预设")
            else:
                display_text = f"{name} (自定义)\n{size_text}"
                item.setToolTip("用户自定义预设")

            item.setText(display_text)
            item.setData(Qt.UserRole, preset)

            # 设置字体样式
            if preset["is_builtin"]:
                font = item.font()
                font.setItalic(True)
                item.setFont(font)

            self.preset_list.addItem(item)

    def on_preset_selected(self):
        """预设选择改变时"""
        current_item = self.preset_list.currentItem()

        if not current_item:
            self.clear_details()
            return

        preset = current_item.data(Qt.UserRole)

        # 更新详情显示
        self.detail_name.setText(preset["name"])
        self.detail_size.setText(f"{preset['width']} × {preset['height']} 像素")
        self.detail_category.setText(preset["category"])
        self.detail_type.setText("内置预设" if preset["is_builtin"] else "用户自定义")

        # 更新预览
        self.update_preview(preset["width"], preset["height"])

        # 更新按钮状态
        is_custom = not preset["is_builtin"]
        self.edit_button.setEnabled(is_custom)
        self.delete_button.setEnabled(is_custom)

    def clear_details(self):
        """清空详情显示"""
        self.detail_name.setText("-")
        self.detail_size.setText("-")
        self.detail_category.setText("-")
        self.detail_type.setText("-")

        self.preview_label.setText("未选择预设")

        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)

    def update_preview(self, width, height):
        """更新尺寸预览"""
        # 计算显示比例
        max_width = 200
        max_height = 150

        scale = min(max_width / width, max_height / height)
        display_width = int(width * scale)
        display_height = int(height * scale)

        # 更新预览文本
        aspect_ratio = width / height if height != 0 else 1
        ratio_text = f"比例: {aspect_ratio:.2f}:1"

        preview_text = f"{width} × {height}\n{ratio_text}\n预览: {display_width} × {display_height}"
        self.preview_label.setText(preview_text)

    def add_preset(self):
        """添加新预设"""
        dialog = AddCanvasPresetDialog(self.preset_manager, self)

        if dialog.exec() == QDialog.Accepted:
            preset_data = dialog.get_preset_data()

            if not preset_data["name"]:
                QMessageBox.warning(self, "错误", "请输入预设名称")
                return

            # 尝试添加预设
            success = self.preset_manager.add_custom_preset(
                preset_data["name"],
                preset_data["width"],
                preset_data["height"],
                preset_data["category"]
            )

            if success:
                self.load_presets()
                self.presets_changed.emit()
                QMessageBox.information(self, "成功", "预设添加成功！")
            else:
                QMessageBox.warning(self, "错误", "预设名称已存在或添加失败")

    def edit_preset(self):
        """编辑选中的预设"""
        current_item = self.preset_list.currentItem()
        if not current_item:
            return

        preset = current_item.data(Qt.UserRole)
        if preset["is_builtin"]:
            QMessageBox.information(self, "提示", "无法编辑内置预设")
            return

        dialog = EditCanvasPresetDialog(self.preset_manager, preset, self)

        if dialog.exec() == QDialog.Accepted:
            new_data = dialog.get_preset_data()

            if not new_data["name"]:
                QMessageBox.warning(self, "错误", "请输入预设名称")
                return

            # 尝试更新预设
            success = self.preset_manager.update_custom_preset(
                preset["name"],
                new_data["name"],
                new_data["width"],
                new_data["height"],
                new_data["category"]
            )

            if success:
                self.load_presets()
                self.presets_changed.emit()
                QMessageBox.information(self, "成功", "预设更新成功！")
            else:
                QMessageBox.warning(self, "错误", "预设名称已存在或更新失败")

    def delete_preset(self):
        """删除选中的预设"""
        current_item = self.preset_list.currentItem()
        if not current_item:
            return

        preset = current_item.data(Qt.UserRole)
        if preset["is_builtin"]:
            QMessageBox.information(self, "提示", "无法删除内置预设")
            return

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除预设 '{preset['name']}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            success = self.preset_manager.remove_custom_preset(preset["name"])

            if success:
                self.load_presets()
                self.presets_changed.emit()
                QMessageBox.information(self, "成功", "预设删除成功！")
            else:
                QMessageBox.warning(self, "错误", "删除预设失败") 