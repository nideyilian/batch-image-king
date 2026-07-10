"""
文档控制器
负责管理文档的创建、打开、保存等操作
保持与MainWindow的信号连接兼容性
"""

import os
from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog, QDialog
from PySide6.QtCore import QObject, Signal

from app.models.document import Document
from app.ui.new_canvas_dialog import NewCanvasDialog
from app.utils.initial_preview import prime_initial_preview


class DocumentController(QObject):
    """文档控制器类"""
    
    # 信号定义 - 保持与MainWindow兼容
    document_operation_completed = Signal(str, bool)  # 操作名, 是否成功
    status_message = Signal(str, int)  # 状态消息, 显示时间(ms)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
    def new_document(self):
        """创建新文档 - 从MainWindow迁移"""
        dialog = NewCanvasDialog(self.main_window)
        if dialog.exec():
            # 获取用户输入的参数
            width = dialog.width_spinbox.value()
            height = dialog.height_spinbox.value()
            
            # 创建新文档
            document = Document(parent=self.main_window)
            document.create_new(width, height)
            
            # 创建新标签页
            tab_index = self.main_window.create_new_tab(document)
            
            self.document_operation_completed.emit("new_document", True)
            return tab_index
        
        return None
    
    def open_document(self):
        """打开文档 - 从MainWindow迁移"""
        file_dialog = QFileDialog(self.main_window)
        file_dialog.setNameFilter("合成项目文件 (*.cmp);;所有文件 (*)")
        file_dialog.setDefaultSuffix("cmp")
        
        if file_dialog.exec():
            file_paths = file_dialog.selectedFiles()
            if file_paths:
                file_path = file_paths[0]
                
                # 创建新文档
                document = Document(parent=self.main_window)
                
                try:
                    # 加载文档
                    if document.load_document(file_path):
                        prime_initial_preview(document)
                        # 创建新标签页
                        tab_index = self.main_window.create_new_tab(document)
                        self.document_operation_completed.emit("open_document", True)
                        self.status_message.emit(f"成功打开文档: {os.path.basename(file_path)}", 3000)
                        return tab_index
                    else:
                        # 处理加载错误
                        self._handle_document_load_error(file_path)
                        self.document_operation_completed.emit("open_document", False)
                        return None
                        
                except Exception as e:
                    # 处理异常，显示更友好的错误消息
                    self._handle_document_load_exception(file_path, e)
                    self.document_operation_completed.emit("open_document", False)
                    return None
                
        return None
    
    def save_document(self):
        """保存当前文档 - 从MainWindow迁移"""
        if not self.main_window.document:
            return False
            
        if not self.main_window.document.current_file_path:
            return self.save_document_as()
        
        # 保存前同步当前标签页的视图参数（标尺/参考线/缩放等）
        current_index = self.main_window.tab_widget.currentIndex()
        if hasattr(self.main_window, '_sync_document_view_settings_from_tab'):
            self.main_window._sync_document_view_settings_from_tab(current_index)
            
        # 保存文档
        result = self.main_window.document.save_document(self.main_window.document.current_file_path)
        
        # 如果保存成功，更新状态指示器
        if result:
            from app.ui.status_indicators import status_manager
            if hasattr(self.main_window, 'document_status_indicator'):
                status_manager.mark_document_saved()
            self.document_operation_completed.emit("save_document", True)
            self.status_message.emit("文档保存成功", 2000)
        else:
            self.document_operation_completed.emit("save_document", False)
            self.status_message.emit("文档保存失败", 3000)
            
        return result
    
    def save_document_as(self):
        """另存为 - 从MainWindow迁移"""
        if not self.main_window.document:
            return False
            
        file_dialog = QFileDialog(self.main_window)
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setNameFilter("合成项目文件 (*.cmp);;所有文件 (*)")
        file_dialog.setDefaultSuffix("cmp")
        
        if file_dialog.exec():
            file_paths = file_dialog.selectedFiles()
            if file_paths:
                file_path = file_paths[0]
                
                # 保存前同步当前标签页的视图参数（标尺/参考线/缩放等）
                current_index = self.main_window.tab_widget.currentIndex()
                if hasattr(self.main_window, '_sync_document_view_settings_from_tab'):
                    self.main_window._sync_document_view_settings_from_tab(current_index)
                
                # 保存文档
                if self.main_window.document.save_document(file_path):
                    # 更新标签页名称
                    current_index = self.main_window.tab_widget.currentIndex()
                    self.main_window.update_tab_name(current_index)
                    
                    # 更新窗口标题
                    self.main_window.update_window_title()
                    
                    # 更新状态指示器
                    from app.ui.status_indicators import status_manager
                    if hasattr(self.main_window, 'document_status_indicator'):
                        status_manager.mark_document_saved()
                    
                    self.document_operation_completed.emit("save_document_as", True)
                    self.status_message.emit(f"文档另存为: {os.path.basename(file_path)}", 3000)
                    return True
                else:
                    QMessageBox.warning(self.main_window, "错误", f"无法保存文件: {file_path}")
                    self.document_operation_completed.emit("save_document_as", False)
        
        return False
    
    def _handle_document_load_error(self, file_path):
        """处理文档加载错误"""
        # 导入main模块中的错误处理函数
        try:
            from main import get_document_load_error, clear_document_load_error
            
            # 获取上次文档加载错误
            error = get_document_load_error()
            if error:
                # 显示详细错误信息
                error_dialog = QMessageBox(self.main_window)
                error_dialog.setIcon(QMessageBox.Warning)
                error_dialog.setWindowTitle("文档加载错误")
                error_dialog.setText(f"无法打开文件: {file_path}")
                error_dialog.setInformativeText("这可能是由于文件格式版本不兼容或文件已损坏。")
                error_dialog.setDetailedText(f"错误详情: {str(error)}")
                error_dialog.addButton("确定", QMessageBox.AcceptRole)
                error_dialog.exec()
                
                # 清除错误
                clear_document_load_error()
            else:
                # 显示一般错误
                QMessageBox.warning(self.main_window, "错误", f"无法打开文件: {file_path}")
        except ImportError:
            # 如果没有main模块的错误处理，显示一般错误
            QMessageBox.warning(self.main_window, "错误", f"无法打开文件: {file_path}")
    
    def _handle_document_load_exception(self, file_path, exception):
        """处理文档加载异常"""
        error_dialog = QMessageBox(self.main_window)
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle("文档加载错误")
        error_dialog.setText(f"加载文档时发生错误: {file_path}")
        error_dialog.setInformativeText("这可能是由于文件格式版本不兼容或文件已损坏。")
        
        # 提供更详细的错误信息
        error_details = f"错误类型: {type(exception).__name__}\n"
        error_details += f"错误信息: {str(exception)}\n"
        
        # 显示栈跟踪信息
        import traceback
        error_details += "\n详细栈跟踪:\n"
        error_details += "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        
        error_dialog.setDetailedText(error_details)
        error_dialog.setStandardButtons(QMessageBox.Ok)
        error_dialog.exec()
