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

class OptimizedBatchExecutorIoExport(object):
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
        if self.is_batch_mode:
            try:
                task_mem_mb = float(self._estimate_single_task_memory_mb())
                if task_mem_mb >= 512:
                    max_preload = min(max_preload, 16)
                    max_bytes = min(max_bytes, 64 * 1024 * 1024)
                elif task_mem_mb >= 256:
                    max_preload = min(max_preload, 32)
                    max_bytes = min(max_bytes, 96 * 1024 * 1024)
                elif task_mem_mb >= 128:
                    max_preload = min(max_preload, 64)
                    max_bytes = min(max_bytes, 160 * 1024 * 1024)
            except Exception:
                pass
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
