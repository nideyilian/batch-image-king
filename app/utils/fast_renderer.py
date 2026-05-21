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
# 内孔检测算法版本号：用于缓存键，避免算法升级后命中旧检测结果
_SIZE_MATCH_HOLE_DETECT_VER = "v10"
# 自动倾斜最小触发角（度）：小于该值视为不倾斜，减少误判抖动
_AUTO_ROTATE_MIN_DEG = 4.0


def print(*args, **kwargs):
    if _FAST_RENDERER_DEBUG:
        builtins.print(*args, **kwargs)

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


class FastRenderer:
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
        self._batch_processed_image_cache = OrderedDict()
        self._batch_processed_image_lock = threading.RLock()
        self._max_batch_processed_entries = 512
        
        if self._verbose_logging:
            print("[快速渲染] 初始化完成，使用智能缓存系统和内存管理")

    @classmethod
    def reset_batch_metrics(cls):
        """重置批量导出渲染指标。"""
        with cls._batch_metrics_lock:
            for k in cls._batch_metrics.keys():
                cls._batch_metrics[k] = 0

    @classmethod
    def get_batch_metrics(cls):
        """获取批量导出渲染指标快照。"""
        with cls._batch_metrics_lock:
            return dict(cls._batch_metrics)

    @classmethod
    def _inc_batch_metric(cls, key: str, delta: int = 1):
        with cls._batch_metrics_lock:
            if key not in cls._batch_metrics:
                cls._batch_metrics[key] = 0
            cls._batch_metrics[key] += int(delta)
    
    def clear_cache(self):
        """清空缓存"""
        self.intelligent_cache.clear()
        self._clear_layer_surface_cache()
        self._clear_layer_positions_cache()
        self._clear_interactive_base_cache()
        self._clear_interactive_layer_surface_cache()
        self._clear_size_match_caches()
        self._clear_batch_session_caches()
        if self._verbose_logging:
            print("[快速渲染] 缓存已清空")
    
    def get_cache_stats(self):
        """获取缓存统计"""
        return self.intelligent_cache.get_stats()
    
    def optimize_cache(self):
        """优化缓存"""
        self.intelligent_cache.optimize_cache()
    
    def invalidate_document_cache(self, document):
        """使文档缓存失效"""
        self.intelligent_cache.invalidate_document(document)
        self._invalidate_layer_surfaces_for_document(document)
        self._invalidate_interactive_base_for_document(document)
        self._invalidate_interactive_layer_surfaces_for_document(document)
        self._invalidate_size_match_caches_for_document(document)
        self._invalidate_batch_session_caches_for_document(document)
    
    def get_memory_status(self):
        """获取内存状态"""
        return self.memory_manager.get_memory_status()

    def _get_cached_memory_status(self):
        """Throttle psutil-heavy memory probes during interactive preview."""
        now = time.time()
        if (
            self._memory_status_cache is not None
            and now - self._memory_status_cache_time < self._memory_status_cache_ttl
        ):
            return self._memory_status_cache
        status = self.memory_manager.get_memory_status()
        self._memory_status_cache = status
        self._memory_status_cache_time = now
        return status
    
    def optimize_memory(self):
        """优化内存使用"""
        self.memory_manager.force_optimization()
    
    def start_memory_monitoring(self):
        """启动内存监控"""
        self.memory_manager.start_monitoring()
    
    def stop_memory_monitoring(self):
        """停止内存监控"""
        self.memory_manager.stop_monitoring()

    def _is_export_preview_frozen(self, document) -> bool:
        """导出期间是否冻结预览重渲染（由导出设置控制）"""
        if not bool(getattr(document, '_is_batch_export_running', False)):
            return False
        try:
            settings = getattr(document, 'export_settings', {}) or {}
            return bool(settings.get('freeze_preview_during_export', False))
        except Exception:
            return False
    
    def render_preview(self, document, force_refresh: bool = False, interactive_low_quality: bool = False) -> Optional[Image.Image]:
        """预览渲染 - 优化版本，使用智能缓存和内存管理"""
        quality_level = 'preview_interactive' if interactive_low_quality else 'preview'
        log_branch(
            "fast_renderer.render_preview",
            "enter",
            force_refresh=force_refresh,
            interactive_low_quality=interactive_low_quality
        )
        # 导出过程中默认复用已有预览，降低UI卡顿与线程争用
        if self._is_export_preview_frozen(document) and not force_refresh:
            cached = self.intelligent_cache.get(document, quality_level=quality_level)
            if cached:
                log_branch("fast_renderer.render_preview", "cache_hit_export_freeze")
                return cached
            if self._last_preview_snapshot is not None:
                log_branch("fast_renderer.render_preview", "snapshot_hit_export_freeze")
                return self._last_preview_snapshot.copy()
        
        # 检查内存状态
        memory_status = self._get_cached_memory_status()
        if memory_status['pressure_level'] in ['high', 'critical']:
            if self._verbose_logging:
                print(f"[快速渲染] 内存压力较高: {memory_status['pressure_level']}，执行优化")
            self.memory_manager.force_optimization()
        
        # 检查文档是否需要强制刷新缓存
        if hasattr(document, '_needs_cache_refresh') and document._needs_cache_refresh:
            force_refresh = True
            if self._verbose_logging:
                print(f"[快速渲染] 文档标记需要缓存刷新，强制重新渲染")

        # 检查智能缓存
        if not force_refresh:
            cached = self.intelligent_cache.get(document, quality_level=quality_level)
            if cached:
                log_branch("fast_renderer.render_preview", "cache_hit")
                if self._verbose_logging:
                    print(f"[快速渲染] 使用智能缓存预览")
                return cached

        if self._verbose_logging:
            print(f"[快速渲染] 重新渲染预览，强制刷新: {force_refresh}")

        # 记录渲染开始时间
        start_time = time.time()

        try:
            # 使用快速设置渲染
            composition = self._fast_render(
                document,
                preview_mode=True,
                low_quality_preview=interactive_low_quality
            )
            log_branch("fast_renderer.render_preview", "fast_render_preview")

            if composition:
                # 注册图像进行内存追踪
                register_image_for_tracking(composition, f"preview_{document.canvas_width}x{document.canvas_height}")
                
                # 计算渲染时间
                render_time = time.time() - start_time
                
                # 存入智能缓存
                self.intelligent_cache.put(document, composition, render_time, quality_level=quality_level)

                # 清除文档的缓存刷新标记
                if hasattr(document, '_needs_cache_refresh'):
                    document._needs_cache_refresh = False

                # 记录渲染时间
                self._last_render_time['preview'] = render_time
                self._last_preview_snapshot = composition.copy()

                if self._verbose_logging:
                    print(f"[快速渲染] 预览渲染完成，耗时: {render_time:.3f}秒")

            return composition

        except Exception as e:
            log_branch("fast_renderer.render_preview", "fallback_document_render", error=str(e))
            if self._verbose_logging:
                print(f"[快速渲染] 预览渲染失败: {e}")
            # 回退到标准渲染
            return document.render_composition()

    def render_preview_incremental(
        self,
        document,
        active_layer_index: int,
        force_refresh: bool = False,
        interactive_low_quality: bool = True
    ) -> Optional[Image.Image]:
        """交互期增量预览：复用静态底图，仅重算当前操作图层并合成。"""
        try:
            if active_layer_index < 0 or active_layer_index >= len(document.layers):
                return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)

            active_layer = document.layers[active_layer_index]
            if active_layer is None or not getattr(active_layer, 'visible', True):
                return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)

            base = self._get_or_build_interaction_base(
                document=document,
                active_layer_index=active_layer_index,
                force_refresh=force_refresh,
                interactive_low_quality=interactive_low_quality
            )
            if base is None:
                return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)

            composition = base.copy()
            if interactive_low_quality:
                layer_image = self._get_layer_surface_interactive_cached(
                    active_layer,
                    document,
                    was_just_loaded=False
                )
            else:
                layer_image = self._get_layer_surface_cached(active_layer, document, was_just_loaded=False)
            if layer_image is None:
                return composition

            opacity = getattr(active_layer, 'opacity', 1.0)
            blend_mode = self._get_layer_blend_mode(active_layer)
            positions_info, mirror_mode = self._get_layer_positions_info_cached(active_layer, document)

            from PIL import ImageOps
            mirrored_h = ImageOps.mirror(layer_image) if mirror_mode == 'horizontal' else None
            mirrored_v = ImageOps.flip(layer_image) if mirror_mode == 'vertical' else None
            for pos_x, pos_y, is_mirror in positions_info:
                if is_mirror and mirror_mode == 'horizontal':
                    img_for_pos = mirrored_h if mirrored_h is not None else layer_image
                elif is_mirror and mirror_mode == 'vertical':
                    img_for_pos = mirrored_v if mirrored_v is not None else layer_image
                else:
                    img_for_pos = layer_image
                draw_x = int(pos_x) + int(getattr(active_layer, '_render_offset_x', 0))
                draw_y = int(pos_y) + int(getattr(active_layer, '_render_offset_y', 0))
                composition = self._fast_composite(
                    composition,
                    img_for_pos,
                    draw_x,
                    draw_y,
                    opacity,
                    preview_mode=True,
                    blend_mode=blend_mode,
                    low_quality_preview=interactive_low_quality
                )
            return composition
        except Exception as e:
            print(f"[快速渲染] 增量预览失败，回退普通预览: {e}")
            return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)
    
    def render_batch(self, document) -> Optional[Image.Image]:
        """批量渲染 - 导出优先保证混合模式与结果正确性"""
        start_time = time.time()

        try:
            # 🔧 关键修复：批量导出使用与预览完全相同的渲染方式和参数
            if _BATCH_RENDER_VERBOSE:
                print(f"[批量渲染] 使用与预览一致的快速渲染方案")
                print(f"[批量渲染] 文档信息: 画布={document.canvas_width}x{document.canvas_height}, 图层数={len(document.layers)}")
                from app.utils.layer_tree import is_layer_group, is_effectively_visible
                visible_layers = [
                    layer for layer in document.layers
                    if layer is not None and not is_layer_group(layer) and is_effectively_visible(layer, document.layers)
                ]
                print(f"[批量渲染] 可见图层数: {len(visible_layers)}")
                for i, layer in enumerate(visible_layers):
                    print(f"[批量渲染] 图层{i+1}: {layer.name}, 位置=({layer.x}, {layer.y}), 尺寸={layer.width}x{layer.height}")

            # 导出路径使用非预览模式，避免在回退逻辑中走简化混合分支导致混合模式失效
            composition = self._fast_render(document, preview_mode=False, was_just_loaded=False)

            if composition:
                render_time = time.time() - start_time
                self._last_render_time['batch'] = render_time
                if _BATCH_RENDER_VERBOSE:
                    print(f"[批量渲染] 渲染成功: {composition.size}, 模式={composition.mode}")
                if _BATCH_RENDER_VERBOSE and render_time > 0.1:  # 超过100ms记录
                    print(f"[批量渲染] 批量渲染耗时: {render_time:.3f}秒")
            else:
                if _BATCH_RENDER_VERBOSE:
                    print(f"[批量渲染] _fast_render 返回 None")

            return composition

        except Exception as e:
            print(f"[批量渲染] 批量渲染失败: {e}")
            import traceback
            traceback.print_exc()

            # 回退到最简单的渲染方案
            try:
                if _BATCH_RENDER_VERBOSE:
                    print(f"[批量渲染] 尝试简化渲染方案")
                return self._simple_fallback_render(document)
            except Exception as fallback_e:
                print(f"[批量渲染] 简化渲染也失败: {fallback_e}")
                return None
    
    def _fast_render(
        self,
        document,
        preview_mode: bool = True,
        was_just_loaded: bool = False,
        low_quality_preview: bool = False,
        skip_layer_index: int = -1
    ) -> Optional[Image.Image]:
        """快速渲染实现"""
        # 创建画布
        composition = Image.new('RGBA', (document.canvas_width, document.canvas_height), (0, 0, 0, 0))
        export_trace_enabled = bool(getattr(document, '_export_debug_trace_enabled', False))
        export_trace_task = str(getattr(document, '_export_debug_trace_task', '') or '')
        export_trace_layer_paths = getattr(document, '_export_debug_trace_layer_paths', {}) or {}
        export_trace_file = str(getattr(document, '_export_debug_trace_file', '') or '')

        def _emit_export_trace(message: str):
            line = f"[导出调试] {str(message)}"
            try:
                builtins.print(line)
            except Exception:
                pass
            if export_trace_file:
                try:
                    with open(export_trace_file, 'a', encoding='utf-8') as f:
                        f.write(line + "\n")
                except Exception:
                    pass
        
        # 获取可见图层
        try:
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            visible_layers = []
            for idx, layer in enumerate(document.layers):
                if idx == skip_layer_index or layer is None or is_layer_group(layer):
                    continue
                if is_effectively_visible(layer, document.layers):
                    visible_layers.append(layer)
        except Exception:
            visible_layers = []
            for idx, layer in enumerate(document.layers):
                if idx == skip_layer_index:
                    continue
                if layer is not None and getattr(layer, 'visible', True):
                    visible_layers.append(layer)
        if not visible_layers:
            return composition

        size_match_overrides = self._build_size_match_overrides(
            document=document,
            visible_layers=visible_layers,
            was_just_loaded=was_just_loaded
        )
        
        # 渲染每个图层
        for layer in visible_layers:
            # 获取图层属性
            opacity = getattr(layer, 'opacity', 1.0)
            blend_mode = self._get_layer_blend_mode(layer)

            layer_override = size_match_overrides.get(id(layer))
            if layer_override and (not bool(layer_override.get('visible', True))):
                # 一对多自动识别孔位数：多余填充层自动隐藏，不参与本次渲染
                if export_trace_enabled:
                    layer_path = str(export_trace_layer_paths.get(id(layer), '') or '')
                    if not layer_path:
                        layer_path = str(getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '') or getattr(layer, 'image_source', '') or '')
                    _emit_export_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"路径={layer_path} 命中override=True 可见=False"
                    )
                continue
            if layer_override and (not all(k in layer_override for k in ('x', 'y', 'width', 'height'))):
                # 仅包含可见性控制等部分信息时，回退默认渲染路径
                layer_override = None
            if export_trace_enabled:
                layer_path = str(export_trace_layer_paths.get(id(layer), '') or '')
                if not layer_path:
                    layer_path = str(getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '') or getattr(layer, 'image_source', '') or '')
                _emit_export_trace(
                    f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                    f"路径={layer_path} 命中override={bool(layer_override)}"
                )
            if layer_override:
                target_x = int(layer_override['x'])
                target_y = int(layer_override['y'])
                target_w = max(1, int(layer_override['width']))
                target_h = max(1, int(layer_override['height']))
                if export_trace_enabled:
                    _emit_export_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"匹配矩形=({target_x},{target_y},{target_w},{target_h}) "
                        f"匹配旋转={layer_override.get('rotation')}"
                    )
                # 关键修复：匹配模式下按目标尺寸直接重取源图，避免“已处理图再二次缩放”导致发糊
                layer_image = self._get_layer_surface_for_size(
                    layer=layer,
                    document=document,
                    target_w=target_w,
                    target_h=target_h,
                    was_just_loaded=was_just_loaded,
                    rotation_override=layer_override.get('rotation')
                )
                if layer_image is None:
                    continue
                positions_info = [(target_x, target_y, False)]
                mirror_mode = 'none'
            else:
                layer_image = self._get_layer_surface_cached(layer, document, was_just_loaded)
                if layer_image is None:
                    continue
                positions_info, mirror_mode = self._get_layer_positions_info_cached(layer, document)
            from PIL import ImageOps
            mirrored_h = ImageOps.mirror(layer_image) if mirror_mode == 'horizontal' else None
            mirrored_v = ImageOps.flip(layer_image) if mirror_mode == 'vertical' else None
            for pos_x, pos_y, is_mirror in positions_info:
                if is_mirror and mirror_mode == 'horizontal':
                    img_for_pos = mirrored_h if mirrored_h is not None else layer_image
                elif is_mirror and mirror_mode == 'vertical':
                    img_for_pos = mirrored_v if mirrored_v is not None else layer_image
                else:
                    img_for_pos = layer_image
                draw_x = int(pos_x) + int(getattr(layer, '_render_offset_x', 0))
                draw_y = int(pos_y) + int(getattr(layer, '_render_offset_y', 0))
                composition = self._fast_composite(
                    composition,
                    img_for_pos,
                    draw_x,
                    draw_y,
                    opacity,
                    preview_mode,
                    blend_mode,
                    low_quality_preview=low_quality_preview
                )
        
        return composition

    def _get_layer_surface_for_size(
        self,
        layer,
        document,
        target_w: int,
        target_h: int,
        was_just_loaded: bool = False,
        rotation_override: Optional[float] = None
    ) -> Optional[Image.Image]:
        """按指定尺寸重新生成图层 surface（避免二次缩放引起模糊）。"""
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        try:
            base_surface_key = self._build_layer_surface_key(layer, document, was_just_loaded)
        except Exception:
            base_surface_key = f"fallback_{id(layer)}"
        rot_key = "none" if rotation_override is None else f"{float(rotation_override):.4f}"
        override_cache_key = f"{id(document)}:{id(layer)}:{base_surface_key}:size:{target_w}x{target_h}:rot:{rot_key}"

        with self._size_override_surface_lock:
            cached = self._size_override_surface_cache.get(override_cache_key)
            if cached is not None:
                self._size_override_surface_cache.move_to_end(override_cache_key)
                if isinstance(cached, dict):
                    img = cached.get("image")
                    setattr(layer, "_render_offset_x", int(cached.get("offset_x", 0)))
                    setattr(layer, "_render_offset_y", int(cached.get("offset_y", 0)))
                    return img.copy() if img is not None else None
                # 兼容历史缓存结构（仅图片）
                setattr(layer, "_render_offset_x", 0)
                setattr(layer, "_render_offset_y", 0)
                return cached.copy()

        # 文字图层不走此路径
        if hasattr(layer, 'get_text_lines'):
            return self._get_layer_surface_cached(layer, document, was_just_loaded)

        # 优先从当前文件路径直接加载并按目标尺寸处理
        current_image_path = None
        if hasattr(layer, '_current_image_path') and getattr(layer, '_current_image_path', None):
            current_image_path = layer._current_image_path
        elif hasattr(layer, 'current_image_path'):
            try:
                current_image_path = layer.current_image_path
            except Exception:
                current_image_path = None

        if not current_image_path or (not os.path.isfile(current_image_path)):
            # 无有效路径时回退旧逻辑
            fallback = self._get_layer_surface_cached(layer, document, was_just_loaded)
            if fallback is not None:
                # 导出与预览统一：回退分支也必须先裁透明边再覆盖缩放，避免留白
                fallback = self._resize_cover_from_content(fallback, target_w, target_h)
            return fallback

        original_w = int(getattr(layer, 'width', target_w) or target_w)
        original_h = int(getattr(layer, 'height', target_h) or target_h)
        original_rotation = float(getattr(layer, 'rotation', 0.0) or 0.0) if hasattr(layer, 'rotation') else 0.0
        layer_image = None

        try:
            # 临时替换尺寸，仅用于本次重取图像，随后恢复
            if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                props = layer._property_manager._properties
                if 'width' in props and 'height' in props:
                    props['width']['value'] = target_w
                    props['height']['value'] = target_h
            elif hasattr(layer, '_width') and hasattr(layer, '_height'):
                layer._width = target_w
                layer._height = target_h
            else:
                # 最后兜底：可能触发信号，但确保功能可用
                try:
                    layer.width = target_w
                    layer.height = target_h
                except Exception:
                    pass

            if rotation_override is not None:
                try:
                    rot = float(rotation_override)
                except Exception:
                    rot = original_rotation
                if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                    props = layer._property_manager._properties
                    if 'rotation' in props:
                        props['rotation']['value'] = rot
                elif hasattr(layer, '_rotation'):
                    layer._rotation = rot
                else:
                    try:
                        layer.rotation = rot
                    except Exception:
                        pass

            raw_image = self._get_layer_image(layer, document, was_just_loaded)
            if raw_image is None:
                return None
            if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
                raw_image = layer.apply_effects(raw_image)
            layer_image = raw_image
        finally:
            # 恢复原尺寸，避免污染图层状态
            try:
                if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                    props = layer._property_manager._properties
                    if 'width' in props and 'height' in props:
                        props['width']['value'] = original_w
                        props['height']['value'] = original_h
                elif hasattr(layer, '_width') and hasattr(layer, '_height'):
                    layer._width = original_w
                    layer._height = original_h
                else:
                    try:
                        layer.width = original_w
                        layer.height = original_h
                    except Exception:
                        pass

                if rotation_override is not None:
                    if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                        props = layer._property_manager._properties
                        if 'rotation' in props:
                            props['rotation']['value'] = original_rotation
                    elif hasattr(layer, '_rotation'):
                        layer._rotation = original_rotation
                    else:
                        try:
                            layer.rotation = original_rotation
                        except Exception:
                            pass
            except Exception:
                pass

        if layer_image is not None:
            # 关键修复：先裁掉透明边再覆盖缩放，避免匹配后留白
            layer_image = self._resize_cover_from_content(layer_image, target_w, target_h)
        if layer_image is not None:
            with self._size_override_surface_lock:
                self._size_override_surface_cache[override_cache_key] = {
                    "image": layer_image.copy(),
                    "offset_x": int(getattr(layer, "_render_offset_x", 0)),
                    "offset_y": int(getattr(layer, "_render_offset_y", 0)),
                }
                self._size_override_surface_cache.move_to_end(override_cache_key)
                while len(self._size_override_surface_cache) > self._max_size_override_surface_entries:
                    self._size_override_surface_cache.popitem(last=False)
        return layer_image

    def _resize_cover_keep_ratio(self, image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """
        等比覆盖缩放：保持比例，不拉伸，必要时中心裁剪以填满目标区域。
        """
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        src_w, src_h = image.size
        if src_w <= 0 or src_h <= 0:
            return image
        if src_w == target_w and src_h == target_h:
            return image

        scale = max(target_w / src_w, target_h / src_h)
        resized_w = max(1, int(round(src_w * scale)))
        resized_h = max(1, int(round(src_h * scale)))
        try:
            resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)
        except Exception:
            resized = image.resize((resized_w, resized_h))

        left = max(0, (resized_w - target_w) // 2)
        top = max(0, (resized_h - target_h) // 2)
        right = min(resized_w, left + target_w)
        bottom = min(resized_h, top + target_h)
        cropped = resized.crop((left, top, right, bottom))
        if cropped.size != (target_w, target_h):
            try:
                cropped = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            except Exception:
                cropped = cropped.resize((target_w, target_h))
        return cropped

    def _crop_nontransparent_bbox(self, image: Image.Image) -> Image.Image:
        """裁掉图像四周透明边，避免匹配后留白。"""
        try:
            rgba = image if image.mode == 'RGBA' else image.convert('RGBA')
            alpha = np.array(rgba.split()[3])
            ys, xs = np.where(alpha > 0)
            if xs.size == 0 or ys.size == 0:
                return rgba
            left = int(xs.min())
            right = int(xs.max()) + 1
            top = int(ys.min())
            bottom = int(ys.max()) + 1
            if left <= 0 and top <= 0 and right >= rgba.width and bottom >= rgba.height:
                return rgba
            cropped = rgba.crop((left, top, right, bottom))
            return cropped if cropped.size[0] > 0 and cropped.size[1] > 0 else rgba
        except Exception:
            return image

    def _resize_cover_from_content(self, image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """先按非透明内容裁边，再等比覆盖缩放到目标尺寸。"""
        trimmed = self._crop_nontransparent_bbox(image)
        return self._resize_cover_keep_ratio(trimmed, target_w, target_h)

    def _normalize_angle_180(self, angle: float) -> float:
        """归一化角度到 (-180, 180]。"""
        a = float(angle)
        while a <= -180.0:
            a += 360.0
        while a > 180.0:
            a -= 360.0
        return a

    def _pick_min_delta_rotation(self, target_angle: float, reference_angle: float) -> float:
        """从等价角中选与参考角差值最小的角度，并将旋转差限制在 ±90°。"""
        ref = self._normalize_angle_180(reference_angle)
        candidates = []
        for k in (-2, -1, 0, 1, 2):
            candidates.append(float(target_angle) + 180.0 * float(k))
        best_delta = None
        best_abs = None
        for c in candidates:
            delta = self._normalize_angle_180(c - ref)
            # 矩形方向 180° 周期等价：优先把差值折叠到 [-90, 90]
            if delta > 90.0:
                delta -= 180.0
            elif delta < -90.0:
                delta += 180.0
            abs_delta = abs(delta)
            if best_delta is None or abs_delta < best_abs:
                best_delta = delta
                best_abs = abs_delta
        if best_delta is None:
            return self._normalize_angle_180(ref)
        return self._normalize_angle_180(ref + best_delta)

    def _to_small_tilt_by_axis(self, raw_angle_deg: float, bbox_w: int, bbox_h: int) -> float:
        """
        将主轴角度转换为“相对主方向的小倾角”。
        - 自动选择最接近的主方向基准轴（0° 水平 / 90° 垂直）
        - 若两者接近，使用 bbox 长宽作为稳定性兜底
        返回值限制在 [-90, 90]，并优先最小绝对值。
        """
        a = self._normalize_angle_180(raw_angle_deg)
        # 角度以 180° 为等价周期，先计算相对两条主轴的最小差值
        tilt_h = self._normalize_angle_180(a)
        if tilt_h > 90.0:
            tilt_h -= 180.0
        elif tilt_h < -90.0:
            tilt_h += 180.0

        tilt_v = self._normalize_angle_180(a - 90.0)
        if tilt_v > 90.0:
            tilt_v -= 180.0
        elif tilt_v < -90.0:
            tilt_v += 180.0

        abs_h = abs(float(tilt_h))
        abs_v = abs(float(tilt_v))

        # 两轴都接近时，使用 bbox 方向作为稳定兜底，避免角度在预览中抖动跳变
        if abs(abs_h - abs_v) <= 3.0:
            tilt = float(tilt_v if int(bbox_h) >= int(bbox_w) else tilt_h)
        else:
            tilt = float(tilt_h if abs_h <= abs_v else tilt_v)

        if tilt > 90.0:
            tilt -= 180.0
        elif tilt < -90.0:
            tilt += 180.0
        return float(tilt)

    def _estimate_oriented_size(
        self,
        points_xy,
        center_x: float,
        center_y: float,
        rotation_deg: float
    ) -> Tuple[int, int]:
        """
        在给定旋转角下估算连通域在局部坐标系中的宽高。
        说明：
        - rotation_deg 与图层 rotation 语义保持一致（顺时针为正）
        - 返回最小为 1x1，且做轻量边界余量，减少裁切
        """
        if not points_xy:
            return 1, 1
        theta = math.radians(float(rotation_deg))
        ux = math.cos(theta)
        uy = math.sin(theta)
        vx = -math.sin(theta)
        vy = math.cos(theta)

        min_u = None
        max_u = None
        min_v = None
        max_v = None

        for px, py in points_xy:
            dx = float(px) - float(center_x)
            dy = float(py) - float(center_y)
            pu = dx * ux + dy * uy
            pv = dx * vx + dy * vy
            if min_u is None or pu < min_u:
                min_u = pu
            if max_u is None or pu > max_u:
                max_u = pu
            if min_v is None or pv < min_v:
                min_v = pv
            if max_v is None or pv > max_v:
                max_v = pv

        if min_u is None or max_u is None or min_v is None or max_v is None:
            return 1, 1

        # +1 像素把离散点覆盖为像素区间；再加 1 像素冗余减少边缘抽样裁切
        ow = max(1, int(math.ceil((max_u - min_u) + 1.0)) + 1)
        oh = max(1, int(math.ceil((max_v - min_v) + 1.0)) + 1)
        return ow, oh

    def _oriented_bbox_metrics(self, points_xy, center_x: float, center_y: float, rotation_deg: float) -> Tuple[int, int, float]:
        """计算给定旋转角下的最小包围宽高与面积。"""
        ow, oh = self._estimate_oriented_size(points_xy, center_x, center_y, rotation_deg)
        return int(ow), int(oh), float(max(1, int(ow) * int(oh)))

    def _estimate_tilt_from_min_rect(
        self,
        points_xy,
        center_x: float,
        center_y: float,
        axis_w: int,
        axis_h: int,
        seed_angle_deg: float
    ) -> Tuple[float, int, int, float]:
        """
        基于“最小面积倾斜矩形 vs 轴对齐矩形”估计倾角。
        返回 (tilt_deg, oriented_w, oriented_h, area_gain)。
        """
        axis_area = float(max(1, int(axis_w) * int(axis_h)))
        best_angle = float(seed_angle_deg)
        best_w, best_h, best_area = self._oriented_bbox_metrics(points_xy, center_x, center_y, best_angle)

        # 分两轮搜索：粗搜 + 精搜（围绕最佳角）
        coarse_step = 3.0
        for i in range(-15, 16):
            a = float(seed_angle_deg) + float(i) * coarse_step
            w, h, area = self._oriented_bbox_metrics(points_xy, center_x, center_y, a)
            if area < best_area:
                best_angle, best_w, best_h, best_area = float(a), int(w), int(h), float(area)

        fine_step = 0.6
        for i in range(-12, 13):
            a = float(best_angle) + float(i) * fine_step
            w, h, area = self._oriented_bbox_metrics(points_xy, center_x, center_y, a)
            if area < best_area:
                best_angle, best_w, best_h, best_area = float(a), int(w), int(h), float(area)

        # 统一转换为相对主轴的小倾角（[-90, 90]）
        tilt = self._to_small_tilt_by_axis(best_angle, axis_w, axis_h)
        oriented_w, oriented_h, oriented_area = self._oriented_bbox_metrics(points_xy, center_x, center_y, tilt)
        area_gain = max(0.0, (axis_area - oriented_area) / axis_area)
        return float(tilt), int(oriented_w), int(oriented_h), float(area_gain)

    def _binary_dilate_3x3(self, mask: np.ndarray) -> np.ndarray:
        """3x3 膨胀（bool）。"""
        h, w = mask.shape
        padded = np.pad(mask, ((1, 1), (1, 1)), mode='constant', constant_values=False)
        out = np.zeros((h, w), dtype=bool)
        for dy in range(3):
            for dx in range(3):
                out |= padded[dy:dy + h, dx:dx + w]
        return out

    def _binary_erode_3x3(self, mask: np.ndarray) -> np.ndarray:
        """3x3 腐蚀（bool）。"""
        h, w = mask.shape
        padded = np.pad(mask, ((1, 1), (1, 1)), mode='constant', constant_values=False)
        out = np.ones((h, w), dtype=bool)
        for dy in range(3):
            for dx in range(3):
                out &= padded[dy:dy + h, dx:dx + w]
        return out

    def _close_opaque_mask(self, opaque: np.ndarray) -> np.ndarray:
        """对不透明区域做一次闭运算，封堵细小裂缝，减少孔位偶发漏检。"""
        return self._binary_erode_3x3(self._binary_dilate_3x3(opaque))

    def _classify_hole_shape(self, bbox_w: int, bbox_h: int) -> str:
        """按宽高比粗分类：square / horizontal_rect / vertical_rect。"""
        w = max(1.0, float(bbox_w))
        h = max(1.0, float(bbox_h))
        ratio = w / h
        if 0.85 <= ratio <= 1.18:
            return "square"
        return "horizontal_rect" if ratio > 1.0 else "vertical_rect"

    def _sort_holes_left_to_right_then_top_to_bottom(self, holes):
        """
        孔位排序规则（业务固定）：
        1) 先按“左到右”分列
        2) 列内按“上到下”
        """
        if not holes:
            return []
        widths = []
        for h in holes:
            try:
                l, t, r, b = h.get('bbox', (0, 0, 1, 1))
                widths.append(max(1, int(r - l)))
            except Exception:
                widths.append(1)
        median_w = float(np.median(np.asarray(widths, dtype=np.float32))) if widths else 1.0
        col_tol = max(8.0, median_w * 0.45)
        ordered = sorted(holes, key=lambda h: (float(h.get('center_x', 0.0)), float(h.get('center_y', 0.0))))
        cols = []
        for hole in ordered:
            cx = float(hole.get('center_x', 0.0))
            placed = False
            for col in cols:
                if abs(cx - col['anchor_x']) <= col_tol:
                    col['items'].append(hole)
                    col['anchor_x'] = (col['anchor_x'] * float(col['count']) + cx) / float(col['count'] + 1)
                    col['count'] += 1
                    placed = True
                    break
            if not placed:
                cols.append({'anchor_x': cx, 'count': 1, 'items': [hole]})
        cols.sort(key=lambda c: float(c['anchor_x']))
        flattened = []
        for col in cols:
            col_items = sorted(col['items'], key=lambda h: float(h.get('center_y', 0.0)))
            flattened.extend(col_items)
        return flattened

    def _sort_layers_left_to_right_then_top_to_bottom(self, layers):
        """目标图层排序：先左到右分列，再列内上到下。"""
        if not layers:
            return []
        widths = [max(1, int(getattr(l, 'width', 1) or 1)) for l in layers]
        median_w = float(np.median(np.asarray(widths, dtype=np.float32))) if widths else 1.0
        col_tol = max(8.0, median_w * 0.45)
        ordered = sorted(layers, key=lambda l: (float(getattr(l, 'x', 0.0)), float(getattr(l, 'y', 0.0))))
        cols = []
        for layer in ordered:
            cx = float(getattr(layer, 'x', 0.0))
            placed = False
            for col in cols:
                if abs(cx - col['anchor_x']) <= col_tol:
                    col['items'].append(layer)
                    col['anchor_x'] = (col['anchor_x'] * float(col['count']) + cx) / float(col['count'] + 1)
                    col['count'] += 1
                    placed = True
                    break
            if not placed:
                cols.append({'anchor_x': cx, 'count': 1, 'items': [layer]})
        cols.sort(key=lambda c: float(c['anchor_x']))
        flattened = []
        for col in cols:
            col_items = sorted(col['items'], key=lambda l: float(getattr(l, 'y', 0.0)))
            flattened.extend(col_items)
        return flattened

    def _ensure_rect_covers_hole_bbox(
        self,
        source_x: int,
        source_y: int,
        hole_bbox: Tuple[int, int, int, int],
        x: int,
        y: int,
        width: int,
        height: int,
        extra_margin: int = 0
    ) -> Tuple[int, int, int, int]:
        """
        兜底校验：确保填充矩形至少完整覆盖挖孔 bbox（含可选额外边距）。
        用于避免“已匹配但仍留透明区域”。
        """
        try:
            left, top, right, bottom = hole_bbox
            need_l = int(source_x + left - max(0, int(extra_margin)))
            need_t = int(source_y + top - max(0, int(extra_margin)))
            need_r = int(source_x + right + max(0, int(extra_margin)))
            need_b = int(source_y + bottom + max(0, int(extra_margin)))

            x0 = int(x)
            y0 = int(y)
            x1 = int(x0 + max(1, int(width)))
            y1 = int(y0 + max(1, int(height)))

            if x0 > need_l:
                x0 = need_l
            if y0 > need_t:
                y0 = need_t
            if x1 < need_r:
                x1 = need_r
            if y1 < need_b:
                y1 = need_b

            out_w = max(1, int(x1 - x0))
            out_h = max(1, int(y1 - y0))
            return int(x0), int(y0), int(out_w), int(out_h)
        except Exception:
            return int(x), int(y), max(1, int(width)), max(1, int(height))

    def _build_size_match_overrides(self, document, visible_layers, was_just_loaded: bool = False) -> Dict[int, Dict[str, Any]]:
        """根据图层大小匹配配置构建临时覆写，不修改原始图层参数。"""
        overrides: Dict[int, Dict[str, Any]] = {}
        export_trace_enabled = bool(getattr(document, '_export_debug_trace_enabled', False))
        export_trace_task = str(getattr(document, '_export_debug_trace_task', '') or '')
        export_trace_file = str(getattr(document, '_export_debug_trace_file', '') or '')

        def _emit_size_match_trace(message: str):
            if not export_trace_enabled:
                return
            line = f"[导出调试] {str(message)}"
            try:
                builtins.print(line)
            except Exception:
                pass
            if export_trace_file:
                try:
                    with open(export_trace_file, 'a', encoding='utf-8') as f:
                        f.write(line + "\n")
                except Exception:
                    pass

        manager = getattr(document, 'layer_size_match_manager', None)
        if not manager or not getattr(manager, 'global_enabled', False):
            _emit_size_match_trace(f"任务={export_trace_task} 图层匹配关闭或管理器不可用")
            return overrides

        try:
            active_relations = manager.get_active_relations() if hasattr(manager, 'get_active_relations') else []
        except Exception:
            active_relations = []
        if not active_relations:
            _emit_size_match_trace(f"任务={export_trace_task} 图层匹配无有效关系")
            return overrides

        layer_by_name = {}
        for layer in visible_layers:
            name = str(getattr(layer, 'name', '')).strip()
            if name and name not in layer_by_name:
                layer_by_name[name] = layer

        for relation in active_relations:
            source_name = str(relation.get('source_layer_name', '')).strip()
            source_layer = layer_by_name.get(source_name)
            if source_layer is None or hasattr(source_layer, 'get_text_lines'):
                _emit_size_match_trace(
                    f"任务={export_trace_task} 匹配关系跳过 source={source_name} 原因=source_missing_or_text"
                )
                continue

            holes = self._get_inner_holes_cached(source_layer, document, was_just_loaded)
            _emit_size_match_trace(
                f"任务={export_trace_task} 匹配关系 source={source_name} 孔位数量={len(holes)}"
            )

            source_w = int(getattr(source_layer, 'width', 1) or 1)
            source_h = int(getattr(source_layer, 'height', 1) or 1)

            target_names = relation.get('target_layer_names') or []
            if not isinstance(target_names, list) or not target_names:
                legacy_target = str(relation.get('target_layer_name', '')).strip()
                target_names = [legacy_target] if legacy_target else []
            targets = []
            for name in target_names:
                layer_obj = layer_by_name.get(str(name).strip())
                if layer_obj is None or hasattr(layer_obj, 'get_text_lines'):
                    continue
                targets.append(layer_obj)
            if not targets:
                _emit_size_match_trace(
                    f"任务={export_trace_task} 匹配关系 source={source_name} 原因=target_missing"
                )
                continue
            one_to_many = bool(relation.get('one_to_many', False))
            auto_rotate = bool(relation.get('auto_rotate', False))
            # 兼容旧数据：历史版本可能出现“多目标但one_to_many未开启”的关系。
            # 若仅按一对一处理会导致只有第一个目标层生效，其余图层位置/尺寸不匹配。
            effective_one_to_many = bool(one_to_many or len(targets) > 1)

            # 自动识别挖孔数量：一对多下，多余填充层自动隐藏
            if effective_one_to_many and (not holes):
                for target_layer in targets:
                    overrides[id(target_layer)] = {'visible': False}
                    _emit_size_match_trace(
                        f"任务={export_trace_task} source={source_name} target={getattr(target_layer, 'name', '')} "
                        f"孔位为空 -> hide"
                    )
                continue
            if not holes:
                _emit_size_match_trace(f"任务={export_trace_task} source={source_name} 孔位为空 -> 跳过")
                continue

            positions_info, _ = self._get_layer_positions_info_cached(source_layer, document)
            if not positions_info:
                continue
            source_x, source_y, _ = positions_info[0]
            padding = max(0, int(relation.get('padding', 1)))

            # 阶段1：只负责“目标图层 <-> 挖孔”配对，不参与任何角度计算
            if effective_one_to_many:
                # 过滤噪点内孔，优先选面积较大的有效孔，再按方向排序配对
                source_area = max(1, source_w * source_h)
                min_area = max(64, int(source_area * 0.0004))
                significant = [h for h in holes if int(h.get('area', 0)) >= min_area]
                if len(significant) < len(targets):
                    # 降低阈值重试，避免合法小孔被误滤掉导致“某一孔偶发不填充”
                    min_area_soft = max(16, int(source_area * 0.00008))
                    significant = [h for h in holes if int(h.get('area', 0)) >= min_area_soft]
                if len(significant) < len(targets):
                    # 仍不足时使用全部孔位，优先保证“识别出的孔位完整参与”
                    significant = list(holes)
                ordered_holes = self._sort_holes_left_to_right_then_top_to_bottom(significant)
                targets = self._sort_layers_left_to_right_then_top_to_bottom(targets)
                target_count = len(targets)
                hole_count = len(ordered_holes)
                pair_plan = []
                if hole_count <= 0:
                    pair_plan = []
                elif hole_count >= target_count:
                    # 孔位充足：按顺序一一配对
                    pair_plan = [(targets[i], ordered_holes[i]) for i in range(target_count)]
                else:
                    # 孔位不足：优先保证全部目标层有匹配，避免“一对多只生效第一个”
                    # 采用均匀复用映射，保持空间顺序语义
                    if target_count <= 1:
                        pair_plan = [(targets[0], ordered_holes[0])]
                    elif hole_count == 1:
                        pair_plan = [(t, ordered_holes[0]) for t in targets]
                    else:
                        for i, target_layer in enumerate(targets):
                            mapped = int(round((float(i) * float(hole_count - 1)) / float(target_count - 1)))
                            hole_idx = max(0, min(hole_count - 1, mapped))
                            pair_plan.append((target_layer, ordered_holes[hole_idx]))
            else:
                ordered_holes = self._sort_holes_left_to_right_then_top_to_bottom(holes)
                pair_plan = [(targets[0], ordered_holes[0])]

            # 阶段2：基于已完成配对的结果，逐孔计算旋转与尺寸
            for target_layer, hole in pair_plan:
                left, top, right, bottom = hole['bbox']
                rotation = None
                # 自动倾斜与一对多完全解耦：只要该孔角度可信，就独立应用其角度
                if auto_rotate and bool(hole.get('angle_valid', False)):
                    raw_angle = float(hole.get('angle_deg', 0.0))
                    base_rotation = float(getattr(target_layer, 'rotation', 0.0) or 0.0)
                    candidate_rotation = self._pick_min_delta_rotation(raw_angle, base_rotation)
                    delta_rotation = self._normalize_angle_180(candidate_rotation - base_rotation)
                    if abs(float(delta_rotation)) >= float(_AUTO_ROTATE_MIN_DEG):
                        rotation = candidate_rotation

                if auto_rotate and rotation is not None:
                    # 旋转匹配路径：使用孔中心 + 局部坐标系尺寸，避免按轴对齐 bbox 导致偏大/偏移
                    cx = float(hole.get('bbox_center_x', (left + right) * 0.5))
                    cy = float(hole.get('bbox_center_y', (top + bottom) * 0.5))
                    ow = int(hole.get('oriented_w', max(1, int(right - left))))
                    oh = int(hole.get('oriented_h', max(1, int(bottom - top))))
                    # 旋转时保守外扩 + 覆盖校验兜底，避免过度放大又防止留白
                    safety_expand = max(3, int(round(min(ow, oh) * 0.018)))
                    width = max(1, int(ow + padding * 2 + safety_expand * 2))
                    height = max(1, int(oh + padding * 2 + safety_expand * 2))
                    x = int(round(source_x + cx - (width * 0.5)))
                    y = int(round(source_y + cy - (height * 0.5)))
                else:
                    # 非旋转路径保持原逻辑，保证旧模板行为稳定
                    bw = max(1, int(right - left))
                    bh = max(1, int(bottom - top))
                    # 优先完整填充：非旋转路径也增加轻量外扩，避免留白/细缝
                    safety_expand = max(1, int(round(min(bw, bh) * 0.01)))
                    x = int(source_x + left - padding - safety_expand)
                    y = int(source_y + top - padding - safety_expand)
                    width = max(1, int(bw + padding * 2 + safety_expand * 2))
                    height = max(1, int(bh + padding * 2 + safety_expand * 2))

                # 透明检查兜底（几何版）：强制覆盖挖孔 bbox，避免残留透明
                x, y, width, height = self._ensure_rect_covers_hole_bbox(
                    source_x=source_x,
                    source_y=source_y,
                    hole_bbox=(left, top, right, bottom),
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    extra_margin=max(0, int(padding + (2 if (auto_rotate and rotation is not None) else 0)))
                )

                # 倾斜后保底：围绕中心轻量二次放大，消除极端模板边缘残留透明
                if auto_rotate and rotation is not None:
                    cx_box = float(x) + float(width) * 0.5
                    cy_box = float(y) + float(height) * 0.5
                    grow_scale = 1.05
                    width = max(1, int(math.ceil(float(width) * grow_scale)) + 2)
                    height = max(1, int(math.ceil(float(height) * grow_scale)) + 2)
                    x = int(round(cx_box - float(width) * 0.5))
                    y = int(round(cy_box - float(height) * 0.5))
                # 最终兜底外扩：优先保证“不留白”，允许轻微重叠
                final_guard = max(2, int(round(min(width, height) * 0.012)))
                if auto_rotate and rotation is not None:
                    final_guard += 2
                elif effective_one_to_many:
                    final_guard += 1
                if final_guard > 0:
                    cx_box = float(x) + float(width) * 0.5
                    cy_box = float(y) + float(height) * 0.5
                    width = max(1, int(width + final_guard * 2))
                    height = max(1, int(height + final_guard * 2))
                    x = int(round(cx_box - float(width) * 0.5))
                    y = int(round(cy_box - float(height) * 0.5))

                overrides[id(target_layer)] = {
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height,
                    'rotation': rotation,
                }
                _emit_size_match_trace(
                    f"任务={export_trace_task} source={source_name} target={getattr(target_layer, 'name', '')} "
                    f"孔位bbox=({left},{top},{right},{bottom}) 最终匹配矩形=({x},{y},{width},{height}) "
                    f"旋转={rotation}"
                )

        return overrides

    def _detect_inner_holes(self, image: Image.Image, alpha_threshold: int = 6):
        """检测所有内孔并返回边界、面积与角度信息。"""
        try:
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            alpha = np.array(image.split()[3])
            if alpha.size == 0:
                return []

            transparent = alpha <= int(alpha_threshold)
            if not transparent.any():
                return []

            # 修复偶发漏检：若边框存在极细裂缝，外部背景会“漏进”内孔导致孔丢失
            # 先对不透明区域做轻量闭运算，再反推透明区域，可显著提升稳定性。
            try:
                opaque = alpha > int(alpha_threshold)
                if opaque.any():
                    opaque = self._close_opaque_mask(opaque)
                    transparent = ~opaque
            except Exception:
                pass

            h, w = transparent.shape
            background = np.zeros_like(transparent, dtype=bool)
            q = deque()

            for x in range(w):
                if transparent[0, x]:
                    background[0, x] = True
                    q.append((0, x))
                if transparent[h - 1, x] and not background[h - 1, x]:
                    background[h - 1, x] = True
                    q.append((h - 1, x))
            for y in range(h):
                if transparent[y, 0] and not background[y, 0]:
                    background[y, 0] = True
                    q.append((y, 0))
                if transparent[y, w - 1] and not background[y, w - 1]:
                    background[y, w - 1] = True
                    q.append((y, w - 1))

            while q:
                cy, cx = q.popleft()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if ny < 0 or ny >= h or nx < 0 or nx >= w:
                        continue
                    if background[ny, nx] or (not transparent[ny, nx]):
                        continue
                    background[ny, nx] = True
                    q.append((ny, nx))

            holes = transparent & (~background)
            if not holes.any():
                return []

            visited = np.zeros_like(holes, dtype=bool)
            result = []
            ys, xs = np.where(holes)
            for y0, x0 in zip(ys, xs):
                if visited[y0, x0]:
                    continue
                q = deque([(y0, x0)])
                visited[y0, x0] = True
                area = 0
                min_x = max_x = x0
                min_y = max_y = y0
                points_xy = []

                while q:
                    cy, cx = q.popleft()
                    area += 1
                    points_xy.append((cx, cy))
                    if cx < min_x:
                        min_x = cx
                    if cx > max_x:
                        max_x = cx
                    if cy < min_y:
                        min_y = cy
                    if cy > max_y:
                        max_y = cy
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if ny < 0 or ny >= h or nx < 0 or nx >= w:
                            continue
                        if visited[ny, nx] or (not holes[ny, nx]):
                            continue
                        visited[ny, nx] = True
                        q.append((ny, nx))

                bw = max_x - min_x + 1
                bh = max_y - min_y + 1
                bbox_area = max(1, bw * bh)
                fill_ratio = float(area) / float(bbox_area)
                rect_like = (fill_ratio >= 0.55 and area >= 30 and bw >= 8 and bh >= 8)
                angle_deg = 0.0
                angle_valid = False
                oriented_w = max(1, int(bw))
                oriented_h = max(1, int(bh))
                center_x = float((min_x + max_x) / 2.0)
                center_y = float((min_y + max_y) / 2.0)
                bbox_center_x = float((min_x + max_x) / 2.0)
                bbox_center_y = float((min_y + max_y) / 2.0)
                if area >= 20 and bw >= 6 and bh >= 6:
                    arr = np.asarray(points_xy, dtype=np.float32)
                    mx = float(np.mean(arr[:, 0]))
                    my = float(np.mean(arr[:, 1]))
                    center_x = float(mx)
                    center_y = float(my)
                    dx = arr[:, 0] - mx
                    dy = arr[:, 1] - my
                    cov_xx = float(np.mean(dx * dx))
                    cov_yy = float(np.mean(dy * dy))
                    cov_xy = float(np.mean(dx * dy))
                    area_anisotropy = abs(cov_xx - cov_yy) / max(1e-6, (cov_xx + cov_yy))
                    area_raw_angle = math.degrees(0.5 * math.atan2(2.0 * cov_xy, cov_xx - cov_yy))

                    # 边界主轴通常比区域主轴更贴近“孔框方向”，可提升倾角稳定性
                    boundary_points = []
                    for px, py in points_xy:
                        if (
                            px <= 0 or py <= 0 or px >= (w - 1) or py >= (h - 1)
                            or (not holes[py - 1, px]) or (not holes[py + 1, px])
                            or (not holes[py, px - 1]) or (not holes[py, px + 1])
                        ):
                            boundary_points.append((px, py))
                    boundary_anisotropy = 0.0
                    boundary_raw_angle = area_raw_angle
                    if len(boundary_points) >= 16:
                        barr = np.asarray(boundary_points, dtype=np.float32)
                        bmx = float(np.mean(barr[:, 0]))
                        bmy = float(np.mean(barr[:, 1]))
                        bdx = barr[:, 0] - bmx
                        bdy = barr[:, 1] - bmy
                        bcov_xx = float(np.mean(bdx * bdx))
                        bcov_yy = float(np.mean(bdy * bdy))
                        bcov_xy = float(np.mean(bdx * bdy))
                        boundary_anisotropy = abs(bcov_xx - bcov_yy) / max(1e-6, (bcov_xx + bcov_yy))
                        boundary_raw_angle = math.degrees(0.5 * math.atan2(2.0 * bcov_xy, bcov_xx - bcov_yy))

                    aspect = max(float(bw), float(bh)) / max(1.0, min(float(bw), float(bh)))
                    use_boundary = bool(boundary_anisotropy >= area_anisotropy * 0.92 and len(boundary_points) >= 16)
                    chosen_raw_angle = boundary_raw_angle if use_boundary else area_raw_angle
                    chosen_anisotropy = max(area_anisotropy, boundary_anisotropy)
                    angle_deg, est_w, est_h, area_gain = self._estimate_tilt_from_min_rect(
                        points_xy=points_xy,
                        center_x=center_x,
                        center_y=center_y,
                        axis_w=bw,
                        axis_h=bh,
                        seed_angle_deg=chosen_raw_angle
                    )

                    # 近似正方形且各向异性弱时，不做自动倾斜，避免误判
                    if aspect < 1.10 and chosen_anisotropy < 0.028:
                        angle_deg = 0.0
                        angle_valid = False
                    else:
                        # 防误判：
                        # 1) 小角度死区（<4°）视为不倾斜
                        # 2) 旋转收益很小（局部包围面积改善不足）也视为不倾斜
                        if abs(float(angle_deg)) < float(_AUTO_ROTATE_MIN_DEG) or area_gain < 0.015:
                            angle_deg = 0.0
                            angle_valid = False
                        else:
                            angle_valid = True
                            oriented_w = int(est_w)
                            oriented_h = int(est_h)

                result.append({
                    'bbox': (min_x, min_y, max_x + 1, max_y + 1),
                    'area': int(area),
                    'bbox_w': int(bw),
                    'bbox_h': int(bh),
                    'shape_type': self._classify_hole_shape(bw, bh),
                    'center_x': float(center_x),
                    'center_y': float(center_y),
                    'bbox_center_x': float(bbox_center_x),
                    'bbox_center_y': float(bbox_center_y),
                    'rect_like': bool(rect_like),
                    'angle_valid': bool(angle_valid),
                    'angle_deg': float(angle_deg),
                    'oriented_w': int(oriented_w),
                    'oriented_h': int(oriented_h),
                })

            return result
        except Exception:
            return []

    def _get_inner_holes_cached(self, source_layer, document, was_just_loaded: bool = False):
        """获取内孔检测结果缓存，降低预览时重复连通域分析开销。"""
        try:
            source_surface_key = self._build_layer_surface_key(source_layer, document, was_just_loaded)
        except Exception:
            source_surface_key = f"fallback_{id(source_layer)}"
        cache_key = f"{id(document)}:{id(source_layer)}:{source_surface_key}:{_SIZE_MATCH_HOLE_DETECT_VER}"

        with self._size_match_holes_lock:
            cached = self._size_match_holes_cache.get(cache_key)
            if cached is not None:
                self._size_match_holes_cache.move_to_end(cache_key)
                return [dict(h) for h in cached]

        source_image = self._get_layer_surface_cached(source_layer, document, was_just_loaded)
        if source_image is None:
            return []
        holes = self._detect_inner_holes(source_image)
        holes = self._refine_holes_with_adaptive_alpha_threshold(source_image, holes)

        with self._size_match_holes_lock:
            self._size_match_holes_cache[cache_key] = [dict(h) for h in holes]
            self._size_match_holes_cache.move_to_end(cache_key)
            while len(self._size_match_holes_cache) > self._max_size_match_holes_entries:
                self._size_match_holes_cache.popitem(last=False)
        return holes

    def _refine_holes_with_adaptive_alpha_threshold(self, source_image: Image.Image, holes):
        """
        对“半透明孔位”做自适应阈值回退，避免孔 bbox 被误识别成细条。
        场景：模板孔位存在羽化/半透明边缘，固定阈值(<=6)会低估孔尺寸。
        """
        try:
            if source_image is None:
                return holes or []
            source_w = int(getattr(source_image, 'width', 0) or 0)
            source_h = int(getattr(source_image, 'height', 0) or 0)
            source_area = max(1, source_w * source_h)

            base_holes = list(holes or [])
            base_total = int(sum(max(0, int(h.get('area', 0))) for h in base_holes))

            # 经验阈值：当已识别面积足够时，不做额外回退，避免无谓计算
            if base_holes and base_total >= int(source_area * 0.015):
                return base_holes

            best_holes = base_holes
            best_total = base_total
            # 从保守到激进逐步放宽透明阈值
            candidate_thresholds = (12, 20, 28, 36, 48, 64, 80, 96)

            for th in candidate_thresholds:
                candidate = self._detect_inner_holes(source_image, alpha_threshold=int(th))
                if not candidate:
                    continue
                total_area = int(sum(max(0, int(h.get('area', 0))) for h in candidate))
                if total_area <= best_total:
                    continue
                # 防止阈值过高把大块区域误识别为孔位
                if total_area >= int(source_area * 0.82):
                    continue
                max_area = max([int(h.get('area', 0)) for h in candidate] or [0])
                if max_area < int(source_area * 0.002):
                    continue
                best_holes = candidate
                best_total = total_area

            return best_holes
        except Exception:
            return holes or []

    def _build_layer_positions_key(self, layer, document) -> str:
        """构建图层位置缓存键（仅包含影响分身/填充位置的参数）"""
        try:
            parts = [
                f"doc:{id(document)}",
                f"layer:{id(layer)}",
                f"canvas:{document.canvas_width}x{document.canvas_height}",
                f"base:{getattr(layer, 'x', 0)},{getattr(layer, 'y', 0)}",
                f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
                f"clone:{int(bool(getattr(layer, 'clone_enabled', False)))}",
                f"fill:{int(bool(getattr(layer, 'clone_fill_enabled', False)))}",
                f"fill_spacing:{getattr(layer, 'clone_fill_spacing', 0)}",
                f"fill_angle:{float(getattr(layer, 'clone_fill_angle', 0.0)):.3f}",
                f"fill_mode:{getattr(layer, 'clone_fill_mode', 'grid')}",
                f"fill_margin:{getattr(layer, 'clone_fill_margin', 0)}",
                f"mirror:{getattr(layer, 'clone_mirror_mode', 'none')}",
                f"rnd_dx:{getattr(layer, '_current_random_offset_x', 0)}",
                f"rnd_dy:{getattr(layer, '_current_random_offset_y', 0)}",
                f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
                f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
            ]
            return hashlib.md5("|".join([str(p) for p in parts]).encode('utf-8')).hexdigest()
        except Exception:
            return f"fallback_layer_positions_{id(layer)}_{time.time()}"

    def _get_layer_positions_info_cached(self, layer, document):
        """获取图层位置缓存，必要时重新计算"""
        cache_key = self._build_layer_positions_key(layer, document)
        entry_key = f"{id(document)}:{id(layer)}"
        with self._layer_positions_lock:
            entry = self._layer_positions_cache.get(entry_key)
            if entry and entry.get("cache_key") == cache_key:
                self._layer_positions_cache.move_to_end(entry_key)
                positions_info = entry.get("positions_info", [])
                mirror_mode = entry.get("mirror_mode", "none")
                return positions_info[:], mirror_mode

        positions_info, mirror_mode = self._calculate_layer_positions_info(layer, document)
        with self._layer_positions_lock:
            self._layer_positions_cache[entry_key] = {
                "cache_key": cache_key,
                "positions_info": positions_info[:],
                "mirror_mode": mirror_mode
            }
            self._layer_positions_cache.move_to_end(entry_key)
            while len(self._layer_positions_cache) > self._max_layer_positions_entries:
                self._layer_positions_cache.popitem(last=False)
        return positions_info, mirror_mode

    def _calculate_layer_positions_info(self, layer, document):
        """计算图层分身/填充位置信息"""
        clone_positions = []
        is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled
        if is_clone_enabled and hasattr(layer, 'get_effective_clone_positions'):
            try:
                clone_positions = layer.get_effective_clone_positions()
            except Exception as e:
                print(f"[快速渲染] 获取分身位置失败: {e}")
                if hasattr(layer, 'get_effective_position'):
                    clone_positions = [layer.get_effective_position()]
                else:
                    clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]
        else:
            if hasattr(layer, 'get_effective_position'):
                clone_positions = [layer.get_effective_position()]
            else:
                clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]

        fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
        if fill_enabled:
            spacing = int(getattr(layer, 'clone_fill_spacing', 0))
            angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
            mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
            dx = max(1, int(getattr(layer, 'width', 0) + spacing))
            dy = max(1, int(getattr(layer, 'height', 0) + spacing))
            positions = []
            cx = document.canvas_width / 2.0
            cy = document.canvas_height / 2.0
            base_x = getattr(layer, 'x', 0)
            base_y = getattr(layer, 'y', 0)
            import math
            angle = math.radians(angle_deg % 360.0)
            start_y = -getattr(layer, 'height', 0)
            end_y = document.canvas_height + getattr(layer, 'height', 0)
            if mode == 'border':
                w = getattr(layer, 'width', 0)
                h = getattr(layer, 'height', 0)
                margin = int(getattr(layer, 'clone_fill_margin', 0))
                effective_width = document.canvas_width - 2 * margin
                effective_height = document.canvas_height - 2 * margin
                top_bottom_count = max(2, (effective_width + dx) // dx)
                left_right_count = max(2, (effective_height + dy) // dy)
                top_bottom_spacing = (effective_width - w) / (top_bottom_count - 1) if top_bottom_count > 1 else 0
                left_right_spacing = (effective_height - h) / (left_right_count - 1) if left_right_count > 1 else 0
                for i in range(top_bottom_count):
                    x = margin + int(i * top_bottom_spacing)
                    if x <= document.canvas_width - w - margin:
                        positions.append((x, margin))
                for i in range(top_bottom_count):
                    x = margin + int(i * top_bottom_spacing)
                    if x <= document.canvas_width - w - margin:
                        positions.append((x, document.canvas_height - h - margin))
                for i in range(1, left_right_count - 1):
                    y = margin + int(i * left_right_spacing)
                    if margin < y < document.canvas_height - h - margin:
                        positions.append((margin, y))
                for i in range(1, left_right_count - 1):
                    y = margin + int(i * left_right_spacing)
                    if margin < y < document.canvas_height - h - margin:
                        positions.append((document.canvas_width - w - margin, y))
            else:
                step_y = dy
                i_row = 0
                for row_y in range(start_y, end_y + 1, step_y):
                    offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                    for col_x in range(-getattr(layer, 'width', 0), document.canvas_width + getattr(layer, 'width', 0) + 1, dx):
                        x0 = base_x + col_x + offset
                        y0 = base_y + row_y
                        if angle != 0.0:
                            rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                            ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                            x = int(rx)
                            y = int(ry)
                        else:
                            x = x0
                            y = y0
                        positions.append((x, y))
                    i_row += 1
            clone_positions = positions if positions else clone_positions

        positions_info = [(x, y, False) for (x, y) in clone_positions]
        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
        if mirror_mode and mirror_mode != 'none':
            base = clone_positions[:]
            min_x = min([x for x, _ in base])
            max_x = max([x + layer.width for x, _ in base])
            min_y = min([y for _, y in base])
            max_y = max([y + layer.height for _, y in base])
            group_width = max_x - min_x
            group_height = max_y - min_y
            if mirror_mode == 'horizontal':
                mirrored_left = document.canvas_width - (min_x + group_width)
                for x, y in base:
                    offset_x = x - min_x
                    positions_info.append((mirrored_left + offset_x, y, True))
            elif mirror_mode == 'vertical':
                mirrored_top = document.canvas_height - (min_y + group_height)
                for x, y in base:
                    offset_y = y - min_y
                    positions_info.append((x, mirrored_top + offset_y, True))
        return positions_info, mirror_mode

    def _build_layer_surface_key(self, layer, document, was_just_loaded: bool = False) -> str:
        """构建图层surface缓存键（仅包含影响图层图像像素的参数）"""
        try:
            layer_parts = [
                "vec_pipe_ver:v4",
                f"src:{getattr(layer, 'image_source', '')}",
                f"current:{getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '')}",
                f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
                f"fit:{getattr(layer, 'fit_mode', 0)}",
                f"crop:{getattr(layer, 'crop_direction', 0)}",
                f"use_orig:{int(bool(getattr(layer, 'use_original_size', False)))}",
                f"flip_h:{int(bool(getattr(layer, 'flip_horizontal', False)))}",
                f"flip_v:{int(bool(getattr(layer, 'flip_vertical', False)))}",
                f"rot:{float(getattr(layer, 'rotation', 0.0)):.3f}",
                # 样式参数（关键：缺失会导致圆角/描边更新后仍命中旧缓存）
                f"corner:{int(getattr(layer, 'corner_radius', getattr(layer, '_corner_radius', 0)))}",
                f"stroke_on:{int(bool(getattr(layer, 'stroke_enabled', getattr(layer, '_stroke_enabled', False))))}",
                f"stroke_type:{int(getattr(layer, 'stroke_type', getattr(layer, '_stroke_type', 0)))}",
                f"stroke_w:{int(getattr(layer, 'stroke_width', getattr(layer, '_stroke_width', 0)))}",
                f"stroke_c:{str(getattr(layer, 'stroke_color', getattr(layer, '_stroke_color', (0, 0, 0, 255))))}",
                f"overlay_on:{int(bool(getattr(layer, 'color_overlay_enabled', getattr(layer, '_color_overlay_enabled', False))))}",
                f"overlay_c:{str(getattr(layer, 'color_overlay_color', getattr(layer, '_color_overlay_color', (255, 255, 255, 255))))}",
                f"overlay_op:{float(getattr(layer, 'color_overlay_opacity', getattr(layer, '_color_overlay_opacity', 1.0))):.4f}",
                f"grad_on:{int(bool(getattr(layer, 'gradient_overlay_enabled', getattr(layer, '_gradient_overlay_enabled', False))))}",
                f"grad_angle:{float(getattr(layer, 'gradient_overlay_angle', getattr(layer, '_gradient_overlay_angle', 0.0))):.3f}",
                f"grad_op:{float(getattr(layer, 'gradient_overlay_opacity', getattr(layer, '_gradient_overlay_opacity', 1.0))):.4f}",
                f"rnd_dx:{getattr(layer, '_current_random_offset_x', 0)}",
                f"rnd_dy:{getattr(layer, '_current_random_offset_y', 0)}",
                f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
                f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
                f"text:{hashlib.md5(str(getattr(layer, 'current_text', '')).encode('utf-8')).hexdigest()[:8]}",
                f"shape:{getattr(getattr(layer, 'shape_type', ''), 'value', getattr(layer, 'shape_type', ''))}",
                f"trap:{getattr(layer, 'trapezoid_top_width', '')},{getattr(layer, 'trapezoid_bottom_width', '')},{getattr(layer, 'trapezoid_slope_side', '')}",
                f"poly:{getattr(layer, 'polygon_rotation', '')},{getattr(layer, 'polygon_corner_radius', '')}",
            ]
            raw_key = "|".join([str(p) for p in layer_parts])
            return hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        except Exception:
            return f"fallback_layer_surface_{id(layer)}_{time.time()}"

    def _get_layer_surface_cached(self, layer, document, was_just_loaded: bool = False) -> Optional[Image.Image]:
        """获取图层surface缓存；未命中时重新生成并缓存"""
        cache_key = self._build_layer_surface_key(layer, document, was_just_loaded)
        is_batch_session = bool(getattr(document, '_is_batch_export_running', False))
        entry_key = f"{id(document)}:{id(layer)}"
        export_entry_key = f"export:{cache_key}"

        if is_batch_session:
            with self._export_layer_surface_lock:
                export_entry = self._export_layer_surface_cache.get(export_entry_key)
                if export_entry:
                    self._export_layer_surface_cache.move_to_end(export_entry_key)
                    export_image = export_entry.get("image")
                    if export_image is not None:
                        setattr(layer, "_render_offset_x", int(export_entry.get("offset_x", 0)))
                        setattr(layer, "_render_offset_y", int(export_entry.get("offset_y", 0)))
                        FastRenderer._inc_batch_metric("export_layer_cache_hits")
                        return export_image.copy()
            FastRenderer._inc_batch_metric("export_layer_cache_misses")

        with self._layer_surface_lock:
            entry = self._layer_surface_cache.get(entry_key)
            if entry and entry.get("cache_key") == cache_key:
                self._layer_surface_cache.move_to_end(entry_key)
                image = entry.get("image")
                if image is not None:
                    setattr(layer, "_render_offset_x", int(entry.get("offset_x", 0)))
                    setattr(layer, "_render_offset_y", int(entry.get("offset_y", 0)))
                    if is_batch_session:
                        FastRenderer._inc_batch_metric("layer_surface_cache_hits")
                    return image.copy()
        if is_batch_session:
            FastRenderer._inc_batch_metric("layer_surface_cache_misses")

        layer_image = self._get_layer_image(layer, document, was_just_loaded)
        if layer_image is None:
            return None

        if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
            if is_batch_session:
                FastRenderer._inc_batch_metric("apply_effects_calls")
            layer_image = layer.apply_effects(layer_image)
            if layer_image is None:
                return None

        if is_batch_session:
            with self._export_layer_surface_lock:
                self._export_layer_surface_cache[export_entry_key] = {
                    "cache_key": cache_key,
                    "image": layer_image.copy(),
                    "offset_x": int(getattr(layer, "_render_offset_x", 0)),
                    "offset_y": int(getattr(layer, "_render_offset_y", 0)),
                }
                self._export_layer_surface_cache.move_to_end(export_entry_key)
                while len(self._export_layer_surface_cache) > self._max_export_layer_surface_entries:
                    self._export_layer_surface_cache.popitem(last=False)

        with self._layer_surface_lock:
            self._layer_surface_cache[entry_key] = {
                "cache_key": cache_key,
                "image": layer_image.copy(),
                "offset_x": int(getattr(layer, "_render_offset_x", 0)),
                "offset_y": int(getattr(layer, "_render_offset_y", 0)),
            }
            self._layer_surface_cache.move_to_end(entry_key)
            while len(self._layer_surface_cache) > self._max_layer_surface_entries:
                self._layer_surface_cache.popitem(last=False)

        return layer_image

    def _clear_layer_surface_cache(self):
        """清空图层surface缓存"""
        with self._layer_surface_lock:
            self._layer_surface_cache.clear()
        with self._export_layer_surface_lock:
            self._export_layer_surface_cache.clear()
    
    def _clear_layer_positions_cache(self):
        """清空图层位置缓存"""
        with self._layer_positions_lock:
            self._layer_positions_cache.clear()

    def _clear_interactive_base_cache(self):
        """清空交互增量预览底图缓存"""
        with self._interactive_base_lock:
            self._interactive_base_cache.clear()

    def _clear_interactive_layer_surface_cache(self):
        """清空交互活动图层缓存（变换优先路径）。"""
        with self._interactive_layer_surface_lock:
            self._interactive_layer_surface_cache.clear()

    def _clear_size_match_caches(self):
        """清空大小匹配相关缓存。"""
        with self._size_match_holes_lock:
            self._size_match_holes_cache.clear()
        with self._size_override_surface_lock:
            self._size_override_surface_cache.clear()

    def _invalidate_interactive_base_for_document(self, document):
        """清理指定文档的交互底图缓存"""
        doc_prefix = f"{id(document)}:"
        with self._interactive_base_lock:
            keys_to_remove = [k for k in self._interactive_base_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._interactive_base_cache.pop(k, None)

    def _invalidate_interactive_layer_surfaces_for_document(self, document):
        """清理指定文档的交互活动图层缓存。"""
        doc_prefix = f"{id(document)}:"
        with self._interactive_layer_surface_lock:
            keys_to_remove = [
                k for k in self._interactive_layer_surface_cache.keys()
                if str(k).startswith(doc_prefix)
            ]
            for k in keys_to_remove:
                self._interactive_layer_surface_cache.pop(k, None)

    def _invalidate_size_match_caches_for_document(self, document):
        """仅清理指定文档的大小匹配缓存。"""
        doc_prefix = f"{id(document)}:"
        with self._size_match_holes_lock:
            keys_to_remove = [k for k in self._size_match_holes_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._size_match_holes_cache.pop(k, None)
        with self._size_override_surface_lock:
            keys_to_remove = [k for k in self._size_override_surface_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._size_override_surface_cache.pop(k, None)

    def _clear_batch_session_caches(self):
        """清空批量导出会话缓存。"""
        with self._batch_raw_image_lock:
            self._batch_raw_image_cache.clear()
        with self._batch_processed_image_lock:
            self._batch_processed_image_cache.clear()
        with self._export_layer_surface_lock:
            self._export_layer_surface_cache.clear()

    def _invalidate_batch_session_caches_for_document(self, document):
        """清理指定文档的批量导出会话缓存。"""
        doc_prefix = f"{id(document)}:"
        with self._batch_raw_image_lock:
            keys_to_remove = [k for k in self._batch_raw_image_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._batch_raw_image_cache.pop(k, None)
        with self._batch_processed_image_lock:
            keys_to_remove = [k for k in self._batch_processed_image_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._batch_processed_image_cache.pop(k, None)

    def _get_batch_processed_cache_key(self, document, layer, image_path: str) -> str:
        parts = [
            f"{id(document)}",
            f"path:{image_path}",
            f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
            f"fit:{getattr(layer, 'fit_mode', 0)}",
            f"crop:{getattr(layer, 'crop_direction', 0)}",
            f"use_orig:{int(bool(getattr(layer, 'use_original_size', False)))}",
            f"rot:{float(getattr(layer, 'rotation', 0.0)):.3f}",
            f"flip_h:{int(bool(getattr(layer, 'flip_horizontal', False)))}",
            f"flip_v:{int(bool(getattr(layer, 'flip_vertical', False)))}",
            f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
            f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
        ]
        return "|".join([str(p) for p in parts])

    def _build_layer_interactive_surface_key(self, layer, document, was_just_loaded: bool = False) -> str:
        """构建交互活动图层缓存键（只包含几何与变换所需字段）。"""
        try:
            parts = [
                f"src:{getattr(layer, 'image_source', '')}",
                f"current:{getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '')}",
                f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
                f"fit:{getattr(layer, 'fit_mode', 0)}",
                f"crop:{getattr(layer, 'crop_direction', 0)}",
                f"use_orig:{int(bool(getattr(layer, 'use_original_size', False)))}",
                f"flip_h:{int(bool(getattr(layer, 'flip_horizontal', False)))}",
                f"flip_v:{int(bool(getattr(layer, 'flip_vertical', False)))}",
                f"rot:{float(getattr(layer, 'rotation', 0.0)):.3f}",
                f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
                f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
                f"shape:{getattr(getattr(layer, 'shape_type', ''), 'value', getattr(layer, 'shape_type', ''))}",
                f"trap:{getattr(layer, 'trapezoid_top_width', '')},{getattr(layer, 'trapezoid_bottom_width', '')},{getattr(layer, 'trapezoid_slope_side', '')}",
                f"poly:{getattr(layer, 'polygon_rotation', '')},{getattr(layer, 'polygon_corner_radius', '')}",
                f"just_loaded:{int(bool(was_just_loaded))}",
            ]
            raw_key = "|".join([str(p) for p in parts])
            return hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        except Exception:
            return f"fallback_interactive_surface_{id(layer)}_{time.time()}"

    def _apply_interactive_transform_only(self, layer, image: Image.Image) -> Optional[Image.Image]:
        """交互期仅应用必要几何：形状裁切 + 变换；跳过描边/叠加等重特效。"""
        if image is None:
            return None
        try:
            result = image.convert('RGBA') if image.mode != 'RGBA' else image.copy()

            shape_type_val = getattr(getattr(layer, 'shape_type', None), 'value', getattr(layer, 'shape_type', ''))
            has_non_rect_shape = str(shape_type_val) not in ("", "rectangle", "ShapeType.RECTANGLE")
            if has_non_rect_shape and hasattr(layer, '_apply_shape_mask') and callable(getattr(layer, '_apply_shape_mask', None)):
                try:
                    result = layer._apply_shape_mask(result)
                except Exception:
                    # 形状裁切失败时保守回退原图，避免交互中断
                    pass

            if hasattr(layer, '_apply_transformations') and callable(getattr(layer, '_apply_transformations', None)):
                result = layer._apply_transformations(result)

            return result
        except Exception:
            return image

    def _get_layer_surface_interactive_cached(self, layer, document, was_just_loaded: bool = False) -> Optional[Image.Image]:
        """获取交互期活动图层surface：仅重算几何/变换，跳过复杂特效。"""
        cache_key = self._build_layer_interactive_surface_key(layer, document, was_just_loaded)
        entry_key = f"{id(document)}:{id(layer)}"

        with self._interactive_layer_surface_lock:
            entry = self._interactive_layer_surface_cache.get(entry_key)
            if entry and entry.get("cache_key") == cache_key:
                self._interactive_layer_surface_cache.move_to_end(entry_key)
                cached = entry.get("image")
                if cached is not None:
                    return cached.copy()

        base_image = self._get_layer_image(layer, document, was_just_loaded)
        if base_image is None:
            return None

        surface = self._apply_interactive_transform_only(layer, base_image)
        if surface is None:
            return None

        with self._interactive_layer_surface_lock:
            self._interactive_layer_surface_cache[entry_key] = {
                "cache_key": cache_key,
                "image": surface.copy()
            }
            self._interactive_layer_surface_cache.move_to_end(entry_key)
            while len(self._interactive_layer_surface_cache) > self._max_interactive_layer_surface_entries:
                self._interactive_layer_surface_cache.popitem(last=False)

        return surface

    def _get_batch_preloaded_raw_image(self, document, image_path: str):
        """优先从执行器预读缓存获取原图。"""
        preload_cache = getattr(document, '_batch_preloaded_images', None)
        if isinstance(preload_cache, dict):
            img = preload_cache.get(image_path)
            if img is not None:
                return img.copy()
        return None

    def _build_interactive_base_key(self, document, active_layer_index: int, interactive_low_quality: bool) -> str:
        """构建交互增量预览底图缓存键。"""
        parts = [
            f"{id(document)}:{active_layer_index}",
            f"canvas:{document.canvas_width}x{document.canvas_height}",
            f"lowq:{int(bool(interactive_low_quality))}",
        ]
        for idx, layer in enumerate(document.layers):
            if idx == active_layer_index or layer is None or not getattr(layer, 'visible', True):
                continue
            parts.append(self._build_layer_surface_key(layer, document, was_just_loaded=False))
            parts.append(self._build_layer_positions_key(layer, document))
            parts.append(f"opacity:{float(getattr(layer, 'opacity', 1.0)):.4f}")
            parts.append(f"blend:{self._get_layer_blend_mode(layer)}")
        return hashlib.md5("|".join(parts).encode('utf-8')).hexdigest()

    def _get_or_build_interaction_base(
        self,
        document,
        active_layer_index: int,
        force_refresh: bool,
        interactive_low_quality: bool
    ) -> Optional[Image.Image]:
        """获取或构建交互静态底图（不包含当前操作图层）。"""
        cache_key = self._build_interactive_base_key(document, active_layer_index, interactive_low_quality)
        entry_key = f"{id(document)}:{active_layer_index}"
        with self._interactive_base_lock:
            entry = self._interactive_base_cache.get(entry_key)
            if not force_refresh and entry and entry.get("cache_key") == cache_key:
                self._interactive_base_cache.move_to_end(entry_key)
                image = entry.get("image")
                if image is not None:
                    return image.copy()

        image = self._fast_render(
            document=document,
            preview_mode=True,
            was_just_loaded=False,
            low_quality_preview=interactive_low_quality,
            skip_layer_index=active_layer_index
        )
        if image is None:
            return None

        with self._interactive_base_lock:
            self._interactive_base_cache[entry_key] = {
                "cache_key": cache_key,
                "image": image.copy()
            }
            self._interactive_base_cache.move_to_end(entry_key)
            while len(self._interactive_base_cache) > self._max_interactive_base_entries:
                self._interactive_base_cache.popitem(last=False)
        return image

    def _invalidate_layer_surfaces_for_document(self, document):
        """仅清理指定文档的图层surface缓存"""
        doc_prefix = f"{id(document)}:"
        with self._layer_surface_lock:
            keys_to_remove = [k for k in self._layer_surface_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._layer_surface_cache.pop(k, None)
        with self._export_layer_surface_lock:
            keys_to_remove = [k for k in self._export_layer_surface_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._export_layer_surface_cache.pop(k, None)
        with self._layer_positions_lock:
            keys_to_remove = [k for k in self._layer_positions_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._layer_positions_cache.pop(k, None)

    def _simple_fallback_render(self, document) -> Optional[Image.Image]:
        """最简单的后备渲染方案"""
        try:
            print(f"[简化渲染] 使用最基础的渲染方案")

            # 创建画布
            composition = Image.new('RGBA', (document.canvas_width, document.canvas_height), (0, 0, 0, 0))

            # 获取可见图层
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            visible_layers = [
                layer for layer in document.layers
                if not is_layer_group(layer) and is_effectively_visible(layer, document.layers)
            ]
            if not visible_layers:
                return composition

            # 使用最简单的方式渲染每个图层
            for layer in visible_layers:
                try:
                    # 获取图层图像
                    layer_image = self._get_layer_image(layer, document, False)
                    if layer_image is None:
                        continue

                    # 获取不透明度
                    opacity = getattr(layer, 'opacity', 1.0)

                    # 应用不透明度
                    if opacity < 1.0:
                        alpha = layer_image.split()[-1]
                        alpha = alpha.point(lambda p: int(p * opacity))
                        layer_image = layer_image.copy()
                        layer_image.putalpha(alpha)

                    # 处理分身功能
                    clone_positions = []
                    is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled

                    if is_clone_enabled and hasattr(layer, 'get_effective_clone_positions'):
                        # 获取所有分身位置（包含随机偏移）
                        try:
                            clone_positions = layer.get_effective_clone_positions()
                            print(f"[简化渲染] 图层 '{layer.name}' 启用分身，共 {len(clone_positions)} 个位置")
                        except Exception as e:
                            print(f"[简化渲染] 获取分身位置失败: {e}")
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

                    positions_info = [(x, y, False) for (x, y) in clone_positions]
                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    if mirror_mode and mirror_mode != 'none':
                        base = clone_positions[:]
                        min_x = min([x for x, _ in base])
                        max_x = max([x + layer.width for x, _ in base])
                        min_y = min([y for _, y in base])
                        max_y = max([y + layer.height for _, y in base])
                        group_width = max_x - min_x
                        group_height = max_y - min_y
                        if mirror_mode == 'horizontal':
                            mirrored_left = document.canvas_width - (min_x + group_width)
                            for x, y in base:
                                offset_x = x - min_x
                                positions_info.append((mirrored_left + offset_x, y, True))
                        elif mirror_mode == 'vertical':
                            mirrored_top = document.canvas_height - (min_y + group_height)
                            for x, y in base:
                                offset_y = y - min_y
                                positions_info.append((x, mirrored_top + offset_y, True))

                    from PIL import ImageOps
                    for pos_x, pos_y, is_mirror in positions_info:
                        img_for_pos = ImageOps.mirror(layer_image) if (is_mirror and mirror_mode == 'horizontal') else (ImageOps.flip(layer_image) if (is_mirror and mirror_mode == 'vertical') else layer_image)
                        draw_x = int(pos_x) + int(getattr(layer, '_render_offset_x', 0))
                        draw_y = int(pos_y) + int(getattr(layer, '_render_offset_y', 0))
                        composition.paste(img_for_pos, (draw_x, draw_y), img_for_pos)

                except Exception as layer_e:
                    print(f"[简化渲染] 图层渲染失败: {layer_e}")
                    continue

            return composition

        except Exception as e:
            print(f"[简化渲染] 简化渲染失败: {e}")
            return None

    def _get_layer_blend_mode(self, layer):
        """获取图层的混合模式字符串"""
        try:
            blend_mode = getattr(layer, 'blend_mode', 0)

            # 枚举值兼容（如 BlendMode.NORMAL / enum.IntEnum）
            if hasattr(blend_mode, 'value'):
                blend_mode = blend_mode.value

            # 如果是数字，转换为字符串
            if isinstance(blend_mode, int):
                blend_mode_map = {
                    0: 'normal',
                    1: 'multiply',
                    2: 'screen',
                    3: 'overlay',
                    4: 'soft_light',
                    5: 'hard_light',
                    6: 'color_dodge',
                    7: 'color_burn',
                    8: 'darken',
                    9: 'lighten',
                    10: 'difference',
                    11: 'exclusion',
                    12: 'hue',
                    13: 'saturation',
                    14: 'color',
                    15: 'luminosity'
                }
                return blend_mode_map.get(blend_mode, 'normal')

            # 如果是字符串，直接返回
            if isinstance(blend_mode, str):
                normalized = blend_mode.strip().lower()
                # 兼容 "BlendMode.NORMAL" 这类字符串
                if normalized.startswith('blendmode.'):
                    normalized = normalized.split('.', 1)[1]
                return normalized

            # 如果是枚举或其他类型，转换为字符串
            normalized = str(blend_mode).strip().lower()
            if normalized.startswith('blendmode.'):
                normalized = normalized.split('.', 1)[1]
            return normalized

        except Exception as e:
            print(f"[快速渲染] 获取混合模式失败: {e}")
            return 'normal'

    def _get_layer_image(self, layer, document, was_just_loaded: bool = False) -> Optional[Image.Image]:
        """获取图层图像 - 修复版本，支持文件限制"""
        try:
            print(f"[快速渲染] 开始获取图层图像: {layer.name}")
            export_trace_enabled = bool(getattr(document, '_export_debug_trace_enabled', False))
            export_trace_task = str(getattr(document, '_export_debug_trace_task', '') or '')
            export_trace_file = str(getattr(document, '_export_debug_trace_file', '') or '')

            def _emit_layer_source_trace(message: str):
                if not export_trace_enabled:
                    return
                line = f"[导出调试] {str(message)}"
                try:
                    builtins.print(line)
                except Exception:
                    pass
                if export_trace_file:
                    try:
                        with open(export_trace_file, 'a', encoding='utf-8') as f:
                            f.write(line + "\n")
                    except Exception:
                        pass

            # 处理文字图层
            from app.models.text_layer import TextLayer
            if isinstance(layer, TextLayer):
                print(f"[快速渲染] ✓ 文字图层渲染: {layer.name}")
                return layer.render_text()

            # 🔧 关键修复：完全禁用预处理缓存，避免重复图片问题
            # 注释掉所有缓存检查，确保每次都重新加载图像
            # if hasattr(layer, 'cached_image') and layer.cached_image is not None:
            #     if hasattr(layer, 'is_cache_valid') and layer.is_cache_valid():
            #         print(f"[快速渲染] 🚀 使用预处理缓存: {layer.name} -> {layer.cached_image.size}")
            #         return layer.cached_image
            #     else:
            #         print(f"[快速渲染] ⚠️  预处理缓存无效: {layer.name}")

            # 🔧 关键修复：禁用有效缓存图像检查
            # if hasattr(layer, 'get_valid_cached_image'):
            #     cached_image = layer.get_valid_cached_image()
            #     if cached_image is not None:
            #         print(f"[快速渲染] ✓ 使用有效缓存: {layer.name} -> {cached_image.size}")
            #         return cached_image

            print(f"[快速渲染] 🔧 强制重新加载图像: {layer.name} (禁用旧缓存)")
            is_batch_session = bool(getattr(document, '_is_batch_export_running', False))

            # 🔧 关键修复：始终优先使用当前图像路径，确保预览与文档状态一致
            # 同时兼容 LegacyLayer(_current_image_path) 与 LayerNew(current_image_path)
            current_image_path = None
            if hasattr(layer, '_current_image_path') and getattr(layer, '_current_image_path', None):
                current_image_path = layer._current_image_path
            elif hasattr(layer, 'current_image_path'):
                try:
                    current_image_path = layer.current_image_path
                except Exception:
                    current_image_path = None

            if current_image_path:
                # 只有当路径是文件时才尝试加载（避免 text_layer:// 虚拟路径被误加载）
                if os.path.isfile(current_image_path):
                    try:
                        processed_cache_key = None
                        if is_batch_session:
                            processed_cache_key = self._get_batch_processed_cache_key(document, layer, current_image_path)
                            with self._batch_processed_image_lock:
                                cached_processed = self._batch_processed_image_cache.get(processed_cache_key)
                                if cached_processed is not None:
                                    self._batch_processed_image_cache.move_to_end(processed_cache_key)
                                    _emit_layer_source_trace(
                                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                        f"实际图源={current_image_path} 图源模式=current_image_path 命中批处理processed缓存=True"
                                    )
                                    return cached_processed.copy()

                        # 批导优先使用预读原图 + 会话原图缓存，减少重复读盘
                        if is_batch_session and hasattr(layer, '_process_image') and callable(getattr(layer, '_process_image', None)):
                            source_image = self._get_batch_preloaded_raw_image(document, current_image_path)
                            raw_cache_key = f"{id(document)}:{current_image_path}"
                            if source_image is None:
                                with self._batch_raw_image_lock:
                                    cached_raw = self._batch_raw_image_cache.get(raw_cache_key)
                                    if cached_raw is not None:
                                        self._batch_raw_image_cache.move_to_end(raw_cache_key)
                                        source_image = cached_raw.copy()

                            if source_image is None:
                                from app.models.layer_image_loader import LayerImageLoader
                                source_image = LayerImageLoader.load_image_from_path(current_image_path)
                                if source_image is not None:
                                    with self._batch_raw_image_lock:
                                        self._batch_raw_image_cache[raw_cache_key] = source_image.copy()
                                        self._batch_raw_image_cache.move_to_end(raw_cache_key)
                                        while len(self._batch_raw_image_cache) > self._max_batch_raw_entries:
                                            self._batch_raw_image_cache.popitem(last=False)

                            if source_image is not None:
                                processed = layer._process_image(source_image.copy())
                                if processed is not None:
                                    if processed_cache_key is not None:
                                        with self._batch_processed_image_lock:
                                            self._batch_processed_image_cache[processed_cache_key] = processed.copy()
                                            self._batch_processed_image_cache.move_to_end(processed_cache_key)
                                            while len(self._batch_processed_image_cache) > self._max_batch_processed_entries:
                                                self._batch_processed_image_cache.popitem(last=False)
                                    _emit_layer_source_trace(
                                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                        f"实际图源={current_image_path} 图源模式=current_image_path "
                                        f"加载方式=batch_process_image"
                                    )
                                    return processed

                        # 使用图层自己的加载方法，确保应用了所有变换
                        if hasattr(layer, '_load_and_process_image'):
                            image = layer._load_and_process_image(current_image_path)
                            if image:
                                if processed_cache_key is not None:
                                    with self._batch_processed_image_lock:
                                        self._batch_processed_image_cache[processed_cache_key] = image.copy()
                                        self._batch_processed_image_cache.move_to_end(processed_cache_key)
                                        while len(self._batch_processed_image_cache) > self._max_batch_processed_entries:
                                            self._batch_processed_image_cache.popitem(last=False)
                                _emit_layer_source_trace(
                                    f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                    f"实际图源={current_image_path} 图源模式=current_image_path "
                                    f"加载方式=layer_load_and_process"
                                )
                                return image
                        
                        # 如果图层没有这个方法（旧代码），我们回退到标准加载
                        from app.models.layer_image_loader import LayerImageLoader
                        image = LayerImageLoader.load_image_from_path(current_image_path)
                        if image is not None and processed_cache_key is not None:
                            with self._batch_processed_image_lock:
                                self._batch_processed_image_cache[processed_cache_key] = image.copy()
                                self._batch_processed_image_cache.move_to_end(processed_cache_key)
                                while len(self._batch_processed_image_cache) > self._max_batch_processed_entries:
                                    self._batch_processed_image_cache.popitem(last=False)
                        if image is not None:
                            _emit_layer_source_trace(
                                f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                f"实际图源={current_image_path} 图源模式=current_image_path 加载方式=direct_image_loader"
                            )
                        return image
                    except Exception as e:
                        print(f"[快速渲染] ✗ 加载当前图像失败: {layer.name} - {e}")
                        _emit_layer_source_trace(
                            f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                            f"实际图源={current_image_path} 图源模式=current_image_path "
                            f"加载失败={str(e)}"
                        )
            
            # 🔧 新增：检查是否为文档刚加载状态，避免立即处理所有图层
            if was_just_loaded:
                print(f"[快速渲染] 📄 文档刚加载且无有效图片，返回占位符: {layer.name}")
                return self._create_placeholder_image(layer)

            # 如果没有有效缓存，获取新图像
            if hasattr(layer, 'get_random_image'):
                print(f"[快速渲染] → 重新获取图像: {layer.name}")

                # 🔧 关键修复：检查是否有绑定管理器和文件限制
                restricted_files = None
                if document and hasattr(document, 'binding_manager') and document.binding_manager:
                    if document.binding_manager.global_enabled:
                        restricted_files = document.binding_manager.get_layer_file_restrictions(layer)
                        if restricted_files:
                            print(f"[快速渲染] 使用文件限制: {layer.name} -> {len(restricted_files)} 个文件")
                            print(f"[快速渲染] 限制文件示例: {[os.path.basename(f) for f in restricted_files[:3]]}")
                        else:
                            print(f"[快速渲染] 无文件限制: {layer.name}")

                # 调用get_random_image时传递文件限制
                if restricted_files:
                    image = layer.get_random_image(restrict_to_bound_files=restricted_files)
                else:
                    image = layer.get_random_image()

                if image:
                    print(f"[快速渲染] ✓ 图像获取成功: {layer.name} -> {image.size}")
                    # 验证获取的图像路径
                    resolved_path = str(
                        getattr(layer, '_current_image_path', '') or
                        getattr(layer, 'current_image_path', '') or
                        ''
                    )
                    if resolved_path:
                        print(f"[快速渲染] 当前图像路径: {os.path.basename(resolved_path)}")
                    _emit_layer_source_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"实际图源={resolved_path or 'None'} 图源模式=fallback_random"
                    )
                else:
                    print(f"[快速渲染] ✗ 图像获取失败: {layer.name}")
                    _emit_layer_source_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"实际图源=None 图源模式=fallback_random_failed"
                    )
                return image

            print(f"[快速渲染] ✗ 无法获取图像: {layer.name} (无可用方法)")
            return None

        except Exception as e:
            print(f"[快速渲染] ✗ 获取图层图像失败: {layer.name} -> {e}")
            return None

    def _create_placeholder_image(self, layer):
        """为刚加载的文档创建占位图像"""
        try:
            # 创建一个简单的占位图像
            width = max(layer.width, 100)
            height = max(layer.height, 100)

            # 创建半透明的占位图像
            placeholder = Image.new('RGBA', (width, height), (200, 200, 200, 100))

            # 添加图层名称文字（如果PIL支持）
            try:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(placeholder)

                # 尝试使用默认字体
                try:
                    font = ImageFont.load_default()
                except:
                    font = None

                # 绘制图层名称
                text = f"加载中...\n{layer.name}"
                if font:
                    draw.text((10, 10), text, fill=(100, 100, 100, 200), font=font)
                else:
                    draw.text((10, 10), text, fill=(100, 100, 100, 200))

            except Exception as e:
                print(f"[快速渲染] 占位图像文字绘制失败: {e}")

            print(f"[快速渲染] ✓ 创建占位图像: {layer.name} -> {placeholder.size}")
            return placeholder

        except Exception as e:
            print(f"[快速渲染] 创建占位图像失败: {layer.name} - {e}")
            # 返回最简单的占位图像
            return Image.new('RGBA', (100, 100), (200, 200, 200, 100))
    
    def _fast_composite(
        self,
        background: Image.Image,
        foreground: Image.Image,
        pos_x: int,
        pos_y: int,
        opacity: float,
        preview_mode: bool,
        blend_mode: str = 'normal',
        low_quality_preview: bool = False
    ) -> Image.Image:
        """快速合成 - 使用Photoshop风格的sRGB混合以保证渲染质量"""
        if preview_mode and low_quality_preview:
            return self._standard_composite_logic(
                background,
                foreground,
                pos_x,
                pos_y,
                opacity,
                blend_mode,
                is_preview=True,
                low_quality_preview=True
            )

        try:
            # 尝试使用 UnifiedAlphaCompositor 以获得最佳渲染效果
            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
            
            # 无论是预览模式还是批量模式，都使用 sRGB 混合以保证 Photoshop 风格的渲染效果
            # 解决了之前的线性空间转换导致的色差和像素丢失问题
            
            # 🔧 关键修复：禁用边缘增强和亚像素精度，避免颜色偏差
            # edge_enhancement 会调用超级抗锯齿，可能改变图像颜色
            # 为了确保预览和导出颜色一致，统一禁用这些增强功能
            edge_enhancement = False  # 原：not preview_mode
            subpixel_precision = False  # 原：not preview_mode
            
            return UnifiedAlphaCompositor.composite_layer(
                background=background,
                foreground=foreground,
                position=(pos_x, pos_y),
                opacity=opacity,
                blend_mode=blend_mode,
                edge_enhancement=edge_enhancement,
                subpixel_precision=subpixel_precision,
                use_srgb_blending=True  # 启用 Photoshop 风格混合
            )
            
        except Exception as e:
            print(f"[快速渲染] 统一合成失败: {e}，回退到标准逻辑")
            return self._standard_composite_logic(
                background,
                foreground,
                pos_x,
                pos_y,
                opacity,
                blend_mode,
                is_preview=preview_mode,
                low_quality_preview=low_quality_preview
            )

    def _standard_composite_logic(
        self,
        background,
        foreground,
        pos_x,
        pos_y,
        opacity,
        blend_mode,
        is_preview,
        low_quality_preview: bool = False
    ):
        """标准的合成逻辑（原回退逻辑提取）"""
        try:
            # 确保图像格式
            if background.mode != 'RGBA':
                background = background.convert('RGBA')
            if foreground.mode != 'RGBA':
                foreground = foreground.convert('RGBA')
            
            # 应用不透明度
            if opacity < 1.0:
                # 快速不透明度调整
                fg_array = np.array(foreground, dtype=np.float32)
                fg_array[:,:,3] *= opacity
                foreground = Image.fromarray(fg_array.astype(np.uint8), 'RGBA')
            
            # 计算有效区域
            bg_width, bg_height = background.size
            fg_width, fg_height = foreground.size
            
            # 边界检查
            if pos_x >= bg_width or pos_y >= bg_height or pos_x + fg_width <= 0 or pos_y + fg_height <= 0:
                return background
            
            # 计算裁剪区域
            src_x = max(0, -pos_x)
            src_y = max(0, -pos_y)
            src_w = min(fg_width - src_x, bg_width - max(0, pos_x))
            src_h = min(fg_height - src_y, bg_height - max(0, pos_y))
            
            if src_w <= 0 or src_h <= 0:
                return background
            
            # 裁剪前景
            fg_crop = foreground.crop((src_x, src_y, src_x + src_w, src_y + src_h))
            
            # 计算目标位置
            dst_x = max(0, pos_x)
            dst_y = max(0, pos_y)
            
            # 执行合成
            if is_preview:
                # 预览模式：使用快速混合
                if blend_mode == 'normal':
                    # 交互低质模式：强制走最快路径，优先保障拖拽跟手
                    if low_quality_preview:
                        result = background.copy()
                        result.paste(fg_crop, (dst_x, dst_y), fg_crop)
                        return result
                    # 对含半透明边缘的图层，使用高质量alpha合成，避免圆角/描边边缘台阶感
                    if self._has_partial_alpha(fg_crop):
                        return self._high_quality_alpha_composite(background, fg_crop, dst_x, dst_y)
                    # 完全不透明/全透明图像继续走快速分支
                    result = background.copy()
                    result.paste(fg_crop, (dst_x, dst_y), fg_crop)
                    return result
                else:
                    # 其他混合模式使用简化混合
                    return self._apply_blend_mode(background, fg_crop, dst_x, dst_y, blend_mode)
            else:
                # 批量模式（回退情况）：使用高质量合成
                return self._high_quality_composite(background, fg_crop, dst_x, dst_y, blend_mode)
            
        except Exception as e2:
            print(f"[快速渲染] 标准逻辑失败: {e2}")
            return background
    
    def _has_partial_alpha(self, image: Image.Image) -> bool:
        """判断图像是否包含(0,255)之间的半透明像素。"""
        try:
            if image.mode != 'RGBA':
                return False
            alpha = image.getchannel('A')
            lo, hi = alpha.getextrema()
            if lo >= 255 or hi <= 0:
                return False
            # 粗采样检查，避免每帧全量扫描开销
            arr = np.array(alpha, dtype=np.uint8)
            if arr.size > 65536:
                arr = arr[::2, ::2]
            return bool(np.any((arr > 0) & (arr < 255)))
        except Exception:
            return True
    
    def _apply_opacity(self, image: Image.Image, opacity: float) -> Image.Image:
        """应用不透明度"""
        if opacity >= 1.0:
            return image

        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # 调整alpha通道
        r, g, b, a = image.split()
        a = a.point(lambda x: int(x * opacity))
        return Image.merge('RGBA', (r, g, b, a))

    def _apply_blend_mode(self, background: Image.Image, foreground: Image.Image,
                         dst_x: int, dst_y: int, blend_mode: str) -> Image.Image:
        """应用混合模式"""
        try:
            # 创建一个临时画布来应用混合
            temp_canvas = background.copy()

            # 提取需要混合的区域
            fg_width, fg_height = foreground.size
            bg_region = temp_canvas.crop((dst_x, dst_y, dst_x + fg_width, dst_y + fg_height))

            # 应用混合模式
            blended_region = self._blend_images(bg_region, foreground, blend_mode)

            # 将混合结果粘贴回画布
            temp_canvas.paste(blended_region, (dst_x, dst_y), blended_region)
            return temp_canvas

        except Exception as e:
            print(f"[快速渲染] 混合模式应用失败: {e}")
            # 回退到正常合成
            result = background.copy()
            result.paste(foreground, (dst_x, dst_y), foreground)
            return result

    def _blend_images(self, base: Image.Image, top: Image.Image, blend_mode: str) -> Image.Image:
        """执行图像混合"""
        try:
            # 使用文档混合器，确保所有模式生效
            from app.models.document_blend import Blender
            return Blender.apply_blend_mode(base, top, blend_mode, opacity=1.0)

        except Exception as e:
            print(f"[快速渲染] 图像混合失败: {e}")
            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
            return UnifiedAlphaCompositor.blend_normal(base.convert('RGBA'), top.convert('RGBA'), 1.0)

    def _high_quality_composite(self, background: Image.Image, foreground: Image.Image,
                               dst_x: int, dst_y: int, blend_mode: str = 'normal') -> Image.Image:
        """高质量合成（支持混合模式）"""
        try:
            if blend_mode == 'normal':
                # 正常模式使用高精度alpha混合
                return self._high_quality_alpha_composite(background, foreground, dst_x, dst_y)
            else:
                # 其他混合模式使用混合模式管理器
                return self._apply_blend_mode(background, foreground, dst_x, dst_y, blend_mode)

        except Exception as e:
            print(f"[快速渲染] 高质量合成失败: {e}")
            # 回退到简单合成
            result = background.copy()
            result.paste(foreground, (dst_x, dst_y), foreground)
            return result

    def _high_quality_alpha_composite(self, background: Image.Image, foreground: Image.Image,
                                     dst_x: int, dst_y: int) -> Image.Image:
        """高精度alpha合成"""
        try:
            # 使用numpy进行高精度alpha混合
            bg_array = np.array(background, dtype=np.float32) / 255.0
            fg_array = np.array(foreground, dtype=np.float32) / 255.0

            # 获取前景区域
            fg_h, fg_w = fg_array.shape[:2]
            bg_h, bg_w = bg_array.shape[:2]

            # 确保不越界
            end_x = min(dst_x + fg_w, bg_w)
            end_y = min(dst_y + fg_h, bg_h)

            if end_x <= dst_x or end_y <= dst_y:
                return background

            # 提取区域
            bg_region = bg_array[dst_y:end_y, dst_x:end_x]
            fg_region = fg_array[:end_y-dst_y, :end_x-dst_x]

            # Alpha混合
            fg_alpha = fg_region[:,:,3:4]
            bg_alpha = bg_region[:,:,3:4]

            # 转换为线性颜色空间进行混合 - 解决颜色变灰变黑问题
            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
            
            fg_rgb = fg_region[:,:,:3]
            bg_rgb = bg_region[:,:,:3]
            
            # 转换到线性颜色空间
            fg_rgb_linear = UnifiedAlphaCompositor._srgb_to_linear(fg_rgb)
            bg_rgb_linear = UnifiedAlphaCompositor._srgb_to_linear(bg_rgb)

            # 计算输出alpha
            out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)

            # 避免除零
            safe_alpha = np.where(out_alpha > 1e-6, out_alpha, 1e-6)

            # 在线性颜色空间中计算输出颜色 - 解决颜色变灰问题
            out_rgb_linear = (fg_rgb_linear * fg_alpha + bg_rgb_linear * bg_alpha * (1 - fg_alpha)) / safe_alpha
            
            # 转换回sRGB颜色空间
            out_rgb = UnifiedAlphaCompositor._linear_to_srgb(out_rgb_linear)

            # 组合结果
            result_region = np.concatenate([out_rgb, out_alpha], axis=2)

            # 更新背景
            result_array = bg_array.copy()
            result_array[dst_y:end_y, dst_x:end_x] = result_region

            # 🔧 修复：使用抖动转换以消除色阶分层
            try:
                from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
                result_8bit = _float_to_uint8_with_dithering(result_array, use_dithering=True)
            except ImportError:
                # 后备方案：使用四舍五入
                result_8bit = np.round(np.clip(result_array, 0.0, 1.0) * 255.0).astype(np.uint8)
            return Image.fromarray(result_8bit, 'RGBA')

        except Exception as e:
            print(f"[快速渲染] 高精度alpha合成失败: {e}")
            # 回退到简单合成
            result = background.copy()
            result.paste(foreground, (dst_x, dst_y), foreground)
            return result
    
    def invalidate_cache(self):
        """使缓存失效"""
        self.intelligent_cache.clear()
    
    def get_performance_stats(self):
        """获取性能统计"""
        return {
            'cache': self.intelligent_cache.get_stats(),
            'last_render_times': self._last_render_time.copy()
        }


# 全局快速渲染器实例
_global_fast_renderer = None

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
