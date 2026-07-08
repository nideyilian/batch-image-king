"""
统一的图层序列化工具类
消除图层序列化相关的代码重复，提供标准化的序列化和反序列化接口
"""

import copy
from typing import Dict, Any, Optional, Union
from PIL import Image
import logging
logger = logging.getLogger(__name__)


class LayerSerializer:
    """统一的图层序列化工具类"""
    
    # 标准图层属性定义
    BASIC_ATTRIBUTES = {
        'name': (str, '新图层'),
        'x': (int, 0),
        'y': (int, 0),
        'width': (int, 100),
        'height': (int, 100),
        'visible': (bool, True),
        'opacity': (float, 1.0),
        'locked': (bool, False),
    }
    
    IMAGE_ATTRIBUTES = {
        'image_source': (str, None),
        'is_folder': (bool, True),
        'use_original_size': (bool, False),
        'current_image_path': (str, None),
        'fit_mode': (int, 0),
        'crop_direction': (int, 0),
    }
    
    STYLE_ATTRIBUTES = {
        'corner_radius': (int, 0),
        'vector_corner_radius_tl': (int, 0),
        'vector_corner_radius_tr': (int, 0),
        'vector_corner_radius_br': (int, 0),
        'vector_corner_radius_bl': (int, 0),
        'vector_path_enabled': (bool, False),
        'vector_path_points': (list, []),
        'vector_path_mode': (str, 'polygon'),
        'vector_bezier_nodes': (list, []),
        'vector_path_closed': (bool, True),
        'vector_handle_link_mode': (str, 'mirror'),
        'stroke_enabled': (bool, False),
        'stroke_width': (int, 1),
        'stroke_color': (tuple, (0, 0, 0, 255)),
        'stroke_type': (int, 0),
        'stroke_join': (str, 'miter'),
        'stroke_cap': (str, 'butt'),
        'stroke_dash_length': (int, 0),
        'stroke_dash_gap': (int, 0),
        'blend_mode': (int, 0),
    }
    
    CLONE_ATTRIBUTES = {
        'clone_enabled': (bool, False),
        'clone_rows': (int, 1),
        'clone_columns': (int, 1),
        'clone_row_spacing': (int, 0),
        'clone_column_spacing': (int, 0),
        'clone_mirror_mode': (str, 'none'),
        'clone_fill_enabled': (bool, False),
        'clone_fill_mode': (str, 'grid'),
        'clone_fill_spacing': (int, 0),
        'clone_fill_margin': (int, 0),
        'clone_fill_angle': (float, 0.0),
        'clone_custom_size_enabled': (bool, False),
        'clone_custom_width': (int, 0),
        'clone_custom_height': (int, 0),
        'clone_positions': (list, []),
    }
    
    TRANSFORM_ATTRIBUTES = {
        'rotation': (float, 0.0),
        'flip_horizontal': (bool, False),
        'flip_vertical': (bool, False),
        'aspect_ratio_locked': (bool, False),
    }
    
    RANDOM_TRANSFORM_ATTRIBUTES = {
        'random_position_enabled': (bool, False),
        'random_position_range': (int, 10),
        'random_scale_enabled': (bool, False),
        'random_scale_min': (float, 0.9),
        'random_scale_max': (float, 1.1),
        'random_rotation_enabled': (bool, False),
        'random_rotation_range': (float, 5.0),
    }
    
    CURRENT_STATE_ATTRIBUTES = {
        '_current_random_offset_x': (int, 0),
        '_current_random_offset_y': (int, 0),
        '_current_random_scale': (float, 1.0),
        '_current_random_rotation': (float, 0.0),
        'current_random_offset_x': (int, 0),
        'current_random_offset_y': (int, 0),
        'current_random_scale': (float, 1.0),
        'current_random_rotation': (float, 0.0),
    }
    
    BINDING_ATTRIBUTES = {
        'bind_enabled': (bool, False),
        'bind_group': (str, None),
        'bind_strategy': (str, "filename"),
    }
    
    # 异形图层属性
    SHAPED_LAYER_ATTRIBUTES = {
        'shape_type': (str, 'rectangle'),
        'trapezoid_top_width': (int, 100),
        'trapezoid_bottom_width': (float, 80.0),
        'trapezoid_slope_side': (str, 'right'),
        'polygon_rotation': (float, 0.0),
        'polygon_corner_radius': (int, 0),
    }
    
    # 所有属性的汇总
    ALL_ATTRIBUTES = {
        **BASIC_ATTRIBUTES,
        **IMAGE_ATTRIBUTES,
        **STYLE_ATTRIBUTES,
        **CLONE_ATTRIBUTES,
        **TRANSFORM_ATTRIBUTES,
        **RANDOM_TRANSFORM_ATTRIBUTES,
        **CURRENT_STATE_ATTRIBUTES,
        **BINDING_ATTRIBUTES,
        **SHAPED_LAYER_ATTRIBUTES,
    }
    
    @classmethod
    def serialize_layer(cls, layer_obj) -> Dict[str, Any]:
        """
        序列化图层对象为字典
        
        Args:
            layer_obj: 图层对象（支持新Layer和LegacyLayer）
            
        Returns:
            序列化后的字典
        """
        data = {}
        
        # 遍历所有已知属性
        for attr_name, (attr_type, default_value) in cls.ALL_ATTRIBUTES.items():
            try:
                # 尝试获取属性值
                value = cls._get_attribute_value(layer_obj, attr_name, default_value)
                
                # 类型转换和验证
                if value is not None:
                    value = cls._convert_and_validate(value, attr_type, default_value)
                
                data[attr_name] = value
                
            except Exception as e:
                # 如果获取属性失败，使用默认值
                data[attr_name] = default_value
        
        # 处理特殊的混合模式属性
        data['blend_mode'] = cls._serialize_blend_mode(layer_obj)
        
        # 处理扩展属性
        cls._serialize_extended_attributes(layer_obj, data)
        
        return data
    
    @classmethod
    def _get_attribute_value(cls, layer_obj, attr_name: str, default_value):
        """获取图层属性值，支持多种访问方式"""
        # 尝试直接访问私有属性（新Layer类）
        private_attr = f'_{attr_name}' if not attr_name.startswith('_') else attr_name
        
        if hasattr(layer_obj, private_attr):
            return getattr(layer_obj, private_attr)
        
        # 尝试直接访问公共属性（LegacyLayer类）
        if hasattr(layer_obj, attr_name):
            return getattr(layer_obj, attr_name)
        
        # 使用getattr安全访问
        return getattr(layer_obj, attr_name, default_value)
    
    @classmethod
    def _convert_and_validate(cls, value, target_type, default_value):
        """转换和验证属性值"""
        if value is None:
            return default_value
            
        try:
            if target_type == tuple and isinstance(value, (list, tuple)):
                return tuple(value)
            elif target_type == list and isinstance(value, (list, tuple)):
                return list(value)
            elif target_type in (int, float, bool):
                return target_type(value)
            elif target_type == str:
                # 特殊处理字符串类型，检查是否是枚举类型
                if hasattr(value, 'value'):  # 枚举类型
                    return str(value.value)
                else:
                    return str(value)
            else:
                return value
        except (ValueError, TypeError):
            return default_value
    
    @classmethod
    def _serialize_blend_mode(cls, layer_obj):
        """序列化混合模式，处理不同类型的混合模式值"""
        try:
            blend_mode = cls._get_attribute_value(layer_obj, 'blend_mode', 0)
            
            # 如果是字符串类型，直接返回
            if isinstance(blend_mode, str):
                return blend_mode
            
            # 如果是数字类型，也直接返回
            if isinstance(blend_mode, (int, float)):
                return int(blend_mode)
            
            # 如果是枚举类型，尝试获取其值
            if hasattr(blend_mode, 'value'):
                return blend_mode.value
            elif hasattr(blend_mode, 'name'):
                return blend_mode.name
            
            # 默认返回0（正常模式）
            return 0
            
        except Exception:
            return 0
    
    @classmethod
    def _serialize_extended_attributes(cls, layer_obj, data: Dict[str, Any]):
        """序列化扩展属性"""
        # 处理图层类型 - 确保不同类型的图层能被正确识别
        if hasattr(layer_obj, '__class__'):
            class_name = layer_obj.__class__.__name__
            if class_name == 'ShapedLayer':
                data['layer_type'] = 'shaped'
            elif class_name == 'TextLayer':
                data['layer_type'] = 'text'
            else:
                data['layer_type'] = 'image'
        
        # 处理特效属性
        if hasattr(layer_obj, '_effects') or hasattr(layer_obj, 'effects'):
            effects = getattr(layer_obj, '_effects', None) or getattr(layer_obj, 'effects', None)
            if effects is not None:
                data['effects'] = copy.deepcopy(effects) if effects else None
        
        # 处理其他可能的扩展属性
        extended_attrs = ['cached_image_path', 'smart_crop_enabled']
        for attr in extended_attrs:
            if hasattr(layer_obj, attr) or hasattr(layer_obj, f'_{attr}'):
                value = cls._get_attribute_value(layer_obj, attr, None)
                if value is not None:
                    data[attr] = value
    
    @classmethod
    def deserialize_layer(cls, data: Dict[str, Any], layer_class, **kwargs) -> Any:
        """
        反序列化字典为图层对象
        
        Args:
            data: 序列化的图层数据
            layer_class: 图层类（Layer或LegacyLayer）
            **kwargs: 额外的构造参数
            
        Returns:
            反序列化的图层对象
        """
        # 准备构造参数
        constructor_args = {}
        for attr_name in ['name', 'x', 'y', 'width', 'height', 'image_source', 
                         'use_original_size', 'is_folder', 'current_image_path']:
            if attr_name in data:
                constructor_args[attr_name] = data[attr_name]
        
        # 合并额外参数
        constructor_args.update(kwargs)
        
        # 创建图层实例
        layer = layer_class(**constructor_args)
        
        # 设置其他属性
        cls._set_layer_attributes(layer, data)
        
        return layer
    
    @classmethod
    def _set_layer_attributes(cls, layer_obj, data: Dict[str, Any]):
        """设置图层属性"""
        # 设置基本属性
        for attr_name, (attr_type, default_value) in cls.ALL_ATTRIBUTES.items():
            if attr_name in ['name', 'x', 'y', 'width', 'height', 'image_source', 
                           'use_original_size', 'is_folder']:
                continue  # 这些已在构造函数中设置
            
            if attr_name in data:
                value = data[attr_name]
                value = cls._convert_and_validate(value, attr_type, default_value)
                cls._set_attribute_value(layer_obj, attr_name, value)
        
        # 处理混合模式
        cls._deserialize_blend_mode(layer_obj, data)
        
        # 处理扩展属性
        cls._deserialize_extended_attributes(layer_obj, data)
    
    @classmethod
    def _set_attribute_value(cls, layer_obj, attr_name: str, value):
        """设置图层属性值，支持多种设置方式"""
        # 尝试设置私有属性（新Layer类）
        private_attr = f'_{attr_name}' if not attr_name.startswith('_') else attr_name
        
        if hasattr(layer_obj, private_attr):
            setattr(layer_obj, private_attr, value)
            return
        
        # 尝试设置公共属性（LegacyLayer类）
        if hasattr(layer_obj, attr_name):
            setattr(layer_obj, attr_name, value)
            return
        
        # 如果都没有，尝试直接设置
        try:
            setattr(layer_obj, attr_name, value)
        except Exception:
            pass  # 忽略无法设置的属性
    
    @classmethod
    def _deserialize_blend_mode(cls, layer_obj, data: Dict[str, Any]):
        """反序列化混合模式"""
        try:
            blend_mode_value = data.get('blend_mode', 0)
            
            # 尝试导入混合模式枚举
            try:
                from app.models.document_blend import BlendMode
                
                if isinstance(blend_mode_value, str):
                    # 字符串类型，尝试找到对应的枚举值
                    found = False
                    for mode_name in dir(BlendMode):
                        if mode_name.isupper():
                            mode_value = getattr(BlendMode, mode_name)
                            if mode_value == blend_mode_value:
                                cls._set_attribute_value(layer_obj, 'blend_mode', mode_value)
                                found = True
                                break
                    
                    if not found:
                        cls._set_attribute_value(layer_obj, 'blend_mode', BlendMode.NORMAL)
                else:
                    # 数字类型，直接设置
                    cls._set_attribute_value(layer_obj, 'blend_mode', blend_mode_value)
                    
            except ImportError:
                # 如果无法导入混合模式枚举，使用数字值
                cls._set_attribute_value(layer_obj, 'blend_mode', blend_mode_value)
                
        except Exception:
            # 设置失败时使用默认值
            cls._set_attribute_value(layer_obj, 'blend_mode', 0)
    
    @classmethod
    def _deserialize_extended_attributes(cls, layer_obj, data: Dict[str, Any]):
        """反序列化扩展属性"""
        # 处理特效属性
        if 'effects' in data:
            effects_data = data['effects']
            if effects_data is not None:
                cls._set_attribute_value(layer_obj, 'effects', copy.deepcopy(effects_data))
        
        # 处理异形图层属性
        if 'shape_type' in data:
            from app.models.shaped_layer import ShapeType
            shape_type_value = data['shape_type']
            if isinstance(shape_type_value, str):
                try:
                    shape_type = ShapeType(shape_type_value)
                    cls._set_attribute_value(layer_obj, 'shape_type', shape_type)
                except ValueError:
                    cls._set_attribute_value(layer_obj, 'shape_type', ShapeType.RECTANGLE)
        
        # 处理其他扩展属性
        extended_attrs = ['cached_image_path', 'smart_crop_enabled']
        for attr in extended_attrs:
            if attr in data:
                cls._set_attribute_value(layer_obj, attr, data[attr])
    
    @classmethod
    def duplicate_layer(cls, source_layer, target_layer_class=None, name_suffix=" 副本", **kwargs) -> Any:
        """
        复制图层，使用序列化/反序列化确保完整性
        
        Args:
            source_layer: 源图层对象
            target_layer_class: 目标图层类，如果为None则使用源图层的类
            name_suffix: 名称后缀
            
        Returns:
            复制的图层对象
        """
        # 序列化源图层
        data = cls.serialize_layer(source_layer)
        
        # 修改名称
        original_name = data.get('name', '图层')
        data['name'] = f"{original_name}{name_suffix}"
        
        # 确定目标类型
        if target_layer_class is None:
            target_layer_class = source_layer.__class__
        
        # 反序列化为新图层
        new_layer = cls.deserialize_layer(data, target_layer_class, **kwargs)
        
        # 清除缓存相关的属性，让新图层重新加载
        cls._clear_cache_attributes(new_layer)
        
        return new_layer
    
    @classmethod
    def _clear_cache_attributes(cls, layer_obj):
        """清除缓存相关的属性"""
        cache_attrs = ['cached_image', '_cached_image', 'cached_image_path', '_cached_image_path']
        
        for attr in cache_attrs:
            if hasattr(layer_obj, attr):
                try:
                    setattr(layer_obj, attr, None)
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in layer_serializer.py")
                    pass

