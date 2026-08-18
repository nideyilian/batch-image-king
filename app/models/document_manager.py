from PySide6.QtCore import QObject, Signal
from app.models.document import Document
import os

class DocumentManager(QObject):
    """文档管理器，用于管理多个Document实例，实现多标签页功能"""
    
    # 信号定义
    active_document_changed = Signal(Document)  # 当前活动文档变更信号
    document_list_changed = Signal()  # 文档列表变更信号（添加或删除文档时）
    document_name_changed = Signal(int)  # 文档名称变更信号, 参数为文档索引
    
    def __init__(self):
        super().__init__()
        self.documents = []  # 所有打开的文档列表
        self.active_document_index = -1  # 当前活动文档索引
        
    def add_document(self, document):
        """添加一个文档到管理器中"""
        self.documents.append(document)
        
        # 将新文档设置为当前活动文档
        self.active_document_index = len(self.documents) - 1
        
        # 连接文档信号
        document.document_changed.connect(self._on_document_changed)
        
        # 发出信号通知界面更新
        self.document_list_changed.emit()
        self.active_document_changed.emit(document)
        
        return self.active_document_index
    
    def remove_document(self, index):
        """从管理器中移除指定索引的文档"""
        if index < 0 or index >= len(self.documents):
            return False
        
        # 移除文档
        document = self.documents.pop(index)
        
        # 断开文档信号连接
        document.document_changed.disconnect(self._on_document_changed)
        
        # 调整当前活动文档索引
        if self.active_document_index == index:
            # 如果移除的是当前活动文档，则需要选择新的活动文档
            if len(self.documents) > 0:
                # 优先选择后一个文档，如果后面没有则选择前一个
                if index < len(self.documents):
                    self.active_document_index = index
                else:
                    self.active_document_index = len(self.documents) - 1
                
                # 发出活动文档变更信号
                self.active_document_changed.emit(self.documents[self.active_document_index])
            else:
                # 没有文档了
                self.active_document_index = -1
                self.active_document_changed.emit(None)
        elif self.active_document_index > index:
            # 如果当前活动文档在移除的文档之后，则需要调整索引
            self.active_document_index -= 1
        
        # 发出文档列表变更信号
        self.document_list_changed.emit()
        
        return True
    
    def set_active_document(self, index):
        """设置当前活动文档"""
        if index < 0 or index >= len(self.documents):
            return False
        
        if self.active_document_index == index:
            return True  # 已经是当前活动文档，无需切换
        
        self.active_document_index = index
        
        # 发出活动文档变更信号
        self.active_document_changed.emit(self.documents[self.active_document_index])
        
        return True
    
    def get_active_document(self):
        """获取当前活动文档"""
        if self.active_document_index < 0 or self.active_document_index >= len(self.documents):
            return None
        
        return self.documents[self.active_document_index]
    
    def get_document(self, index):
        """获取指定索引的文档"""
        if index < 0 or index >= len(self.documents):
            return None
        
        return self.documents[index]
    
    def get_document_count(self):
        """获取文档数量"""
        return len(self.documents)
    
    def get_document_name(self, index):
        """获取文档名称"""
        if index < 0 or index >= len(self.documents):
            return ""
        
        document = self.documents[index]
        if document.current_file_path:
            return os.path.basename(document.current_file_path)

        for attr_name in ("tab_name", "original_tab_name", "name"):
            name = getattr(document, attr_name, None)
            if isinstance(name, str):
                name = name.strip()
                if name:
                    return name

        return f"未命名-{index + 1}"
    
    def is_document_modified(self, index):
        """检查文档是否已修改"""
        if index < 0 or index >= len(self.documents):
            return False
        
        return self.documents[index].is_modified
    
    def _on_document_changed(self):
        """文档内容变更时的处理函数"""
        # 查找发送信号的文档
        sender = self.sender()
        if sender in self.documents:
            index = self.documents.index(sender)
            # 发出文档名称变更信号
            self.document_name_changed.emit(index)
