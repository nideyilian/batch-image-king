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
import logging

logger = logging.getLogger(__name__)


class FastRendererPreview(object):
    """Mixin for fast_renderer_preview (split from FastRenderer)."""

    @_serialized_preview
    def render_preview(self, document, force_refresh: bool = False, interactive_low_quality: bool = False, cancel_token=None) -> Optional[Image.Image]:
        """预览渲染 - 优化版本，使用智能缓存和内存管理"""
        quality_level = 'preview_interactive' if interactive_low_quality else 'preview'
        log_branch(
            "fast_renderer.render_preview",
            "enter",
            force_refresh=force_refresh,
            interactive_low_quality=interactive_low_quality
        )
        # 导出过程中默认复用已有预览，降低UI卡顿与线程争用
        if self._is_export_preview_frozen(document) and not force_refresh:
            cached = self.intelligent_cache.get(document, quality_level=quality_level)
            if cached:
                log_branch("fast_renderer.render_preview", "cache_hit_export_freeze")
                return cached
            if self._last_preview_snapshot is not None:
                log_branch("fast_renderer.render_preview", "snapshot_hit_export_freeze")
                return self._last_preview_snapshot.copy()
        
        # 检查内存状态
        memory_status = self._get_cached_memory_status()
        if memory_status['pressure_level'] in ['high', 'critical']:
            if self._verbose_logging:
                print(f"[快速渲染] 内存压力较高: {memory_status['pressure_level']}，执行优化")
            self.memory_manager.force_optimization()
        
        # 检查文档是否需要强制刷新缓存
        if hasattr(document, '_needs_cache_refresh') and document._needs_cache_refresh:
            force_refresh = True
            if self._verbose_logging:
                print(f"[快速渲染] 文档标记需要缓存刷新，强制重新渲染")

        # 检查智能缓存
        if not force_refresh:
            cached = self.intelligent_cache.get(document, quality_level=quality_level)
            if cached:
                log_branch("fast_renderer.render_preview", "cache_hit")
                if self._verbose_logging:
                    print(f"[快速渲染] 使用智能缓存预览")
                return cached

        if self._verbose_logging:
            print(f"[快速渲染] 重新渲染预览，强制刷新: {force_refresh}")

        # 记录渲染开始时间
        start_time = time.time()

        try:
            # 使用快速设置渲染
            composition = self._fast_render(
                document,
                preview_mode=True,
                low_quality_preview=interactive_low_quality
            )
            log_branch("fast_renderer.render_preview", "fast_render_preview")

            if composition:
                # 注册图像进行内存追踪
                register_image_for_tracking(composition, f"preview_{document.canvas_width}x{document.canvas_height}")
                
                # 计算渲染时间
                render_time = time.time() - start_time
                
                # 存入智能缓存
                self.intelligent_cache.put(document, composition, render_time, quality_level=quality_level)

                # 清除文档的缓存刷新标记
                if hasattr(document, '_needs_cache_refresh'):
                    document._needs_cache_refresh = False

                # 记录渲染时间
                self._last_render_time['preview'] = render_time
                self._last_preview_snapshot = composition.copy()

                if self._verbose_logging:
                    print(f"[快速渲染] 预览渲染完成，耗时: {render_time:.3f}秒")

            return composition

        except Exception as e:
            log_branch("fast_renderer.render_preview", "fallback_document_render", error=str(e))
            if self._verbose_logging:
                print(f"[快速渲染] 预览渲染失败: {e}")
            # 回退到标准渲染
            from app.services.render_service import render_document_legacy_fallback

            return render_document_legacy_fallback(document)

    @_serialized_preview
    def render_preview_incremental(
        self,
        document,
        active_layer_index: int,
        force_refresh: bool = False,
        interactive_low_quality: bool = True,
        cancel_token=None,
    ) -> Optional[Image.Image]:
        """交互期增量预览：复用静态底图，仅重算当前操作图层并合成。"""
        try:
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return None
            if active_layer_index < 0 or active_layer_index >= len(document.layers):
                return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)

            active_layer = document.layers[active_layer_index]
            if active_layer is None or not getattr(active_layer, 'visible', True):
                return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)

            base = self._get_or_build_interaction_base(
                document=document,
                active_layer_index=active_layer_index,
                force_refresh=force_refresh,
                interactive_low_quality=interactive_low_quality
            )
            if base is None:
                return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)

            composition = base.copy()
            if interactive_low_quality:
                layer_image = self._get_layer_surface_interactive_cached(
                    active_layer,
                    document,
                    was_just_loaded=False
                )
            else:
                layer_image = self._get_layer_surface_cached(active_layer, document, was_just_loaded=False)
            if layer_image is None:
                return composition

            render_scale = self._get_interactive_render_scale(document, True, interactive_low_quality)
            opacity = getattr(active_layer, 'opacity', 1.0)
            blend_mode = self._get_layer_blend_mode(active_layer)
            positions_info, mirror_mode = self._get_layer_positions_info_cached(active_layer, document)

            from PIL import ImageOps
            mirrored_h = ImageOps.mirror(layer_image) if mirror_mode == 'horizontal' else None
            mirrored_v = ImageOps.flip(layer_image) if mirror_mode == 'vertical' else None
            for pos_x, pos_y, is_mirror in positions_info:
                if is_mirror and mirror_mode == 'horizontal':
                    img_for_pos = mirrored_h if mirrored_h is not None else layer_image
                elif is_mirror and mirror_mode == 'vertical':
                    img_for_pos = mirrored_v if mirrored_v is not None else layer_image
                else:
                    img_for_pos = layer_image
                draw_x = int(round((int(pos_x) + int(getattr(active_layer, '_render_offset_x', 0))) * render_scale))
                draw_y = int(round((int(pos_y) + int(getattr(active_layer, '_render_offset_y', 0))) * render_scale))
                img_for_pos = self._scale_layer_for_interactive_preview(img_for_pos, render_scale)
                composition = self._fast_composite(
                    composition,
                    img_for_pos,
                    draw_x,
                    draw_y,
                    opacity,
                    preview_mode=True,
                    blend_mode=blend_mode,
                    low_quality_preview=interactive_low_quality
                )
            return composition
        except Exception as e:
            print(f"[快速渲染] 增量预览失败，回退普通预览: {e}")
            return self.render_preview(force_refresh=force_refresh, document=document, interactive_low_quality=interactive_low_quality)
    
    @_serialized_preview
    def render_preview_live(
        self,
        document,
        interactive_low_quality: bool = True,
        cancel_token=None,
    ) -> Optional[Image.Image]:
        """Render the current document state directly for responsive interaction."""
        try:
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return None
            composition = self._fast_render(
                document,
                preview_mode=True,
                was_just_loaded=False,
                low_quality_preview=interactive_low_quality,
                cancel_token=cancel_token,
            )
            if composition is not None:
                self._last_preview_snapshot = composition.copy()
            return composition
        except Exception:
            logger.warning("静默异常已忽略: except Exception: in fast_renderer_preview.py", exc_info=True)
            return None

    def render_batch(self, document) -> Optional[Image.Image]:
        """批量渲染 - 导出优先保证混合模式与结果正确性"""
        start_time = time.time()

        try:
            # 🔧 关键修复：批量导出使用与预览完全相同的渲染方式和参数
            if _BATCH_RENDER_VERBOSE:
                print(f"[批量渲染] 使用与预览一致的快速渲染方案")
                print(f"[批量渲染] 文档信息: 画布={document.canvas_width}x{document.canvas_height}, 图层数={len(document.layers)}")
                from app.utils.layer_tree import is_layer_group, is_effectively_visible
                visible_layers = [
                    layer for layer in document.layers
                    if layer is not None and not is_layer_group(layer) and is_effectively_visible(layer, document.layers)
                ]
                print(f"[批量渲染] 可见图层数: {len(visible_layers)}")
                for i, layer in enumerate(visible_layers):
                    print(f"[批量渲染] 图层{i+1}: {layer.name}, 位置=({layer.x}, {layer.y}), 尺寸={layer.width}x{layer.height}")

            # 导出路径使用非预览模式，避免在回退逻辑中走简化混合分支导致混合模式失效
            composition = self._fast_render(document, preview_mode=False, was_just_loaded=False)

            if composition:
                render_time = time.time() - start_time
                self._last_render_time['batch'] = render_time
                if _BATCH_RENDER_VERBOSE:
                    print(f"[批量渲染] 渲染成功: {composition.size}, 模式={composition.mode}")
                if _BATCH_RENDER_VERBOSE and render_time > 0.1:  # 超过100ms记录
                    print(f"[批量渲染] 批量渲染耗时: {render_time:.3f}秒")
            else:
                if _BATCH_RENDER_VERBOSE:
                    print(f"[批量渲染] _fast_render 返回 None")

            return composition

        except Exception as e:
            print(f"[批量渲染] 批量渲染失败: {e}")
            import traceback
            traceback.print_exc()

            # 回退到最简单的渲染方案
            try:
                if _BATCH_RENDER_VERBOSE:
                    print(f"[批量渲染] 尝试简化渲染方案")
                return self._simple_fallback_render(document)
            except Exception as fallback_e:
                print(f"[批量渲染] 简化渲染也失败: {fallback_e}")
                return None
    
    def _fast_render(
        self,
        document,
        preview_mode: bool = True,
        was_just_loaded: bool = False,
        low_quality_preview: bool = False,
        skip_layer_index: int = -1,
        cancel_token=None,
    ) -> Optional[Image.Image]:
        """快速渲染实现"""
        render_scale = self._get_interactive_render_scale(document, preview_mode, low_quality_preview)
        render_width = max(1, int(round(document.canvas_width * render_scale)))
        render_height = max(1, int(round(document.canvas_height * render_scale)))
        # 创建画布
        composition = Image.new('RGBA', (render_width, render_height), (0, 0, 0, 0))
        export_trace_enabled = bool(getattr(document, '_export_debug_trace_enabled', False))
        export_trace_task = str(getattr(document, '_export_debug_trace_task', '') or '')
        export_trace_layer_paths = getattr(document, '_export_debug_trace_layer_paths', {}) or {}
        export_trace_file = str(getattr(document, '_export_debug_trace_file', '') or '')

        def _emit_export_trace(message: str):
            line = f"[导出调试] {str(message)}"
            try:
                builtins.print(line)
            except Exception:
                logger.warning("静默异常已忽略: except Exception: in fast_renderer_preview.py", exc_info=True)
                pass
            if export_trace_file:
                try:
                    with open(export_trace_file, 'a', encoding='utf-8') as f:
                        f.write(line + "\n")
                except Exception:
                    logger.warning("静默异常已忽略: except Exception: in fast_renderer_preview.py", exc_info=True)
                    pass
        
        # 获取可见图层（会话缓存，避免每张图重复 O(N^2) 的组可见性展开）
        visible_layers = self._get_visible_layers_cached(document, skip_layer_index)
        if not visible_layers:
            return composition

        size_match_overrides = self._build_size_match_overrides(
            document=document,
            visible_layers=visible_layers,
            was_just_loaded=was_just_loaded
        )
        
        # 渲染每个图层
        for layer in visible_layers:
            # 阶段 4：每层渲染前检查 token，过期任务尽早返回
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return composition
            # 获取图层属性
            opacity = getattr(layer, 'opacity', 1.0)
            blend_mode = self._get_layer_blend_mode(layer)

            layer_override = size_match_overrides.get(id(layer))
            if layer_override and (not bool(layer_override.get('visible', True))):
                # 一对多自动识别孔位数：多余填充层自动隐藏，不参与本次渲染
                if export_trace_enabled:
                    layer_path = str(export_trace_layer_paths.get(id(layer), '') or '')
                    if not layer_path:
                        layer_path = str(getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '') or getattr(layer, 'image_source', '') or '')
                    _emit_export_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"路径={layer_path} 命中override=True 可见=False"
                    )
                continue
            if layer_override and (not all(k in layer_override for k in ('x', 'y', 'width', 'height'))):
                # 仅包含可见性控制等部分信息时，回退默认渲染路径
                layer_override = None
            if export_trace_enabled:
                layer_path = str(export_trace_layer_paths.get(id(layer), '') or '')
                if not layer_path:
                    layer_path = str(getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '') or getattr(layer, 'image_source', '') or '')
                _emit_export_trace(
                    f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                    f"路径={layer_path} 命中override={bool(layer_override)}"
                )
            if layer_override:
                target_x = int(layer_override['x'])
                target_y = int(layer_override['y'])
                target_w = max(1, int(layer_override['width']))
                target_h = max(1, int(layer_override['height']))
                if export_trace_enabled:
                    _emit_export_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"匹配矩形=({target_x},{target_y},{target_w},{target_h}) "
                        f"匹配旋转={layer_override.get('rotation')}"
                    )
                # 关键修复：匹配模式下按目标尺寸直接重取源图，避免“已处理图再二次缩放”导致发糊
                layer_image = self._get_layer_surface_for_size(
                    layer=layer,
                    document=document,
                    target_w=target_w,
                    target_h=target_h,
                    was_just_loaded=was_just_loaded,
                    rotation_override=layer_override.get('rotation')
                )
                if layer_image is None:
                    continue
                positions_info = [(target_x, target_y, False)]
                mirror_mode = 'none'
            else:
                layer_image = self._get_layer_surface_cached(layer, document, was_just_loaded)
                if layer_image is None:
                    continue
                positions_info, mirror_mode = self._get_layer_positions_info_cached(layer, document)
            from PIL import ImageOps
            mirrored_h = ImageOps.mirror(layer_image) if mirror_mode == 'horizontal' else None
            mirrored_v = ImageOps.flip(layer_image) if mirror_mode == 'vertical' else None
            for pos_x, pos_y, is_mirror in positions_info:
                if is_mirror and mirror_mode == 'horizontal':
                    img_for_pos = mirrored_h if mirrored_h is not None else layer_image
                elif is_mirror and mirror_mode == 'vertical':
                    img_for_pos = mirrored_v if mirrored_v is not None else layer_image
                else:
                    img_for_pos = layer_image
                draw_x = int(round((int(pos_x) + int(getattr(layer, '_render_offset_x', 0))) * render_scale))
                draw_y = int(round((int(pos_y) + int(getattr(layer, '_render_offset_y', 0))) * render_scale))
                img_for_pos = self._scale_layer_for_interactive_preview(img_for_pos, render_scale)
                composition = self._fast_composite(
                    composition,
                    img_for_pos,
                    draw_x,
                    draw_y,
                    opacity,
                    preview_mode,
                    blend_mode,
                    low_quality_preview=low_quality_preview
                )
        
        return composition

    def _get_interactive_render_scale(self, document, preview_mode: bool, low_quality_preview: bool) -> float:
        """Return a temporary downsample ratio for interactive preview only."""
        if not (preview_mode and low_quality_preview):
            return 1.0
        max_edge = max(int(getattr(document, "canvas_width", 1) or 1), int(getattr(document, "canvas_height", 1) or 1))
        if max_edge <= _INTERACTIVE_PREVIEW_MAX_EDGE:
            return 1.0
        return max(0.20, min(1.0, _INTERACTIVE_PREVIEW_MAX_EDGE / float(max_edge)))

    def _scale_layer_for_interactive_preview(self, image: Image.Image, render_scale: float) -> Image.Image:
        """Downsample a layer surface for low-cost interaction frames."""
        if image is None or render_scale >= 0.999:
            return image
        try:
            target_size = (
                max(1, int(round(image.width * render_scale))),
                max(1, int(round(image.height * render_scale))),
            )
            if target_size == image.size:
                return image
            if image.mode == 'RGBA':
                from app.utils.rgba_resampler import resize_rgba_premultiplied
                return resize_rgba_premultiplied(image, target_size, Image.Resampling.BILINEAR)
            return image.resize(target_size, Image.Resampling.BILINEAR)
        except Exception:
            return image
