"""
文档渲染模块

负责文档的渲染和预览功能
"""

from typing import Optional, List, Tuple
from PIL import Image
from PySide6.QtCore import QObject, Signal
import numpy as np


class DocumentRenderer(QObject):
    """
    文档渲染器
    
    负责将文档和图层渲染成最终图像，分离渲染逻辑。
    """
    
    # 信号
    render_started = Signal()  # 渲染开始
    render_progress = Signal(int)  # 渲染进度（百分比）
    render_finished = Signal(bool)  # 渲染完成（success）
    
    def __init__(self, parent: QObject = None):
        """
        初始化渲染器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        self._use_fast_renderer = True  # 是否使用快速渲染器
    
    def render_document(self, 
                       canvas_width: int, 
                       canvas_height: int,
                       layers: List['Layer'],
                       background_color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                       force_opaque: bool = False) -> Optional[Image.Image]:
        """
        渲染整个文档
        
        Args:
            canvas_width: 画布宽度
            canvas_height: 画布高度
            layers: 图层列表（从底到顶）
            background_color: 背景颜色（RGBA）
            force_opaque: 是否强制不透明背景
            
        Returns:
            渲染后的PIL图像，失败返回None
        """
        self.render_started.emit()
        
        try:
            # 创建基础画布
            if force_opaque:
                # 强制不透明背景（用于JPEG等格式）
                canvas = Image.new('RGB', (canvas_width, canvas_height), background_color[:3])
            else:
                # 透明背景（用于PNG等格式）
                canvas = Image.new('RGBA', (canvas_width, canvas_height), background_color)
            
            # 渲染每个可见图层
            try:
                from app.utils.layer_tree import is_layer_group, is_effectively_visible
                visible_layers = [
                    layer for layer in layers
                    if not is_layer_group(layer) and is_effectively_visible(layer, layers)
                ]
            except Exception:
                visible_layers = [layer for layer in layers if getattr(layer, 'visible', True)]
            total_layers = len(visible_layers)
            
            for idx, layer in enumerate(visible_layers):
                # 更新进度
                progress = int((idx + 1) / total_layers * 100)
                self.render_progress.emit(progress)
                
                # 渲染图层
                layer_image = self.render_layer(layer)
                if layer_image:
                    # 合成到画布
                    canvas = self._composite_layer(canvas, layer_image, layer)
            
            self.render_finished.emit(True)
            return canvas
            
        except Exception as e:
            print(f"[DocumentRenderer] 渲染失败: {e}")
            import traceback
            traceback.print_exc()
            self.render_finished.emit(False)
            return None
    
    def render_layer(self, layer: 'Layer') -> Optional[Image.Image]:
        """
        渲染单个图层
        
        Args:
            layer: 图层对象
            
        Returns:
            渲染后的图层图像，失败返回None
        """
        try:
            # 获取图层图像（包含所有效果）
            if hasattr(layer, 'get_rendered_image'):
                return layer.get_rendered_image()
            elif hasattr(layer, 'get_image'):
                image = layer.get_image()
                if image is None:
                    return None
                try:
                    # 统一应用形状遮罩和特效
                    if image.mode != 'RGBA':
                        image = image.convert('RGBA')
                    if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
                        image = layer.apply_effects(image)
                    return image
                except Exception:
                    return image
            else:
                print(f"[DocumentRenderer] 图层 {layer.name} 没有渲染方法")
                return None
                
        except Exception as e:
            print(f"[DocumentRenderer] 渲染图层 {layer.name} 失败: {e}")
            return None
    
    def _composite_layer(self, 
                        canvas: Image.Image, 
                        layer_image: Image.Image, 
                        layer: 'Layer') -> Image.Image:
        """
        将图层合成到画布上
        
        Args:
            canvas: 画布图像
            layer_image: 图层图像
            layer: 图层对象（用于获取位置、不透明度等）
            
        Returns:
            合成后的画布
        """
        try:
            # 确保图层图像有alpha通道
            if layer_image.mode != 'RGBA':
                layer_image = layer_image.convert('RGBA')
            
            # 应用图层不透明度
            if hasattr(layer, 'opacity') and layer.opacity < 1.0:
                # 调整alpha通道
                alpha = layer_image.split()[3]
                alpha = alpha.point(lambda p: int(p * layer.opacity))
                layer_image.putalpha(alpha)
            
            # 获取图层位置
            x = int(getattr(layer, 'x', 0))
            y = int(getattr(layer, 'y', 0))
            x += int(getattr(layer, '_render_offset_x', 0))
            y += int(getattr(layer, '_render_offset_y', 0))
            
            # 应用混合模式
            blend_mode = getattr(layer, 'blend_mode', 0)
            if blend_mode == 0:  # 正常模式
                try:
                    from app.utils.unified_alpha_compositor import unified_alpha_compositor
                    canvas = unified_alpha_compositor.composite_layer(
                        background=canvas,
                        foreground=layer_image,
                        position=(x, y),
                        opacity=getattr(layer, 'opacity', 1.0),
                        blend_mode='normal',
                        use_srgb_blending=True  # 使用sRGB混合以保证颜色还原
                    )
                except Exception:
                    # 回退到PIL合成
                    if canvas.mode != 'RGBA':
                        canvas = canvas.convert('RGBA')
                    canvas.paste(layer_image, (x, y), layer_image)
            else:
                # 其他混合模式，使用专业混合器
                canvas = self._apply_blend_mode(canvas, layer_image, x, y, blend_mode)
            
            return canvas
            
        except Exception as e:
            print(f"[DocumentRenderer] 合成图层失败: {e}")
            return canvas
    
    def _apply_blend_mode(self,
                         canvas: Image.Image,
                         layer_image: Image.Image,
                         x: int,
                         y: int,
                         blend_mode: int) -> Image.Image:
        """
        应用混合模式
        
        Args:
            canvas: 画布图像
            layer_image: 图层图像
            x: X坐标
            y: Y坐标
            blend_mode: 混合模式
            
        Returns:
            混合后的画布
        """
        try:
            # 尝试使用专业混合引擎
            from app.models.document_blend import Blender, BlendMode
            
            # 提取需要混合的区域
            width = layer_image.width
            height = layer_image.height
            
            # 确保不超出画布范围
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(canvas.width, x + width)
            y2 = min(canvas.height, y + height)
            
            if x2 <= x1 or y2 <= y1:
                return canvas  # 完全在画布外
            
            # 提取画布的对应区域
            canvas_region = canvas.crop((x1, y1, x2, y2))
            
            # 调整图层图像的区域
            layer_x_offset = x1 - x
            layer_y_offset = y1 - y
            layer_region = layer_image.crop((
                layer_x_offset,
                layer_y_offset,
                layer_x_offset + (x2 - x1),
                layer_y_offset + (y2 - y1)
            ))
            
            # 应用混合模式
            try:
                blended = Blender.apply_blend_mode(
                    canvas_region,
                    layer_region,
                    blend_mode
                )
            except Exception:
                # 如果专业混合失败，降级到普通合成
                blended = canvas_region
                if blended.mode == 'RGBA':
                    blended.paste(layer_region, (0, 0), layer_region)
                else:
                    blended = blended.convert('RGBA')
                    blended.paste(layer_region, (0, 0), layer_region)
            
            # 将混合结果粘贴回画布
            canvas.paste(blended, (x1, y1))
            
            return canvas
            
        except Exception as e:
            print(f"[DocumentRenderer] 应用混合模式失败: {e}")
            # 降级到普通合成
            if canvas.mode == 'RGBA':
                canvas.paste(layer_image, (x, y), layer_image)
            else:
                canvas = canvas.convert('RGBA')
                canvas.paste(layer_image, (x, y), layer_image)
            return canvas
    
    def render_preview(self,
                      canvas_width: int,
                      canvas_height: int,
                      layers: List['Layer'],
                      max_size: Tuple[int, int] = (800, 600)) -> Optional[Image.Image]:
        """
        渲染预览图（可能缩小尺寸以提高性能）
        
        Args:
            canvas_width: 画布宽度
            canvas_height: 画布高度
            layers: 图层列表
            max_size: 最大预览尺寸
            
        Returns:
            预览图像，失败返回None
        """
        try:
            # 渲染完整文档
            full_image = self.render_document(canvas_width, canvas_height, layers)
            
            if not full_image:
                return None
            
            # 如果图像太大，缩小以提高性能
            if canvas_width > max_size[0] or canvas_height > max_size[1]:
                # 计算缩放比例
                scale_x = max_size[0] / canvas_width
                scale_y = max_size[1] / canvas_height
                scale = min(scale_x, scale_y)
                
                new_width = int(canvas_width * scale)
                new_height = int(canvas_height * scale)
                
                from PIL.Image import Resampling
                full_image = full_image.resize((new_width, new_height), Resampling.LANCZOS)
            
            return full_image
            
        except Exception as e:
            print(f"[DocumentRenderer] 渲染预览失败: {e}")
            return None
    
    def set_use_fast_renderer(self, use_fast: bool):
        """
        设置是否使用快速渲染器
        
        Args:
            use_fast: 是否使用快速渲染
        """
        self._use_fast_renderer = use_fast


if __name__ == "__main__":
    # 测试代码
    renderer = DocumentRenderer()
    print("DocumentRenderer 创建成功")
