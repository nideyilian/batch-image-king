#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档混合模式处理
提供各种图层混合模式的实现
"""

import numpy as np
from PIL import Image


class BlendMode:
    """混合模式常量定义"""
    NORMAL = "正常"
    MULTIPLY = "正片叠底"
    SCREEN = "滤色"
    OVERLAY = "叠加"
    SOFT_LIGHT = "柔光"
    HARD_LIGHT = "强光"
    COLOR_DODGE = "颜色减淡"
    COLOR_BURN = "颜色加深"
    DARKEN = "变暗"
    LIGHTEN = "变亮"
    DIFFERENCE = "差值"
    EXCLUSION = "排除"
    HUE = "色相"
    SATURATION = "饱和度"
    COLOR = "颜色"
    LUMINOSITY = "明度"
    
    @classmethod
    def get_all_modes(cls):
        """获取所有混合模式名称"""
        return [
            cls.NORMAL, cls.MULTIPLY, cls.SCREEN, cls.OVERLAY,
            cls.SOFT_LIGHT, cls.HARD_LIGHT, cls.COLOR_DODGE, cls.COLOR_BURN,
            cls.DARKEN, cls.LIGHTEN, cls.DIFFERENCE, cls.EXCLUSION,
            cls.HUE, cls.SATURATION, cls.COLOR, cls.LUMINOSITY
        ]


class Blender:
    """混合模式处理工具类"""

    @staticmethod
    def _blend_via_unified(bottom, top, opacity, blend_mode):
        """统一走 unified_alpha_compositor，确保预览/导出路径一致。"""
        try:
            from app.utils.unified_alpha_compositor import unified_alpha_compositor
            return unified_alpha_compositor.blend_with_mode(bottom, top, blend_mode, opacity)
        except Exception as e:
            print(f"[混合模式] 统一混合器调用失败({blend_mode}): {e}")
            # 最后回退：普通alpha合成，保证稳定
            if bottom.mode != 'RGBA':
                bottom = bottom.convert('RGBA')
            if top.mode != 'RGBA':
                top = top.convert('RGBA')
            if opacity < 1.0:
                top = Blender._apply_opacity(top, opacity)
            return Image.alpha_composite(bottom, top)
    
    @staticmethod
    def apply_blend_mode(bottom, top, mode, opacity=1.0):
        """应用混合模式
        
        Args:
            bottom: 底层图像 (PIL Image)
            top: 顶层图像 (PIL Image)
            mode: 混合模式字符串
            opacity: 不透明度 (0.0-1.0)
            
        Returns:
            混合后的图像 (PIL Image)
        """
        if not bottom or not top:
            return bottom or top
            
        # 确保两个图像尺寸一致
        if bottom.size != top.size:
            top = top.resize(bottom.size, Image.Resampling.LANCZOS)
        
        # 确保图像有alpha通道
        if bottom.mode != 'RGBA':
            bottom = bottom.convert('RGBA')
        if top.mode != 'RGBA':
            top = top.convert('RGBA')
        
        # 根据混合模式字符串选择混合方法
        mode_str = Blender._normalize_mode(mode)
        
        try:
            if mode_str == BlendMode.NORMAL:
                return Blender._blend_normal(bottom, top, opacity)
            elif mode_str == BlendMode.MULTIPLY:
                return Blender._blend_multiply(bottom, top, opacity)
            elif mode_str == BlendMode.SCREEN:
                return Blender._blend_screen(bottom, top, opacity)
            elif mode_str == BlendMode.OVERLAY:
                return Blender._blend_overlay(bottom, top, opacity)
            elif mode_str == BlendMode.SOFT_LIGHT:
                return Blender._blend_soft_light(bottom, top, opacity)
            elif mode_str == BlendMode.HARD_LIGHT:
                return Blender._blend_hard_light(bottom, top, opacity)
            elif mode_str == BlendMode.COLOR_DODGE:
                return Blender._blend_color_dodge(bottom, top, opacity)
            elif mode_str == BlendMode.COLOR_BURN:
                return Blender._blend_color_burn(bottom, top, opacity)
            elif mode_str == BlendMode.DARKEN:
                return Blender._blend_darken(bottom, top, opacity)
            elif mode_str == BlendMode.LIGHTEN:
                return Blender._blend_lighten(bottom, top, opacity)
            elif mode_str == BlendMode.DIFFERENCE:
                return Blender._blend_difference(bottom, top, opacity)
            elif mode_str == BlendMode.EXCLUSION:
                return Blender._blend_exclusion(bottom, top, opacity)
            elif mode_str == BlendMode.HUE:
                return Blender._blend_hue(bottom, top, opacity)
            elif mode_str == BlendMode.SATURATION:
                return Blender._blend_saturation(bottom, top, opacity)
            elif mode_str == BlendMode.COLOR:
                return Blender._blend_color(bottom, top, opacity)
            elif mode_str == BlendMode.LUMINOSITY:
                return Blender._blend_luminosity(bottom, top, opacity)
            else:
                # 未知模式，使用正常混合
                return Blender._blend_normal(bottom, top, opacity)
                
        except Exception as e:
            print(f"[混合模式] 混合失败，使用正常模式: {e}")
            return Blender._blend_normal(bottom, top, opacity)

    @staticmethod
    def _normalize_mode(mode) -> str:
        """标准化混合模式（支持中文/英文/数字）"""
        try:
            if mode is None:
                return BlendMode.NORMAL

            # 数字模式
            if isinstance(mode, int):
                blend_mode_map = {
                    0: BlendMode.NORMAL,
                    1: BlendMode.MULTIPLY,
                    2: BlendMode.SCREEN,
                    3: BlendMode.OVERLAY,
                    4: BlendMode.SOFT_LIGHT,
                    5: BlendMode.HARD_LIGHT,
                    6: BlendMode.COLOR_DODGE,
                    7: BlendMode.COLOR_BURN,
                    8: BlendMode.DARKEN,
                    9: BlendMode.LIGHTEN,
                    10: BlendMode.DIFFERENCE,
                    11: BlendMode.EXCLUSION,
                    12: BlendMode.HUE,
                    13: BlendMode.SATURATION,
                    14: BlendMode.COLOR,
                    15: BlendMode.LUMINOSITY
                }
                return blend_mode_map.get(mode, BlendMode.NORMAL)

            mode_str = str(mode).strip()
            if not mode_str:
                return BlendMode.NORMAL

            # 英文模式映射
            english_map = {
                'normal': BlendMode.NORMAL,
                'multiply': BlendMode.MULTIPLY,
                'screen': BlendMode.SCREEN,
                'overlay': BlendMode.OVERLAY,
                'soft_light': BlendMode.SOFT_LIGHT,
                'hard_light': BlendMode.HARD_LIGHT,
                'color_dodge': BlendMode.COLOR_DODGE,
                'color_burn': BlendMode.COLOR_BURN,
                'darken': BlendMode.DARKEN,
                'lighten': BlendMode.LIGHTEN,
                'difference': BlendMode.DIFFERENCE,
                'exclusion': BlendMode.EXCLUSION,
                'hue': BlendMode.HUE,
                'saturation': BlendMode.SATURATION,
                'color': BlendMode.COLOR,
                'luminosity': BlendMode.LUMINOSITY
            }
            lower = mode_str.lower()
            if lower in english_map:
                return english_map[lower]

            # 已是中文模式
            return mode_str
        except Exception:
            return BlendMode.NORMAL
            
    @staticmethod
    def _blend_normal(bottom, top, opacity):
        """正常混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'normal')

    @staticmethod
    def _blend_multiply(bottom, top, opacity):
        """正片叠底混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'multiply')

    @staticmethod
    def _blend_screen(bottom, top, opacity):
        """滤色混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'screen')

    @staticmethod
    def _blend_overlay(bottom, top, opacity):
        """叠加混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'overlay')
    
    @staticmethod
    def _blend_soft_light(bottom, top, opacity):
        """柔光混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'soft_light')
    
    @staticmethod
    def _blend_hard_light(bottom, top, opacity):
        """强光混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'hard_light')
    
    @staticmethod
    def _blend_color_dodge(bottom, top, opacity):
        """颜色减淡混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'color_dodge')
    
    @staticmethod
    def _blend_color_burn(bottom, top, opacity):
        """颜色加深混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'color_burn')
    
    @staticmethod
    def _blend_darken(bottom, top, opacity):
        """变暗混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'darken')
    
    @staticmethod
    def _blend_lighten(bottom, top, opacity):
        """变亮混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'lighten')
    
    @staticmethod
    def _blend_difference(bottom, top, opacity):
        """差值混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'difference')
    
    @staticmethod
    def _blend_exclusion(bottom, top, opacity):
        """排除混合模式"""
        return Blender._blend_via_unified(bottom, top, opacity, 'exclusion')
    
    @staticmethod
    def _blend_hue(bottom, top, opacity):
        """色相混合模式"""
        # 简化实现，返回顶层
        return Image.alpha_composite(bottom, top)
    
    @staticmethod
    def _blend_saturation(bottom, top, opacity):
        """饱和度混合模式"""
        # 简化实现，返回顶层
        return Image.alpha_composite(bottom, top)
    
    @staticmethod
    def _blend_color(bottom, top, opacity):
        """颜色混合模式"""
        # 简化实现，返回顶层
        return Image.alpha_composite(bottom, top)
    
    @staticmethod
    def _blend_luminosity(bottom, top, opacity):
        """明度混合模式"""
        # 简化实现，返回顶层
        return Image.alpha_composite(bottom, top)
    
    @staticmethod
    def _apply_opacity(image, opacity):
        """应用透明度到图层"""
        if opacity >= 1.0:
            return image
            
        # 创建一个新的图像，调整alpha通道透明度
        result = image.copy()
        if result.mode != 'RGBA':
            result = result.convert('RGBA')
        
        # 调整alpha通道
        r, g, b, a = result.split()
        a = a.point(lambda x: int(x * opacity))
        result = Image.merge('RGBA', (r, g, b, a))
        
        return result

    @staticmethod
    def optimize_png_for_blending(image, quality_level='high'):
        """为混合操作优化PNG图像"""
        try:
            from app.utils.unified_alpha_compositor import optimize_png_rendering
            return optimize_png_rendering(image, quality_level)
        except ImportError:
            return image
        except Exception as e:
            print(f"[混合模式] PNG优化失败: {e}")
            return image


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            print("[DEBUG] Message encoding failed")
