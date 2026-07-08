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


class FastRendererComposite(object):
    """Mixin for fast_renderer_composite (split from FastRenderer)."""

    def _simple_fallback_render(self, document) -> Optional[Image.Image]:
        """最简单的后备渲染方案"""
        try:
            print(f"[简化渲染] 使用最基础的渲染方案")

            # 创建画布
            composition = Image.new('RGBA', (document.canvas_width, document.canvas_height), (0, 0, 0, 0))

            # 获取可见图层
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            visible_layers = [
                layer for layer in document.layers
                if not is_layer_group(layer) and is_effectively_visible(layer, document.layers)
            ]
            if not visible_layers:
                return composition

            # 使用最简单的方式渲染每个图层
            for layer in visible_layers:
                try:
                    # 获取图层图像
                    layer_image = self._get_layer_image(layer, document, False)
                    if layer_image is None:
                        continue

                    # 获取不透明度
                    opacity = getattr(layer, 'opacity', 1.0)

                    # 应用不透明度
                    if opacity < 1.0:
                        alpha = layer_image.split()[-1]
                        alpha = alpha.point(lambda p: int(p * opacity))
                        layer_image = layer_image.copy()
                        layer_image.putalpha(alpha)

                    # 处理分身功能
                    clone_positions = []
                    is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled

                    if is_clone_enabled and hasattr(layer, 'get_effective_clone_positions'):
                        # 获取所有分身位置（包含随机偏移）
                        try:
                            clone_positions = layer.get_effective_clone_positions()
                            print(f"[简化渲染] 图层 '{layer.name}' 启用分身，共 {len(clone_positions)} 个位置")
                        except Exception as e:
                            print(f"[简化渲染] 获取分身位置失败: {e}")
                            # 回退到单一位置
                            if hasattr(layer, 'get_effective_position'):
                                clone_positions = [layer.get_effective_position()]
                            else:
                                clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]
                    else:
                        # 没有启用分身，使用单一位置（包含随机偏移）
                        if hasattr(layer, 'get_effective_position'):
                            clone_positions = [layer.get_effective_position()]
                        else:
                            clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]

                    positions_info = [(x, y, False) for (x, y) in clone_positions]
                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    if mirror_mode and mirror_mode != 'none':
                        base = clone_positions[:]
                        min_x = min([x for x, _ in base])
                        max_x = max([x + layer.width for x, _ in base])
                        min_y = min([y for _, y in base])
                        max_y = max([y + layer.height for _, y in base])
                        group_width = max_x - min_x
                        group_height = max_y - min_y
                        if mirror_mode == 'horizontal':
                            mirrored_left = document.canvas_width - (min_x + group_width)
                            for x, y in base:
                                offset_x = x - min_x
                                positions_info.append((mirrored_left + offset_x, y, True))
                        elif mirror_mode == 'vertical':
                            mirrored_top = document.canvas_height - (min_y + group_height)
                            for x, y in base:
                                offset_y = y - min_y
                                positions_info.append((x, mirrored_top + offset_y, True))

                    from PIL import ImageOps
                    for pos_x, pos_y, is_mirror in positions_info:
                        img_for_pos = ImageOps.mirror(layer_image) if (is_mirror and mirror_mode == 'horizontal') else (ImageOps.flip(layer_image) if (is_mirror and mirror_mode == 'vertical') else layer_image)
                        draw_x = int(pos_x) + int(getattr(layer, '_render_offset_x', 0))
                        draw_y = int(pos_y) + int(getattr(layer, '_render_offset_y', 0))
                        composition.paste(img_for_pos, (draw_x, draw_y), img_for_pos)

                except Exception as layer_e:
                    print(f"[简化渲染] 图层渲染失败: {layer_e}")
                    continue

            return composition

        except Exception as e:
            print(f"[简化渲染] 简化渲染失败: {e}")
            return None

    def _get_layer_blend_mode(self, layer):
        """获取图层的混合模式字符串"""
        try:
            blend_mode = getattr(layer, 'blend_mode', 0)

            # 枚举值兼容（如 BlendMode.NORMAL / enum.IntEnum）
            if hasattr(blend_mode, 'value'):
                blend_mode = blend_mode.value

            # 如果是数字，转换为字符串
            if isinstance(blend_mode, int):
                blend_mode_map = {
                    0: 'normal',
                    1: 'multiply',
                    2: 'screen',
                    3: 'overlay',
                    4: 'soft_light',
                    5: 'hard_light',
                    6: 'color_dodge',
                    7: 'color_burn',
                    8: 'darken',
                    9: 'lighten',
                    10: 'difference',
                    11: 'exclusion',
                    12: 'hue',
                    13: 'saturation',
                    14: 'color',
                    15: 'luminosity'
                }
                return blend_mode_map.get(blend_mode, 'normal')

            # 如果是字符串，直接返回
            if isinstance(blend_mode, str):
                normalized = blend_mode.strip().lower()
                # 兼容 "BlendMode.NORMAL" 这类字符串
                if normalized.startswith('blendmode.'):
                    normalized = normalized.split('.', 1)[1]
                return normalized

            # 如果是枚举或其他类型，转换为字符串
            normalized = str(blend_mode).strip().lower()
            if normalized.startswith('blendmode.'):
                normalized = normalized.split('.', 1)[1]
            return normalized

        except Exception as e:
            print(f"[快速渲染] 获取混合模式失败: {e}")
            return 'normal'

    def _get_layer_image(self, layer, document, was_just_loaded: bool = False) -> Optional[Image.Image]:
        """获取图层图像 - 修复版本，支持文件限制"""
        try:
            print(f"[快速渲染] 开始获取图层图像: {layer.name}")
            export_trace_enabled = bool(getattr(document, '_export_debug_trace_enabled', False))
            export_trace_task = str(getattr(document, '_export_debug_trace_task', '') or '')
            export_trace_file = str(getattr(document, '_export_debug_trace_file', '') or '')

            def _emit_layer_source_trace(message: str):
                if not export_trace_enabled:
                    return
                line = f"[导出调试] {str(message)}"
                try:
                    builtins.print(line)
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in fast_renderer_composite.py")
                    pass
                if export_trace_file:
                    try:
                        with open(export_trace_file, 'a', encoding='utf-8') as f:
                            f.write(line + "\n")
                    except Exception:
                        logger.debug("静默异常已忽略: except Exception: in fast_renderer_composite.py")
                        pass

            # 处理文字图层
            from app.models.text_layer import TextLayer
            if isinstance(layer, TextLayer):
                print(f"[快速渲染] ✓ 文字图层渲染: {layer.name}")
                return layer.render_text()

            # 🔧 关键修复：完全禁用预处理缓存，避免重复图片问题
            # 注释掉所有缓存检查，确保每次都重新加载图像
            # if hasattr(layer, 'cached_image') and layer.cached_image is not None:
            #     if hasattr(layer, 'is_cache_valid') and layer.is_cache_valid():
            #         print(f"[快速渲染] 🚀 使用预处理缓存: {layer.name} -> {layer.cached_image.size}")
            #         return layer.cached_image
            #     else:
            #         print(f"[快速渲染] ⚠️  预处理缓存无效: {layer.name}")

            # 🔧 关键修复：禁用有效缓存图像检查
            # if hasattr(layer, 'get_valid_cached_image'):
            #     cached_image = layer.get_valid_cached_image()
            #     if cached_image is not None:
            #         print(f"[快速渲染] ✓ 使用有效缓存: {layer.name} -> {cached_image.size}")
            #         return cached_image

            print(f"[快速渲染] 🔧 强制重新加载图像: {layer.name} (禁用旧缓存)")
            is_batch_session = bool(getattr(document, '_is_batch_export_running', False))

            # 🔧 关键修复：始终优先使用当前图像路径，确保预览与文档状态一致
            # 同时兼容 LegacyLayer(_current_image_path) 与 LayerNew(current_image_path)
            current_image_path = None
            if hasattr(layer, '_current_image_path') and getattr(layer, '_current_image_path', None):
                current_image_path = layer._current_image_path
            elif hasattr(layer, 'current_image_path'):
                try:
                    current_image_path = layer.current_image_path
                except Exception:
                    current_image_path = None

            if current_image_path:
                # 只有当路径是文件时才尝试加载（避免 text_layer:// 虚拟路径被误加载）
                if os.path.isfile(current_image_path):
                    try:
                        processed_cache_key = None
                        if is_batch_session:
                            processed_cache_key = self._get_batch_processed_cache_key(document, layer, current_image_path)
                            with self._batch_processed_image_lock:
                                cached_processed = self._batch_processed_image_cache.get(processed_cache_key)
                                if cached_processed is not None:
                                    self._batch_processed_image_cache.move_to_end(processed_cache_key)
                                    _emit_layer_source_trace(
                                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                        f"实际图源={current_image_path} 图源模式=current_image_path 命中批处理processed缓存=True"
                                    )
                                    return cached_processed.copy()

                        # 批导优先使用预读原图 + 会话原图缓存，减少重复读盘
                        if is_batch_session and hasattr(layer, '_process_image') and callable(getattr(layer, '_process_image', None)):
                            source_image = self._get_batch_preloaded_raw_image(document, current_image_path)
                            raw_cache_key = f"{id(document)}:{current_image_path}"
                            if source_image is None:
                                with self._batch_raw_image_lock:
                                    cached_raw = self._batch_raw_image_cache.get(raw_cache_key)
                                    if cached_raw is not None:
                                        self._batch_raw_image_cache.move_to_end(raw_cache_key)
                                        source_image = cached_raw.copy()

                            if source_image is None:
                                from app.models.layer_image_loader import LayerImageLoader
                                source_image = LayerImageLoader.load_image_from_path(current_image_path)
                                if source_image is not None:
                                    with self._batch_raw_image_lock:
                                        self._set_cache_value_unlocked(
                                            self._batch_raw_image_cache,
                                            self._batch_raw_image_entry_bytes,
                                            "_batch_raw_image_bytes",
                                            raw_cache_key,
                                            source_image.copy(),
                                            self._max_batch_raw_entries,
                                            self._max_batch_raw_bytes,
                                        )

                            if source_image is not None:
                                processed = layer._process_image(source_image.copy())
                                if processed is not None:
                                    if processed_cache_key is not None:
                                        with self._batch_processed_image_lock:
                                            self._set_cache_value_unlocked(
                                                self._batch_processed_image_cache,
                                                self._batch_processed_image_entry_bytes,
                                                "_batch_processed_image_bytes",
                                                processed_cache_key,
                                                processed.copy(),
                                                self._max_batch_processed_entries,
                                                self._max_batch_processed_bytes,
                                            )
                                    _emit_layer_source_trace(
                                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                        f"实际图源={current_image_path} 图源模式=current_image_path "
                                        f"加载方式=batch_process_image"
                                    )
                                    return processed

                        # 使用图层自己的加载方法，确保应用了所有变换
                        if hasattr(layer, '_load_and_process_image'):
                            image = layer._load_and_process_image(current_image_path)
                            if image:
                                if processed_cache_key is not None:
                                    with self._batch_processed_image_lock:
                                        self._set_cache_value_unlocked(
                                            self._batch_processed_image_cache,
                                            self._batch_processed_image_entry_bytes,
                                            "_batch_processed_image_bytes",
                                            processed_cache_key,
                                            image.copy(),
                                            self._max_batch_processed_entries,
                                            self._max_batch_processed_bytes,
                                        )
                                _emit_layer_source_trace(
                                    f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                    f"实际图源={current_image_path} 图源模式=current_image_path "
                                    f"加载方式=layer_load_and_process"
                                )
                                return image
                        
                        # 如果图层没有这个方法（旧代码），我们回退到标准加载
                        from app.models.layer_image_loader import LayerImageLoader
                        image = LayerImageLoader.load_image_from_path(current_image_path)
                        if image is not None and processed_cache_key is not None:
                            with self._batch_processed_image_lock:
                                self._set_cache_value_unlocked(
                                    self._batch_processed_image_cache,
                                    self._batch_processed_image_entry_bytes,
                                    "_batch_processed_image_bytes",
                                    processed_cache_key,
                                    image.copy(),
                                    self._max_batch_processed_entries,
                                    self._max_batch_processed_bytes,
                                )
                        if image is not None:
                            _emit_layer_source_trace(
                                f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                                f"实际图源={current_image_path} 图源模式=current_image_path 加载方式=direct_image_loader"
                            )
                        return image
                    except Exception as e:
                        print(f"[快速渲染] ✗ 加载当前图像失败: {layer.name} - {e}")
                        _emit_layer_source_trace(
                            f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                            f"实际图源={current_image_path} 图源模式=current_image_path "
                            f"加载失败={str(e)}"
                        )
            
            # 🔧 新增：检查是否为文档刚加载状态，避免立即处理所有图层
            if was_just_loaded:
                print(f"[快速渲染] 📄 文档刚加载且无有效图片，返回占位符: {layer.name}")
                return self._create_placeholder_image(layer)

            # 如果没有有效缓存，获取新图像
            if hasattr(layer, 'get_random_image'):
                print(f"[快速渲染] → 重新获取图像: {layer.name}")

                # 🔧 关键修复：检查是否有绑定管理器和文件限制
                restricted_files = None
                if document and hasattr(document, 'binding_manager') and document.binding_manager:
                    if document.binding_manager.global_enabled:
                        restricted_files = document.binding_manager.get_layer_file_restrictions(layer)
                        if restricted_files:
                            print(f"[快速渲染] 使用文件限制: {layer.name} -> {len(restricted_files)} 个文件")
                            print(f"[快速渲染] 限制文件示例: {[os.path.basename(f) for f in restricted_files[:3]]}")
                        else:
                            print(f"[快速渲染] 无文件限制: {layer.name}")

                # 调用get_random_image时传递文件限制
                if restricted_files:
                    image = layer.get_random_image(restrict_to_bound_files=restricted_files)
                else:
                    image = layer.get_random_image()

                if image:
                    print(f"[快速渲染] ✓ 图像获取成功: {layer.name} -> {image.size}")
                    # 验证获取的图像路径
                    resolved_path = str(
                        getattr(layer, '_current_image_path', '') or
                        getattr(layer, 'current_image_path', '') or
                        ''
                    )
                    if resolved_path:
                        print(f"[快速渲染] 当前图像路径: {os.path.basename(resolved_path)}")
                    _emit_layer_source_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"实际图源={resolved_path or 'None'} 图源模式=fallback_random"
                    )
                else:
                    print(f"[快速渲染] ✗ 图像获取失败: {layer.name}")
                    _emit_layer_source_trace(
                        f"任务={export_trace_task} 图层={getattr(layer, 'name', '')} "
                        f"实际图源=None 图源模式=fallback_random_failed"
                    )
                return image

            print(f"[快速渲染] ✗ 无法获取图像: {layer.name} (无可用方法)")
            return None

        except Exception as e:
            print(f"[快速渲染] ✗ 获取图层图像失败: {layer.name} -> {e}")
            return None

    def _create_placeholder_image(self, layer):
        """为刚加载的文档创建占位图像"""
        try:
            # 创建一个简单的占位图像
            width = max(layer.width, 100)
            height = max(layer.height, 100)

            # 创建半透明的占位图像
            placeholder = Image.new('RGBA', (width, height), (200, 200, 200, 100))

            # 添加图层名称文字（如果PIL支持）
            try:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(placeholder)

                # 尝试使用默认字体
                try:
                    font = ImageFont.load_default()
                except:
                    font = None

                # 绘制图层名称
                text = f"加载中...\n{layer.name}"
                if font:
                    draw.text((10, 10), text, fill=(100, 100, 100, 200), font=font)
                else:
                    draw.text((10, 10), text, fill=(100, 100, 100, 200))

            except Exception as e:
                print(f"[快速渲染] 占位图像文字绘制失败: {e}")

            print(f"[快速渲染] ✓ 创建占位图像: {layer.name} -> {placeholder.size}")
            return placeholder

        except Exception as e:
            print(f"[快速渲染] 创建占位图像失败: {layer.name} - {e}")
            # 返回最简单的占位图像
            return Image.new('RGBA', (100, 100), (200, 200, 200, 100))
    
    def _fast_composite(
        self,
        background: Image.Image,
        foreground: Image.Image,
        pos_x: int,
        pos_y: int,
        opacity: float,
        preview_mode: bool,
        blend_mode: str = 'normal',
        low_quality_preview: bool = False
    ) -> Image.Image:
        """快速合成 - 使用Photoshop风格的sRGB混合以保证渲染质量"""
        if preview_mode and low_quality_preview:
            return self._standard_composite_logic(
                background,
                foreground,
                pos_x,
                pos_y,
                opacity,
                blend_mode,
                is_preview=True,
                low_quality_preview=True
            )

        try:
            # 尝试使用 UnifiedAlphaCompositor 以获得最佳渲染效果
            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
            
            # 无论是预览模式还是批量模式，都使用 sRGB 混合以保证 Photoshop 风格的渲染效果
            # 解决了之前的线性空间转换导致的色差和像素丢失问题
            
            # 🔧 关键修复：禁用边缘增强和亚像素精度，避免颜色偏差
            # edge_enhancement 会调用超级抗锯齿，可能改变图像颜色
            # 为了确保预览和导出颜色一致，统一禁用这些增强功能
            edge_enhancement = False  # 原：not preview_mode
            subpixel_precision = False  # 原：not preview_mode
            
            return UnifiedAlphaCompositor.composite_layer(
                background=background,
                foreground=foreground,
                position=(pos_x, pos_y),
                opacity=opacity,
                blend_mode=blend_mode,
                edge_enhancement=edge_enhancement,
                subpixel_precision=subpixel_precision,
                use_srgb_blending=True  # 启用 Photoshop 风格混合
            )
            
        except Exception as e:
            print(f"[快速渲染] 统一合成失败: {e}，回退到标准逻辑")
            return self._standard_composite_logic(
                background,
                foreground,
                pos_x,
                pos_y,
                opacity,
                blend_mode,
                is_preview=preview_mode,
                low_quality_preview=low_quality_preview
            )

    def _standard_composite_logic(
        self,
        background,
        foreground,
        pos_x,
        pos_y,
        opacity,
        blend_mode,
        is_preview,
        low_quality_preview: bool = False
    ):
        """标准的合成逻辑（原回退逻辑提取）"""
        try:
            # 确保图像格式
            if background.mode != 'RGBA':
                background = background.convert('RGBA')
            if foreground.mode != 'RGBA':
                foreground = foreground.convert('RGBA')
            
            # 应用不透明度
            if opacity < 1.0:
                # 快速不透明度调整
                fg_array = np.array(foreground, dtype=np.float32)
                fg_array[:,:,3] *= opacity
                foreground = Image.fromarray(fg_array.astype(np.uint8), 'RGBA')
            
            # 计算有效区域
            bg_width, bg_height = background.size
            fg_width, fg_height = foreground.size
            
            # 边界检查
            if pos_x >= bg_width or pos_y >= bg_height or pos_x + fg_width <= 0 or pos_y + fg_height <= 0:
                return background
            
            # 计算裁剪区域
            src_x = max(0, -pos_x)
            src_y = max(0, -pos_y)
            src_w = min(fg_width - src_x, bg_width - max(0, pos_x))
            src_h = min(fg_height - src_y, bg_height - max(0, pos_y))
            
            if src_w <= 0 or src_h <= 0:
                return background
            
            # 裁剪前景
            fg_crop = foreground.crop((src_x, src_y, src_x + src_w, src_y + src_h))
            
            # 计算目标位置
            dst_x = max(0, pos_x)
            dst_y = max(0, pos_y)
            
            # 执行合成
            if is_preview:
                # 预览模式：使用快速混合
                if blend_mode == 'normal':
                    # 交互低质模式：强制走最快路径，优先保障拖拽跟手
                    if low_quality_preview:
                        result = background.copy()
                        result.paste(fg_crop, (dst_x, dst_y), fg_crop)
                        return result
                    # 对含半透明边缘的图层，使用高质量alpha合成，避免圆角/描边边缘台阶感
                    if self._has_partial_alpha(fg_crop):
                        return self._high_quality_alpha_composite(background, fg_crop, dst_x, dst_y)
                    # 完全不透明/全透明图像继续走快速分支
                    result = background.copy()
                    result.paste(fg_crop, (dst_x, dst_y), fg_crop)
                    return result
                else:
                    # 其他混合模式使用简化混合
                    return self._apply_blend_mode(background, fg_crop, dst_x, dst_y, blend_mode)
            else:
                # 批量模式（回退情况）：使用高质量合成
                return self._high_quality_composite(background, fg_crop, dst_x, dst_y, blend_mode)
            
        except Exception as e2:
            print(f"[快速渲染] 标准逻辑失败: {e2}")
            return background
    
    def _has_partial_alpha(self, image: Image.Image) -> bool:
        """判断图像是否包含(0,255)之间的半透明像素。"""
        try:
            if image.mode != 'RGBA':
                return False
            alpha = image.getchannel('A')
            lo, hi = alpha.getextrema()
            if lo >= 255 or hi <= 0:
                return False
            # 粗采样检查，避免每帧全量扫描开销
            arr = np.array(alpha, dtype=np.uint8)
            if arr.size > 65536:
                arr = arr[::2, ::2]
            return bool(np.any((arr > 0) & (arr < 255)))
        except Exception:
            return True
    
    def _apply_opacity(self, image: Image.Image, opacity: float) -> Image.Image:
        """应用不透明度"""
        if opacity >= 1.0:
            return image

        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # 调整alpha通道
        r, g, b, a = image.split()
        a = a.point(lambda x: int(x * opacity))
        return Image.merge('RGBA', (r, g, b, a))

    def _apply_blend_mode(self, background: Image.Image, foreground: Image.Image,
                         dst_x: int, dst_y: int, blend_mode: str) -> Image.Image:
        """应用混合模式"""
        try:
            # 创建一个临时画布来应用混合
            temp_canvas = background.copy()

            # 提取需要混合的区域
            fg_width, fg_height = foreground.size
            bg_region = temp_canvas.crop((dst_x, dst_y, dst_x + fg_width, dst_y + fg_height))

            # 应用混合模式
            blended_region = self._blend_images(bg_region, foreground, blend_mode)

            # 将混合结果粘贴回画布
            temp_canvas.paste(blended_region, (dst_x, dst_y), blended_region)
            return temp_canvas

        except Exception as e:
            print(f"[快速渲染] 混合模式应用失败: {e}")
            # 回退到正常合成
            result = background.copy()
            result.paste(foreground, (dst_x, dst_y), foreground)
            return result

    def _blend_images(self, base: Image.Image, top: Image.Image, blend_mode: str) -> Image.Image:
        """执行图像混合"""
        try:
            # 使用文档混合器，确保所有模式生效
            from app.models.document_blend import Blender
            return Blender.apply_blend_mode(base, top, blend_mode, opacity=1.0)

        except Exception as e:
            print(f"[快速渲染] 图像混合失败: {e}")
            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
            return UnifiedAlphaCompositor.blend_normal(base.convert('RGBA'), top.convert('RGBA'), 1.0)

    def _high_quality_composite(self, background: Image.Image, foreground: Image.Image,
                               dst_x: int, dst_y: int, blend_mode: str = 'normal') -> Image.Image:
        """高质量合成（支持混合模式）"""
        try:
            if blend_mode == 'normal':
                # 正常模式使用高精度alpha混合
                return self._high_quality_alpha_composite(background, foreground, dst_x, dst_y)
            else:
                # 其他混合模式使用混合模式管理器
                return self._apply_blend_mode(background, foreground, dst_x, dst_y, blend_mode)

        except Exception as e:
            print(f"[快速渲染] 高质量合成失败: {e}")
            # 回退到简单合成
            result = background.copy()
            result.paste(foreground, (dst_x, dst_y), foreground)
            return result

    def _high_quality_alpha_composite(self, background: Image.Image, foreground: Image.Image,
                                     dst_x: int, dst_y: int) -> Image.Image:
        """高精度alpha合成"""
        try:
            # 使用numpy进行高精度alpha混合
            bg_array = np.array(background, dtype=np.float32) / 255.0
            fg_array = np.array(foreground, dtype=np.float32) / 255.0

            # 获取前景区域
            fg_h, fg_w = fg_array.shape[:2]
            bg_h, bg_w = bg_array.shape[:2]

            # 确保不越界
            end_x = min(dst_x + fg_w, bg_w)
            end_y = min(dst_y + fg_h, bg_h)

            if end_x <= dst_x or end_y <= dst_y:
                return background

            # 提取区域
            bg_region = bg_array[dst_y:end_y, dst_x:end_x]
            fg_region = fg_array[:end_y-dst_y, :end_x-dst_x]

            # Alpha混合
            fg_alpha = fg_region[:,:,3:4]
            bg_alpha = bg_region[:,:,3:4]

            # 转换为线性颜色空间进行混合 - 解决颜色变灰变黑问题
            from app.utils.unified_alpha_compositor import UnifiedAlphaCompositor
            
            fg_rgb = fg_region[:,:,:3]
            bg_rgb = bg_region[:,:,:3]
            
            # 转换到线性颜色空间
            fg_rgb_linear = UnifiedAlphaCompositor._srgb_to_linear(fg_rgb)
            bg_rgb_linear = UnifiedAlphaCompositor._srgb_to_linear(bg_rgb)

            # 计算输出alpha
            out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)

            # 避免除零
            safe_alpha = np.where(out_alpha > 1e-6, out_alpha, 1e-6)

            # 在线性颜色空间中计算输出颜色 - 解决颜色变灰问题
            out_rgb_linear = (fg_rgb_linear * fg_alpha + bg_rgb_linear * bg_alpha * (1 - fg_alpha)) / safe_alpha
            
            # 转换回sRGB颜色空间
            out_rgb = UnifiedAlphaCompositor._linear_to_srgb(out_rgb_linear)

            # 组合结果
            result_region = np.concatenate([out_rgb, out_alpha], axis=2)

            # 更新背景
            result_array = bg_array.copy()
            result_array[dst_y:end_y, dst_x:end_x] = result_region

            # 🔧 修复：使用抖动转换以消除色阶分层
            try:
                from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
                result_8bit = _float_to_uint8_with_dithering(result_array, use_dithering=True)
            except ImportError:
                # 后备方案：使用四舍五入
                result_8bit = np.round(np.clip(result_array, 0.0, 1.0) * 255.0).astype(np.uint8)
            return Image.fromarray(result_8bit, 'RGBA')

        except Exception as e:
            print(f"[快速渲染] 高精度alpha合成失败: {e}")
            # 回退到简单合成
            result = background.copy()
            result.paste(foreground, (dst_x, dst_y), foreground)
            return result
    
    def invalidate_cache(self):
        """使缓存失效"""
        self.intelligent_cache.clear()
    
    def get_performance_stats(self):
        """获取性能统计"""
        return {
            'cache': self.intelligent_cache.get_stats(),
            'last_render_times': self._last_render_time.copy()
        }

