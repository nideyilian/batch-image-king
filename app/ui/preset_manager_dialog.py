from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QListWidget, QListWidgetItem, QMessageBox,
                           QLineEdit, QTextEdit, QFileDialog, QGroupBox, QSplitter,
                           QWidget, QTabWidget, QFormLayout, QDialogButtonBox, QSpinBox,
                           QInputDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon

import os
import datetime
from app.utils.preset_manager import PresetManager

class SavePresetDialog(QDialog):
    """保存预设对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("保存预设")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # 预设名称
        form_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入预设名称...")
        form_layout.addRow("预设名称:", self.name_edit)

        # 预设描述
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("输入预设描述...")
        self.desc_edit.setMaximumHeight(80)
        form_layout.addRow("预设描述:", self.desc_edit)

        layout.addLayout(form_layout)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # 设置按钮中文文本
        button_box.button(QDialogButtonBox.Ok).setText("确定")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")

        layout.addWidget(button_box)

    def get_preset_info(self):
        """获取预设信息"""
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip()
        }

class PresetDetailWidget(QWidget):
    """预设详情显示和编辑小部件"""

    preset_updated = Signal(str)  # 预设更新信号（预设ID）
    preset_deleted = Signal(str)  # 预设删除信号（预设ID）
    preset_exported = Signal(str)  # 预设导出信号（预设ID）
    preset_applied = Signal(str)  # 预设应用信号（预设ID）

    def __init__(self, preset_manager, parent=None):
        super().__init__(parent)

        self.preset_manager = preset_manager
        self.current_preset_id = None

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 预设详情组
        detail_group = QGroupBox("预设详情")
        detail_layout = QVBoxLayout(detail_group)

        # 预设名称和描述
        form_layout = QFormLayout()

        # 预设名称
        self.name_edit = QLineEdit()
        self.name_edit.setReadOnly(True)
        form_layout.addRow("名称:", self.name_edit)

        # 预设描述
        self.desc_edit = QTextEdit()
        self.desc_edit.setReadOnly(True)
        self.desc_edit.setMaximumHeight(80)
        form_layout.addRow("描述:", self.desc_edit)

        # 创建和修改时间
        self.created_label = QLabel()
        form_layout.addRow("创建时间:", self.created_label)

        self.modified_label = QLabel()
        form_layout.addRow("修改时间:", self.modified_label)

        # 文档数量
        self.doc_count_label = QLabel()
        form_layout.addRow("包含标签页:", self.doc_count_label)

        detail_layout.addLayout(form_layout)

        # 操作按钮
        button_layout = QHBoxLayout()

        self.edit_button = QPushButton("编辑信息")
        self.edit_button.clicked.connect(self.edit_preset)
        button_layout.addWidget(self.edit_button)

        self.export_button = QPushButton("导出预设")
        self.export_button.clicked.connect(self.export_preset)
        button_layout.addWidget(self.export_button)

        self.delete_button = QPushButton("删除预设")
        self.delete_button.clicked.connect(self.delete_preset)
        button_layout.addWidget(self.delete_button)

        detail_layout.addLayout(button_layout)

        # 应用按钮
        apply_layout = QHBoxLayout()

        self.apply_button = QPushButton("应用预设")
        self.apply_button.setStyleSheet("background-color: #4CAF50; color: #FFFFFF; font-weight: bold;")
        self.apply_button.clicked.connect(lambda: self.preset_applied.emit(self.current_preset_id))
        apply_layout.addWidget(self.apply_button)

        detail_layout.addLayout(apply_layout)

        layout.addWidget(detail_group)

        # 文档列表
        docs_group = QGroupBox("包含的标签页")
        docs_layout = QVBoxLayout(docs_group)

        self.docs_list = QListWidget()
        docs_layout.addWidget(self.docs_list)

        layout.addWidget(docs_group)

        # 禁用所有控件，直到选择预设
        self.name_edit.setEnabled(False)
        self.desc_edit.setEnabled(False)
        self.edit_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.docs_list.setEnabled(False)

    def set_preset(self, preset_id):
        """设置当前预设"""
        if not preset_id:
            self.clear_preset()
            return

        self.current_preset_id = preset_id

        # 加载预设信息
        preset_info = self.preset_manager.load_preset(preset_id)
        if not preset_info:
            self.clear_preset()
            return

        # 更新UI
        self.name_edit.setText(preset_info.get("name", ""))
        self.desc_edit.setText(preset_info.get("description", ""))

        # 格式化日期显示
        created = preset_info.get("created_at", "")
        if created:
            try:
                created_dt = datetime.datetime.fromisoformat(created)
                created = created_dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

        modified = preset_info.get("modified_at", "")
        if modified:
            try:
                modified_dt = datetime.datetime.fromisoformat(modified)
                modified = modified_dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

        self.created_label.setText(created)
        self.modified_label.setText(modified)

        # 文档列表
        documents = preset_info.get("documents", [])
        self.doc_count_label.setText(str(len(documents)))

        self.docs_list.clear()
        for doc in documents:
            item = QListWidgetItem(doc.get("name", f"标签页 {doc.get('index', 0)+1}"))
            self.docs_list.addItem(item)

        # 启用控件
        self.name_edit.setEnabled(True)
        self.desc_edit.setEnabled(True)
        self.edit_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.docs_list.setEnabled(True)

    def clear_preset(self):
        """清除当前预设"""
        self.current_preset_id = None

        self.name_edit.setText("")
        self.desc_edit.setText("")
        self.created_label.setText("")
        self.modified_label.setText("")
        self.doc_count_label.setText("0")
        self.docs_list.clear()

        # 禁用控件
        self.name_edit.setEnabled(False)
        self.desc_edit.setEnabled(False)
        self.edit_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.docs_list.setEnabled(False)

    def edit_preset(self):
        """编辑当前预设信息"""
        if not self.current_preset_id:
            return

        # 显示编辑对话框
        dialog = SavePresetDialog(self)
        dialog.name_edit.setText(self.name_edit.text())
        dialog.desc_edit.setText(self.desc_edit.toPlainText())

        if dialog.exec_():
            # 获取新的预设信息
            preset_info = dialog.get_preset_info()

            # 更新预设
            success = self.preset_manager.update_preset(
                self.current_preset_id,
                name=preset_info["name"],
                description=preset_info["description"]
            )

            if success:
                # 更新UI
                self.name_edit.setText(preset_info["name"])
                self.desc_edit.setText(preset_info["description"])

                # 发送更新信号
                self.preset_updated.emit(self.current_preset_id)

                QMessageBox.information(self, "预设更新", "预设信息已更新。")
            else:
                QMessageBox.warning(self, "更新失败", "无法更新预设信息。")

    def export_preset(self):
        """导出当前预设"""
        if not self.current_preset_id:
            return

        # 获取保存路径
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出预设", "", "预设文件 (*.pst)"
        )

        if not file_path:
            return

        # 如果用户没有添加.pst扩展名，则添加
        if not file_path.lower().endswith('.pst'):
            file_path += '.pst'

        # 导出预设
        success = self.preset_manager.export_preset(self.current_preset_id, file_path)

        if success:
            # 发送导出信号
            self.preset_exported.emit(self.current_preset_id)

            QMessageBox.information(self, "预设导出", f"预设已成功导出到: {file_path}")
        else:
            QMessageBox.warning(self, "导出失败", "无法导出预设。")

    def delete_preset(self):
        """删除当前预设"""
        if not self.current_preset_id:
            return

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除预设 '{self.name_edit.text()}'吗？此操作无法撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 删除预设
        success = self.preset_manager.delete_preset(self.current_preset_id)

        if success:
            # 发送删除信号
            preset_id = self.current_preset_id
            self.clear_preset()
            self.preset_deleted.emit(preset_id)

            QMessageBox.information(self, "预设删除", "预设已成功删除。")
        else:
            QMessageBox.warning(self, "删除失败", "无法删除预设。")

class PresetSaveDialog(QDialog):
    """保存预设对话框 - 选择要保存的标签页和预设信息"""

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)

        self.main_window = main_window

        self.setWindowTitle("保存为预设")
        self.setMinimumSize(550, 400)

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        main_layout = QVBoxLayout(self)

        # 预设信息区域
        info_group = QGroupBox("预设信息")
        info_layout = QFormLayout()

        # 预设名称
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入预设名称...")
        info_layout.addRow("预设名称:", self.name_edit)

        # 预设描述
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("输入预设描述...")
        self.desc_edit.setMaximumHeight(60)
        info_layout.addRow("预设描述:", self.desc_edit)

        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)

        # 标签页选择区域
        tabs_group = QGroupBox("选择要包含的标签页")
        tabs_layout = QVBoxLayout()

        # 标签页列表
        self.tabs_list = QListWidget()
        self.tabs_list.setSelectionMode(QListWidget.MultiSelection)

        # 添加标签页
        if self.main_window and hasattr(self.main_window, 'tab_widget'):
            for i in range(self.main_window.tab_widget.count()):
                tab_name = self.main_window.tab_widget.tabText(i)
                item = QListWidgetItem(tab_name)
                item.setData(Qt.UserRole, i)
                item.setSelected(True)  # 默认选中
                self.tabs_list.addItem(item)

        tabs_layout.addWidget(self.tabs_list)

        # 选择按钮
        button_layout = QHBoxLayout()

        self.select_all_button = QPushButton("全选")
        self.select_all_button.clicked.connect(self.select_all_tabs)
        button_layout.addWidget(self.select_all_button)

        self.select_none_button = QPushButton("取消全选")
        self.select_none_button.clicked.connect(self.select_none_tabs)
        button_layout.addWidget(self.select_none_button)

        tabs_layout.addLayout(button_layout)
        tabs_group.setLayout(tabs_layout)
        main_layout.addWidget(tabs_group)

        # 底部按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)

        # 设置按钮中文文本
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")

        main_layout.addWidget(buttons)

    def select_all_tabs(self):
        """选择所有标签页"""
        for i in range(self.tabs_list.count()):
            self.tabs_list.item(i).setSelected(True)

    def select_none_tabs(self):
        """取消选择所有标签页"""
        for i in range(self.tabs_list.count()):
            self.tabs_list.item(i).setSelected(False)

    def validate_and_accept(self):
        """验证输入并接受"""
        # 检查是否选择了标签页
        if not self.get_selected_tabs():
            QMessageBox.warning(self, "验证失败", "请至少选择一个标签页。")
            return

        # 检查预设名称
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "验证失败", "请输入预设名称。")
            return

        self.accept()

    def get_selected_tabs(self):
        """获取选中的标签页索引"""
        selected_tabs = []

        for i in range(self.tabs_list.count()):
            item = self.tabs_list.item(i)
            if item.isSelected():
                tab_index = item.data(Qt.UserRole)
                selected_tabs.append(tab_index)

        return selected_tabs

    def get_preset_info(self):
        """获取预设信息"""
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip()
        }

class PresetManagerDialog(QDialog):
    """预设管理对话框"""

    preset_applied = Signal(str)  # 预设应用信号（预设ID）

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)

        self.main_window = main_window
        self.preset_manager = PresetManager()

        self.setWindowTitle("预设管理")
        self.setMinimumSize(800, 550)

        self.setup_ui()
        self.load_presets()

    def setup_ui(self):
        """设置UI"""
        main_layout = QVBoxLayout(self)

        # 顶部工具栏 - 简化为按钮行
        toolbar_layout = QHBoxLayout()

        self.new_preset_button = QPushButton("保存当前标签页为预设")
        self.new_preset_button.clicked.connect(self.save_current_tabs)
        toolbar_layout.addWidget(self.new_preset_button)

        self.import_button = QPushButton("导入预设")
        self.import_button.clicked.connect(self.import_preset)
        toolbar_layout.addWidget(self.import_button)

        # 添加导出所有预设按钮
        self.export_all_button = QPushButton("导出所有预设")
        self.export_all_button.clicked.connect(self.export_all_presets)
        self.export_all_button.setToolTip("将所有预设导出为一个合集文件")
        toolbar_layout.addWidget(self.export_all_button)

        main_layout.addLayout(toolbar_layout)

        # 内容区域 - 使用分割器让用户可以调整大小
        splitter = QSplitter(Qt.Horizontal)

        # 左侧 - 预设列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        preset_label = QLabel("预设列表:")
        left_layout.addWidget(preset_label)

        self.presets_list = QListWidget()
        self.presets_list.setSelectionMode(QListWidget.SingleSelection)
        self.presets_list.currentItemChanged.connect(self.on_preset_selected)
        left_layout.addWidget(self.presets_list)

        splitter.addWidget(left_panel)

        # 右侧 - 预设详情和操作
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 详情组
        details_group = QGroupBox("预设详情")
        details_layout = QFormLayout()

        self.name_label = QLabel()
        self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_layout.addRow("名称:", self.name_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_layout.addRow("描述:", self.desc_label)

        self.date_label = QLabel()
        details_layout.addRow("创建时间:", self.date_label)

        self.tabs_count_label = QLabel()
        details_layout.addRow("包含标签页:", self.tabs_count_label)

        details_group.setLayout(details_layout)
        right_layout.addWidget(details_group)

        # 标签页列表组
        tabs_group = QGroupBox("包含的标签页")
        tabs_layout = QVBoxLayout()

        self.tabs_list = QListWidget()
        tabs_layout.addWidget(self.tabs_list)

        tabs_group.setLayout(tabs_layout)
        right_layout.addWidget(tabs_group)

        # 操作按钮组
        buttons_group = QGroupBox("操作")
        buttons_layout = QVBoxLayout()

        # 编辑和删除
        edit_delete_layout = QHBoxLayout()

        self.rename_button = QPushButton("重命名")
        self.rename_button.clicked.connect(self.rename_preset)
        edit_delete_layout.addWidget(self.rename_button)

        self.export_button = QPushButton("导出预设")
        self.export_button.clicked.connect(self.export_preset)
        edit_delete_layout.addWidget(self.export_button)

        self.delete_button = QPushButton("删除预设")
        self.delete_button.clicked.connect(self.delete_preset)
        edit_delete_layout.addWidget(self.delete_button)

        buttons_layout.addLayout(edit_delete_layout)

        # 应用预设按钮
        self.apply_button = QPushButton("应用预设")
        self.apply_button.setStyleSheet("background-color: #4CAF50; color: #FFFFFF; font-weight: bold; padding: 6px;")
        self.apply_button.clicked.connect(self.apply_preset)
        buttons_layout.addWidget(self.apply_button)

        buttons_group.setLayout(buttons_layout)
        right_layout.addWidget(buttons_group)

        splitter.addWidget(right_panel)

        # 初始分割比例
        splitter.setSizes([250, 550])
        main_layout.addWidget(splitter)

        # 底部按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.reject)
        bottom_layout.addWidget(self.close_button)

        main_layout.addLayout(bottom_layout)

        # 初始状态 - 禁用详情和操作按钮
        self.disable_details()

    def disable_details(self):
        """禁用详情和操作按钮"""
        self.name_label.setText("")
        self.desc_label.setText("")
        self.date_label.setText("")
        self.tabs_count_label.setText("")
        self.tabs_list.clear()

        self.rename_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.apply_button.setEnabled(False)

    def load_presets(self):
        """加载预设列表"""
        self.presets_list.clear()

        presets = self.preset_manager.get_all_presets()

        for preset in presets:
            item = QListWidgetItem(preset["name"])
            item.setData(Qt.UserRole, preset["id"])
            self.presets_list.addItem(item)

    def on_preset_selected(self, current, previous):
        """当选择预设时"""
        if not current:
            self.disable_details()
            return

        preset_id = current.data(Qt.UserRole)

        # 加载预设详情
        preset_info = self.preset_manager.load_preset(preset_id)
        if not preset_info:
            self.disable_details()
            return

        # 更新详情显示
        self.name_label.setText(preset_info.get("name", ""))
        self.desc_label.setText(preset_info.get("description", ""))

        # 格式化日期
        created_at = preset_info.get("created_at", "")
        if created_at:
            try:
                created_dt = datetime.datetime.fromisoformat(created_at)
                created_at = created_dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
        self.date_label.setText(created_at)

        # 标签页数量
        documents = preset_info.get("documents", [])
        self.tabs_count_label.setText(str(len(documents)))

        # 填充标签页列表
        self.tabs_list.clear()
        for doc in documents:
            # 优先使用原始标签名
            tab_name = doc.get("original_tab_name", doc.get("name", f"标签页 {doc.get('index', 0)+1}"))
            self.tabs_list.addItem(tab_name)

        # 启用按钮
        self.rename_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.apply_button.setEnabled(True)

    def save_current_tabs(self):
        """保存当前标签页为预设"""
        if not self.main_window:
            QMessageBox.warning(self, "无法保存", "无法获取主窗口引用。")
            return

        if self.main_window.tab_widget.count() == 0:
            QMessageBox.warning(self, "无法保存", "没有打开的标签页。")
            return

        # 显示更简洁的保存对话框
        dialog = PresetSaveDialog(self.main_window, self)

        if dialog.exec_():
            # 获取选中的标签页和预设信息
            selected_tabs = dialog.get_selected_tabs()
            preset_info = dialog.get_preset_info()

            if not selected_tabs:
                QMessageBox.warning(self, "无法保存", "没有选择要保存的标签页。")
                return

            # 获取文档对象
            documents = []
            for tab_index in selected_tabs:
                documents.append(self.main_window.documents[tab_index])

            # 获取全局设置
            global_settings = {}
            if hasattr(self.main_window, 'get_global_settings'):
                global_settings = self.main_window.get_global_settings()

            # 使用新方法直接从文档对象保存预设
            result = self.preset_manager.save_preset_documents(
                preset_info["name"],
                preset_info["description"],
                documents,
                global_settings
            )

            # 检查是否存在同名预设
            if isinstance(result, dict) and result.get("duplicate"):
                # 提示用户是否要更新已有预设
                reply = QMessageBox.question(
                    self,
                    "预设名称已存在",
                    f"已存在名为 '{result['name']}' 的预设，是否要更新它？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    # 更新已有预设
                    # 首先需要删除旧预设
                    existing_id = result["existing_id"]
                    success = self.preset_manager.delete_preset(existing_id)

                    if success:
                        # 然后用相同名称保存新预设
                        preset_id = self.preset_manager.save_preset_documents(
                            preset_info["name"],
                            preset_info["description"],
                            documents,
                            global_settings
                        )

                        if preset_id:
                            # 重新加载预设列表
                            self.load_presets()

                            # 选择更新后的预设
                            for i in range(self.presets_list.count()):
                                item = self.presets_list.item(i)
                                if item.data(Qt.UserRole) == preset_id:
                                    self.presets_list.setCurrentItem(item)
                                    break

                            QMessageBox.information(self, "预设更新", "预设已成功更新。")
                        else:
                            QMessageBox.warning(self, "更新失败", "无法更新预设。")
                    else:
                        QMessageBox.warning(self, "更新失败", "删除旧预设失败，无法完成更新。")
                # 如果用户选择不更新，则不执行任何操作

            elif result:  # 正常保存成功
                # 重新加载预设列表
                self.load_presets()

                # 选择新保存的预设
                for i in range(self.presets_list.count()):
                    item = self.presets_list.item(i)
                    if item.data(Qt.UserRole) == result:
                        self.presets_list.setCurrentItem(item)
                        break

                QMessageBox.information(self, "预设保存", "预设已成功保存。")
            else:  # 保存失败
                QMessageBox.warning(self, "保存失败", "无法保存预设。")

    def import_preset(self):
        """导入预设"""
        # 选择导入文件
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入预设", "", "预设文件 (*.pst)"
        )

        if not file_path:
            return

        # 导入预设
        preset_id = self.preset_manager.import_preset(file_path)

        if preset_id:
            # 重新加载预设列表
            self.load_presets()

            # 选择新导入的预设
            for i in range(self.presets_list.count()):
                item = self.presets_list.item(i)
                if item.data(Qt.UserRole) == preset_id:
                    self.presets_list.setCurrentItem(item)
                    break

            QMessageBox.information(self, "预设导入", "预设已成功导入。")
        else:
            QMessageBox.warning(self, "导入失败", "无法导入预设。请确保文件格式正确。")

    def rename_preset(self):
        """重命名预设"""
        current_item = self.presets_list.currentItem()
        if not current_item:
            return

        preset_id = current_item.data(Qt.UserRole)
        current_name = current_item.text()

        # 提示输入新名称
        new_name, ok = QInputDialog.getText(
            self, "重命名预设", "输入新名称:", QLineEdit.Normal, current_name
        )

        if ok and new_name.strip():
            # 更新预设名称
            success = self.preset_manager.update_preset(preset_id, name=new_name.strip())

            if success:
                # 更新列表项
                current_item.setText(new_name.strip())
                # 更新详情显示
                self.name_label.setText(new_name.strip())

                QMessageBox.information(self, "重命名成功", "预设已重命名。")
            else:
                QMessageBox.warning(self, "重命名失败", "无法重命名预设。")

    def export_preset(self):
        """导出预设"""
        current_item = self.presets_list.currentItem()
        if not current_item:
            return

        preset_id = current_item.data(Qt.UserRole)
        preset_name = current_item.text()

        # 选择导出路径
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出预设", preset_name, "预设文件 (*.pst)"
        )

        if not file_path:
            return

        # 确保有.pst扩展名
        if not file_path.lower().endswith('.pst'):
            file_path += '.pst'

        # 导出预设
        success = self.preset_manager.export_preset(preset_id, file_path)

        if success:
            QMessageBox.information(self, "导出成功", f"预设已导出至 {file_path}")
        else:
            QMessageBox.warning(self, "导出失败", "无法导出预设。")

    def delete_preset(self):
        """删除预设"""
        current_item = self.presets_list.currentItem()
        if not current_item:
            return

        preset_id = current_item.data(Qt.UserRole)
        preset_name = current_item.text()

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除预设 '{preset_name}'？此操作无法撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 删除预设
        success = self.preset_manager.delete_preset(preset_id)

        if success:
            # 从列表中移除
            row = self.presets_list.row(current_item)
            self.presets_list.takeItem(row)

            # 清空详情
            self.disable_details()

            QMessageBox.information(self, "删除成功", "预设已删除。")
        else:
            QMessageBox.warning(self, "删除失败", "无法删除预设。")

    def apply_preset(self):
        """应用预设"""
        current_item = self.presets_list.currentItem()
        if not current_item:
            return

        preset_id = current_item.data(Qt.UserRole)

        # 发送应用信号
        self.preset_applied.emit(preset_id)

        # 关闭对话框
        self.accept()

    def export_all_presets(self):
        """导出所有预设"""
        # 选择导出路径
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出所有预设", "", "预设文件 (*.pst)"
        )

        if not file_path:
            return

        # 确保有.pst扩展名
        if not file_path.lower().endswith('.pst'):
            file_path += '.pst'

        # 导出所有预设
        success = self.preset_manager.export_all_presets(file_path)

        if success:
            QMessageBox.information(self, "导出成功", f"所有预设已导出至 {file_path}")
        else:
            QMessageBox.warning(self, "导出失败", "无法导出所有预设。") 