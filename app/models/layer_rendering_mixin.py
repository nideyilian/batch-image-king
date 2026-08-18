#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
"""Layer 子 mixin 5: 渲染管线（_apply_effects + 描边 + 形状 + 蒙版 + 颜色/渐变 + resize/rotate 工具）

从原 layer_new.py 拆分。涵盖：
- 入口：apply_effects + _apply_effects（3 阶段可缓存渲染管线）
- 缓存：_build_effects_stage_cache_key + _get/_set_effects_stage_cache
- 描边：_apply_inner_stroke / _apply_center_stroke / _apply_outer_stroke
- 蒙版辅助：_create_antialiased_rounded_rect_mask / _create_antialiased_rounded_ring_mask
            / _create_optimized_corner_mask / _get_mask_supersample_scale
            / _create_stroke_mask / _create_center_stroke_mask / _create_outer_stroke_mask
- 形状：_apply_shape_mask + _create_shape_mask + _draw_right_trapezoid + _draw_circle
        + _draw_regular_polygon + _apply_polygon_corner_radius
- 通用：_apply_corner_radius_improved + _apply_mask_to_image + _create_error_image
- 颜色/渐变叠加：_apply_color_overlay / _apply_gradient_overlay / _create_linear_gradient
- 边缘处理：_bleed_transparent_edges
- 工具：_resize_rgba_premultiplied / _rotate_rgba_premultiplied
"""

import os
import hashlib
import logging
from collections import OrderedDict
from typing import List

from PIL import Image, ImageDraw, ImageFilter, ImageChops
from PIL.Image import Resampling

import numpy as np

from app.models.layer_properties import ShapeType
from app.utils.render_diagnostics import log_branch, log_sampling

logger = logging.getLogger(__name__)

# 模块级 verbose flag（与 layer_attrs_mixin/layer_transform_mixin 共享）
_LAYER_RENDER_VERBOSE = os.environ.get("BTPW_LAYER_RENDER_VERBOSE", "0") == "1"


class LayerRenderingMixin:
    """渲染管线（拆分自 Layer）。"""

    # ==================== 入口 ====================
    def apply_effects(self, image):
        """应用图层特效的公共方法"""
        return self._apply_effects(image)

    def _apply_effects(self, image):
        """应用图层特效（圆角、描边、形状等）和变换（旋转、翻转）"""
        if image is None:
            return None
        self._render_offset_x = 0
        self._render_offset_y = 0

        if _LAYER_RENDER_VERBOSE:
            print(f"应用特效前图像尺寸: {image.width}x{image.height}, 图层尺寸: {self.width}x{self.height}")

        # 如果图像尺寸与图层尺寸不匹配，根据模式处理
        fit_mode = int(getattr(self, 'fit_mode', 0))
        if image.width != self.width or image.height != self.height:
            if fit_mode == 2:
                # 等比缩放不裁剪模式：保持原图尺寸，继续应用特效
                if _LAYER_RENDER_VERBOSE:
                    print(f"等比缩放不裁剪模式：保持图像尺寸不变 {image.width}x{image.height}，继续应用圆角/描边")
            elif fit_mode == 1:
                image = self._center_image_on_layer_canvas(image, self.width, self.height)
            else:
                if _LAYER_RENDER_VERBOSE:
                    print(f"警告：图像尺寸与图层尺寸不匹配，调整图像大小: {image.width}x{image.height} => {self.width}x{self.height}")
                image = self._resize_rgba_premultiplied(image, (self.width, self.height), Resampling.BICUBIC)

        stroke_enabled = self.stroke_enabled and self.stroke_width > 0
        use_vector_pipeline = self._use_rectangle_vector_pipeline(stroke_enabled)
        log_branch(
            "layer_new._apply_effects",
            "enter",
            shape_type=getattr(getattr(self, 'shape_type', None), 'value', getattr(self, 'shape_type', 'unknown')),
            corner_radius=self.corner_radius,
            stroke_enabled=stroke_enabled,
            stroke_type=getattr(self, 'stroke_type', -1),
            stroke_width=getattr(self, 'stroke_width', 0),
            vector_pipeline=use_vector_pipeline,
        )

        # 阶段1：几何与变换（可缓存）
        stage1_extra_parts = [
            f"shape:{getattr(getattr(self, 'shape_type', ''), 'value', getattr(self, 'shape_type', ''))}",
            f"corner:{int(getattr(self, 'corner_radius', 0))}",
            f"vcorner:{int(self.vector_corner_radius_tl)}:{int(self.vector_corner_radius_tr)}:"
            f"{int(self.vector_corner_radius_br)}:{int(self.vector_corner_radius_bl)}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"vpath_on:{int(bool(self.vector_path_enabled))}",
            f"vpath_pts:{str(self.vector_path_points)}",
            f"vpath_mode:{str(self.vector_path_mode)}",
            f"vpath_bezier:{str(self.vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self.vector_path_closed))}",
            f"vpath_link:{str(self.vector_handle_link_mode)}",
            f"trap:{getattr(self, 'trapezoid_top_width', '')},{getattr(self, 'trapezoid_bottom_width', '')},{getattr(self, 'trapezoid_slope_side', '')}",
            f"poly:{getattr(self, 'polygon_rotation', '')},{getattr(self, 'polygon_corner_radius', '')}",
        ]
        stage1_key = self._build_effects_stage_cache_key("geometry", image, stage1_extra_parts)
        result = self._get_effects_stage_cache(stage1_key)
        if result is None:
            result = (image.convert('RGBA') if image.mode != 'RGBA' else image.copy())
            if (self.shape_type != ShapeType.RECTANGLE) and (not use_vector_pipeline):
                result = self._apply_shape_mask(result)
            result = self._apply_transformations(result)
            # 矩形图层若走矢量几何管线，圆角/路径裁剪统一在阶段3处理，避免位图圆角遮罩
            if (
                self.corner_radius > 0
                and self.shape_type == ShapeType.RECTANGLE
                and not stroke_enabled
                and not use_vector_pipeline
            ):
                log_branch("layer_new._apply_effects", "corner_only")
                result = self._apply_corner_radius_improved(result)
            self._set_effects_stage_cache(stage1_key, result)

        # 阶段2：叠加样式（可缓存）
        stage2_extra_parts = [
            f"base:{stage1_key}",
            f"overlay_on:{int(bool(getattr(self, 'color_overlay_enabled', False)))}",
            f"overlay_c:{str(getattr(self, 'color_overlay_color', (255, 255, 255, 255)))}",
            f"overlay_op:{float(getattr(self, 'color_overlay_opacity', 1.0)):.4f}",
            f"grad_on:{int(bool(getattr(self, 'gradient_overlay_enabled', False)))}",
            f"grad_angle:{float(getattr(self, 'gradient_overlay_angle', 0.0)):.3f}",
            f"grad_op:{float(getattr(self, 'gradient_overlay_opacity', 1.0)):.4f}",
            f"grad_colors:{str(getattr(self, 'gradient_overlay_colors', []))}",
        ]
        stage2_key = self._build_effects_stage_cache_key("overlay", image, stage2_extra_parts)
        overlay_result = self._get_effects_stage_cache(stage2_key)
        if overlay_result is None:
            overlay_result = result.copy()
            if self.color_overlay_enabled:
                overlay_result = self._apply_color_overlay(overlay_result)
            if self.gradient_overlay_enabled:
                overlay_result = self._apply_gradient_overlay(overlay_result)
            self._set_effects_stage_cache(stage2_key, overlay_result)
        result = overlay_result

        # 阶段3：描边与最终收敛（可缓存）
        stage3_extra_parts = [
            "vec_pipe_ver:v5",
            f"base:{stage2_key}",
            f"stroke_on:{int(bool(stroke_enabled))}",
            f"stroke_type:{int(getattr(self, 'stroke_type', 0))}",
            f"stroke_w:{int(getattr(self, 'stroke_width', 0))}",
            f"stroke_c:{str(getattr(self, 'stroke_color', (0, 0, 0, 255)))}",
            f"stroke_join:{str(getattr(self, 'stroke_join', 'miter'))}",
            f"stroke_cap:{str(getattr(self, 'stroke_cap', 'butt'))}",
            f"dash_len:{int(getattr(self, 'stroke_dash_length', 0))}",
            f"dash_gap:{int(getattr(self, 'stroke_dash_gap', 0))}",
            f"shape:{getattr(getattr(self, 'shape_type', ''), 'value', getattr(self, 'shape_type', ''))}",
            f"corner:{int(getattr(self, 'corner_radius', 0))}",
            f"vcorner:{int(self.vector_corner_radius_tl)}:{int(self.vector_corner_radius_tr)}:"
            f"{int(self.vector_corner_radius_br)}:{int(self.vector_corner_radius_bl)}",
            f"vpath_on:{int(bool(self.vector_path_enabled))}",
            f"vpath_pts:{str(self.vector_path_points)}",
            f"vpath_mode:{str(self.vector_path_mode)}",
            f"vpath_bezier:{str(self.vector_bezier_nodes)}",
            f"vpath_closed:{int(bool(self.vector_path_closed))}",
            f"vpath_link:{str(self.vector_handle_link_mode)}",
            f"vec_pipe:{int(bool(use_vector_pipeline))}",
            f"out_size:{int(getattr(self, 'width', 0))}x{int(getattr(self, 'height', 0))}",
        ]
        stage3_key = self._build_effects_stage_cache_key("stroke_finalize", image, stage3_extra_parts)
        final_result = self._get_effects_stage_cache(stage3_key)
        if final_result is None:
            final_result = result.copy()
            if use_vector_pipeline:
                from app.utils.vector_layer_effects import (
                    VectorEffectParams,
                    alpha_composite_layers,
                    apply_vector_path_effects,
                )

                params = VectorEffectParams.collect(self)
                params.stroke_enabled = bool(stroke_enabled)
                final_result = apply_vector_path_effects(
                    final_result, params, alpha_composite=alpha_composite_layers
                )
                self._render_offset_x = int(final_result.info.get("vector_offset_x", 0))
                self._render_offset_y = int(final_result.info.get("vector_offset_y", 0))
            elif stroke_enabled:
                if self.stroke_type == 0:  # 内描边
                    log_branch("layer_new._apply_effects", "stroke_inner")
                    final_result = self._apply_inner_stroke(final_result)
                elif self.stroke_type == 1:  # 居中描边
                    log_branch("layer_new._apply_effects", "stroke_center")
                    final_result = self._apply_center_stroke(final_result)
                elif self.stroke_type == 2:  # 外描边
                    log_branch("layer_new._apply_effects", "stroke_outer")
                    final_result = self._apply_outer_stroke(final_result)

            # 非矢量管线才强制收敛到图层尺寸；矢量管线允许外扩（居中/外描边）
            # 关键修复：fit_mode==2 (智能适配不缩放) 的图层保留原图比例，绝对不能在此
            # 强制 resize 到 self.width/self.height，否则会把等比素材拉成图层宽高比。
            # fit_mode==0/1 在 _process_image 已经处理过尺寸，理论上尺寸与图层一致；
            # fit_mode==3 (else 拉伸) 是用户显式选择拉伸，按既有行为处理。
            if (not use_vector_pipeline) and (int(getattr(self, 'fit_mode', 0)) not in (1, 2)) \
                    and (final_result.width != self.width or final_result.height != self.height):
                final_result = self._resize_rgba_premultiplied(final_result, (self.width, self.height), Resampling.LANCZOS)

            # 边缘优化：在最终合成前进行一次透明边缘颜色出血，避免白/黑晕
            # 注意：该步骤会创建新图像对象，需保留矢量外扩偏移元数据（vector_offset_x/y），
            # 否则居中/外描边会在画布合成时丢失负偏移，表现为内容相对形状“右下偏移”。
            vector_offset_x = int(getattr(final_result, 'info', {}).get('vector_offset_x', 0))
            vector_offset_y = int(getattr(final_result, 'info', {}).get('vector_offset_y', 0))
            try:
                final_result = self._bleed_transparent_edges(final_result)
                final_result.info["vector_offset_x"] = vector_offset_x
                final_result.info["vector_offset_y"] = vector_offset_y
            except Exception:
                logger.warning("静默异常已忽略: except Exception: in layer_new.py", exc_info=True)
                pass
            self._set_effects_stage_cache(stage3_key, final_result)

        self._render_offset_x = int(getattr(final_result, 'info', {}).get('vector_offset_x', 0))
        self._render_offset_y = int(getattr(final_result, 'info', {}).get('vector_offset_y', 0))
        if _LAYER_RENDER_VERBOSE:
            print(f"应用特效后图像尺寸: {final_result.width}x{final_result.height}, 图层尺寸: {self.width}x{self.height}")
        return final_result

    # ==================== 缓存（类级）====================
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
            image = self._resize_rgba_premultiplied(image, new_size, Resampling.LANCZOS)
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
            f"path:{getattr(self, 'current_image_path', '') or ''}",
            f"src:{getattr(self, 'image_source', '') or ''}",
            f"img:{getattr(image, 'width', 0)}x{getattr(image, 'height', 0)}:{getattr(image, 'mode', '')}",
            f"layer:{getattr(self, 'width', 0)}x{getattr(self, 'height', 0)}",
            f"fit:{getattr(self, 'fit_mode', 0)}",
            f"crop:{getattr(self, 'crop_direction', 0)}",
            f"use_orig:{int(bool(getattr(self, 'use_original_size', False)))}",
            f"rot:{float(getattr(self, 'rotation', 0.0)):.3f}",
            f"flip_h:{int(bool(getattr(self, 'flip_horizontal', False)))}",
            f"flip_v:{int(bool(getattr(self, 'flip_vertical', False)))}",
            f"rnd_scale:{float(getattr(self, '_current_random_scale', 1.0)):.6f}",
            f"rnd_rot:{float(getattr(self, '_current_random_rotation', 0.0)):.3f}",
        ]
        source_parts.extend(extra_parts)
        return hashlib.md5("|".join([str(p) for p in source_parts]).encode('utf-8')).hexdigest()

    # ==================== 圆角 / 描边 ====================
    def _apply_corner_radius_improved(self, image):
        try:
            radius = max(0, min(int(self.corner_radius), min(image.width, image.height) // 2))
            if radius <= 0:
                return image
            mask = self._create_antialiased_rounded_rect_mask(image.width, image.height, radius)
            return self._apply_mask_to_image(image, mask)
        except Exception as e:
            print(f"应用圆角时出错: {e}")
            return image

    def _get_mask_supersample_scale(self, width, height, edge_size=0):
        """根据图层尺寸与边缘复杂度动态选择超采样倍数。"""
        min_side = max(1, min(int(width), int(height)))
        edge_size = max(0, int(edge_size))

        # 边缘质量优先：避免在大图层上降到2x导致圆角/描边内线台阶
        if min_side <= 256:
            scale = 8
        elif min_side <= 1024:
            scale = 7
        elif min_side <= 2048:
            scale = 6
        else:
            scale = 5

        # 小圆角/细描边对采样更敏感，提升采样倍数
        if edge_size <= 4:
            scale = max(scale, 8 if min_side <= 1024 else 6)
        elif edge_size <= 10:
            scale = max(scale, 7 if min_side <= 1024 else 6)

        log_sampling("layer_new.mask_scale", width, height, edge_size, scale)
        return scale

    def _create_antialiased_rounded_rect_mask(self, width, height, radius):
        """使用超采样生成高质量圆角矩形蒙版。"""
        width = max(1, int(width))
        height = max(1, int(height))
        radius = max(0, min(int(radius), min(width, height) // 2))

        if radius <= 0:
            return Image.new('L', (width, height), 255)

        scale = self._get_mask_supersample_scale(width, height, radius)
        large_size = (width * scale, height * scale)
        large_radius = radius * scale

        large_mask = Image.new('L', large_size, 0)
        draw = ImageDraw.Draw(large_mask)
        draw.rounded_rectangle(
            (0, 0, large_size[0] - 1, large_size[1] - 1),
            radius=large_radius,
            fill=255
        )

        return large_mask.resize((width, height), Resampling.LANCZOS)

    def _create_antialiased_rounded_ring_mask(self, width, height, outer_radius, inset, inner_radius):
        """使用超采样生成高质量圆角环带蒙版（用于描边）。"""
        width = max(1, int(width))
        height = max(1, int(height))
        inset = max(0, int(inset))
        outer_radius = max(0, min(int(outer_radius), min(width, height) // 2))
        inner_radius = max(0, min(int(inner_radius), min(width, height) // 2))

        scale = self._get_mask_supersample_scale(width, height, max(outer_radius, inset))
        large_width = width * scale
        large_height = height * scale

        large_mask = Image.new('L', (large_width, large_height), 0)
        draw = ImageDraw.Draw(large_mask)

        draw.rounded_rectangle(
            (0, 0, large_width - 1, large_height - 1),
            radius=outer_radius * scale,
            fill=255
        )

        if inset > 0 and inset * 2 < width and inset * 2 < height:
            large_inset = inset * scale
            draw.rounded_rectangle(
                (
                    large_inset,
                    large_inset,
                    large_width - large_inset - 1,
                    large_height - large_inset - 1
                ),
                radius=inner_radius * scale,
                fill=0
            )

        return large_mask.resize((width, height), Resampling.LANCZOS)

    def _create_optimized_corner_mask(self, width, height, radius):
        """创建优化的圆角蒙版"""
        try:
            return self._create_antialiased_rounded_rect_mask(width, height, radius)

        except Exception as e:
            print(f"创建圆角蒙版时出错: {e}")
            # 回退到简单蒙版
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            return mask

    def _apply_inner_stroke(self, image):
        """应用内向描边效果"""
        if image is None or self.stroke_width <= 0:
            return image

        try:
            # 保持原始图层尺寸
            result_width = self.width
            result_height = self.height

            # 创建描边蒙版
            stroke_width = min(self.stroke_width, min(result_width, result_height) // 4)
            stroke_mask = self._create_stroke_mask(result_width, result_height, stroke_width, self.corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self.stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 合成
            result = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
            result = Image.alpha_composite(result, stroke_layer)

            # 缩放原图像以适应内容区域
            if stroke_width * 2 < result_width and stroke_width * 2 < result_height:
                content_width = result_width - stroke_width * 2
                content_height = result_height - stroke_width * 2
                scaled_image = self._resize_rgba_premultiplied(image, (content_width, content_height), Resampling.LANCZOS)

                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (stroke_width, stroke_width), scaled_image)

                if self.shape_type == ShapeType.RECTANGLE:
                    inner_radius = max(0, self.corner_radius - stroke_width) if self.corner_radius > 0 else 0
                    content_mask = self._create_antialiased_rounded_rect_mask(content_width, content_height, inner_radius)
                    alpha_canvas = Image.new('L', (result_width, result_height), 0)
                    alpha_canvas.paste(content_mask, (stroke_width, stroke_width))
                    content_layer = self._apply_mask_to_image(content_layer, alpha_canvas)

                # 合成内容
                result = Image.alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用内向描边效果时出错: {e}")
            return image

    def _create_stroke_mask(self, width, height, stroke_width, corner_radius):
        """创建描边蒙版（内描边）"""
        try:
            # 非矩形形状使用形状蒙版的形态学腐蚀生成等宽描边
            if self.shape_type != ShapeType.RECTANGLE:
                base = self._create_shape_mask(width, height)
                k = max(3, stroke_width * 2 + 1)
                inner = base.filter(ImageFilter.MinFilter(k))
                stroke = ImageChops.subtract(base, inner)
                return stroke

            # 矩形继续使用圆角优化路径
            outer_radius = corner_radius if corner_radius > 0 else 0
            inner_radius = max(0, corner_radius - stroke_width) if corner_radius > 0 else 0
            return self._create_antialiased_rounded_ring_mask(
                width=width,
                height=height,
                outer_radius=outer_radius,
                inset=stroke_width,
                inner_radius=inner_radius
            )
        except Exception as e:
            print(f"创建描边蒙版时出错: {e}")
            return Image.new('L', (width, height), 255)

    def _apply_center_stroke(self, image):
        """应用居中描边效果"""
        if image is None or self.stroke_width <= 0:
            return image

        try:
            result_width = self.width
            result_height = self.height

            # 居中描边：一半向内，一半向外
            half_stroke = self.stroke_width / 2.0
            inner_stroke = int(half_stroke)

            # 创建居中描边蒙版
            stroke_mask = self._create_center_stroke_mask(result_width, result_height, inner_stroke, self.corner_radius)

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), self.stroke_color)
            stroke_layer.putalpha(stroke_mask)

            # 合成
            result = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
            result = Image.alpha_composite(result, stroke_layer)

            # 缩放原图像以适应内容区域
            if inner_stroke * 2 < result_width and inner_stroke * 2 < result_height:
                content_width = result_width - inner_stroke * 2
                content_height = result_height - inner_stroke * 2
                scaled_image = self._resize_rgba_premultiplied(image, (content_width, content_height), Resampling.LANCZOS)

                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (inner_stroke, inner_stroke), scaled_image)

                if self.shape_type == ShapeType.RECTANGLE:
                    inner_radius = max(0, self.corner_radius - inner_stroke) if self.corner_radius > 0 else 0
                    content_mask = self._create_antialiased_rounded_rect_mask(content_width, content_height, inner_radius)
                    alpha_canvas = Image.new('L', (result_width, result_height), 0)
                    alpha_canvas.paste(content_mask, (inner_stroke, inner_stroke))
                    content_layer = self._apply_mask_to_image(content_layer, alpha_canvas)

                # 合成内容
                result = Image.alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用居中描边效果时出错: {e}")
            return image

    def _create_center_stroke_mask(self, width, height, inner_stroke, corner_radius):
        try:
            if self.shape_type != ShapeType.RECTANGLE:
                base = self._create_shape_mask(width, height)
                k = max(3, inner_stroke * 2 + 1)
                inner = base.filter(ImageFilter.MinFilter(k))
                outer = base.filter(ImageFilter.MaxFilter(k))
                return ImageChops.subtract(outer, inner)
            # 矩形优化
            outer_radius = corner_radius + inner_stroke if corner_radius > 0 else inner_stroke
            inner_radius = corner_radius if corner_radius > 0 else 0
            return self._create_antialiased_rounded_ring_mask(
                width=width,
                height=height,
                outer_radius=outer_radius,
                inset=inner_stroke,
                inner_radius=inner_radius
            )
        except Exception as e:
            print(f"创建居中描边蒙版时出错: {e}")
            return Image.new('L', (width, height), 255)

    def _apply_outer_stroke(self, image):
        """应用外向描边效果"""
        if image is None or self.stroke_width <= 0:
            return image

        try:
            result_width = self.width
            result_height = self.height
            stroke_width = self.stroke_width

            # 外描边需要画布外扩
            outer_width = result_width + stroke_width * 2
            outer_height = result_height + stroke_width * 2

            stroke_mask = self._create_outer_stroke_mask(outer_width, outer_height, stroke_width, self.corner_radius)

            stroke_layer = Image.new('RGBA', (outer_width, outer_height), self.stroke_color)
            stroke_layer.putalpha(stroke_mask)

            result = Image.new('RGBA', (outer_width, outer_height), (0, 0, 0, 0))
            result = Image.alpha_composite(result, stroke_layer)

            # 原图放到中央
            if result_width > 0 and result_height > 0:
                scaled_image = self._resize_rgba_premultiplied(image, (result_width, result_height), Resampling.LANCZOS)
                content_layer = Image.new('RGBA', (outer_width, outer_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (stroke_width, stroke_width), scaled_image)
                if self.shape_type == ShapeType.RECTANGLE:
                    content_mask = self._create_antialiased_rounded_rect_mask(result_width, result_height, self.corner_radius)
                    alpha_canvas = Image.new('L', (outer_width, outer_height), 0)
                    alpha_canvas.paste(content_mask, (stroke_width, stroke_width))
                    content_layer = self._apply_mask_to_image(content_layer, alpha_canvas)
                result = Image.alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用外向描边效果时出错: {e}")
            return image

    def _create_outer_stroke_mask(self, width, height, stroke_width, corner_radius):
        try:
            if self.shape_type != ShapeType.RECTANGLE:
                base = self._create_shape_mask(width, height)
                k = max(3, stroke_width * 2 + 1)
                dilated = base.filter(ImageFilter.MaxFilter(k))
                stroke = ImageChops.subtract(dilated, base)
                return stroke

            # 矩形继续原逻辑
            outer_radius = corner_radius + stroke_width if corner_radius > 0 else stroke_width
            inner_radius = corner_radius if corner_radius > 0 else 0
            return self._create_antialiased_rounded_ring_mask(
                width=width,
                height=height,
                outer_radius=outer_radius,
                inset=stroke_width,
                inner_radius=inner_radius
            )
        except Exception as e:
            print(f"创建外描边蒙版时出错: {e}")
            return Image.new('L', (width, height), 255)

    def _create_error_image(self):
        """创建错误图像（红色底色）"""
        return Image.new('RGBA', (self.width, self.height), (255, 0, 0, 128))

    # ==================== 形状蒙版 ====================
    def _apply_shape_mask(self, image):
        """应用形状蒙版到图像"""
        if image is None:
            return None

        # 创建形状蒙版
        shape_mask = self._create_shape_mask(image.width, image.height)

        # 应用蒙版
        return self._apply_mask_to_image(image, shape_mask)

    def _create_shape_mask(self, width, height):
        """创建形状蒙版 - 带缓存优化"""
        # 创建缓存键，包含所有影响形状的属性
        cache_key = (
            width, height, self.shape_type.value,
            self.corner_radius, self.trapezoid_top_width, self.trapezoid_bottom_width,
            self.trapezoid_slope_side, self.polygon_rotation, self.polygon_corner_radius
        )

        # 检查缓存
        if not hasattr(self, '_shape_mask_cache'):
            self._shape_mask_cache = {}

        if cache_key in self._shape_mask_cache:
            return self._shape_mask_cache[cache_key].copy()

        # 创建透明蒙版
        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)

        shape_type = self.shape_type

        if shape_type == ShapeType.RECTANGLE:
            # 矩形 - 使用传统圆角处理
            if self.corner_radius > 0:
                radius = min(self.corner_radius, min(width, height) // 2)
                draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            else:
                draw.rectangle((0, 0, width-1, height-1), fill=255)

        elif shape_type == ShapeType.RIGHT_TRAPEZOID:
            # 直角梯形
            self._draw_right_trapezoid(draw, width, height)

        elif shape_type == ShapeType.CIRCLE:
            # 圆形
            self._draw_circle(draw, width, height)

        elif shape_type == ShapeType.PENTAGON:
            # 正五边形
            self._draw_regular_polygon(draw, width, height, 5)

        elif shape_type == ShapeType.HEXAGON:
            # 正六边形
            self._draw_regular_polygon(draw, width, height, 6)

        # 缓存结果
        self._shape_mask_cache[cache_key] = mask.copy()
        return mask

    def _draw_right_trapezoid(self, draw, width, height):
        """绘制直角梯形"""
        # 将百分比转换为实际像素值
        top_width_pixels = int(width * self.trapezoid_top_width / 100)
        bottom_width_pixels = int(width * self.trapezoid_bottom_width / 100)

        # 确保宽度不超过画布宽度
        top_width = min(top_width_pixels, width)
        bottom_width = min(bottom_width_pixels, width)

        # 计算梯形各顶点坐标
        if self.trapezoid_slope_side == "right":
            # 斜边在右侧
            points = [
                (0, 0),  # 左上
                (top_width, 0),  # 右上
                (bottom_width, height),  # 右下
                (0, height)  # 左下
            ]
        else:
            # 斜边在左侧
            points = [
                (width - top_width, 0),  # 左上
                (width, 0),  # 右上
                (width, height),  # 右下
                (width - bottom_width, height)  # 左下
            ]

        draw.polygon(points, fill=255)

    def _draw_circle(self, draw, width, height):
        """绘制圆形"""
        # 确保圆形在边界内，留一点边距
        margin = 2
        diameter = min(width, height) - margin * 2
        center_x = width // 2
        center_y = height // 2
        radius = diameter // 2

        # 绘制圆形
        bbox = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)
        draw.ellipse(bbox, fill=255)

        # 如果有多边形圆角设置，应用轻微的内圆角
        if self.polygon_corner_radius > 0:
            self._apply_polygon_corner_radius(draw, width, height, [(center_x, center_y)], radius)

    def _draw_regular_polygon(self, draw, width, height, sides):
        """绘制正多边形"""
        import math

        center_x = width // 2
        center_y = height // 2

        # 计算内切圆半径（确保多边形在边界内）
        margin = 5
        max_radius = min(width, height) // 2 - margin

        # 生成多边形顶点
        points = []
        for i in range(sides):
            angle = 2 * math.pi * i / sides + math.radians(self.polygon_rotation)
            x = center_x + max_radius * math.cos(angle - math.pi / 2)  # -pi/2让顶点朝上
            y = center_y + max_radius * math.sin(angle - math.pi / 2)
            points.append((int(x), int(y)))

        # 绘制多边形
        draw.polygon(points, fill=255)

        # 应用多边形圆角
        if self.polygon_corner_radius > 0:
            self._apply_polygon_corner_radius(draw, width, height, points, max_radius)

    def _apply_polygon_corner_radius(self, draw, width, height, vertices, max_radius):
        """应用多边形圆角效果"""
        if self.polygon_corner_radius <= 0 or len(vertices) < 3:
            return

        # 限制圆角半径
        corner_radius = min(self.polygon_corner_radius, max_radius // 4)

        # 在顶点处绘制小圆角
        for i, (x, y) in enumerate(vertices):
            next_i = (i + 1) % len(vertices)
            prev_i = (i - 1) % len(vertices)

            # 计算顶点处的圆角
            prev_vertex = vertices[prev_i]
            next_vertex = vertices[next_i]

            # 绘制小圆角
            small_radius = min(corner_radius, 5)  # 限制小圆角大小
            draw.ellipse((x - small_radius, y - small_radius,
                          x + small_radius, y + small_radius), fill=255)

    def _apply_mask_to_image(self, image, mask):
        if image is None or mask is None:
            return image
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        r, g, b, a = image.split()
        new_alpha = ImageChops.multiply(a, mask)
        return Image.merge('RGBA', (r, g, b, new_alpha))

    # ==================== 颜色/渐变叠加 ====================
    def _apply_color_overlay(self, image):
        """应用颜色叠加"""
        if image is None or not self.color_overlay_enabled or self.color_overlay_opacity <= 0:
            return image

        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # 获取颜色
            color = self.color_overlay_color
            if not isinstance(color, (list, tuple)):
                return image

            # 处理颜色格式
            if len(color) == 3:
                r, g, b = color
                a = 255
            elif len(color) >= 4:
                r, g, b, a = color[:4]
            else:
                return image

            # 创建纯色层
            overlay = Image.new('RGBA', image.size, (int(r), int(g), int(b), int(a)))

            # 使用原图的alpha通道作为蒙版
            orig_r, orig_g, orig_b, orig_a = image.split()
            overlay.putalpha(orig_a)

            # 混合
            return Image.blend(image, overlay, self.color_overlay_opacity)

        except Exception as e:
            print(f"应用颜色叠加出错: {e}")
            return image

    def _apply_gradient_overlay(self, image):
        """应用渐变叠加"""
        if image is None or not self.gradient_overlay_enabled or self.gradient_overlay_opacity <= 0:
            return image

        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # 创建渐变层
            gradient = self._create_linear_gradient(
                image.width,
                image.height,
                self.gradient_overlay_colors,
                self.gradient_overlay_angle
            )

            if gradient is None:
                return image

            # 使用原图的alpha通道作为蒙版
            orig_r, orig_g, orig_b, orig_a = image.split()

            # 确保gradient有alpha通道
            if gradient.mode != 'RGBA':
                gradient = gradient.convert('RGBA')

            grad_r, grad_g, grad_b, grad_a = gradient.split()

            # 组合alpha
            new_alpha = ImageChops.multiply(orig_a, grad_a)

            gradient.putalpha(new_alpha)

            # 混合
            return Image.blend(image, gradient, self.gradient_overlay_opacity)

        except Exception as e:
            print(f"应用渐变叠加出错: {e}")
            return image

    def _create_linear_gradient(self, width, height, colors, angle):
        """创建线性渐变图像"""
        try:
            import math

            if not colors or len(colors) < 2:
                # 默认黑白
                colors = [(0, 0, 0, 255), (255, 255, 255, 255)]

            # 计算角度
            rad = math.radians(angle)
            dx = math.cos(rad)
            dy = -math.sin(rad)  # PIL坐标系Y轴向下

            # 中心点
            cx, cy = width / 2, height / 2

            # 计算投影范围
            corners = [
                (0, 0), (width, 0), (0, height), (width, height)
            ]
            projections = [x * dx + y * dy for x, y in corners]
            min_p = min(projections)
            max_p = max(projections)
            range_p = max_p - min_p
            if range_p == 0: range_p = 1

            # 生成网格
            x = np.arange(width)
            y = np.arange(height)
            xv, yv = np.meshgrid(x, y)

            # 计算投影并归一化
            p = xv * dx + yv * dy
            t = (p - min_p) / range_p
            t = np.clip(t, 0, 1)

            # 颜色插值
            num_stops = len(colors)

            if num_stops == 2:
                c1 = np.array(colors[0])
                c2 = np.array(colors[1])

                t_exp = t[:, :, np.newaxis]
                res = c1 * (1 - t_exp) + c2 * t_exp
                rgba = res.astype(np.uint8)
            else:
                # 简单处理多色：均匀分布
                scaled_t = t * (num_stops - 1)
                indices = np.floor(scaled_t).astype(int)
                indices = np.clip(indices, 0, num_stops - 2)

                local_t = scaled_t - indices
                local_t_exp = local_t[:, :, np.newaxis]

                # 准备颜色数组
                colors_arr = np.array(colors)
                c_start = colors_arr[indices]
                c_end = colors_arr[indices + 1]

                res = c_start * (1 - local_t_exp) + c_end * local_t_exp
                rgba = res.astype(np.uint8)

            return Image.fromarray(rgba)

        except Exception as e:
            print(f"创建渐变出错: {e}")
            return None

    # ==================== 边缘处理 / Resize 工具 ====================
    def _bleed_transparent_edges(self, image: 'Image.Image') -> 'Image.Image':
        """将不透明区域的颜色向半透明边缘传播，避免白/黑边缘晕圈"""
        original_info = dict(getattr(image, "info", {}) or {})
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        arr = np.array(image, dtype=np.float32) / 255.0
        rgb = arr[:, :, :3]
        a = arr[:, :, 3:4]
        premul = rgb * a

        # 将各通道转换为图像以使用MaxFilter
        r_img = Image.fromarray((premul[:, :, 0] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))
        g_img = Image.fromarray((premul[:, :, 1] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))
        b_img = Image.fromarray((premul[:, :, 2] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))
        a_img = Image.fromarray((a[:, :, 0] * 255.0).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))

        r2 = np.array(r_img, dtype=np.float32) / 255.0
        g2 = np.array(g_img, dtype=np.float32) / 255.0
        b2 = np.array(b_img, dtype=np.float32) / 255.0
        a2 = np.array(a_img, dtype=np.float32) / 255.0

        eps = 1e-6
        rgb_bleed = np.stack([
            np.divide(r2, a2 + eps),
            np.divide(g2, a2 + eps),
            np.divide(b2, a2 + eps)
        ], axis=2)

        # 在半透明区域使用出血颜色，其它保持原色
        alpha_mask = (a[:, :, 0] > 0.0) & (a[:, :, 0] < 0.98)
        rgb_out = rgb.copy()
        rgb_out[alpha_mask] = rgb_bleed[alpha_mask]

        out = np.concatenate([np.clip(rgb_out, 0.0, 1.0), a], axis=2)
        result = Image.fromarray((out * 255.0).astype(np.uint8))
        if original_info:
            result.info.update(original_info)
        return result

    def _resize_rgba_premultiplied(self, image, size, resample=Resampling.LANCZOS):
        from app.utils.rgba_resampler import resize_rgba_premultiplied

        return resize_rgba_premultiplied(image, size, resample)

    def _rotate_rgba_premultiplied(self, image, angle, resample=Resampling.BICUBIC, fillcolor=(0, 0, 0, 0)):
        from app.utils.rgba_resampler import rotate_rgba_premultiplied

        return rotate_rgba_premultiplied(
            image,
            angle,
            resample=resample,
            expand=True,
            fillcolor=fillcolor,
        )
