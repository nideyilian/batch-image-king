"""
真正有效的快速渲染器（优化版本）
解决实际使用中的性能问题，不降低质量
集成智能渲染缓存系统
"""

import time
import hashlib
import threading
import os
import builtins
from collections import OrderedDict, deque
from functools import wraps
from typing import Optional, Dict, Any, Tuple
import math
from PIL import Image
import numpy as np
import weakref
import gc

# 默认关闭快速渲染器调试输出，避免预览阶段高频 I/O 导致掉帧
_FAST_RENDERER_DEBUG = os.environ.get("BTPW_FAST_RENDERER_DEBUG", "0") == "1"
# 默认关闭批量渲染高频日志，避免导出阶段控制台 I/O 成为瓶颈
_BATCH_RENDER_VERBOSE = os.environ.get("BTPW_BATCH_RENDER_VERBOSE", "0") == "1"
try:
    _INTERACTIVE_PREVIEW_MAX_EDGE = max(480, int(os.environ.get("BTPW_INTERACTIVE_PREVIEW_MAX_EDGE", "1200")))
except Exception:
    _INTERACTIVE_PREVIEW_MAX_EDGE = 1200
# 内孔检测算法版本号：用于缓存键，避免算法升级后命中旧检测结果
_SIZE_MATCH_HOLE_DETECT_VER = "v10"
# 自动倾斜最小触发角（度）：小于该值视为不倾斜，减少误判抖动
_AUTO_ROTATE_MIN_DEG = 4.0


def print(*args, **kwargs):
    if _FAST_RENDERER_DEBUG:
        builtins.print(*args, **kwargs)


def _serialized_preview(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._preview_render_lock:
            return method(self, *args, **kwargs)
    return wrapper


# 导入新的智能缓存系统
from .intelligent_render_cache import get_intelligent_cache
# 导入智能内存管理系统
from .intelligent_memory_manager import get_memory_manager, register_image_for_tracking
from .render_diagnostics import log_branch


class SmartCache:
    """智能缓存系统"""
    
    def __init__(self, max_size: int = 10):
        self._cache = {}
        self._access_times = {}
        self._max_size = max_size
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, document) -> str:
        """生成缓存键 - 包含随机变换参数"""
        try:
            key_parts = [
                f"canvas:{document.canvas_width}x{document.canvas_height}"
            ]

            # 图层大小匹配配置纳入缓存键，避免切换规则后命中旧缓存
            try:
                manager = getattr(document, 'layer_size_match_manager', None)
                if manager and getattr(manager, 'global_enabled', False):
                    serialized = manager.serialize() if hasattr(manager, 'serialize') else {}
                    serialized_text = str(serialized)
                    match_hash = hashlib.md5(serialized_text.encode('utf-8')).hexdigest()[:8]
                    key_parts.append(f"size_match:{match_hash}")
            except Exception:
                pass

            for i, layer in enumerate(document.layers):
                if not layer.visible:
                    continue

                layer_key = f"layer{i}:{getattr(layer, 'x', 0)}:{getattr(layer, 'y', 0)}:{getattr(layer, 'opacity', 1.0)}"

                # 添加图像源路径到缓存键（关键修复：当文件夹地址改变时缓存失效）
                image_source = getattr(layer, 'image_source', None) or getattr(layer, '_image_source', None)
                if image_source:
                    # 使用路径的哈希值来避免缓存键过长
                    source_hash = hashlib.md5(str(image_source).encode()).hexdigest()[:8]
                    layer_key += f":src{source_hash}"

                # 添加随机变换参数到缓存键
                if hasattr(layer, '_current_random_offset_x'):
                    layer_key += f":rnd_pos{getattr(layer, '_current_random_offset_x', 0)},{getattr(layer, '_current_random_offset_y', 0)}"
                if hasattr(layer, '_current_random_scale'):
                    layer_key += f":rnd_scale{getattr(layer, '_current_random_scale', 1.0):.3f}"
                if hasattr(layer, '_current_random_rotation'):
                    layer_key += f":rnd_rot{getattr(layer, '_current_random_rotation', 0.0):.1f}"

                # 添加当前图像路径标识（对于随机图像选择）
                if hasattr(layer, 'current_image_path') and layer.current_image_path:
                    img_name = os.path.basename(layer.current_image_path)
                    layer_key += f":img{img_name}"
                elif hasattr(layer, 'cached_image') and layer.cached_image:
                    img_id = id(layer.cached_image)
                    layer_key += f":cached{img_id}"
                elif hasattr(layer, 'image_paths') and layer.image_paths:
                    layer_key += f":path{len(layer.image_paths)}"

                # 添加文字图层关键排版参数（修复：竖排/边距等切换后缓存未失效）
                if hasattr(layer, 'current_text'):
                    text_value = getattr(layer, 'current_text', '') or ''
                    text_hash = hashlib.md5(text_value.encode('utf-8')).hexdigest()[:8]
                    layer_key += f":text{text_hash}"
                    layer_key += f":font{getattr(layer, 'font_family', '')}"
                    layer_key += f":fs{getattr(layer, 'font_size', 0)}"
                    layer_key += f":fst{getattr(layer, 'font_style', '')}"
                    layer_key += f":align{getattr(layer, 'text_align', '')}"
                    layer_key += f":ls{getattr(layer, 'line_spacing', 1.0)}"
                    layer_key += f":cs{getattr(layer, 'letter_spacing', 0)}"
                    layer_key += f":v{int(bool(getattr(layer, 'vertical_layout', False)))}"
                    layer_key += f":af{int(bool(getattr(layer, 'auto_fit_text_box', False)))}"
                    layer_key += f":pad{int(getattr(layer, 'text_box_padding', 0))}"
                    layer_key += f":tc{getattr(layer, 'text_color', '')}"
                    layer_key += f":tcr{getattr(layer, 'text_color_ranges', getattr(layer, '_text_color_ranges', []))}"
                    layer_key += f":se{int(bool(getattr(layer, 'stroke_enabled', False)))}"
                    layer_key += f":sw{getattr(layer, 'stroke_width', 0)}"
                    layer_key += f":sc{getattr(layer, 'stroke_color', '')}"
                    layer_key += f":be{int(bool(getattr(layer, 'background_enabled', False)))}"
                    layer_key += f":bc{getattr(layer, 'background_color', '')}"
                    layer_key += f":bp{getattr(layer, 'background_padding', 0)}"
                    layer_key += f":ge{int(bool(getattr(layer, 'gradient_enabled', False)))}"
                    layer_key += f":gt{getattr(layer, 'gradient_type', '')}"
                    layer_key += f":gd{getattr(layer, 'gradient_direction', '')}"
                    layer_key += f":gsc{getattr(layer, 'gradient_start_color', '')}"
                    layer_key += f":gec{getattr(layer, 'gradient_end_color', '')}"
                    layer_key += f":gc{getattr(layer, 'gradient_center_x', 0.5)},{getattr(layer, 'gradient_center_y', 0.5)}"

                key_parts.append(layer_key)

            key_string = "|".join(key_parts)
            return hashlib.md5(key_string.encode()).hexdigest()[:16]
        except Exception as e:
            # 如果生成缓存键失败，使用时间戳确保不会使用错误的缓存
            print(f"[快速渲染] 缓存键生成失败: {e}")
            return f"fallback_{time.time()}"
    
    def get(self, document, is_batch_mode: bool = False) -> Optional[Image.Image]:
        """获取缓存 - 🔧 智能修复：预览启用缓存，批量禁用缓存"""
        with self._lock:
            if is_batch_mode:
                # 🔧 批量模式：禁用缓存，避免重复图片问题
                self._misses += 1
                return None  # 批量导出时总是重新渲染
            else:
                # 🔧 预览模式：启用缓存，提高预览性能
                key = self._generate_key(document)
                if key in self._cache:
                    self._access_times[key] = time.time()
                    self._hits += 1
                    return self._cache[key].copy()

                self._misses += 1
                return None
    
    def put(self, document, image: Image.Image, is_batch_mode: bool = False):
        """存储缓存 - 🔧 智能修复：预览启用缓存，批量禁用缓存"""
        if is_batch_mode:
            # 🔧 批量模式：禁用缓存存储，避免重复图片问题
            return  # 批量导出时不保存缓存

        # 🔧 预览模式：启用缓存存储，提高预览性能
        with self._lock:
            key = self._generate_key(document)

            # 清理旧缓存
            while len(self._cache) >= self._max_size:
                oldest_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
                del self._cache[oldest_key]
                del self._access_times[oldest_key]

            self._cache[key] = image.copy()
            self._access_times[key] = time.time()
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
    
    def get_stats(self):
        """获取统计信息"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            'size': len(self._cache),
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': hit_rate
        }



from app.utils.fast_renderer_cache import FastRendererCache
from app.utils.fast_renderer_preview import FastRendererPreview
from app.utils.fast_renderer_surface import FastRendererSurface
from app.utils.fast_renderer_composite import FastRendererComposite

class FastRenderer(FastRendererCache, FastRendererPreview, FastRendererSurface, FastRendererComposite):
    """真正快速的渲染器（优化版本）"""
    _batch_metrics_lock = threading.RLock()
    _batch_metrics = {
        "export_layer_cache_hits": 0,
        "export_layer_cache_misses": 0,
        "layer_surface_cache_hits": 0,
        "layer_surface_cache_misses": 0,
        "apply_effects_calls": 0,
    }
    

    def __init__(self):
        self._preview_render_lock = threading.RLock()
        # 使用新的智能缓存系统
        self.intelligent_cache = get_intelligent_cache()
        # 集成智能内存管理系统
        self.memory_manager = get_memory_manager()
        self._memory_status_cache = None
        self._memory_status_cache_time = 0.0
        self._memory_status_cache_ttl = 0.75
        self._last_render_time = {}
        self._verbose_logging = False
        # 图层级 surface 缓存（Photoshop 风格：仅重算脏图层）
        self._layer_surface_cache = OrderedDict()
        self._layer_surface_lock = threading.RLock()
        self._max_layer_surface_entries = 96
        # 导出层缓存（按图层+参数hash复用），提升批量导出重复参数命中率
        self._export_layer_surface_cache = OrderedDict()
        self._export_layer_surface_lock = threading.RLock()
        self._max_export_layer_surface_entries = 320
        self._export_layer_surface_bytes = 0
        self._export_layer_surface_entry_bytes = {}
        self._max_export_layer_surface_bytes = self._resolve_cache_budget_bytes(
            "BTPW_EXPORT_LAYER_CACHE_MB", 384, minimum_mb=64
        )
        # 图层分身/填充位置缓存，减少重复几何计算
        self._layer_positions_cache = OrderedDict()
        self._layer_positions_lock = threading.RLock()
        self._max_layer_positions_entries = 256
        # 预览快照：导出进行中可直接复用，避免与导出线程争用渲染资源
        self._last_preview_snapshot: Optional[Image.Image] = None
        # 交互增量预览底图缓存（排除当前操作图层后的静态画面）
        self._interactive_base_cache = OrderedDict()
        self._interactive_base_lock = threading.RLock()
        self._max_interactive_base_entries = 16
        # 交互增量预览活动图层缓存（仅几何/变换，不含复杂特效）
        self._interactive_layer_surface_cache = OrderedDict()
        self._interactive_layer_surface_lock = threading.RLock()
        self._max_interactive_layer_surface_entries = 64
        # 大小匹配相关缓存：内孔检测缓存 + 指定尺寸surface缓存
        self._size_match_holes_cache = OrderedDict()
        self._size_match_holes_lock = threading.RLock()
        self._max_size_match_holes_entries = 96
        self._size_override_surface_cache = OrderedDict()
        self._size_override_surface_lock = threading.RLock()
        self._max_size_override_surface_entries = 192
        # 批量导出会话缓存：减少重复读盘与重复处理
        self._batch_raw_image_cache = OrderedDict()
        self._batch_raw_image_lock = threading.RLock()
        self._max_batch_raw_entries = 128
        self._batch_raw_image_bytes = 0
        self._batch_raw_image_entry_bytes = {}
        self._max_batch_raw_bytes = self._resolve_cache_budget_bytes(
            "BTPW_BATCH_RAW_CACHE_MB", 256, minimum_mb=32
        )
        self._batch_processed_image_cache = OrderedDict()
        self._batch_processed_image_lock = threading.RLock()
        self._max_batch_processed_entries = 512
        self._batch_processed_image_bytes = 0
        self._batch_processed_image_entry_bytes = {}
        self._max_batch_processed_bytes = self._resolve_cache_budget_bytes(
            "BTPW_BATCH_PROCESSED_CACHE_MB", 512, minimum_mb=64
        )
        
        if self._verbose_logging:
            print("[快速渲染] 初始化完成，使用智能缓存系统和内存管理")



# 以下方法实现位于各个 mixin 模块中，通过多重继承组合进来。
# 主类仅保留类级属性与 __init__。

def get_global_fast_renderer() -> FastRenderer:
    """获取全局快速渲染器"""
    global _global_fast_renderer
    if _global_fast_renderer is None:
        _global_fast_renderer = FastRenderer()
        print("[快速渲染] 初始化全局快速渲染器")
    return _global_fast_renderer


def test_fast_renderer():
    """测试快速渲染器"""
    print("=== 测试快速渲染器 ===")
    
    try:
        renderer = get_global_fast_renderer()
        
        # 创建模拟文档
        class MockDocument:
            def __init__(self):
                self.canvas_width = 800
                self.canvas_height = 600
                self.layers = []
        
        class MockLayer:
            def __init__(self, x, y):
                self.x = x
                self.y = y
                self.visible = True
                self.opacity = 0.8
                self.cached_image = Image.new('RGBA', (100, 100), (255, 0, 0, 200))
        
        doc = MockDocument()
        doc.layers = [MockLayer(50, 50), MockLayer(150, 150)]
        
        # 测试预览渲染
        start_time = time.time()
        result1 = renderer.render_preview(doc)
        time1 = time.time() - start_time
        
        # 测试缓存命中
        start_time = time.time()
        result2 = renderer.render_preview(doc)
        time2 = time.time() - start_time
        
        # 测试批量渲染
        start_time = time.time()
        result3 = renderer.render_batch(doc)
        time3 = time.time() - start_time
        
        print(f"预览渲染耗时: {time1:.3f}秒")
        print(f"缓存命中耗时: {time2:.3f}秒")
        print(f"批量渲染耗时: {time3:.3f}秒")
        
        # 获取统计信息
        stats = renderer.get_performance_stats()
        print(f"性能统计: {stats}")
        
        print("✓ 快速渲染器测试完成")
        return True
        
    except Exception as e:
        print(f"✗ 快速渲染器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_fast_renderer()
