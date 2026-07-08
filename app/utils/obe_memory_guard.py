# -*- coding: utf-8 -*-
"""Optimized batch executor components."""

import logging

logger = logging.getLogger(__name__)
from __future__ import annotations

import os as os_module  # 避免局部变量遮蔽
import time
import threading
import builtins
from collections import Counter, OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from PIL import Image
import gc
import io
import math

class OptimizedBatchExecutorMemoryGuard(object):
    def _estimate_single_task_memory_mb(self) -> float:
        """估算单个导出任务在渲染+写盘阶段的大致峰值内存占用。"""
        try:
            width = max(1, int(getattr(self.document, 'canvas_width', 0) or 0))
            height = max(1, int(getattr(self.document, 'canvas_height', 0) or 0))
            visible_layers = max(1, len([layer for layer in getattr(self.document, 'layers', []) if getattr(layer, 'visible', True)]))
            canvas_rgba_mb = (width * height * 4) / (1024 * 1024)
            # 渲染中间态 + 对象开销保守系数，避免高并发时误判过低
            overhead_factor = 1.8 + min(1.6, visible_layers * 0.08)
            return max(8.0, canvas_rgba_mb * overhead_factor)
        except Exception:
            return 24.0

    def _get_process_rss_mb(self) -> float:
        """返回当前进程 RSS 内存，失败时返回最近一次值。"""
        try:
            import psutil
            rss_mb = float(psutil.Process().memory_info().rss) / (1024 * 1024)
        except Exception:
            rss_mb = float(getattr(self, '_last_memory_rss_mb', 0.0) or 0.0)
        self._last_memory_rss_mb = rss_mb
        with self._lock:
            self.stats['memory_current_mb'] = rss_mb
            self.stats['memory_peak_mb'] = max(float(self.stats.get('memory_peak_mb', 0.0) or 0.0), rss_mb)
            self.stats['peak_memory_mb'] = max(float(self.stats.get('peak_memory_mb', 0.0) or 0.0), rss_mb)
        return rss_mb

    def _refresh_memory_budget(self, force: bool = False) -> float:
        """计算并缓存本次批导的进程级内存预算。"""
        now = time.time()
        if (not force) and self._memory_budget_limit_mb > 0:
            return float(self._memory_budget_limit_mb)
        self._last_memory_check_ts = now

        rss_mb = self._get_process_rss_mb()
        mode = str(getattr(self, '_export_memory_guard_mode', 'auto') or 'auto').lower()
        if mode == 'off':
            self._memory_budget_limit_mb = 0.0
            with self._lock:
                self.stats['memory_limit_mb'] = 0.0
            return 0.0

        try:
            import psutil
            vm = psutil.virtual_memory()
            total_mb = float(vm.total) / (1024 * 1024)
            available_mb = float(vm.available) / (1024 * 1024)
        except Exception:
            total_mb = max(4096.0, rss_mb * 2.0)
            available_mb = max(1024.0, rss_mb)

        reserve_mb = float(getattr(self, '_export_memory_reserve_mb', 2048) or 2048)
        available_for_growth = max(256.0, available_mb - reserve_mb)
        task_floor_mb = max(384.0, self._estimate_single_task_memory_mb() * 1.6)

        if mode == 'custom' and self._export_memory_limit_mb > 0:
            requested_limit = float(self._export_memory_limit_mb)
            # 自定义值低于当前基线时仍允许导出继续，但会立刻降到最低并发。
            limit_mb = max(requested_limit, rss_mb + task_floor_mb)
            if limit_mb > requested_limit and not self._memory_budget_warning_printed:
                self._memory_budget_warning_printed = True
                if self.is_batch_mode:
                    print(
                        f"[批处理] 自定义内存限制 {requested_limit:.0f}MB 低于当前运行基线，"
                        f"本次临时使用有效限制 {limit_mb:.0f}MB"
                    )
        elif mode == 'low':
            limit_mb = rss_mb + max(512.0, min(1024.0, available_for_growth * 0.25))
            limit_mb = min(limit_mb, max(task_floor_mb, total_mb * 0.35))
        else:
            limit_mb = rss_mb + max(768.0, available_for_growth * 0.45)
            limit_mb = min(limit_mb, max(task_floor_mb, total_mb * 0.55))

        self._memory_budget_limit_mb = max(task_floor_mb, float(limit_mb))
        with self._lock:
            self.stats['memory_limit_mb'] = float(self._memory_budget_limit_mb)
            self.stats['memory_requested_limit_mb'] = float(self._export_memory_limit_mb or 0)
            self.stats['memory_guard_mode'] = mode
        return float(self._memory_budget_limit_mb)

    def _memory_pressure_ratio(self) -> float:
        limit_mb = self._refresh_memory_budget()
        if limit_mb <= 0:
            return 0.0
        return self._get_process_rss_mb() / max(1.0, limit_mb)

    def _clear_memory_pressure_caches(self):
        """内存压力下清理批导可丢弃缓存。"""
        cleared = False
        try:
            if getattr(self, '_image_preload_cache', None):
                self._clear_preload_cache()
                cleared = True
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass
        try:
            if getattr(self, '_render_cache', None):
                self._render_cache.clear()
                cleared = True
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass
        try:
            if self._clear_registered_worker_renderer_caches() > 0:
                cleared = True
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass
        try:
            gc.collect()
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass
        if cleared:
            with self._lock:
                self.stats['memory_cache_clear_events'] += 1

    def _register_worker_renderer(self, renderer):
        """Track every worker FastRenderer so memory pressure can clear all of them."""
        if renderer is None:
            return renderer
        try:
            renderer_id = id(renderer)
            with self._worker_renderers_lock:
                if renderer_id not in self._worker_renderer_ids:
                    self._worker_renderer_ids.add(renderer_id)
                    self._worker_renderers.append(renderer)
                    renderer_count = len(self._worker_renderers)
                else:
                    renderer_count = len(self._worker_renderers)
            with self._lock:
                self.stats['worker_renderer_count'] = int(renderer_count)
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass
        return renderer

    def _clear_registered_worker_renderer_caches(self, count_event: bool = True) -> int:
        """Clear FastRenderer caches held by all worker threads."""
        try:
            with self._worker_renderers_lock:
                renderers = list(self._worker_renderers)
        except Exception:
            renderers = []

        cleared_count = 0
        for renderer in renderers:
            if renderer is None:
                continue
            try:
                if hasattr(renderer, 'clear_cache'):
                    renderer.clear_cache()
                    cleared_count += 1
            except Exception:
                logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
                pass

        if cleared_count > 0 and count_event:
            with self._lock:
                self.stats['worker_renderer_cache_clear_events'] += 1
                self.stats['worker_renderer_count'] = len(renderers)
        return cleared_count

    def _release_registered_worker_renderers(self):
        """Clear and release worker renderer references after the export finishes."""
        try:
            self._clear_registered_worker_renderer_caches(count_event=False)
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass
        try:
            with self._worker_renderers_lock:
                self._worker_renderers.clear()
                self._worker_renderer_ids.clear()
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass

    def _enforce_memory_budget(
        self,
        wait_for_relief: bool = False,
        cancel_event: Optional[threading.Event] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """按进程级预算限流。返回 False 表示当前不宜继续提交新任务。"""
        if self._export_memory_guard_mode == 'off':
            return True
        limit_mb = self._refresh_memory_budget()
        if limit_mb <= 0:
            return True

        ratio = self._memory_pressure_ratio()
        if ratio < self._export_memory_soft_ratio:
            return True

        hard_pressure = ratio >= self._export_memory_hard_ratio
        with self._lock:
            if hard_pressure:
                self.stats['memory_hard_throttle_events'] += 1
            else:
                self.stats['memory_soft_throttle_events'] += 1
            self.stats['safety_throttle_events'] += 1

        self._clear_memory_pressure_caches()

        if not wait_for_relief:
            return not hard_pressure

        wait_started = time.time()
        max_wait = 8.0 if hard_pressure else 2.5
        while time.time() - wait_started < max_wait:
            if self._is_cancel_requested(cancel_event, cancel_callback):
                return False
            if self._memory_pressure_ratio() < self._export_memory_soft_ratio:
                break
            time.sleep(0.15 if hard_pressure else 0.08)
            try:
                gc.collect()
            except Exception:
                logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
                pass

        waited = time.time() - wait_started
        if waited > 0:
            with self._lock:
                self.stats['memory_wait_seconds'] += waited
        return self._memory_pressure_ratio() < self._export_memory_hard_ratio

    def _calculate_memory_guard_in_flight_limit(self, current_limit: int) -> int:
        """基于可用内存计算在途任务上限，防止任务堆积触发卡死/闪退。"""
        if not self._export_safety_enabled:
            return max(1, int(current_limit))
        try:
            import psutil
            available_mb = float(psutil.virtual_memory().available) / (1024 * 1024)
            task_mem_mb = self._estimate_single_task_memory_mb()
            budget_mb = max(64.0, available_mb * float(self._export_safety_memory_guard_ratio))
            process_limit_mb = self._refresh_memory_budget()
            if process_limit_mb > 0:
                rss_mb = self._get_process_rss_mb()
                process_budget_mb = max(task_mem_mb, process_limit_mb - rss_mb)
                budget_mb = min(budget_mb, process_budget_mb)
            guard_limit = max(1, int(budget_mb / max(1.0, task_mem_mb)))
            return max(1, min(int(current_limit), guard_limit))
        except Exception:
            return max(1, int(current_limit))

    def _apply_worker_hard_cap(self, workers: int, cpu_count: Optional[int] = None) -> int:
        """对并发数应用硬上限，保证 UI 和系统可响应。"""
        try:
            cores = int(cpu_count or (os_module.cpu_count() or 4))
            cap_by_reserve = max(1, cores - int(getattr(self, '_reserve_cpu_cores', 1)))
            cap_by_util = max(1, int(math.floor(float(cores) * float(getattr(self, '_cpu_utilization_cap', 0.60)))))
            hard_cap = max(1, min(cap_by_reserve, cap_by_util))
            return max(1, min(int(workers), hard_cap))
        except Exception:
            return max(1, int(workers))
        if not self._export_trace_file:
            return
        try:
            with open(self._export_trace_file, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_memory_guard.py")
            pass

    def _optimize_memory_usage(self):
        """优化内存使用 - 清理各种缓存"""
        # 清除预加载缓存
        if hasattr(self, '_image_preload_cache'):
            self._clear_preload_cache()
    
        # 清除渲染缓存（批处理模式下已禁用，但保险起见）
        if hasattr(self, '_render_cache'):
            self._render_cache.clear()
    
        # 批导渲染使用 worker 文档，避免清理主 UI 文档图层缓存造成预览状态污染。
        if (not self.is_batch_mode) and hasattr(self.document, 'layers'):
            for layer in self.document.layers:
                # 清理异形图层的形状遮罩缓存
                if hasattr(layer, 'clear_cache'):
                    layer.clear_cache()
                # 清理普通图层的图像缓存
                if hasattr(layer, '_cached_image'):
                    layer._cached_image = None
                if hasattr(layer, 'cached_image'):
                    layer.cached_image = None
    
        # 强制垃圾回收
        import gc
        gc.collect()
    
        if self.is_batch_mode:
            print("[批处理] 已执行内存优化")

    def _should_optimize_memory(self) -> bool:
        """"""
        canvas_size = self.document.canvas_width * self.document.canvas_height
        layer_count = len([layer for layer in self.document.layers if layer.visible])

        # 
        should_optimize = canvas_size > 4000000 or layer_count > 10  # 4MP+  10+ 
        if should_optimize:
            print(f"[] : {canvas_size}, {layer_count}")
        return should_optimize
