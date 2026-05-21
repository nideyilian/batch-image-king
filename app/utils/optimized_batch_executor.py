"""


"""

import os as os_module  # 避免局部变量遮蔽
import time
import threading
from collections import Counter, OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from PIL import Image
import gc
import io
import math

try:
    from .batch_export_precomputer import PrecomputedExportPlan, ExportTask
    from .export_metrics import build_export_report
    from .text_layer_virtual_path import is_text_layer_virtual_path, parse_text_layer_virtual_path
except ImportError:
    # 兼容直接以脚本方式运行：python app/utils/optimized_batch_executor.py
    import sys
    script_dir = os_module.path.dirname(os_module.path.abspath(__file__))
    project_root = os_module.path.dirname(os_module.path.dirname(script_dir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from app.utils.batch_export_precomputer import PrecomputedExportPlan, ExportTask
    from app.utils.export_metrics import build_export_report
    from app.utils.text_layer_virtual_path import is_text_layer_virtual_path, parse_text_layer_virtual_path


@dataclass
class SaveTaskResult:
    success: bool
    render_time: float = 0.0
    io_time: float = 0.0
    file_path: str = ""
    backend_used: str = "pillow"
    written_bytes: int = 0
    error: str = ""


class OptimizedBatchExecutor:
    """"""
    
    def __init__(self, document, max_workers: int = None):
        self.document = document
        #  
        self.is_batch_mode = True  # 默认批处理模式
        # 先初始化性能配置，避免 _calculate_optimal_workers 读取未初始化字段
        self._max_file_size_kb = 0
        self._io_profile = "balanced"
        self._png_compress_level_override = -1
        self._jpeg_quality_override = 0
        self._batch_preload_enabled_setting = True
        self._batch_preload_max_images = 120
        self._batch_preload_memory_mb = 384
        self._export_backend = "pillow"
        self._vips_allow_with_size_limit = False
        self._reserve_cpu_cores = 1
        self._cpu_utilization_cap = 0.60
        self._export_safety_enabled = True
        self._export_safety_memory_guard_ratio = 0.40
        self._export_safety_max_consecutive_failures = 8
        self._export_safety_failure_rate_limit = 0.45
        self._export_safety_failure_rate_min_samples = 12
        self._export_safety_stall_timeout_seconds = 180
        self._export_memory_guard_mode = "auto"
        self._export_memory_limit_mb = 0
        self._export_memory_reserve_mb = 2048
        self._export_memory_soft_ratio = 0.88
        self._export_memory_hard_ratio = 0.98
        try:
            if hasattr(self.document, 'export_settings') and isinstance(self.document.export_settings, dict):
                self._max_file_size_kb = int(self.document.export_settings.get('max_file_size_kb', 0) or 0)
                # 性能参数改为程序自动策略：忽略历史手动档位配置
                self._png_compress_level_override = int(self.document.export_settings.get('png_compress_level_override', -1))
                self._jpeg_quality_override = int(self.document.export_settings.get('jpeg_quality_override', 0) or 0)
                self._batch_preload_enabled_setting = bool(self.document.export_settings.get('batch_preload_enabled', True))
                self._batch_preload_max_images = max(0, int(self.document.export_settings.get('batch_preload_max_images', 120) or 120))
                self._batch_preload_memory_mb = max(64, int(self.document.export_settings.get('batch_preload_memory_mb', 384) or 384))
                self._export_backend = str(self.document.export_settings.get('export_backend', 'pillow') or 'pillow').strip().lower()
                self._vips_allow_with_size_limit = bool(self.document.export_settings.get('vips_allow_with_size_limit', False))
                self._reserve_cpu_cores = max(0, int(self.document.export_settings.get('export_reserve_cpu_cores', 1) or 1))
                cap_raw = float(self.document.export_settings.get('export_cpu_utilization_cap', 0.60) or 0.60)
                self._cpu_utilization_cap = max(0.20, min(0.95, cap_raw))
                self._export_safety_enabled = bool(self.document.export_settings.get('export_safety_enabled', True))
                self._export_safety_memory_guard_ratio = max(
                    0.15,
                    min(0.80, float(self.document.export_settings.get('export_safety_memory_guard_ratio', 0.40) or 0.40))
                )
                self._export_safety_max_consecutive_failures = max(
                    3,
                    int(self.document.export_settings.get('export_safety_max_consecutive_failures', 8) or 8)
                )
                self._export_safety_failure_rate_limit = max(
                    0.20,
                    min(0.90, float(self.document.export_settings.get('export_safety_failure_rate_limit', 0.45) or 0.45))
                )
                self._export_safety_failure_rate_min_samples = max(
                    6,
                    int(self.document.export_settings.get('export_safety_failure_rate_min_samples', 12) or 12)
                )
                self._export_safety_stall_timeout_seconds = max(
                    30,
                    int(self.document.export_settings.get('export_safety_stall_timeout_seconds', 180) or 180)
                )
                self._export_memory_guard_mode = str(
                    self.document.export_settings.get('export_memory_guard_mode', 'auto') or 'auto'
                ).strip().lower()
                if self._export_memory_guard_mode not in ('auto', 'low', 'custom', 'off'):
                    self._export_memory_guard_mode = 'auto'
                self._export_memory_limit_mb = max(
                    0,
                    int(self.document.export_settings.get('export_memory_limit_mb', 0) or 0)
                )
                self._export_memory_reserve_mb = max(
                    512,
                    int(self.document.export_settings.get('export_memory_reserve_mb', 2048) or 2048)
                )
        except Exception:
            self._max_file_size_kb = 0
            self._io_profile = "balanced"
            self._png_compress_level_override = -1
            self._jpeg_quality_override = 0
            self._batch_preload_enabled_setting = True
            self._batch_preload_max_images = 120
            self._batch_preload_memory_mb = 384
            self._export_backend = "pillow"
            self._vips_allow_with_size_limit = False
            self._reserve_cpu_cores = 1
            self._cpu_utilization_cap = 0.60
            self._export_safety_enabled = True
            self._export_safety_memory_guard_ratio = 0.40
            self._export_safety_max_consecutive_failures = 8
            self._export_safety_failure_rate_limit = 0.45
            self._export_safety_failure_rate_min_samples = 12
            self._export_safety_stall_timeout_seconds = 180
            self._export_memory_guard_mode = "auto"
            self._export_memory_limit_mb = 0
            self._export_memory_reserve_mb = 2048

        selected_workers = max_workers if max_workers is not None else self._calculate_optimal_workers()
        self.max_workers = self._apply_worker_hard_cap(selected_workers)
        if self._export_memory_guard_mode == 'low':
            self.max_workers = max(1, min(self.max_workers, 2))
            self._preload_enabled = False
        self._memory_budget_limit_mb = 0.0
        self._memory_budget_requested_mb = float(self._export_memory_limit_mb or 0)
        self._last_memory_check_ts = 0.0
        self._last_memory_rss_mb = 0.0
        self._memory_budget_warning_printed = False
        self._export_trace_enabled = bool(
            os_module.environ.get("BTPW_EXPORT_TRACE", "0") == "1"
            or (
                hasattr(self.document, 'export_settings')
                and isinstance(self.document.export_settings, dict)
                and bool(self.document.export_settings.get('export_debug_trace', False))
            )
        )
        self._export_trace_file = ""
        if self._export_trace_enabled:
            try:
                trace_dir = os_module.path.join(os_module.path.expanduser('~'), '.config', '批图王', 'logs')
                os_module.makedirs(trace_dir, exist_ok=True)
                trace_name = f"export_trace_{time.strftime('%Y%m%d_%H%M%S')}.log"
                self._export_trace_file = os_module.path.join(trace_dir, trace_name)
                setattr(self.document, '_export_debug_trace_file', self._export_trace_file)
                self._emit_export_trace(f"导出调试已启用，日志文件: {self._export_trace_file}")
            except Exception:
                self._export_trace_file = ""
        
        # 
        self.is_canceled = False
        self.current_progress = 0
        self.total_tasks = 0
        
        # 🔧 增强错误报告
        self.last_error_message = ""
        
        # 
        self.progress_callback: Optional[Callable[[int], None]] = None
        self.file_completed_callback: Optional[Callable[[str], None]] = None
        
        # 
        self.stats = {
            'start_time': 0.0,
            'end_time': 0.0,
            'total_time': 0.0,
            'images_per_second': 0.0,
            'peak_memory_mb': 0.0,
            'cache_hits': 0,
            'render_time': 0.0,
            'io_time': 0.0,
            'completed_count': 0,
            'failed_count': 0,
            'scheduler_adjustments': 0,
            'queue_backpressure_events': 0,
            'safety_throttle_events': 0,
            'safety_stopped_by_failures': 0,
            'safety_stopped_by_timeout': 0,
            'memory_guard_mode': self._export_memory_guard_mode,
            'memory_limit_mb': 0.0,
            'memory_requested_limit_mb': float(self._export_memory_limit_mb or 0),
            'memory_current_mb': 0.0,
            'memory_peak_mb': 0.0,
            'memory_soft_throttle_events': 0,
            'memory_hard_throttle_events': 0,
            'memory_wait_seconds': 0.0,
            'memory_cache_clear_events': 0,
            'safety_initial_in_flight_cap': 0,
            'min_in_flight_limit': 0,
            'max_in_flight_limit': 0,
            'final_in_flight_limit': 0,
            'render_queue_submitted': 0,
            'save_queue_submitted': 0,
            'max_render_backlog': 0,
            'max_save_backlog': 0,
            'max_pipeline_backlog': 0,
            'worker_document_seed_available': 0,
            'worker_document_create_failures': 0,
            'shared_document_render_count': 0,
            'main_document_mutation_warnings': 0,
            'preload_unique_images': 0,
            'preload_loaded_images': 0,
            'preload_skipped_by_memory': 0,
            'preload_memory_mb': 0.0,
            'preload_hits': 0,
            'io_workers': 0,
            'written_bytes': 0,
            'export_service_time': 0.0,
            'pillow_save_count': 0,
            'vips_attempts': 0,
            'vips_save_count': 0,
            'vips_fallback_count': 0,
            'vips_size_fallback_count': 0,
            'save_error_count': 0,
            'render_cache_hit_rate': 0.0,
            'apply_effects_calls': 0,
        }
        
        # 
        self._lock = threading.Lock()
        self._render_cache = {}  # 
        self.max_cache_size = 100  # 
        self._thread_local = threading.local()
        self._worker_document_seed = None
        self._plan_mutable_doc_indices = set()
        self._prepare_worker_document_seed()
        if self.is_batch_mode and not self._worker_document_seed and self.max_workers > 1:
            self.max_workers = 1
            print("[批处理] 线程文档快照不可用，已降级为单线程共享锁渲染以降低主文档污染风险")
        
        # 图片预加载缓存 - 批处理模式可按开关启用（配合渲染器会话缓存减少读盘）
        self._image_preload_cache = OrderedDict()
        self._image_preload_cache_bytes = 0
        # 批导默认启用预读，配合内存上限自适应
        self._preload_enabled = bool(self._batch_preload_enabled_setting) and self._export_memory_guard_mode != 'low'
        # 记录最近一次错误，供UI提示
        self.last_error_message = ""
        # 默认关闭高频调试日志，降低批量导出的控制台I/O开销
        self._verbose_logs = os_module.environ.get("BTPW_BATCH_EXPORT_VERBOSE", "0") == "1"

        if self.is_batch_mode:
            self._refresh_memory_budget(force=True)
            print(f"[批处理] 最大工作线程: {self.max_workers}")
            print(f"[批处理] 预读开关: {'开' if self._preload_enabled else '关'} (上限{self._batch_preload_max_images}张 / {self._batch_preload_memory_mb}MB)")
            print(f"[批处理] 导出后端: {self._export_backend} (保留CPU核心: {self._reserve_cpu_cores}, CPU占用上限: {self._cpu_utilization_cap:.2f})")
            print(
                f"[批处理] 内存保护: {self._export_memory_guard_mode} "
                f"(限制 {self._memory_budget_limit_mb:.0f}MB, 系统预留 {self._export_memory_reserve_mb}MB)"
            )
            print(
                f"[批处理] 安全保护: {'开' if self._export_safety_enabled else '关'} "
                f"(内存保护比{self._export_safety_memory_guard_ratio:.2f}, "
                f"连续失败阈值{self._export_safety_max_consecutive_failures}, "
                f"卡住超时{self._export_safety_stall_timeout_seconds}s)"
            )
            if self._export_backend in ('auto', 'pyvips', 'vips'):
                print(f"[批处理] pyvips可用: {'是' if self._is_vips_runtime_available() else '否'}")
            print(f"[批处理] 最大文件大小限制: {int(self._max_file_size_kb)}KB")
            if int(self._max_file_size_kb) > 0 and not bool(self._vips_allow_with_size_limit):
                print("[批处理] pyvips大小限制策略: 关闭（避免回退放大耗时）")

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
            pass
        try:
            if getattr(self, '_render_cache', None):
                self._render_cache.clear()
                cleared = True
        except Exception:
            pass
        try:
            renderer = getattr(self._thread_local, 'fast_renderer', None)
            if renderer is not None and hasattr(renderer, 'clear_cache'):
                renderer.clear_cache()
                cleared = True
        except Exception:
            pass
        try:
            gc.collect()
        except Exception:
            pass
        if cleared:
            with self._lock:
                self.stats['memory_cache_clear_events'] += 1

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

    def _emit_export_trace(self, message: str):
        """导出调试输出：同时写控制台和调试文件（UTF-8）。"""
        if not self._export_trace_enabled:
            return
        line = f"[导出调试] {str(message)}"
        try:
            print(line)
        except Exception:
            pass

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
            pass

    def _collect_layer_runtime_snapshot(self, layer) -> str:
        """采集图层关键运行时状态，定位任务间状态串扰。"""
        try:
            current_path = str(
                getattr(layer, '_current_image_path', '') or
                getattr(layer, 'current_image_path', '') or
                ''
            )
            return (
                f"path={current_path or 'None'} "
                f"xy=({getattr(layer, 'x', None)},{getattr(layer, 'y', None)}) "
                f"wh=({getattr(layer, 'width', None)},{getattr(layer, 'height', None)}) "
                f"fit={getattr(layer, 'fit_mode', None)} crop={getattr(layer, 'crop_direction', None)} "
                f"rot={getattr(layer, 'rotation', None)} "
                f"rnd=({getattr(layer, '_current_random_offset_x', 0)},"
                f"{getattr(layer, '_current_random_offset_y', 0)},"
                f"{getattr(layer, '_current_random_scale', 1.0)},"
                f"{getattr(layer, '_current_random_rotation', 0.0)}) "
                f"flip=({getattr(layer, 'flip_horizontal', False)},{getattr(layer, 'flip_vertical', False)}) "
                f"clone=({getattr(layer, '_clone_enabled', getattr(layer, 'clone_enabled', False))},"
                f"{getattr(layer, '_clone_rows', getattr(layer, 'clone_rows', 1))},"
                f"{getattr(layer, '_clone_columns', getattr(layer, 'clone_columns', 1))})"
            )
        except Exception as e:
            return f"snapshot_error={str(e)}"

    def _emit_runtime_snapshot_for_indices(self, document, doc_indices, task_name: str, stage: str):
        """输出指定图层索引集合的运行时状态快照。"""
        if not self._export_trace_enabled:
            return
        if not hasattr(document, 'layers'):
            return
        for doc_idx in sorted([int(i) for i in (doc_indices or set())]):
            if doc_idx < 0 or doc_idx >= len(document.layers):
                continue
            layer = document.layers[doc_idx]
            self._emit_export_trace(
                f"任务={task_name} 运行时快照 stage={stage} 文档索引={doc_idx} "
                f"图层={getattr(layer, 'name', '')} {self._collect_layer_runtime_snapshot(layer)}"
            )

    def _capture_document_runtime_fingerprint(self, document, target_doc_indices: Optional[set] = None) -> Dict[int, Dict[str, object]]:
        """采集主文档运行时指纹，用于确认批导没有污染 UI 文档。"""
        snapshot: Dict[int, Dict[str, object]] = {}
        try:
            if not hasattr(document, 'layers'):
                return snapshot
            try:
                from app.models.text_layer import TextLayer
            except Exception:
                TextLayer = None
            target_indices = set(target_doc_indices or [])
            for idx, layer in enumerate(document.layers):
                if target_indices and idx not in target_indices:
                    continue
                item = {
                    'current_image_path': getattr(layer, '_current_image_path', getattr(layer, 'current_image_path', None)),
                    'cached_image_path': getattr(layer, '_cached_image_path', None),
                    'random_offset_x': getattr(layer, '_current_random_offset_x', 0),
                    'random_offset_y': getattr(layer, '_current_random_offset_y', 0),
                    'random_scale': getattr(layer, '_current_random_scale', 1.0),
                    'random_rotation': getattr(layer, '_current_random_rotation', 0.0),
                    'clone_enabled': getattr(layer, '_clone_enabled', getattr(layer, 'clone_enabled', False)),
                    'clone_rows': getattr(layer, '_clone_rows', getattr(layer, 'clone_rows', 1)),
                    'clone_columns': getattr(layer, '_clone_columns', getattr(layer, 'clone_columns', 1)),
                }
                if TextLayer is not None and isinstance(layer, TextLayer):
                    item['current_text'] = getattr(layer, '_current_text', getattr(layer, 'current_text', None))
                snapshot[idx] = item
        except Exception:
            return snapshot
        return snapshot

    def _detect_main_document_runtime_mutation(self, before: Dict[int, Dict[str, object]]) -> List[str]:
        """比较主文档运行时指纹，返回被批导修改过的图层描述。"""
        changes: List[str] = []
        if not before:
            return changes
        try:
            after = self._capture_document_runtime_fingerprint(self.document, set(before.keys()))
            for idx, before_item in before.items():
                after_item = after.get(idx, {})
                if before_item != after_item:
                    layer_name = ""
                    try:
                        layer_name = str(getattr(self.document.layers[idx], 'name', '') or f"图层{idx}")
                    except Exception:
                        layer_name = f"图层{idx}"
                    changes.append(f"{idx}:{layer_name}")
        except Exception:
            return changes
        return changes

    def _prepare_worker_document_seed(self):
        """为线程独立渲染准备文档快照"""
        try:
            from app.models.document_serializer import DocumentSerializer
            self._worker_document_seed = DocumentSerializer.serialize_document_data(self.document)
            self._sanitize_worker_document_seed_runtime_state()
            with self._lock:
                self.stats['worker_document_seed_available'] = 1
        except Exception as e:
            self._worker_document_seed = None
            if self.is_batch_mode:
                print(f"[批处理] 线程文档快照准备失败，将回退共享文档渲染: {e}")

    def _sanitize_worker_document_seed_runtime_state(self):
        """清理快照里的运行期字段，避免 worker 继承 UI 预览临时状态。"""
        try:
            if not isinstance(self._worker_document_seed, dict):
                return
            layers_data = self._worker_document_seed.get('layers', [])
            if not isinstance(layers_data, list):
                return

            runtime_keys = (
                'current_image_path', '_current_image_path',
                'cached_image', '_cached_image', '_cached_image_path',
                '_current_image_cache', '_cache_valid',
                '_current_random_offset_x', '_current_random_offset_y',
                '_current_random_scale', '_current_random_rotation',
            )
            for layer_data in layers_data:
                if not isinstance(layer_data, dict):
                    continue
                for key in runtime_keys:
                    layer_data.pop(key, None)
        except Exception:
            pass

    def _build_visible_doc_indices(self, document) -> List[int]:
        """构建可见图层在 document.layers 中的真实索引列表。"""
        try:
            if not hasattr(document, 'layers'):
                return []
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            return [
                idx for idx, layer in enumerate(document.layers)
                if not is_layer_group(layer) and is_effectively_visible(layer, document.layers)
            ]
        except Exception:
            return []

    def _should_use_visible_index_mode(self, document, combination, visible_doc_indices: List[int]) -> bool:
        """
        判断组合索引语义：
        - True: 组合使用“可见图层序号”
        - False: 组合使用“文档真实图层索引”
        """
        try:
            if not hasattr(combination, 'layer_states') or not isinstance(combination.layer_states, dict):
                return False
            if not hasattr(document, 'layers'):
                return False
            if len(visible_doc_indices) >= len(document.layers):
                # 无隐藏图层时两种语义等价，默认按文档索引处理
                return False
            keys = [int(k) for k in combination.layer_states.keys() if isinstance(k, int) or str(k).isdigit()]
            if not keys:
                return False
            # 关键判据：若 key 直接命中隐藏图层，说明 key 更可能是“可见层序号”
            hidden_hit = 0
            for k in keys:
                if 0 <= k < len(document.layers) and (not bool(getattr(document.layers[k], 'visible', True))):
                    hidden_hit += 1
            return hidden_hit > 0
        except Exception:
            return False

    def _resolve_combination_layer_index(
        self,
        document,
        combo_layer_idx,
        visible_doc_indices: List[int],
        use_visible_index_mode: bool
    ) -> Optional[int]:
        """把组合里的图层索引解析为 document.layers 的真实索引。"""
        try:
            idx = int(combo_layer_idx)
        except Exception:
            return None

        if use_visible_index_mode:
            if 0 <= idx < len(visible_doc_indices):
                return int(visible_doc_indices[idx])
            return None

        if hasattr(document, 'layers') and 0 <= idx < len(document.layers):
            return idx
        return None

    def _get_target_document_for_render(self):
        """获取当前任务使用的文档对象及是否需要共享锁"""
        if not self.is_batch_mode:
            return self.document, True
        if not self._worker_document_seed:
            with self._lock:
                self.stats['shared_document_render_count'] += 1
            return self.document, True

        cached_doc = getattr(self._thread_local, 'render_document', None)
        if cached_doc is not None:
            return cached_doc, False

        try:
            from app.models.document import Document
            from app.models.document_serializer import DocumentSerializer

            worker_doc = Document(parent=None)
            restored = DocumentSerializer.restore_document_data(worker_doc, self._worker_document_seed)
            if not restored:
                with self._lock:
                    self.stats['worker_document_create_failures'] += 1
                    self.stats['shared_document_render_count'] += 1
                return self.document, True

            worker_doc._is_batch_export_running = True
            worker_doc._export_canceled = False
            self._thread_local.render_document = worker_doc
            return worker_doc, False
        except Exception as e:
            if self.is_batch_mode:
                print(f"[批处理] 创建线程独立文档失败，回退共享文档渲染: {e}")
            with self._lock:
                self.stats['worker_document_create_failures'] += 1
                self.stats['shared_document_render_count'] += 1
            return self.document, True

    def _get_thread_local_fast_renderer(self):
        """获取线程独立 FastRenderer，避免高并发导出时状态串扰。"""
        cached_renderer = getattr(self._thread_local, 'fast_renderer', None)
        if cached_renderer is not None:
            return cached_renderer
        try:
            from app.utils.fast_renderer import FastRenderer
            renderer = FastRenderer()
            self._thread_local.fast_renderer = renderer
            return renderer
        except Exception:
            # 保底回退：若实例化失败，继续使用全局渲染器
            from app.utils.fast_renderer import get_global_fast_renderer
            return get_global_fast_renderer()
    
    def execute_plan(self, plan: PrecomputedExportPlan, 
                    progress_callback: Optional[Callable[[int], None]] = None,
                    file_completed_callback: Optional[Callable[[str], None]] = None,
                    cancel_callback: Optional[Callable[[], bool]] = None) -> bool:
        """执行批处理导出计划"""
        
        # 批处理模式下简化日志输出
        if self.is_batch_mode:
            print(f"[批处理] 开始执行导出任务")
            print(f"[批处理] 任务数量: {len(plan.tasks)}")
            print(f"[批处理] 预估时间: {plan.estimated_time:.1f}秒")
        else:
            # 非批处理模式保持详细日志
            print(f"[]  ")
            print(f"[]    : {len(plan.tasks)}")
            print(f"[]    : {plan.unique_combinations}")
            print(f"[]    : {plan.estimated_time:.1f}")
            print(f"[]    : {self.max_workers}")
        
        # 
        if plan.tasks:
            first_task = plan.tasks[0]
            output_dir = os_module.path.dirname(first_task.file_path)
            file_ext = os_module.path.splitext(first_task.filename)[1]
            first_format = os_module.path.splitext(first_task.file_path)[1].lower().lstrip('.')
            if self.is_batch_mode:
                print(f"[批处理] 输出目录: {output_dir}")
                can_vips, reason = self._get_vips_policy_for_format(first_format)
                print(f"[批处理] pyvips策略: {'启用' if can_vips else '禁用'} ({reason}, format={first_format})")
            else:
                print(f"[]    : {output_dir}")
                print(f"[]    : {file_ext}")
        
        self.progress_callback = progress_callback
        self.file_completed_callback = file_completed_callback
        self.total_tasks = len(plan.tasks)
        self.current_progress = 0
        self.is_canceled = False
        self._refresh_memory_budget(force=True)
        self._plan_mutable_doc_indices = self._collect_plan_mutable_doc_indices(plan, self.document)
        main_doc_runtime_before = self._capture_document_runtime_fingerprint(
            self.document,
            self._plan_mutable_doc_indices if self._plan_mutable_doc_indices else None
        )

        # 重置导出期渲染指标（缓存命中、apply_effects调用次数）
        try:
            from app.utils.fast_renderer import FastRenderer
            FastRenderer.reset_batch_metrics()
        except Exception:
            pass
        
        print(f"[] : {self.total_tasks} ")

        # 阶段二：批导渲染只修改 worker 文档。主 UI 文档保留原状态，靠 worker 快照清理
        # 避免预览临时路径影响导出。
        self._clear_layer_image_paths(
            self._plan_mutable_doc_indices if self._plan_mutable_doc_indices else None,
            document_data=self._worker_document_seed,
        )

        #  
        self._preload_images_for_plan(plan, cancel_callback=cancel_callback)
        self._enforce_memory_budget(wait_for_relief=True, cancel_callback=cancel_callback)

        self.stats['start_time'] = time.time()
        
        try:
            # 创建输出目录
            output_dirs = set(os_module.path.dirname(task.file_path) for task in plan.tasks)
            for directory in output_dirs:
                if not os_module.path.exists(directory):
                    os_module.makedirs(directory)
                    if self.is_batch_mode:
                        print(f"[批处理] 创建目录: {directory}")
                    else:
                        print(f"[] : {directory}")
            
            # 执行并行导出
            success = self._execute_parallel_export(plan.tasks, cancel_callback)
            
            self.stats['end_time'] = time.time()
            self.stats['total_time'] = self.stats['end_time'] - self.stats['start_time']
            
            if success and self.stats['total_time'] > 0:
                self.stats['images_per_second'] = self.total_tasks / self.stats['total_time']
                
                if self.is_batch_mode:
                    print(f"[批处理] 导出统计:")
                    print(f"  - 总耗时: {self.stats['total_time']:.2f}秒")
                    print(f"  - 处理速度: {self.stats['images_per_second']:.2f}张/秒")
                    print(f"  - 渲染时间: {self.stats['render_time']:.2f}秒")
                    print(f"  - I/O时间: {self.stats['io_time']:.2f}秒")
                    print(
                        f"  - pyvips命中: {int(self.stats.get('vips_save_count', 0))}/"
                        f"{int(self.stats.get('vips_attempts', 0))}"
                        f" (回退 {int(self.stats.get('vips_fallback_count', 0))})"
                    )
                    print(
                        f"  - Pillow保存: {int(self.stats.get('pillow_save_count', 0))}, "
                        f"服务层写盘耗时: {float(self.stats.get('export_service_time', 0.0) or 0.0):.2f}秒, "
                        f"保存失败: {int(self.stats.get('save_error_count', 0))}"
                    )
                    if int(self.stats.get('vips_size_fallback_count', 0)) > 0:
                        print(f"  - pyvips因体积限制回退: {int(self.stats.get('vips_size_fallback_count', 0))}")
                    try:
                        from app.utils.fast_renderer import FastRenderer
                        render_metrics = FastRenderer.get_batch_metrics()
                    except Exception:
                        render_metrics = {}
                    export_hits = int(render_metrics.get('export_layer_cache_hits', 0) or 0)
                    export_misses = int(render_metrics.get('export_layer_cache_misses', 0) or 0)
                    layer_hits = int(render_metrics.get('layer_surface_cache_hits', 0) or 0)
                    layer_misses = int(render_metrics.get('layer_surface_cache_misses', 0) or 0)
                    apply_calls = int(render_metrics.get('apply_effects_calls', 0) or 0)
                    total_cache_access = export_hits + export_misses + layer_hits + layer_misses
                    cache_hit_rate = (float(export_hits + layer_hits) / float(total_cache_access) * 100.0) if total_cache_access > 0 else 0.0
                    self.stats['render_cache_hit_rate'] = cache_hit_rate
                    self.stats['apply_effects_calls'] = apply_calls
                    print(
                        f"  - 渲染缓存命中率: {cache_hit_rate:.1f}% "
                        f"(export:{export_hits}/{max(1, export_hits + export_misses)}, "
                        f"layer:{layer_hits}/{max(1, layer_hits + layer_misses)})"
                    )
                    print(f"  - apply_effects调用次数: {apply_calls}")
                    print(f"  - 缓存命中: {self.stats['cache_hits']}")
                    print(
                        f"  - 流水线峰值: render={int(self.stats.get('max_render_backlog', 0) or 0)}, "
                        f"save={int(self.stats.get('max_save_backlog', 0) or 0)}, "
                        f"total={int(self.stats.get('max_pipeline_backlog', 0) or 0)}"
                    )
                else:
                    print(f"[] :")
                    print(f"  - : {self.stats['total_time']:.2f}")
                    print(f"  - : {self.stats['images_per_second']:.2f}/")
                    print(f"  - : {self.stats['render_time']:.2f}")
                    print(f"  - I/O: {self.stats['io_time']:.2f}")
                    print(f"  - : {self.stats['cache_hits']}")
                
                #  2
                self._record_exported_combinations(plan)
            
            # 导出失败时，将错误信息反馈到文档
            if not success and hasattr(self.document, '__dict__'):
                try:
                    setattr(self.document, '_last_export_error', self.last_error_message or '导出失败')
                except Exception:
                    pass
            main_doc_changes = self._detect_main_document_runtime_mutation(main_doc_runtime_before)
            if main_doc_changes:
                with self._lock:
                    self.stats['main_document_mutation_warnings'] = len(main_doc_changes)
                warning = "批导期间检测到主文档运行时状态变化: " + ", ".join(main_doc_changes[:8])
                try:
                    setattr(self.document, '_last_export_snapshot_warning', warning)
                except Exception:
                    pass
                if self.is_batch_mode:
                    print(f"[批处理] ⚠️ {warning}")
            else:
                try:
                    setattr(self.document, '_last_export_snapshot_warning', "")
                except Exception:
                    pass
            return success
            
        except Exception as e:
            if self.is_batch_mode:
                print(f"[批处理] 导出错误: {e}")
            else:
                print(f"[] : {e}")
            return False
        finally:
            # 清理资源
            self._cleanup_resources()
            try:
                if hasattr(self.document, '_batch_preloaded_images'):
                    delattr(self.document, '_batch_preloaded_images')
            except Exception:
                pass
            self._clear_preload_cache()
            # 批处理模式下执行额外的内存优化
            if self.is_batch_mode:
                self._optimize_memory_usage()

    def _record_exported_combinations(self, plan):
        """ - +"""
        try:
            from app.utils.global_avoid_repeat_manager import GlobalAvoidRepeatManager
            global_manager = GlobalAvoidRepeatManager()
            
            recorded_count = 0
            duplicate_count = 0
            
            #  
            for task in plan.tasks:
                if hasattr(task, 'combination') and task.combination:
                    # 
                    file_paths = []
                    if hasattr(task.combination, 'layer_states'):
                        file_paths = list(task.combination.layer_states.values())
                    elif isinstance(task.combination, dict):
                        file_paths = list(task.combination.values())
                    
                    if file_paths:
                        # 
                        if global_manager.is_combination_fresh(file_paths):
                            global_manager.record_combination_usage(file_paths)  # 
                            recorded_count += 1
                        else:
                            duplicate_count += 1
            
            #  I/O
            global_manager.force_save_if_needed()
            
            print(f"[]  : {recorded_count} , {duplicate_count} ")
            
            #  
            self._display_avoid_repeat_statistics(plan, global_manager, recorded_count, duplicate_count)
            
        except Exception as e:
            print(f"[]  : {e}")
            import traceback
            traceback.print_exc()
    
    def _display_avoid_repeat_statistics(self, plan, global_manager, recorded_count, duplicate_count):
        """ - """
        try:
            # 1. 
            total_exported = len(plan.tasks)
            unique_rate = (recorded_count / total_exported * 100) if total_exported > 0 else 0
            duplicate_rate = (duplicate_count / total_exported * 100) if total_exported > 0 else 0
            
            print(f"\n")
            print(f"  :     {total_exported}")
            print(f"  :     {recorded_count} ({unique_rate:.1f}%)")
            print(f"  :   {duplicate_count} ({duplicate_rate:.1f}%)")
            
            # 2. 
            print(f"\n")
            print(f"  : {len(global_manager.combination_history)}")
            print(f"  : {len(global_manager.image_usage_history)}")
            print(f"  :   {len(global_manager.recent_combinations)}")
            
            # 3. 
            if global_manager.image_usage_history:
                usage_counts = list(global_manager.image_usage_history.values())
                avg_usage = sum(usage_counts) / len(usage_counts)
                max_usage = max(usage_counts)
                min_usage = min(usage_counts)
                
                print(f"\n")
                print(f"  : {avg_usage:.2f}")
                print(f"  : {max_usage}")
                print(f"  : {min_usage}")
                print(f"  :   {(min_usage/max_usage*100):.1f}%" if max_usage > 0 else "  :   N/A")
            
            # 4. 
            diversity_score = self._calculate_diversity_score(
                recorded_count, duplicate_count, total_exported
            )
            
            print(f"\n")
            if diversity_score >= 90:
                grade = " "
                advice = ""
            elif diversity_score >= 70:
                grade = " "
                advice = ""
            elif diversity_score >= 50:
                grade = " "
                advice = ""
            else:
                grade = ""
                advice = ""
            
            print(f"  :     {diversity_score:.1f}/100 ({grade})")
            print(f"  :     {advice}")
            
            print("=" * 60 + "\n")
            
        except Exception as e:
            print(f"[]  : {e}")
    
    def _calculate_diversity_score(self, recorded_count, duplicate_count, total_exported):
        """0-100"""
        if total_exported == 0:
            return 0
        
        # 
        base_score = (recorded_count / total_exported) * 60
        
        # 
        duplicate_penalty = (duplicate_count / total_exported) * 30
        
        # 
        volume_bonus = min(10, recorded_count / 10)
        
        final_score = base_score + (30 - duplicate_penalty) + volume_bonus
        return max(0, min(100, final_score))
    
    def _apply_clone_settings(self, layer, clone_settings):
        """"""
        try:
            # 🔧 批量导出优化：检查是否处于批量导出模式
            is_batch_mode = (hasattr(self.document, '_is_batch_export_running') and 
                           self.document._is_batch_export_running)
            
            # 
            if hasattr(layer, 'clone_enabled'):
                if is_batch_mode and hasattr(layer, '_clone_enabled'):
                    layer._clone_enabled = clone_settings.get('clone_enabled', False)
                else:
                    layer.clone_enabled = clone_settings.get('clone_enabled', False)
            elif hasattr(layer, '_clone_enabled'):
                layer._clone_enabled = clone_settings.get('clone_enabled', False)

            if hasattr(layer, 'clone_rows'):
                if is_batch_mode and hasattr(layer, '_clone_rows'):
                    layer._clone_rows = clone_settings.get('clone_rows', 1)
                else:
                    layer.clone_rows = clone_settings.get('clone_rows', 1)
            elif hasattr(layer, '_clone_rows'):
                layer._clone_rows = clone_settings.get('clone_rows', 1)

            if hasattr(layer, 'clone_columns'):
                if is_batch_mode and hasattr(layer, '_clone_columns'):
                    layer._clone_columns = clone_settings.get('clone_columns', 1)
                else:
                    layer.clone_columns = clone_settings.get('clone_columns', 1)
            elif hasattr(layer, '_clone_columns'):
                layer._clone_columns = clone_settings.get('clone_columns', 1)

            if hasattr(layer, 'clone_row_spacing'):
                if is_batch_mode and hasattr(layer, '_clone_row_spacing'):
                    layer._clone_row_spacing = clone_settings.get('clone_row_spacing', 0)
                else:
                    layer.clone_row_spacing = clone_settings.get('clone_row_spacing', 0)
            elif hasattr(layer, '_clone_row_spacing'):
                layer._clone_row_spacing = clone_settings.get('clone_row_spacing', 0)

            if hasattr(layer, 'clone_column_spacing'):
                if is_batch_mode and hasattr(layer, '_clone_column_spacing'):
                    layer._clone_column_spacing = clone_settings.get('clone_column_spacing', 0)
                else:
                    layer.clone_column_spacing = clone_settings.get('clone_column_spacing', 0)
            elif hasattr(layer, '_clone_column_spacing'):
                layer._clone_column_spacing = clone_settings.get('clone_column_spacing', 0)

        except Exception as e:
            print(f"[] : {e}")

    def _apply_layer_parameters_fast(self, layer, params: Dict[str, object]):
        """
        批量导出场景快速应用图层参数：
        - 对 LayerNew 使用属性字典直写，避免大量信号与高频日志；
        - 其他类型回退到 setattr，保证兼容。
        """
        if not isinstance(params, dict) or not params:
            return

        keys = (
            'opacity', 'blend_mode',
            'x', 'y', 'width', 'height',
            'fit_mode', 'crop_direction',
            'corner_radius',
            'stroke_enabled', 'stroke_width', 'stroke_color', 'stroke_type',
            'color_overlay_enabled', 'color_overlay_color', 'color_overlay_opacity',
            'gradient_overlay_enabled', 'gradient_overlay_colors', 'gradient_overlay_angle', 'gradient_overlay_opacity',
            'shape_type', 'trapezoid_top_width', 'trapezoid_bottom_width', 'trapezoid_slope_side',
            'polygon_rotation', 'polygon_corner_radius',
            'rotation', 'flip_horizontal', 'flip_vertical',
        )

        property_manager = getattr(layer, '_property_manager', None)
        properties = getattr(property_manager, '_properties', None) if property_manager is not None else None
        used_fast_path = False

        if isinstance(properties, dict):
            for key in keys:
                if key not in params:
                    continue
                value = params[key]
                # 快速路径下补齐关键类型转换，避免字符串直接写入导致运行时异常
                if key == 'shape_type':
                    try:
                        from app.models.layer_properties import ShapeType
                        if isinstance(value, str):
                            value = ShapeType(value)
                    except Exception:
                        pass
                if key in properties and isinstance(properties[key], dict) and 'value' in properties[key]:
                    properties[key]['value'] = value
                    used_fast_path = True
                elif hasattr(layer, key):
                    try:
                        setattr(layer, key, value)
                    except Exception:
                        pass

            if used_fast_path:
                # 手动清理图像缓存，等价于属性管理器的 cache_marker 行为
                for attr in ('_cached_image', '_cached_image_path', '_cache_valid', 'cached_image'):
                    if hasattr(layer, attr):
                        try:
                            if attr == '_cache_valid':
                                setattr(layer, attr, False)
                            else:
                                setattr(layer, attr, None)
                        except Exception:
                            pass
                return

        # 兜底：普通对象（例如 TextLayer）
        for key in keys:
            if key in params and hasattr(layer, key):
                try:
                    value = params[key]
                    if key == 'shape_type':
                        try:
                            from app.models.layer_properties import ShapeType
                            if isinstance(value, str):
                                value = ShapeType(value)
                        except Exception:
                            pass
                    setattr(layer, key, value)
                except Exception:
                    pass

    def _is_cancel_requested(
        self,
        cancel_event: Optional[threading.Event] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
        set_event: bool = True,
    ) -> bool:
        """统一取消判断，避免批导流水线各阶段漏查取消状态。"""
        try:
            if bool(getattr(self, 'is_canceled', False)):
                if set_event and cancel_event:
                    cancel_event.set()
                return True
            if cancel_event and cancel_event.is_set():
                self.is_canceled = True
                return True
            if cancel_callback and cancel_callback():
                self.is_canceled = True
                if set_event and cancel_event:
                    cancel_event.set()
                if hasattr(self.document, '_export_canceled'):
                    self.document._export_canceled = True
                return True
        except Exception:
            return bool(getattr(self, 'is_canceled', False))
        return False
    
    def _execute_parallel_export(self, tasks: List[ExportTask], 
                                cancel_callback: Optional[Callable[[], bool]] = None) -> bool:
        """"""
        
        completed_count = 0
        failed_count = 0
        cancel_event = threading.Event()
        
        # 
        if self.is_canceled:
            return False
        
        render_executor = ThreadPoolExecutor(max_workers=self.max_workers)
        # 自动I/O并发：结合 I/O 策略动态伸缩，避免写盘成为瓶颈
        if str(self._io_profile) == 'speed':
            io_workers = max(2, min(8, max(2, self.max_workers - 1)))
        elif str(self._io_profile) == 'size':
            io_workers = max(1, min(4, max(1, self.max_workers // 2)))
        else:
            io_workers = max(2, min(6, max(2, self.max_workers)))
        if self._export_memory_guard_mode == 'low':
            io_workers = max(1, min(io_workers, 2))
        io_executor = ThreadPoolExecutor(max_workers=io_workers)
        render_future_to_task = {}
        save_future_to_task = {}
        task_iter = iter(tasks)
        tasks_exhausted = False
        min_in_flight_limit = max(2, self.max_workers)
        if self._export_safety_enabled:
            min_in_flight_limit = max(1, min(min_in_flight_limit, max(1, self.max_workers // 2)))
        if self._export_memory_guard_mode == 'low':
            min_in_flight_limit = 1
        max_in_flight_limit = max(min_in_flight_limit, self.max_workers * 3)
        in_flight_limit = max(3, self.max_workers + 1)
        if self._export_memory_guard_mode == 'low':
            in_flight_limit = min(in_flight_limit, 2)
            max_in_flight_limit = min(max_in_flight_limit, 3)
        in_flight_limit = max(min_in_flight_limit, min(max_in_flight_limit, in_flight_limit))
        safety_in_flight_cap = self._calculate_memory_guard_in_flight_limit(in_flight_limit)
        if self._export_safety_enabled and safety_in_flight_cap < in_flight_limit:
            with self._lock:
                self.stats['safety_throttle_events'] += 1
            in_flight_limit = max(min_in_flight_limit, safety_in_flight_cap)
        last_progress_ts = time.time()
        consecutive_failures = 0
        recent_render_times: List[float] = []
        recent_io_times: List[float] = []
        with self._lock:
            self.stats['io_workers'] = io_workers
            self.stats['min_in_flight_limit'] = min_in_flight_limit
            self.stats['max_in_flight_limit'] = max_in_flight_limit
            self.stats['safety_initial_in_flight_cap'] = int(safety_in_flight_cap)

        def _avg(values: List[float]) -> float:
            if not values:
                return 0.0
            return float(sum(values)) / float(len(values))

        def _record_pipeline_depths():
            """记录流水线队列深度，便于诊断背压是否生效。"""
            try:
                render_backlog = len(render_future_to_task)
                save_backlog = len(save_future_to_task)
                with self._lock:
                    self.stats['max_render_backlog'] = max(
                        int(self.stats.get('max_render_backlog', 0) or 0),
                        int(render_backlog)
                    )
                    self.stats['max_save_backlog'] = max(
                        int(self.stats.get('max_save_backlog', 0) or 0),
                        int(save_backlog)
                    )
                    self.stats['max_pipeline_backlog'] = max(
                        int(self.stats.get('max_pipeline_backlog', 0) or 0),
                        int(render_backlog + save_backlog)
                    )
            except Exception:
                pass

        def _rebalance_in_flight_limit():
            nonlocal in_flight_limit
            avg_render = _avg(recent_render_times)
            avg_io = _avg(recent_io_times)
            save_backlog = len(save_future_to_task)
            old_limit = in_flight_limit

            # I/O 背压优先：写盘排队过长或写盘显著慢于渲染时，降低渲染在途任务
            if save_backlog > io_workers * 3 or (avg_io > 0 and avg_render > 0 and avg_io > avg_render * 1.4):
                reduce_step = max(1, int(max(1, in_flight_limit) * 0.15))
                in_flight_limit = max(min_in_flight_limit, in_flight_limit - reduce_step)
                if save_backlog > io_workers * 3:
                    with self._lock:
                        self.stats['queue_backpressure_events'] += 1
            # 队列健康时逐步恢复并发，提升吞吐
            elif save_backlog <= io_workers and (avg_io == 0 or avg_render == 0 or avg_io <= avg_render * 1.1):
                increase_step = max(1, int(max(1, in_flight_limit) * 0.10))
                in_flight_limit = min(max_in_flight_limit, in_flight_limit + increase_step)

            if self._export_safety_enabled:
                guarded_limit = self._calculate_memory_guard_in_flight_limit(in_flight_limit)
                if guarded_limit < in_flight_limit:
                    in_flight_limit = max(min_in_flight_limit, guarded_limit)
                    with self._lock:
                        self.stats['safety_throttle_events'] += 1
            if self._export_memory_guard_mode != 'off':
                pressure = self._memory_pressure_ratio()
                if pressure >= self._export_memory_hard_ratio:
                    in_flight_limit = min(in_flight_limit, 1)
                elif pressure >= self._export_memory_soft_ratio:
                    in_flight_limit = max(min_in_flight_limit, in_flight_limit - 1)

            if in_flight_limit != old_limit:
                with self._lock:
                    self.stats['scheduler_adjustments'] += 1

        def _submit_render_tasks():
            nonlocal tasks_exhausted
            # 阶段二流水线背压：限制 render+save 总在途量，而不是只看渲染队列。
            # 写盘慢时，PIL 图像会滞留在 save 队列；继续提交渲染会放大内存峰值。
            while (
                (not tasks_exhausted)
                and ((len(render_future_to_task) + len(save_future_to_task)) < in_flight_limit)
            ):
                if self._is_cancel_requested(cancel_event, cancel_callback):
                    break
                if not self._enforce_memory_budget(
                    wait_for_relief=True,
                    cancel_event=cancel_event,
                    cancel_callback=cancel_callback,
                ):
                    # 如果已有任务在途，等待它们释放内存；否则允许以最低并发继续推进。
                    if render_future_to_task or save_future_to_task:
                        break
                try:
                    task = next(task_iter)
                except StopIteration:
                    tasks_exhausted = True
                    break
                future = render_executor.submit(self._render_task, task, cancel_event, cancel_callback)
                render_future_to_task[future] = task
                with self._lock:
                    self.stats['render_queue_submitted'] += 1
                _record_pipeline_depths()

        try:
            _submit_render_tasks()
            while render_future_to_task or save_future_to_task:
                if self._is_cancel_requested(cancel_event, cancel_callback):
                    for f in list(render_future_to_task.keys()):
                        f.cancel()
                    for f in list(save_future_to_task.keys()):
                        f.cancel()
                    render_executor.shutdown(wait=False, cancel_futures=True)
                    io_executor.shutdown(wait=False, cancel_futures=True)
                    return False

                all_futures = list(render_future_to_task.keys()) + list(save_future_to_task.keys())
                if not all_futures:
                    break
                done, _ = wait(all_futures, timeout=0.1, return_when=FIRST_COMPLETED)
                if self._export_safety_enabled and (time.time() - last_progress_ts) > float(self._export_safety_stall_timeout_seconds):
                    self.is_canceled = True
                    cancel_event.set()
                    self.last_error_message = (
                        f"导出保护触发：检测到任务{int(self._export_safety_stall_timeout_seconds)}秒无进展，"
                        "已自动停止以避免卡死或闪退。建议减少导出数量后重试。"
                    )
                    if hasattr(self.document, '_export_canceled'):
                        self.document._export_canceled = True
                    with self._lock:
                        self.stats['safety_stopped_by_timeout'] += 1
                    for f in list(render_future_to_task.keys()):
                        f.cancel()
                    for f in list(save_future_to_task.keys()):
                        f.cancel()
                    render_executor.shutdown(wait=False, cancel_futures=True)
                    io_executor.shutdown(wait=False, cancel_futures=True)
                    return False
                for future in done:
                    last_progress_ts = time.time()
                    if future in render_future_to_task:
                        task = render_future_to_task.pop(future)
                        try:
                            render_success, canvas, render_time = future.result()
                            if render_success and canvas is not None:
                                self._enforce_memory_budget(
                                    wait_for_relief=False,
                                    cancel_event=cancel_event,
                                    cancel_callback=cancel_callback,
                                )
                                save_future = io_executor.submit(
                                    self._save_rendered_task,
                                    task,
                                    canvas,
                                    render_time,
                                    cancel_event,
                                    cancel_callback
                                )
                                save_future_to_task[save_future] = task
                                with self._lock:
                                    self.stats['save_queue_submitted'] += 1
                                _record_pipeline_depths()
                            else:
                                failed_count += 1
                                consecutive_failures += 1
                        except Exception as e:
                            failed_count += 1
                            consecutive_failures += 1
                            print(f"[] : {getattr(task, 'filename', '')}, : {e}")
                        _submit_render_tasks()
                    elif future in save_future_to_task:
                        task = save_future_to_task.pop(future)
                        try:
                            save_result = future.result()
                            if isinstance(save_result, SaveTaskResult):
                                success = bool(save_result.success)
                                render_time = float(save_result.render_time or 0.0)
                                io_time = float(save_result.io_time or 0.0)
                                if (not success) and save_result.error:
                                    self.last_error_message = save_result.error
                            else:
                                success, render_time, io_time = save_result
                            if render_time > 0:
                                recent_render_times.append(render_time)
                                if len(recent_render_times) > 48:
                                    del recent_render_times[:-48]
                            if io_time > 0:
                                recent_io_times.append(io_time)
                                if len(recent_io_times) > 48:
                                    del recent_io_times[:-48]
                            _rebalance_in_flight_limit()
                            self._enforce_memory_budget(
                                wait_for_relief=False,
                                cancel_event=cancel_event,
                                cancel_callback=cancel_callback,
                            )
                            _record_pipeline_depths()
                            with self._lock:
                                self.stats['render_time'] += render_time
                                self.stats['io_time'] += io_time
                            if success:
                                completed_count += 1
                                consecutive_failures = 0
                                if self.file_completed_callback:
                                    self.file_completed_callback(f": {task.filename}")
                            else:
                                failed_count += 1
                                consecutive_failures += 1
                        except Exception as e:
                            failed_count += 1
                            consecutive_failures += 1
                            print(f"[] : {getattr(task, 'filename', '')}, : {e}")
                        else:
                            pass
                        # A completed save frees one pipeline slot. Submit more render
                        # work here as well as after render completion, otherwise the
                        # exporter can stop after the initial in-flight window.
                        _submit_render_tasks()

                    with self._lock:
                        self.current_progress = completed_count + failed_count
                        if self.progress_callback:
                            self.progress_callback(self.current_progress)
                    if self._export_safety_enabled:
                        processed = completed_count + failed_count
                        failure_rate = (failed_count / processed) if processed > 0 else 0.0
                        too_many_failures = consecutive_failures >= int(self._export_safety_max_consecutive_failures)
                        bad_failure_rate = (
                            processed >= int(self._export_safety_failure_rate_min_samples)
                            and failure_rate >= float(self._export_safety_failure_rate_limit)
                        )
                        if too_many_failures or bad_failure_rate:
                            self.is_canceled = True
                            cancel_event.set()
                            with self._lock:
                                self.stats['safety_stopped_by_failures'] += 1
                            if too_many_failures:
                                reason = f"连续失败达到{consecutive_failures}次"
                            else:
                                reason = f"失败率达到{failure_rate:.1%}（{failed_count}/{processed}）"
                            self.last_error_message = (
                                f"导出保护触发：{reason}，已自动停止以避免任务堆积导致程序不稳定。"
                                "建议降低导出数量或检查图层素材。"
                            )
                            if hasattr(self.document, '_export_canceled'):
                                self.document._export_canceled = True
                            for f in list(render_future_to_task.keys()):
                                f.cancel()
                            for f in list(save_future_to_task.keys()):
                                f.cancel()
                            render_executor.shutdown(wait=False, cancel_futures=True)
                            io_executor.shutdown(wait=False, cancel_futures=True)
                            return False
        finally:
            try:
                render_executor.shutdown(wait=not self.is_canceled, cancel_futures=True)
                io_executor.shutdown(wait=not self.is_canceled, cancel_futures=True)
            except Exception:
                try:
                    render_executor.shutdown(wait=False)
                except Exception:
                    pass
                try:
                    io_executor.shutdown(wait=False)
                except Exception:
                    pass
        
        success_rate = completed_count / self.total_tasks if self.total_tasks > 0 else 0
        with self._lock:
            self.stats['completed_count'] = completed_count
            self.stats['failed_count'] = failed_count
            self.stats['final_in_flight_limit'] = int(in_flight_limit)
        print(f"[] : {completed_count}/{self.total_tasks} ({success_rate:.1%})")
        
        processed_count = completed_count + failed_count
        return (
            not self.is_canceled
            and failed_count == 0
            and processed_count == self.total_tasks
        )

    def _render_task(self, task: ExportTask, cancel_event: Optional[threading.Event] = None,
                     cancel_callback: Optional[Callable[[], bool]] = None):
        """仅负责渲染，不做磁盘写入"""
        try:
            if self._is_cancel_requested(cancel_event, cancel_callback):
                return False, None, 0.0

            render_start = time.time()
            def _is_cancelled():
                return self._is_cancel_requested(cancel_event, cancel_callback)

            canvas = self._render_with_combination(
                task.combination,
                task=task,
                cancel_callback=_is_cancelled,
            )
            render_time = time.time() - render_start
            if canvas is None:
                self.last_error_message = f"渲染失败: {task.filename}"
                return False, None, render_time
            return True, canvas, render_time
        except Exception as e:
            self.last_error_message = f"渲染失败: {task.filename}: {e}"
            print(f"[] : {task.filename}, : {e}")
            return False, None, 0.0

    def _save_rendered_task(self, task: ExportTask, canvas: Image.Image, render_time: float,
                            cancel_event: Optional[threading.Event] = None,
                            cancel_callback: Optional[Callable[[], bool]] = None):
        """仅负责写盘，和渲染阶段解耦"""
        io_time = 0.0
        try:
            if self._is_cancel_requested(cancel_event, cancel_callback):
                return SaveTaskResult(
                    success=False,
                    render_time=render_time,
                    io_time=io_time,
                    file_path=getattr(task, 'file_path', ''),
                    error="导出已取消",
                )

            io_start = time.time()
            success = self._save_image_optimized(canvas, task.file_path)
            io_time = time.time() - io_start
            error = "" if success else (self.last_error_message or f"保存失败: {task.filename}")
            if error:
                self.last_error_message = error
            return SaveTaskResult(
                success=bool(success),
                render_time=render_time,
                io_time=io_time,
                file_path=str(getattr(task, 'file_path', '') or ''),
                error=error,
            )
        except Exception as e:
            self.last_error_message = f"保存失败: {task.filename}: {e}"
            print(f"[] : {task.filename}, : {e}")
            return SaveTaskResult(
                success=False,
                render_time=render_time,
                io_time=io_time,
                file_path=getattr(task, 'file_path', ''),
                error=self.last_error_message,
            )
        finally:
            try:
                if hasattr(canvas, 'close'):
                    canvas.close()
            except Exception:
                pass
            try:
                del canvas
            except Exception:
                pass
    
    def _execute_single_task(self, task: ExportTask, cancel_event: Optional[threading.Event] = None,
                             cancel_callback: Optional[Callable[[], bool]] = None) -> bool:
        """"""
        try:
            if self._is_cancel_requested(cancel_event, cancel_callback):
                return False

            render_start = time.time()

            # 渲染图像
            def _is_cancelled():
                return self._is_cancel_requested(cancel_event, cancel_callback)

            canvas = self._render_with_combination(
                task.combination,
                task=task,
                cancel_callback=_is_cancelled,
            )
            if canvas is None:
                print(f"[执行器] 错误：渲染返回None - {task.filename}")
                self.last_error_message = f"渲染失败: {task.filename}"
                return False

            if self._is_cancel_requested(cancel_event, cancel_callback):
                try:
                    del canvas
                except Exception:
                    pass
                return False
            if self._is_cancel_requested(cancel_event, cancel_callback):
                try:
                    del canvas
                except Exception:
                    pass
                return False

            render_time = time.time() - render_start

            # 
            io_start = time.time()
            success = self._save_image_optimized(canvas, task.file_path)
            io_time = time.time() - io_start

            # 
            with self._lock:
                self.stats['render_time'] += render_time
                self.stats['io_time'] += io_time

            return success
            
        except Exception as e:
            msg = f"渲染或保存失败: {task.filename}: {e}"
            print(f"[] : {task.filename}, : {e}")
            self.last_error_message = msg
            return False
        finally:
            try:
                if 'canvas' in locals() and hasattr(canvas, 'close'):
                    canvas.close()
            except Exception:
                pass
            try:
                if 'canvas' in locals():
                    del canvas
            except Exception:
                pass
    
    def _apply_layer_combination(self, combination):
        """"""
        visible_doc_indices = self._build_visible_doc_indices(self.document)
        use_visible_index_mode = self._should_use_visible_index_mode(self.document, combination, visible_doc_indices)
        for combo_layer_idx, image_path in combination.layer_states.items():
            doc_layer_idx = self._resolve_combination_layer_index(
                document=self.document,
                combo_layer_idx=combo_layer_idx,
                visible_doc_indices=visible_doc_indices,
                use_visible_index_mode=use_visible_index_mode
            )
            if doc_layer_idx is not None:
                layer = self.document.layers[doc_layer_idx]

                #  
                if not getattr(layer, 'visible', True):
                    continue

                # 🔧 关键修复：处理文字图层的虚拟路径
                from app.models.text_layer import TextLayer
                
                if isinstance(layer, TextLayer):
                    # 文字图层：解析虚拟路径并设置文本内容
                    if is_text_layer_virtual_path(image_path):
                        try:
                            _, text_content = parse_text_layer_virtual_path(image_path)
                            if text_content.strip():
                                # 批量导出时通过统一入口静默更新文字，避免污染 UI 信号流
                                if hasattr(self.document, '_is_batch_export_running') and self.document._is_batch_export_running:
                                    if hasattr(layer, 'set_current_text_silent'):
                                        layer.set_current_text_silent(text_content)
                                    else:
                                        layer._current_text = text_content
                                        layer._cached_image = None
                                else:
                                    if hasattr(layer, 'set_current_text'):
                                        layer.set_current_text(text_content)
                                    else:
                                        layer.current_text = text_content
                            else:
                                if self._verbose_logs:
                                    print(f"[应用组合] ⚠️ 无法解析虚拟路径: {image_path}")
                        except Exception as e:
                            print(f"[应用组合] ❌ 解析文字图层虚拟路径失败: {e}")
                    else:
                        if self._verbose_logs:
                            print(f"[应用组合] ⚠️ 文字图层路径格式错误: {image_path}")
                else:
                    # 普通图层：设置图像路径
                    if hasattr(layer, 'current_image_path'):
                        # 🔧 关键修复：使用公共属性setter，正确处理Layer和LegacyLayer
                        layer.current_image_path = image_path

                        # 清理缓存
                        if hasattr(layer, '_cached_image'):
                            layer._cached_image = None
                        if hasattr(layer, '_cached_image_path'):
                            layer._cached_image_path = None
                        if hasattr(layer, '_cache_valid'):
                            layer._cache_valid = False

                    elif hasattr(layer, 'current_image_path'):
                        # LegacyLayer
                        # 🔧 批量导出优化：直接设置内部属性，避免触发信号
                        layer.current_image_path = image_path

                        # 
                        if hasattr(layer, 'cached_image'):
                            layer.cached_image = None

                # 
                if hasattr(combination, 'layer_clone_settings') and combo_layer_idx in combination.layer_clone_settings:
                    clone_settings = combination.layer_clone_settings[combo_layer_idx]
                    self._apply_clone_settings(layer, clone_settings)

    def _render_with_combination(
        self,
        combination,
        task: Optional[ExportTask] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Optional[Image.Image]:
        """ - """
        cache_key = combination.combination_hash

        #  
        # 
        # if cache_key in self._render_cache:
        #     with self._lock:
        #         self.stats['cache_hits'] += 1
        #     return self._render_cache[cache_key].copy()

        target_document, use_shared_lock = self._get_target_document_for_render()
        lock_context = self._lock if use_shared_lock else nullcontext()
        with lock_context:
            visible_doc_indices = self._build_visible_doc_indices(target_document)
            use_visible_index_mode = self._should_use_visible_index_mode(target_document, combination, visible_doc_indices)
            trace_task_name = str(getattr(task, 'filename', '') or getattr(combination, 'combination_hash', '') or 'unknown_task')
            if self._export_trace_enabled:
                self._emit_export_trace(
                    f"任务={trace_task_name} 索引语义={'visible_index' if use_visible_index_mode else 'document_index'} "
                    f"visible_doc_indices={visible_doc_indices}"
                )
            #  
            original_states = {}
            for combo_layer_idx, image_path in combination.layer_states.items():
                doc_layer_idx = self._resolve_combination_layer_index(
                    document=target_document,
                    combo_layer_idx=combo_layer_idx,
                    visible_doc_indices=visible_doc_indices,
                    use_visible_index_mode=use_visible_index_mode
                )
                if self._export_trace_enabled:
                    layer_name = ""
                    if doc_layer_idx is not None and hasattr(target_document, 'layers') and 0 <= doc_layer_idx < len(target_document.layers):
                        layer_name = str(getattr(target_document.layers[doc_layer_idx], 'name', '') or '')
                    self._emit_export_trace(
                        f"任务={trace_task_name} 组合索引={combo_layer_idx} -> 文档索引={doc_layer_idx} "
                        f"图层={layer_name} 路径={str(image_path or '')}"
                    )
                if doc_layer_idx is not None:
                    layer = target_document.layers[doc_layer_idx]
                    # 🔧 关键修复：只保存用户配置的属性，不保存临时工作变量
                    # _current_image_path 是临时变量，每次组合都不同，不应该恢复
                    original_states[doc_layer_idx] = {
                        # 保存图像源相关属性（用户配置）
                        'image_source': getattr(layer, 'image_source', None),
                        '_image_source': getattr(layer, '_image_source', None),
                        'is_folder': getattr(layer, 'is_folder', None),
                        '_is_folder': getattr(layer, '_is_folder', None),
                        # 注意：不保存 _current_image_path 和缓存，这些是临时变量
                        # 保存分身设置
                        'clone_enabled': getattr(layer, 'clone_enabled', getattr(layer, '_clone_enabled', False)),
                        'clone_rows': getattr(layer, 'clone_rows', getattr(layer, '_clone_rows', 1)),
                        'clone_columns': getattr(layer, 'clone_columns', getattr(layer, '_clone_columns', 1)),
                        'clone_row_spacing': getattr(layer, 'clone_row_spacing', getattr(layer, '_clone_row_spacing', 0)),
                        'clone_column_spacing': getattr(layer, 'clone_column_spacing', getattr(layer, '_clone_column_spacing', 0))
                    }

            resolved_doc_indices_in_combo = set()
            try:
                # 导出任务隔离：清理未参与当前组合的图层临时状态，避免任务间状态串扰
                debug_layer_path_by_id = {}
                for combo_layer_idx in combination.layer_states.keys():
                    doc_layer_idx = self._resolve_combination_layer_index(
                        document=target_document,
                        combo_layer_idx=combo_layer_idx,
                        visible_doc_indices=visible_doc_indices,
                        use_visible_index_mode=use_visible_index_mode
                    )
                    if doc_layer_idx is not None:
                        resolved_doc_indices_in_combo.add(int(doc_layer_idx))

                try:
                    from app.models.text_layer import TextLayer as _TextLayerForIsolation
                except Exception:
                    _TextLayerForIsolation = None
                if hasattr(target_document, 'layers'):
                    mutable_doc_indices = set(self._plan_mutable_doc_indices or [])
                    for doc_idx, layer in enumerate(target_document.layers):
                        if doc_idx in resolved_doc_indices_in_combo:
                            continue
                        if mutable_doc_indices and doc_idx not in mutable_doc_indices:
                            # 非动态替换图层不参与清理，避免破坏固定图层（如镂空参考层）的匹配输入
                            continue
                        if not getattr(layer, 'visible', True):
                            continue
                        if _TextLayerForIsolation is not None and isinstance(layer, _TextLayerForIsolation):
                            continue
                        if hasattr(layer, 'current_image_path'):
                            try:
                                layer.current_image_path = None
                            except Exception:
                                pass
                        for attr in ('cached_image', '_cached_image', '_cached_image_path', '_current_image_cache'):
                            if hasattr(layer, attr):
                                try:
                                    setattr(layer, attr, None)
                                except Exception:
                                    pass

                # 🔧 强化预计算：应用预计算的完整参数
                for combo_layer_idx, image_path in combination.layer_states.items():
                    doc_layer_idx = self._resolve_combination_layer_index(
                        document=target_document,
                        combo_layer_idx=combo_layer_idx,
                        visible_doc_indices=visible_doc_indices,
                        use_visible_index_mode=use_visible_index_mode
                    )
                    if doc_layer_idx is not None:
                        layer = target_document.layers[doc_layer_idx]
                        debug_layer_path_by_id[id(layer)] = str(image_path or "")
                        
                        # 检查图层可见性
                        if not getattr(layer, 'visible', True):
                            continue

                        # 1. 设置图片路径或处理文字图层虚拟路径
                        from app.models.text_layer import TextLayer
                        
                        if isinstance(layer, TextLayer):
                            # 🔧 关键修复：处理文字图层的虚拟路径
                            if is_text_layer_virtual_path(image_path):
                                try:
                                    _, text_content = parse_text_layer_virtual_path(image_path)
                                    if text_content.strip():
                                        if hasattr(layer, 'set_current_text'):
                                            layer.set_current_text(
                                                text_content,
                                                emit_signals=not bool(getattr(target_document, '_is_batch_export_running', False))
                                            )
                                        else:
                                            layer.current_text = text_content
                                    else:
                                        if self._verbose_logs:
                                            print(f"[执行器] ⚠️ 无法解析文字图层虚拟路径: {image_path}")
                                except Exception as e:
                                    print(f"[执行器] ❌ 解析文字图层虚拟路径失败: {e}")
                            else:
                                if self._verbose_logs:
                                    print(f"[执行器] ⚠️ 文字图层路径不是虚拟路径格式: {image_path}")
                        else:
                            # 普通图层：设置图像路径
                            if hasattr(layer, 'current_image_path'):
                                # 🔧 关键修复：使用公共属性setter
                                layer.current_image_path = image_path

                        # 2. 清除缓存
                        cache_attrs = ['cached_image', '_cached_image', '_cached_image_path', '_current_image_cache']
                        for attr in cache_attrs:
                            if hasattr(layer, attr):
                                setattr(layer, attr, None)

                        # 3. 🔧 关键：应用预计算的随机变换参数
                        # 文字图层不参与随机缩放/旋转，避免批量导出出现文字尺寸抖动
                        if hasattr(combination, 'random_transforms') and combination.random_transforms:
                            if combo_layer_idx in combination.random_transforms and not isinstance(layer, TextLayer):
                                transforms = combination.random_transforms[combo_layer_idx]
                                # 设置预计算的随机变换参数
                                if hasattr(layer, '_current_random_offset_x'):
                                    layer._current_random_offset_x = transforms.get('random_offset_x', 0)
                                    layer._current_random_offset_y = transforms.get('random_offset_y', 0)
                                    layer._current_random_scale = transforms.get('random_scale', 1.0)
                                    layer._current_random_rotation = transforms.get('random_rotation', 0.0)
                        
                        # 4. 🔧 关键：应用预计算的图层参数（如果有）
                        if hasattr(combination, 'layer_parameters') and combination.layer_parameters:
                            if combo_layer_idx in combination.layer_parameters:
                                params = combination.layer_parameters[combo_layer_idx]
                                self._apply_layer_parameters_fast(layer, params)

                        # 5. 加载图片
                        if hasattr(layer, 'get_random_image') and image_path:
                            try:
                                if hasattr(layer, '_load_and_process_image') and os_module.path.isfile(image_path):
                                    loaded_image = layer._load_and_process_image(image_path)
                                    if loaded_image:
                                        if hasattr(layer, '_cached_image'):
                                            layer._cached_image = loaded_image
                                        if hasattr(layer, 'cached_image'):
                                            layer.cached_image = loaded_image
                            except Exception as e:
                                if self._verbose_logs:
                                    print(f"[执行器] ⚠️ 加载图片失败 '{layer.name}': {e}")

                        # 6. 应用分身设置
                        if hasattr(combination, 'layer_clone_settings') and combo_layer_idx in combination.layer_clone_settings:
                            clone_settings = combination.layer_clone_settings[combo_layer_idx]
                            self._apply_clone_settings(layer, clone_settings)

                self._emit_runtime_snapshot_for_indices(
                    document=target_document,
                    doc_indices=resolved_doc_indices_in_combo,
                    task_name=trace_task_name,
                    stage='before_render'
                )

                # 处理文字图层随机化
                try:
                    from app.models.text_layer import TextLayer
                    combo_text_doc_indices = set()
                    for combo_idx, path in combination.layer_states.items():
                        if is_text_layer_virtual_path(path):
                            doc_idx = self._resolve_combination_layer_index(
                                document=target_document,
                                combo_layer_idx=combo_idx,
                                visible_doc_indices=visible_doc_indices,
                                use_visible_index_mode=use_visible_index_mode
                            )
                            if doc_idx is not None:
                                combo_text_doc_indices.add(doc_idx)

                    if hasattr(target_document, 'layers'):
                        if hasattr(target_document, 'binding_manager') and target_document.binding_manager and getattr(target_document.binding_manager, 'global_enabled', False):
                            categories = []
                            try:
                                categories = target_document._get_binding_common_categories() or []
                                selected = []
                                for group in target_document.binding_manager.binding_groups.values():
                                    if getattr(group, 'last_selected_category', None):
                                        selected.append(group.last_selected_category)
                                if selected:
                                    categories = selected
                            except Exception:
                                categories = []
                            for i, layer in enumerate(target_document.layers):
                                if getattr(layer, 'visible', True) and isinstance(layer, TextLayer) and i not in combo_text_doc_indices:
                                    try:
                                        target_document._randomize_text_layer_with_binding_categories(layer, categories)
                                    except Exception:
                                        layer.randomize_text()
                        else:
                            for i, layer in enumerate(target_document.layers):
                                if getattr(layer, 'visible', True) and isinstance(layer, TextLayer) and i not in combo_text_doc_indices:
                                    layer.randomize_text()
                except Exception:
                    pass

                # 🔧 关键修复：使用与预览一致的渲染方式，避免颜色偏差
                # 导入快速渲染器，使用与预览窗口完全相同的渲染逻辑和参数
                fast_renderer = self._get_thread_local_fast_renderer()
                if self._export_trace_enabled:
                    task_name = ""
                    try:
                        task_name = str(getattr(task, 'filename', '') or '')
                    except Exception:
                        task_name = ""
                    if not task_name:
                        task_name = str(getattr(combination, 'combination_hash', '') or 'unknown_task')
                    self._emit_export_trace(f"开始任务: {task_name}")
                    try:
                        setattr(target_document, '_export_debug_trace_enabled', True)
                        setattr(target_document, '_export_debug_trace_task', task_name)
                        setattr(target_document, '_export_debug_trace_layer_paths', dict(debug_layer_path_by_id))
                        setattr(target_document, '_export_debug_trace_file', self._export_trace_file)
                    except Exception:
                        pass
                if self._preload_enabled:
                    setattr(target_document, '_batch_preloaded_images', self._image_preload_cache)
                else:
                    try:
                        if hasattr(target_document, '_batch_preloaded_images'):
                            delattr(target_document, '_batch_preloaded_images')
                    except Exception:
                        pass
                
                if self._is_cancel_requested(None, cancel_callback):
                    return None

                # 阶段二：渲染入口收束到 RenderService，线程本地 FastRenderer 仍由执行器注入，
                # 避免回到全局 renderer 导致高并发状态串扰。
                from app.services.render_service import RenderRequest, get_render_service

                render_result = get_render_service().render(
                    RenderRequest(
                        document=target_document,
                        mode="export",
                        quality_profile=self._resolve_export_quality_profile(),
                        batch_mode=True,
                        renderer=fast_renderer,
                        cancel_callback=cancel_callback,
                    )
                )
                canvas = render_result.image
                if not render_result.ok:
                    error_msg = str(render_result.error or "渲染失败")
                    self.last_error_message = f"渲染失败: {trace_task_name}: {error_msg}"
                    if self._export_trace_enabled:
                        self._emit_export_trace(self.last_error_message)
                    return None

                # 仅在非批处理模式下启用渲染缓存，批处理模式下禁用缓存以减少内存占用
                if not self.is_batch_mode and canvas and self._should_cache_render(combination):
                    cache_key = self._generate_smart_cache_key(combination)
                    if len(self._render_cache) < self.max_cache_size:
                        self._render_cache[cache_key] = canvas.copy()
                        self.stats['cache_hits'] += 1

                self._emit_runtime_snapshot_for_indices(
                    document=target_document,
                    doc_indices=resolved_doc_indices_in_combo,
                    task_name=trace_task_name,
                    stage='after_render_before_restore'
                )

                return canvas

            finally:
                try:
                    if hasattr(target_document, '_export_debug_trace_enabled'):
                        delattr(target_document, '_export_debug_trace_enabled')
                    if hasattr(target_document, '_export_debug_trace_task'):
                        delattr(target_document, '_export_debug_trace_task')
                    if hasattr(target_document, '_export_debug_trace_layer_paths'):
                        delattr(target_document, '_export_debug_trace_layer_paths')
                except Exception:
                    pass
                try:
                    if hasattr(target_document, '_batch_preloaded_images'):
                        delattr(target_document, '_batch_preloaded_images')
                except Exception:
                    pass
                # 🔧 关键修复：只恢复用户配置的属性，不恢复临时工作变量
                for layer_idx, original_state in original_states.items():
                    if layer_idx < len(target_document.layers):
                        layer = target_document.layers[layer_idx]

                        # 恢复图像源相关属性（用户配置）
                        if hasattr(layer, '_image_source'):
                            layer._image_source = original_state.get('_image_source')
                        if hasattr(layer, 'image_source'):
                            layer.image_source = original_state.get('image_source')
                        if hasattr(layer, '_is_folder'):
                            layer._is_folder = original_state.get('_is_folder')
                        if hasattr(layer, 'is_folder'):
                            layer.is_folder = original_state.get('is_folder')
                        
                        # 🔧 关键：不恢复 _current_image_path 和缓存
                        # 这些是临时变量，每次组合都不同，恢复会导致图片重复

                        # 批量模式下优先走内部字段，避免触发 changed 信号导致预览卡顿
                        try:
                            if hasattr(layer, '_clone_enabled'):
                                layer._clone_enabled = original_state['clone_enabled']
                            elif hasattr(layer, 'clone_enabled'):
                                layer.clone_enabled = original_state['clone_enabled']

                            if hasattr(layer, '_clone_rows'):
                                layer._clone_rows = original_state['clone_rows']
                            elif hasattr(layer, 'clone_rows'):
                                layer.clone_rows = original_state['clone_rows']

                            if hasattr(layer, '_clone_columns'):
                                layer._clone_columns = original_state['clone_columns']
                            elif hasattr(layer, 'clone_columns'):
                                layer.clone_columns = original_state['clone_columns']

                            if hasattr(layer, '_clone_row_spacing'):
                                layer._clone_row_spacing = original_state['clone_row_spacing']
                            elif hasattr(layer, 'clone_row_spacing'):
                                layer.clone_row_spacing = original_state['clone_row_spacing']

                            if hasattr(layer, '_clone_column_spacing'):
                                layer._clone_column_spacing = original_state['clone_column_spacing']
                            elif hasattr(layer, 'clone_column_spacing'):
                                layer.clone_column_spacing = original_state['clone_column_spacing']
                        except Exception as e:
                            print(f"[] : {e}")

                self._emit_runtime_snapshot_for_indices(
                    document=target_document,
                    doc_indices=resolved_doc_indices_in_combo,
                    task_name=trace_task_name,
                    stage='after_restore'
                )

    def _should_use_gpu_for_task(self) -> bool:
        """GPU"""
        try:
            # GPU
            try:
                import torch
                if not torch.cuda.is_available():
                    return False
            except ImportError:
                # torchFalse
                return False

            # 
            canvas_size = self.document.canvas_width * self.document.canvas_height
            layer_count = len([layer for layer in self.document.layers if layer.visible])

            # GPU
            if canvas_size > 2000000 or layer_count > 5:  # 2MP+  5+ 
                print(f"[] GPU: {canvas_size}, {layer_count}")
                return True

            return False
        except (ImportError, Exception):
            return False

    def _should_optimize_memory(self) -> bool:
        """"""
        canvas_size = self.document.canvas_width * self.document.canvas_height
        layer_count = len([layer for layer in self.document.layers if layer.visible])

        # 
        should_optimize = canvas_size > 4000000 or layer_count > 10  # 4MP+  10+ 
        if should_optimize:
            print(f"[] : {canvas_size}, {layer_count}")
        return should_optimize

    def _should_cache_render(self, combination) -> bool:
        """"""
        #  
        # 
        cache_key = self._generate_smart_cache_key(combination)
        return cache_key not in self._render_cache

    def _generate_smart_cache_key(self, combination) -> str:
        """"""
        # 
        layer_states = []
        for layer_idx, image_path in combination.layer_states.items():
            layer_states.append(f"{layer_idx}:{os_module.path.basename(image_path) if image_path else 'none'}")

        return f"render:{'|'.join(sorted(layer_states))}"

    def _calculate_optimal_workers(self) -> int:
        """计算最优工作线程数 - 优化内存使用和性能"""
        cpu_count = os_module.cpu_count() or 4
        # 支持手动覆盖并行度，便于在高性能机器上压榨吞吐
        workers_override = os_module.environ.get("BTPW_BATCH_EXPORT_WORKERS", "").strip()
        if workers_override:
            try:
                override = max(1, int(workers_override))
                if self.is_batch_mode:
                    print(f"[批处理] 使用环境变量并行度覆盖: {override}")
                return override
            except ValueError:
                if self.is_batch_mode:
                    print(f"[批处理] 并行度覆盖无效，回退自动计算: {workers_override}")

        # 计算画布面积和可见图层数
        canvas_size = self.document.canvas_width * self.document.canvas_height
        layer_count = len([layer for layer in self.document.layers if layer.visible])
        
        # 检查是否有异形形状图层 - 异形形状处理更耗内存
        has_shaped_layers = any(hasattr(layer, '_shape_type') for layer in self.document.layers if layer.visible)
        shaped_layer_count = sum(1 for layer in self.document.layers if layer.visible and hasattr(layer, '_shape_type'))

        # 基础规则：根据画布大小和图层数量调整（更积极的并发上限）
        if canvas_size > 4000000 or layer_count > 10:  # 大图或复杂项目
            if has_shaped_layers:
                optimal_workers = min(3, max(1, cpu_count // 2))
            else:
                optimal_workers = min(4, max(1, cpu_count // 2))
        elif canvas_size > 1000000 or layer_count > 5:  # 中等大小
            if has_shaped_layers:
                optimal_workers = min(4, max(1, cpu_count // 2 + 1))
            else:
                optimal_workers = min(cpu_count, 6)
        else:  # 小项目
            if has_shaped_layers:
                optimal_workers = min(5, cpu_count)
            else:
                optimal_workers = min(cpu_count, 8)

        # 高压缩目标通常更吃CPU，略降并发减少抖动
        if self._max_file_size_kb > 0:
            optimal_workers = max(1, optimal_workers - 1)

        # I/O策略联动：速度档适度增并发，体积档保守
        if str(self._io_profile) == 'speed':
            optimal_workers = min(cpu_count, optimal_workers + 1)
        elif str(self._io_profile) == 'size':
            optimal_workers = max(1, optimal_workers - 1)

        # 受控并发：给 UI / 系统预留资源，避免“跑满但不快”
        optimal_workers = self._apply_worker_hard_cap(optimal_workers, cpu_count=cpu_count)
        hard_cap = self._apply_worker_hard_cap(cpu_count, cpu_count=cpu_count)
        if self.is_batch_mode:
            print(
                f"[批处理] 并行度: {optimal_workers} "
                f"(CPU: {cpu_count}, 上限: {hard_cap}, 画布: {canvas_size}, 图层: {layer_count}, 异形: {shaped_layer_count})"
            )
        return optimal_workers

    def _preload_images_for_plan(self, plan: 'PrecomputedExportPlan', cancel_callback: Optional[Callable[[], bool]] = None):
        """"""
        if not self._preload_enabled:
            return

        print("[] ...")
        usage_counter = Counter()
        first_seen = {}

        # 
        for task_index, task in enumerate(plan.tasks):
            for layer_idx, image_path in task.combination.layer_states.items():
                if image_path and isinstance(image_path, str) and (not is_text_layer_virtual_path(image_path)) and os_module.path.exists(image_path):
                    usage_counter[image_path] += 1
                    first_seen.setdefault(image_path, task_index)

        # 
        unique_images = list(usage_counter.keys())
        max_preload = min(len(unique_images), self._batch_preload_max_images if self.is_batch_mode else 50)
        preload_count = 0
        max_bytes = max(64, self._batch_preload_memory_mb) * 1024 * 1024
        memory_limit_mb = self._refresh_memory_budget()
        if self.is_batch_mode and memory_limit_mb > 0:
            preload_budget_ratio = 0.06 if self._export_memory_guard_mode == 'low' else 0.14
            max_bytes = min(max_bytes, int(memory_limit_mb * preload_budget_ratio) * 1024 * 1024)
        try:
            import psutil
            available_bytes = int(psutil.virtual_memory().available)
            max_bytes = min(max_bytes, max(32 * 1024 * 1024, int(available_bytes * 0.18)))
        except Exception:
            pass
        preload_candidates = sorted(
            unique_images,
            key=lambda p: (-int(usage_counter.get(p, 0)), int(first_seen.get(p, 0)), str(p).lower())
        )[:max_preload]
        skipped_by_memory = 0

        for image_path in preload_candidates:
            if self._is_cancel_requested(None, cancel_callback):
                return
            if self._memory_pressure_ratio() >= self._export_memory_soft_ratio:
                skipped_by_memory += 1
                break
            try:
                from PIL import Image
                with Image.open(image_path) as img:
                    img_rgba = img.convert('RGBA') if img.mode != 'RGBA' else img
                    img_rgba.load()
                    cached = img_rgba.copy()
                    approx_bytes = int(cached.width * cached.height * 4)
                    if self.is_batch_mode and (self._image_preload_cache_bytes + approx_bytes > max_bytes):
                        if self._verbose_logs:
                            print(f"[批处理] 预读达到内存上限，停止继续预读")
                        skipped_by_memory += 1
                        break
                    self._image_preload_cache[image_path] = cached
                    self._image_preload_cache_bytes += approx_bytes
                preload_count += 1
            except Exception as e:
                print(f"[]  {image_path}: {e}")

        with self._lock:
            self.stats['preload_unique_images'] = len(unique_images)
            self.stats['preload_loaded_images'] = preload_count
            self.stats['preload_skipped_by_memory'] = skipped_by_memory
            self.stats['preload_memory_mb'] = float(self._image_preload_cache_bytes) / (1024 * 1024)
        print(f"[] : {preload_count}/{len(unique_images)} (≈{self._image_preload_cache_bytes // (1024 * 1024)}MB)")

    def _get_preloaded_image(self, image_path: str):
        """"""
        cached = self._image_preload_cache.get(image_path)
        if cached is not None:
            try:
                self._image_preload_cache.move_to_end(image_path)
            except Exception:
                pass
            with self._lock:
                self.stats['preload_hits'] += 1
        return cached

    def _clear_preload_cache(self):
        """清除预加载缓存，释放内存"""
        self._image_preload_cache.clear()
        self._image_preload_cache_bytes = 0
        if self.is_batch_mode:
            print("[批处理] 已清除预加载缓存")
        else:
            print("[] ")
    
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

    def _render_with_cache(self, combination) -> Optional[Image.Image]:
        """"""
        cache_key = combination.combination_hash
        
        #  
        # 
        # if cache_key in self._render_cache:
        #     with self._lock:
        #         self.stats['cache_hits'] += 1
        #     return self._render_cache[cache_key].copy()
        
        # 
        try:
            canvas = self.document.render_composition(
                random_mode=False,  # 
                optimize_memory=True,
                is_batch_mode=True,
                enable_gpu=False  # GPU
            )
            
            #  
            # 
            # if len(self._render_cache) < 10:  # 10
            #     self._render_cache[cache_key] = canvas.copy()
            
            return canvas
            
        except Exception as e:
            print(f"[] : {e}")
            return None

    def _can_use_vips_backend(self, file_format: str) -> bool:
        """判断当前任务是否走 pyvips 保存链路。"""
        enabled, _ = self._get_vips_policy_for_format(file_format)
        return enabled

    def _get_vips_policy_for_format(self, file_format: str):
        """返回 (是否启用vips, 原因) 供日志和统计使用。"""
        try:
            backend = str(getattr(self, '_export_backend', 'auto') or 'auto').lower()
            if backend not in ('auto', 'pyvips', 'vips'):
                return False, f"export_backend={backend}"

            # 避免“先vips后回退Pillow”导致总耗时更高：有大小限制默认禁用vips
            if int(getattr(self, '_max_file_size_kb', 0) or 0) > 0 and (not bool(getattr(self, '_vips_allow_with_size_limit', False))):
                return False, "size_limit_prefers_pillow"

            fmt = str(file_format).lower()
            if fmt not in ('jpg', 'jpeg', 'png', 'webp'):
                return False, f"format_not_supported:{fmt}"

            from app.utils.vips_export_engine import VipsExportEngine
            if not bool(VipsExportEngine.is_available()):
                return False, "pyvips_unavailable"
            return True, "enabled"
        except Exception as e:
            return False, f"policy_exception:{e}"

    def _is_vips_runtime_available(self) -> bool:
        """运行时检查 pyvips 是否可用。"""
        try:
            from app.utils.vips_export_engine import VipsExportEngine
            return bool(VipsExportEngine.is_available())
        except Exception:
            return False

    def _save_image_with_vips(self, image: Image.Image, file_path: str, file_format: str) -> bool:
        """使用 pyvips 进行编码保存。"""
        from app.utils.vips_export_engine import VipsExportEngine
        return bool(
            VipsExportEngine.save_image(
                image=image,
                file_path=file_path,
                file_format=file_format,
                io_profile=str(getattr(self, '_io_profile', 'balanced') or 'balanced'),
                jpeg_quality=int(getattr(self, '_jpeg_quality_override', 0) or 0),
                png_compress_level=int(getattr(self, '_png_compress_level_override', -1)),
                max_file_size_kb=int(getattr(self, '_max_file_size_kb', 0) or 0),
            )
        )

    def _resolve_export_quality_profile(self) -> str:
        """统一解析导出质量档位，供渲染和编码共用。"""
        try:
            settings = getattr(self.document, 'export_settings', {}) or {}
            profile = str(settings.get('export_quality_profile', '') or '').strip().lower()
            if profile in ('quality', 'balanced', 'speed', 'size'):
                return profile
        except Exception:
            pass

        io_profile = str(getattr(self, '_io_profile', 'balanced') or 'balanced').strip().lower()
        if io_profile == 'speed':
            return 'speed'
        if io_profile == 'size':
            return 'size'
        return 'quality'
    
    def _save_image_optimized(self, image: Image.Image, file_path: str) -> bool:
        """"""
        try:
            max_kb = int(getattr(self, '_max_file_size_kb', 0) or 0)
            # 目录存在性检测（写权限已在导出启动阶段统一验证）
            out_dir = os_module.path.dirname(file_path) or '.'
            if out_dir and not os_module.path.isdir(out_dir):
                os_module.makedirs(out_dir, exist_ok=True)
            # 
            file_format = os_module.path.splitext(file_path)[1].lower().lstrip('.')

            # 统一编码策略：默认质量优先，只有显式 size 档才执行有损体积压缩。
            try:
                from app.services.export_service import ExportJob, get_export_service

                settings = getattr(self.document, 'export_settings', {}) or {}
                quality_profile = self._resolve_export_quality_profile()
                backend = str(settings.get('export_backend', getattr(self, '_export_backend', 'pillow')) or 'pillow')
                report = get_export_service().save_image(
                    image,
                    ExportJob(
                        file_path=file_path,
                        file_format=file_format,
                        quality_profile=quality_profile,
                        max_file_size_kb=int(getattr(self, '_max_file_size_kb', 0) or 0),
                        jpeg_quality=int(getattr(self, '_jpeg_quality_override', 0) or 0),
                        png_compress_level=int(getattr(self, '_png_compress_level_override', -1)),
                        backend=backend,
                        allow_lossy_size_reduction=bool(settings.get('allow_lossy_size_reduction', False)),
                    )
                )
                if report.success:
                    with self._lock:
                        self.stats['written_bytes'] += max(0, int(report.written_bytes or 0))
                        self.stats['export_service_time'] += max(0.0, float(report.elapsed or 0.0))
                        if report.backend_used == 'pyvips':
                            self.stats['vips_attempts'] += 1
                            self.stats['vips_save_count'] += 1
                        else:
                            self.stats['pillow_save_count'] += 1
                    return True
                self.last_error_message = report.error or f"保存文件失败: {file_path}"
                with self._lock:
                    self.stats['export_service_time'] += max(0.0, float(report.elapsed or 0.0))
                    self.stats['save_error_count'] += 1
                return False
            except Exception:
                # 服务层异常时回落到旧保存路径，保持可用性。
                pass
            
            # JPEG
            if file_format in ['jpg', 'jpeg'] and image.mode == 'RGBA':
                # 
                bg_rgba = Image.new('RGBA', image.size, (255, 255, 255, 255))
                from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
                image_rgba = image if image.mode == 'RGBA' else image.convert('RGBA')
                composited = UnifiedAlphaCompositor.blend_normal(bg_rgba, image_rgba, 1.0)
                image = composited.convert('RGB')

            # 优先尝试 pyvips 后端（可选依赖，失败自动回退 Pillow）
            if self._can_use_vips_backend(file_format):
                with self._lock:
                    self.stats['vips_attempts'] += 1
                need_pillow_fallback = False
                try:
                    if self._save_image_with_vips(image, file_path, file_format):
                        current_size = 0
                        try:
                            current_size = int(os_module.path.getsize(file_path))
                        except Exception:
                            current_size = 0
                        # 有大小限制时：优先尝试 vips，超限再回退到 Pillow 压缩链路
                        if max_kb > 0 and current_size > max_kb * 1024:
                            need_pillow_fallback = True
                            with self._lock:
                                self.stats['vips_size_fallback_count'] += 1
                        else:
                            try:
                                with self._lock:
                                    self.stats['written_bytes'] += max(0, current_size)
                                    self.stats['vips_save_count'] += 1
                            except Exception:
                                pass
                            return True
                    else:
                        need_pillow_fallback = True
                except Exception:
                    need_pillow_fallback = True
                if need_pillow_fallback:
                    with self._lock:
                        self.stats['vips_fallback_count'] += 1
            
            success = False
            if self._io_profile == 'speed':
                # 速度优先：降低编码开销，减少CPU占用
                if file_format in ['jpg', 'jpeg']:
                    q = self._jpeg_quality_override if self._jpeg_quality_override > 0 else 90
                    image.save(file_path, quality=max(60, min(98, q)), optimize=False)
                elif file_format == 'png':
                    level = self._png_compress_level_override if self._png_compress_level_override >= 0 else 1
                    image.save(file_path, format='PNG', compress_level=max(0, min(9, level)), optimize=False)
                else:
                    image.save(file_path)
                success = True
            elif self._io_profile == 'size':
                # 体积优先：更激进压缩
                if file_format in ['jpg', 'jpeg']:
                    q = self._jpeg_quality_override if self._jpeg_quality_override > 0 else 94
                    image.save(file_path, quality=max(60, min(98, q)), optimize=True, progressive=True)
                elif file_format == 'png':
                    level = self._png_compress_level_override if self._png_compress_level_override >= 0 else 9
                    image.save(file_path, format='PNG', compress_level=max(0, min(9, level)), optimize=True)
                else:
                    image.save(file_path, optimize=True)
                success = True
            else:
                # 平衡模式：优先使用现有高质量保存器
                from app.utils.image_quality import ImageQualityManager
                success = ImageQualityManager.save_high_quality_image(
                    image, file_path, format_hint=file_format
                )

                if not success:
                    if file_format in ['jpg', 'jpeg']:
                        q = self._jpeg_quality_override if self._jpeg_quality_override > 0 else 95
                        image.save(file_path, quality=max(60, min(98, q)), optimize=True)
                    elif file_format == 'png':
                        level = self._png_compress_level_override if self._png_compress_level_override >= 0 else 6
                        image.save(file_path, format='PNG', compress_level=max(0, min(9, level)), optimize=True)
                    else:
                        image.save(file_path, optimize=True)

            # 额外：文件大小上限控制（KB），0 表示不限制
            try:
                if max_kb and max_kb > 0:
                    target_bytes = max_kb * 1024
                    # 使用内存缓冲区尝试压缩到目标大小
                    if file_format in ['jpg', 'jpeg']:
                        # 二分搜索质量参数
                        low, high = 40, 95
                        best_buf = None
                        best_quality = high
                        # 确保是RGB
                        img_rgb = image
                        if img_rgb.mode == 'RGBA':
                            bg_rgba = Image.new('RGBA', img_rgb.size, (255, 255, 255, 255))
                            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
                            img_rgba = img_rgb if img_rgb.mode == 'RGBA' else img_rgb.convert('RGBA')
                            composited = UnifiedAlphaCompositor.blend_normal(bg_rgba, img_rgba, 1.0)
                            img_rgb = composited.convert('RGB')
                        for _ in range(7):
                            q = (low + high) // 2
                            buf = io.BytesIO()
                            img_rgb.save(buf, format='JPEG', quality=q, optimize=True)
                            size = buf.tell()
                            if size <= target_bytes:
                                best_buf = buf
                                best_quality = q
                                low = q + 1
                            else:
                                high = q - 1
                        if best_buf is None:
                            # 仍未满足，使用最低质量写入
                            buf = io.BytesIO()
                            img_rgb.save(buf, format='JPEG', quality=max(low, 30), optimize=True)
                            best_buf = buf
                        with open(file_path, 'wb') as f:
                            f.write(best_buf.getvalue())
                    elif file_format in ['png']:
                        # 先尝试优化保存
                        buf = io.BytesIO()
                        image.save(buf, format='PNG', optimize=True)
                        if buf.tell() > target_bytes:
                            # 量化为调色板减少大小
                            quant = image.convert('P', palette=Image.ADAPTIVE, colors=256)
                            buf = io.BytesIO()
                            quant.save(buf, format='PNG', optimize=True)
                        # 如果仍然超出，尝试降低颜色数量
                        if buf.tell() > target_bytes:
                            quant = image.convert('P', palette=Image.ADAPTIVE, colors=128)
                            buf = io.BytesIO()
                            quant.save(buf, format='PNG', optimize=True)
                        with open(file_path, 'wb') as f:
                            f.write(buf.getvalue())
                    # 其他格式按默认保存即可
            except Exception:
                # 大小控制失败时，保留已有文件
                pass

            try:
                written = int(os_module.path.getsize(file_path))
                with self._lock:
                    self.stats['written_bytes'] += max(0, written)
            except Exception:
                pass

            return True
        
        except Exception as e:
            msg = f"保存文件失败: {file_path}: {e}"
            print(f"[] : {file_path}, : {e}")
            self.last_error_message = msg
            return False
    
    def _cleanup_resources(self):
        """"""
        try:
            # 
            self._render_cache.clear()
            
            # 
            gc.collect()
            
            print("[] ")
            try:
                from app.utils.intelligent_render_cache import clear_global_cache as _irc_clear
                _irc_clear()
            except Exception:
                pass
            try:
                from app.utils.intelligent_cache_system import get_intelligent_cache as _get_ics
                _get_ics().clear_all_caches()
            except Exception:
                pass
            try:
                from app.utils.advanced_image_cache import get_advanced_image_cache as _get_aic
                _get_aic().clear_cache()
            except Exception:
                pass
            
            # 批导任务使用 worker 文档，结束时不再清理主 UI 文档，避免污染预览状态。
            
        except Exception as e:
            print(f"[] : {e}")
    
    def _collect_plan_mutable_doc_indices(self, plan: PrecomputedExportPlan, document) -> set:
        """收集本次计划里会被动态替换的图层索引。"""
        mutable_indices = set()
        try:
            if not plan or not getattr(plan, 'tasks', None) or not hasattr(document, 'layers'):
                return mutable_indices
            visible_doc_indices = self._build_visible_doc_indices(document)
            for task in plan.tasks:
                combination = getattr(task, 'combination', None)
                if combination is None or not hasattr(combination, 'layer_states'):
                    continue
                use_visible_index_mode = self._should_use_visible_index_mode(document, combination, visible_doc_indices)
                for combo_layer_idx in combination.layer_states.keys():
                    doc_layer_idx = self._resolve_combination_layer_index(
                        document=document,
                        combo_layer_idx=combo_layer_idx,
                        visible_doc_indices=visible_doc_indices,
                        use_visible_index_mode=use_visible_index_mode
                    )
                    if doc_layer_idx is not None:
                        mutable_indices.add(int(doc_layer_idx))
        except Exception:
            return mutable_indices
        return mutable_indices

    def _clear_layer_image_paths(
        self,
        target_doc_indices: Optional[set] = None,
        document=None,
        document_data: Optional[Dict[str, object]] = None,
    ):
        """清理图层临时图像路径
        
        优先作用于 worker 快照或显式传入的文档；默认不直接修改主 UI 文档。
        """
        try:
            if isinstance(document_data, dict):
                layers_data = document_data.get('layers', [])
                if not isinstance(layers_data, list):
                    return
                cleared_count = 0
                runtime_keys = (
                    'current_image_path', '_current_image_path',
                    'cached_image', '_cached_image', '_cached_image_path',
                    '_current_image_cache', '_cache_valid',
                )
                for idx, layer_data in enumerate(layers_data):
                    if target_doc_indices and idx not in target_doc_indices:
                        continue
                    if not isinstance(layer_data, dict):
                        continue
                    for key in runtime_keys:
                        if key in layer_data:
                            cleared_count += 1
                            layer_data.pop(key, None)
                if cleared_count > 0 and self.is_batch_mode:
                    print(f"[批处理] 已清理 worker 快照中的 {cleared_count} 个运行时图层字段")
                return

            target_document = document
            if target_document is None:
                if self.is_batch_mode:
                    return
                target_document = self.document

            if not hasattr(target_document, 'layers'):
                return
                
            cleared_count = 0
            for idx, layer in enumerate(target_document.layers):
                if target_doc_indices and idx not in target_doc_indices:
                    continue
                # 🔧 关键修复：使用公共属性 current_image_path 而不是私有属性 _current_image_path
                # Layer（layer_new.py）使用属性管理器，LegacyLayer直接使用实例属性
                # 通过setter正确处理两种情况
                if hasattr(layer, 'current_image_path'):
                    old_path = layer.current_image_path
                    if old_path is not None:
                        cleared_count += 1
                        try:
                            basename = os_module.path.basename(old_path) if isinstance(old_path, str) else str(old_path)
                            print(f"[批处理] 清理图层 '{layer.name}' 的临时路径: {basename}")
                        except:
                            print(f"[批处理] 清理图层 '{layer.name}' 的临时路径")
                    layer.current_image_path = None  # 使用setter正确清理
                
                # 清理图像缓存
                if hasattr(layer, '_cached_image'):
                    layer._cached_image = None
                if hasattr(layer, '_cached_image_path'):
                    layer._cached_image_path = None
                if hasattr(layer, '_cache_valid'):
                    layer._cache_valid = False
                if hasattr(layer, 'cached_image'):
                    try:
                        # 对于有setter的cached_image属性
                        layer.cached_image = None
                    except:
                        pass
            
            if cleared_count > 0:
                print(f"[批处理] 🧹 已清理 {cleared_count} 个图层的临时图像路径")
            else:
                print(f"[批处理] ℹ️ 所有图层的临时路径已是干净状态")
                
        except Exception as e:
            print(f"[批处理] ⚠️ 清理图层路径时出错: {e}")
            import traceback
            traceback.print_exc()
            print(f"[批处理] ⚠️ 清理图层图像路径时出错: {e}")
    
    def cancel(self):
        """"""
        with self._lock:
            self.is_canceled = True
        print("[] ")
        
        # 
        try:
            import gc
            gc.collect()
        except:
            pass


class OptimizedBatchExportManager:
    """"""

    @staticmethod
    def _record_export_report(document, report: Dict[str, object]):
        """写入最近一次报告并维护历史。"""
        if not isinstance(report, dict):
            return
        try:
            document._last_export_report = report
        except Exception:
            pass
        try:
            history = getattr(document, '_export_report_history', None)
            if not isinstance(history, list):
                history = []
            history.append(report)
            settings = getattr(document, 'export_settings', {}) or {}
            limit = int(settings.get('export_report_history_limit', 80) or 80)
            limit = max(10, min(300, limit))
            if len(history) > limit:
                history = history[-limit:]
            document._export_report_history = history
        except Exception:
            pass
        try:
            import json
            log_dir = os_module.path.join(os_module.path.expanduser('~'), '.config', '批图王', 'logs')
            os_module.makedirs(log_dir, exist_ok=True)
            report_file = os_module.path.join(log_dir, 'export_reports.jsonl')
            with open(report_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
            setattr(document, '_last_export_report_file', report_file)
        except Exception:
            pass

    @staticmethod
    def _summarize_precompute_diagnostics(precompute_diagnostics: Dict[str, object]) -> Dict[str, object]:
        """把预计算诊断转成可直接消费的结论摘要。"""
        diag = precompute_diagnostics or {}
        shortage = diag.get("shortage_analysis", {}) or {}
        reasons = list(shortage.get("primary_reasons", []) or [])
        recommendations = []

        if "combination_space_limited" in reasons:
            recommendations.append("可用组合空间已接近上限，建议减少约束或扩充素材池")
        if "dedup_blocking" in reasons:
            recommendations.append("去重命中较高，建议调整去重策略或放宽阈值")
        if "category_coverage_low" in reasons:
            recommendations.append("绑定分类覆盖不足，建议补齐分类映射与素材")
        if bool(diag.get("relax_dedup_used", False)):
            gain = int(diag.get("relax_gain_count", 0) or 0)
            recommendations.append(f"已启用去重放宽，额外获得 {gain} 个组合")
        dynamic_budget = diag.get("dynamic_budget", {}) or {}
        if bool(dynamic_budget.get("enabled", False)):
            expanded_times = int(dynamic_budget.get("expanded_times", 0) or 0)
            shrunk_times = int(dynamic_budget.get("shrunk_times", 0) or 0)
            if expanded_times > 0 or shrunk_times > 0:
                recommendations.append(
                    f"动态预算已调整（扩容{expanded_times}次/收缩{shrunk_times}次），可根据导出耗时再微调阈值"
                )
        else:
            recommendations.append("可开启动态预算以提升凑满稳定性")
        if not recommendations and int(shortage.get("shortage_count", 0) or 0) > 0:
            recommendations.append("建议提高预计算尝试上限并检查图层池质量")

        return {
            "mode": str(diag.get("mode", "")),
            "dedup_strategy": str(diag.get("dedup_strategy", "")),
            "shortage": shortage,
            "recommendations": recommendations,
        }

    @staticmethod
    def _derive_runtime_tuning_plan(document, precompute_summary: Dict[str, object], planned_count: int, file_format: str) -> Dict[str, object]:
        """根据预计算摘要推导执行阶段策略（迭代3：端到端联动）。"""
        settings = getattr(document, 'export_settings', {}) or {}
        auto_enabled = bool(settings.get('auto_runtime_tuning_enabled', True))
        if not auto_enabled:
            return {"enabled": False}

        shortage = precompute_summary.get("shortage", {}) if isinstance(precompute_summary, dict) else {}
        reasons = list(shortage.get("primary_reasons", []) or [])
        cpu_count = os_module.cpu_count() or 4
        derived_workers = None
        derived_io_profile = None

        if int(planned_count) <= 20:
            derived_workers = max(1, min(2, cpu_count))
        elif "combination_space_limited" in reasons and int(planned_count) < 80:
            derived_workers = max(1, min(3, cpu_count))
        elif int(planned_count) >= 300:
            # 历史策略过于激进会挤占 UI 资源，这里改为温和提速
            derived_workers = max(2, min(6, cpu_count))

        fmt = str(file_format or "").lower()
        if fmt in ("png", "bmp") and int(planned_count) >= 120:
            derived_io_profile = "speed"
        elif "combination_space_limited" in reasons and int(planned_count) < 80:
            derived_io_profile = "size"

        return {
            "enabled": True,
            "derived_workers": int(derived_workers) if derived_workers is not None else None,
            "derived_io_profile": derived_io_profile,
            "manual_worker_override": False,
            "manual_io_override": False,
            "planned_count": int(planned_count),
            "reasons": reasons,
        }

    @staticmethod
    def export_batch_optimized_v2(document, document_analysis: dict, directory: str, count: int,
                                 filename_template: str = "image_{number:04d}",
                                 file_format: str = "png", start_index: int = 1,
                                 progress_callback: Optional[Callable[[int], None]] = None,
                                 file_completed_callback: Optional[Callable[[str], None]] = None,
                                 stage_callback: Optional[Callable[[str], None]] = None,
                                 cancel_callback: Optional[Callable[[], bool]] = None,
                                 traverse_mode: bool = False,
                                 avoid_duplicates: bool = True) -> bool:
        """ V2 - """

        def _clear_active_handles():
            try:
                if hasattr(document, '_active_export_executor'):
                    document._active_export_executor = None
                if hasattr(document, '_active_precomputer'):
                    document._active_precomputer = None
            except Exception:
                pass

        print(f"[V2] : {count} ")
        print(f"[V2] : {document_analysis['export_mode']}")
        print(f"[V2] : {document_analysis['binding_enabled']}")
        print(f"[V2] : {'开启' if avoid_duplicates else '关闭'}")
        adjustment_info = {
            'requested': count,
            'planned': 0,
            'reasons': []
        }

        # 验证输出目录
        try:
            # 测试目录是否存在且可写
            if not os_module.path.exists(directory):
                try:
                    os_module.makedirs(directory, exist_ok=True)
                except (OSError, PermissionError) as e:
                    error_msg = f"无法创建输出目录 '{directory}': {e}"
                    print(f"[V2] ❌ {error_msg}")
                    if hasattr(document, '_last_export_error'):
                        document._last_export_error = error_msg
                    try:
                        report = build_export_report(
                            requested_count=count,
                            planned_count=0,
                            exported_count=0,
                            success=False,
                            canceled=False,
                            error_message=error_msg,
                            export_mode=document_analysis.get('export_mode', 'unknown'),
                            binding_enabled=bool(document_analysis.get('binding_enabled', False)),
                            precompute_time=0.0,
                            render_time=0.0,
                            io_time=0.0,
                            total_time=0.0,
                            throughput=0.0,
                            directory=directory,
                            file_format=file_format,
                            adjustment_info=adjustment_info,
                            extra={"phase": "validate_output_directory"}
                        )
                        OptimizedBatchExportManager._record_export_report(document, report)
                    except Exception:
                        pass
                    return False
            
            # 测试目录是否可写
            test_file = os_module.path.join(directory, '.write_test')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os_module.remove(test_file)
            except (OSError, PermissionError, IOError) as e:
                error_msg = f"输出目录无写入权限 '{directory}': {e}"
                print(f"[V2] ❌ {error_msg}")
                if hasattr(document, '_last_export_error'):
                    document._last_export_error = error_msg
                try:
                    report = build_export_report(
                        requested_count=count,
                        planned_count=0,
                        exported_count=0,
                        success=False,
                        canceled=False,
                        error_message=error_msg,
                        export_mode=document_analysis.get('export_mode', 'unknown'),
                        binding_enabled=bool(document_analysis.get('binding_enabled', False)),
                        precompute_time=0.0,
                        render_time=0.0,
                        io_time=0.0,
                        total_time=0.0,
                        throughput=0.0,
                        directory=directory,
                        file_format=file_format,
                        adjustment_info=adjustment_info,
                        extra={"phase": "validate_output_directory"}
                    )
                    OptimizedBatchExportManager._record_export_report(document, report)
                except Exception:
                    pass
                return False
                
        except Exception as e:
            error_msg = f"目录验证失败 '{directory}': {e}"
            print(f"[V2] ❌ {error_msg}")
            if hasattr(document, '_last_export_error'):
                document._last_export_error = error_msg
            try:
                report = build_export_report(
                    requested_count=count,
                    planned_count=0,
                    exported_count=0,
                    success=False,
                    canceled=False,
                    error_message=error_msg,
                    export_mode=document_analysis.get('export_mode', 'unknown'),
                    binding_enabled=bool(document_analysis.get('binding_enabled', False)),
                    precompute_time=0.0,
                    render_time=0.0,
                    io_time=0.0,
                    total_time=0.0,
                    throughput=0.0,
                    directory=directory,
                    file_format=file_format,
                    adjustment_info=adjustment_info,
                    extra={"phase": "validate_output_directory"}
                )
                OptimizedBatchExportManager._record_export_report(document, report)
            except Exception:
                pass
            return False

        try:
            #  
            from app.utils.batch_export_precomputer import get_batch_precomputer_v2
            precomputer = get_batch_precomputer_v2(document, document_analysis)
            try:
                document._active_precomputer = precomputer
            except Exception:
                pass

            #  
            print("[V2] ...")
            if stage_callback:
                stage_callback("预计算分析")
            precompute_start_time = time.time()
            total_combinations = precomputer.analyze_document_with_context(cancel_callback=cancel_callback)

            #  
            print("[V2] ...")
            if stage_callback:
                stage_callback("预计算建模")
            plan = precomputer.create_export_plan(
                directory=directory,
                count=count,
                filename_template=filename_template,
                file_format=file_format,
                start_index=start_index,
                avoid_duplicates=avoid_duplicates,
                traverse_mode=traverse_mode,
                cancel_callback=cancel_callback
            )
            precompute_time = max(0.0, time.time() - precompute_start_time)
            precompute_diagnostics = dict(getattr(plan, 'precompute_diagnostics', {}) or {})
            precompute_summary = OptimizedBatchExportManager._summarize_precompute_diagnostics(precompute_diagnostics)
            runtime_tuning = OptimizedBatchExportManager._derive_runtime_tuning_plan(
                document=document,
                precompute_summary=precompute_summary,
                planned_count=len(getattr(plan, 'tasks', []) or []),
                file_format=file_format,
            )
            try:
                document._last_precompute_diagnostics = precompute_diagnostics
                document._last_precompute_summary = precompute_summary
                document._last_runtime_tuning = runtime_tuning
            except Exception:
                pass

            # 记录导出调整信息，供 UI 提示
            try:
                if hasattr(plan, 'adjustment_info'):
                    document._last_export_adjustment = plan.adjustment_info
                    adjustment_info = plan.adjustment_info
                else:
                    document._last_export_adjustment = {
                        'requested': count,
                        'planned': len(plan.tasks),
                        'reasons': []
                    }
                    adjustment_info = document._last_export_adjustment
            except Exception:
                pass

            if getattr(precomputer, '_was_canceled', False):
                print("[V2] 用户取消：预计算已中止")
                try:
                    report = build_export_report(
                        requested_count=count,
                        planned_count=len(getattr(plan, 'tasks', []) if 'plan' in locals() else []),
                        exported_count=0,
                        success=False,
                        canceled=True,
                        error_message="导出已取消",
                        export_mode=document_analysis.get('export_mode', 'unknown'),
                        binding_enabled=bool(document_analysis.get('binding_enabled', False)),
                        precompute_time=precompute_time if 'precompute_time' in locals() else 0.0,
                        render_time=0.0,
                        io_time=0.0,
                        total_time=0.0,
                        throughput=0.0,
                        directory=directory,
                        file_format=file_format,
                        adjustment_info=adjustment_info,
                        extra={
                            "phase": "precompute",
                            "total_combinations": int(total_combinations),
                            "precompute_diagnostics": precompute_diagnostics,
                            "precompute_summary": precompute_summary,
                            "runtime_tuning": runtime_tuning,
                        }
                    )
                    OptimizedBatchExportManager._record_export_report(document, report)
                except Exception:
                    pass
                return False

            #  
            print(f"[V2] :")
            print(f"  - : {plan.estimated_time:.1f}")
            print(f"  - : {plan.memory_requirement_mb:.1f}MB")
            print(f"  - : {total_combinations}")
            for suggestion in plan.optimization_suggestions:
                print(f"  - : {suggestion}")

            #  
            print("[V2] ...")
            tuned_workers = runtime_tuning.get("derived_workers")
            executor = OptimizedBatchExecutor(document, max_workers=tuned_workers if tuned_workers is not None else None)
            if runtime_tuning.get("derived_io_profile"):
                try:
                    executor._io_profile = str(runtime_tuning.get("derived_io_profile"))
                except Exception:
                    pass
            try:
                document._active_export_executor = executor
            except Exception:
                pass
            if stage_callback:
                stage_callback("渲染与写盘")
            success = executor.execute_plan(
                plan=plan,
                progress_callback=progress_callback,
                file_completed_callback=file_completed_callback,
                cancel_callback=cancel_callback
            )
            fallback_attempted = False
            fallback_succeeded = False
            try:
                first_completed = int(getattr(executor, 'stats', {}).get('completed_count', 0) or 0)
                can_retry = (
                    (not success)
                    and bool(runtime_tuning.get("enabled", False))
                    and (runtime_tuning.get("derived_workers") is not None or runtime_tuning.get("derived_io_profile"))
                    and first_completed == 0
                    and not bool(cancel_callback and cancel_callback())
                )
                if can_retry:
                    fallback_attempted = True
                    print("[V2] 自动调优执行失败，回退默认执行参数重试一次...")
                    fallback_executor = OptimizedBatchExecutor(document)
                    success = fallback_executor.execute_plan(
                        plan=plan,
                        progress_callback=progress_callback,
                        file_completed_callback=file_completed_callback,
                        cancel_callback=cancel_callback
                    )
                    if success:
                        fallback_succeeded = True
                        executor = fallback_executor
            except Exception:
                pass

            # 记录导出性能统计，供 UI 诊断面板展示
            try:
                if stage_callback:
                    stage_callback("汇总统计")
                stats = getattr(executor, 'stats', {}) if executor else {}
                total_time = float(stats.get('total_time', 0.0) or 0.0)
                render_time = float(stats.get('render_time', 0.0) or 0.0)
                io_time = float(stats.get('io_time', 0.0) or 0.0)
                throughput = float(stats.get('images_per_second', 0.0) or 0.0)
                if throughput <= 0.0 and total_time > 0:
                    throughput = len(plan.tasks) / total_time
                document._last_export_perf_stats = {
                    'precompute_time': float(precompute_time),
                    'render_time': render_time,
                    'io_time': io_time,
                    'total_time': total_time,
                    'throughput': throughput,
                    'exported_count': int(len(plan.tasks)),
                    'success': bool(success),
                    'scheduler_adjustments': int(stats.get('scheduler_adjustments', 0) or 0),
                    'queue_backpressure_events': int(stats.get('queue_backpressure_events', 0) or 0),
                    'io_workers': int(stats.get('io_workers', 0) or 0),
                    'min_in_flight_limit': int(stats.get('min_in_flight_limit', 0) or 0),
                    'max_in_flight_limit': int(stats.get('max_in_flight_limit', 0) or 0),
                    'final_in_flight_limit': int(stats.get('final_in_flight_limit', 0) or 0),
                    'render_queue_submitted': int(stats.get('render_queue_submitted', 0) or 0),
                    'save_queue_submitted': int(stats.get('save_queue_submitted', 0) or 0),
                    'max_render_backlog': int(stats.get('max_render_backlog', 0) or 0),
                    'max_save_backlog': int(stats.get('max_save_backlog', 0) or 0),
                    'max_pipeline_backlog': int(stats.get('max_pipeline_backlog', 0) or 0),
                    'worker_document_seed_available': int(stats.get('worker_document_seed_available', 0) or 0),
                    'worker_document_create_failures': int(stats.get('worker_document_create_failures', 0) or 0),
                    'shared_document_render_count': int(stats.get('shared_document_render_count', 0) or 0),
                    'main_document_mutation_warnings': int(stats.get('main_document_mutation_warnings', 0) or 0),
                    'snapshot_warning': str(getattr(document, '_last_export_snapshot_warning', '') or ''),
                    'preload_unique_images': int(stats.get('preload_unique_images', 0) or 0),
                    'preload_loaded_images': int(stats.get('preload_loaded_images', 0) or 0),
                    'preload_skipped_by_memory': int(stats.get('preload_skipped_by_memory', 0) or 0),
                    'preload_memory_mb': float(stats.get('preload_memory_mb', 0.0) or 0.0),
                    'preload_hits': int(stats.get('preload_hits', 0) or 0),
                    'written_bytes': int(stats.get('written_bytes', 0) or 0),
                    'io_profile': str(getattr(executor, '_io_profile', 'balanced')),
                    'quality_profile': str(executor._resolve_export_quality_profile() if executor else 'quality'),
                    'export_backend': str(getattr(executor, '_export_backend', 'pillow')),
                    'export_service_time': float(stats.get('export_service_time', 0.0) or 0.0),
                    'pillow_save_count': int(stats.get('pillow_save_count', 0) or 0),
                    'vips_save_count': int(stats.get('vips_save_count', 0) or 0),
                    'save_error_count': int(stats.get('save_error_count', 0) or 0),
                    'memory_guard_mode': str(stats.get('memory_guard_mode', getattr(executor, '_export_memory_guard_mode', 'auto'))),
                    'memory_limit_mb': float(stats.get('memory_limit_mb', 0.0) or 0.0),
                    'memory_requested_limit_mb': float(stats.get('memory_requested_limit_mb', 0.0) or 0.0),
                    'memory_current_mb': float(stats.get('memory_current_mb', 0.0) or 0.0),
                    'memory_peak_mb': float(stats.get('memory_peak_mb', 0.0) or 0.0),
                    'memory_soft_throttle_events': int(stats.get('memory_soft_throttle_events', 0) or 0),
                    'memory_hard_throttle_events': int(stats.get('memory_hard_throttle_events', 0) or 0),
                    'memory_wait_seconds': float(stats.get('memory_wait_seconds', 0.0) or 0.0),
                    'memory_cache_clear_events': int(stats.get('memory_cache_clear_events', 0) or 0),
                    'runtime_fallback_attempted': bool(fallback_attempted),
                    'runtime_fallback_succeeded': bool(fallback_succeeded),
                }
                report = build_export_report(
                    requested_count=count,
                    planned_count=len(plan.tasks),
                    exported_count=len(plan.tasks) if success else int(stats.get('completed_count', 0) or 0),
                    success=bool(success),
                    canceled=bool(cancel_callback and cancel_callback()),
                    error_message="" if success else str(getattr(executor, 'last_error_message', '') or getattr(document, '_last_export_error', '') or "导出失败"),
                    export_mode=document_analysis.get('export_mode', 'unknown'),
                    binding_enabled=bool(document_analysis.get('binding_enabled', False)),
                    precompute_time=float(precompute_time),
                    render_time=render_time,
                    io_time=io_time,
                    total_time=total_time,
                    throughput=throughput,
                    directory=directory,
                    file_format=file_format,
                    adjustment_info=adjustment_info,
                    extra={
                        "phase": "execute",
                        "total_combinations": int(total_combinations),
                        "max_workers": int(getattr(executor, 'max_workers', 0)),
                        "scheduler": {
                            "adjustments": int(stats.get('scheduler_adjustments', 0) or 0),
                            "queue_backpressure_events": int(stats.get('queue_backpressure_events', 0) or 0),
                            "io_workers": int(stats.get('io_workers', 0) or 0),
                            "min_in_flight_limit": int(stats.get('min_in_flight_limit', 0) or 0),
                            "max_in_flight_limit": int(stats.get('max_in_flight_limit', 0) or 0),
                            "final_in_flight_limit": int(stats.get('final_in_flight_limit', 0) or 0),
                            "render_queue_submitted": int(stats.get('render_queue_submitted', 0) or 0),
                            "save_queue_submitted": int(stats.get('save_queue_submitted', 0) or 0),
                            "max_render_backlog": int(stats.get('max_render_backlog', 0) or 0),
                            "max_save_backlog": int(stats.get('max_save_backlog', 0) or 0),
                            "max_pipeline_backlog": int(stats.get('max_pipeline_backlog', 0) or 0),
                        },
                        "io": {
                            "profile": str(getattr(executor, '_io_profile', 'balanced')),
                            "quality_profile": str(executor._resolve_export_quality_profile() if executor else 'quality'),
                            "export_backend": str(getattr(executor, '_export_backend', 'pillow')),
                            "written_bytes": int(stats.get('written_bytes', 0) or 0),
                            "max_file_size_kb": int(getattr(executor, '_max_file_size_kb', 0) or 0),
                            "export_service_time": float(stats.get('export_service_time', 0.0) or 0.0),
                            "pillow_save_count": int(stats.get('pillow_save_count', 0) or 0),
                            "vips_save_count": int(stats.get('vips_save_count', 0) or 0),
                            "save_error_count": int(stats.get('save_error_count', 0) or 0),
                        },
                        "runtime_tuning": runtime_tuning,
                        "runtime_fallback": {
                            "attempted": bool(fallback_attempted),
                            "succeeded": bool(fallback_succeeded),
                        },
                        "document_snapshot": {
                            "worker_seed_available": int(stats.get('worker_document_seed_available', 0) or 0),
                            "worker_create_failures": int(stats.get('worker_document_create_failures', 0) or 0),
                            "shared_document_render_count": int(stats.get('shared_document_render_count', 0) or 0),
                            "main_document_mutation_warnings": int(stats.get('main_document_mutation_warnings', 0) or 0),
                            "warning": str(getattr(document, '_last_export_snapshot_warning', '') or ''),
                        },
                        "preload": {
                            "unique_images": int(stats.get('preload_unique_images', 0) or 0),
                            "loaded_images": int(stats.get('preload_loaded_images', 0) or 0),
                            "skipped_by_memory": int(stats.get('preload_skipped_by_memory', 0) or 0),
                            "memory_mb": float(stats.get('preload_memory_mb', 0.0) or 0.0),
                            "hits": int(stats.get('preload_hits', 0) or 0),
                        },
                        "memory": {
                            "mode": str(stats.get('memory_guard_mode', getattr(executor, '_export_memory_guard_mode', 'auto'))),
                            "limit_mb": float(stats.get('memory_limit_mb', 0.0) or 0.0),
                            "requested_limit_mb": float(stats.get('memory_requested_limit_mb', 0.0) or 0.0),
                            "current_mb": float(stats.get('memory_current_mb', 0.0) or 0.0),
                            "peak_mb": float(stats.get('memory_peak_mb', 0.0) or 0.0),
                            "soft_throttle_events": int(stats.get('memory_soft_throttle_events', 0) or 0),
                            "hard_throttle_events": int(stats.get('memory_hard_throttle_events', 0) or 0),
                            "wait_seconds": float(stats.get('memory_wait_seconds', 0.0) or 0.0),
                            "cache_clear_events": int(stats.get('memory_cache_clear_events', 0) or 0),
                        },
                        "precompute_diagnostics": precompute_diagnostics,
                        "precompute_summary": precompute_summary,
                    }
                )
                OptimizedBatchExportManager._record_export_report(document, report)
            except Exception:
                pass

            if success:
                print(f"[V2] ")
                _clear_active_handles()
                return True
            else:
                print(f"[V2] ")
                _clear_active_handles()
                return False

        except Exception as e:
            error_msg = f"批量导出失败: {e}"
            print(f"[V2] ❌ {error_msg}")
            import traceback
            traceback.print_exc()
            
            # 存储错误信息到文档对象
            if hasattr(document, '_last_export_error'):
                document._last_export_error = error_msg
            elif hasattr(document, 'setattr'):
                try:
                    setattr(document, '_last_export_error', error_msg)
                except:
                    pass
            _clear_active_handles()
            try:
                report = build_export_report(
                    requested_count=count,
                    planned_count=0,
                    exported_count=0,
                    success=False,
                    canceled=bool(cancel_callback and cancel_callback()),
                    error_message=error_msg,
                    export_mode=document_analysis.get('export_mode', 'unknown'),
                    binding_enabled=bool(document_analysis.get('binding_enabled', False)),
                    precompute_time=0.0,
                    render_time=0.0,
                    io_time=0.0,
                    total_time=0.0,
                    throughput=0.0,
                    directory=directory,
                    file_format=file_format,
                    adjustment_info=adjustment_info,
                    extra={"phase": "exception"}
                )
                OptimizedBatchExportManager._record_export_report(document, report)
            except Exception:
                pass
            return False


def export_batch_with_precomputation_v2(document, document_analysis: dict, **kwargs) -> bool:
    """ V2 - """
    return OptimizedBatchExportManager.export_batch_optimized_v2(document, document_analysis, **kwargs)
