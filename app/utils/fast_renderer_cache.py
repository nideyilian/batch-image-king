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



class FastRendererCache(object):
    """Mixin for fast_renderer_cache (split from FastRenderer)."""

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

    @staticmethod
    def _resolve_cache_budget_bytes(env_name: str, default_mb: int, minimum_mb: int = 16) -> int:
        try:
            value_mb = int(os.environ.get(env_name, str(default_mb)) or default_mb)
        except Exception:
            value_mb = int(default_mb)
        value_mb = max(int(minimum_mb), int(value_mb))
        return int(value_mb) * 1024 * 1024

    @staticmethod
    def _estimate_image_bytes(image: Optional[Image.Image]) -> int:
        if image is None:
            return 0
        try:
            bands = max(1, len(image.getbands()))
            return int(image.width) * int(image.height) * bands
        except Exception:
            return 0

    def _cached_value_image(self, value):
        if isinstance(value, dict):
            return value.get("image")
        return value

    def _close_cached_value(self, value):
        image = self._cached_value_image(value)
        try:
            if image is not None and hasattr(image, "close"):
                image.close()
        except Exception:
            pass

    def _cache_value_bytes(self, value) -> int:
        if isinstance(value, dict) and "bytes" in value:
            try:
                return int(value.get("bytes") or 0)
            except Exception:
                return 0
        return self._estimate_image_bytes(self._cached_value_image(value))

    def _trim_cache_by_budget_unlocked(
        self,
        cache: OrderedDict,
        entry_bytes: dict,
        total_attr: str,
        max_entries: int,
        max_bytes: int,
    ):
        while cache and (len(cache) > max_entries or int(getattr(self, total_attr, 0)) > int(max_bytes)):
            old_key, old_value = cache.popitem(last=False)
            old_bytes = int(entry_bytes.pop(old_key, self._cache_value_bytes(old_value)) or 0)
            setattr(self, total_attr, max(0, int(getattr(self, total_attr, 0)) - old_bytes))
            self._close_cached_value(old_value)

    def _set_cache_value_unlocked(
        self,
        cache: OrderedDict,
        entry_bytes: dict,
        total_attr: str,
        key,
        value,
        max_entries: int,
        max_bytes: int,
    ):
        old_value = cache.pop(key, None)
        if old_value is not None:
            old_bytes = int(entry_bytes.pop(key, self._cache_value_bytes(old_value)) or 0)
            setattr(self, total_attr, max(0, int(getattr(self, total_attr, 0)) - old_bytes))
            self._close_cached_value(old_value)

        value_bytes = self._cache_value_bytes(value)
        cache[key] = value
        entry_bytes[key] = value_bytes
        setattr(self, total_attr, int(getattr(self, total_attr, 0)) + value_bytes)
        cache.move_to_end(key)
        self._trim_cache_by_budget_unlocked(cache, entry_bytes, total_attr, max_entries, max_bytes)

    def _remove_cache_keys_unlocked(self, cache: OrderedDict, entry_bytes: dict, total_attr: str, keys):
        for key in keys:
            old_value = cache.pop(key, None)
            if old_value is None:
                continue
            old_bytes = int(entry_bytes.pop(key, self._cache_value_bytes(old_value)) or 0)
            setattr(self, total_attr, max(0, int(getattr(self, total_attr, 0)) - old_bytes))
            self._close_cached_value(old_value)

    def _clear_budgeted_cache_unlocked(self, cache: OrderedDict, entry_bytes: dict, total_attr: str):
        for value in list(cache.values()):
            self._close_cached_value(value)
        cache.clear()
        entry_bytes.clear()
        setattr(self, total_attr, 0)
    
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
    
