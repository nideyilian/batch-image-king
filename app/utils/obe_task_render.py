# -*- coding: utf-8 -*-
"""Optimized batch executor components."""

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
import logging
from app.utils.print_utils import safe_print as print

from app.utils.text_layer_virtual_path import (
    is_text_layer_virtual_path,
    parse_text_layer_virtual_path,
    build_text_layer_virtual_path,
)

logger = logging.getLogger(__name__)


@dataclass
class SaveTaskResult:
    """保存单张任务结果的轻量数据类（原位于 optimized_batch_executor 模块顶层）。"""
    success: bool
    render_time: float = 0.0
    io_time: float = 0.0
    file_path: str = ""
    backend_used: str = "pillow"
    written_bytes: int = 0
    error: str = ""


class OptimizedBatchExecutorTaskRender(object):
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
            in_flight_limit = max(1, safety_in_flight_cap)
            min_in_flight_limit = min(min_in_flight_limit, in_flight_limit)
            max_in_flight_limit = max(min_in_flight_limit, min(max_in_flight_limit, max(1, in_flight_limit)))
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
                logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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
                                self._record_completed_task(completed_count, task)
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
                        current_progress = self.current_progress
                    self._notify_progress(current_progress)
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
                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                    pass
                try:
                    io_executor.shutdown(wait=False)
                except Exception:
                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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
                logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                pass
            try:
                del canvas
            except Exception:
                logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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
                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                    pass
                return False
            if self._is_cancel_requested(cancel_event, cancel_callback):
                try:
                    del canvas
                except Exception:
                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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
                logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                pass
            try:
                if 'canvas' in locals():
                    del canvas
            except Exception:
                logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                pass

    def _render_with_combination(
        self,
        combination,
        task: Optional[ExportTask] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Optional[Image.Image]:
        """ - """
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
                                logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                                pass
                        for attr in ('cached_image', '_cached_image', '_cached_image_path', '_current_image_cache'):
                            if hasattr(layer, attr):
                                try:
                                    setattr(layer, attr, None)
                                except Exception:
                                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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
                        # 关键：只有在绑定功能启用且确实存在绑定组时才做绑定分析。
                        # 绑定组有无是文档数据（binding_manager.binding_groups）里现成可知的，
                        # 没有绑定组就不应进入 _get_binding_common_categories 反复"分析"。
                        bm = getattr(target_document, 'binding_manager', None)
                        if bm and getattr(bm, 'global_enabled', False) and getattr(bm, 'binding_groups', None):
                            categories = []
                            try:
                                categories = target_document._get_binding_common_categories_cached() or []
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
                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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
                        logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                        pass
                if self._preload_enabled:
                    setattr(target_document, '_batch_preloaded_images', self._image_preload_cache)
                else:
                    try:
                        if hasattr(target_document, '_batch_preloaded_images'):
                            delattr(target_document, '_batch_preloaded_images')
                    except Exception:
                        logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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
                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                    pass
                try:
                    if hasattr(target_document, '_batch_preloaded_images'):
                        delattr(target_document, '_batch_preloaded_images')
                except Exception:
                    logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
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

    def _cleanup_resources(self):
        """"""
        try:
            self._release_registered_worker_renderers()
        
            # 
            gc.collect()
        
            print("[] ")
            try:
                from app.utils.intelligent_render_cache import clear_global_cache as _irc_clear
                _irc_clear()
            except Exception:
                logger.warning("静默异常已忽略: except Exception: in obe_task_render.py", exc_info=True)
                pass
        
            # 批导任务使用 worker 文档，结束时不再清理主 UI 文档，避免污染预览状态。
        
        except Exception as e:
            print(f"[] : {e}")

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
                        except Exception:
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
                    except Exception:
                        logger.warning("静默异常已忽略: except: in obe_task_render.py", exc_info=True)
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
