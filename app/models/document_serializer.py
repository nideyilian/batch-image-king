"""
文档序列化模块

负责文档的保存和加载
"""

import os
import pickle
from typing import Optional, Dict, Any
from PySide6.QtCore import QObject, Signal

from app.utils.trusted_pickle import load_trusted_pickle


class DocumentSerializer(QObject):
    """
    文档序列化器
    
    负责文档的保存和加载，支持多种格式。
    目前主要使用pickle格式，未来可以扩展支持JSON、XML等格式。
    """
    
    # 信号
    serialization_started = Signal()  # 序列化开始
    serialization_finished = Signal(bool)  # 序列化完成(success)
    deserialization_started = Signal()  # 反序列化开始
    deserialization_finished = Signal(bool)  # 反序列化完成(success)
    
    def __init__(self, parent: QObject = None):
        """
        初始化序列化器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
    
    def serialize_document(self, document_data: Dict[str, Any], file_path: str) -> bool:
        """
        序列化文档到文件
        
        Args:
            document_data: 文档数据字典
            file_path: 文件路径
            
        Returns:
            成功返回True，失败返回False
        """
        self.serialization_started.emit()
        
        try:
            # 确保目录存在
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
            
            # 使用pickle保存
            with open(file_path, 'wb') as f:
                pickle.dump(document_data, f)
            
            self.serialization_finished.emit(True)
            return True
            
        except Exception as e:
            print(f"[DocumentSerializer] 序列化失败: {e}")
            import traceback
            traceback.print_exc()
            self.serialization_finished.emit(False)
            return False
    
    def deserialize_document(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        从文件反序列化文档
        
        Args:
            file_path: 文件路径
            
        Returns:
            成功返回文档数据字典，失败返回None
        """
        self.deserialization_started.emit()
        
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                print(f"[DocumentSerializer] 文件不存在: {file_path}")
                self.deserialization_finished.emit(False)
                return None
            
            # 使用pickle加载
            with open(file_path, 'rb') as f:
                document_data = load_trusted_pickle(f, file_path)
            
            self.deserialization_finished.emit(True)
            return document_data
            
        except Exception as e:
            print(f"[DocumentSerializer] 反序列化失败: {e}")
            import traceback
            traceback.print_exc()
            self.deserialization_finished.emit(False)
            return None
    
    @staticmethod
    def serialize_document_data(document: 'Document') -> Dict[str, Any]:
        """
        兼容接口：供批量导出线程快照使用。
        与 prepare_document_data 保持一致，避免执行器回退到共享文档渲染。
        """
        return DocumentSerializer.prepare_document_data(document)

    @staticmethod
    def prepare_document_data(document: 'Document') -> Dict[str, Any]:
        """
        准备文档数据用于序列化
        
        Args:
            document: Document实例
            
        Returns:
            文档数据字典
        """
        from app.models.layer_new import Layer
        
        # 构建文档数据字典
        document_data = {
            'version': 5,
            'canvas_width': document.canvas_width,
            'canvas_height': document.canvas_height,
            'layers': [],
            'selected_layer_index': document.selected_layer_index,
            'export_settings': document.export_settings.copy() if hasattr(document, 'export_settings') else {},
            'view_settings': document.get_view_settings() if hasattr(document, 'get_view_settings') else {},
            'layer_size_matches': document.layer_size_match_manager.serialize() if hasattr(document, 'layer_size_match_manager') and document.layer_size_match_manager else {},
        }
        
        # 序列化每个图层
        try:
            from app.utils.layer_tree import serialize_layer_tree
            document_data['layers'] = serialize_layer_tree(document.layers, DocumentSerializer.serialize_layer)
        except Exception:
            for layer in document.layers:
                layer_data = DocumentSerializer.serialize_layer(layer)
                document_data['layers'].append(layer_data)
        
        # 如果有绑定管理器，也保存（适配新接口，弃用旧方法）
        if hasattr(document, 'binding_manager') and document.binding_manager:
            try:
                if hasattr(document.binding_manager, 'serialize') and callable(document.binding_manager.serialize):
                    document_data['binding_groups'] = document.binding_manager.serialize()
                elif hasattr(document.binding_manager, 'get_all_groups_data') and callable(document.binding_manager.get_all_groups_data):
                    # 兼容旧接口（不推荐）：返回旧格式
                    document_data['binding_groups'] = document.binding_manager.get_all_groups_data()
                else:
                    # 显式弃用：无可用接口
                    print("[DocumentSerializer] 绑定管理器未提供序列化接口，已跳过绑定数据保存")
                    document_data['binding_groups'] = {}
            except Exception as e:
                print(f"[DocumentSerializer] 保存绑定组失败: {e}")
                document_data['binding_groups'] = {}
        
        return document_data
    
    @staticmethod
    def serialize_layer(layer: 'Layer') -> Dict[str, Any]:
        """
        序列化单个图层
        
        Args:
            layer: Layer实例
            
        Returns:
            图层数据字典
        """
        # 检查图层类型
        from app.models.text_layer import TextLayer
        from app.models.shaped_layer_new import ShapedLayer
        from app.utils.layer_tree import is_layer_group
        
        # 优先使用图层自身的序列化能力，避免导出工作文档漏掉新样式字段
        layer_data: Dict[str, Any]
        if hasattr(layer, 'serialize') and callable(getattr(layer, 'serialize', None)):
            try:
                serialized = layer.serialize()
                layer_data = dict(serialized) if isinstance(serialized, dict) else {}
            except Exception:
                layer_data = {}
        else:
            layer_data = {}

        # 兼容兜底：补齐核心字段（序列化结果已有则不覆盖）
        layer_data.setdefault('name', getattr(layer, 'name', '新图层'))
        layer_data.setdefault('x', getattr(layer, 'x', 0))
        layer_data.setdefault('y', getattr(layer, 'y', 0))
        layer_data.setdefault('width', getattr(layer, 'width', 100))
        layer_data.setdefault('height', getattr(layer, 'height', 100))
        layer_data.setdefault('visible', getattr(layer, 'visible', True))
        layer_data.setdefault('opacity', getattr(layer, 'opacity', 1.0))
        layer_data.setdefault('locked', getattr(layer, 'locked', False))
        
        # 根据图层类型添加类型标识
        if is_layer_group(layer) or layer_data.get('type') == 'group':
            layer_data['type'] = 'group'
        elif isinstance(layer, TextLayer):
            layer_data['type'] = 'text'
        elif isinstance(layer, ShapedLayer):
            layer_data['type'] = 'shaped'
        else:
            layer_data['type'] = 'image'  # 默认类型
        
        # 保存随机变换属性
        parent_group_id = getattr(layer, 'parent_group_id', getattr(layer, '_parent_group_id', None))
        if parent_group_id:
            layer_data['parent_group_id'] = str(parent_group_id)

        if hasattr(layer, 'random_position_enabled'):
            layer_data['random_position_enabled'] = layer.random_position_enabled
            layer_data['random_position_range'] = getattr(layer, 'random_position_range', 10)
        
        if hasattr(layer, 'random_scale_enabled'):
            layer_data['random_scale_enabled'] = layer.random_scale_enabled
            layer_data['random_scale_min'] = getattr(layer, 'random_scale_min', 0.9)
            layer_data['random_scale_max'] = getattr(layer, 'random_scale_max', 1.1)
        
        if hasattr(layer, 'random_rotation_enabled'):
            layer_data['random_rotation_enabled'] = layer.random_rotation_enabled
            layer_data['random_rotation_range'] = getattr(layer, 'random_rotation_range', 5.0)
        
        # 保存分身属性
        if hasattr(layer, 'clone_enabled'):
            layer_data['clone_enabled'] = layer.clone_enabled
            layer_data['clone_rows'] = getattr(layer, 'clone_rows', 1)
            layer_data['clone_columns'] = getattr(layer, 'clone_columns', 1)
            layer_data['clone_row_spacing'] = getattr(layer, 'clone_row_spacing', 0)
            layer_data['clone_column_spacing'] = getattr(layer, 'clone_column_spacing', 0)
            layer_data['clone_mirror_mode'] = getattr(layer, 'clone_mirror_mode', 'none')
            layer_data['clone_fill_enabled'] = getattr(layer, 'clone_fill_enabled', False)
            layer_data['clone_fill_mode'] = getattr(layer, 'clone_fill_mode', 'grid')
            layer_data['clone_fill_spacing'] = getattr(layer, 'clone_fill_spacing', 0)
            layer_data['clone_fill_margin'] = getattr(layer, 'clone_fill_margin', 0)  # 新增边距参数
            layer_data['clone_fill_angle'] = getattr(layer, 'clone_fill_angle', 0.0)
            layer_data['clone_custom_size_enabled'] = getattr(layer, 'clone_custom_size_enabled', False)
            layer_data['clone_custom_width'] = getattr(layer, 'clone_custom_width', 0)
            layer_data['clone_custom_height'] = getattr(layer, 'clone_custom_height', 0)
        
        # 与旧格式兼容：确保文档序列化统一包含 type 字段
        
        return layer_data
    
    @staticmethod
    def restore_document_data(document: 'Document', document_data: Dict[str, Any]) -> bool:
        """
        从数据字典恢复文档
        
        Args:
            document: Document实例
            document_data: 文档数据字典
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            from app.models.layer_new import Layer
            
            # 恢复画布尺寸
            document.canvas_width = document_data.get('canvas_width', 800)
            document.canvas_height = document_data.get('canvas_height', 600)
            
            # 清空现有图层
            document.layers.clear()
            
            # 恢复图层
            layers_data = document_data.get('layers', [])
            try:
                from app.utils.layer_tree import deserialize_layer_tree
                document.layers.extend(
                    deserialize_layer_tree(layers_data, DocumentSerializer.deserialize_layer, parent=document)
                )
            except Exception:
                for layer_data in layers_data:
                    layer = DocumentSerializer.deserialize_layer(layer_data, parent=document)
                    document.layers.append(layer)
            
            # 恢复选中图层
            document.selected_layer_index = document_data.get('selected_layer_index', -1)
            
            # 恢复导出设置
            if 'export_settings' in document_data:
                document.export_settings.update(document_data['export_settings'])
            
            # 恢复视图设置
            if 'view_settings' in document_data and hasattr(document, 'set_view_settings'):
                document.set_view_settings(document_data.get('view_settings') or {})
            
            # 恢复绑定组（兼容新旧接口）
            if 'binding_groups' in document_data and hasattr(document, 'binding_manager'):
                try:
                    binding_data = document_data.get('binding_groups') or {}
                    manager = document.binding_manager
                    if hasattr(manager, 'restore_from_data') and callable(manager.restore_from_data):
                        manager.restore_from_data(binding_data)
                    elif hasattr(manager, 'deserialize') and callable(manager.deserialize):
                        manager.deserialize(binding_data, getattr(document, 'layers', []))
                    else:
                        print("[DocumentSerializer] 绑定管理器缺少可用的恢复接口，已跳过绑定组恢复")
                except Exception as e:
                    print(f"[DocumentSerializer] 恢复绑定组失败: {e}")

            # 恢复图层大小匹配配置
            if 'layer_size_matches' in document_data and hasattr(document, 'layer_size_match_manager') and document.layer_size_match_manager:
                try:
                    document.layer_size_match_manager.deserialize(document_data.get('layer_size_matches') or {})
                except Exception as e:
                    print(f"[DocumentSerializer] 恢复图层大小匹配失败: {e}")
            
            return True
            
        except Exception as e:
            print(f"[DocumentSerializer] 恢复文档数据失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def deserialize_layer(layer_data: Dict[str, Any], parent: QObject = None) -> 'Layer':
        """
        反序列化单个图层
        
        Args:
            layer_data: 图层数据字典
            parent: 父对象
            
        Returns:
            Layer实例
        """
        # 根据图层类型创建相应的图层对象
        layer_type = layer_data.get('type', 'image')
        
        if layer_type == 'group':
            from app.models.layer_group import LayerGroup
            return LayerGroup.deserialize(layer_data, parent=parent)
        elif layer_type == 'text':
            # 文字图层
            from app.models.text_layer import TextLayer
            layer = TextLayer.deserialize(layer_data, parent=parent)
            parent_group_id = layer_data.get('parent_group_id') or layer_data.get('_parent_group_id')
            if parent_group_id:
                setattr(layer, 'parent_group_id', str(parent_group_id))
                setattr(layer, '_parent_group_id', str(parent_group_id))
            return layer
        elif layer_type == 'shaped':
            # 异形图层
            from app.models.shaped_layer_new import ShapedLayer
            layer = ShapedLayer.deserialize(layer_data, parent=parent)
            parent_group_id = layer_data.get('parent_group_id') or layer_data.get('_parent_group_id')
            if parent_group_id:
                setattr(layer, 'parent_group_id', str(parent_group_id))
                setattr(layer, '_parent_group_id', str(parent_group_id))
            return layer
        else:
            # 普通图层
            from app.models.layer_new import Layer
            layer = Layer.deserialize(layer_data, parent=parent)
            parent_group_id = layer_data.get('parent_group_id') or layer_data.get('_parent_group_id')
            if parent_group_id:
                setattr(layer, 'parent_group_id', str(parent_group_id))
                setattr(layer, '_parent_group_id', str(parent_group_id))
            return layer


if __name__ == "__main__":
    # 测试代码
    serializer = DocumentSerializer()
    
    # 创建测试数据
    test_data = {
        'canvas_width': 1920,
        'canvas_height': 1080,
        'layers': [],
        'selected_layer_index': 0,
        'export_settings': {},
    }
    
    # 序列化
    success = serializer.serialize_document(test_data, "test_document.pkl")
    print(f"序列化: {success}")
    
    # 反序列化
    loaded_data = serializer.deserialize_document("test_document.pkl")
    print(f"反序列化: {loaded_data}")

from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
