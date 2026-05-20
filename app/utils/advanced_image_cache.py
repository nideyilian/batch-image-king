"""
高级图像缓存系统
智能缓存策略，大幅提升图像处理性能
"""

import os
import time
import hashlib
import threading
from typing import Dict, Optional, Tuple, Any, List
from dataclasses import dataclass
from collections import OrderedDict
from PIL import Image
import weakref
import gc

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        safe_print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            safe_print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            safe_print("[DEBUG] Message encoding failed")



@dataclass
class CacheEntry:
    """缓存条目"""
    image: Image.Image
    file_path: str
    file_mtime: float
    effects_hash: str
    access_count: int
    last_access: float
    memory_size: int
    creation_time: float


@dataclass
class CacheStats:
    """缓存统计"""
    total_entries: int
    total_memory_mb: float
    hit_count: int
    miss_count: int
    hit_rate: float
    eviction_count: int
    avg_access_time: float


class AdvancedImageCache:
    """高级图像缓存系统"""
    
    def __init__(self, max_memory_mb: int = 1024, max_entries: int = 1000):
        self.max_memory = max_memory_mb * 1024 * 1024
        self.max_entries = max_entries
        
        # 缓存存储
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.current_memory = 0
        
        # 统计信息
        self.hit_count = 0
        self.miss_count = 0
        self.eviction_count = 0
        self.access_times = []
        
        # 线程安全
        self.lock = threading.RLock()
        
        # 自动清理
        self.cleanup_timer = threading.Timer(60.0, self._periodic_cleanup)
        # 恢复为守护线程，防止进程残留
        self.cleanup_timer.daemon = True
        self.cleanup_timer.start()
        
        safe_print(f"[高级缓存] 初始化完成，最大内存: {max_memory_mb}MB, 最大条目: {max_entries}")
    
    def get_cached_image(self, file_path: str, effects_params: Dict[str, Any] = None) -> Optional[Image.Image]:
        """获取缓存的图像"""
        start_time = time.time()
        
        try:
            with self.lock:
                # 生成缓存键
                cache_key = self._generate_cache_key(file_path, effects_params)
                
                # 检查文件是否存在和修改时间
                if not os.path.exists(file_path):
                    return None
                
                file_mtime = os.path.getmtime(file_path)
                
                # 查找缓存条目
                if cache_key in self.cache:
                    entry = self.cache[cache_key]
                    
                    # 检查文件是否被修改
                    if entry.file_mtime == file_mtime:
                        # 缓存命中
                        self._update_access_info(cache_key, entry)
                        self.hit_count += 1
                        
                        access_time = time.time() - start_time
                        self.access_times.append(access_time)
                        if len(self.access_times) > 1000:
                            self.access_times = self.access_times[-500:]
                        
                        safe_print(f"[高级缓存] 缓存命中: {os.path.basename(file_path)}")
                        return entry.image.copy()  # 返回副本避免修改缓存
                    else:
                        # 文件已修改，移除过期缓存
                        self._remove_entry(cache_key)
                        safe_print(f"[高级缓存] 文件已修改，移除过期缓存: {os.path.basename(file_path)}")
                
                # 缓存未命中
                self.miss_count += 1
                return None
                
        except Exception as e:
            safe_print(f"[高级缓存] 获取缓存图像失败: {e}")
            return None
    
    def cache_image(self, file_path: str, image: Image.Image, effects_params: Dict[str, Any] = None):
        """缓存图像"""
        try:
            with self.lock:
                # 生成缓存键
                cache_key = self._generate_cache_key(file_path, effects_params)
                
                # 检查文件信息
                if not os.path.exists(file_path):
                    return
                
                file_mtime = os.path.getmtime(file_path)
                effects_hash = self._hash_effects(effects_params)
                
                # 计算图像内存大小
                memory_size = self._calculate_image_size(image)
                
                # 检查是否需要清理空间
                self._ensure_space(memory_size)
                
                # 创建缓存条目
                entry = CacheEntry(
                    image=image.copy(),  # 存储副本
                    file_path=file_path,
                    file_mtime=file_mtime,
                    effects_hash=effects_hash,
                    access_count=1,
                    last_access=time.time(),
                    memory_size=memory_size,
                    creation_time=time.time()
                )
                
                # 添加到缓存
                self.cache[cache_key] = entry
                self.current_memory += memory_size
                
                safe_print(f"[高级缓存] 缓存图像: {os.path.basename(file_path)}, 大小: {memory_size/1024/1024:.2f}MB")
                
        except Exception as e:
            safe_print(f"[高级缓存] 缓存图像失败: {e}")
    
    def _generate_cache_key(self, file_path: str, effects_params: Dict[str, Any] = None) -> str:
        """生成缓存键"""
        # 使用文件路径和效果参数生成唯一键
        key_parts = [file_path]
        
        if effects_params:
            # 将效果参数转换为稳定的字符串
            effects_str = self._serialize_effects(effects_params)
            key_parts.append(effects_str)
        
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _serialize_effects(self, effects_params: Dict[str, Any]) -> str:
        """序列化效果参数"""
        if not effects_params:
            return ""
        
        # 排序键以确保一致性
        sorted_items = sorted(effects_params.items())
        
        # 转换为字符串
        parts = []
        for key, value in sorted_items:
            if isinstance(value, (int, float, str, bool)):
                parts.append(f"{key}:{value}")
            elif isinstance(value, (list, tuple)):
                parts.append(f"{key}:{','.join(map(str, value))}")
            elif isinstance(value, dict):
                parts.append(f"{key}:{self._serialize_effects(value)}")
        
        return "|".join(parts)
    
    def _hash_effects(self, effects_params: Dict[str, Any] = None) -> str:
        """计算效果参数的哈希值"""
        if not effects_params:
            return ""
        
        effects_str = self._serialize_effects(effects_params)
        return hashlib.md5(effects_str.encode()).hexdigest()[:16]
    
    def _calculate_image_size(self, image: Image.Image) -> int:
        """计算图像内存大小"""
        if image is None:
            return 0
        
        # 计算像素数据大小
        width, height = image.size
        channels = len(image.getbands())
        
        # 假设每个通道1字节
        return width * height * channels
    
    def _update_access_info(self, cache_key: str, entry: CacheEntry):
        """更新访问信息"""
        entry.access_count += 1
        entry.last_access = time.time()
        
        # 移动到末尾（LRU）
        self.cache.move_to_end(cache_key)
    
    def _ensure_space(self, required_size: int):
        """确保有足够的缓存空间"""
        # 检查条目数量限制
        while len(self.cache) >= self.max_entries:
            self._evict_lru_entry()
        
        # 检查内存限制
        while (self.current_memory + required_size) > self.max_memory and self.cache:
            self._evict_lru_entry()
    
    def _evict_lru_entry(self):
        """驱逐最近最少使用的条目"""
        if not self.cache:
            return
        
        # 获取最旧的条目
        cache_key, entry = self.cache.popitem(last=False)
        self.current_memory -= entry.memory_size
        self.eviction_count += 1
        
        safe_print(f"[高级缓存] 驱逐条目: {os.path.basename(entry.file_path)}, "
              f"访问次数: {entry.access_count}")
    
    def _remove_entry(self, cache_key: str):
        """移除指定条目"""
        if cache_key in self.cache:
            entry = self.cache.pop(cache_key)
            self.current_memory -= entry.memory_size
    
    def _periodic_cleanup(self):
        """定期清理"""
        try:
            with self.lock:
                self._cleanup_expired_entries()
                self._optimize_cache()
            
            # 重新启动定时器
            self.cleanup_timer = threading.Timer(60.0, self._periodic_cleanup)
            # 恢复为守护线程，防止进程残留
            self.cleanup_timer.daemon = True
            self.cleanup_timer.start()
            
        except Exception as e:
            safe_print(f"[高级缓存] 定期清理失败: {e}")
    
    def _cleanup_expired_entries(self):
        """清理过期条目"""
        current_time = time.time()
        expired_keys = []
        
        for cache_key, entry in self.cache.items():
            # 检查文件是否还存在
            if not os.path.exists(entry.file_path):
                expired_keys.append(cache_key)
                continue
            
            # 检查文件是否被修改
            try:
                file_mtime = os.path.getmtime(entry.file_path)
                if file_mtime != entry.file_mtime:
                    expired_keys.append(cache_key)
                    continue
            except:
                expired_keys.append(cache_key)
                continue
            
            # 检查是否长时间未访问（超过1小时）
            if current_time - entry.last_access > 3600:
                if entry.access_count <= 1:  # 只访问过一次的条目
                    expired_keys.append(cache_key)
        
        # 移除过期条目
        for cache_key in expired_keys:
            self._remove_entry(cache_key)
        
        if expired_keys:
            safe_print(f"[高级缓存] 清理过期条目: {len(expired_keys)} 个")
    
    def _optimize_cache(self):
        """优化缓存"""
        # 如果内存使用超过80%，主动清理一些条目
        if self.current_memory > self.max_memory * 0.8:
            # 按访问频率排序，移除访问频率最低的条目
            entries_by_frequency = sorted(
                self.cache.items(),
                key=lambda x: x[1].access_count / max(1, time.time() - x[1].creation_time)
            )
            
            # 移除最低频率的10%条目
            remove_count = max(1, len(entries_by_frequency) // 10)
            for i in range(remove_count):
                cache_key, _ = entries_by_frequency[i]
                self._remove_entry(cache_key)
            
            safe_print(f"[高级缓存] 优化清理: {remove_count} 个低频条目")
        
        # 强制垃圾回收
        gc.collect()
    
    def get_stats(self) -> CacheStats:
        """获取缓存统计"""
        with self.lock:
            total_requests = self.hit_count + self.miss_count
            hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
            
            avg_access_time = (sum(self.access_times) / len(self.access_times) * 1000) if self.access_times else 0
            
            return CacheStats(
                total_entries=len(self.cache),
                total_memory_mb=self.current_memory / 1024 / 1024,
                hit_count=self.hit_count,
                miss_count=self.miss_count,
                hit_rate=hit_rate,
                eviction_count=self.eviction_count,
                avg_access_time=avg_access_time
            )
    
    def clear_cache(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.current_memory = 0
            safe_print("[高级缓存] 缓存已清空")
    
    def preload_images(self, file_paths: List[str], effects_params: Dict[str, Any] = None):
        """预加载图像"""
        safe_print(f"[高级缓存] 开始预加载 {len(file_paths)} 张图像")
        
        for file_path in file_paths:
            try:
                if not self.get_cached_image(file_path, effects_params):
                    with Image.open(file_path) as img:
                        image = img.copy()
                    self.cache_image(file_path, image, effects_params)
            except Exception as e:
                safe_print(f"[高级缓存] 预加载失败: {file_path}, 错误: {e}")
        
        safe_print(f"[高级缓存] 预加载完成")
    
    def shutdown(self):
        """关闭缓存系统"""
        try:
            if hasattr(self, 'cleanup_timer'):
                self.cleanup_timer.cancel()
            
            with self.lock:
                self.cache.clear()
                self.current_memory = 0
            
            safe_print("[高级缓存] 缓存系统已关闭")
            
        except Exception as e:
            safe_print(f"[高级缓存] 关闭缓存系统失败: {e}")


# 全局缓存实例
_global_image_cache = None

def get_advanced_image_cache() -> AdvancedImageCache:
    """获取全局高级图像缓存"""
    global _global_image_cache
    if _global_image_cache is None:
        _global_image_cache = AdvancedImageCache()
    return _global_image_cache

def shutdown_advanced_image_cache():
    """关闭全局高级图像缓存"""
    global _global_image_cache
    if _global_image_cache is not None:
        _global_image_cache.shutdown()
        _global_image_cache = None
