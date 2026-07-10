#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内存管理器
提供内存监控和缓存管理功能
"""

import os
import gc
import threading
from typing import Dict, Any, Optional
import weakref


class ImageCacheManager:
    """图像缓存管理器"""
    
    def __init__(self, max_size_mb: int = 500):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.cache: Dict[str, Any] = {}
        self.cache_sizes: Dict[str, int] = {}
        self.access_order = []
        self.current_size = 0
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存项"""
        with self.lock:
            if key in self.cache:
                # 更新访问顺序
                if key in self.access_order:
                    self.access_order.remove(key)
                self.access_order.append(key)
                return self.cache[key]
            return None
    
    def put(self, key: str, value: Any, size_bytes: int = None):
        """添加缓存项"""
        with self.lock:
            # 估算大小
            if size_bytes is None:
                size_bytes = self._estimate_size(value)
            
            # 如果已存在，先移除
            if key in self.cache:
                self.remove(key)
            
            # 确保有足够空间
            while self.current_size + size_bytes > self.max_size_bytes and self.access_order:
                oldest_key = self.access_order[0]
                self.remove(oldest_key)
            
            # 添加新项
            self.cache[key] = value
            self.cache_sizes[key] = size_bytes
            self.access_order.append(key)
            self.current_size += size_bytes
    
    def remove(self, key: str):
        """移除缓存项"""
        with self.lock:
            if key in self.cache:
                size = self.cache_sizes.get(key, 0)
                del self.cache[key]
                del self.cache_sizes[key]
                if key in self.access_order:
                    self.access_order.remove(key)
                self.current_size -= size
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.cache_sizes.clear()
            self.access_order.clear()
            self.current_size = 0
            gc.collect()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.lock:
            return {
                'items': len(self.cache),
                'size_mb': self.current_size / (1024 * 1024),
                'max_size_mb': self.max_size_bytes / (1024 * 1024),
                'usage_percent': (self.current_size / self.max_size_bytes) * 100
            }
    
    def _estimate_size(self, obj) -> int:
        """估算对象大小"""
        try:
            if hasattr(obj, 'size') and hasattr(obj, 'mode'):
                # PIL Image对象
                width, height = obj.size
                channels = len(obj.mode)
                return width * height * channels
            else:
                # 其他对象的粗略估算
                return len(str(obj)) * 2
        except Exception:
            return 1024  # 默认1KB


class MemoryMonitor:
    """内存监控器"""
    
    @staticmethod
    def get_memory_info() -> Dict[str, int]:
        """获取内存信息"""
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                'rss': memory_info.rss,  # 物理内存
                'vms': memory_info.vms,  # 虚拟内存
                'percent': process.memory_percent(),
                'available': psutil.virtual_memory().available
            }
        except ImportError:
            # 回退到系统特定的方法
            return MemoryMonitor._get_system_memory_info()
    
    @staticmethod
    def _get_system_memory_info() -> Dict[str, int]:
        """获取系统内存信息（回退方法）"""
        try:
            if os.name == 'nt':
                return MemoryMonitor._get_windows_memory_info()
            else:
                return MemoryMonitor._get_unix_memory_info()
        except Exception as e:
            print(f"获取内存信息失败: {e}")
            return {'rss': 0, 'vms': 0, 'percent': 0, 'available': 0}
    
    @staticmethod
    def _get_windows_memory_info() -> Dict[str, int]:
        """Windows平台内存信息"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # 获取进程内存信息
            kernel32 = ctypes.windll.kernel32
            process_handle = kernel32.GetCurrentProcess()
            
            # 获取内存状态
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            
            memory_status = MEMORYSTATUSEX()
            memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status))
            
            return {
                'rss': memory_status.ullTotalPhys - memory_status.ullAvailPhys,
                'vms': memory_status.ullTotalVirtual - memory_status.ullAvailVirtual,
                'percent': memory_status.dwMemoryLoad,
                'available': memory_status.ullAvailPhys
            }
            
        except Exception as e:
            print(f"获取Windows内存信息失败: {e}")
            return {'rss': 0, 'vms': 0, 'percent': 0, 'available': 0}
    
    @staticmethod
    def _get_unix_memory_info() -> Dict[str, int]:
        """Unix/Linux平台内存信息"""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            
            # 读取/proc/meminfo获取系统内存信息
            if os.path.exists('/proc/meminfo'):
                with open('/proc/meminfo', 'r') as f:
                    meminfo = f.read()
            else:
                meminfo = ''
            
            mem_total = 0
            mem_available = 0
            for line in meminfo.split('\n'):
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1]) * 1024
                elif line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1]) * 1024
            
            return {
                'rss': usage.ru_maxrss * 1024,  # Linux中ru_maxrss是KB
                'vms': 0,  # 虚拟内存大小不易获取
                'percent': ((mem_total - mem_available) / mem_total) * 100 if mem_total > 0 else 0,
                'available': mem_available
            }
            
        except Exception as e:
            print(f"获取Unix内存信息失败: {e}")
            return {'rss': 0, 'vms': 0, 'percent': 0, 'available': 0}
    
    @staticmethod
    def force_garbage_collection():
        """强制垃圾回收"""
        collected = gc.collect()
        print(f"垃圾回收完成，回收了 {collected} 个对象")
        return collected


# 全局缓存管理器实例
_image_cache_manager = None
_cache_lock = threading.Lock()


def get_image_cache_manager() -> ImageCacheManager:
    """获取全局图像缓存管理器实例"""
    global _image_cache_manager
    
    if _image_cache_manager is None:
        with _cache_lock:
            if _image_cache_manager is None:
                _image_cache_manager = ImageCacheManager()
    
    return _image_cache_manager


def cleanup_memory():
    """清理内存"""
    cache_manager = get_image_cache_manager()
    cache_manager.clear()
    MemoryMonitor.force_garbage_collection()


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            print("[DEBUG] Message encoding failed")
