from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                           QListWidget, QListWidgetItem, QLabel, QFrame,
                           QLineEdit, QFileDialog, QMessageBox, QInputDialog,
                           QScrollArea, QTextBrowser)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
import os

class PresetPanel(QWidget):
    """预设面板，显示预设列表和相关操作"""
    # 定义信号
    preset_selected = Signal(str)  # 选择了预设时传递预设ID
    preset_applied = Signal(str)   # 应用预设时传递预设ID

    def __init__(self, preset_manager, main_window=None, parent=None):
        super().__init__(parent)
        self.preset_manager = preset_manager
        self.main_window = main_window
        self.current_preset_id = None
        self.setup_ui()

    def setup_ui(self):
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_label = QLabel("预设")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        main_layout.addWidget(title_label)

        # 按钮区域（功能操作）
        buttons_layout = QHBoxLayout()

        # 保存预设按钮
        self.save_button = QPushButton("保存")
        self.save_button.setToolTip("保存当前标签页为预设")
        self.save_button.clicked.connect(self.save_preset)
        buttons_layout.addWidget(self.save_button)

        # 应用预设按钮
        self.apply_button = QPushButton("应用")
        self.apply_button.setToolTip("应用选中的预设")
        self.apply_button.clicked.connect(self.apply_preset)
        self.apply_button.setEnabled(False)  # 初始禁用
        buttons_layout.addWidget(self.apply_button)

        main_layout.addLayout(buttons_layout)

        # 第二排按钮
        buttons_layout2 = QHBoxLayout()

        # 删除预设按钮
        self.delete_button = QPushButton("删除")
        self.delete_button.setToolTip("删除选中的预设")
        self.delete_button.clicked.connect(self.delete_preset)
        self.delete_button.setEnabled(False)  # 初始禁用
        buttons_layout2.addWidget(self.delete_button)

        # 导出预设按钮
        self.export_button = QPushButton("导出")
        self.export_button.setToolTip("导出选中的预设")
        self.export_button.clicked.connect(self.export_preset)
        self.export_button.setEnabled(False)  # 初始禁用
        buttons_layout2.addWidget(self.export_button)

        # 导入预设按钮
        self.import_button = QPushButton("导入")
        self.import_button.setToolTip("导入预设或预设合集")
        self.import_button.clicked.connect(self.import_preset)
        buttons_layout2.addWidget(self.import_button)

        main_layout.addLayout(buttons_layout2)

        # 添加第三排按钮，用于其他操作
        buttons_layout3 = QHBoxLayout()

        # 导出所有预设按钮
        self.export_all_button = QPushButton("导出所有")
        self.export_all_button.setToolTip("将所有预设导出为一个合集文件")
        self.export_all_button.clicked.connect(self.export_all_presets)
        buttons_layout3.addWidget(self.export_all_button)

        # 管理预设按钮
        self.manage_button = QPushButton("管理预设")
        self.manage_button.setToolTip("打开预设管理器")
        self.manage_button.clicked.connect(self.show_preset_manager)
        buttons_layout3.addWidget(self.manage_button)

        main_layout.addLayout(buttons_layout3)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索预设...")
        self.search_edit.textChanged.connect(self.filter_presets)
        main_layout.addWidget(self.search_edit)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)

        # 预设列表
        self.preset_list = QListWidget()
        self.preset_list.setSelectionMode(QListWidget.SingleSelection)
        self.preset_list.itemClicked.connect(self.on_preset_clicked)
        self.preset_list.itemDoubleClicked.connect(self.on_preset_double_clicked)
        main_layout.addWidget(self.preset_list)

        # 创建预设信息显示区域 - 带有滚动条
        info_layout = QVBoxLayout()

        # 标题
        info_title = QLabel("预设信息")
        info_title.setAlignment(Qt.AlignCenter)
        info_title.setStyleSheet("font-weight: bold; padding: 2px;")
        info_layout.addWidget(info_title)

        # 分隔线
        info_line = QFrame()
        info_line.setFrameShape(QFrame.HLine)
        info_line.setFrameShadow(QFrame.Sunken)
        info_layout.addWidget(info_line)

        # 信息浏览器
        self.info_browser = QTextBrowser()
        self.info_browser.setMinimumHeight(120)
        self.info_browser.setMaximumHeight(220)
        self.info_browser.setOpenExternalLinks(False)
        self.info_browser.setStyleSheet("font-size: 12px; background-color: transparent;")

        # 默认文本
        self.info_browser.setHtml("<center><i>选择一个预设查看详细信息</i></center>")

        info_layout.addWidget(self.info_browser)
        main_layout.addLayout(info_layout)

        # 加载预设列表
        self.refresh_presets()

    def refresh_presets(self):
        """刷新预设列表"""
        self.preset_list.clear()

        presets = self.preset_manager.get_all_presets()
        for preset in presets:
            item = QListWidgetItem(preset.get("name", "未命名预设"))
            # 存储预设ID为用户数据
            item.setData(Qt.UserRole, preset.get("id"))
            # 设置提示信息显示描述
            description = preset.get("description", "")
            if description:
                item.setToolTip(description)
            self.preset_list.addItem(item)

    def filter_presets(self, text):
        """根据搜索文本过滤预设列表"""
        for i in range(self.preset_list.count()):
            item = self.preset_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def on_preset_clicked(self, item):
        """点击预设项时触发"""
        preset_id = item.data(Qt.UserRole)
        self.current_preset_id = preset_id
        self.preset_selected.emit(preset_id)

        # 启用相关按钮
        self.apply_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.export_button.setEnabled(True)

        # 更新预设信息显示
        self.update_preset_info(preset_id)

    def on_preset_double_clicked(self, item):
        """双击预设项时触发应用预设"""
        preset_id = item.data(Qt.UserRole)
        self.preset_applied.emit(preset_id)

    def get_selected_preset_id(self):
        """获取当前选中的预设ID"""
        selected_items = self.preset_list.selectedItems()
        if selected_items:
            return selected_items[0].data(Qt.UserRole)
        return None

    def save_preset(self):
        """保存所有标签页为预设"""
        if not self.main_window or not hasattr(self.main_window, 'tab_widget'):
            QMessageBox.warning(self, "错误", "无法获取标签页")
            return

        if self.main_window.tab_widget.count() == 0:
            QMessageBox.warning(self, "错误", "没有标签页可保存")
            return

        # 使用更好的保存对话框
        from app.ui.preset_manager_dialog import PresetSaveDialog
        dialog = PresetSaveDialog(self.main_window, self)

        if not dialog.exec():
            return

        # 获取预设信息
        preset_info = dialog.get_preset_info()
        selected_tabs = dialog.get_selected_tabs()

        name = preset_info["name"]
        description = preset_info["description"]

        # 收集选中的标签页文档
        documents = []
        safe_print(f"准备保存预设 '{name}'，包含 {len(selected_tabs)} 个选中的标签页")

        for tab_index in selected_tabs:
            if hasattr(self.main_window, '_sync_document_view_settings_from_tab'):
                self.main_window._sync_document_view_settings_from_tab(tab_index)
            # 获取对应的文档
            doc = self.main_window.documents[tab_index]

            # 获取标签页实际显示的文本
            tab_text = self.main_window.tab_widget.tabText(tab_index)
            # 如果标签页文本以 " *" 结尾 (表示未保存)，移除它
            if tab_text.endswith(" *"):
                tab_text = tab_text[:-2]

            # 显式设置tab_name属性和original_tab_name属性
            doc.tab_name = tab_text
            doc.original_tab_name = tab_text

            safe_print(f"标签页 {tab_index}: '{tab_text}'")
            documents.append(doc)

        # 获取全局设置
        global_settings = {}
        if hasattr(self.main_window, 'get_global_settings'):
            global_settings = self.main_window.get_global_settings()

        # 使用新方法直接从文档对象保存预设
        result = self.preset_manager.save_preset_documents(
            name,
            description,  # 使用用户输入的描述
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
                        name,
                        description,  # 使用用户输入的描述
                        documents,
                        global_settings
                    )

                    if preset_id:
                        QMessageBox.information(self, "成功", f"预设 '{name}' 已更新 (包含 {len(documents)} 个标签页)")
                        self.refresh_presets()
                    else:
                        QMessageBox.warning(self, "错误", "更新预设失败")
                else:
                    QMessageBox.warning(self, "错误", "删除旧预设失败，无法完成更新")
            # 如果用户选择不更新，则不执行任何操作

        elif result:  # 正常保存成功
            QMessageBox.information(self, "成功", f"预设 '{name}' 已保存 (包含 {len(documents)} 个标签页)")
            self.refresh_presets()
        else:  # 保存失败
            QMessageBox.warning(self, "错误", "保存预设失败")

    def apply_preset(self):
        """应用选中的预设"""
        preset_id = self.get_selected_preset_id()
        if preset_id:
            self.preset_applied.emit(preset_id)
        else:
            QMessageBox.warning(self, "错误", "请先选择一个预设")

    def delete_preset(self):
        """删除选中的预设"""
        preset_id = self.get_selected_preset_id()
        if not preset_id:
            return

        # 获取预设名称
        selected_items = self.preset_list.selectedItems()
        preset_name = selected_items[0].text()

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除预设 '{preset_name}' 吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            success = self.preset_manager.delete_preset(preset_id)
            if success:
                QMessageBox.information(self, "成功", f"预设 '{preset_name}' 已删除")
                self.refresh_presets()

                # 禁用相关按钮
                self.apply_button.setEnabled(False)
                self.delete_button.setEnabled(False)
                self.export_button.setEnabled(False)
            else:
                QMessageBox.warning(self, "错误", "删除预设失败")

    def export_preset(self):
        """导出选中的预设"""
        preset_id = self.get_selected_preset_id()
        if not preset_id:
            return

        # 获取预设名称
        selected_items = self.preset_list.selectedItems()
        preset_name = selected_items[0].text()

        # 弹出文件保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出预设",
            f"{preset_name}.preset",
            "预设文件 (*.preset);;所有文件 (*)"
        )

        if file_path:
            success = self.preset_manager.export_preset(preset_id, file_path)
            if success:
                QMessageBox.information(self, "成功", f"预设已导出到: {file_path}")
            else:
                QMessageBox.warning(self, "错误", "导出预设失败")

    def import_preset(self):
        """导入预设"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入预设",
            "",
            "预设文件 (*.preset);;所有文件 (*)"
        )

        if file_path:
            preset_id = self.preset_manager.import_preset(file_path)
            if preset_id:
                self.refresh_presets()
                QMessageBox.information(self, "成功", "预设已导入")
            else:
                QMessageBox.warning(self, "错误", "导入预设失败，文件可能已损坏或格式不正确")

    def update_preset_info(self, preset_id):
        """更新预设信息显示"""
        preset_info = self.preset_manager.load_preset(preset_id)
        if not preset_info:
            self.info_browser.setHtml("<center><i>无法加载预设信息</i></center>")
            return

        # 基本信息
        preset_name = preset_info.get("name", "未命名预设")
        doc_count = len(preset_info.get("documents", []))
        created_at = preset_info.get("created_at", "")
        modified_at = preset_info.get("modified_at", "")
        description = preset_info.get("description", "")

        # 格式化时间
        if created_at:
            try:
                # 简化ISO格式时间显示
                created_at = created_at.split("T")[0]
            except:
                pass

        if modified_at:
            try:
                modified_at = modified_at.split("T")[0]
            except:
                pass

        # 构建HTML内容
        html = f"""
        <div style="margin-bottom: 10px;">
            <h3 style="margin: 2px 0; color: #C7C7C9;">{preset_name}</h3>
            <div style="color: #555; font-size: 11px;">
                创建: {created_at} | 修改: {modified_at}
            </div>
            <div style="margin: 8px 0; color: #C7C7C9;">
                <b>包含 {doc_count} 个标签页</b>
            </div>
        """

        # 添加描述（如果有）
        if description:
            html += f"""
            <div style="margin: 5px 0; border-left: 3px solid #aaa; padding-left: 8px; color: #444;">
                {description}
            </div>
            """

        # 添加标签页信息
        html += """
        <div style="margin-top: 10px;">
            <b style="color: #C7C7C9;">标签页列表:</b>
            <table style="width: 100%; margin-top: 5px; border-collapse: collapse;">
                <tr style="background-color: #e0e0e0;">
                    <th style="text-align: left; padding: 3px; border: 1px solid #ccc; color: #C7C7C9;">标签名</th>
                    <th style="text-align: center; padding: 3px; border: 1px solid #ccc; color: #C7C7C9;">画布尺寸</th>
                    <th style="text-align: center; padding: 3px; border: 1px solid #ccc; color: #C7C7C9;">图层数</th>
                </tr>
        """

        # 获取每个文档的信息
        documents = preset_info.get("documents", [])
        for i, doc_info in enumerate(documents):
            # 获取标签页名称
            tab_name = doc_info.get("original_tab_name", doc_info.get("name", f"标签页 {i+1}"))

            # 获取画布尺寸
            canvas_width = doc_info.get("canvas_width", 0)
            canvas_height = doc_info.get("canvas_height", 0)
            canvas_size = f"{canvas_width}×{canvas_height}" if canvas_width and canvas_height else "未知"

            # 获取图层数
            layers = doc_info.get("layers", [])
            layer_count = len(layers)

            # 添加到表格
            bg_color = "#f0f0f0" if i % 2 == 0 else "#ffffff"
            html += f"""
            <tr style="background-color: {bg_color};">
                <td style="padding: 3px; border: 1px solid #ccc; color: #C7C7C9;">{tab_name}</td>
                <td style="text-align: center; padding: 3px; border: 1px solid #ccc; color: #C7C7C9;">{canvas_size}</td>
                <td style="text-align: center; padding: 3px; border: 1px solid #ccc; color: #C7C7C9;">{layer_count}</td>
            </tr>
            """

        # 关闭表格
        html += """
            </table>
        </div>
        </div>
        """

        # 设置HTML内容
        self.info_browser.setHtml(html)

    def export_all_presets(self):
        """导出所有预设为一个合集文件"""
        # 弹出文件保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出所有预设",
            "预设合集.preset",
            "预设合集文件 (*.preset);;所有文件 (*)"
        )

        if not file_path:
            return

        # 调用预设管理器的方法导出所有预设
        preset_count = self.preset_manager.export_all_presets(file_path)

        if preset_count > 0:
            QMessageBox.information(self, "成功", f"已将 {preset_count} 个预设导出到: {file_path}")
        else:
            QMessageBox.warning(self, "错误", "导出所有预设失败，可能没有可导出的预设")

    def show_preset_manager(self):
        """打开预设管理对话框"""
        from app.ui.preset_manager_dialog import PresetManagerDialog
        dialog = PresetManagerDialog(self.main_window, self)

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


        # 连接信号
        dialog.preset_applied.connect(self.preset_applied.emit)

        # 显示对话框
        dialog.exec()

        # 对话框关闭后刷新预设列表
        self.refresh_presets() 