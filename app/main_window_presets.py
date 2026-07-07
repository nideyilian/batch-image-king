# -*- coding: utf-8 -*-
"""Main window components."""

from PySide6.QtWidgets import (QMainWindow, QDockWidget, QFileDialog,                                QVBoxLayout, QWidget, QMenu, QToolBar, QSplitter,                               QLabel, QSpinBox, QHBoxLayout, QPushButton, QMessageBox, QInputDialog,                               QTabWidget, QTabBar, QDialog, QFormLayout, QDialogButtonBox,                               QSizePolicy, QLineEdit)
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QSettings, QTimer
from PySide6.QtGui import QIcon, QColor, QAction, QCloseEvent, QKeySequence, QPixmap
from app.ui.canvas import CanvasWidget
from app.ui.layer_panel import LayerPanel
from app.models.document import Document
from app.models.document_manager import DocumentManager
from app.ui.document_tab import DocumentTab
from app.ui.new_canvas_dialog import NewCanvasDialog
from app.ui.layer_properties import LayerPropertiesPanel
from app.utils.preset_manager import PresetManager
from app.ui.status_indicators import status_manager
from app.ui.visual_hierarchy import VisualHierarchy
import os
import pickle

class MainWindowPresets(object):
    def save_as_preset(self):
        """将所有打开的标签页保存为预设"""
        # 检查是否有打开的标签页
        if self.tab_widget.count() == 0:
            QMessageBox.warning(self, "保存预设", "没有打开的标签页")
            return
        
        # 询问预设名称
        default_name = self._current_editing_preset_name or ""
        preset_name, ok = QInputDialog.getText(
            self,
            "保存预设",
            "输入预设名称:",
            QLineEdit.Normal,
            default_name
        )
        if not ok or not preset_name:
            return
    
        # 收集所有打开的标签页文档
        documents = []
        print(f"准备保存预设 '{preset_name}'，包含 {self.tab_widget.count()} 个标签页")
    
        for i in range(self.tab_widget.count()):
            self._sync_document_view_settings_from_tab(i)
            # 获取对应的文档
            doc = self.document_manager.get_document(i)
        
            # 获取标签页实际显示的文本
            tab_text = self.tab_widget.tabText(i)
            # 如果标签页文本以 " *" 结尾 (表示未保存)，移除它
            if tab_text.endswith(" *"):
                tab_text = tab_text[:-2]
            
            # 设置tab_name属性和original_tab_name属性
            doc.tab_name = tab_text
            doc.original_tab_name = tab_text
        
            print(f"标签页 {i}: '{tab_text}'")
            documents.append(doc)
    
        # 获取全局设置（如果有的话）
        global_settings = {}
        if hasattr(self, 'get_global_settings'):
            global_settings = self.get_global_settings()
        
        # 使用预设管理器的save_preset_documents方法保存多标签页预设
        result = self.preset_manager.save_preset_documents(
            preset_name,
            "",  # 空描述
            documents,
            global_settings
        )
    
        # 检查结果
        if isinstance(result, dict) and result.get("duplicate"):
            # 提示用户是否要更新已有预设
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("预设名称已存在")
            msg_box.setText(f"已存在名为 '{result['name']}' 的预设，是否要更新它？")
            msg_box.setIcon(QMessageBox.Question)
        
            yes_btn = msg_box.addButton("是", QMessageBox.AcceptRole)
            no_btn = msg_box.addButton("否", QMessageBox.RejectRole)
        
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
        
            if clicked_button == yes_btn:
                # 更新已有预设
                existing_id = result["existing_id"]
                success = self.preset_manager.delete_preset(existing_id)
            
                if success:
                    # 然后用相同名称保存新预设
                    preset_id = self.preset_manager.save_preset_documents(
                        preset_name,
                        "",  # 空描述
                        documents,
                        global_settings
                    )
                
                    if preset_id:
                        self._set_current_editing_preset(preset_id, preset_name)
                        QMessageBox.information(self, "保存预设", f"预设 '{preset_name}' 已更新 (包含 {len(documents)} 个标签页)")
                    else:
                        QMessageBox.warning(self, "保存预设", "更新预设失败")
                else:
                    QMessageBox.warning(self, "保存预设", "删除旧预设失败，无法完成更新")
        elif result:  # 保存成功
            self._set_current_editing_preset(result, preset_name)
            QMessageBox.information(self, "保存预设", f"预设 '{preset_name}' 已保存 (包含 {len(documents)} 个标签页)")
        else:  # 保存失败
            QMessageBox.warning(self, "保存预设", "保存预设失败")

    def load_preset(self):
        """打开预设中心。"""
        self.open_preset_store()

    def manage_presets(self):
        """打开预设中心。"""
        self.open_preset_store()

    def open_preset_store(self):
        """打开应用商店式预设中心。"""
        from app.ui.preset_store_dialog import PresetStoreDialog

        dialog = PresetStoreDialog(self, self)
        dialog.preset_edit_requested.connect(
            lambda preset_id: dialog.accept() if self._edit_preset_from_store(preset_id) else None
        )
        dialog.exec()

    def _edit_preset_from_store(self, preset_id):
        """从预设中心进入编辑。"""
        if not self._confirm_unsaved_before_loading_preset():
            return False

        close_existing = False
        if self.document_manager.get_document_count() > 0:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("进入编辑")
            msg_box.setText("是否要关闭现有标签页并加载预设？\n选择“否”会把预设添加到当前标签页之后。")
            msg_box.setIcon(QMessageBox.Question)
            yes_btn = msg_box.addButton("关闭现有", QMessageBox.AcceptRole)
            no_btn = msg_box.addButton("追加加载", QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            if clicked_button == cancel_btn:
                return False
            close_existing = clicked_button == yes_btn

        return self.apply_preset_to_tabs(preset_id, close_existing=close_existing)

    def _confirm_unsaved_before_loading_preset(self):
        """加载预设前处理未保存文档。"""
        any_modified = False
        for i in range(self.document_manager.get_document_count()):
            doc = self.document_manager.get_document(i)
            if hasattr(doc, 'is_modified') and doc.is_modified:
                any_modified = True
                break

        if not any_modified:
            return True

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("加载预设")
        msg_box.setText("当前有未保存的文档。继续加载预设前是否保存？")
        msg_box.setIcon(QMessageBox.Question)
        save_btn = msg_box.addButton("保存", QMessageBox.AcceptRole)
        discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.exec()
        clicked_button = msg_box.clickedButton()

        if clicked_button == cancel_btn:
            return False
        if clicked_button == save_btn:
            for i in range(self.document_manager.get_document_count()):
                if self.document_manager.is_document_modified(i):
                    self.tab_widget.setCurrentIndex(i)
                    if not self.save_document():
                        return False
        return True

    def apply_preset_to_tabs(self, preset_id, close_existing=False):
        """将预设加载到编辑标签页。"""
        preset_data = self.preset_manager.load_preset(preset_id)
        summary = self.preset_manager.get_preset_summary(preset_id) or {}
        preset_name = summary.get('name', '预设')
        if not preset_data:
            QMessageBox.warning(self, "加载预设", "无法加载预设数据")
            return False

        if close_existing:
            while self.tab_widget.count() > 0:
                self.close_tab(0)

        try:
            from app.utils.preset_document_loader import documents_from_preset_data
            documents = documents_from_preset_data(preset_data, parent=self)
            if documents:
                created_tabs = 0
                for document in documents:
                    tab_index = self.create_new_tab(document)
                    tab_name = getattr(document, 'original_tab_name', None) or getattr(document, 'tab_name', None) or f"标签页 {tab_index + 1}"
                    self.tab_widget.setTabText(tab_index, tab_name)
                    created_tabs += 1
                self._set_current_editing_preset(
                    preset_id,
                    preset_name,
                    summary.get('description', '')
                )
                QMessageBox.information(self, "加载预设", f"已成功加载预设 '{preset_name}'，包含 {created_tabs} 个标签页")
                return True

            QMessageBox.warning(self, "加载预设", f"无法加载预设 '{preset_name}'")
            return False
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"加载预设时出错: {e}\n{error_details}")
            QMessageBox.warning(self, "加载预设", f"无法加载预设 '{preset_name}':\n{str(e)}")
            return False

    def _set_current_editing_preset(self, preset_id, name, description=None):
        """记录当前从预设进入编辑的上下文，用于下次保存时默认回填名称。"""
        summary = self.preset_manager.get_preset_summary(preset_id) or {}
        self._current_editing_preset_id = preset_id
        self._current_editing_preset_name = name or summary.get('name', '')
        if description is None:
            description = summary.get('description', '')
        self._current_editing_preset_description = description or ""

    def manage_canvas_presets(self):
        """打开画布预设管理对话框"""
        from app.ui.canvas_preset_dialog import CanvasPresetManagerDialog
        dialog = CanvasPresetManagerDialog(self)
        dialog.exec()
