#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layer 子 mixin 6: 序列化/反序列化/duplicate

从原 layer_new.py 拆分。涵盖：
- serialize: 序列化为字典（含随机变换参数）
- to_dict: serialize 的别名（历史记录用）
- from_dict: 根据 layer_type 选择具体子类（TextLayer/ShapedLayer）的 deserialize
- duplicate: serialize + deserialize
- deserialize: 反序列化为新实例

⚠️ 当前 Layer 类实际上没有自己的 duplicate 实现（除了这个 from_dict 路由）。
   Layer 实例的复制通过 serialize + deserialize 完成。
"""

import logging

logger = logging.getLogger(__name__)


class LayerSerializeMixin:
    """序列化/反序列化/duplicate（拆分自 Layer）。"""

    def serialize(self):
        """将图层序列化为字典"""
        # 获取属性管理器序列化的数据
        data = self._property_manager.serialize_properties()

        # 添加图层特有属性
        data.update({
            'layer_id': self._layer_id,
            'layer_type': 'Layer',
            'random_position_enabled': self._random_position_enabled,
            'random_position_range': self._random_position_range,
            'random_scale_enabled': self._random_scale_enabled,
            'random_scale_min': self._random_scale_min,
            'random_scale_max': self._random_scale_max,
            'random_rotation_enabled': self._random_rotation_enabled,
            'random_rotation_range': self._random_rotation_range,
        })

        return data

    # 兼容别名：历史记录(document.save_state/_restore_state)使用 to_dict/from_dict
    def to_dict(self):
        """序列化图层的别名，供文档历史记录使用"""
        return self.serialize()

    @classmethod
    def from_dict(cls, data, parent=None):
        """反序列化图层的别名，供文档历史记录使用。
        根据图层类型标记选择具体子类，保证 TextLayer/ShapedLayer 撤销后类型不退化。"""
        layer_type = data.get('layer_type') or data.get('type')
        target_cls = cls
        if layer_type == 'TextLayer' or layer_type == 'text':
            from app.models.text_layer import TextLayer
            target_cls = TextLayer
        elif layer_type == 'ShapedLayer':
            from app.models.shaped_layer_new import ShapedLayer
            target_cls = ShapedLayer
        elif layer_type == 'group':
            from app.models.layer_group import LayerGroup
            return LayerGroup.deserialize(data, parent=parent)
        if not hasattr(target_cls, 'deserialize'):
            target_cls = cls
        return target_cls.deserialize(data, parent=parent)

    def duplicate(self, parent=None):
        """复制图层，创建一个完全相同的新实例"""
        # 序列化当前图层
        data = self.serialize()

        # 反序列化创建新实例
        return self.deserialize(data, parent=parent if parent is not None else self.parent())

    @classmethod
    def deserialize(cls, data, parent=None):
        """从字典反序列化图层"""
        # 创建新实例
        layer = cls(parent=parent)

        # 反序列化属性
        if 'layer_id' in data:
            layer._layer_id = data['layer_id']

        # 使用属性管理器反序列化
        properties_data = {k: v for k, v in data.items() if k not in ['layer_id', 'layer_type']}
        layer._property_manager.deserialize_properties(properties_data)

        # 恢复属性管理器之外的图层参数
        layer.random_position_enabled = data.get('random_position_enabled', False)
        layer.random_position_range = data.get('random_position_range', 10)
        layer.random_scale_enabled = data.get('random_scale_enabled', False)
        layer.random_scale_min = data.get('random_scale_min', 0.9)
        layer.random_scale_max = data.get('random_scale_max', 1.1)
        layer.random_rotation_enabled = data.get('random_rotation_enabled', False)
        layer.random_rotation_range = data.get('random_rotation_range', 5.0)

        return layer
