"""
高级合成管理器
统一管理所有Photoshop级图像合成功能，包括：
1. 高精度半透明处理
2. 专业级混合模式
3. 智能画质保持
4. 性能优化
5. 向后兼容性
"""

import numpy as np
from PIL import Image
from typing import Tuple, Optional, Dict, Any, List, Union
from enum import Enum
import time
import gc

# 导入我们的高级引擎
try:
    from .photoshop_compositor import PhotoshopCompositor, BlendMode as PSBlendMode
    from .alpha_compositor import AlphaCompositor, CompositeOperation
    from .quality_engine import QualityEngine, ScalingMethod, ContentType
    from .professional_blends import ProfessionalBlender, BlendMode as ProBlendMode
    ADVANCED_ENGINES_AVAILABLE = True
except ImportError as e:
    safe_print(f"[WARNING] 高级合成引擎导入失败: {e}")
    ADVANCED_ENGINES_AVAILABLE = False
    # 定义后备类型
    PSBlendMode = str
    ProBlendMode = str

# 导入现有的混合模式作为后备
try:
    from app.models.document_blend import Blender as LegacyBlender, BlendMode as LegacyBlendMode
    from app.ui.blend_mode_manager import BlendModeManager
    LEGACY_BLENDER_AVAILABLE = True
except ImportError:
    LEGACY_BLENDER_AVAILABLE = False


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")


class CompositeQuality(Enum):
    """合成质量级别"""
    FAST = "fast"           # 快速模式，优先性能
    BALANCED = "balanced"   # 平衡模式，质量和性能兼顾
    HIGH = "high"          # 高质量模式，优先质量
    PHOTOSHOP = "photoshop" # Photoshop级质量，最高质量


class AdvancedCompositorManager:
    """高级合成管理器"""
    
    def __init__(self, quality: CompositeQuality = CompositeQuality.BALANCED,
                 enable_gpu: bool = False, cache_size: int = 100):
        """
        初始化高级合成管理器
        
        Args:
            quality: 合成质量级别
            enable_gpu: 是否启用GPU加速
            cache_size: 缓存大小（MB）
        """
        self.quality = quality
        self.enable_gpu = enable_gpu
        self.cache_size = cache_size
        
        # 初始化引擎
        self._init_engines()
        
        # 性能统计
        self.stats = {
            'total_operations': 0,
            'total_time': 0.0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # 简单缓存
        self._cache = {}
        self._cache_order = []
    
    def _init_engines(self):
        """初始化各种合成引擎"""
        self.engines_available = ADVANCED_ENGINES_AVAILABLE
        
        if ADVANCED_ENGINES_AVAILABLE:
            try:
                # 根据质量级别选择参数
                if self.quality == CompositeQuality.PHOTOSHOP:
                    use_16bit = True
                    color_space = 'srgb'  # Photoshop默认使用sRGB混合（除非是32位）
                elif self.quality == CompositeQuality.HIGH:
                    use_16bit = False
                    color_space = 'srgb'  # 保持一致性，避免半透明像素丢失
                else:
                    use_16bit = False
                    color_space = 'srgb'
                
                # 初始化引擎
                self.photoshop_compositor = PhotoshopCompositor(
                    color_space=color_space, 
                    use_16bit=use_16bit, 
                    enable_gpu=self.enable_gpu
                )
                
                self.alpha_compositor = AlphaCompositor(
                    use_subpixel=(self.quality in [CompositeQuality.HIGH, CompositeQuality.PHOTOSHOP]),
                    anti_alias=True
                )
                
                self.quality_engine = QualityEngine(enable_gpu=self.enable_gpu)
                
                self.professional_blender = ProfessionalBlender(
                    use_16bit=use_16bit,
                    color_space=color_space.replace('linear', 'linear_rgb')
                )
                
                safe_print(f"[INFO] 高级合成引擎初始化成功，质量级别: {self.quality.value}")
                
            except Exception as e:
                safe_print(f"[ERROR] 高级引擎初始化失败: {e}")
                self.engines_available = False
        
        # 后备引擎
        if not self.engines_available and LEGACY_BLENDER_AVAILABLE:
            safe_print("[INFO] 使用传统混合引擎作为后备")
    
    def composite_layers(self, layers: List[Dict[str, Any]], 
                        canvas_size: Tuple[int, int],
                        background_color: Tuple[int, int, int, int] = (0, 0, 0, 0),
                        optimize_memory: bool = True) -> Image.Image:
        """
        合成多个图层（主要接口）
        
        Args:
            layers: 图层列表，格式：[{
                'image': PIL.Image,
                'blend_mode': str,
                'opacity': float,
                'position': (x, y),
                'mask': PIL.Image (可选)
            }]
            canvas_size: 画布尺寸
            background_color: 背景颜色
            optimize_memory: 是否优化内存使用
            
        Returns:
            合成后的图像
        """
        start_time = time.time()
        
        try:
            # 快速检查输入数据
            if not layers:
                return Image.new('RGBA', canvas_size, background_color)

            # 验证图层数据
            valid_layers = []
            for layer in layers:
                if (isinstance(layer, dict) and
                    'image' in layer and
                    layer['image'] is not None):
                    valid_layers.append(layer)

            if not valid_layers:
                safe_print("[WARNING] 没有有效的图层数据")
                return Image.new('RGBA', canvas_size, background_color)

            layers = valid_layers

            # 检查缓存
            cache_key = self._generate_cache_key(layers, canvas_size, background_color)
            if cache_key in self._cache:
                self.stats['cache_hits'] += 1
                return self._cache[cache_key].copy()

            self.stats['cache_misses'] += 1
            
            # 选择合成方法 - 简化条件，减少复杂度
            if self.engines_available and len(layers) > 0:
                # 对于简单情况，使用标准合成以提高性能
                if len(layers) <= 2 and self.quality == CompositeQuality.BALANCED:
                    result = self._standard_composite(layers, canvas_size, background_color)
                else:
                    result = self._advanced_composite(layers, canvas_size, background_color)
            else:
                result = self._standard_composite(layers, canvas_size, background_color)
            
            # 缓存结果
            if cache_key:
                self._add_to_cache(cache_key, result.copy())
            
            # 内存优化
            if optimize_memory:
                gc.collect()
            
            # 更新统计
            self.stats['total_operations'] += 1
            self.stats['total_time'] += time.time() - start_time
            
            return result
            
        except Exception as e:
            safe_print(f"[ERROR] 图层合成失败: {e}")
            # 回退到简单合成
            return self._fallback_composite(layers, canvas_size, background_color)
    
    def _advanced_composite(self, layers: List[Dict[str, Any]], 
                           canvas_size: Tuple[int, int],
                           background_color: Tuple[int, int, int, int]) -> Image.Image:
        """使用高级引擎进行合成"""
        # 转换图层格式
        ps_layers = []
        for layer in layers:
            ps_layer = {
                'image': layer['image'],
                'blend_mode': self._convert_blend_mode(layer.get('blend_mode', 'normal')),
                'opacity': layer.get('opacity', 1.0),
                'position': layer.get('position', (0, 0)),
                'mask': layer.get('mask', None)
            }
            ps_layers.append(ps_layer)
        
        # 使用Photoshop合成器
        return self.photoshop_compositor.composite_layers(ps_layers, canvas_size, background_color)
    
    def _standard_composite(self, layers: List[Dict[str, Any]], 
                           canvas_size: Tuple[int, int],
                           background_color: Tuple[int, int, int, int]) -> Image.Image:
        """使用标准方法进行合成"""
        # 创建画布
        canvas = Image.new('RGBA', canvas_size, background_color)
        
        # 逐层合成
        for layer in layers:
            image = layer['image']
            blend_mode = layer.get('blend_mode', 'normal')
            opacity = layer.get('opacity', 1.0)
            position = layer.get('position', (0, 0))
            mask = layer.get('mask', None)
            
            # 应用蒙版
            if mask:
                image = self._apply_mask(image, mask)
            
            # 应用不透明度
            if opacity < 1.0:
                image = self._apply_opacity(image, opacity)
            
            # 定位图层
            positioned_image = self._position_layer(image, canvas_size, position)
            
            # 混合
            if self.engines_available:
                canvas = self.professional_blender.blend(
                    canvas, positioned_image, 
                    self._convert_pro_blend_mode(blend_mode), 1.0
                )
            else:
                canvas = self._legacy_blend(canvas, positioned_image, blend_mode)
        
        return canvas
    
    def _fallback_composite(self, layers: List[Dict[str, Any]], 
                           canvas_size: Tuple[int, int],
                           background_color: Tuple[int, int, int, int]) -> Image.Image:
        """后备合成方法"""
        canvas = Image.new('RGBA', canvas_size, background_color)
        
        for layer in layers:
            image = layer['image']
            position = layer.get('position', (0, 0))
            opacity = layer.get('opacity', 1.0)
            
            # 简单的alpha合成
            if opacity < 1.0:
                image = self._apply_opacity(image, opacity)
            
            # 粘贴到画布
            if image.mode == 'RGBA':
                canvas.paste(image, position, image)
            else:
                canvas.paste(image, position)
        
        return canvas
    
    def smart_resize(self, image: Image.Image, target_size: Tuple[int, int],
                    method: Optional[str] = None) -> Image.Image:
        """
        智能缩放图像
        
        Args:
            image: 输入图像
            target_size: 目标尺寸
            method: 缩放方法（None表示自动选择）
            
        Returns:
            缩放后的图像
        """
        if not self.engines_available:
            return image.resize(target_size, Image.LANCZOS)
        
        try:
            # 转换方法名称
            scaling_method = None
            if method:
                method_map = {
                    'edge_preserving': ScalingMethod.EDGE_PRESERVING,
                    'super_resolution': ScalingMethod.SUPER_RESOLUTION,
                    'lanczos_plus': ScalingMethod.LANCZOS_PLUS,
                    'bicubic_sharp': ScalingMethod.BICUBIC_SHARP,
                    'adaptive': ScalingMethod.ADAPTIVE
                }
                scaling_method = method_map.get(method)
            
            return self.quality_engine.smart_resize(image, target_size, scaling_method)
            
        except Exception as e:
            safe_print(f"[ERROR] 智能缩放失败: {e}")
            return image.resize(target_size, Image.LANCZOS)
    
    def enhance_transparency(self, image: Image.Image, method: str = 'subpixel') -> Image.Image:
        """
        增强半透明效果
        
        Args:
            image: 输入图像
            method: 增强方法
            
        Returns:
            增强后的图像
        """
        if not self.engines_available:
            return image
        
        try:
            return self.alpha_compositor.enhance_alpha_edges(image, method)
        except Exception as e:
            safe_print(f"[ERROR] 透明度增强失败: {e}")
            return image
    
    def _convert_blend_mode(self, mode_str):
        """转换混合模式到Photoshop格式"""
        if not ADVANCED_ENGINES_AVAILABLE:
            return str(mode_str)

        # 确保输入是字符串
        if not isinstance(mode_str, str):
            mode_str = str(mode_str)

        mode_map = {
            'normal': PSBlendMode.NORMAL,
            'multiply': PSBlendMode.MULTIPLY,
            'screen': PSBlendMode.SCREEN,
            'overlay': PSBlendMode.OVERLAY,
            'soft_light': PSBlendMode.SOFT_LIGHT,
            'hard_light': PSBlendMode.HARD_LIGHT,
            'color_dodge': PSBlendMode.COLOR_DODGE,
            'color_burn': PSBlendMode.COLOR_BURN,
            'darken': PSBlendMode.DARKEN,
            'lighten': PSBlendMode.LIGHTEN,
            'difference': PSBlendMode.DIFFERENCE,
            'exclusion': PSBlendMode.EXCLUSION,
            '0': PSBlendMode.NORMAL,  # 处理数字形式的混合模式
            '1': PSBlendMode.MULTIPLY,
            '2': PSBlendMode.SCREEN
        }
        return mode_map.get(mode_str.lower(), PSBlendMode.NORMAL)

    def _convert_pro_blend_mode(self, mode_str):
        """转换混合模式到专业格式"""
        if not ADVANCED_ENGINES_AVAILABLE:
            return str(mode_str)

        # 确保输入是字符串
        if not isinstance(mode_str, str):
            mode_str = str(mode_str)

        mode_map = {
            'normal': ProBlendMode.NORMAL,
            'multiply': ProBlendMode.MULTIPLY,
            'screen': ProBlendMode.SCREEN,
            'overlay': ProBlendMode.OVERLAY,
            'soft_light': ProBlendMode.SOFT_LIGHT,
            'hard_light': ProBlendMode.HARD_LIGHT,
            'color_dodge': ProBlendMode.COLOR_DODGE,
            'color_burn': ProBlendMode.COLOR_BURN,
            'darken': ProBlendMode.DARKEN,
            'lighten': ProBlendMode.LIGHTEN,
            'difference': ProBlendMode.DIFFERENCE,
            'exclusion': ProBlendMode.EXCLUSION,
            '0': ProBlendMode.NORMAL,  # 处理数字形式的混合模式
            '1': ProBlendMode.MULTIPLY,
            '2': ProBlendMode.SCREEN
        }
        return mode_map.get(mode_str.lower(), ProBlendMode.NORMAL)
    
    def _legacy_blend(self, base: Image.Image, overlay: Image.Image, mode: str) -> Image.Image:
        """使用传统混合方法"""
        if LEGACY_BLENDER_AVAILABLE:
            try:
                return LegacyBlender.apply_blend_mode(base, overlay, mode, 1.0)
            except:
                pass
        
        # 最简单的alpha合成
        result = base.copy()
        if overlay.mode == 'RGBA':
            result.paste(overlay, (0, 0), overlay)
        else:
            result.paste(overlay, (0, 0))
        return result
    
    def _apply_mask(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        """应用蒙版"""
        if mask.mode != 'L':
            mask = mask.convert('L')
        
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 将蒙版应用到alpha通道
        r, g, b, a = image.split()
        a = Image.composite(a, Image.new('L', a.size, 0), mask)
        return Image.merge('RGBA', (r, g, b, a))
    
    def _apply_opacity(self, image: Image.Image, opacity: float) -> Image.Image:
        """应用不透明度"""
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        r, g, b, a = image.split()
        a = a.point(lambda x: int(x * opacity))
        return Image.merge('RGBA', (r, g, b, a))
    
    def _position_layer(self, image: Image.Image, canvas_size: Tuple[int, int], 
                       position: Tuple[int, int]) -> Image.Image:
        """定位图层"""
        canvas = Image.new('RGBA', canvas_size, (0, 0, 0, 0))
        canvas.paste(image, position, image if image.mode == 'RGBA' else None)
        return canvas
    
    def _generate_cache_key(self, layers: List[Dict[str, Any]], 
                           canvas_size: Tuple[int, int],
                           background_color: Tuple[int, int, int, int]) -> Optional[str]:
        """生成缓存键"""
        try:
            # 简化的缓存键生成
            key_parts = [
                str(canvas_size),
                str(background_color),
                str(len(layers)),
                str(self.quality.value)
            ]
            return '_'.join(key_parts)
        except:
            return None
    
    def _add_to_cache(self, key: str, image: Image.Image):
        """添加到缓存"""
        # 简单的LRU缓存
        if len(self._cache) >= 10:  # 限制缓存大小
            oldest_key = self._cache_order.pop(0)
            del self._cache[oldest_key]
        
        self._cache[key] = image
        self._cache_order.append(key)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        stats = self.stats.copy()
        if stats['total_operations'] > 0:
            stats['avg_time_per_operation'] = stats['total_time'] / stats['total_operations']
            stats['cache_hit_rate'] = stats['cache_hits'] / (stats['cache_hits'] + stats['cache_misses'])
        return stats
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._cache_order.clear()
        gc.collect()
