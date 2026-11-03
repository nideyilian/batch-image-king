"""
真正有效的快速渲染器（优化版本）
解决实际使用中的性能问题，不降低质量
集成智能渲染缓存系统
"""

import time
import os
import builtins
from functools import wraps
from typing import Optional
from PIL import Image

# 默认关闭快速渲染器调试输出，避免预览阶段高频 I/O 导致掉帧
_FAST_RENDERER_DEBUG = os.environ.get("BTPW_FAST_RENDERER_DEBUG", "0") == "1"
# 默认关闭批量渲染高频日志，避免导出阶段控制台 I/O 成为瓶颈
_BATCH_RENDER_VERBOSE = os.environ.get("BTPW_BATCH_RENDER_VERBOSE", "0") == "1"
try:
    _INTERACTIVE_PREVIEW_MAX_EDGE = max(480, int(os.environ.get("BTPW_INTERACTIVE_PREVIEW_MAX_EDGE", "1200")))
except Exception:
    _INTERACTIVE_PREVIEW_MAX_EDGE = 1200
# 交互帧降采样的最小收益门槛。
#
# 降采样省的是「合成面积」，代价是「每层一次重采样」。设图层数为 N、
# 比例为 r，则合成耗时 ∝ r²，重采样耗时 ∝ N 且与 r 基本无关。
# 实测 8 层、1080×1350、r=0.889：不降采样 29.5ms（合成占比高但面积小），
# 降采样 402.7ms（用 float 预乘时）；换成 PIL 快速重采样后两者都是 ~30ms。
#
# 也就是说 r 不够小时，「省下的合成」根本抵不掉「多付的那次重采样」。
# 取 0.75：到这个比例才真正省下 44% 的合成面积，才值得为每层多付一次 resize。
# 0.75~1.0 之间直接返回 1.0（不降采样），此时画面还是全分辨率，
# 顺带消除了「交互帧 960×1200 ↔ final 帧 1080×1350」的纹理尺寸跳变（闪烁来源之一）。
try:
    _INTERACTIVE_PREVIEW_MIN_GAIN = float(os.environ.get("BTPW_INTERACTIVE_PREVIEW_MIN_GAIN", "0.75"))
except Exception:
    _INTERACTIVE_PREVIEW_MIN_GAIN = 0.75
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
# 导入智能内存管理系统
from .intelligent_memory_manager import register_image_for_tracking
from .render_diagnostics import log_branch
import logging

logger = logging.getLogger(__name__)


class FastRendererPreview(object):
    """Mixin for fast_renderer_preview (split from FastRenderer)."""

    @_serialized_preview
    def render_preview(self, document, force_refresh: bool = False, interactive_low_quality: bool = False, cancel_token=None) -> Optional[Image.Image]:
        """预览渲染 - 优化版本，使用智能缓存和内存管理"""
        if cancel_token is not None and getattr(cancel_token, "cancelled", False):
            return None
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
                low_quality_preview=interactive_low_quality,
                cancel_token=cancel_token,
            )
            log_branch("fast_renderer.render_preview", "fast_render_preview")

            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return None
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
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return None
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
                return self.render_preview(
                    force_refresh=force_refresh,
                    document=document,
                    interactive_low_quality=interactive_low_quality,
                    cancel_token=cancel_token,
                )

            active_layer = document.layers[active_layer_index]
            if active_layer is None or not getattr(active_layer, 'visible', True):
                return self.render_preview(
                    force_refresh=force_refresh,
                    document=document,
                    interactive_low_quality=interactive_low_quality,
                    cancel_token=cancel_token,
                )

            base = self._get_or_build_interaction_base(
                document=document,
                active_layer_index=active_layer_index,
                force_refresh=force_refresh,
                interactive_low_quality=interactive_low_quality,
                cancel_token=cancel_token,
            )
            if base is None:
                return self.render_preview(
                    force_refresh=force_refresh,
                    document=document,
                    interactive_low_quality=interactive_low_quality,
                    cancel_token=cancel_token,
                )

            render_scale = self._get_interactive_render_scale(document, True, interactive_low_quality)
            opacity = getattr(active_layer, 'opacity', 1.0)
            blend_mode = self._get_layer_blend_mode(active_layer)
            positions_info, mirror_mode = self._get_layer_positions_info_cached(active_layer, document)

            # 活动层 surface：交互低质走专用缓存（只含几何/变换），否则走通用 surface 缓存。
            # copy_result=False —— 下面只做 resize/paste，不改写这张图。
            if interactive_low_quality:
                layer_image = self._get_layer_surface_interactive_cached(
                    active_layer, document, was_just_loaded=False
                )
            else:
                layer_image = self.get_layer_surface_cached(
                    active_layer, document, was_just_loaded=False, copy_result=False
                )
            if layer_image is None:
                # 图层没有可用位图（空图层/加载失败）：退化成只有底图
                return base.copy()
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return None

            from PIL import ImageOps
            mirrored_h = ImageOps.mirror(layer_image) if mirror_mode == 'horizontal' else None
            mirrored_v = ImageOps.flip(layer_image) if mirror_mode == 'vertical' else None

            # 脏矩形：拖动只影响活动层的新旧两个矩形，其余像素与 base 完全一致。
            # 先算出本帧活动层要落到的所有目标矩形，再决定走「局部重合成」还是
            # 「整画布拷贝」——后者只在区域太大、或混合模式不允许局部裁切时使用。
            target_rects = []
            scaled_cache = []
            for pos_x, pos_y, is_mirror in positions_info:
                if is_mirror and mirror_mode == 'horizontal':
                    img_for_pos = mirrored_h if mirrored_h is not None else layer_image
                elif is_mirror and mirror_mode == 'vertical':
                    img_for_pos = mirrored_v if mirrored_v is not None else layer_image
                else:
                    img_for_pos = layer_image
                draw_x = int(round((int(pos_x) + int(getattr(active_layer, '_render_offset_x', 0))) * render_scale))
                draw_y = int(round((int(pos_y) + int(getattr(active_layer, '_render_offset_y', 0))) * render_scale))
                img_for_pos = self._scale_layer_for_interactive_preview(
                    img_for_pos, render_scale,
                    cache_key_part=(self._build_layer_surface_key(active_layer, document, False), is_mirror),
                )
                if img_for_pos is None:
                    continue
                target_rects.append((draw_x, draw_y, img_for_pos))
                scaled_cache.append(img_for_pos)

            if not target_rects:
                return base.copy()

            dirty = self._dirty_region_for_layer(active_layer, document, target_rects, render_scale)
            # 只有 normal 混合能安全做局部重合成：overlay/soft-light 等依赖
            # 上下文，局部裁切会改变结果，这类必须走整画布路径。
            can_patch = dirty is not None and blend_mode == 'normal'
            if can_patch:
                composition = self._compose_in_dirty_region(
                    base=base,
                    dirty=dirty,
                    target_rects=target_rects,
                    opacity=opacity,
                    interactive_low_quality=interactive_low_quality,
                    active_layer_index=active_layer_index,
                )
                if composition is not None:
                    return composition

            # 回退：整画布拷贝 + 逐矩形合成（原路径）
            composition = base.copy()
            for draw_x, draw_y, img_for_pos in target_rects:
                if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                    return None
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
            return self.render_preview(
                force_refresh=force_refresh,
                document=document,
                interactive_low_quality=interactive_low_quality,
                cancel_token=cancel_token,
            )

    # ---------------------------------------------------------------- 脏矩形

    def _dirty_region_for_layer(self, layer, document, target_rects, render_scale):
        """返回本帧需要重合成的像素矩形 (x0, y0, x1, y1)，含活动层新旧位置并集。

        为什么取**新旧并集**：拖动时旧位置会露出下层，只重算新位置会留残影。

        为什么必须加**效果外扩**：描边、阴影、外发光都会画到图层 bbox 之外，
        外扩量不够同样会留边。
        """
        try:
            rects = []
            for draw_x, draw_y, img in target_rects:
                rects.append((draw_x, draw_y, draw_x + img.width, draw_y + img.height))

            prev = getattr(self, '_dirty_prev_rects', None)
            prev_key = getattr(self, '_dirty_prev_key', None)
            cur_key = (id(document), id(layer))
            if prev and prev_key == cur_key:
                rects.extend(prev)

            if not rects:
                return None

            outset = self._layer_effects_outset_px(layer, render_scale)
            x0 = min(r[0] for r in rects) - outset
            y0 = min(r[1] for r in rects) - outset
            x1 = max(r[2] for r in rects) + outset
            y1 = max(r[3] for r in rects) + outset

            # 记录本帧矩形，供下一帧做并集
            self._dirty_prev_rects = [
                (draw_x, draw_y, draw_x + img.width, draw_y + img.height)
                for draw_x, draw_y, img in target_rects
            ]
            self._dirty_prev_key = cur_key

            # 裁到画布范围内
            canvas_w, canvas_h = int(document.canvas_width * render_scale), int(document.canvas_height * render_scale)
            x0 = max(0, int(x0)); y0 = max(0, int(y0))
            x1 = min(canvas_w, int(x1)); y1 = min(canvas_h, int(y1))
            if x1 <= x0 or y1 <= y0:
                return None
            return (x0, y0, x1, y1)
        except Exception:
            logger.warning("脏矩形计算失败，回退全量合成", exc_info=True)
            return None

    @staticmethod
    def _layer_effects_outset_px(layer, render_scale: float) -> int:
        """图层效果画到 bbox 之外的距离（像素，已按 render_scale 缩放）。

        覆盖当前支持的会外扩的效果：描边、阴影（偏移+模糊）、外发光。
        宁可多算几个像素（多重合成的面积很小），也不能漏 —— 漏了就是残影。
        """
        try:
            outset = 0.0
            if bool(getattr(layer, 'stroke_enabled', False)):
                outset = max(outset, float(getattr(layer, 'stroke_width', 0) or 0))
            if bool(getattr(layer, 'shadow_enabled', False)):
                blur = float(getattr(layer, 'shadow_blur', 0) or 0)
                off = max(
                    abs(float(getattr(layer, 'shadow_offset_x', 0) or 0)),
                    abs(float(getattr(layer, 'shadow_offset_y', 0) or 0)),
                )
                outset = max(outset, blur * 2.0 + off)
            if bool(getattr(layer, 'glow_enabled', False)):
                outset = max(outset, float(getattr(layer, 'glow_radius', 0) or 0) * 2.0)
            return int(round(outset * float(render_scale))) + 2
        except Exception:
            # 算不出来就当作「有外扩」，用保守值，避免出残影
            return 16

    def _compose_in_dirty_region(self, *, base, dirty, target_rects, opacity,
                                 interactive_low_quality, active_layer_index):
        """只重合成 dirty 矩形内的像素，返回整张画布；无法安全处理时返回 None。

        关键点：**不能只把活动层贴上去**。活动层移动后，它下方原本被遮住的
        图层要在脏区内重新露出来，只贴活动层会得到「旧内容 + 新图层」的错误叠加。

        正确做法：脏区内 = 「base 中该区域**位于活动层之下**的合成结果」
        + 「活动层按新位置叠加」。

        而 base 本身是「**去掉活动层**后的静态底图」（见 _get_or_build_interaction_base），
        所以 base 的脏区内容天然就是「活动层之下」的正确结果 —— 直接在它上面
        叠加活动层即可，既正确又只需处理一个小矩形。
        """
        x0, y0, x1, y1 = dirty
        try:
            region = base.crop(dirty)
            for draw_x, draw_y, img in target_rects:
                region = self._fast_composite(
                    region,
                    img,
                    draw_x - x0,
                    draw_y - y0,
                    opacity,
                    preview_mode=True,
                    blend_mode='normal',
                    low_quality_preview=interactive_low_quality,
                )
            result = base.copy()
            result.paste(region, (x0, y0))
            return result
        except Exception:
            logger.warning("脏区重合成立失败，回退全量", exc_info=True)
            return None

    @_serialized_preview
    def render_preview_without_layer(
        self,
        document,
        active_layer_index: int,
        force_refresh: bool = False,
        interactive_low_quality: bool = True,
        cancel_token=None,
    ) -> Optional[Image.Image]:
        """Render a preview base with the active layer omitted for direct editing."""
        try:
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return None
            if active_layer_index < 0 or active_layer_index >= len(document.layers):
                return self.render_preview(
                    document=document,
                    force_refresh=force_refresh,
                    interactive_low_quality=interactive_low_quality,
                    cancel_token=cancel_token,
                )
            return self._get_or_build_interaction_base(
                document=document,
                active_layer_index=active_layer_index,
                force_refresh=force_refresh,
                interactive_low_quality=interactive_low_quality,
                cancel_token=cancel_token,
            )
        except Exception as e:
            print(f"[快速渲染] 编辑底图预览失败，回退普通预览: {e}")
            return self.render_preview(
                document=document,
                force_refresh=force_refresh,
                interactive_low_quality=interactive_low_quality,
                cancel_token=cancel_token,
            )
    
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
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                return None
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
                return None
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
                # copy_result=False：交互预览只读这张 surface（resize/paste），
                # 不改写它。省掉每层一次整图拷贝（2000x2500 是 15MB），
                # 并让下游降采样缓存能按内容键稳定命中。
                layer_image = self.get_layer_surface_cached(
                    layer, document, was_just_loaded, copy_result=False
                )
                if layer_image is None:
                    continue
                positions_info, mirror_mode = self._get_layer_positions_info_cached(layer, document)

            # 降采样缓存的键：用 surface 的内容键，不用 id()。
            # id() 会随缓存驱逐/重建而漂移（同一图层重新生成的 surface 拿到新 id），
            # 导致旧条目变成孤儿、条目数无限增长。content key 由图层属性决定，
            # 驱逐后重建也能命中同一 key。
            scaled_cache_key = self._build_layer_surface_key(layer, document, was_just_loaded)
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
                img_for_pos = self._scale_layer_for_interactive_preview(
                    img_for_pos, render_scale, cache_key_part=(scaled_cache_key, is_mirror)
                )
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
        """Return a temporary downsample ratio for interactive preview only.

        只有「真能省下来」的降采样才做。实测（`docs/audit/_probe_bleed.py`、
        `_bench_drag_frames.py`）：降采样要付出**每层一次重采样**的代价，
        而画布合成开销只按面积线性降。降到 89% 时省下的合成时间
        （约 3ms/帧）远小于重采样代价（8 层 × 4.3ms ≈ 34ms，用 float 预乘时 345ms），
        整体反而比不降采样更慢 —— 这就是「拖得比松手后还慢」的原因。

        所以低于 ``_INTERACTIVE_PREVIEW_MIN_GAIN`` 的比例直接按 1.0 处理：
        宁可多合成一点面积，也不要每层多一次重采样。
        """
        if not (preview_mode and low_quality_preview):
            return 1.0
        max_edge = max(int(getattr(document, "canvas_width", 1) or 1), int(getattr(document, "canvas_height", 1) or 1))
        if max_edge <= _INTERACTIVE_PREVIEW_MAX_EDGE:
            return 1.0
        ratio = max(0.20, min(1.0, _INTERACTIVE_PREVIEW_MAX_EDGE / float(max_edge)))
        if ratio >= _INTERACTIVE_PREVIEW_MIN_GAIN:
            return 1.0
        return ratio

    def _scale_layer_for_interactive_preview(self, image: Image.Image, render_scale: float,
                                             cache_key_part=None) -> Image.Image:
        """Downsample a layer surface for low-cost interaction frames.

        这里**不能用** ``rgba_resampler.resize_rgba_premultiplied``：
        它为了消除透明区的 RGB 渗色，把 RGBA 拆成 4 个 float32 通道分别重采样
        再相除还原，精度高但慢一个数量级（实测 760×560 单层 43.3ms）。
        那条路径属于导出/缩略图这类「只做一次」的场景，交互帧套用它是选错了工具。

        交互帧改用 PIL 单次 BILINEAR：同尺寸 4.3ms（10 倍快）。
        精度代价实测（`docs/audit/_probe_bleed.py`，素材透明区刻意填纯黑）：
        缩到 0.3 时实心区平均色差 0.7/255，0.5 及以下为 0.0/255 —— 肉眼不可见，
        而且下一帧 final 就会用全质量重算，误差不会留在成图上。
        """
        if image is None or render_scale >= 0.999:
            return image
        target_size = (
            max(1, int(round(image.width * render_scale))),
            max(1, int(round(image.height * render_scale))),
        )
        if target_size == image.size:
            return image

        # 降采样结果按 (内容键, 尺寸) 缓存：同一图层 surface 的内容和缩放比例
        # 在多帧之间通常不变，而 resize+convert 实测占 4000x5000 单帧的 76%。
        # key 必须用**内容键**而不是 id(image)：surface 缓存驱逐后重建会拿到
        # 新对象，id 变化会让旧条目变孤儿、条目数无限增长（实测 8→16→24…）。
        if cache_key_part is None:
            cache_key = ("obj", id(image), target_size)
        else:
            cache_key = (cache_key_part, target_size)
        scale_token = float(render_scale)
        try:
            with self._interactive_scaled_lock:
                if self._interactive_scaled_render_scale != scale_token:
                    # 缩放比例变了 → 整批失效，避免不同 scale 的结果互相污染
                    for value in list(self._interactive_scaled_cache.values()):
                        self._close_cached_value(value)
                    self._interactive_scaled_cache.clear()
                    self._interactive_scaled_entry_bytes.clear()
                    self._interactive_scaled_bytes = 0
                    self._interactive_scaled_render_scale = scale_token
                else:
                    entry = self._interactive_scaled_cache.get(cache_key)
                    if entry is not None:
                        self._interactive_scaled_cache.move_to_end(cache_key)
                        cached = entry.get("image")
                        if cached is not None:
                            return cached.copy()
        except Exception:
            logger.warning("交互缩放缓存查询失败，回退直接重采样", exc_info=True)

        try:
            scaled = image.resize(target_size, Image.Resampling.BILINEAR)
        except Exception:
            return image

        try:
            with self._interactive_scaled_lock:
                self._set_cache_value_unlocked(
                    self._interactive_scaled_cache,
                    self._interactive_scaled_entry_bytes,
                    "_interactive_scaled_bytes",
                    cache_key,
                    {"image": scaled.copy()},
                    self._max_interactive_scaled_entries,
                    self._max_interactive_scaled_bytes,
                )
        except Exception:
            logger.warning("交互缩放缓存写入失败", exc_info=True)
        return scaled
