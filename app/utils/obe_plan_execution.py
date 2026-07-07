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

class OptimizedBatchExecutorPlanExecution(object):
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

    def _record_completed_task(self, completed_count: int, task) -> None:
        with self._lock:
            self.stats['completed_count'] = max(
                int(self.stats.get('completed_count', 0) or 0),
                int(completed_count),
            )
        if not self.file_completed_callback:
            return
        try:
            self.file_completed_callback(f": {task.filename}")
        except Exception as exc:
            with self._lock:
                self.stats['callback_error_count'] = (
                    int(self.stats.get('callback_error_count', 0) or 0) + 1
                )
            print(f"[批处理] 进度通知失败，导出继续: {exc}")

    def _notify_progress(self, current_progress: int) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(current_progress)
        except Exception as exc:
            with self._lock:
                self.stats['callback_error_count'] = (
                    int(self.stats.get('callback_error_count', 0) or 0) + 1
                )
            print(f"[批处理] 进度通知失败，导出继续: {exc}")

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

    def _emit_export_trace(self, message: str):
        """导出调试输出：同时写控制台和调试文件（UTF-8）。"""
        if not self._export_trace_enabled:
            return
        line = f"[导出调试] {str(message)}"
        try:
            print(line)
        except Exception:
            pass
