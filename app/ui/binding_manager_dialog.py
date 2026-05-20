#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图层绑定管理对话框
提供图形界面来管理图层绑定组
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QListWidget, QListWidgetItem,
                           QGroupBox, QLineEdit, QCheckBox, QComboBox,
                           QMessageBox, QInputDialog, QTextEdit,
                           QSplitter, QWidget, QFormLayout, QSpinBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import os

from app.ui.icon_manager import IconManager


class BindingGroupWidget(QWidget):
    """绑定组显示组件"""

    def __init__(self, group_info, binding_manager, dialog, parent=None):
        super().__init__(parent)
        self.group_info = group_info
        self.binding_manager = binding_manager
        self.dialog = dialog  # 直接保存对话框引用
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 组名标题
        # 使用图标管理器创建绑定图标
        icon_text = IconManager.get_icon_text('link')
        title_label = QLabel(f"{icon_text} {self.group_info['name']}")
        title_font = QFont()
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # 组信息
        info_text = f"图层数量: {self.group_info['layer_count']}\n"
        info_text += f"可用分类: {', '.join(self.group_info['categories']) if self.group_info['categories'] else '无'}"

        info_label = QLabel(info_text)
        info_label.setStyleSheet("color: #8E8E93; font-size: 9pt;")
        layout.addWidget(info_label)

        # 图层列表
        layers_text = "绑定图层: " + ", ".join(self.group_info['layers'])
        layers_label = QLabel(layers_text)
        layers_label.setWordWrap(True)
        layers_label.setStyleSheet("color: #C7C7C9; font-size: 9pt;")
        layout.addWidget(layers_label)

        # 操作按钮
        button_layout = QHBoxLayout()

        delete_btn = QPushButton("删除组")
        delete_btn.clicked.connect(self.delete_group)
        button_layout.addWidget(delete_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # 设置样式
        self.setStyleSheet("""
            BindingGroupWidget {
                border: 1px solid #303033;
                border-radius: 4px;
                background-color: #1F1F1F;
                margin: 2px;
            }
        """)

    def delete_group(self):
        """删除绑定组"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除绑定组 '{self.group_info['name']}' 吗？\n这将解除所有图层的绑定关系。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.binding_manager.delete_binding_group(self.group_info['group_id'])
            # 使用直接的对话框引用来刷新
            self.dialog.refresh_groups()
            self.dialog.refresh_layer_list()


class LayerBindingManagerDialog(QDialog):
    """图层绑定管理器对话框"""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.binding_manager = document.binding_manager

        self.setWindowTitle("图层绑定管理器")
        self.setMinimumSize(800, 600)
        self.setup_ui()
        self.refresh_groups()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 左侧：绑定组列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        left_layout.addWidget(QLabel("现有绑定组:"))

        self.groups_list = QListWidget()
        left_layout.addWidget(self.groups_list)

        # 全局设置
        global_group = QGroupBox("全局设置")
        global_layout = QFormLayout()

        self.global_enabled_cb = QCheckBox()
        self.global_enabled_cb.setChecked(self.binding_manager.global_enabled)
        self.global_enabled_cb.clicked.connect(self.toggle_global_enabled)
        global_layout.addRow("启用绑定功能:", self.global_enabled_cb)

        global_group.setLayout(global_layout)
        left_layout.addWidget(global_group)

        splitter.addWidget(left_widget)

        # 右侧：创建绑定组
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 创建新绑定组
        create_group = QGroupBox("创建新绑定组")
        create_layout = QFormLayout()

        self.group_name_edit = QLineEdit()
        self.group_name_edit.setPlaceholderText("输入绑定组名称，如：角色组")
        create_layout.addRow("组名称:", self.group_name_edit)

        # 创建按钮
        create_btn = QPushButton("创建绑定组")
        create_btn.clicked.connect(self.create_binding_group)
        create_layout.addRow("", create_btn)

        # 完成组的布局设置
        create_group.setLayout(create_layout)
        right_layout.addWidget(create_group)

        # 图层选择
        layers_label = QLabel("选择要绑定的图层 (按住Ctrl多选):")
        right_layout.addWidget(layers_label)

        self.layers_list = QListWidget()
        self.layers_list.setSelectionMode(QListWidget.MultiSelection)

        # 填充图层列表
        for i, layer in enumerate(self.document.layers):
            item = QListWidgetItem(f"{layer.name} ({layer.width}x{layer.height})")
            item.setData(Qt.UserRole, i)  # 存储图层索引

            # 如果图层已绑定，显示绑定信息
            binding_info = self.binding_manager.get_layer_binding_info(layer)
            if binding_info:
                group_id, group_name = binding_info
                item.setText(f"{layer.name} [已绑定到: {group_name}]")
                item.setBackground(Qt.lightGray)

            self.layers_list.addItem(item)

        right_layout.addWidget(self.layers_list)

        # 文件分析预览
        preview_group = QGroupBox("文件分析预览")
        preview_layout = QVBoxLayout()

        analyze_btn = QPushButton("分析所选图层文件")
        analyze_btn.clicked.connect(self.analyze_selected_layers)
        preview_layout.addWidget(analyze_btn)

        self.analysis_text = QTextEdit()
        self.analysis_text.setMaximumHeight(150)
        self.analysis_text.setReadOnly(True)
        preview_layout.addWidget(self.analysis_text)

        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)

        right_layout.addStretch()
        splitter.addWidget(right_widget)

        # 设置分割器比例
        splitter.setSizes([400, 400])

        # 底部按钮
        button_layout = QHBoxLayout()

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_groups)
        button_layout.addWidget(refresh_btn)

        button_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def refresh_groups(self):
        """刷新绑定组列表 - 增强版，重新分析文字图层"""
        print("[绑定管理器UI] 开始刷新绑定组...")

        # 🔧 新增：重新分析所有绑定组中的文字图层
        for group_id, group in self.binding_manager.binding_groups.items():
            print(f"[绑定管理器UI] 重新分析绑定组: {group.name}")
            # 触发绑定组的分类重建
            group._rebuild_file_categories()

        self.groups_list.clear()

        groups_info = self.binding_manager.get_binding_groups_info()

        if not groups_info:
            item = QListWidgetItem("暂无绑定组")
            item.setFlags(Qt.NoItemFlags)
            self.groups_list.addItem(item)
            print("[绑定管理器UI] 没有可用的绑定组")
            return

        print(f"[绑定管理器UI] 找到 {len(groups_info)} 个绑定组")

        for group_info in groups_info:
            item = QListWidgetItem()
            group_widget = BindingGroupWidget(group_info, self.binding_manager, self, self)

            item.setSizeHint(group_widget.sizeHint())
            self.groups_list.addItem(item)
            self.groups_list.setItemWidget(item, group_widget)

            print(f"[绑定管理器UI] 添加绑定组: {group_info['name']}, 分类: {len(group_info['categories'])} 个")

        print("[绑定管理器UI] 绑定组刷新完成")

    def toggle_global_enabled(self, enabled):
        """切换全局绑定开关"""
        self.binding_manager.set_global_enabled(enabled)

    def create_binding_group(self):
        """创建新的绑定组"""
        group_name = self.group_name_edit.text().strip()
        if not group_name:
            # 如果输入框为空，弹出输入对话框
            from PySide6.QtWidgets import QInputDialog
            group_name, ok = QInputDialog.getText(
                self,
                "输入绑定组名称",
                "请输入绑定组名称:",
                text="角色组"
            )
            if not ok or not group_name.strip():
                return
            group_name = group_name.strip()
            # 将输入的名称设置到输入框中
            self.group_name_edit.setText(group_name)

        # 获取选中的图层
        selected_items = self.layers_list.selectedItems()
        if len(selected_items) < 2:
            QMessageBox.warning(self, "选择错误", "请至少选择2个图层进行绑定")
            return

        selected_layers = []
        for item in selected_items:
            layer_index = item.data(Qt.UserRole)
            layer = self.document.layers[layer_index]

            # 检查图层是否已绑定
            if self.binding_manager.is_layer_bound(layer):
                reply = QMessageBox.question(
                    self,
                    "图层已绑定",
                    f"图层 '{layer.name}' 已绑定到其他组。\n是否要将其移到新组？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    continue
                else:
                    # 从原组移除
                    self.binding_manager.remove_layer_from_group(layer)

            selected_layers.append(layer)

        if len(selected_layers) < 2:
            QMessageBox.warning(self, "选择错误", "有效的绑定图层不足2个")
            return

        # 创建绑定组
        try:
            group_id = self.binding_manager.create_binding_group(group_name, selected_layers)

            # 🔧 检查绑定组的有效性（是否有共同分类）
            group = self.binding_manager.binding_groups[group_id]
            available_categories = group.get_available_categories()

            if not available_categories:
                reply = QMessageBox.warning(
                    self,
                    "绑定组警告",
                    f"绑定组 '{group_name}' 已创建，但没有发现可用的共同分类。\n\n这意味着图层之间可能没有匹配的文件名或文字内容（非同类绑定）。\n\n是否保留此绑定组？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.No:
                    self.binding_manager.delete_binding_group(group_id)
                    # 刷新显示以确保一致性
                    self.refresh_groups()
                    self.refresh_layer_list()
                    return
                else:
                    QMessageBox.information(self, "创建成功", f"绑定组 '{group_name}' 创建成功（无可用分类）。")
            else:
                QMessageBox.information(self, "创建成功", f"绑定组 '{group_name}' 创建成功！")

            # 清空输入
            self.group_name_edit.clear()

            # 刷新显示
            self.refresh_groups()
            self.refresh_layer_list()

        except Exception as e:
            QMessageBox.critical(self, "创建失败", f"创建绑定组时出错: {str(e)}")

    def refresh_layer_list(self):
        """刷新图层列表显示"""
        for i in range(self.layers_list.count()):
            item = self.layers_list.item(i)
            layer_index = item.data(Qt.UserRole)
            layer = self.document.layers[layer_index]

            # 更新显示文本
            binding_info = self.binding_manager.get_layer_binding_info(layer)
            if binding_info:
                group_id, group_name = binding_info
                item.setText(f"{layer.name} [已绑定到: {group_name}]")
                item.setBackground(Qt.lightGray)
            else:
                item.setText(f"{layer.name} ({layer.width}x{layer.height})")
                item.setBackground(Qt.white)

    def analyze_selected_layers(self):
        """分析选中图层的文件"""
        selected_items = self.layers_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要分析的图层")
            return

        analysis_result = []
        analysis_result.append("=== 文件分析结果 ===\n")

        all_categories = set()
        layer_categories = {}

        for item in selected_items:
            layer_index = item.data(Qt.UserRole)
            layer = self.document.layers[layer_index]

            analysis_result.append(f"图层: {layer.name}")
            analysis_result.append(f"路径: {layer.image_source}")

            # 检查是否为文字图层
            is_text_layer = False
            if hasattr(self.binding_manager, '_is_text_layer'):
                is_text_layer = self.binding_manager._is_text_layer(layer)
            elif hasattr(layer, 'text_content') or hasattr(layer, 'get_text_lines'):
                is_text_layer = True

            if (not layer.image_source or not os.path.isdir(layer.image_source)) and not is_text_layer:
                analysis_result.append(f"  {IconManager.get_icon_text('remove')} 无效的文件夹路径\n")
                continue

            # 分析文件或文字
            if is_text_layer:
                categories = self._analyze_text_layer(layer)
            else:
                categories = self._analyze_layer_files(layer)

            layer_categories[layer.name] = categories
            all_categories.update(categories.keys())

            if categories:
                if is_text_layer:
                    analysis_result.append(f"  {IconManager.get_icon_text('edit')} 发现 {len(categories)} 个文字分类:")
                else:
                    analysis_result.append(f"  {IconManager.get_icon_text('folder')} 发现 {len(categories)} 个文件分类:")

                for category, files in categories.items():
                    if is_text_layer:
                        analysis_result.append(f"    - {category}")
                    else:
                        analysis_result.append(f"    - {category}: {len(files)} 个文件")
            else:
                if is_text_layer:
                     analysis_result.append(f"  {IconManager.get_icon_text('remove')} 未识别到有效的文字分类")
                else:
                     analysis_result.append(f"  {IconManager.get_icon_text('remove')} 未发现有效的图像文件")

            analysis_result.append("")

        # 分析公共分类
        if len(selected_items) > 1:
            analysis_result.append("=== 公共分类分析 ===")
            common_categories = all_categories.copy()
            for layer_name, categories in layer_categories.items():
                common_categories &= set(categories.keys())

            if common_categories:
                analysis_result.append(f"{IconManager.get_icon_text('success')} 发现 {len(common_categories)} 个公共分类:")
                for category in sorted(common_categories):
                    analysis_result.append(f"  - {category}")
                analysis_result.append("\n这些分类可以用于绑定匹配！")
            else:
                analysis_result.append(f"{IconManager.get_icon_text('remove')} 没有发现公共分类")
                analysis_result.append("建议检查文件命名规则是否一致")

        self.analysis_text.setText("\n".join(analysis_result))

    def _analyze_text_layer(self, layer):
        """分析文字图层的分类"""
        categories = {}

        # 获取文字内容
        text_lines = []
        if hasattr(layer, 'get_text_lines'):
             lines = layer.get_text_lines()
             if lines:
                 text_lines.extend(lines)

        if hasattr(layer, 'text_content') and layer.text_content:
             if layer.text_content not in text_lines:
                 text_lines.append(layer.text_content)

        if not text_lines:
            return {}

        for text in text_lines:
            if not text:
                continue

            # 使用绑定管理器的提取逻辑
            keywords = set()
            if hasattr(self.binding_manager, '_extract_keywords_from_text'):
                keywords = self.binding_manager._extract_keywords_from_text(text)
            else:
                # 简单的后备逻辑
                keywords.add(str(text).strip())

            # 同时将完整文本作为一个分类（如果它看起来像一个分类）
            text_str = str(text).strip()
            if len(text_str) < 10 and text_str not in keywords:
                keywords.add(text_str)

            for keyword in keywords:
                if keyword not in categories:
                    categories[keyword] = []
                # 添加虚拟路径或直接添加文本内容作为"文件"
                categories[keyword].append(f"text://{text}")

        return categories

    def _analyze_layer_files(self, layer):
        """分析单个图层的文件"""
        if not layer.image_source or not os.path.isdir(layer.image_source):
            return {}

        categories = {}
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']

        try:
            for file in os.listdir(layer.image_source):
                ext = os.path.splitext(file)[1].lower()
                if ext in image_extensions:
                    filename_without_ext = os.path.splitext(file)[0]
                    core_name = self._extract_core_name(filename_without_ext)

                    if core_name not in categories:
                        categories[core_name] = []
                    categories[core_name].append(file)
        except Exception as e:
            safe_print(f"分析图层文件时出错: {e}")

        return categories

    def _extract_core_name(self, filename: str) -> str:
        """提取文件名的核心部分"""
        # 去除扩展的分隔符与尾随修饰
        name = str(filename).strip()
        # 优先按 '-' 分割
        if '-' in name:
            name = name.split('-')[0].strip()
        else:
            # 再按 '_' 分割，并移除末尾纯数字片段
            if '_' in name:
                parts = name.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    name = '_'.join(parts[:-1])
                else:
                    name = str(filename)
        # 去掉末尾数字
        import re
        m = re.match(r'^(.+?)(\d+)$', name)
        if m:
            return m.group(1).strip('_-')
        return name

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            print("[DEBUG] Message encoding failed")

# 为了向后兼容，创建别名
BindingManagerDialog = LayerBindingManagerDialog
