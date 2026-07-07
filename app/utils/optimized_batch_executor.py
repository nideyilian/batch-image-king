# -*- coding: utf-8 -*-
"""Optimized batch executor components."""

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

from app.utils.obe_memory_guard import OptimizedBatchExecutorMemoryGuard
from app.utils.obe_runtime_snapshot import OptimizedBatchExecutorRuntimeSnapshot
from app.utils.obe_plan_execution import OptimizedBatchExecutorPlanExecution
from app.utils.obe_task_render import OptimizedBatchExecutorTaskRender
from app.utils.obe_io_export import OptimizedBatchExecutorIoExport
from app.utils.obe_task_render import SaveTaskResult  # 兼容 re-export

def _should_retry_with_default_runtime(
    *,
    success: bool,
    runtime_tuning: dict,
    completed_count: int,
    canceled: bool,
) -> bool:
    return (
        not success
        and bool(runtime_tuning.get("enabled", False))
        and (
            runtime_tuning.get("derived_workers") is not None
            or runtime_tuning.get("derived_io_profile")
        )
        and int(completed_count or 0) == 0
        and not canceled
    )

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
                can_retry = _should_retry_with_default_runtime(
                    success=bool(success),
                    runtime_tuning=runtime_tuning,
                    completed_count=first_completed,
                    canceled=bool(cancel_callback and cancel_callback()),
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
                    'worker_renderer_count': int(stats.get('worker_renderer_count', 0) or 0),
                    'worker_renderer_cache_clear_events': int(stats.get('worker_renderer_cache_clear_events', 0) or 0),
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
                            "worker_renderer_count": int(stats.get('worker_renderer_count', 0) or 0),
                            "worker_renderer_cache_clear_events": int(stats.get('worker_renderer_cache_clear_events', 0) or 0),
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

class OptimizedBatchExecutor(OptimizedBatchExecutorMemoryGuard, OptimizedBatchExecutorRuntimeSnapshot, OptimizedBatchExecutorPlanExecution, OptimizedBatchExecutorTaskRender, OptimizedBatchExecutorIoExport):
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
            'callback_error_count': 0,
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
            'worker_renderer_count': 0,
            'worker_renderer_cache_clear_events': 0,
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
        self._worker_renderers_lock = threading.Lock()
        self._worker_renderers = []
        self._worker_renderer_ids = set()
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
