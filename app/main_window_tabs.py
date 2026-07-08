# -*- coding: utf-8 -*-
"""Main window components."""

import logging

logger = logging.getLogger(__name__)
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

class MainWindowTabs(object):
    def active_document_changed(self, document):
        """当活动文档变更时"""
        # 先断开旧文档的信号连接
        if hasattr(self, 'document') and self.document:
            try:
                # 断开信号连接
                self.document.history_changed.disconnect(self.update_history_actions)
                self.document.document_changed.disconnect(self.update_document_info)
                # 断开图层选择信号
                if hasattr(self.document, 'layer_selected'):
                    self.document.layer_selected.disconnect(self.update_copy_paste_actions)
            except Exception:
                logger.debug("静默异常已忽略: except in main_window_tabs.py")
                pass
    
        # 更新document引用
        self.document = document
    
        # 更新面板
        if self.document and hasattr(self, 'layer_panel') and hasattr(self, 'properties_panel'):
            print(f"[主窗口] 开始更新面板，文档有效，图层数量: {len(self.document.layers)}")
        
            # 更新图层面板的文档引用 - 修复：使用set_document方法确保界面更新
            if hasattr(self.layer_panel, 'set_document'):
                print(f"[主窗口] 调用图层面板的set_document方法")
                self.layer_panel.set_document(self.document)
            else:
                print(f"[主窗口] 图层面板没有set_document方法，直接设置document属性")
                self.layer_panel.document = self.document
                # 手动触发更新
                if hasattr(self.layer_panel, 'update_layers'):
                    self.layer_panel.update_layers()
        
            # 更新属性面板
            if hasattr(self.properties_panel, 'set_document'):
                self.properties_panel.set_document(self.document)
            elif hasattr(self.properties_panel, 'document'):
                self.properties_panel.document = self.document
        
            # 更新状态指示器
            if hasattr(self, 'document_status_indicator'):
                status_manager.set_document(self.document)
        
            # 更新窗口标题
            self.update_window_title()
        
            # 更新状态栏
            if hasattr(self.document, 'canvas_width') and hasattr(self.document, 'canvas_height'):
                self.size_label.setText(f"大小: {self.document.canvas_width} x {self.document.canvas_height}")
            else:
                self.size_label.setText("大小: 0 x 0")
        
            # 连接当前文档的信号
            self.document.history_changed.connect(self.update_history_actions)
            self.document.document_changed.connect(self.update_document_info)
            # 连接图层选择信号，用于更新复制粘贴按钮状态
            if hasattr(self.document, 'layer_selected'):
                self.document.layer_selected.connect(self.update_copy_paste_actions)
        
            # 立即更新撤销/重做按钮状态
            self.update_history_actions()
        
            # 更新复制粘贴按钮状态
            self.update_copy_paste_actions()
        elif hasattr(self, 'layer_panel') and hasattr(self, 'properties_panel'):
            print(f"[主窗口] 没有活动文档，清空面板")
        
            # 没有活动文档 - 修复：使用set_document方法清空面板
            if hasattr(self.layer_panel, 'set_document'):
                print(f"[主窗口] 调用图层面板的set_document(None)")
                self.layer_panel.set_document(None)
            else:
                print(f"[主窗口] 直接设置图层面板document为None")
                self.layer_panel.document = None
                # 手动清空列表
                if hasattr(self.layer_panel, 'layer_list'):
                    self.layer_panel.layer_list.clear()
        
            if hasattr(self.properties_panel, 'set_document'):
                self.properties_panel.set_document(None)
            elif hasattr(self.properties_panel, 'document'):
                self.properties_panel.document = None
            self.setWindowTitle("图像批量合成工具")
            self.size_label.setText("大小: 0 x 0")
        
            # 禁用撤销/重做按钮
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)
        
            # 禁用复制粘贴按钮
            self.copy_layer_action.setEnabled(False)
            self.paste_layer_action.setEnabled(False)

    def update_window_title(self):
        """更新窗口标题"""
        title = "图像批量合成工具"
    
        if self.document:
            if self.document.current_file_path:
                title += f" - {os.path.basename(self.document.current_file_path)}"
            else:
                # 获取当前标签索引
                current_index = self.tab_widget.currentIndex()
                if current_index >= 0:
                    title += f" - {self.document_manager.get_document_name(current_index)}"
            
            if hasattr(self.document, 'is_modified') and self.document.is_modified:
                title += " *"
            
        self.setWindowTitle(title)

    def update_tab_name(self, index):
        """更新标签名称"""
        if index < 0 or index >= self.tab_widget.count():
            return
    
        name = self.document_manager.get_document_name(index)
        if self.document_manager.is_document_modified(index):
            name += " *"

        doc = self.document_manager.get_document(index)
        status = self._document_runtime_status_by_id.get(id(doc), "") if doc else ""
        if status:
            name += f" [{status}]"
        
        self.tab_widget.setTabText(index, name)

    def set_document_runtime_status(self, document, status_text=""):
        """设置文档运行状态并刷新对应标签名称"""
        if document is None:
            return
        doc_id = id(document)
        status_text = (status_text or "").strip()
        if status_text:
            self._document_runtime_status_by_id[doc_id] = status_text
        else:
            self._document_runtime_status_by_id.pop(doc_id, None)

        for i in range(self.document_manager.get_document_count()):
            doc = self.document_manager.get_document(i)
            if doc is document:
                self.update_tab_name(i)
                break

    def create_new_tab(self, document=None):
        """创建新标签页"""
        if document is None:
            # 创建新文档
            document = Document(parent=self)
            document.create_new(800, 600)
    
        # 创建标签页内容
        tab = DocumentTab(document)
    
        # 生成标签名
        doc_index = self.document_manager.add_document(document)
        tab_name = self.document_manager.get_document_name(doc_index)
    
        # 添加到标签页控件
        tab_index = self.tab_widget.addTab(tab, tab_name)
    
        # 激活新标签页
        self.tab_widget.setCurrentIndex(tab_index)
    
        # 连接画布信号
        tab.canvas.position_changed.connect(self.update_position_label)
    
        # 连接图层操作信号到属性面板更新
        if hasattr(tab.canvas, 'layer_moved'):
            tab.canvas.layer_moved.connect(self.on_canvas_layer_moved)
        if hasattr(tab.canvas, 'layer_resized'):
            tab.canvas.layer_resized.connect(self.on_canvas_layer_resized)
    
        return tab_index

    def _sync_document_view_settings_from_tab(self, tab_index):
        """将指定标签页画布视图设置同步到文档对象"""
        if tab_index < 0 or tab_index >= self.tab_widget.count():
            return
        tab = self.tab_widget.widget(tab_index)
        doc = self.document_manager.get_document(tab_index)
        if not tab or not doc or not hasattr(tab, 'canvas'):
            return
        canvas = tab.canvas
        if hasattr(doc, 'set_view_settings'):
            doc.set_view_settings({
                'show_rulers': bool(getattr(canvas, 'show_rulers', True)),
                'show_guides': bool(getattr(canvas, 'show_guides', True)),
                'snap_to_guides': bool(getattr(canvas, 'snap_to_guides', True)),
                'ruler_size': int(getattr(canvas, '_ruler_size', 20)),
                'horizontal_guides': list(getattr(canvas, 'horizontal_guides', [])),
                'vertical_guides': list(getattr(canvas, 'vertical_guides', [])),
                'zoom_factor': float(getattr(canvas, 'zoom_factor', 1.0)),
                'offset_x': int(getattr(canvas, 'offset', QPoint(0, 0)).x()),
                'offset_y': int(getattr(canvas, 'offset', QPoint(0, 0)).y()),
            })

    def close_tab(self, index):
        """关闭标签页"""
        if index < 0 or index >= self.tab_widget.count():
            return
    
        document = self.document_manager.get_document(index)
        if not document:
            return
    
        # 检查是否有未保存的更改
        if hasattr(document, 'is_modified') and document.is_modified:
            # 弹出确认对话框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("关闭文档")
            msg_box.setText(f"文档 '{self.document_manager.get_document_name(index)}' 有未保存的更改，是否保存？")
            msg_box.setIcon(QMessageBox.Question)
        
            save_btn = msg_box.addButton("保存", QMessageBox.AcceptRole)
            discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
        
            if clicked_button == save_btn:
                # 先激活要关闭的标签
                self.tab_widget.setCurrentIndex(index)
                # 保存文档
                if not self.save_document():
                    # 保存失败，取消关闭
                    return
            elif clicked_button == cancel_btn:
                # 取消关闭
                return
    
        # 移除标签页
        self.tab_widget.removeTab(index)
    
        # 从文档管理器中移除文档
        self._document_runtime_status_by_id.pop(id(document), None)
        self.document_manager.remove_document(index)

    def duplicate_tab(self):
        """复制当前标签页"""
        # 获取当前标签页索引
        current_index = self.tab_widget.currentIndex()
        if current_index < 0:
            return
    
        # 获取当前文档
        current_document = self.document_manager.get_document(current_index)
        if not current_document:
            return
    
        # 创建文档副本
        new_document = Document(parent=self)
        new_document.canvas_width = current_document.canvas_width
        new_document.canvas_height = current_document.canvas_height
    
        # 复制所有图层
        for layer in current_document.layers:
            if layer is None:
                continue
            # 创建图层副本
            try:
                new_layer = layer.duplicate(parent=new_document)
            except TypeError:
                new_layer = layer.duplicate()
            except Exception as e:
                print(f"复制图层失败，已跳过: {e}")
                continue
            if new_layer is not None:
                new_document.layers.append(new_layer)
    
        # 设置相同的选中图层
        new_document.selected_layer_index = current_document.selected_layer_index
    
        # 复制导出设置
        new_document.export_settings = current_document.export_settings.copy()
    
        # 标记为已修改
        new_document.is_modified = True
    
        # 创建新标签页，放在当前标签页后面
        new_tab_index = self.create_new_tab(new_document)
    
        return new_tab_index

    def show_tab_context_menu(self, position):
        """显示标签页右键菜单"""
        # 获取点击位置所在的标签页索引
        index = self.tab_widget.tabBar().tabAt(position)
        if index < 0:
            return
    
        # 创建右键菜单
        menu = QMenu()
        document = self.document_manager.get_document(index)
        export_dialog = self._get_running_export_dialog_for_document(document)
    
        # 添加菜单项
        close_action = menu.addAction("关闭标签页")
        close_other_action = menu.addAction("关闭其他标签页")
        menu.addSeparator()
        duplicate_action = menu.addAction("复制标签页")
        restore_export_action = None
        if export_dialog is not None:
            restore_export_action = menu.addAction("恢复导出窗口")
        menu.addSeparator()
        rename_action = menu.addAction("重命名标签页")
    
        # 显示菜单并获取用户选择的操作
        action = menu.exec_(self.tab_widget.tabBar().mapToGlobal(position))
    
        # 处理用户选择的操作
        if action == close_action:
            self.close_tab(index)
        elif action == close_other_action:
            self.close_other_tabs(index)
        elif action == duplicate_action:
            # 先切换到要复制的标签页
            self.tab_widget.setCurrentIndex(index)
            # 然后执行复制
            self.duplicate_tab()
        elif restore_export_action and action == restore_export_action:
            self.restore_export_dialog(index)
        elif action == rename_action:
            self.rename_tab(index)

    def _get_running_export_dialog_for_document(self, document):
        """获取文档正在后台运行的导出窗口（若存在）"""
        if document is None:
            return None
        doc_key = id(document)
        dialog = self._batch_export_dialogs_by_doc.get(doc_key)
        if dialog is not None and getattr(dialog, "_export_running", False):
            return dialog
        dialog = self._multi_tab_export_dialogs_by_doc.get(doc_key)
        if dialog is not None and getattr(dialog, "_export_started", False):
            return dialog
        return None

    def restore_export_dialog(self, index):
        """恢复指定标签页的导出窗口"""
        if index < 0 or index >= self.tab_widget.count():
            return
        document = self.document_manager.get_document(index)
        dialog = self._get_running_export_dialog_for_document(document)
        if dialog is None:
            return
        self.tab_widget.setCurrentIndex(index)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def close_other_tabs(self, keep_index):
        """关闭除了指定索引外的所有标签页"""
        if keep_index < 0 or keep_index >= self.tab_widget.count():
            return
    
        # 从后向前关闭标签页，避免索引变化问题
        for i in range(self.tab_widget.count() - 1, -1, -1):
            if i != keep_index:
                self.close_tab(i)

    def rename_tab(self, index):
        """重命名标签页"""
        if index < 0 or index >= self.tab_widget.count():
            return
    
        document = self.document_manager.get_document(index)
        if not document:
            return
    
        # 获取当前名称
        current_name = self.tab_widget.tabText(index)
        if current_name.endswith(" *"):  # 移除修改标记
            current_name = current_name[:-2]
    
        # 弹出输入对话框
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "重命名标签页", "输入新名称:", 
            text=current_name
        )
    
        if ok and new_name:
            # 如果文档模型中有name属性，也要同步更新
            if hasattr(document, 'name'):
                document.name = new_name
            document.tab_name = new_name
            document.original_tab_name = new_name
        
            # 更新标签页文本
            self.tab_widget.setTabText(index, new_name)
        
            # 如果是已修改状态，添加修改标记
            if self.document_manager.is_document_modified(index):
                self.tab_widget.setTabText(index, new_name + " *")

    def tab_changed(self, index):
        """切换标签页时触发"""
        # the current tab has changed, update the current document
        if 0 <= index < self.tab_widget.count():
            self.document_manager.set_active_document(index)
        
            # 主动更新撤销/重做按钮状态，确保与当前文档同步
            self.update_history_actions()
        else:
            # 没有标签页了
            self.document_manager.active_document_index = -1
            self.document_manager.active_document_changed.emit(None)

    def _on_controller_status_message(self, message, timeout):
        """处理控制器状态消息"""
        self.statusbar.showMessage(message, timeout)

    def _on_document_operation_completed(self, operation, success):
        """处理文档操作完成信号"""
        # 可以在这里添加额外的处理逻辑，比如更新UI状态
        if operation == "new_document" and success:
            print(f"[INFO] 新文档创建成功")
        elif operation == "open_document" and success:
            print(f"[INFO] 文档打开成功")
        elif operation.startswith("save") and success:
            print(f"[INFO] 文档保存成功")

    def _on_layer_operation_completed(self, operation, success):
        """处理图层操作完成信号"""
        # 可以在这里添加额外的处理逻辑，比如更新UI状态
        if success:
            print(f"[INFO] 图层操作成功: {operation}")
        else:
            print(f"[WARNING] 图层操作失败: {operation}")

    def _on_layer_selection_changed(self):
        """处理图层选择改变信号"""
        # 可以在这里更新UI状态，如工具栏按钮的启用状态
        # 目前只是记录日志
        pass

    def connect_signals(self):
        """连接信号与槽"""
        # 连接文档管理器信号
        self.document_manager.active_document_changed.connect(self.active_document_changed)
        self.document_manager.document_name_changed.connect(self.update_tab_name)
    
        # 连接文档控制器信号
        self.document_controller.status_message.connect(self._on_controller_status_message)
        self.document_controller.document_operation_completed.connect(self._on_document_operation_completed)
    
        # 连接图层控制器信号
        self.layer_controller.status_message.connect(self._on_controller_status_message)
        self.layer_controller.layer_operation_completed.connect(self._on_layer_operation_completed)
        self.layer_controller.layer_selection_changed.connect(self._on_layer_selection_changed)
