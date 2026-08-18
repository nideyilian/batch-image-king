from PySide6.QtCore import QObject, Signal
from PIL import Image, ImageDraw
import numpy as np
import math
from enum import Enum
from typing import List, Tuple, Optional
from app.models.layer_new import Layer
from app.models.layer_properties import LayerPropertyManager, ShapeType
from app.utils.render_diagnostics import log_branch


class ShapedLayer(Layer):
    """重构后的异形图层类 - 完全使用父类的属性管理和形状功能"""
    
    def __init__(self, name="异形图层", x=0, y=0, width=100, height=100, 
                 image_source=None, use_original_size=False, is_folder=True, 
                 current_image_path=None, parent=None, shape_type=ShapeType.RECTANGLE):
        """
        初始化异形图层 - 完全依赖父类的属性管理
        
        Args:
            name: 图层名称
            x: X坐标
            y: Y坐标
            width: 宽度
            height: 高度
            image_source: 图像源
            use_original_size: 是否使用原始图像尺寸
            is_folder: 图像源是否为文件夹
            current_image_path: 当前使用的图像文件路径
            parent: 父对象
            shape_type: 形状类型
        """
        # 调用父类初始化 - 父类已经包含所有形状属性和蒙版创建逻辑
        super().__init__(name, x, y, width, height, image_source, 
                        use_original_size, is_folder, current_image_path, parent)
        
        # 设置默认形状为异形图层的默认形状
        self._property_manager.set_property('shape_type', shape_type, validate=False)
        
        # 设置梯形默认参数（如果需要）
        if shape_type == ShapeType.RIGHT_TRAPEZOID:
            # 使用当前图层的宽度，而不是默认的100
            self._property_manager.set_property('trapezoid_top_width', self.width, validate=False)
            self._property_manager.set_property('trapezoid_bottom_width', int(self.width * 0.8), validate=False)
            self._property_manager.set_property('trapezoid_slope_side', "right", validate=False)
    
    # 异形图层不再重写形状蒙版创建方法，完全使用父类的优化实现
    
    def get_shape_description(self) -> str:
        """获取形状的描述文本 - 完全使用父类的属性"""
        shape_names = {
            ShapeType.RECTANGLE: "矩形",
            ShapeType.RIGHT_TRAPEZOID: "直角梯形",
            ShapeType.CIRCLE: "圆形",
            ShapeType.PENTAGON: "正五边形",
            ShapeType.HEXAGON: "正六边形"
        }
        
        base_name = shape_names.get(self.shape_type, "未知形状")
        
        if self.shape_type == ShapeType.RIGHT_TRAPEZOID:
            return f"{base_name} ({self.trapezoid_slope_side})"
        elif self.shape_type in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
            if self.polygon_rotation != 0:
                return f"{base_name} (旋转{self.polygon_rotation}°)"
        
        return base_name
    
    def _apply_effects(self, image):
        """异形图层的效果应用 - 完全依赖父类实现"""
        if image is None:
            return None
            
        # 异形图层只需要调用父类的方法，父类已经处理了形状蒙版
        log_branch(
            "shaped_layer_new._apply_effects",
            "delegate_to_layer_new",
            shape_type=getattr(getattr(self, "shape_type", None), "value", getattr(self, "shape_type", "unknown")),
            corner_radius=getattr(self, "corner_radius", 0),
            stroke_enabled=bool(getattr(self, "stroke_enabled", False)),
            stroke_width=getattr(self, "stroke_width", 0),
            stroke_type=getattr(self, "stroke_type", -1),
        )
        return super()._apply_effects(image)
    
    def duplicate(self, parent=None):
        """复制异形图层"""
        # 序列化当前图层
        data = self.serialize()
        
        # 反序列化创建新实例
        return self.deserialize(data, parent=parent if parent is not None else self.parent())
    
    def serialize(self):
        """序列化异形图层"""
        # 获取父类序列化的数据 - 父类已经包含所有形状属性
        data = super().serialize()
        
        # 标记为异形图层
        data['layer_type'] = 'ShapedLayer'
        
        return data
    
    @classmethod
    def deserialize(cls, data, parent=None):
        """反序列化异形图层"""
        # 父类反序列化已经包含所有形状属性
        return super().deserialize(data, parent=parent)