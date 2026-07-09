"""``DocumentExportSerialize`` mixin：文档序列化 / 反序列化。

本 mixin 负责：

- ``create_layer_from_data``: 从 dict 创建 Layer/TextLayer/ShapedLayer/LayerGroup，
  含类型推断与异常恢复。
- ``save_document``: 委托 DocumentSerializer + pickle 写盘（version=5）。
- ``load_document``: pickle 读盘 + 创建图层树 + 重置 history + 绑定组/大小匹配反序列化。

注意：依赖 ``self._build_default_export_settings`` / ``self.set_view_settings`` /
``self._clear_layer_temporary_states`` —— 这些都跨 mixin 存在。
"""
from __future__ import annotations

import logging
import os
import pickle

logger = logging.getLogger(__name__)

from app.models.layer_new import Layer as NewLayer  # noqa: E402
from app.utils.trusted_pickle import load_trusted_pickle


class DocumentExportSerialize:
    """Document 导出相关：序列化子 mixin。"""

    def create_layer_from_data(self, layer_data):
        """从序列化的数据创建图层对象

        参数:
            layer_data (dict): 序列化的图层数据

        返回:
            Layer或TextLayer或ShapedLayer: 创建的图层对象
        """
        if not isinstance(layer_data, dict):
            # 兜底为默认图层，避免把None/非法数据注入图层列表
            return NewLayer(name='错误图层', x=0, y=0, width=100, height=100)

        try:
            # 检查图层类型 - 支持 type 和 layer_type 两种字段名
            layer_type = layer_data.get('layer_type') or layer_data.get('type', 'image')

            # 🔧 增强：通过检查关键字段来验证图层类型
            if 'shape_type' in layer_data and layer_type not in ('image', 'Layer'):
                # 如果有 shape_type 字段，应该是异形图层
                if layer_type != 'shaped':
                    print(f"[警告] 图层数据包含shape_type但layer_type为{layer_type}，强制使用异形图层")
                    layer_type = 'shaped'

            if layer_type == 'group':
                from app.models.layer_group import LayerGroup
                return LayerGroup.deserialize(layer_data, parent=self)
            elif layer_type == 'text':
                # 文字图层
                from app.models.text_layer import TextLayer
                layer = TextLayer.deserialize(layer_data)
            elif layer_type == 'shaped':
                # 异形图层
                from app.models.shaped_layer_new import ShapedLayer
                layer = ShapedLayer.deserialize(layer_data)
            else:
                # 普通图层
                layer = NewLayer.deserialize(layer_data)
            parent_group_id = layer_data.get('parent_group_id') or layer_data.get('_parent_group_id')
            if parent_group_id:
                try:
                    setattr(layer, 'parent_group_id', str(parent_group_id))
                    setattr(layer, '_parent_group_id', str(parent_group_id))
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in document_export_serialize.py")
                    pass
            return layer

        except Exception as e:
            print(f"从数据创建图层失败: {e}")
            import traceback
            traceback.print_exc()

            # 🔧 增强异常处理：尝试根据数据特征恢复图层类型
            try:
                if 'shape_type' in layer_data:
                    # 尝试作为异形图层创建
                    print("[恢复] 尝试作为异形图层恢复...")
                    from app.models.shaped_layer_new import ShapedLayer
                    layer = ShapedLayer(
                        name=layer_data.get('name', '恢复的异形图层'),
                        x=layer_data.get('x', 0),
                        y=layer_data.get('y', 0),
                        width=layer_data.get('width', 100),
                        height=layer_data.get('height', 100),
                        image_source=layer_data.get('image_source'),
                        use_original_size=layer_data.get('use_original_size', False),
                        is_folder=layer_data.get('is_folder', True)
                        # 🔧 关键修复：不传入current_image_path，这是临时状态
                    )
                    # 尝试设置异形属性
                    for key in ['shape_type', 'trapezoid_top_width', 'trapezoid_bottom_width',
                               'trapezoid_slope_side', 'polygon_rotation', 'polygon_corner_radius']:
                        if key in layer_data:
                            try:
                                setattr(layer, key, layer_data[key])
                            except Exception as attr_e:
                                print(f"[恢复] 设置属性 {key} 失败: {attr_e}")
                    return layer
                else:
                    # 回退到普通图层
                    raise Exception("不是异形图层数据")
            except Exception as recovery_e:
                # 最终回退方案
                print(f"[恢复] 异形图层恢复失败: {recovery_e}")
                print("[恢复] 最终回退到普通图层")
                default_layer = NewLayer(
                    name=layer_data.get('name', '错误图层'),
                    x=layer_data.get('x', 0),
                    y=layer_data.get('y', 0),
                    width=layer_data.get('width', 100),
                    height=layer_data.get('height', 100)
                )
                return default_layer

    def save_document(self, file_path):
        """保存文档到指定路径"""
        try:
            from app.models.document_serializer import DocumentSerializer

            document_data = DocumentSerializer.prepare_document_data(self)
            document_data['version'] = 5  # 统一图层参数序列化，补齐随机/文字扩展字段

            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

            # 保存数据
            with open(file_path, 'wb') as f:
                pickle.dump(document_data, f)

            self.current_file_path = file_path

            # 标记文档为未修改状态
            self.is_modified = False

            # 发送文档变更信号，通知界面更新
            self.document_changed.emit()

            return True
        except Exception as e:
            # 使用日志记录错误，同时保持原有的print输出以确保兼容性
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(f"保存文档失败: {e}", exc_info=True)
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in document_export_serialize.py")
                pass
            print(f"保存文档失败: {e}")
            return False

    def load_document(self, file_path):
        """从指定路径加载文档"""
        try:
            # 尝试导入错误处理函数
            try:
                from main import set_document_load_error
                has_error_handler = True
            except ImportError:
                has_error_handler = False

            with open(file_path, 'rb') as f:
                document_data = load_trusted_pickle(f, file_path)

            # 检查文档版本
            doc_version = document_data.get('version', 1)  # 默认为版本1（无版本号的旧文件）
            print(f"加载文档, 版本: {doc_version}")

            self.canvas_width = document_data.get('canvas_width', 0)
            self.canvas_height = document_data.get('canvas_height', 0)

            # 加载图层
            self.layers = []
            layers_data = document_data.get('layers', [])
            try:
                from app.utils.layer_tree import deserialize_layer_tree
                self.layers.extend(
                    deserialize_layer_tree(
                        layers_data,
                        lambda data, parent=None: self.create_layer_from_data(data),
                        parent=self,
                    )
                )
            except Exception:
                for layer_data in layers_data:
                    layer = self.create_layer_from_data(layer_data)
                    if layer is not None:
                        self.layers.append(layer)

            self.selected_layer_index = document_data.get('selected_layer_index', -1)
            self.selected_layer_indices = [self.selected_layer_index] if self.selected_layer_index >= 0 else []

            # 如果选择的图层索引超出范围，重置为-1
            if self.selected_layer_index >= len(self.layers):
                self.selected_layer_index = -1
                self.selected_layer_indices = []

            # 加载导出设置
            if 'export_settings' in document_data:
                loaded_settings = document_data.get('export_settings', {})
                merged_settings = self._build_default_export_settings()
                if isinstance(loaded_settings, dict):
                    merged_settings.update(loaded_settings)
                self.export_settings = merged_settings

            # 加载视图设置（标尺/参考线/吸附/缩放位移）
            self.set_view_settings(document_data.get('view_settings', {}))

            self.current_file_path = file_path

            # 标记文档为未修改状态
            self.is_modified = False

            # 重置历史记录
            self.history = []
            self.history_index = -1

            # 确保绑定管理器正确初始化（兼容性处理）
            if not hasattr(self, 'binding_manager'):
                from app.models.binding_manager import LayerBindingManager
                self.binding_manager = LayerBindingManager()

            # 加载绑定组数据（如果存在）
            if 'binding_groups' in document_data:
                try:
                    self.binding_manager.deserialize(document_data['binding_groups'], self.layers)
                except Exception as e:
                    print(f"加载绑定组数据失败: {e}")
                    # 如果加载失败，使用空的绑定管理器
                    from app.models.binding_manager import LayerBindingManager
                    self.binding_manager = LayerBindingManager()

            # 加载图层大小匹配配置
            if not hasattr(self, 'layer_size_match_manager') or self.layer_size_match_manager is None:
                from app.models.layer_size_match_manager import LayerSizeMatchManager
                self.layer_size_match_manager = LayerSizeMatchManager(parent=self)
            try:
                self.layer_size_match_manager.deserialize(document_data.get('layer_size_matches', {}))
            except Exception as e:
                print(f"加载图层大小匹配配置失败: {e}")
                from app.models.layer_size_match_manager import LayerSizeMatchManager
                self.layer_size_match_manager = LayerSizeMatchManager(parent=self)

            # 🔧 关键修复：加载文档后，清除所有图层的临时图像路径
            # 这确保从旧版本文件加载时，不会保留过时的图像路径
            self._clear_layer_temporary_states()

            # 发出信号通知界面更新
            self.document_changed.emit()
            self.layer_changed.emit()

            return True
        except Exception as e:
            error_msg = f"加载文档失败: {e}"
            # 使用日志记录错误，同时保持原有的print输出
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(error_msg, exc_info=True)
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in document_export_serialize.py")
                pass
            print(error_msg)

            # 如果存在错误处理函数，设置错误信息
            if has_error_handler:
                set_document_load_error(e)

            return False
