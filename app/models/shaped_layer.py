import logging

logger = logging.getLogger(__name__)
from PySide6.QtCore import QObject, Signal
from PIL import Image, ImageDraw, ImageChops
import numpy as np
import math
from enum import Enum
from typing import List, Tuple, Optional
from app.models.layer import Layer
from app.utils.render_diagnostics import log_branch, log_sampling


class ShapeType(Enum):
    """异形图层形状类型枚举"""
    RECTANGLE = "rectangle"  # 矩形（默认）
    RIGHT_TRAPEZOID = "right_trapezoid"  # 直角梯形
    CIRCLE = "circle"  # 圆形
    PENTAGON = "pentagon"  # 正五边形
    HEXAGON = "hexagon"  # 正六边形


class ShapedLayer(Layer):
    """异形图层类 - 支持各种几何形状的图层容器"""
    
    def __init__(self, name="异形图层", x=0, y=0, width=100, height=100, 
                 image_source=None, use_original_size=False, is_folder=True, 
                 parent=None, shape_type=ShapeType.RECTANGLE, current_image_path=None):
        """
        初始化异形图层
        
        self._shape_mask_cache = None
        self._shape_mask_cache_key = None
        Args:
            name: 图层名称
            x: X坐标
            y: Y坐标
            width: 宽度
            height: 高度
            image_source: 图像源
            use_original_size: 是否使用原始图像尺寸
            is_folder: 图像源是否为文件夹
            parent: 父对象
            shape_type: 形状类型
        """
        super().__init__(name, x, y, width, height, image_source, 
                        use_original_size, is_folder, parent)
        
        # 设置当前图像路径（如果提供）
        if current_image_path:
            self._current_image_path = current_image_path
        
        # 异形图层特有属性
        self._shape_type = shape_type
        self._shape_params = {}  # 形状参数，可用于自定义形状
        
        # 直角梯形特有参数
        self._trapezoid_top_width = width  # 梯形上底宽度
        self._trapezoid_bottom_width = width * 0.8  # 梯形下底宽度（默认80%）
        self._trapezoid_slope_side = "right"  # 斜边方向：left, right
        
        # 多边形参数（五边形、六边形等）
        self._polygon_rotation = 0  # 多边形旋转角度（度）
        self._polygon_corner_radius = 0  # 多边形圆角半径
        
        # 形状遮罩缓存 - 优化内存使用
        self._shape_mask_cache = None
        self._shape_mask_cache_key = None
        
    @property
    def shape_type(self):
        """获取形状类型"""
        return self._shape_type
        
    @shape_type.setter
    def shape_type(self, value):
        """设置形状类型"""
        if self._shape_type != value:
            self._shape_type = value
            self._cached_image = None  # 清除缓存
            self._shape_mask_cache = None
            self._shape_mask_cache_key = None
            self.changed.emit()
            
    @property
    def trapezoid_top_width(self):
        """获取梯形上底宽度"""
        return self._trapezoid_top_width
        
    @trapezoid_top_width.setter
    def trapezoid_top_width(self, value):
        """设置梯形上底宽度"""
        if self._trapezoid_top_width != value and value > 0:
            self._trapezoid_top_width = value
            self._cached_image = None
            self._shape_mask_cache = None
            self._shape_mask_cache_key = None
            self.changed.emit()
            
    @property
    def trapezoid_bottom_width(self):
        """获取梯形下底宽度"""
        return self._trapezoid_bottom_width
        
    @trapezoid_bottom_width.setter
    def trapezoid_bottom_width(self, value):
        """设置梯形下底宽度"""
        if self._trapezoid_bottom_width != value and value > 0:
            self._trapezoid_bottom_width = value
            self._cached_image = None
            self._shape_mask_cache = None
            self._shape_mask_cache_key = None
            self.changed.emit()
            
    @property
    def trapezoid_slope_side(self):
        """获取梯形斜边方向"""
        return self._trapezoid_slope_side
        
    @trapezoid_slope_side.setter
    def trapezoid_slope_side(self, value):
        """设置梯形斜边方向"""
        if value in ["left", "right"] and self._trapezoid_slope_side != value:
            self._trapezoid_slope_side = value
            self._cached_image = None
            self._shape_mask_cache = None
            self._shape_mask_cache_key = None
            self.changed.emit()
            
    @property
    def polygon_rotation(self):
        """获取多边形旋转角度"""
        return self._polygon_rotation
        
    @polygon_rotation.setter
    def polygon_rotation(self, value):
        """设置多边形旋转角度"""
        normalized_value = float(value) % 360
        if abs(self._polygon_rotation - normalized_value) > 0.001:
            self._polygon_rotation = normalized_value
            self._cached_image = None
            self._shape_mask_cache = None
            self._shape_mask_cache_key = None
            self.changed.emit()
            
    @property
    def polygon_corner_radius(self):
        """获取多边形圆角半径"""
        return self._polygon_corner_radius
        
    @polygon_corner_radius.setter
    def polygon_corner_radius(self, value):
        """设置多边形圆角半径"""
        if self._polygon_corner_radius != value and value >= 0:
            self._polygon_corner_radius = value
            self._cached_image = None
            self._shape_mask_cache = None
            self._shape_mask_cache_key = None
            self.changed.emit()
    
    def _create_shape_mask(self, width: int, height: int) -> Image.Image:
        """
        创建形状蒙版 - 优化内存使用
        
        Args:
            width: 蒙版宽度
            height: 蒙版高度
            
        Returns:
            PIL.Image: 形状蒙版（L模式）
        """
        key = (width, height, self._shape_type.value, int(self._trapezoid_top_width), int(self._trapezoid_bottom_width), self._trapezoid_slope_side, int(self._polygon_rotation), int(self._polygon_corner_radius))
        if self._shape_mask_cache is not None and self._shape_mask_cache_key == key:
            # 直接返回缓存的遮罩，避免不必要的copy操作
            return self._shape_mask_cache

        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)
        
        if self._shape_type == ShapeType.RECTANGLE:
            # 矩形：使用超采样圆角，避免边缘锯齿传递到后续描边
            if self._corner_radius > 0:
                radius = min(self._corner_radius, min(width, height) // 2)
                log_branch("shaped_layer._create_shape_mask", "rectangle_rounded", width=width, height=height, radius=radius)
                mask = self._create_antialiased_rounded_rect_mask(width, height, radius)
            else:
                log_branch("shaped_layer._create_shape_mask", "rectangle_plain", width=width, height=height)
                draw.rectangle((0, 0, width-1, height-1), fill=255)
                
        elif self._shape_type == ShapeType.RIGHT_TRAPEZOID:
            # 直角梯形
            log_branch("shaped_layer._create_shape_mask", "right_trapezoid", width=width, height=height)
            self._draw_right_trapezoid(draw, width, height)
            
        elif self._shape_type == ShapeType.CIRCLE:
            # 圆形
            log_branch("shaped_layer._create_shape_mask", "circle", width=width, height=height)
            self._draw_circle(draw, width, height)
            
        elif self._shape_type == ShapeType.PENTAGON:
            # 正五边形
            log_branch("shaped_layer._create_shape_mask", "pentagon", width=width, height=height)
            self._draw_regular_polygon(draw, width, height, 5)
            
        elif self._shape_type == ShapeType.HEXAGON:
            # 正六边形
            log_branch("shaped_layer._create_shape_mask", "hexagon", width=width, height=height)
            self._draw_regular_polygon(draw, width, height, 6)
            
        # 直接缓存创建的遮罩，避免额外的copy操作
        self._shape_mask_cache = mask
        self._shape_mask_cache_key = key
        return mask
    
    def _get_mask_supersample_scale(self, width: int, height: int, edge_size: int = 0) -> int:
        """根据尺寸和边缘复杂度选择超采样倍数。"""
        min_side = max(1, min(int(width), int(height)))
        edge_size = max(0, int(edge_size))

        if min_side <= 256:
            scale = 8
        elif min_side <= 1024:
            scale = 7
        elif min_side <= 2048:
            scale = 6
        else:
            scale = 5

        if edge_size <= 4:
            scale = max(scale, 8 if min_side <= 1024 else 6)
        elif edge_size <= 10:
            scale = max(scale, 7 if min_side <= 1024 else 6)
        log_sampling("shaped_layer.mask_scale", width, height, edge_size, scale)
        return scale
    
    def _create_antialiased_rounded_rect_mask(self, width: int, height: int, radius: int) -> Image.Image:
        """使用超采样+LANCZOS回采样生成平滑圆角蒙版。"""
        width = max(1, int(width))
        height = max(1, int(height))
        radius = max(0, min(int(radius), min(width, height) // 2))
        if radius <= 0:
            return Image.new('L', (width, height), 255)
        
        scale = self._get_mask_supersample_scale(width, height, radius)
        large_w = width * scale
        large_h = height * scale
        large_mask = Image.new('L', (large_w, large_h), 0)
        draw = ImageDraw.Draw(large_mask)
        draw.rounded_rectangle((0, 0, large_w - 1, large_h - 1), radius=radius * scale, fill=255)
        return large_mask.resize((width, height), Image.Resampling.LANCZOS)
    
    def _draw_right_trapezoid(self, draw: ImageDraw.Draw, width: int, height: int):
        """绘制直角梯形"""
        top_width = min(self._trapezoid_top_width, width)
        bottom_width = min(self._trapezoid_bottom_width, width)
        
        # 计算梯形各顶点坐标
        if self._trapezoid_slope_side == "right":
            # 斜边在右侧
            points = [
                (0, 0),  # 左上
                (top_width, 0),  # 右上
                (bottom_width, height),  # 右下
                (0, height)  # 左下
            ]
        else:
            # 斜边在左侧
            points = [
                (width - top_width, 0),  # 左上
                (width, 0),  # 右上
                (width, height),  # 右下
                (width - bottom_width, height)  # 左下
            ]
        
        draw.polygon(points, fill=255)
    
    def _draw_circle(self, draw: ImageDraw.Draw, width: int, height: int):
        """绘制圆形"""
        # 确保圆形在边界内，留一点边距
        margin = 2
        diameter = min(width, height) - margin * 2
        center_x = width // 2
        center_y = height // 2
        radius = diameter // 2
        
        # 绘制圆形
        bbox = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)
        draw.ellipse(bbox, fill=255)
        
        # 如果有多边形圆角设置，应用轻微的内圆角
        if self._polygon_corner_radius > 0:
            self._apply_polygon_corner_radius(draw, width, height, [(center_x, center_y)], radius)
    
    def _draw_regular_polygon(self, draw: ImageDraw.Draw, width: int, height: int, sides: int):
        """绘制正多边形"""
        center_x = width // 2
        center_y = height // 2
        
        # 计算内切圆半径（确保多边形在边界内）
        margin = 5
        max_radius = min(width, height) // 2 - margin
        
        # 生成多边形顶点
        points = []
        for i in range(sides):
            angle = 2 * math.pi * i / sides + math.radians(self._polygon_rotation)
            x = center_x + max_radius * math.cos(angle - math.pi / 2)  # -pi/2让顶点朝上
            y = center_y + max_radius * math.sin(angle - math.pi / 2)
            points.append((int(x), int(y)))
        
        # 绘制多边形
        draw.polygon(points, fill=255)
        
        # 应用多边形圆角
        if self._polygon_corner_radius > 0:
            self._apply_polygon_corner_radius(draw, width, height, points, max_radius)
    
    def _apply_polygon_corner_radius(self, draw: ImageDraw.Draw, width: int, height: int, 
                                   vertices: List[Tuple[int, int]], max_radius: int):
        """应用多边形圆角效果"""
        if self._polygon_corner_radius <= 0 or len(vertices) < 3:
            return
        corner_radius = min(self._polygon_corner_radius, max_radius // 4)
        self._draw_rounded_polygon(draw, vertices, corner_radius)
    
    def _draw_rounded_polygon(self, draw: ImageDraw.Draw, vertices: List[Tuple[int, int]], radius: int):
        """绘制圆角多边形"""
        if len(vertices) < 3:
            return
            
        # 简化的圆角多边形实现
        # 先绘制普通多边形
        draw.polygon(vertices, fill=255)
        
        # 在顶点处绘制小圆角
        for i, (x, y) in enumerate(vertices):
            next_i = (i + 1) % len(vertices)
            prev_i = (i - 1) % len(vertices)
            
            # 计算顶点处的圆角
            prev_vertex = vertices[prev_i]
            next_vertex = vertices[next_i]
            
            # 绘制小圆角
            small_radius = min(radius, 5)  # 限制小圆角大小
            draw.ellipse((x - small_radius, y - small_radius, 
                         x + small_radius, y + small_radius), fill=255)
    
    def _apply_shape_mask(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        """
        应用形状蒙版到图像 - 优化内存使用
        
        Args:
            image: 原始图像
            mask: 形状蒙版
            
        Returns:
            PIL.Image: 应用形状后的图像
        """
        if image is None:
            return None
            
        # 确保图像是RGBA模式
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 如果原图的alpha通道完全不透明，可以直接使用putalpha来优化性能
        # 只有当原图有透明区域时才需要使用ImageChops.darker
        if self._has_transparency(image):
            # 原图有透明区域，使用乘法可保持平滑边缘过渡
            r, g, b, a = image.split()
            new_alpha = ImageChops.multiply(a, mask)
            return Image.merge('RGBA', (r, g, b, new_alpha))
        else:
            # 原图完全不透明，直接使用putalpha应用遮罩，性能更好
            result = image.copy()
            result.putalpha(mask)
            return result
    
    def _has_transparency(self, image: Image.Image) -> bool:
        """检查图像是否有透明区域"""
        if image.mode != 'RGBA':
            return False
        
        # 快速检查alpha通道是否全部为255（完全不透明）
        alpha = image.split()[-1]
        return alpha.getextrema()[0] < 255
    
    def _apply_effects(self, image):
        """重写父类的方法，在应用其他效果前先应用形状蒙版"""
        if image is None:
            return None
            
        # 批处理模式下减少日志输出以提高性能
        if not getattr(self, '_is_batch_mode', False):
            print(f"[异形图层] 开始应用形状效果: {self._shape_type.value}")
        
        # 第一步：应用形状蒙版
        shape_mask = self._create_shape_mask(image.width, image.height)
        shaped_image = self._apply_shape_mask(image, shape_mask)
        
        # 第二步：调用父类的方法应用其他效果（圆角、描边、变换等）
        result = super()._apply_effects(shaped_image)
        
        if not getattr(self, '_is_batch_mode', False):
            print(f"[异形图层] 形状效果应用完成: {self._shape_type.value}")
        return result
    
    def get_shape_description(self) -> str:
        """获取形状的描述文本"""
        shape_names = {
            ShapeType.RECTANGLE: "矩形",
            ShapeType.RIGHT_TRAPEZOID: "直角梯形",
            ShapeType.CIRCLE: "圆形",
            ShapeType.PENTAGON: "正五边形",
            ShapeType.HEXAGON: "正六边形"
        }
        
        base_name = shape_names.get(self._shape_type, "未知形状")
        
        if self._shape_type == ShapeType.RIGHT_TRAPEZOID:
            return f"{base_name} ({self._trapezoid_slope_side})"
        elif self._shape_type in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
            if self._polygon_rotation != 0:
                return f"{base_name} (旋转{self._polygon_rotation}°)"
        
        return base_name
    
    def duplicate(self, parent=None):
        """复制异形图层"""
        # 使用序列化工具进行复制
        from app.utils.layer_serializer import LayerSerializer
        
        kwargs = {}
        if parent is not None:
            kwargs['parent'] = parent
        else:
            kwargs['parent'] = self.parent()
            
        return LayerSerializer.duplicate_layer(self, target_layer_class=ShapedLayer, **kwargs)
    
    def serialize(self):
        """序列化异形图层"""
        # 使用统一的序列化工具 - LayerSerializer 已经通过 SHAPED_LAYER_ATTRIBUTES 处理异形属性
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.serialize_layer(self)
    
    @classmethod
    def deserialize(cls, data, parent=None):
        """反序列化异形图层"""
        # 使用统一的序列化工具
        from app.utils.layer_serializer import LayerSerializer
        
        # 创建基础图层
        layer = LayerSerializer.deserialize_layer(data, cls, parent=parent)
        
        # 设置异形图层特有属性
        if 'shape_type' in data:
            layer._shape_type = ShapeType(data['shape_type'])
        if 'trapezoid_top_width' in data:
            layer._trapezoid_top_width = data['trapezoid_top_width']
        if 'trapezoid_bottom_width' in data:
            layer._trapezoid_bottom_width = data['trapezoid_bottom_width']
        if 'trapezoid_slope_side' in data:
            layer._trapezoid_slope_side = data['trapezoid_slope_side']
        if 'polygon_rotation' in data:
            layer._polygon_rotation = data['polygon_rotation']
        if 'polygon_corner_radius' in data:
            layer._polygon_corner_radius = data['polygon_corner_radius']
            
        return layer
    
    def clear_cache(self):
        """清除形状遮罩缓存，释放内存"""
        self._shape_mask_cache = None
        self._shape_mask_cache_key = None
    
    def __del__(self):
        """析构函数，确保释放缓存资源"""
        try:
            self.clear_cache()
        except Exception:
            logger.debug("静默异常已忽略: except in models/shaped_layer.py")
            pass