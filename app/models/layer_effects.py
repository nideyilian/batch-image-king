from PySide6.QtCore import QObject, Signal, Property
import os
import builtins
import sys
import random
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from enum import Enum, auto
import copy  # 导入copy模块实现深拷贝
from collections import OrderedDict
import hashlib
import threading
from typing import List, Tuple
import math
from app.utils.image.high_quality_resampler import HighQualityResampler
from app.utils.render_diagnostics import log_branch


_LAYER_DEBUG = os.environ.get("BTPW_LAYER_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")


def print(*args, **kwargs):
    """Keep noisy layer diagnostics off the interactive preview path by default."""
    if _LAYER_DEBUG:
        builtins.print(*args, **kwargs)


def _is_batch_render_context() -> bool:
    """Cheap call-stack check used by legacy layer code.

    The previous inspect.stack() call allocates FrameInfo objects for the whole
    stack on every image load. Walking frames directly is much lighter and keeps
    the same behavior for batch/export detection.
    """
    frame = sys._getframe(1)
    checked = 0
    while frame is not None and checked < 32:
        name = frame.f_code.co_name
        if (
            "batch_export" in name
            or "render_batch" in name
            or "export_batch" in name
            or "generate_combinations" in name
        ):
            return True
        frame = frame.f_back
        checked += 1
    return False


class LayerEffects(object):
    """Mixin for layer_effects (split from Layer)."""

    def apply_effects(self, image):
        """应用图层特效的公共方法，调用私有实现"""
        return self._apply_effects(image)

    @classmethod
    def _get_effects_stage_cache(cls, cache_key: str):
        with cls._effects_stage_cache_lock:
            cached = cls._effects_stage_cache.get(cache_key)
            if cached is None:
                return None
            cls._effects_stage_cache.move_to_end(cache_key)
            return cached.copy()

    @classmethod
    def _set_effects_stage_cache(cls, cache_key: str, image):
        if image is None:
            return
        with cls._effects_stage_cache_lock:
            cls._effects_stage_cache[cache_key] = image.copy()
            cls._effects_stage_cache.move_to_end(cache_key)
            while len(cls._effects_stage_cache) > cls._effects_stage_cache_max_entries:
                cls._effects_stage_cache.popitem(last=False)

    def _build_effects_stage_cache_key(self, stage_name: str, image, extra_parts: List[str]) -> str:
        source_parts = [
            f"stage:{stage_name}",
            f"path:{self._current_image_path or ''}",
            f"src:{self._image_source or ''}",
            f"img:{getattr(image, 'width', 0)}x{getattr(image, 'height', 0)}:{getattr(image, 'mode', '')}",
            f"layer:{self._width}x{self._height}",
            f"fit:{self._fit_mode}",
            f"crop:{self._crop_direction}",
            f"use_orig:{int(bool(self._use_original_size))}",
            f"rot:{float(self._rotation):.3f}",
            f"flip_h:{int(bool(self._flip_horizontal))}",
            f"flip_v:{int(bool(self._flip_vertical))}",
            f"rnd_scale:{float(getattr(self, '_current_random_scale', 1.0)):.6f}",
            f"rnd_rot:{float(getattr(self, '_current_random_rotation', 0.0)):.3f}",
        ]
        source_parts.extend(extra_parts)
        return hashlib.md5("|".join([str(p) for p in source_parts]).encode('utf-8')).hexdigest()
    
    def _apply_effects(self, image):
        """应用图层特效（圆角、描边等）和变换（旋转、翻转）"""
        if image is None:
            return None
        self._render_offset_x = 0
        self._render_offset_y = 0
        
        # 批处理模式下减少日志输出
        is_batch_mode = getattr(self, '_is_batch_mode', False)
        if not is_batch_mode:
            print(f"应用特效前图像尺寸: {image.width}x{image.height}, 图层尺寸: {self._width}x{self._height}")
        
        # 如果图像尺寸与图层尺寸不匹配，根据模式处理
        fit_mode = int(getattr(self, '_fit_mode', 0))
        if image.width != self._width or image.height != self._height:
            if fit_mode == 2:
                # 等比缩放不裁剪模式：保持原图尺寸，继续应用特效
                if not is_batch_mode:
                    print(f"等比缩放不裁剪模式：保持图像尺寸不变 {image.width}x{image.height}，继续应用圆角/描边")
            elif fit_mode == 1:
                image = self._center_image_on_layer_canvas(image, self._width, self._height)
            else:
                if not is_batch_mode:
                    print(f"警告：图像尺寸与图层尺寸不匹配，调整图像大小: {image.width}x{image.height} => {self._width}x{self._height}")
                image = self._resize_with_premultiplied_alpha(image, (self._width, self._height))
        
        stroke_enabled = self._stroke_enabled and self._stroke_width > 0
        log_branch(
            "layer._apply_effects",
            "enter",
            corner_radius=self._corner_radius,
            stroke_enabled=stroke_enabled,
            stroke_type=self._stroke_type,
            stroke_width=self._stroke_width,
        )

        # 阶段1：几何与变换（可缓存）
        stage1_extra_parts = [
            f"corner:{int(self._corner_radius)}",
            f"vcorner:{int(self._vector_corner_radius_tl)}:{int(self._vector_corner_radius_tr)}:"
            f"{int(self._vector_corner_radius_br)}:{int(self._vector_corner_radius_bl)}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"vpath_on:{int(bool(self._vector_path_enabled))}",
            f"vpath_pts:{str(self._vector_path_points)}",
            f"vpath_mode:{str(self._vector_path_mode)}",
            f"vpath_bezier:{str(self._vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self._vector_path_closed))}",
            f"vpath_link:{str(self._vector_handle_link_mode)}",
            f"shape:{getattr(getattr(self, '_shape_type', ''), 'value', getattr(self, '_shape_type', ''))}",
            f"trap:{getattr(self, '_trapezoid_top_width', '')},{getattr(self, '_trapezoid_bottom_width', '')},{getattr(self, '_trapezoid_slope_side', '')}",
            f"poly:{getattr(self, '_polygon_rotation', '')},{getattr(self, '_polygon_corner_radius', '')}",
        ]
        stage1_key = self._build_effects_stage_cache_key("geometry", image, stage1_extra_parts)
        result = self._get_effects_stage_cache(stage1_key)
        if result is None:
            result = (image.convert('RGBA') if image.mode != 'RGBA' else image.copy())
            result = self._apply_transformations(result)
            # 统一走矢量几何路径，不再在此阶段做位图圆角遮罩后处理
            self._set_effects_stage_cache(stage1_key, result)

        # 阶段2：叠加样式（可缓存）
        stage2_extra_parts = [
            f"base:{stage1_key}",
            f"overlay_on:{int(bool(self._color_overlay_enabled))}",
            f"overlay_c:{str(self._color_overlay_color)}",
            f"overlay_op:{float(self._color_overlay_opacity):.4f}",
            f"grad_on:{int(bool(self._gradient_overlay_enabled))}",
            f"grad_angle:{float(self._gradient_overlay_angle):.3f}",
            f"grad_op:{float(self._gradient_overlay_opacity):.4f}",
            f"grad_colors:{str(self._gradient_overlay_colors)}",
        ]
        stage2_key = self._build_effects_stage_cache_key("overlay", image, stage2_extra_parts)
        overlay_result = self._get_effects_stage_cache(stage2_key)
        if overlay_result is None:
            overlay_result = result.copy()
            if self._color_overlay_enabled:
                overlay_result = self._apply_color_overlay(overlay_result)
            if self._gradient_overlay_enabled:
                overlay_result = self._apply_gradient_overlay(overlay_result)
            self._set_effects_stage_cache(stage2_key, overlay_result)
        result = overlay_result
        
        # 阶段3：描边与最终收敛（可缓存）
        stage3_extra_parts = [
            "vec_pipe_ver:v5",
            f"base:{stage2_key}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"stroke_type:{int(self._stroke_type)}",
            f"stroke_w:{int(self._stroke_width)}",
            f"stroke_c:{str(self._stroke_color)}",
            f"stroke_join:{str(self._stroke_join)}",
            f"stroke_cap:{str(self._stroke_cap)}",
            f"dash_len:{int(self._stroke_dash_length)}",
            f"dash_gap:{int(self._stroke_dash_gap)}",
            f"corner:{int(self._corner_radius)}",
            f"vcorner:{int(self._vector_corner_radius_tl)}:{int(self._vector_corner_radius_tr)}:"
            f"{int(self._vector_corner_radius_br)}:{int(self._vector_corner_radius_bl)}",
            f"vpath_on:{int(bool(self._vector_path_enabled))}",
            f"vpath_pts:{str(self._vector_path_points)}",
            f"vpath_mode:{str(self._vector_path_mode)}",
            f"vpath_bezier:{str(self._vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self._vector_path_closed))}",
            f"vpath_link:{str(self._vector_handle_link_mode)}",
            f"shape:{getattr(getattr(self, '_shape_type', ''), 'value', getattr(self, '_shape_type', ''))}",
            f"trap:{getattr(self, '_trapezoid_top_width', '')},{getattr(self, '_trapezoid_bottom_width', '')},{getattr(self, '_trapezoid_slope_side', '')}",
            f"poly:{getattr(self, '_polygon_rotation', '')},{getattr(self, '_polygon_corner_radius', '')}",
            f"out_size:{int(self._width)}x{int(self._height)}",
            f"fit:{int(self._fit_mode)}",
        ]
        stage3_key = self._build_effects_stage_cache_key("stroke_finalize", image, stage3_extra_parts)
        final_result = self._get_effects_stage_cache(stage3_key)
        if final_result is None:
            final_result = result.copy()
            shape_type_value = str(getattr(getattr(self, "_shape_type", None), "value", getattr(self, "_shape_type", "rectangle")))
            non_rect_shape = shape_type_value != "rectangle"
            use_vector_stroke_pipeline = bool(
                non_rect_shape
                or self._vector_path_enabled
                or stroke_enabled
                or self._corner_radius > 0
                or getattr(self, '_vector_corner_radius_tl', 0) > 0
                or getattr(self, '_vector_corner_radius_tr', 0) > 0
                or getattr(self, '_vector_corner_radius_br', 0) > 0
                or getattr(self, '_vector_corner_radius_bl', 0) > 0
                or self._stroke_dash_length > 0
                or self._stroke_dash_gap > 0
                or self._stroke_join != "miter"
                or self._stroke_cap != "butt"
            )
            if use_vector_stroke_pipeline:
                final_result = self._apply_vector_path_effects(final_result, stroke_enabled)
            elif stroke_enabled:
                if self._stroke_type == 0:  # 内描边
                    log_branch("layer._apply_effects", "stroke_inner")
                    final_result = self._apply_inner_stroke(final_result)
                elif self._stroke_type == 1:  # 居中描边
                    log_branch("layer._apply_effects", "stroke_center")
                    final_result = self._apply_center_stroke(final_result)
                elif self._stroke_type == 2:  # 外描边
                    log_branch("layer._apply_effects", "stroke_outer")
                    final_result = self._apply_outer_stroke(final_result)

            # 非矢量管线才强制收敛到图层尺寸；矢量管线允许外扩（居中/外描边）
            if (not use_vector_stroke_pipeline) and self._fit_mode not in (1, 2) and (final_result.width != self._width or final_result.height != self._height):
                if not is_batch_mode:
                    print(f"警告：应用特效后图像尺寸变化: {final_result.width}x{final_result.height}，调整为图层尺寸: {self._width}x{self._height}")
                final_result = self._resize_with_premultiplied_alpha(final_result, (self._width, self._height))
            self._set_effects_stage_cache(stage3_key, final_result)

        self._render_offset_x = int(getattr(final_result, 'info', {}).get('vector_offset_x', 0))
        self._render_offset_y = int(getattr(final_result, 'info', {}).get('vector_offset_y', 0))
        if not is_batch_mode:
            print(f"应用特效后图像尺寸: {final_result.width}x{final_result.height}, 图层尺寸: {self._width}x{self._height}")
        return final_result

    def _center_image_on_layer_canvas(self, image, target_width, target_height):
        """Return a layer-sized transparent canvas with image centered, preserving ratio."""
        target_width = max(1, int(target_width))
        target_height = max(1, int(target_height))
        if image.width > target_width or image.height > target_height:
            scale = min(target_width / image.width, target_height / image.height)
            new_size = (
                max(1, int(round(image.width * scale))),
                max(1, int(round(image.height * scale))),
            )
            image = self._resize_with_premultiplied_alpha(image, new_size)
        elif image.mode != 'RGBA':
            image = image.convert('RGBA')

        canvas = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
        x = (target_width - image.width) // 2
        y = (target_height - image.height) // 2
        if image.mode == 'RGBA':
            canvas.paste(image, (x, y), image)
        else:
            canvas.paste(image, (x, y))
        return canvas

    def _build_rounded_rect_outline_points_px(self):
        from app.utils.vector_layer_geometry import build_rounded_rect_outline_points

        return build_rounded_rect_outline_points(
            float(self._width),
            float(self._height),
            float(self._corner_radius),
            float(self._vector_corner_radius_tl),
            float(self._vector_corner_radius_tr),
            float(self._vector_corner_radius_br),
            float(self._vector_corner_radius_bl),
        )

    def _build_vector_outline_points_px(self):
        from app.utils.vector_layer_geometry import build_vector_outline_points_px

        return build_vector_outline_points_px(
            int(self._width),
            int(self._height),
            int(self._corner_radius),
            int(self._vector_corner_radius_tl),
            int(self._vector_corner_radius_tr),
            int(self._vector_corner_radius_br),
            int(self._vector_corner_radius_bl),
            bool(self._vector_path_enabled),
            str(self._vector_path_mode),
            self._vector_path_points,
            self._vector_bezier_nodes,
            bool(self._vector_path_closed),
            str(getattr(getattr(self, "_shape_type", "rectangle"), "value", getattr(self, "_shape_type", "rectangle"))),
            int(getattr(self, "_trapezoid_top_width", 100)),
            int(getattr(self, "_trapezoid_bottom_width", 80)),
            str(getattr(self, "_trapezoid_slope_side", "right")),
            float(getattr(self, "_polygon_rotation", 0.0)),
            int(getattr(self, "_polygon_corner_radius", 0)),
        )

    def _apply_vector_path_effects(self, image, stroke_enabled):
        """基于可编辑路径应用内容裁剪与描边几何，保证导出一致"""
        from app.utils.vector_layer_effects import VectorEffectParams, apply_vector_path_effects

        p = VectorEffectParams(
            width=int(self._width),
            height=int(self._height),
            corner_radius=int(self._corner_radius),
            vector_corner_radius_tl=int(self._vector_corner_radius_tl),
            vector_corner_radius_tr=int(self._vector_corner_radius_tr),
            vector_corner_radius_br=int(self._vector_corner_radius_br),
            vector_corner_radius_bl=int(self._vector_corner_radius_bl),
            vector_path_enabled=bool(self._vector_path_enabled),
            vector_path_points=self._vector_path_points,
            vector_path_mode=str(self._vector_path_mode),
            vector_bezier_nodes=self._vector_bezier_nodes,
            vector_path_closed=bool(self._vector_path_closed),
            shape_type=str(getattr(getattr(self, "_shape_type", "rectangle"), "value", getattr(self, "_shape_type", "rectangle"))),
            trapezoid_top_width=int(getattr(self, "_trapezoid_top_width", 100)),
            trapezoid_bottom_width=int(getattr(self, "_trapezoid_bottom_width", 80)),
            trapezoid_slope_side=str(getattr(self, "_trapezoid_slope_side", "right")),
            polygon_rotation=float(getattr(self, "_polygon_rotation", 0.0)),
            polygon_corner_radius=int(getattr(self, "_polygon_corner_radius", 0)),
            stroke_enabled=bool(stroke_enabled),
            stroke_width=int(self._stroke_width),
            stroke_type=int(self._stroke_type),
            stroke_color=tuple(self._stroke_color),
            stroke_join=str(self._stroke_join),
            stroke_cap=str(self._stroke_cap),
            stroke_dash_length=int(self._stroke_dash_length),
            stroke_dash_gap=int(self._stroke_dash_gap),
        )
        result = apply_vector_path_effects(image, p, alpha_composite=self._safe_alpha_composite)
        self._render_offset_x = int(result.info.get("vector_offset_x", 0))
        self._render_offset_y = int(result.info.get("vector_offset_y", 0))
        return result

    def _apply_inner_stroke(self, image):
        """应用内向描边效果，保持图层尺寸不变 - 使用现代样式渲染器"""
        if image is None or self._stroke_width <= 0:
            return image

        try:
            # 强制使用本地几何描边实现，确保颜色/对齐/透明参数稳定生效
            raise RuntimeError("force_legacy_stroke_pipeline")
            # 🚀 使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代内描边，宽度: {self._stroke_width}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:
                quality = "fast"
            elif image.width * image.height > 250000:
                quality = "medium"
            else:
                quality = "high"

            result = modern_renderer.apply_modern_stroke(
                image, self._stroke_width, self._stroke_color, "inner", quality, self._corner_radius
            )

            if result is not None:
                print(f"[图层效果] 现代内描边成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代内描边返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代内描边失败: {modern_e}")
            # 降级到原有实现
            # 保持原始图层尺寸
            result_width = self._width
            result_height = self._height

            # 创建高质量描边蒙版
            stroke_width = min(self._stroke_width, min(result_width, result_height) // 4)  # 限制描边宽度
            stroke_mask = self._create_stroke_mask(result_width, result_height, stroke_width, self._corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self._stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 使用改进的合成方式避免黑色边缘
            result = self._safe_alpha_composite(image.convert('RGBA'), stroke_layer)

            # 将原图像内容粘贴到描边上方（保留原图像内容）
            if stroke_width * 2 < result_width and stroke_width * 2 < result_height:
                # 创建内容区域的高质量蒙版
                inner_radius = max(0, self._corner_radius - stroke_width) if self._corner_radius > 0 else 0
                content_mask = self._create_content_mask(result_width, result_height, stroke_width, inner_radius)

                # 缩放原图像以适应内容区域
                content_width = result_width - stroke_width * 2
                content_height = result_height - stroke_width * 2
                scaled_image = image.resize((content_width, content_height), Resampling.LANCZOS)

                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (stroke_width, stroke_width), scaled_image)
                content_layer.putalpha(content_mask)

                # 使用改进的合成方式
                result = self._safe_alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用内向描边效果时出错: {e}")
            return image

    def _apply_center_stroke(self, image):
        """应用居中描边效果，保持图层尺寸不变 - 使用现代样式渲染器"""
        if image is None or self._stroke_width <= 0:
            return image

        try:
            # 强制使用本地几何描边实现，确保颜色/对齐/透明参数稳定生效
            raise RuntimeError("force_legacy_stroke_pipeline")
            # 🚀 使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代居中描边，宽度: {self._stroke_width}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:
                quality = "fast"
            elif image.width * image.height > 250000:
                quality = "medium"
            else:
                quality = "high"

            result = modern_renderer.apply_modern_stroke(
                image, self._stroke_width, self._stroke_color, "center", quality, self._corner_radius
            )

            if result is not None:
                print(f"[图层效果] 现代居中描边成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代居中描边返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代居中描边失败: {modern_e}")
            # 降级到原有实现
            # 保持原始图层尺寸
            result_width = self._width
            result_height = self._height

            # 居中描边：一半向内，一半向外，但最终保持图层尺寸
            half_stroke = self._stroke_width / 2.0

            # 创建高质量居中描边蒙版
            inner_stroke = int(half_stroke)
            stroke_mask = self._create_center_stroke_mask(result_width, result_height, inner_stroke, self._corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self._stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 使用改进的合成方式避免黑色边缘
            result = self._safe_alpha_composite(image.convert('RGBA'), stroke_layer)

            # 将原图像内容缩放并居中放置
            if inner_stroke * 2 < result_width and inner_stroke * 2 < result_height:
                # 创建内容区域的高质量蒙版
                inner_radius = max(0, self._corner_radius - half_stroke) if self._corner_radius > 0 else 0
                content_mask = self._create_content_mask(result_width, result_height, inner_stroke, inner_radius)

                # 缩放原图像以适应内容区域
                content_width = result_width - inner_stroke * 2
                content_height = result_height - inner_stroke * 2
                scaled_image = image.resize((content_width, content_height), Resampling.LANCZOS)

                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (inner_stroke, inner_stroke), scaled_image)
                content_layer.putalpha(content_mask)

                # 使用改进的合成方式
                result = self._safe_alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用居中描边效果时出错: {e}")
            return image

    def _apply_outer_stroke(self, image):
        """应用外描边效果 - 使用现代样式渲染器（不改变图层尺寸）"""
        if image is None or self._stroke_width <= 0:
            return image

        try:
            # 强制使用本地几何描边实现，确保颜色/对齐/透明参数稳定生效
            raise RuntimeError("force_legacy_stroke_pipeline")
            # 🚀 使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代外描边，宽度: {self._stroke_width}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:
                quality = "fast"
            elif image.width * image.height > 250000:
                quality = "medium"
            else:
                quality = "high"

            result = modern_renderer.apply_modern_stroke(
                image, self._stroke_width, self._stroke_color, "outer", quality, self._corner_radius
            )

            if result is not None:
                print(f"[图层效果] 现代外描边成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代外描边返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代外描边失败: {modern_e}")
            # 降级到原有实现
            # 外描边会增加图层尺寸
            stroke_width = self._stroke_width
            expanded_width = self._width + stroke_width * 2
            expanded_height = self._height + stroke_width * 2

            # 创建扩展画布
            expanded_image = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))

            # 创建高质量外描边蒙版
            stroke_mask = self._create_outer_stroke_mask(expanded_width, expanded_height, stroke_width, self._corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (expanded_width, expanded_height), self._stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 使用改进的合成方式避免黑色边缘
            expanded_image = self._safe_alpha_composite(expanded_image, stroke_layer)

            # 将内容图层放到中央并按内轮廓裁切，确保与描边几何严格一致
            content_layer = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))
            content_layer.paste(image, (stroke_width, stroke_width), image)
            content_mask = self._create_content_mask(expanded_width, expanded_height, stroke_width, self._corner_radius)
            content_layer.putalpha(content_mask)
            expanded_image = self._safe_alpha_composite(expanded_image, content_layer)

            return expanded_image

        except Exception as e:
            print(f"应用外描边效果时出错: {e}")
            return image

    def _apply_corner_radius_improved(self, image):
        """改进的圆角处理，使用现代样式渲染器"""
        if image is None or self._corner_radius <= 0:
            return image

        try:
            # 🚀 新方案：使用现代样式渲染器
            from app.utils.modern_style_renderer import get_modern_style_renderer
            modern_renderer = get_modern_style_renderer()

            print(f"[图层效果] 使用现代样式渲染器，半径: {self._corner_radius}")

            # 根据图像尺寸自动选择质量等级
            if image.width * image.height > 1000000:  # 大图像使用快速模式
                quality = "fast"
            elif image.width * image.height > 250000:  # 中图像使用中等质量
                quality = "medium"
            else:  # 小图像使用高质量
                quality = "high"

            result = modern_renderer.apply_modern_corner_radius(image, self._corner_radius, quality)

            if result is not None:
                print(f"[图层效果] 现代圆角渲染成功 (质量: {quality})")
                return result
            else:
                print(f"[图层效果] 现代圆角渲染返回None，使用降级方案")

        except Exception as modern_e:
            print(f"[图层效果] 现代圆角处理失败: {modern_e}")
            # 降级到增强圆角渲染器
            try:
                from app.utils.enhanced_corner_renderer import get_enhanced_corner_renderer
                enhanced_renderer = get_enhanced_corner_renderer()
                result = enhanced_renderer.apply_enhanced_corner_radius(image, self._corner_radius)
                if result is not None:
                    return result
            except Exception as enhanced_e:
                print(f"[图层效果] 增强圆角处理也失败: {enhanced_e}")
            # 继续降级到终极圆角渲染器
            try:
                from app.utils.enhanced_corner_renderer import get_ultimate_corner_renderer
                ultimate_renderer = get_ultimate_corner_renderer()

                print(f"[图层效果] 使用终极圆角渲染器，半径: {self._corner_radius}")

                result = ultimate_renderer.apply_ultimate_corner_radius(image, self._corner_radius)

                if result is not None:
                    print(f"[图层效果] 终极圆角渲染成功")
                    return result
                else:
                    print(f"[图层效果] 终极圆角渲染返回None，使用降级方案")

            except Exception as ultimate_e:
                print(f"[图层效果] 终极圆角处理失败: {ultimate_e}")



        # 最终降级：使用优化的传统方法
        try:
            print(f"[图层效果] 使用优化传统圆角处理，半径: {self._corner_radius}")

            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # 创建优化的圆角蒙版
            mask = self._create_optimized_corner_mask(self._width, self._height, self._corner_radius)

            # 使用numpy进行精确的Alpha混合
            import numpy as np

            # 分离RGBA通道
            r, g, b, a = image.split()

            # 转换为numpy数组进行精确计算
            a_array = np.array(a, dtype=np.float32) / 255.0
            mask_array = np.array(mask, dtype=np.float32) / 255.0

            # 精确的Alpha混合
            new_alpha_array = a_array * mask_array

            # 转换回PIL格式
            new_alpha_array = np.clip(new_alpha_array * 255, 0, 255).astype(np.uint8)
            new_alpha = Image.fromarray(new_alpha_array, mode='L')

            # 重新组合图像
            result = Image.merge('RGBA', (r, g, b, new_alpha))

            print(f"[图层效果] 优化传统圆角处理完成")
            return result

        except Exception as fallback_e:
            print(f"[图层效果] 所有圆角处理方法都失败: {fallback_e}")
            return image

    def _create_optimized_corner_mask(self, width, height, radius):
        """创建优化的圆角蒙版，平衡质量和性能"""
        try:
            # 🎯 智能超采样：根据半径大小调整超采样倍数
            if radius <= 5:
                scale = 2  # 小半径用2倍超采样
            elif radius <= 15:
                scale = 3  # 中等半径用3倍超采样
            else:
                scale = 4  # 大半径用4倍超采样

            large_width = width * scale
            large_height = height * scale
            large_radius = radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 绘制圆角矩形
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=large_radius,
                fill=255
            )

            # 🎯 优化：根据半径大小调整模糊强度
            if radius > 10:
                # 大半径：使用轻微模糊进一步平滑
                large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=0.8))
            elif radius > 5:
                # 中等半径：使用很轻的模糊
                large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=0.4))
            # 小半径不需要额外模糊

            # 缩放回原始尺寸，使用最高质量重采样
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            # 🎯 最终优化：对小半径进行微调
            if radius <= 3:
                mask = mask.filter(ImageFilter.GaussianBlur(radius=0.1))

            return mask

        except Exception as e:
            print(f"[图层效果] 创建优化圆角蒙版失败: {e}")
            # 回退到传统平滑蒙版
            return self._create_smooth_corner_mask(width, height, radius)

    def _create_smooth_corner_mask(self, width, height, radius):
        """创建平滑的圆角蒙版，使用抗锯齿（降级方案）"""
        try:
            # 创建更大的蒙版用于抗锯齿
            scale = 4  # 超采样倍数
            large_width = width * scale
            large_height = height * scale
            large_radius = radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 绘制圆角矩形
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=large_radius,
                fill=255
            )

            # 缩放回原始尺寸，这会产生抗锯齿效果
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"[图层效果] 创建平滑圆角蒙版失败: {e}")
            # 回退到最简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            return mask

    def _create_stroke_mask(self, width, height, stroke_width, corner_radius):
        """创建高质量的描边蒙版，避免黑色弧线"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = stroke_width * scale
            large_radius = corner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 外层边界（图层边缘）
            outer_radius = large_radius if large_radius > 0 else 0
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=int(outer_radius),
                fill=255
            )

            # 内层边界（描边内边缘）
            inner_radius = max(0, large_radius - large_stroke) if large_radius > 0 else 0

            if large_stroke * 2 < large_width and large_stroke * 2 < large_height:
                draw.rounded_rectangle(
                    (int(large_stroke), int(large_stroke),
                     large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                    radius=int(inner_radius),
                    fill=0
                )

            # 缩放回原始尺寸，产生抗锯齿效果
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建描边蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)

            outer_radius = corner_radius if corner_radius > 0 else 0
            draw.rounded_rectangle((0, 0, width-1, height-1), radius=outer_radius, fill=255)

            inner_radius = max(0, corner_radius - stroke_width) if corner_radius > 0 else 0
            if stroke_width * 2 < width and stroke_width * 2 < height:
                draw.rounded_rectangle(
                    (stroke_width, stroke_width, width - stroke_width - 1, height - stroke_width - 1),
                    radius=inner_radius, fill=0
                )

            return mask

    def _create_content_mask(self, width, height, stroke_width, inner_radius):
        """创建内容区域的高质量蒙版"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = stroke_width * scale
            large_radius = inner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 绘制内容区域
            draw.rounded_rectangle(
                (int(large_stroke), int(large_stroke),
                 large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                radius=int(large_radius),
                fill=255
            )

            # 缩放回原始尺寸
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建内容蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle(
                (stroke_width, stroke_width, width - stroke_width - 1, height - stroke_width - 1),
                radius=inner_radius, fill=255
            )
            return mask

    def _create_center_stroke_mask(self, width, height, inner_stroke, corner_radius):
        """创建居中描边的高质量蒙版"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = inner_stroke * scale
            large_radius = corner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 外层边界（描边外边缘）
            outer_radius = large_radius + large_stroke if large_radius > 0 else large_stroke
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=int(outer_radius),
                fill=255
            )

            # 内层边界（描边内边缘）
            inner_radius = max(0, large_radius - large_stroke) if large_radius > 0 else 0

            if large_stroke * 2 < large_width and large_stroke * 2 < large_height:
                draw.rounded_rectangle(
                    (int(large_stroke), int(large_stroke),
                     large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                    radius=int(inner_radius),
                    fill=0
                )

            # 缩放回原始尺寸
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建居中描边蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)

            outer_radius = corner_radius + inner_stroke if corner_radius > 0 else inner_stroke
            draw.rounded_rectangle((0, 0, width-1, height-1), radius=outer_radius, fill=255)

            inner_radius = max(0, corner_radius - inner_stroke) if corner_radius > 0 else 0
            if inner_stroke * 2 < width and inner_stroke * 2 < height:
                draw.rounded_rectangle(
                    (inner_stroke, inner_stroke, width - inner_stroke - 1, height - inner_stroke - 1),
                    radius=inner_radius, fill=0
                )

            return mask

    def _create_outer_stroke_mask(self, width, height, stroke_width, corner_radius):
        """创建外描边的高质量蒙版"""
        try:
            # 使用超采样创建平滑蒙版
            scale = 4
            large_width = width * scale
            large_height = height * scale
            large_stroke = stroke_width * scale
            large_radius = corner_radius * scale

            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)

            # 外层边界（描边外边缘）
            outer_radius = large_radius + large_stroke if large_radius > 0 else large_stroke
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=int(outer_radius),
                fill=255
            )

            # 内层边界（原图像边缘）
            inner_radius = large_radius if large_radius > 0 else 0
            draw.rounded_rectangle(
                (int(large_stroke), int(large_stroke),
                 large_width - int(large_stroke) - 1, large_height - int(large_stroke) - 1),
                radius=int(inner_radius),
                fill=0
            )

            # 缩放回原始尺寸
            mask = large_mask.resize((width, height), Resampling.LANCZOS)

            return mask

        except Exception as e:
            print(f"创建外描边蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)

            outer_radius = corner_radius + stroke_width if corner_radius > 0 else stroke_width
            draw.rounded_rectangle((0, 0, width-1, height-1), radius=outer_radius, fill=255)

            inner_radius = corner_radius if corner_radius > 0 else 0
            draw.rounded_rectangle(
                (stroke_width, stroke_width, width - stroke_width - 1, height - stroke_width - 1),
                radius=inner_radius, fill=0
            )

            return mask

    def _safe_alpha_composite(self, base, overlay):
        """安全的alpha合成，避免黑色边缘问题 - 使用高质量修复器"""
        try:
            # 🔧 修复：使用高质量修复器进行合成，解决深色边缘问题
            from app.utils.image_quality_fixer import get_image_quality_fixer
            quality_fixer = get_image_quality_fixer()
            
            result = quality_fixer.composite_with_quality(
                background=base,
                foreground=overlay,
                position=(0, 0),
                opacity=1.0,
                fix_edges=True,
                enhance_aa=True
            )
            
            print(f"[图层效果] 使用高质量安全合成")
            return result
            
        except Exception as quality_e:
            print(f"高质量安全合成失败: {quality_e}，使用传统方法")
            # 降级到传统方法
            try:
                # 确保两个图像都是RGBA模式
                if base.mode != 'RGBA':
                    base = base.convert('RGBA')
                if overlay.mode != 'RGBA':
                    overlay = overlay.convert('RGBA')

                # 使用PIL的paste方法进行合成，这样可以更好地处理透明度
                result = base.copy()
                result.paste(overlay, (0, 0), overlay)

                return result

            except Exception as e:
                print(f"安全alpha合成失败，回退到标准方法: {e}")
                return Image.alpha_composite(base, overlay)

