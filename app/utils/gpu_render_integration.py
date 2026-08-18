"""
GPU渲染集成器
将GPU加速渲染无缝集成到现有的渲染管线中
保持完全的向后兼容性
"""


import os as _os
_BTPW_VERBOSE = _os.environ.get("BTPW_VERBOSE_LOG", "0").strip().lower() in ("1", "true", "yes", "on")
_ALWAYS_PRINT_KW = ("[ERROR]", "[CRITICAL]", "[严重错误]", "错误", "失败", "Exception", "Traceback", "[WARNING]")
def print(*args, **kwargs):
    if _BTPW_VERBOSE:
        __builtins__["print"](*args, **kwargs)
        return
    try:
        msg = " ".join(str(a) for a in args)
    except Exception:
        msg = ""
    if any(kw in msg for kw in _ALWAYS_PRINT_KW):
        __builtins__["print"](*args, **kwargs)

import time
import threading
from typing import Optional, List, Any, Dict
from PIL import Image
from dataclasses import dataclass

# 导入GPU渲染器
try:
    from app.utils.gpu_renderer import get_gpu_renderer, GPURenderConfig, cleanup_gpu_renderer
    GPU_RENDERER_AVAILABLE = True
except ImportError:
    GPU_RENDERER_AVAILABLE = False
    print("[GPU集成] GPU渲染器不可用")


@dataclass
class RenderStats:
    """渲染统计"""
    total_renders: int = 0
    gpu_renders: int = 0
    cpu_renders: int = 0
    gpu_time: float = 0.0
    cpu_time: float = 0.0
    gpu_failures: int = 0


class GPURenderIntegrator:
    """GPU渲染集成器"""
    
    def __init__(self):
        self.gpu_renderer = None
        self.gpu_enabled = True
        self.auto_fallback = True
        self.stats = RenderStats()
        self.lock = threading.Lock()
        
        # 性能阈值
        self.min_layers_for_gpu = 2  # 最少图层数才使用GPU
        self.min_canvas_size_for_gpu = 100 * 100  # 最小画布尺寸
        self.gpu_failure_threshold = 3  # GPU失败次数阈值
        self.consecutive_failures = 0
        
        print("[GPU集成] GPU渲染集成器初始化完成")
    
    def should_use_gpu(self, layers: List[Any], canvas_width: int, canvas_height: int) -> bool:
        """判断是否应该使用GPU渲染"""
        if not self.gpu_enabled or not GPU_RENDERER_AVAILABLE:
            return False
        
        # 检查连续失败次数
        if self.consecutive_failures >= self.gpu_failure_threshold:
            return False
        
        # 检查图层数量
        visible_layers = [layer for layer in layers if layer.visible]
        if len(visible_layers) < self.min_layers_for_gpu:
            return False
        
        # 检查画布尺寸
        canvas_area = canvas_width * canvas_height
        if canvas_area < self.min_canvas_size_for_gpu:
            return False
        
        # 检查是否有复杂效果
        has_complex_effects = any(
            (hasattr(layer, 'corner_radius') and layer.corner_radius > 0) or
            (hasattr(layer, 'blur_radius') and layer.blur_radius > 0) or
            (hasattr(layer, 'opacity') and layer.opacity < 1.0)
            for layer in visible_layers
        )
        
        # 复杂效果更适合GPU处理
        if has_complex_effects:
            return True
        
        # 大画布或多图层适合GPU处理
        return canvas_area > 500 * 500 or len(visible_layers) > 5
    
    def render_composition_integrated(self, document, **kwargs) -> Optional[Image.Image]:
        """集成的图层组合渲染"""
        layers = document.layers
        canvas_width = document.canvas_width
        canvas_height = document.canvas_height
        
        # 决定使用GPU还是CPU渲染
        use_gpu = self.should_use_gpu(layers, canvas_width, canvas_height)
        
        if use_gpu:
            return self._render_with_gpu(document, **kwargs)
        else:
            return self._render_with_cpu(document, **kwargs)
    
    def _render_with_gpu(self, document, **kwargs) -> Optional[Image.Image]:
        """使用GPU渲染"""
        start_time = time.time()
        
        try:
            with self.lock:
                # 初始化GPU渲染器（如果需要）
                if self.gpu_renderer is None:
                    config = GPURenderConfig(
                        enable_gpu=True,
                        fallback_to_cpu=True,
                        max_texture_size=4096
                    )
                    self.gpu_renderer = get_gpu_renderer(config)
                
                # 初始化GPU上下文（如果需要）
                if not self.gpu_renderer.is_gpu_available():
                    if not self.gpu_renderer.initialize(document.canvas_width, document.canvas_height):
                        print("[GPU集成] GPU初始化失败，回退到CPU渲染")
                        return self._render_with_cpu(document, **kwargs)
                
                # 执行GPU渲染
                result = self.gpu_renderer.render_composition_gpu(
                    document.layers, 
                    document.canvas_width, 
                    document.canvas_height
                )
                
                if result is not None:
                    # GPU渲染成功
                    render_time = time.time() - start_time
                    self.stats.total_renders += 1
                    self.stats.gpu_renders += 1
                    self.stats.gpu_time += render_time
                    self.consecutive_failures = 0

                    print(f"[GPU集成] GPU渲染成功: {render_time:.3f}秒")
                    return result
                else:
                    # GPU渲染失败，回退到CPU
                    print("[GPU集成] GPU渲染返回None，回退到CPU渲染")
                    self.consecutive_failures += 1
                    self.stats.gpu_failures += 1
                    return self._render_with_cpu(document, **kwargs)
                
        except Exception as e:
            print(f"[GPU集成] GPU渲染异常: {e}")
            self.consecutive_failures += 1
            self.stats.gpu_failures += 1
            
            # 回退到CPU渲染
            return self._render_with_cpu(document, **kwargs)
    
    def _render_with_cpu(self, document, **kwargs) -> Optional[Image.Image]:
        """使用CPU渲染（原始方法）"""
        start_time = time.time()
        
        try:
            # 调用原始的渲染方法
            result = self._original_render_composition(document, **kwargs)
            
            if result is not None:
                render_time = time.time() - start_time
                self.stats.total_renders += 1
                self.stats.cpu_renders += 1
                self.stats.cpu_time += render_time

                print(f"[GPU集成] CPU渲染完成: {render_time:.3f}秒")
                return result
            
        except Exception as e:
            print(f"[GPU集成] CPU渲染失败: {e}")
        
        return None
    
    def _original_render_composition(self, document, **kwargs) -> Optional[Image.Image]:
        """原始的CPU渲染方法"""
        # 这里调用原始的render_composition方法
        # 为了避免循环导入，我们直接实现基础的CPU渲染逻辑
        
        try:
            from app.models.text_layer import TextLayer
            # 创建空白画布
            composition = Image.new('RGBA', (document.canvas_width, document.canvas_height), (0, 0, 0, 0))
            
            # 渲染每个图层
            for layer in document.layers:
                if not layer.visible:
                    continue
                
                # 获取图层图像
                layer_image = None
                if isinstance(layer, TextLayer):
                    layer_image = layer.render_text()
                else:
                    if hasattr(layer, 'cached_image') and layer.cached_image is not None:
                        layer_image = layer.cached_image
                    elif hasattr(layer, 'get_random_image'):
                        layer_image = layer.get_random_image()
                
                if layer_image is None:
                    continue
                
                # 应用图层效果
                if hasattr(layer, 'apply_effects'):
                    layer_image = layer.apply_effects(layer_image)
                
                # 合成到画布上
                if layer_image.mode != 'RGBA':
                    layer_image = layer_image.convert('RGBA')

                # 应用透明度
                if hasattr(layer, 'opacity') and layer.opacity < 1.0:
                    # 创建透明度蒙版
                    alpha = layer_image.split()[-1]
                    alpha = alpha.point(lambda p: int(p * layer.opacity))
                    layer_image.putalpha(alpha)

                # 处理分身功能
                clone_positions = []
                is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled

                if is_clone_enabled and hasattr(layer, 'get_effective_clone_positions'):
                    # 获取所有分身位置（包含随机偏移）
                    try:
                        clone_positions = layer.get_effective_clone_positions()
                        print(f"[GPU集成] 图层 '{layer.name}' 启用分身，共 {len(clone_positions)} 个位置")
                    except Exception as e:
                        print(f"[GPU集成] 获取分身位置失败: {e}")
                        # 回退到单一位置
                        if hasattr(layer, 'get_effective_position'):
                            clone_positions = [layer.get_effective_position()]
                        else:
                            clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]
                else:
                    # 没有启用分身，使用单一位置（包含随机偏移）
                    if hasattr(layer, 'get_effective_position'):
                        clone_positions = [layer.get_effective_position()]
                    else:
                        clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]

                # 为每个分身位置合成图层
                for pos_x, pos_y in clone_positions:
                    from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
                    if composition.mode != 'RGBA':
                        composition = composition.convert('RGBA')
                    if layer_image.mode != 'RGBA':
                        layer_image = layer_image.convert('RGBA')
                    if composition.size == layer_image.size:
                        composition = UnifiedAlphaCompositor.blend_normal(composition, layer_image, 1.0)
                    else:
                        temp_layer = Image.new('RGBA', composition.size, (0, 0, 0, 0))
                        temp_layer.paste(layer_image, (pos_x, pos_y), layer_image)
                        composition = UnifiedAlphaCompositor.blend_normal(composition, temp_layer, 1.0)
            
            return composition
            
        except Exception as e:
            print(f"[GPU集成] 原始渲染方法失败: {e}")
            return None
    
    def get_render_stats(self) -> Dict[str, Any]:
        """获取渲染统计"""
        total_renders = self.stats.total_renders
        if total_renders == 0:
            return {
                'total_renders': 0,
                'gpu_usage_rate': 0.0,
                'avg_gpu_time': 0.0,
                'avg_cpu_time': 0.0,
                'gpu_speedup': 1.0,
                'gpu_failure_rate': 0.0
            }
        
        gpu_usage_rate = (self.stats.gpu_renders / total_renders) * 100
        avg_gpu_time = (self.stats.gpu_time / self.stats.gpu_renders) if self.stats.gpu_renders > 0 else 0
        avg_cpu_time = (self.stats.cpu_time / self.stats.cpu_renders) if self.stats.cpu_renders > 0 else 0
        gpu_speedup = (avg_cpu_time / avg_gpu_time) if avg_gpu_time > 0 else 1.0
        gpu_failure_rate = (self.stats.gpu_failures / (self.stats.gpu_renders + self.stats.gpu_failures)) * 100 if (self.stats.gpu_renders + self.stats.gpu_failures) > 0 else 0
        
        return {
            'total_renders': total_renders,
            'gpu_renders': self.stats.gpu_renders,
            'cpu_renders': self.stats.cpu_renders,
            'gpu_usage_rate': gpu_usage_rate,
            'avg_gpu_time': avg_gpu_time,
            'avg_cpu_time': avg_cpu_time,
            'gpu_speedup': gpu_speedup,
            'gpu_failure_rate': gpu_failure_rate,
            'consecutive_failures': self.consecutive_failures
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = RenderStats()
        self.consecutive_failures = 0
        print("[GPU集成] 渲染统计已重置")
    
    def enable_gpu(self, enabled: bool = True):
        """启用/禁用GPU渲染"""
        self.gpu_enabled = enabled
        if not enabled:
            self.consecutive_failures = 0
        print(f"[GPU集成] GPU渲染{'启用' if enabled else '禁用'}")
    
    def set_gpu_thresholds(self, min_layers: int = None, min_canvas_size: int = None, failure_threshold: int = None):
        """设置GPU使用阈值"""
        if min_layers is not None:
            self.min_layers_for_gpu = min_layers
        if min_canvas_size is not None:
            self.min_canvas_size_for_gpu = min_canvas_size
        if failure_threshold is not None:
            self.gpu_failure_threshold = failure_threshold
        
        print(f"[GPU集成] GPU阈值更新: 最少图层={self.min_layers_for_gpu}, "
              f"最小画布={self.min_canvas_size_for_gpu}, 失败阈值={self.gpu_failure_threshold}")
    
    def force_gpu_reset(self):
        """强制重置GPU状态"""
        with self.lock:
            if self.gpu_renderer:
                self.gpu_renderer.cleanup()
                self.gpu_renderer = None
            self.consecutive_failures = 0
            print("[GPU集成] GPU状态已强制重置")
    
    def cleanup(self):
        """清理GPU集成器"""
        with self.lock:
            if self.gpu_renderer:
                self.gpu_renderer.cleanup()
                self.gpu_renderer = None
            
            cleanup_gpu_renderer()
            print("[GPU集成] GPU集成器已清理")


# 全局GPU集成器实例
_gpu_integrator = None
_integrator_lock = threading.Lock()

def get_gpu_integrator() -> GPURenderIntegrator:
    """获取全局GPU集成器实例"""
    global _gpu_integrator
    
    with _integrator_lock:
        if _gpu_integrator is None:
            _gpu_integrator = GPURenderIntegrator()
        return _gpu_integrator

def cleanup_gpu_integrator():
    """清理全局GPU集成器"""
    global _gpu_integrator
    
    with _integrator_lock:
        if _gpu_integrator is not None:
            _gpu_integrator.cleanup()
            _gpu_integrator = None


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")
