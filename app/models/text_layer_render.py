# -*- coding: utf-8 -*-
"""TextLayer 方法 mixin：本文件由拆分脚本生成，方法原属于 TextLayer。"""
from PySide6.QtCore import QObject, Signal, Property
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import os
import random
import platform
import math
import threading
from typing import List, Tuple, Dict, Set, Optional
from enum import Enum, auto
import json
from pathlib import Path
from app.models.text_layer_enums import (
    TextAlign, FontStyle, GradientType, GradientDirection, safe_print
)
from app.models.text_render_layout import normalize_auto_fit_padding


class TextLayerRenderMixin:

    def _text_effect_margin(self) -> int:
        margin = 0
        if getattr(self, '_shadow_enabled', False):
            margin = max(
                margin,
                int(getattr(self, '_shadow_blur', 0)) * 3
                + abs(int(getattr(self, '_shadow_offset_x', 0))),
                int(getattr(self, '_shadow_blur', 0)) * 3
                + abs(int(getattr(self, '_shadow_offset_y', 0))),
            )
        if getattr(self, '_glow_enabled', False):
            margin = max(margin, int(getattr(self, '_glow_radius', 1)) * 3)
        return margin

    @staticmethod
    def _colored_mask(mask: Image.Image, color) -> Image.Image:
        rgba = tuple(color) if isinstance(color, (tuple, list)) else (0, 0, 0, 255)
        if len(rgba) < 4:
            rgba = rgba[:3] + (255,)
        alpha_scale = max(0, min(255, int(rgba[3]))) / 255.0
        if alpha_scale < 1.0:
            mask = mask.point(lambda value: round(value * alpha_scale))
        result = Image.new('RGBA', mask.size, tuple(rgba[:3]) + (0,))
        result.putalpha(mask)
        return result

    @staticmethod
    def _offset_mask(mask: Image.Image, offset_x: int, offset_y: int) -> Image.Image:
        shifted = Image.new('L', mask.size, 0)
        shifted.paste(mask, (int(offset_x), int(offset_y)))
        return shifted

    def _draw_background_from_content(self, image: Image.Image, content: Image.Image) -> None:
        bbox = content.getbbox()
        if bbox is None:
            return
        padding = int(getattr(self, '_background_padding', 0))
        left = max(0, bbox[0] - padding)
        top = max(0, bbox[1] - padding)
        right = min(image.width, bbox[2] + padding)
        bottom = min(image.height, bbox[3] + padding)
        if right <= left or bottom <= top:
            return
        ImageDraw.Draw(image).rectangle(
            [left, top, right - 1, bottom - 1],
            fill=self._background_color,
        )

    def _compose_text_effects(self, background: Image.Image, text_image: Image.Image) -> Image.Image:
        result = background
        alpha = text_image.getchannel('A')

        if getattr(self, '_glow_enabled', False) and getattr(self, '_glow_strength', 0) > 0:
            radius = max(1, int(getattr(self, '_glow_radius', 1)))
            strength = max(0, min(20, int(getattr(self, '_glow_strength', 0))))
            glow_image = text_image.filter(ImageFilter.GaussianBlur(radius=radius))
            glow_mask = glow_image.getchannel('A')
            glow_mask = glow_mask.point(
                lambda value: min(255, round(value * (strength / 5.0)))
            )
            glow_image.putalpha(glow_mask)
            result = Image.alpha_composite(result, glow_image)

        if getattr(self, '_shadow_enabled', False):
            blur = max(0, int(getattr(self, '_shadow_blur', 0)))
            shadow_mask = alpha.filter(ImageFilter.GaussianBlur(radius=blur)) if blur else alpha
            shadow_mask = self._offset_mask(
                shadow_mask,
                getattr(self, '_shadow_offset_x', 0),
                getattr(self, '_shadow_offset_y', 0),
            )
            result = Image.alpha_composite(
                result,
                self._colored_mask(shadow_mask, self._shadow_color),
            )

        return Image.alpha_composite(result, text_image)

    def _create_gradient_image(self, width: int, height: int) -> Image.Image:
        """创建渐变图像"""
        if not self._gradient_enabled or self._gradient_type == GradientType.NONE:
            # 返回纯色图像
            return Image.new('RGBA', (width, height), self._text_color)

        # 创建渐变图像
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        start_r, start_g, start_b, start_a = self._gradient_start_color
        end_r, end_g, end_b, end_a = self._gradient_end_color

        if self._gradient_type == GradientType.LINEAR:
            return self._create_linear_gradient(width, height, start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a)
        elif self._gradient_type == GradientType.RADIAL:
            return self._create_radial_gradient(width, height, start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a)
        elif self._gradient_type == GradientType.ANGULAR:
            return self._create_angular_gradient(width, height, start_r, start_g, start_b, start_a,
                                               end_r, end_g, end_b, end_a)

        return Image.new('RGBA', (width, height), self._text_color)

    def _create_linear_gradient(self, width, height, start_r, start_g, start_b, start_a,
                               end_r, end_g, end_b, end_a):
        """创建线性渐变"""
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        # 根据方向计算渐变
        if self._gradient_direction == GradientDirection.HORIZONTAL:
            for x in range(width):
                ratio = x / (width - 1) if width > 1 else 0
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                for y in range(height):
                    pixels[x, y] = color
        elif self._gradient_direction == GradientDirection.VERTICAL:
            for y in range(height):
                ratio = y / (height - 1) if height > 1 else 0
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                for x in range(width):
                    pixels[x, y] = color
        elif self._gradient_direction == GradientDirection.DIAGONAL_LR:
            diagonal_length = math.sqrt(width * width + height * height)
            for x in range(width):
                for y in range(height):
                    distance = math.sqrt(x * x + y * y)
                    ratio = distance / diagonal_length if diagonal_length > 0 else 0
                    ratio = min(1.0, ratio)
                    color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                                  end_r, end_g, end_b, end_a, ratio)
                    pixels[x, y] = color
        elif self._gradient_direction == GradientDirection.DIAGONAL_RL:
            diagonal_length = math.sqrt(width * width + height * height)
            for x in range(width):
                for y in range(height):
                    distance = math.sqrt((width - x) * (width - x) + y * y)
                    ratio = distance / diagonal_length if diagonal_length > 0 else 0
                    ratio = min(1.0, ratio)
                    color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                                  end_r, end_g, end_b, end_a, ratio)
                    pixels[x, y] = color

        return gradient_img

    def _create_radial_gradient(self, width, height, start_r, start_g, start_b, start_a,
                               end_r, end_g, end_b, end_a):
        """创建径向渐变"""
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        center_x = int(width * self._gradient_center_x)
        center_y = int(height * self._gradient_center_y)
        max_radius = max(
            math.sqrt(center_x * center_x + center_y * center_y),
            math.sqrt((width - center_x) * (width - center_x) + center_y * center_y),
            math.sqrt(center_x * center_x + (height - center_y) * (height - center_y)),
            math.sqrt((width - center_x) * (width - center_x) + (height - center_y) * (height - center_y))
        )

        for x in range(width):
            for y in range(height):
                distance = math.sqrt((x - center_x) * (x - center_x) + (y - center_y) * (y - center_y))
                ratio = distance / max_radius if max_radius > 0 else 0
                ratio = min(1.0, ratio)
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                pixels[x, y] = color

        return gradient_img

    def _create_angular_gradient(self, width, height, start_r, start_g, start_b, start_a,
                                end_r, end_g, end_b, end_a):
        """创建角度渐变"""
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        center_x = width / 2
        center_y = height / 2

        for x in range(width):
            for y in range(height):
                angle = math.atan2(y - center_y, x - center_x)
                # 将角度转换为0-1的比例
                ratio = (angle + math.pi) / (2 * math.pi)
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                pixels[x, y] = color

        return gradient_img

    def _interpolate_color(self, start_r, start_g, start_b, start_a,
                          end_r, end_g, end_b, end_a, ratio):
        """颜色插值"""
        ratio = max(0.0, min(1.0, ratio))
        r = int(start_r + (end_r - start_r) * ratio)
        g = int(start_g + (end_g - start_g) * ratio)
        b = int(start_b + (end_b - start_b) * ratio)
        a = int(start_a + (end_a - start_a) * ratio)
        return (r, g, b, a)

    def _draw_text_with_style(self, draw, x, y, text, font, color_or_image):
        """绘制带样式的文字，支持渐变"""
        # 如果启用了渐变，使用渐变图像作为填充
        if self._gradient_enabled and isinstance(color_or_image, Image.Image):
            # 创建文字蒙版
            text_mask = Image.new('L', (self._width, self._height), 0)
            mask_draw = ImageDraw.Draw(text_mask)

            # 根据字体样式绘制蒙版
            if self._font_style == FontStyle.NORMAL:
                mask_draw.text((x, y), text, font=font, fill=255)
            elif self._font_style == FontStyle.BOLD:
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    mask_draw.text((x + dx, y + dy), text, font=font, fill=255)
            elif self._font_style == FontStyle.ITALIC:
                mask_draw.text((x, y), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)
            elif self._font_style == FontStyle.BOLD_ITALIC:
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    mask_draw.text((x + dx, y + dy), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)

            # 将渐变图像应用到文字区域
            # 创建临时图像用于合成
            temp_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
            temp_img.paste(color_or_image, (0, 0))

            # 使用蒙版将渐变应用到文字
            result_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
            result_img.paste(temp_img, (0, 0), text_mask)

            return result_img
        else:
            # 普通颜色填充
            if self._font_style == FontStyle.NORMAL:
                draw.text((x, y), text, font=font, fill=color_or_image)
            elif self._font_style == FontStyle.BOLD:
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    draw.text((x + dx, y + dy), text, font=font, fill=color_or_image)
            elif self._font_style == FontStyle.ITALIC:
                # 使用蒙版实现斜体
                text_mask = Image.new('L', (self._width, self._height), 0)
                mask_draw = ImageDraw.Draw(text_mask)
                mask_draw.text((x, y), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)
                colored = Image.new('RGBA', (self._width, self._height), color_or_image if isinstance(color_or_image, tuple) else (0,0,0,0))
                result_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                result_img.paste(colored, (0, 0), text_mask)
                # 合成到主图像
                draw_image = Image.new('RGBA', (self._width, self._height))
                draw_image.paste(result_img, (0, 0))
                # 将生成的图层与当前图像合成
                # 注意：这里无法直接用draw对象合成，调用者在上层会alpha合成
                return result_img
            elif self._font_style == FontStyle.BOLD_ITALIC:
                text_mask = Image.new('L', (self._width, self._height), 0)
                mask_draw = ImageDraw.Draw(text_mask)
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    mask_draw.text((x + dx, y + dy), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)
                colored = Image.new('RGBA', (self._width, self._height), color_or_image if isinstance(color_or_image, tuple) else (0,0,0,0))
                result_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                result_img.paste(colored, (0, 0), text_mask)
                return result_img

            return None

    def _draw_text_background(self, draw: ImageDraw.Draw, lines: list, font, start_y: int, line_widths: list, line_heights: list, max_line_height: int) -> None:
        """绘制文字背景 - 基于实际文字像素边界的完全居中算法，支持±距离控制"""
        if not self._background_enabled or not lines:
            return

        # 创建一个临时图像来获取文字的实际像素边界（包含所有效果）
        temp_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_image)

        # 准备渐变图像（如果启用）
        gradient_image = None
        if self._gradient_enabled:
            gradient_image = self._create_gradient_image(self._width, self._height)

        # 渲染文字到临时图像（包含所有效果：描边、渐变等）
        current_y = start_y
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break

            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height

            # 计算X位置
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                x = max(0, self._width - line_width)
            else:  # LEFT
                x = 0

            # 渲染描边（如果启用）
            if self._stroke_enabled and self._stroke_width > 0:
                if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
                    # 斜体描边：创建描边蒙版并应用斜体变换
                    stroke_mask = Image.new('L', (self._width, self._height), 0)
                    stroke_draw = ImageDraw.Draw(stroke_mask)

                    # 绘制描边蒙版
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                stroke_draw.text((x + dx, current_y + dy), line, font=font, fill=255)

                    # 应用斜体变换
                    stroke_mask = self._apply_italic_shear(stroke_mask)

                    # 创建描边颜色图像并应用蒙版
                    stroke_colored = Image.new('RGBA', (self._width, self._height), self._stroke_color)
                    stroke_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                    stroke_result.paste(stroke_colored, (0, 0), stroke_mask)

                    # 合成描边到临时图像
                    temp_image = Image.alpha_composite(temp_image, stroke_result)
                else:
                    # 普通描边：直接绘制
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                temp_draw.text(
                                    (x + dx, current_y + dy),
                                    line,
                                    font=font,
                                    fill=self._stroke_color
                                )

            # 渲染主文字，考虑渐变和字体样式
            if self._gradient_enabled and gradient_image:
                # 使用渐变绘制
                gradient_result = self._draw_text_with_style(temp_draw, x, current_y, line, font, gradient_image)
                if gradient_result:
                    # 将渐变文字合成到临时图像
                    temp_image = Image.alpha_composite(temp_image, gradient_result)
            else:
                # 使用纯色绘制（可能返回合成图像用于斜体）
                color_result = self._draw_text_with_style(temp_draw, x, current_y, line, font, self._text_color)
                if color_result:
                    temp_image = Image.alpha_composite(temp_image, color_result)
                else:
                    temp_draw.text((x, current_y), line, font=font, fill=self._text_color)

            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))

        # 扫描像素找到文字的实际边界（包含所有效果）
        pixels = temp_image.load()
        text_left = self._width
        text_top = self._height
        text_right = 0
        text_bottom = 0
        found_text = False

        for y in range(self._height):
            for x in range(self._width):
                r, g, b, a = pixels[x, y]
                if a > 10:  # 检测到文字像素（包含描边等效果）
                    text_left = min(text_left, x)
                    text_top = min(text_top, y)
                    text_right = max(text_right, x)
                    text_bottom = max(text_bottom, y)
                    found_text = True

        if not found_text:
            return

        # 计算文字的中心位置
        text_center_x = (text_left + text_right) // 2
        text_center_y = (text_top + text_bottom) // 2
        text_width = text_right - text_left + 1
        text_height = text_bottom - text_top + 1

        # 根据背景内边距参数计算背景尺寸
        # 正数：背景大于文字（向外扩展），负数：背景小于文字（向内收缩）
        bg_width = max(1, text_width + 2 * self._background_padding)  # 确保最小宽度
        bg_height = max(1, text_height + 2 * self._background_padding)  # 确保最小高度

        # 计算背景位置（以文字中心为基准，实现完全居中）
        bg_left = text_center_x - bg_width // 2
        bg_top = text_center_y - bg_height // 2
        bg_right = bg_left + bg_width
        bg_bottom = bg_top + bg_height

        # 确保背景不超出图层边界
        bg_left = max(0, bg_left)
        bg_right = min(self._width, bg_right)
        bg_top = max(0, bg_top)
        bg_bottom = min(self._height, bg_bottom)

        # 绘制背景矩形
        draw.rectangle(
            [bg_left, bg_top, bg_right, bg_bottom],
            fill=self._background_color
        )

    def _apply_italic_shear(self, mask_img: Image.Image) -> Image.Image:
        """对文字蒙版应用水平斜切以模拟斜体"""
        # 典型斜体角度约12度
        shear_angle = 12.0
        shear = math.tan(math.radians(shear_angle))
        # 仿射变换：x' = x + shear*y
        a, b, c = 1, shear, 0
        d, e, f = 0, 1, 0
        try:
            return mask_img.transform(mask_img.size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.BILINEAR)
        except Exception:
            return mask_img

    def _draw_text_with_letter_spacing(self, draw: ImageDraw.Draw, x: int, y: int, text: str, font, fill,
                                      stroke_width: int = 0, stroke_fill=None, bold: bool = False) -> tuple:
        """绘制带字间距的文本，返回实际绘制的宽度和高度

        Args:
            draw: ImageDraw对象
            x: 起始X坐标
            y: 起始Y坐标
            text: 要绘制的文本
            font: 字体对象
            fill: 填充颜色

        Returns:
            tuple: (实际宽度, 实际高度)
        """
        if self._letter_spacing == 0:
            # 没有字间距，使用标准绘制
            draw.text((x, y), text, font=font, fill=fill)
            bbox = draw.textbbox((x, y), text, font=font)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])

        # 有字间距，逐字符绘制
        current_x = x
        max_height = 0

        bold_offsets = [(0, 0), (1, 0), (0, 1), (1, 1)] if bold else [(0, 0)]
        for char in text:
            # 绘制当前字符
            for dx, dy in bold_offsets:
                draw.text(
                    (current_x + dx, y + dy),
                    char,
                    font=font,
                    fill=fill,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill
                )

            # 获取字符的宽度
            bbox = draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            char_height = bbox[3] - bbox[1]
            max_height = max(max_height, char_height)

            # 移动到下一个字符位置（字符宽度 + 字间距）
            current_x += char_width + self._letter_spacing

        # 返回总宽度（不包括最后的字间距）
        total_width = current_x - x - self._letter_spacing if text else 0
        return (total_width, max_height)

    def _create_text_mask_with_spacing(self, x: int, y: int, text: str, font,
                                      stroke_width: int = 0, bold: bool = False) -> Image.Image:
        """创建带字间距的文字蒙版（支持斜体/粗体）"""
        mask = Image.new('L', (self._width, self._height), 0)
        mask_draw = ImageDraw.Draw(mask)
        temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))

        current_x = x
        bold_offsets = [(0, 0), (1, 0), (0, 1), (1, 1)] if bold else [(0, 0)]

        for char in text:
            for dx, dy in bold_offsets:
                mask_draw.text(
                    (current_x + dx, y + dy),
                    char,
                    font=font,
                    fill=255,
                    stroke_width=stroke_width,
                    stroke_fill=255
                )
            bbox = temp_draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            current_x += char_width + self._letter_spacing

        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            mask = self._apply_italic_shear(mask)

        return mask

    def _get_text_width_with_spacing(self, text: str, font) -> int:
        """计算带字间距的文本宽度

        Args:
            text: 文本内容
            font: 字体对象

        Returns:
            int: 文本宽度（像素）
        """
        if not text:
            return 0

        if self._letter_spacing == 0:
            # 没有字间距，使用标准计算
            temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0]

        # 有字间距，逐字符计算
        temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        total_width = 0

        for char in text:
            bbox = temp_draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            total_width += char_width + self._letter_spacing

        # 减去最后一个字符后多余的字间距
        if text:
            total_width -= self._letter_spacing

        return total_width

    def _measure_horizontal_text(self, lines: List[str], font, draw: ImageDraw.Draw) -> Tuple[int, int]:
        """测量横排文字内容尺寸（不含外边距）"""
        if not lines:
            return 0, 0

        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        italic_shear_extra = 0
        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            italic_shear_extra = int(math.tan(math.radians(12.0)) * max(1, self._font_size))

        line_widths = []
        line_heights = []
        for line in lines:
            line_text = line if line else " "
            line_width = self._get_text_width_with_spacing(line_text, font)
            bbox = draw.textbbox((0, 0), line_text, font=font, stroke_width=stroke_for_measure)
            bbox_width = max(0, bbox[2] - bbox[0])
            line_height = max(0, bbox[3] - bbox[1])
            render_width = max(line_width, bbox_width) + italic_shear_extra
            line_widths.append(max(0, render_width))
            line_heights.append(max(0, line_height))

        max_line_height = max(line_heights) if line_heights else 0
        line_gap = int(max_line_height * (self._line_spacing - 1)) if max_line_height else 0
        content_width = max(line_widths) if line_widths else 0
        content_height = sum(line_heights) + max(0, len(line_heights) - 1) * line_gap
        return content_width, content_height

    def _measure_vertical_text(self, lines: List[str], font, draw: ImageDraw.Draw) -> Tuple[int, int]:
        """测量竖排文字内容尺寸（不含外边距）"""
        if not lines:
            return 0, 0

        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        italic_shear_extra = 0
        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            italic_shear_extra = int(math.tan(math.radians(12.0)) * max(1, self._font_size))

        column_widths = []
        column_heights = []

        for line in lines:
            chars = list(line) if line else [" "]
            char_heights = []
            char_widths = []
            for ch in chars:
                bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_for_measure)
                cw = max(0, bbox[2] - bbox[0])
                chh = max(0, bbox[3] - bbox[1])
                char_widths.append(cw)
                char_heights.append(chh)

            column_width = (max(char_widths) if char_widths else 0) + italic_shear_extra
            base_gap = int((max(char_heights) if char_heights else 0) * (self._line_spacing - 1))
            char_gap = base_gap + self._letter_spacing
            column_height = sum(char_heights) + max(0, len(char_heights) - 1) * char_gap

            column_widths.append(column_width)
            column_heights.append(column_height)

        max_col_width = max(column_widths) if column_widths else 0
        col_gap = int(max_col_width * (self._line_spacing - 1)) if max_col_width else 0
        content_width = sum(column_widths) + max(0, len(column_widths) - 1) * col_gap
        content_height = max(column_heights) if column_heights else 0
        return content_width, content_height

    def _update_text_box_size_if_needed(self) -> bool:
        """根据文字内容自动调整边框尺寸。返回是否发生尺寸变化。"""
        if not self._auto_fit_text_box or self._auto_fit_lock:
            return False

        try:
            self._auto_fit_lock = True
            font = self._get_font_object()
            temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            lines = (self._current_text or "").split('\n')
            if not lines:
                lines = [""]

            if self._vertical_layout:
                content_width, content_height = self._measure_vertical_text(lines, font, temp_draw)
            else:
                content_width, content_height = self._measure_horizontal_text(lines, font, temp_draw)

            # content_width/content_height 已包含描边测量，不再重复叠加 stroke_extra
            padding = self._text_box_padding + self._text_effect_margin()
            target_width = max(1, int(content_width + padding * 2))
            target_height = max(1, int(content_height + padding * 2))

            changed = (target_width != self._width or target_height != self._height)
            if changed:
                self._width = target_width
                self._height = target_height
            return changed
        except Exception:
            return False
        finally:
            self._auto_fit_lock = False

    def randomize_text(self):
        """随机选择文字内容，增强随机性避免重复"""
        if self._text_lines and len(self._text_lines) > 0:
            rng = random.SystemRandom()

            # 如果只有一个文字选项，在批量导出时也要触发变化通知
            if len(self._text_lines) == 1:
                self.set_current_text(self._text_lines[0], force=True)
                return

            # 多个文字选项时，确保选择的文字与当前不同（如果可能）
            available_texts = [text for text in self._text_lines if text != self._current_text]

            if available_texts:
                # 从不同于当前文字的选项中随机选择
                selected_text = rng.choice(available_texts)
            else:
                # 如果所有文字都相同或只有当前文字，随机选择任意一条
                selected_text = rng.choice(list(self._text_lines))

            self.set_current_text(selected_text)

    def get_image(self):
        """获取当前文字的渲染图像（遍历模式专用）

        直接使用当前设置的文字进行渲染，不进行随机选择
        """
        safe_print(f"文字图层 '{self._name}' 渲染当前文字: '{self._current_text}'")
        return self.render_text()

    def _get_rendered_text_bounds(self, lines, font, line_widths, line_heights) -> tuple:
        """获取渲染后文字的实际像素边界（ink bounds）

        Returns:
            tuple: (left, top, right, bottom) - 实际像素边界
        """
        # 创建临时图像用于渲染和测量
        temp_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_image)

        # 计算基础布局（使用当前逻辑）
        if not line_heights:
            return (0, 0, 0, 0)

        max_line_height = max(line_heights)
        total_height = sum(line_heights) + (len(lines) - 1) * int(max_line_height * (self._line_spacing - 1))

        # 基础居中位置
        if total_height > 0:
            start_y = (self._height - total_height) // 2 + 2  # 使用当前的偏移
        else:
            start_y = (self._height - total_height) // 2

        # 准备渐变图像（如果启用）
        gradient_image = None
        if self._gradient_enabled:
            gradient_image = self._create_gradient_image(self._width, self._height)

        # 渲染文字到临时图像
        current_y = start_y
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break

            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height

            # 计算X位置
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                x = max(0, self._width - line_width)
            else:  # LEFT
                x = 0

            current_line_y = current_y

            # 绘制描边
            if self._stroke_enabled and self._stroke_width > 0:
                if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
                    # 斜体描边：创建描边蒙版并应用斜体变换
                    stroke_mask = Image.new('L', (self._width, self._height), 0)
                    stroke_draw = ImageDraw.Draw(stroke_mask)

                    # 绘制描边蒙版
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                stroke_draw.text((x + dx, current_line_y + dy), line, font=font, fill=255)

                    # 应用斜体变换
                    stroke_mask = self._apply_italic_shear(stroke_mask)

                    # 创建描边颜色图像并应用蒙版
                    stroke_colored = Image.new('RGBA', (self._width, self._height), self._stroke_color)
                    stroke_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                    stroke_result.paste(stroke_colored, (0, 0), stroke_mask)

                    # 合成描边到主图像
                    temp_image = Image.alpha_composite(temp_image, stroke_result)
                else:
                    # 普通描边：直接绘制
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                temp_draw.text(
                                    (x + dx, current_line_y + dy),
                                    line,
                                    font=font,
                                    fill=self._stroke_color
                                )

            # 绘制主文字，考虑渐变和字体样式
            if self._gradient_enabled and gradient_image:
                # 使用渐变绘制
                gradient_result = self._draw_text_with_style(temp_draw, x, current_line_y, line, font, gradient_image)
                if gradient_result:
                    # 将渐变文字合成到主图像
                    temp_image = Image.alpha_composite(temp_image, gradient_result)
            else:
                # 使用纯色绘制（可能返回合成图像用于斜体）
                color_result = self._draw_text_with_style(temp_draw, x, current_line_y, line, font, self._text_color)
                if color_result:
                    temp_image = Image.alpha_composite(temp_image, color_result)

            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))

        # 扫描像素获取实际边界
        pixels = temp_image.load()
        left = self._width
        top = self._height
        right = 0
        bottom = 0
        found_pixels = False

        for y in range(self._height):
            for x in range(self._width):
                r, g, b, a = pixels[x, y]
                # 检测非透明像素（文字或描边）
                if a > 5:  # 使用阈值5来忽略抗锯齿的轻微透明
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
                    found_pixels = True

        if not found_pixels:
            return (0, 0, 0, 0)

        return (left, top, right + 1, bottom + 1)  # +1 转换为exclusive边界

    def _calculate_visual_center_y(self, lines: list, font, temp_draw: ImageDraw.Draw) -> int:
        """基于实际渲染像素计算视觉居中Y位置"""
        if not lines:
            return self._height // 2

        # 创建一个临时图像来渲染文字并分析实际像素边界
        test_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        test_draw = ImageDraw.Draw(test_image)

        # 先使用字体度量计算基础位置
        line_heights = []
        line_widths = []

        for line in lines:
            # 使用字间距计算宽度
            line_width = self._get_text_width_with_spacing(line, font)
            bbox = temp_draw.textbbox((0, 0), line, font=font)
            line_height = bbox[3] - bbox[1]
            line_widths.append(line_width)
            line_heights.append(line_height)

        if not line_heights:
            return self._height // 2

        max_line_height = max(line_heights)
        total_height = sum(line_heights) + (len(lines) - 1) * int(max_line_height * (self._line_spacing - 1))
        base_start_y = (self._height - total_height) // 2

        # 在临时图像上渲染文字（使用基础位置）
        current_y = base_start_y
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break

            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height

            # 计算X位置
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                x = max(0, self._width - line_width)
            else:  # LEFT
                x = 0

            # 渲染文字到临时图像
            test_draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))

            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))

        # 分析实际像素边界
        pixels = test_image.load()
        left = self._width
        top = self._height
        right = 0
        bottom = 0
        found_pixels = False

        for y in range(self._height):
            for x in range(self._width):
                r, g, b, a = pixels[x, y]
                if a > 10:  # 检测到文字像素
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
                    found_pixels = True

        if not found_pixels:
            return base_start_y

        # 计算实际文字中心
        actual_text_center = (top + bottom) // 2
        layer_center = self._height // 2

        # 计算需要调整的偏移量
        center_offset = layer_center - actual_text_center

        # 返回调整后的Y位置
        return max(0, min(self._height - total_height, base_start_y + center_offset))

    def render_text(self) -> Image.Image:
        """渲染文字为图像（基于实际像素边界的智能居中算法）"""
        with self._render_lock:
            if self._cached_image:
                return self._cached_image

            if self._should_supersample():
                image = self._render_text_supersampled()
            else:
                image = self._render_text_internal()

            self._cached_image = image
            return image

    def _should_supersample(self) -> bool:
        """判断是否启用超采样渲染以提升质量"""
        scale = max(2, int(getattr(self, '_supersample_scale', 2)))
        enabled = getattr(self, '_supersample_enabled', True)
        if not enabled or scale <= 1:
            return False

        # 避免超大图层导致性能问题
        max_pixels = 4_000_000  # 约4MP
        return (self._width * self._height) <= max_pixels

    def _render_text_supersampled(self) -> Image.Image:
        """使用超采样渲染文字，再缩放回目标尺寸"""
        scale = max(2, int(getattr(self, '_supersample_scale', 2)))
        prev_auto_fit_lock = self._auto_fit_lock

        # 先在基准尺度完成自动适配，避免超采样阶段再次触发自适配导致
        # “大尺寸渲染后缩回旧尺寸”的非等比压缩。
        if self._auto_fit_text_box and not self._auto_fit_lock:
            self._update_text_box_size_if_needed()

        # 保存原始参数
        original = {
            'width': self._width,
            'height': self._height,
            'font_size': self._font_size,
            'stroke_width': self._stroke_width,
            'letter_spacing': self._letter_spacing,
            'text_box_padding': self._text_box_padding,
            'background_padding': self._background_padding,
            'shadow_offset_x': self._shadow_offset_x,
            'shadow_offset_y': self._shadow_offset_y,
            'shadow_blur': self._shadow_blur,
            'glow_radius': self._glow_radius,
        }

        try:
            # 放大参数
            self._width = int(self._width * scale)
            self._height = int(self._height * scale)
            self._font_size = int(self._font_size * scale)
            self._stroke_width = int(self._stroke_width * scale)
            self._letter_spacing = int(self._letter_spacing * scale)
            self._text_box_padding = int(self._text_box_padding * scale)
            self._background_padding = int(self._background_padding * scale)
            self._shadow_offset_x = int(self._shadow_offset_x * scale)
            self._shadow_offset_y = int(self._shadow_offset_y * scale)
            self._shadow_blur = int(self._shadow_blur * scale)
            self._glow_radius = int(self._glow_radius * scale)

            # 锁住自适配，避免在放大参数下重算图层尺寸
            self._auto_fit_lock = True

            # 重新渲染为大图
            large_image = self._render_text_internal()
            # 缩回目标尺寸
            image = large_image.resize((original['width'], original['height']), Image.Resampling.LANCZOS)
        finally:
            # 还原参数
            self._width = original['width']
            self._height = original['height']
            self._font_size = original['font_size']
            self._stroke_width = original['stroke_width']
            self._letter_spacing = original['letter_spacing']
            self._text_box_padding = original['text_box_padding']
            self._background_padding = original['background_padding']
            self._shadow_offset_x = original['shadow_offset_x']
            self._shadow_offset_y = original['shadow_offset_y']
            self._shadow_blur = original['shadow_blur']
            self._glow_radius = original['glow_radius']
            self._auto_fit_lock = prev_auto_fit_lock

        return self._normalize_auto_fit_padding(image)

    def _normalize_auto_fit_padding(self, image: Image.Image) -> Image.Image:
        """自动适配时按真实非透明像素统一四边内边距。"""
        if not self._auto_fit_text_box or self._auto_fit_lock or self._background_enabled:
            return image

        try:
            normalized, normalized_size = normalize_auto_fit_padding(image, self._text_box_padding)
            if normalized_size:
                self._width, self._height = normalized_size
            return normalized
        except Exception:
            return image

    def _color_for_text_index(self, index):
        for item in self._text_color_ranges:
            if item["start"] <= index < item["end"]:
                return tuple(item["color"])
        return None

    def _iter_line_color_segments(self, line: str, line_start_index: int):
        if not line:
            return

        segment_start = 0
        segment_color = self._color_for_text_index(line_start_index)
        for offset in range(1, len(line)):
            color = self._color_for_text_index(line_start_index + offset)
            if color != segment_color:
                yield segment_start, offset, segment_color
                segment_start = offset
                segment_color = color
        yield segment_start, len(line), segment_color

    def _draw_text_fill_piece(self, image: Image.Image, x: int, y: int, text: str, font, fill) -> Image.Image:
        if not text:
            return image
        draw = ImageDraw.Draw(image)
        result = self._draw_text_with_style(draw, x, y, text, font, fill)
        if result:
            image = Image.alpha_composite(image, result)
        return image

    def _draw_text_line_fill(self, image: Image.Image, x: int, y: int, line: str,
                             line_start_index: int, font, gradient_image) -> Image.Image:
        if not line:
            return image

        use_gradient = self._gradient_enabled and gradient_image is not None
        if self._letter_spacing != 0:
            current_x = x
            temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            for offset, ch in enumerate(line):
                local_color = self._color_for_text_index(line_start_index + offset)
                fill = local_color if local_color is not None else (gradient_image if use_gradient else self._text_color)
                image = self._draw_text_fill_piece(image, current_x, y, ch, font, fill)
                bbox = temp_draw.textbbox((0, 0), ch, font=font)
                current_x += (bbox[2] - bbox[0]) + self._letter_spacing
            return image

        for start, end, local_color in self._iter_line_color_segments(line, line_start_index):
            segment = line[start:end]
            segment_x = x + self._get_text_width_with_spacing(line[:start], font)
            fill = local_color if local_color is not None else (gradient_image if use_gradient else self._text_color)
            image = self._draw_text_fill_piece(image, segment_x, y, segment, font, fill)
        return image

    def _render_text_internal(self) -> Image.Image:
        """内部渲染实现（不写缓存）"""
        # 自动适配边框：在渲染前保证尺寸与当前文字一致
        self._update_text_box_size_if_needed()

        # 获取字体
        font = self._get_font_object()

        # 处理多行文字
        lines = self._current_text.split('\n')

        # 计算基础布局
        temp_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_image)

        line_heights = []
        line_widths = []
        line_left_offsets = []
        line_top_offsets = []
        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        italic_shear_extra = 0
        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            italic_shear_extra = int(math.tan(math.radians(12.0)) * max(1, self._font_size))

        for line in lines:
            # 使用字间距计算宽度
            line_text = line if line else " "
            line_width = self._get_text_width_with_spacing(line_text, font)
            bbox = temp_draw.textbbox((0, 0), line_text, font=font, stroke_width=stroke_for_measure)
            bbox_width = max(0, bbox[2] - bbox[0])
            bbox_height = max(0, bbox[3] - bbox[1])

            render_width = max(line_width, bbox_width) + italic_shear_extra
            line_widths.append(render_width)
            line_heights.append(bbox_height)
            # 关键修复：必须完整使用 -bbox 偏移（含正负），否则中文字体 top>0 时会整体下移
            line_left_offsets.append(int(-bbox[0]))
            line_top_offsets.append(int(-bbox[1]))

        # 计算总高度
        if not line_heights:
            total_height = 0
            max_line_height = 0
        else:
            max_line_height = max(line_heights)
            total_height = sum(line_heights) + (len(lines) - 1) * int(max_line_height * (self._line_spacing - 1))

        # 竖排：单独布局渲染
        if self._vertical_layout:
            return self._render_text_vertical_internal(font, lines, temp_draw)

        # 自动适配边框时，以边距为锚点；否则沿用原视觉居中算法
        if self._auto_fit_text_box:
            final_start_y = max(0, self._text_box_padding + self._text_effect_margin())
        else:
            # 非自动适配时，使用与测量一致的几何居中，避免视觉中心算法与bbox口径不一致
            final_start_y = max(0, (self._height - total_height) // 2)

        # 准备渐变图像（如果启用）
        gradient_image = None
        if self._gradient_enabled:
            gradient_image = self._create_gradient_image(self._width, self._height)

        # 背景和文字分层渲染，阴影/发光只使用文字蒙版。
        image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        text_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_image)

        # 使用调整后的位置进行最终渲染
        current_y = final_start_y
        line_start_index = 0
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break

            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height
            x_offset = line_left_offsets[i] if i < len(line_left_offsets) else 0
            y_offset = line_top_offsets[i] if i < len(line_top_offsets) else 0

            # 计算X位置 - 改进水平居中
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                if self._auto_fit_text_box:
                    x = max(
                        0,
                        self._width
                        - self._text_box_padding
                        - self._text_effect_margin()
                        - line_width,
                    )
                else:
                    x = max(0, self._width - line_width)
            else:  # LEFT
                if self._auto_fit_text_box:
                    x = max(0, self._text_box_padding + self._text_effect_margin())
                else:
                    x = 0

            # 垂直位置 - 使用调整后的Y位置
            current_line_y = current_y
            draw_x = x + x_offset
            draw_y = current_line_y + y_offset

            # 绘制描边
            if self._stroke_enabled and self._stroke_width > 0:
                if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
                    stroke_mask = self._create_text_mask_with_spacing(
                        draw_x,
                        draw_y,
                        line,
                        font,
                        stroke_width=self._stroke_width,
                        bold=self._font_style == FontStyle.BOLD_ITALIC
                    )
                    stroke_colored = Image.new('RGBA', (self._width, self._height), self._stroke_color)
                    stroke_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                    stroke_result.paste(stroke_colored, (0, 0), stroke_mask)
                    text_image = Image.alpha_composite(text_image, stroke_result)
                    draw = ImageDraw.Draw(text_image)
                else:
                    if self._letter_spacing != 0:
                        self._draw_text_with_letter_spacing(
                            draw,
                            draw_x,
                            draw_y,
                            line,
                            font,
                            self._stroke_color,
                            stroke_width=self._stroke_width,
                            stroke_fill=self._stroke_color,
                            bold=self._font_style == FontStyle.BOLD
                        )
                    else:
                        draw.text(
                            (draw_x, draw_y),
                            line,
                            font=font,
                            fill=self._stroke_color,
                            stroke_width=self._stroke_width,
                            stroke_fill=self._stroke_color
                        )

            text_image = self._draw_text_line_fill(
                text_image,
                draw_x,
                draw_y,
                line,
                line_start_index,
                font,
                gradient_image,
            )
            draw = ImageDraw.Draw(text_image)

            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))
            line_start_index += len(line) + 1

        if self._background_enabled:
            self._draw_background_from_content(image, text_image)
        image = self._compose_text_effects(image, text_image)

        # 应用透明度
        if self._opacity < 1.0:
            alpha = image.split()[-1]
            alpha = alpha.point(lambda p: int(p * self._opacity))
            image.putalpha(alpha)

        return self._normalize_auto_fit_padding(image)

    def _render_text_vertical_internal(self, font, lines: List[str], temp_draw: ImageDraw.Draw) -> Image.Image:
        """竖排渲染实现。"""
        text_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_image)

        # 计算列宽和列高
        column_data = []
        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        text_index = 0
        for line in lines:
            chars = list(line) if line else [" "]
            char_sizes = []
            for offset, ch in enumerate(chars):
                bbox = temp_draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_for_measure)
                char_sizes.append((
                    max(0, bbox[2] - bbox[0]),
                    max(0, bbox[3] - bbox[1]),
                    int(-bbox[0]),
                    int(-bbox[1]),
                    ch,
                    text_index + offset
                ))
            col_width = max((w for w, _, _, _, _, _ in char_sizes), default=0)
            base_gap = int(max((h for _, h, _, _, _, _ in char_sizes), default=0) * (self._line_spacing - 1))
            char_gap = base_gap + self._letter_spacing
            col_height = sum(h for _, h, _, _, _, _ in char_sizes) + max(0, len(char_sizes) - 1) * char_gap
            column_data.append((col_width, col_height, char_sizes, char_gap))
            text_index += len(line) + 1

        total_width = 0
        if column_data:
            max_col_width = max(w for w, _, _, _ in column_data)
            col_gap = int(max_col_width * (self._line_spacing - 1))
            total_width = sum(w for w, _, _, _ in column_data) + max(0, len(column_data) - 1) * col_gap
        else:
            col_gap = 0

        max_height = max((h for _, h, _, _ in column_data), default=0)

        # 起始位置
        if self._auto_fit_text_box:
            padding = self._text_box_padding + self._text_effect_margin()
            start_x = max(0, padding)
            start_y = max(0, padding)
        else:
            if self._text_align == TextAlign.CENTER:
                start_x = max(0, (self._width - total_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                start_x = max(0, self._width - total_width)
            else:
                start_x = 0
            start_y = max(0, (self._height - max_height) // 2)

        gradient_image = self._create_gradient_image(self._width, self._height) if self._gradient_enabled else None

        current_x = start_x
        for col_width, col_height, char_sizes, char_gap in column_data:
            current_y = start_y
            for char_width, char_height, char_left_off, char_top_off, ch, char_index in char_sizes:
                char_x = current_x + max(0, (col_width - char_width) // 2) + char_left_off
                char_y = current_y + char_top_off

                if self._stroke_enabled and self._stroke_width > 0:
                    draw.text(
                        (char_x, char_y),
                        ch,
                        font=font,
                        fill=self._stroke_color,
                        stroke_width=self._stroke_width,
                        stroke_fill=self._stroke_color
                    )

                local_color = self._color_for_text_index(char_index)
                if local_color is not None:
                    color_result = self._draw_text_with_style(draw, char_x, char_y, ch, font, local_color)
                    if color_result:
                        text_image = Image.alpha_composite(text_image, color_result)
                        draw = ImageDraw.Draw(text_image)
                elif self._gradient_enabled and gradient_image is not None:
                    gradient_result = self._draw_text_with_style(draw, char_x, char_y, ch, font, gradient_image)
                    if gradient_result:
                        text_image = Image.alpha_composite(text_image, gradient_result)
                        draw = ImageDraw.Draw(text_image)
                else:
                    color_result = self._draw_text_with_style(draw, char_x, char_y, ch, font, self._text_color)
                    if color_result:
                        text_image = Image.alpha_composite(text_image, color_result)
                        draw = ImageDraw.Draw(text_image)
                    else:
                        draw.text((char_x, char_y), ch, font=font, fill=self._text_color)

                current_y += char_height + char_gap

            current_x += col_width + col_gap

        image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        if self._background_enabled:
            self._draw_background_from_content(image, text_image)
        image = self._compose_text_effects(image, text_image)

        if self._opacity < 1.0:
            alpha = image.split()[-1]
            alpha = alpha.point(lambda p: int(p * self._opacity))
            image.putalpha(alpha)

        return self._normalize_auto_fit_padding(image)
