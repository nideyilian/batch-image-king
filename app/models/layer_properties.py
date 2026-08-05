from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
from PySide6.QtCore import QObject, Signal
from typing import Any, Dict, Optional, Union
from enum import Enum
import copy
import math
import os


class ShapeType(Enum):
    """形状类型枚举 - 所有图层都可以使用的形状"""
    RECTANGLE = "rectangle"  # 矩形（默认）
    RIGHT_TRAPEZOID = "right_trapezoid"  # 直角梯形
    CIRCLE = "circle"  # 圆形
    PENTAGON = "pentagon"  # 正五边形
    HEXAGON = "hexagon"  # 正六边形


class PropertyChangeNotifier:
    """属性变化通知器 - 统一管理属性变化和信号发射"""
    
    def __init__(self, owner: QObject):
        self._owner = owner
        self._updating = False
        self._change_listeners = []
    
    def add_change_listener(self, listener):
        """添加变化监听器"""
        self._change_listeners.append(listener)
    
    def notify_change(self, property_name: str, old_value: Any, new_value: Any):
        """通知属性变化"""
        if self._updating or old_value == new_value:
            return False
            
        self._updating = True
        try:
            # 通知所有监听器
            for listener in self._change_listeners:
                if hasattr(listener, 'on_property_changed'):
                    listener.on_property_changed(property_name, old_value, new_value)
            
            # 发射信号
            if hasattr(self._owner, 'changed'):
                self._owner.changed.emit()
                
            return True
        finally:
            self._updating = False


class LayerPropertyManager:
    """图层属性管理器 - 统一管理所有图层属性"""
    
    def __init__(self, owner: QObject):
        self._owner = owner
        self._properties = {}
        self._notifier = PropertyChangeNotifier(owner)
        self._cache_markers = set()  # 需要清除缓存的属性
        
        # 初始化基本属性
        self._init_basic_properties()
        self._init_appearance_properties()
        self._init_transform_properties()
        self._init_effects_properties()
        self._init_shape_properties()
        self._init_advanced_properties()
        self._debug_enabled = os.environ.get("BTPW_PROPERTY_DEBUG", "0") == "1"

    def _debug_log(self, message: str):
        if self._debug_enabled:
            print(message)
    
    def _init_basic_properties(self):
        """初始化基本属性"""
        basic_props = {
            'name': ('新图层', str),
            'x': (0, int),
            'y': (0, int),
            'width': (100, int),
            'height': (100, int),
            'visible': (True, bool),
            'locked': (False, bool),
            'opacity': (1.0, float),
        }
        
        for name, (default, prop_type) in basic_props.items():
            self._properties[name] = {
                'value': default,
                'type': prop_type,
                'validator': None,
                'cache_marker': False
            }
    
    def _init_appearance_properties(self):
        """初始化外观属性"""
        appearance_props = {
            'image_source': (None, (str, type(None))),
            'is_folder': (True, bool),
            'use_original_size': (False, bool),
            'fit_mode': (0, int),
            'crop_direction': (0, int),
            'crop_rect': ([0.0, 0.0, 1.0, 1.0], list),
            'current_image_path': (None, (str, type(None))),
        }
        
        for name, (default, prop_type) in appearance_props.items():
            self._properties[name] = {
                'value': default,
                'type': prop_type,
                'validator': None,
                'cache_marker': True  # 这些属性变化需要清除缓存
            }
    
    def _init_transform_properties(self):
        """初始化变换属性"""
        transform_props = {
            'rotation': (0.0, float),
            'flip_horizontal': (False, bool),
            'flip_vertical': (False, bool),
            'aspect_ratio_locked': (False, bool),
        }
        
        for name, (default, prop_type) in transform_props.items():
            self._properties[name] = {
                'value': default,
                'type': prop_type,
                'validator': None,
                'cache_marker': True
            }
    
    def _init_effects_properties(self):
        """初始化效果属性"""
        effects_props = {
            'corner_radius': (0, int),
            'vector_corner_radius_tl': (0, int),
            'vector_corner_radius_tr': (0, int),
            'vector_corner_radius_br': (0, int),
            'vector_corner_radius_bl': (0, int),
            'vector_path_enabled': (False, bool),
            'vector_path_points': ([], list),
            'vector_path_mode': ("polygon", str),
            'vector_bezier_nodes': ([], list),
            'vector_path_closed': (True, bool),
            'vector_handle_link_mode': ("mirror", str),
            'stroke_enabled': (False, bool),
            'stroke_width': (1, int),
            'stroke_color': ((0, 0, 0, 255), tuple),
            'stroke_type': (0, int),
            'stroke_join': ("miter", str),
            'stroke_cap': ("butt", str),
            'stroke_dash_length': (0, int),
            'stroke_dash_gap': (0, int),
            'blend_mode': (0, int),
            # 颜色叠加
            'color_overlay_enabled': (False, bool),
            'color_overlay_color': ((255, 0, 0, 255), tuple),
            'color_overlay_opacity': (1.0, float),
            # 渐变叠加
            'gradient_overlay_enabled': (False, bool),
            'gradient_overlay_colors': ([(0, 0, 0, 255), (255, 255, 255, 255)], list),
            'gradient_overlay_angle': (90.0, float),
            'gradient_overlay_opacity': (1.0, float),
        }
        
        for name, (default, prop_type) in effects_props.items():
            self._properties[name] = {
                'value': default,
                'type': prop_type,
                'validator': None,
                'cache_marker': True
            }
    
    def _init_shape_properties(self):
        """初始化形状属性 - 所有图层都可以使用形状功能"""
        shape_props = {
            'shape_type': (ShapeType.RECTANGLE, ShapeType),  # 形状类型
            'trapezoid_top_width': (100, int),  # 梯形上底宽度
            'trapezoid_bottom_width': (80, int),  # 梯形下底宽度
            'trapezoid_slope_side': ("right", str),  # 梯形斜边方向
            'polygon_rotation': (0.0, float),  # 多边形旋转角度
            'polygon_corner_radius': (0, int),  # 多边形圆角半径
        }
        
        for name, (default, prop_type) in shape_props.items():
            self._properties[name] = {
                'value': default,
                'type': prop_type,
                'validator': None,
                'cache_marker': True  # 形状变化需要清除缓存
            }
    
    def _init_advanced_properties(self):
        """初始化高级属性"""
        advanced_props = {
            'clone_enabled': (False, bool),
            'clone_rows': (1, int),
            'clone_columns': (1, int),
            'clone_row_spacing': (0, int),
            'clone_column_spacing': (0, int),
            'clone_mirror_mode': ("none", str),
            'clone_fill_enabled': (False, bool),
            'clone_fill_mode': ("grid", str),
            'clone_fill_spacing': (0, int),
            'clone_fill_margin': (0, int),  # 新增画布边距属性
            'clone_fill_angle': (0.0, float),
            'clone_custom_size_enabled': (False, bool),  # 自定义分身大小启用
            'clone_custom_width': (0, int),  # 自定义分身宽度
            'clone_custom_height': (0, int),  # 自定义分身高度
            'bind_enabled': (False, bool),
            'bind_group': (None, (str, type(None))),
            'bind_strategy': ("filename", str),
        }
        
        for name, (default, prop_type) in advanced_props.items():
            self._properties[name] = {
                'value': default,
                'type': prop_type,
                'validator': None,
                'cache_marker': False
            }
    
    def get_property(self, name: str) -> Any:
        """获取属性值"""
        self._debug_log(f"[属性管理器调试] 获取属性: {name}")
        if name not in self._properties:
            self._debug_log(f"[属性管理器调试] 属性 '{name}' 不存在")
            raise AttributeError(f"属性 '{name}' 不存在")
        
        result = self._properties[name]['value']
        self._debug_log(f"[属性管理器调试] 属性 '{name}' 的值: {result} (类型: {type(result)})")
        return result
    
    def set_property(self, name: str, value: Any, validate: bool = True) -> bool:
        """设置属性值"""
        self._debug_log(f"[属性管理器调试] 设置属性: {name} = {value} (类型: {type(value)})")
        if name not in self._properties:
            self._debug_log(f"[属性管理器调试] 属性 '{name}' 不存在")
            raise AttributeError(f"属性 '{name}' 不存在")
        
        prop_info = self._properties[name]
        old_value = prop_info['value']
        self._debug_log(f"[属性管理器调试] 旧值: {old_value} (类型: {type(old_value)})")
        
        # 类型检查和转换
        if validate and prop_info['type'] is not None:
            value = self._validate_and_convert_type(name, value, prop_info['type'])
            self._debug_log(f"[属性管理器调试] 类型转换后: {value} (类型: {type(value)})")
        
        # 自定义验证器
        if validate and prop_info['validator'] is not None:
            value = prop_info['validator'](value)
        
        # 值相同则无需更新
        if old_value == value:
            self._debug_log(f"[属性管理器调试] 值相同，无需更新")
            return False
        
        # 更新属性值
        prop_info['value'] = value
        self._debug_log(f"[属性管理器调试] 更新属性值完成")
        
        # 清除缓存（如果需要）
        if prop_info.get('cache_marker', False):
            self._clear_cache()
        
        # 通知变化
        return self._notifier.notify_change(name, old_value, value)
    
    def _validate_and_convert_type(self, name: str, value: Any, expected_type: type) -> Any:
        """验证和转换类型"""
        if expected_type is None:
            return value
            
        # 处理联合类型
        if isinstance(expected_type, tuple):
            for t in expected_type:
                try:
                    return self._validate_and_convert_type(name, value, t)
                except (ValueError, TypeError):
                    continue
            raise TypeError(f"属性 '{name}' 必须是 {expected_type} 之一")
        
        # 特殊处理
        if name == 'opacity' and expected_type == float:
            return max(0.0, min(1.0, float(value)))
        elif name == 'color_overlay_opacity' and expected_type == float:
            return max(0.0, min(1.0, float(value)))
        elif name == 'gradient_overlay_opacity' and expected_type == float:
            return max(0.0, min(1.0, float(value)))
        elif name == 'crop_rect' and expected_type == list:
            if not isinstance(value, (list, tuple)) or len(value) != 4:
                return [0.0, 0.0, 1.0, 1.0]
            try:
                left, top, right, bottom = (float(item) for item in value)
            except (TypeError, ValueError):
                return [0.0, 0.0, 1.0, 1.0]
            left = max(0.0, min(1.0, left))
            top = max(0.0, min(1.0, top))
            right = max(left + 0.001, min(1.0, right))
            bottom = max(top + 0.001, min(1.0, bottom))
            if right > 1.0 or bottom > 1.0:
                return [0.0, 0.0, 1.0, 1.0]
            return [left, top, right, bottom]
        elif name == 'rotation' and expected_type == float:
            return float(value) % 360
        elif name == 'gradient_overlay_angle' and expected_type == float:
            return float(value) % 360
        elif name == 'stroke_width' and expected_type == int:
            return max(1, int(value))
        elif name == 'corner_radius' and expected_type == int:
            return max(0, int(value))
        elif name in {'vector_corner_radius_tl', 'vector_corner_radius_tr', 'vector_corner_radius_br', 'vector_corner_radius_bl'} and expected_type == int:
            return max(0, int(value))
        elif name == 'clone_rows' and expected_type == int:
            return max(1, int(value))
        elif name == 'clone_columns' and expected_type == int:
            return max(1, int(value))
        elif name == 'clone_row_spacing' and expected_type == int:
            return max(0, int(value))
        elif name == 'clone_column_spacing' and expected_type == int:
            return max(0, int(value))
        elif name == 'clone_fill_spacing' and expected_type == int:
            return max(0, int(value))
        elif name == 'clone_fill_margin' and expected_type == int:
            return max(0, int(value))
        elif name == 'clone_custom_width' and expected_type == int:
            return max(0, int(value))
        elif name == 'clone_custom_height' and expected_type == int:
            return max(0, int(value))
        elif name == 'clone_mirror_mode' and expected_type == str:
            allowed_modes = {"none", "horizontal", "vertical", "both"}
            return value if value in allowed_modes else "none"
        elif name == 'clone_fill_mode' and expected_type == str:
            allowed_modes = {"grid", "staggered", "border", "diagonal", "edge_only", "hex"}
            return value if value in allowed_modes else "grid"
        elif name == 'stroke_type' and expected_type == int:
            return max(0, min(2, int(value)))
        elif name == 'stroke_join' and expected_type == str:
            return value if value in {"miter", "round", "bevel"} else "miter"
        elif name == 'stroke_cap' and expected_type == str:
            return value if value in {"butt", "round", "square"} else "butt"
        elif name == 'vector_path_mode' and expected_type == str:
            return value if value in {"polygon", "bezier"} else "polygon"
        elif name == 'vector_handle_link_mode' and expected_type == str:
            return value if value in {"mirror", "collinear", "free"} else "mirror"
        elif name in {'stroke_dash_length', 'stroke_dash_gap'} and expected_type == int:
            return max(0, int(value))
        elif name == 'polygon_rotation' and expected_type == float:
            return float(value) % 360
        elif name == 'clone_fill_angle' and expected_type == float:
            return float(value)
        elif name == 'polygon_corner_radius' and expected_type == int:
            return max(0, int(value))
        elif name == 'trapezoid_top_width' and expected_type == int:
            return max(1, int(value))
        elif name == 'trapezoid_bottom_width' and expected_type == int:
            return max(1, int(value))
        elif name == 'trapezoid_slope_side' and expected_type == str:
            if value in ["left", "right"]:
                return value
            return "right"  # 默认右侧
        
        # 处理枚举类型 - 如果值已经是枚举实例，直接返回
        if hasattr(expected_type, '__bases__') and Enum in expected_type.__bases__:
            if isinstance(value, expected_type):
                return value
            # 如果是字符串，尝试通过值创建枚举
            elif isinstance(value, str):
                try:
                    return expected_type(value)
                except ValueError:
                    # 如果值无效，返回默认值
                    return self._properties[name]['value']
        
        # 默认类型转换
        return expected_type(value)
    
    def _clear_cache(self):
        """清除缓存"""
        if hasattr(self._owner, '_cached_image'):
            self._owner._cached_image = None
        if hasattr(self._owner, '_cache_valid'):
            self._owner._cache_valid = False
        if hasattr(self._owner, '_cached_image_path'):
            self._owner._cached_image_path = None
    
    def add_validator(self, name: str, validator):
        """添加属性验证器"""
        if name in self._properties:
            self._properties[name]['validator'] = validator
    
    def add_custom_property(self, name: str, default_value: Any, prop_type: type = None, 
                          validator=None, cache_marker: bool = False):
        """添加自定义属性"""
        self._properties[name] = {
            'value': default_value,
            'type': prop_type,
            'validator': validator,
            'cache_marker': cache_marker
        }
    
    def remove_property(self, name: str):
        """移除属性"""
        if name in self._properties:
            del self._properties[name]
    
    def has_property(self, name: str) -> bool:
        """检查属性是否存在"""
        return name in self._properties
    
    def get_property_names(self) -> list:
        """获取所有属性名"""
        return list(self._properties.keys())
    
    def serialize_properties(self) -> Dict[str, Any]:
        """序列化所有属性"""
        return {name: info['value'] for name, info in self._properties.items()}
    
    def deserialize_properties(self, data: Dict[str, Any]):
        """反序列化属性"""
        for name, value in data.items():
            if name in self._properties:
                try:
                    self.set_property(name, value, validate=True)
                except Exception as e:
                    print(f"属性 '{name}' 反序列化失败: {e}")


class CommonLayerOperations:
    """通用图层操作 - 提供所有图层共用的操作方法"""
    
    def __init__(self, layer):
        self._layer = layer
        self._property_manager = layer._property_manager if hasattr(layer, '_property_manager') else None
    
    def reset_transformations(self):
        """重置所有变换"""
        if self._property_manager:
            self._property_manager.set_property('rotation', 0.0)
            self._property_manager.set_property('opacity', 1.0)
            self._property_manager.set_property('flip_horizontal', False)
            self._property_manager.set_property('flip_vertical', False)
            
            # 重置随机变换参数
            if hasattr(self._layer, 'random_offset_x'):
                self._property_manager.set_property('random_offset_x', 0.0)
            if hasattr(self._layer, 'random_offset_y'):
                self._property_manager.set_property('random_offset_y', 0.0)
            if hasattr(self._layer, 'random_rotation'):
                self._property_manager.set_property('random_rotation', 0.0)
            if hasattr(self._layer, 'random_scale_enabled'):
                self._property_manager.set_property('random_scale_enabled', False)
        
        # 清除缓存
        if hasattr(self._layer, '_cached_image'):
            self._layer._cached_image = None
    
    def apply_rotation_preset(self, preset: str):
        """应用旋转预设"""
        presets = {
            'rotate_90': 90.0,
            'rotate_180': 180.0,
            'rotate_270': 270.0,
            'rotate_45': 45.0,
            'rotate_-45': -45.0
        }
        
        if preset in presets and self._property_manager:
            self._property_manager.set_property('rotation', presets[preset])
            print(f"应用旋转预设: {preset} ({presets[preset]}度)")
    
    def get_effective_position(self) -> tuple:
        """获取有效位置（考虑随机偏移）"""
        if self._property_manager:
            x = self._property_manager.get_property('x')
            y = self._property_manager.get_property('y')
            
            # 添加随机偏移
            if hasattr(self._layer, '_current_random_offset_x'):
                x += self._layer._current_random_offset_x
            if hasattr(self._layer, '_current_random_offset_y'):
                y += self._layer._current_random_offset_y
                
            return (x, y)
        
        return (0, 0)
    
    def get_clone_positions(self) -> list:
        """获取分身位置列表"""
        if not self._property_manager:
            return [self.get_effective_position()]
        
        clone_enabled = self._property_manager.get_property('clone_enabled')
        clone_rows = self._property_manager.get_property('clone_rows')
        clone_columns = self._property_manager.get_property('clone_columns')
        
        if not clone_enabled or clone_rows <= 0 or clone_columns <= 0:
            return [self.get_effective_position()]
        
        positions = []
        base_x, base_y = self.get_effective_position()
        width = self._property_manager.get_property('width')
        height = self._property_manager.get_property('height')
        row_spacing = self._property_manager.get_property('clone_row_spacing')
        column_spacing = self._property_manager.get_property('clone_column_spacing')
        
        # 获取实际使用的宽高（考虑自定义大小）
        clone_custom_size_enabled = self._property_manager.get_property('clone_custom_size_enabled')
        if clone_custom_size_enabled:
            clone_custom_width = self._property_manager.get_property('clone_custom_width')
            clone_custom_height = self._property_manager.get_property('clone_custom_height')
            if clone_custom_width > 0:
                width = clone_custom_width
            if clone_custom_height > 0:
                height = clone_custom_height
        
        for row in range(clone_rows):
            for col in range(clone_columns):
                pos_x = base_x + col * (width + column_spacing)
                pos_y = base_y + row * (height + row_spacing)
                positions.append((pos_x, pos_y))
        
        return positions
