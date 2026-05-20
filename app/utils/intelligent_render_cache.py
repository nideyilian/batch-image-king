"""
智能渲染缓存系统
整合和优化现有的缓存机制，提供统一、高效的缓存解决方案
"""

import time
import hashlib
import threading
import os
import weakref
import gc
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass
from collections import OrderedDict
from PIL import Image
import numpy as np


@dataclass
class CacheEntry:
    """缓存条目"""
    image: Image.Image
    cache_key: str
    full_key: str
    creation_time: float
    last_access: float
    access_count: int
    memory_size: int
    render_time: float
    quality_level: str  # 'preview', 'batch', 'export'
    
    def update_access(self):
        """更新访问信息"""
        self.last_access = time.time()
        self.access_count += 1


@dataclass
class CacheStats:
    """缓存统计信息"""
    total_entries: int
    memory_usage_mb: float
    hit_count: int
    miss_count: int
    hit_rate: float
    avg_render_time: float
    cache_efficiency: float


class AdaptiveCacheStrategy:
    """自适应缓存策略"""
    
    @staticmethod
    def calculate_cache_priority(entry: CacheEntry) -> float:
        """计算缓存优先级，数值越高优先级越高"""
        now = time.time()
        
        # 基础分数
        score = 100.0
        
        # 访问频率加分（访问次数越多分数越高）
        score += min(entry.access_count * 10, 50)
        
        # 时间衰减（越新的越有价值）
        age_hours = (now - entry.creation_time) / 3600
        if age_hours < 1:  # 1小时内
            score += 30
        elif age_hours < 6:  # 6小时内
            score += 15
        elif age_hours > 24:  # 超过24小时
            score -= 20
        
        # 最近访问加分
        last_access_hours = (now - entry.last_access) / 3600
        if last_access_hours < 0.5:  # 30分钟内
            score += 25
        elif last_access_hours < 2:  # 2小时内
            score += 10
        elif last_access_hours > 12:  # 超过12小时未访问
            score -= 15
        
        # 质量级别加分
        quality_bonus = {
            'export': 20,  # 导出质量最重要
            'batch': 15,   # 批量处理次之
            'preview': 10  # 预览最低
        }
        score += quality_bonus.get(entry.quality_level, 0)
        
        # 内存效率考虑（小图像优先保留）
        if entry.memory_size < 1024 * 1024:  # 小于1MB
            score += 10
        elif entry.memory_size > 10 * 1024 * 1024:  # 大于10MB
            score -= 15
        
        return max(score, 1.0)  # 确保分数为正
    
    @staticmethod
    def should_cache_result(render_time: float, image_size: Tuple[int, int], 
                          quality_level: str) -> bool:
        """判断是否应该缓存渲染结果"""
        width, height = image_size
        pixel_count = width * height
        
        # 渲染时间长的优先缓存
        if render_time > 0.5:  # 渲染超过0.5秒
            return True
        
        # 大图像优先缓存
        if pixel_count > 1000000:  # 1MP以上
            return True
        
        # 导出质量一定要缓存
        if quality_level == 'export':
            return True
        
        # 预览也允许缓存，减少频繁重绘卡顿
        if quality_level == 'preview' and render_time < 0.03:
            return True
        
        return True


class IntelligentRenderCache:
    """智能渲染缓存系统"""
    
    def __init__(self, max_memory_mb: int = 512, max_entries: int = 100):
        """
        初始化智能缓存
        
        Args:
            max_memory_mb: 最大内存使用量（MB）
            max_entries: 最大缓存条目数
        """
        self.max_memory = max_memory_mb * 1024 * 1024  # 转换为字节
        self.max_entries = max_entries
        
        # 缓存存储
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        
        # 统计信息
        self._hits = 0
        self._misses = 0
        self._memory_usage = 0
        self._total_render_time = 0.0
        self._render_count = 0
        
        # 自适应策略
        self._strategy = AdaptiveCacheStrategy()
        
        # 缓存清理设置
        self._cleanup_threshold = 0.85  # 内存使用率超过85%时清理
        self._target_memory_ratio = 0.70  # 清理到70%内存使用率
        
        self._verbose_logging = False
        if self._verbose_logging:
            print(f"[智能缓存] 初始化完成，最大内存: {max_memory_mb}MB，最大条目数: {max_entries}")
    
    def _generate_cache_key(self, document, quality_level: str = 'preview') -> Tuple[str, str]:
        """生成缓存键"""
        try:
            key_parts = [
                f"canvas:{document.canvas_width}x{document.canvas_height}",
                f"quality:{quality_level}"
            ]
            
            # 遍历所有可见图层
            for i, layer in enumerate(document.layers):
                if not layer.visible:
                    continue
                
                layer_parts = [
                    f"layer{i}",
                    f"pos:{getattr(layer, 'x', 0)},{getattr(layer, 'y', 0)}",
                    f"size:{getattr(layer, 'width', 100)}x{getattr(layer, 'height', 100)}",
                    f"opacity:{getattr(layer, 'opacity', 1.0):.3f}"
                ]
                
                # 图像源信息
                image_source = getattr(layer, 'image_source', None) or getattr(layer, '_image_source', None)
                if image_source:
                    source_hash = hashlib.md5(str(image_source).encode()).hexdigest()[:8]
                    layer_parts.append(f"src:{source_hash}")
                
                # 当前图像路径（对于随机图像）
                if hasattr(layer, 'current_image_path') and layer.current_image_path:
                    img_name = os.path.basename(layer.current_image_path)
                    img_hash = hashlib.md5(img_name.encode()).hexdigest()[:6]
                    layer_parts.append(f"img:{img_hash}")
                
                # 随机变换参数
                if hasattr(layer, '_current_random_offset_x'):
                    layer_parts.append(f"rnd_pos:{getattr(layer, '_current_random_offset_x', 0)},{getattr(layer, '_current_random_offset_y', 0)}")
                if hasattr(layer, '_current_random_scale'):
                    layer_parts.append(f"rnd_scale:{getattr(layer, '_current_random_scale', 1.0):.3f}")
                if hasattr(layer, '_current_random_rotation'):
                    layer_parts.append(f"rnd_rot:{getattr(layer, '_current_random_rotation', 0.0):.1f}")
                
                # 特效参数
                if hasattr(layer, 'blend_mode'):
                    layer_parts.append(f"blend:{getattr(layer, 'blend_mode', 0)}")
                
                # 🔧 修复：添加圆角参数
                if hasattr(layer, 'corner_radius') and getattr(layer, 'corner_radius', 0) > 0:
                    layer_parts.append(f"radius:{getattr(layer, 'corner_radius', 0)}")

                # 🔧 关键修复：加入形状相关参数，确保切换形状时缓存失效
                try:
                    if hasattr(layer, 'shape_type'):
                        st = getattr(layer, 'shape_type')
                        # 兼容枚举/字符串
                        st_val = st.value if hasattr(st, 'value') else str(st)
                        layer_parts.append(f"shape:{st_val}")
                        # 梯形参数
                        if hasattr(layer, 'trapezoid_top_width'):
                            layer_parts.append(f"trap_top:{getattr(layer, 'trapezoid_top_width', 100)}")
                        if hasattr(layer, 'trapezoid_bottom_width'):
                            layer_parts.append(f"trap_bottom:{getattr(layer, 'trapezoid_bottom_width', 100)}")
                        if hasattr(layer, 'trapezoid_slope_side'):
                            layer_parts.append(f"trap_side:{getattr(layer, 'trapezoid_slope_side', 'right')}")
                        # 多边形参数
                        if hasattr(layer, 'polygon_rotation'):
                            layer_parts.append(f"poly_rot:{getattr(layer, 'polygon_rotation', 0.0):.1f}")
                        if hasattr(layer, 'polygon_corner_radius'):
                            layer_parts.append(f"poly_radius:{getattr(layer, 'polygon_corner_radius', 0)}")
                except Exception:
                    pass
                
                # 🔧 修复：添加描边参数到缓存键
                if hasattr(layer, 'stroke_enabled') and getattr(layer, 'stroke_enabled', False):
                    stroke_width = getattr(layer, 'stroke_width', 1)
                    stroke_type = getattr(layer, 'stroke_type', 0)
                    stroke_color = getattr(layer, 'stroke_color', (0, 0, 0, 255))
                    # 将颜色元组转换为简短的哈希
                    color_str = f"{stroke_color[0]},{stroke_color[1]},{stroke_color[2]},{stroke_color[3]}"
                    layer_parts.append(f"stroke:{stroke_width}:{stroke_type}:{color_str}")
                
                # 分身与镜像参数
                if hasattr(layer, 'clone_enabled'):
                    layer_parts.append(f"clone:{int(getattr(layer, 'clone_enabled', False))}")
                if hasattr(layer, 'clone_rows'):
                    layer_parts.append(f"rows:{getattr(layer, 'clone_rows', 1)}")
                if hasattr(layer, 'clone_columns'):
                    layer_parts.append(f"cols:{getattr(layer, 'clone_columns', 1)}")
                if hasattr(layer, 'clone_row_spacing'):
                    layer_parts.append(f"rspace:{getattr(layer, 'clone_row_spacing', 0)}")
                if hasattr(layer, 'clone_column_spacing'):
                    layer_parts.append(f"cspace:{getattr(layer, 'clone_column_spacing', 0)}")
                if hasattr(layer, 'clone_mirror_mode'):
                    layer_parts.append(f"mirror:{getattr(layer, 'clone_mirror_mode', 'none')}")
                if hasattr(layer, 'clone_fill_enabled'):
                    layer_parts.append(f"fill:{int(getattr(layer, 'clone_fill_enabled', False))}")
                if hasattr(layer, 'clone_fill_mode'):
                    layer_parts.append(f"fillmode:{getattr(layer, 'clone_fill_mode', 'grid')}")
                if hasattr(layer, 'clone_fill_spacing'):
                    layer_parts.append(f"fillsp:{getattr(layer, 'clone_fill_spacing', 0)}")
                if hasattr(layer, 'clone_fill_angle'):
                    layer_parts.append(f"fillang:{int(getattr(layer, 'clone_fill_angle', 0.0))}")

                # 文字图层特殊处理（修复：竖排等排版参数变化需触发缓存失效）
                if hasattr(layer, 'current_text'):
                    text_value = getattr(layer, 'current_text', '') or ''
                    text_hash = hashlib.md5(text_value.encode('utf-8')).hexdigest()[:8]
                    layer_parts.append(f"text:{text_hash}")
                    layer_parts.append(f"font:{getattr(layer, 'font_family', '')}")
                    layer_parts.append(f"fs:{getattr(layer, 'font_size', 0)}")
                    layer_parts.append(f"fst:{getattr(layer, 'font_style', '')}")
                    layer_parts.append(f"align:{getattr(layer, 'text_align', '')}")
                    layer_parts.append(f"ls:{getattr(layer, 'line_spacing', 1.0)}")
                    layer_parts.append(f"cs:{getattr(layer, 'letter_spacing', 0)}")
                    layer_parts.append(f"vertical:{int(bool(getattr(layer, 'vertical_layout', False)))}")
                    layer_parts.append(f"autofit:{int(bool(getattr(layer, 'auto_fit_text_box', False)))}")
                    layer_parts.append(f"pad:{int(getattr(layer, 'text_box_padding', 0))}")
                
                key_parts.append(":".join(layer_parts))
            
            # 生成最终键值
            key_string = "|".join(key_parts)
            cache_key = hashlib.md5(key_string.encode()).hexdigest()[:16]
            
            return cache_key, key_string
            
        except Exception as e:
            print(f"[智能缓存] 缓存键生成失败: {e}")
            # 回退方案：使用时间戳确保唯一性
            fallback = f"fallback_{time.time():.6f}_{quality_level}"
            return fallback, fallback
    
    def _estimate_image_memory(self, image: Image.Image) -> int:
        """估算图像内存占用"""
        if not image:
            return 0
        
        # 计算像素数量
        width, height = image.size
        channels = len(image.getbands())
        
        # 估算内存使用（字节）
        memory_size = width * height * channels
        
        # 考虑PIL内部开销，增加25%
        return int(memory_size * 1.25)
    
    def _smart_cleanup(self):
        """智能缓存清理"""
        if self._verbose_logging:
            print(f"[智能缓存] 开始智能清理，当前条目数: {len(self._cache)}")
        
        if not self._cache:
            return
        
        # 计算所有条目的优先级
        priorities = []
        for key, entry in self._cache.items():
            priority = self._strategy.calculate_cache_priority(entry)
            priorities.append((priority, key, entry))
        
        # 按优先级排序（优先级低的先删除）
        priorities.sort(key=lambda x: x[0])
        
        # 计算需要清理的内存量
        target_memory = int(self.max_memory * self._target_memory_ratio)
        memory_to_free = self._memory_usage - target_memory
        
        # 清理低优先级条目
        freed_memory = 0
        removed_count = 0
        
        for priority, key, entry in priorities:
            if freed_memory >= memory_to_free and len(self._cache) <= self.max_entries * 0.8:
                break
            
            # 删除条目
            if key in self._cache:
                del self._cache[key]
                freed_memory += entry.memory_size
                self._memory_usage -= entry.memory_size
                removed_count += 1
        
        if self._verbose_logging:
            print(f"[智能缓存] 清理完成，删除{removed_count}个条目，释放{freed_memory/(1024*1024):.1f}MB内存")
        
        # 强制垃圾收集
        gc.collect()
    
    def get(self, document, quality_level: str = 'preview') -> Optional[Image.Image]:
        """获取缓存图像"""
        with self._lock:
            cache_key, _ = self._generate_cache_key(document, quality_level)
            
            if cache_key in self._cache:
                entry = self._cache[cache_key]
                entry.update_access()
                
                # 移到末尾（LRU策略）
                self._cache.move_to_end(cache_key)
                
                self._hits += 1
                if self._verbose_logging:
                    print(f"[智能缓存] 缓存命中: {cache_key[:12]}..., 访问次数: {entry.access_count}")
                
                # 返回图像副本（防止外部修改）
                return entry.image.copy()
            
            self._misses += 1
            return None
    
    def put(self, document, image: Image.Image, render_time: float, 
            quality_level: str = 'preview') -> bool:
        """存储图像到缓存"""
        if not image:
            return False
        
        # 检查是否应该缓存
        if not self._strategy.should_cache_result(render_time, image.size, quality_level):
            if self._verbose_logging:
                print(f"[智能缓存] 跳过缓存: 渲染时间{render_time:.3f}s，尺寸{image.size}，质量{quality_level}")
            return False
        
        with self._lock:
            cache_key, full_key = self._generate_cache_key(document, quality_level)
            memory_size = self._estimate_image_memory(image)
            
            # 检查内存限制
            if memory_size > self.max_memory * 0.5:  # 单个图像不能超过总内存的50%
                if self._verbose_logging:
                    print(f"[智能缓存] 图像过大，跳过缓存: {memory_size/(1024*1024):.1f}MB")
                return False
            
            # 如果超过内存阈值，执行清理
            if (self._memory_usage + memory_size) > (self.max_memory * self._cleanup_threshold) or \
               len(self._cache) >= self.max_entries:
                self._smart_cleanup()
            
            # 创建缓存条目
            entry = CacheEntry(
                image=image.copy(),
                cache_key=cache_key,
                full_key=full_key,
                creation_time=time.time(),
                last_access=time.time(),
                access_count=1,
                memory_size=memory_size,
                render_time=render_time,
                quality_level=quality_level
            )
            
            # 如果键已存在，更新内存统计
            if cache_key in self._cache:
                old_entry = self._cache[cache_key]
                self._memory_usage -= old_entry.memory_size
            
            # 存储条目
            self._cache[cache_key] = entry
            self._memory_usage += memory_size
            
            # 更新统计
            self._total_render_time += render_time
            self._render_count += 1
            
            if self._verbose_logging:
                print(f"[智能缓存] 存储成功: {cache_key[:12]}..., 内存: {memory_size/(1024*1024):.1f}MB, "
                      f"总使用: {self._memory_usage/(1024*1024):.1f}MB")
            
            return True
    
    def invalidate_document(self, document):
        """使文档相关的缓存失效"""
        with self._lock:
            # 生成文档标识
            doc_prefix = f"canvas:{document.canvas_width}x{document.canvas_height}"
            
            keys_to_remove = []
            for key, entry in self._cache.items():
                # 简单检查：如果缓存键包含文档信息，则删除
                if doc_prefix in entry.full_key or self._is_document_related(entry, document):
                    keys_to_remove.append(key)
            
            # 删除相关缓存
            removed_memory = 0
            for key in keys_to_remove:
                if key in self._cache:
                    entry = self._cache[key]
                    removed_memory += entry.memory_size
                    self._memory_usage -= entry.memory_size
                    del self._cache[key]
            
            if keys_to_remove and self._verbose_logging:
                print(f"[智能缓存] 文档缓存失效: 删除{len(keys_to_remove)}个条目，"
                      f"释放{removed_memory/(1024*1024):.1f}MB内存")
    
    def _is_document_related(self, entry: CacheEntry, document) -> bool:
        """检查缓存条目是否与文档相关"""
        # 简单的关联检查，可以根据需要扩展
        try:
            # 这里可以实现更复杂的关联逻辑
            return False
        except:
            return False
    
    def clear(self):
        """清空所有缓存"""
        with self._lock:
            entry_count = len(self._cache)
            memory_freed = self._memory_usage
            
            self._cache.clear()
            self._memory_usage = 0
            
            if self._verbose_logging:
                print(f"[智能缓存] 清空完成: 删除{entry_count}个条目，释放{memory_freed/(1024*1024):.1f}MB内存")
    
    def get_stats(self) -> CacheStats:
        """获取缓存统计信息"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            avg_render_time = (self._total_render_time / self._render_count) if self._render_count > 0 else 0
            
            # 计算缓存效率（命中率 * 平均节省时间）
            cache_efficiency = hit_rate * avg_render_time / 100
            
            return CacheStats(
                total_entries=len(self._cache),
                memory_usage_mb=self._memory_usage / (1024 * 1024),
                hit_count=self._hits,
                miss_count=self._misses,
                hit_rate=hit_rate,
                avg_render_time=avg_render_time,
                cache_efficiency=cache_efficiency
            )
    
    def optimize_cache(self):
        """主动优化缓存"""
        with self._lock:
            print("[智能缓存] 开始主动优化...")
            
            before_stats = self.get_stats()
            
            # 执行智能清理
            if self._memory_usage > self.max_memory * 0.6:  # 超过60%使用率
                self._smart_cleanup()
            
            # 清理过期条目（超过24小时未访问）
            current_time = time.time()
            expired_keys = []
            
            for key, entry in self._cache.items():
                hours_since_access = (current_time - entry.last_access) / 3600
                if hours_since_access > 24:
                    expired_keys.append(key)
            
            for key in expired_keys:
                if key in self._cache:
                    entry = self._cache[key]
                    self._memory_usage -= entry.memory_size
                    del self._cache[key]
            
            if expired_keys:
                print(f"[智能缓存] 清理过期条目: {len(expired_keys)}个")
            
            after_stats = self.get_stats()
            print(f"[智能缓存] 优化完成: 内存使用 {before_stats.memory_usage_mb:.1f}MB -> {after_stats.memory_usage_mb:.1f}MB")


# 全局缓存实例
_global_cache = None

def get_intelligent_cache() -> IntelligentRenderCache:
    """获取全局智能缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = IntelligentRenderCache(max_memory_mb=512, max_entries=100)
    return _global_cache


def optimize_global_cache():
    """优化全局缓存"""
    cache = get_intelligent_cache()
    cache.optimize_cache()


def clear_global_cache():
    """清空全局缓存"""
    cache = get_intelligent_cache()
    cache.clear()


def get_cache_stats() -> CacheStats:
    """获取全局缓存统计"""
    cache = get_intelligent_cache()
    return cache.get_stats()
