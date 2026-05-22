"""
统一Alpha合成器
整合所有alpha合成功能，提供专业级的图像混合能力
解决半透明像素变灰、边缘锯齿等问题

合并了以下模块的功能：
- advanced_alpha_compositor.py - 高级Alpha合成器
- perfect_alpha_blend.py - 完美Alpha混合器

新增PNG渲染优化功能：
- PNG黑边修复
- 高质量抗锯齿
- 预乘Alpha处理
"""

import numpy as np
from PIL import Image, ImageFilter
from typing import Tuple, Optional, Union
from enum import Enum

# 导入PNG渲染优化模块
try:
    from .image.png_renderer_optimizer import optimize_png_image
    from .image.premultiplied_alpha_handler import fix_premultiplied_alpha
    from .image.advanced_antialiasing import apply_png_antialiasing
    from .image.png_edge_fixer import fix_png_dark_edges_direct, auto_fix_png_for_background_direct
    PNG_OPTIMIZATION_AVAILABLE = True
except ImportError:
    PNG_OPTIMIZATION_AVAILABLE = False
    # 只在调试模式下显示详细信息
    import os
    if os.getenv('DEBUG_MODE') == '1':
        safe_print("[INFO] PNG渲染优化模块不可用，将使用基础实现")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    # 只在调试模式下显示详细警告
    import os
    if os.getenv('DEBUG_MODE') == '1':
        safe_print("[WARNING] OpenCV不可用，部分高级功能将被禁用")

try:
    import scipy.ndimage as ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    # 只在调试模式下显示详细警告
    import os
    if os.getenv('DEBUG_MODE') == '1':
        safe_print("[WARNING] SciPy不可用，部分高级功能将被禁用")


# 颜色空间转换常量 - 用于线性颜色空间混合
SRGB_THRESHOLD = 0.04045
SRGB_ALPHA = 0.055
SRGB_GAMMA = 2.4

# 预计算 sRGB 到 Linear RGB 的查找表 (LUT)
# 这极大地加速了 uint8 图像的颜色空间转换
def _create_srgb_to_linear_lut():
    lut = np.zeros(256, dtype=np.float64)
    for i in range(256):
        val = i / 255.0
        if val <= SRGB_THRESHOLD:
            lut[i] = val / 12.92
        else:
            lut[i] = ((val + SRGB_ALPHA) / (1 + SRGB_ALPHA)) ** SRGB_GAMMA
    return lut

# 创建全局查找表
SRGB_TO_LINEAR_LUT = _create_srgb_to_linear_lut()


def _apply_dithering(array: np.ndarray, rng_seed: int = 42) -> np.ndarray:
    """
    应用抖动（dithering）以消除色阶分层
    
    使用三角形概率密度函数（TPDF）抖动，这是音频/图像处理的标准方法
    可以有效消除量化噪声和色带
    
    Args:
        array: 归一化的浮点数组 (0.0-1.0)
        rng_seed: 随机数种子（用于可重复的结果）
        
    Returns:
        应用抖动后的数组
    """
    # 使用固定种子的随机数生成器以确保可重复性
    rng = np.random.RandomState(rng_seed)
    
    # 三角形概率密度函数（TPDF）抖动
    # 生成两个均匀分布的随机数，它们的和服从三角分布
    # 这比简单的矩形抖动（单个随机数）听觉/视觉效果更好
    dither1 = rng.uniform(-0.5/255.0, 0.5/255.0, array.shape)
    dither2 = rng.uniform(-0.5/255.0, 0.5/255.0, array.shape)
    dither = (dither1 + dither2) / 2.0
    
    # 应用抖动
    return array + dither


def _float_to_uint8_with_dithering(array: np.ndarray, use_dithering: bool = True) -> np.ndarray:
    """
    将浮点数组转换为uint8，可选应用抖动以防止色阶分层
    
    Args:
        array: 归一化的浮点数组 (0.0-1.0)
        use_dithering: 是否应用抖动
        
    Returns:
        uint8数组
    """
    # 确保数组在有效范围内
    array = np.clip(array, 0.0, 1.0)
    
    # 应用抖动。RGBA 图像只抖动颜色通道，不抖动 Alpha；
    # 否则半透明边缘会变成随机透明度噪点。
    if use_dithering:
        if array.ndim == 3 and array.shape[2] == 4:
            rgb = _apply_dithering(array[:, :, :3])
            array = np.concatenate([rgb, array[:, :, 3:4]], axis=2)
        else:
            array = _apply_dithering(array)

    # 抖动可能把 0/1 边界推出有效范围，必须在转 uint8 前再次裁剪；
    # 否则负数会绕回 255，表现为半透明区域的马赛克/噪点。
    array = np.clip(array, 0.0, 1.0)
    
    # 转换为8位，使用四舍五入而不是截断
    # 四舍五入可以减少系统性误差
    result = np.round(array * 255.0).astype(np.uint8)
    
    return result


class BlendMode(Enum):
    """混合模式枚举"""
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"
    COLOR_DODGE = "color_dodge"
    COLOR_BURN = "color_burn"
    DARKEN = "darken"
    LIGHTEN = "lighten"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"


class UnifiedAlphaCompositor:
    """统一Alpha合成器 - 整合所有alpha合成功能"""

    def __init__(self):
        """初始化合成器"""
        self.use_antialiasing = True
        self.use_subpixel_precision = True
        self.edge_enhancement = True

    # composite_layer definition removed to resolve duplication

    
    @staticmethod
    def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
        """sRGB到线性RGB转换 - 解决颜色变灰变黑问题"""
        # 优化：如果是uint8类型，直接使用查找表
        if rgb.dtype == np.uint8:
            return SRGB_TO_LINEAR_LUT[rgb]

        # 使用标准sRGB转换公式
        linear = np.where(rgb <= SRGB_THRESHOLD,
                         rgb / 12.92,
                         np.power((rgb + SRGB_ALPHA) / (1 + SRGB_ALPHA), SRGB_GAMMA))
        return linear
    
    @staticmethod
    def _linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
        """线性RGB到sRGB转换"""
        srgb = np.where(rgb <= 0.0031308,
                       rgb * 12.92,
                       (1 + SRGB_ALPHA) * np.power(rgb, 1/SRGB_GAMMA) - SRGB_ALPHA)
        return srgb
    
    @staticmethod
    def blend_photoshop_srgb(bottom: Image.Image, top: Image.Image, opacity: float = 1.0) -> Image.Image:
        """
        Photoshop风格的标准混合（sRGB空间）- 使用PIL原生实现
        
        使用Image.alpha_composite实现标准的Source Over混合（sRGB空间），
        与Photoshop的图层混合行为一致。
        """
        try:
            # 确保图像格式
            if bottom.mode != 'RGBA':
                bottom = bottom.convert('RGBA')
            if top.mode != 'RGBA':
                top = top.convert('RGBA')

            # 确保图像尺寸匹配
            if bottom.size != top.size:
                # 简单回退
                result = bottom.copy()
                if opacity < 1.0:
                    alpha = top.split()[-1]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    top = top.copy()
                    top.putalpha(alpha)
                result.paste(top, (0, 0), top)
                return result

            # 如果不透明度小于1.0，需要调整前景Alpha
            if opacity < 1.0:
                # 创建副本以避免修改原图
                top = top.copy()
                alpha = top.split()[-1]
                # 使用查找表加速Alpha调整
                lut = [int(x * opacity) for x in range(256)]
                alpha = alpha.point(lut)
                top.putalpha(alpha)
            
            # 使用PIL的高性能alpha_composite (C实现)
            # 这实现了标准的 Porter-Duff Source Over 混合
            return Image.alpha_composite(bottom, top)

        except Exception as e:
            print(f"[UnifiedAlphaCompositor] blend_photoshop_srgb failed: {e}")
            return UnifiedAlphaCompositor.blend_normal(bottom, top, opacity)

    @staticmethod
    def blend_normal(bottom: Image.Image, top: Image.Image, opacity: float = 1.0) -> Image.Image:
        """
        完美的正常混合模式 - 修复版本，解决渲染噪点问题

        Args:
            bottom: 底层图像
            top: 顶层图像
            opacity: 顶层不透明度 (0.0-1.0)

        Returns:
            正确混合后的图像
        """
        try:
            # 确保图像格式
            if bottom.mode != 'RGBA':
                bottom = bottom.convert('RGBA')
            if top.mode != 'RGBA':
                top = top.convert('RGBA')

            # 确保图像尺寸匹配
            if bottom.size != top.size:
                safe_print(f"[警告] 图像尺寸不匹配: bottom={bottom.size}, top={top.size}")
                # 使用简单的PIL合成作为后备
                result = bottom.copy()
                if opacity < 1.0:
                    alpha = top.split()[-1]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    top = top.copy()
                    top.putalpha(alpha)
                result.paste(top, (0, 0), top)
                return result

            # 优化：不直接转换为float64，而是先保持uint8以利用LUT
            bottom_array = np.array(bottom)
            top_array = np.array(top)

            # 检查数组形状
            if bottom_array.shape != top_array.shape:
                safe_print(f"[错误] 数组形状不匹配: bottom={bottom_array.shape}, top={top_array.shape}")
                # 回退到简单合成
                result = bottom.copy()
                result.paste(top, (0, 0), top)
                return result

            # 提取RGB并转换为线性空间（使用LUT加速）
            # 注意：这里传入的是uint8数组，会触发_srgb_to_linear的LUT优化
            bottom_rgb_linear = UnifiedAlphaCompositor._srgb_to_linear(bottom_array[:, :, :3])
            top_rgb_linear = UnifiedAlphaCompositor._srgb_to_linear(top_array[:, :, :3])

            # 提取Alpha通道并归一化
            bottom_alpha = bottom_array[:, :, 3:4].astype(np.float64) / 255.0
            top_alpha = top_array[:, :, 3:4].astype(np.float64) / 255.0

            if opacity < 1.0:
                top_alpha *= opacity

            out_alpha = top_alpha + bottom_alpha * (1 - top_alpha)
            safe_alpha = np.maximum(out_alpha, 1e-10)

            out_rgb_linear = (top_rgb_linear * top_alpha + bottom_rgb_linear * bottom_alpha * (1 - top_alpha)) / safe_alpha
            out_rgb = UnifiedAlphaCompositor._linear_to_srgb(out_rgb_linear)

            result = np.concatenate([np.clip(out_rgb, 0.0, 1.0), np.clip(out_alpha, 0.0, 1.0)], axis=2)
            
            # 🔧 修复：使用抖动转换以消除色阶分层
            result_8bit = _float_to_uint8_with_dithering(result, use_dithering=True)
            return Image.fromarray(result_8bit, 'RGBA')

        except Exception as e:
            safe_print(f"[错误] blend_normal失败: {e}")
            # 完全回退到PIL的简单合成
            result = bottom.copy()
            if opacity < 1.0:
                alpha = top.split()[-1]
                alpha = alpha.point(lambda p: int(p * opacity))
                top = top.copy()
                top.putalpha(alpha)
            result.paste(top, (0, 0), top)
            return result

    @staticmethod
    def _normalize_blend_mode_name(blend_mode: Union[str, int, None]) -> str:
        """标准化混合模式名称，统一为英文小写。"""
        if blend_mode is None:
            return 'normal'

        if isinstance(blend_mode, int):
            mode_map = {
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
            return mode_map.get(blend_mode, 'normal')

        mode = str(blend_mode).strip().lower()
        if not mode:
            return 'normal'

        zh_map = {
            '正常': 'normal',
            '正片叠底': 'multiply',
            '滤色': 'screen',
            '叠加': 'overlay',
            '柔光': 'soft_light',
            '强光': 'hard_light',
            '颜色减淡': 'color_dodge',
            '颜色加深': 'color_burn',
            '变暗': 'darken',
            '变亮': 'lighten',
            '差值': 'difference',
            '排除': 'exclusion',
            '色相': 'hue',
            '饱和度': 'saturation',
            '颜色': 'color',
            '明度': 'luminosity'
        }
        return zh_map.get(mode, mode)

    @staticmethod
    def _separable_blend_rgb(bottom_rgb: np.ndarray, top_rgb: np.ndarray, mode: str) -> np.ndarray:
        """计算不含 alpha 的可分离混合结果 B(Cb, Cs)。"""
        if mode == 'multiply':
            return bottom_rgb * top_rgb
        if mode == 'screen':
            return 1.0 - (1.0 - bottom_rgb) * (1.0 - top_rgb)
        if mode == 'overlay':
            return np.where(
                bottom_rgb <= 0.5,
                2.0 * bottom_rgb * top_rgb,
                1.0 - 2.0 * (1.0 - bottom_rgb) * (1.0 - top_rgb)
            )
        if mode == 'hard_light':
            return np.where(
                top_rgb <= 0.5,
                2.0 * bottom_rgb * top_rgb,
                1.0 - 2.0 * (1.0 - bottom_rgb) * (1.0 - top_rgb)
            )
        if mode == 'soft_light':
            d = np.where(
                bottom_rgb <= 0.25,
                ((16.0 * bottom_rgb - 12.0) * bottom_rgb + 4.0) * bottom_rgb,
                np.sqrt(np.clip(bottom_rgb, 0.0, 1.0))
            )
            return np.where(
                top_rgb <= 0.5,
                bottom_rgb - (1.0 - 2.0 * top_rgb) * bottom_rgb * (1.0 - bottom_rgb),
                bottom_rgb + (2.0 * top_rgb - 1.0) * (d - bottom_rgb)
            )
        if mode == 'color_dodge':
            return np.where(
                top_rgb >= 1.0 - 1e-10,
                1.0,
                np.minimum(1.0, bottom_rgb / np.maximum(1.0 - top_rgb, 1e-10))
            )
        if mode == 'color_burn':
            return np.where(
                top_rgb <= 1e-10,
                0.0,
                np.maximum(0.0, 1.0 - (1.0 - bottom_rgb) / np.maximum(top_rgb, 1e-10))
            )
        if mode == 'darken':
            return np.minimum(bottom_rgb, top_rgb)
        if mode == 'lighten':
            return np.maximum(bottom_rgb, top_rgb)
        if mode == 'difference':
            return np.abs(bottom_rgb - top_rgb)
        if mode == 'exclusion':
            return bottom_rgb + top_rgb - 2.0 * bottom_rgb * top_rgb
        return top_rgb

    @staticmethod
    def _blend_separable_rgba(bottom: Image.Image, top: Image.Image, mode: str, opacity: float = 1.0) -> Image.Image:
        """
        基于 W3C/PDF 组合公式的 RGBA 混合，正确处理半透明像素。
        Co_premul = (1-As)*Ab*Cb + (1-Ab)*As*Cs + Ab*As*B(Cb, Cs)
        Ao = As + Ab*(1-As)
        """
        if bottom.mode != 'RGBA':
            bottom = bottom.convert('RGBA')
        if top.mode != 'RGBA':
            top = top.convert('RGBA')
        if bottom.size != top.size:
            top = top.resize(bottom.size, Image.Resampling.LANCZOS)

        bottom_arr = np.array(bottom, dtype=np.float64) / 255.0
        top_arr = np.array(top, dtype=np.float64) / 255.0

        cb = np.clip(bottom_arr[:, :, :3], 0.0, 1.0)
        cs = np.clip(top_arr[:, :, :3], 0.0, 1.0)
        ab = np.clip(bottom_arr[:, :, 3:4], 0.0, 1.0)
        a_s = np.clip(top_arr[:, :, 3:4], 0.0, 1.0) * float(opacity)

        b_rgb = UnifiedAlphaCompositor._separable_blend_rgb(cb, cs, mode)

        out_alpha = a_s + ab * (1.0 - a_s)
        out_rgb_premul = (
            (1.0 - a_s) * ab * cb
            + (1.0 - ab) * a_s * cs
            + ab * a_s * b_rgb
        )

        safe_alpha = np.where(out_alpha > 1e-10, out_alpha, 1e-10)
        out_rgb = out_rgb_premul / safe_alpha

        result = np.concatenate([np.clip(out_rgb, 0.0, 1.0), np.clip(out_alpha, 0.0, 1.0)], axis=2)
        result_8bit = _float_to_uint8_with_dithering(result, use_dithering=True)
        return Image.fromarray(result_8bit, 'RGBA')

    @staticmethod
    def blend_with_mode(bottom: Image.Image, top: Image.Image, blend_mode: Union[str, int], opacity: float = 1.0) -> Image.Image:
        """统一混合入口，供预览/导出共享，避免多套实现不一致。"""
        mode = UnifiedAlphaCompositor._normalize_blend_mode_name(blend_mode)
        if mode == 'normal':
            return UnifiedAlphaCompositor.blend_photoshop_srgb(bottom, top, opacity)

        separable_modes = {
            'multiply', 'screen', 'overlay', 'soft_light', 'hard_light',
            'color_dodge', 'color_burn', 'darken', 'lighten', 'difference', 'exclusion'
        }
        if mode in separable_modes:
            return UnifiedAlphaCompositor._blend_separable_rgba(bottom, top, mode, opacity)

        # 非可分离模式暂无完整实现，回退到稳定 normal，保证链路一致性和可预期。
        return UnifiedAlphaCompositor.blend_photoshop_srgb(bottom, top, opacity)
    
    @staticmethod
    def _enhance_edges(image: Image.Image, strength: float = 1.0) -> Image.Image:
        """
        边缘增强处理 (静态方法)
        """
        if strength <= 0:
            return image
        
        try:
            # 使用PIL的边缘增强滤镜
            enhanced = image.filter(ImageFilter.EDGE_ENHANCE_MORE)
            
            # 混合原图和增强图
            if strength < 1.0:
                enhanced = Image.blend(image, enhanced, strength)
            
            return enhanced
        except Exception:
            return image

    @staticmethod
    def composite_layer(background: Image.Image, foreground: Image.Image,
                       position: Tuple[int, int], opacity: float = 1.0,
                       blend_mode: str = 'normal',
                       edge_enhancement: bool = False,
                       subpixel_precision: bool = True,
                       antialiasing_method: str = 'auto',
                       use_srgb_blending: bool = True) -> Image.Image:
        """
        高级图层合成 - 解决半透明和边缘问题
        
        Args:
            background: 背景图像
            foreground: 前景图像
            position: 位置 (x, y)
            opacity: 不透明度
            blend_mode: 混合模式
            edge_enhancement: 是否启用边缘增强
            subpixel_precision: 是否使用亚像素精度
            antialiasing_method: 抗锯齿方法
            use_srgb_blending: 是否使用sRGB空间混合（Photoshop标准），解决像素丢失问题
            
        Returns:
            合成后的图像
        """
        # 确保图像格式
        if background.mode != 'RGBA':
            background = background.convert('RGBA')
        if foreground.mode != 'RGBA':
            foreground = foreground.convert('RGBA')
        
        # 修复预乘alpha问题 - 解决PNG边缘黑边
        # 注意：自动检测预乘Alpha可能会误判深色半透明物体（如阴影），导致颜色变亮/失真
        # 因此默认禁用自动修复，除非明确确认输入是预乘Alpha
        # if PNG_OPTIMIZATION_AVAILABLE:
        #     try:
        #         foreground, _ = fix_premultiplied_alpha(foreground)
        #     except Exception as e:
        #         # 如果修复失败，继续使用原图
        #         pass

        # 边缘预处理
        if edge_enhancement:
            foreground = UnifiedAlphaCompositor._enhance_edges(foreground)
        
        # 创建结果图像
        result = background.copy()
        
        # 计算实际合成区域
        bg_w, bg_h = background.size
        fg_w, fg_h = foreground.size
        
        # 🔧 修复：确保坐标为整数，避免浮点数导致的裁剪误差
        x = int(round(position[0]))
        y = int(round(position[1]))
        
        # 计算裁剪区域
        left = max(0, -x)
        top = max(0, -y)
        right = min(fg_w, bg_w - x)
        bottom = min(fg_h, bg_h - y)
        
        # 如果没有重叠区域，直接返回背景
        if left >= right or top >= bottom:
            return result
        
        # 裁剪前景图像
        fg_cropped = foreground.crop((left, top, right, bottom))
        
        # 计算背景上的对应区域
        bg_left = max(0, x)
        bg_top = max(0, y)
        bg_right = bg_left + (right - left)
        bg_bottom = bg_top + (bottom - top)
        
        # 提取背景区域
        bg_region = background.crop((bg_left, bg_top, bg_right, bg_bottom))
        
        normalized_mode = UnifiedAlphaCompositor._normalize_blend_mode_name(blend_mode)

        # 执行混合
        if normalized_mode == 'normal':
            if use_srgb_blending:
                blended = UnifiedAlphaCompositor.blend_photoshop_srgb(bg_region, fg_cropped, opacity)
            else:
                blended = UnifiedAlphaCompositor.blend_normal(bg_region, fg_cropped, opacity)
        else:
            blended = UnifiedAlphaCompositor.blend_with_mode(
                bg_region, fg_cropped, normalized_mode, opacity
            )
        
        # 将混合结果粘贴回原图
        result.paste(blended, (bg_left, bg_top))
        
        return result
    
    def enhance_edges(self, image: Image.Image, strength: float = 1.0) -> Image.Image:
        """
        边缘增强处理
        
        Args:
            image: 输入图像
            strength: 增强强度
            
        Returns:
            边缘增强后的图像
        """
        if not self.edge_enhancement or strength <= 0:
            return image
        
        # 使用PIL的边缘增强滤镜
        enhanced = image.filter(ImageFilter.EDGE_ENHANCE_MORE)
        
        # 混合原图和增强图
        if strength < 1.0:
            enhanced = Image.blend(image, enhanced, strength)
        
        return enhanced
    
    def apply_antialiasing(self, image: Image.Image, method: str = 'lanczos') -> Image.Image:
        """
        应用抗锯齿处理
        
        Args:
            image: 输入图像
            method: 抗锯齿方法
            
        Returns:
            抗锯齿处理后的图像
        """
        if not self.use_antialiasing:
            return image
        
        # 获取原始尺寸
        original_size = image.size
        
        # 临时放大2倍
        enlarged = image.resize(
            (original_size[0] * 2, original_size[1] * 2),
            Image.LANCZOS
        )
        
        # 应用轻微的模糊
        blurred = enlarged.filter(ImageFilter.GaussianBlur(radius=0.5))
        
        # 缩回原尺寸
        result = blurred.resize(original_size, Image.LANCZOS)
        
        return result
    
    def composite_with_quality(self, background: Image.Image, foreground: Image.Image,
                              position: Tuple[int, int], opacity: float = 1.0,
                              blend_mode: str = 'normal',
                              apply_antialiasing: bool = None,
                              edge_strength: float = 0.0) -> Image.Image:
        """
        高质量合成 - 修复版本，不依赖缺失的模块

        Args:
            background: 背景图像
            foreground: 前景图像
            position: 位置
            opacity: 不透明度
            blend_mode: 混合模式
            apply_antialiasing: 是否应用抗锯齿
            edge_strength: 边缘增强强度

        Returns:
            高质量合成后的图像
        """
        try:
            safe_print(f"[统一合成器] 使用内置高质量合成方法")

            # 应用抗锯齿到前景图像
            if apply_antialiasing is None:
                apply_antialiasing = self.use_antialiasing

            if apply_antialiasing:
                try:
                    foreground = self.apply_antialiasing(foreground)
                except Exception as aa_e:
                    safe_print(f"[警告] 抗锯齿处理失败: {aa_e}")

            # 执行基础合成
            result = self.composite_layer(background, foreground, position, opacity, blend_mode)

            # 应用边缘增强
            if edge_strength > 0:
                try:
                    result = self.enhance_edges(result, edge_strength)
                except Exception as edge_e:
                    safe_print(f"[警告] 边缘增强失败: {edge_e}")

            return result

        except Exception as e:
            safe_print(f"[错误] 高质量合成失败: {e}，使用简单合成")
            # 最后的后备方案：使用最简单的PIL合成
            try:
                result = background.copy()
                if opacity < 1.0:
                    alpha = foreground.split()[-1]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    foreground = foreground.copy()
                    foreground.putalpha(alpha)

                x, y = position
                result.paste(foreground, (x, y), foreground)
                return result
            except Exception as final_e:
                safe_print(f"[严重错误] 所有合成方法都失败: {final_e}")
                return background
    
    @staticmethod
    def premultiply_alpha(image: Image.Image) -> np.ndarray:
        """预乘alpha处理"""
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        array = np.array(image, dtype=np.float32) / 255.0
        rgb = array[:, :, :3]
        alpha = array[:, :, 3:4]
        
        # 预乘处理
        premult_rgb = rgb * alpha
        
        return np.concatenate([premult_rgb, alpha], axis=2)
    
    @staticmethod
    def unpremultiply_alpha(array: np.ndarray) -> Image.Image:
        """去预乘alpha处理"""
        rgb = array[:, :, :3]
        alpha = array[:, :, 3:4]
        
        # 避免除零
        mask = alpha > 1e-6
        unpremult_rgb = np.zeros_like(rgb)
        unpremult_rgb[mask.squeeze()] = rgb[mask.squeeze()] / alpha[mask.squeeze()]
        
        result = np.concatenate([unpremult_rgb, alpha], axis=2)
        result = np.clip(result * 255, 0, 255).astype(np.uint8)
        
        return Image.fromarray(result, 'RGBA')

    @staticmethod
    def _enhance_edges(image: Image.Image) -> Image.Image:
        """边缘增强处理"""
        try:
            # 使用超级抗锯齿系统（如果可用）
            from app.utils.super_antialiasing import SuperAntialiasing

            # 根据图像大小选择合适的抗锯齿方法
            width, height = image.size
            total_pixels = width * height

            if total_pixels > 500000:  # 大图像使用快速方法
                return SuperAntialiasing.apply_super_antialiasing(image, 'fxaa', strength=1.2)
            elif total_pixels > 100000:  # 中等图像使用平衡方法
                return SuperAntialiasing.apply_super_antialiasing(image, 'smaa', strength=1.0)
            else:  # 小图像使用最高质量方法
                return SuperAntialiasing.apply_super_antialiasing(image, 'msaa_8x', strength=1.0)

        except ImportError:
            # 后备方案：传统边缘处理
            return UnifiedAlphaCompositor._fallback_edge_enhancement(image)

    @staticmethod
    def _fallback_edge_enhancement(image: Image.Image) -> Image.Image:
        """后备边缘增强方案"""
        if not CV2_AVAILABLE:
            return image

        try:
            # 转换为数组
            img_array = np.array(image, dtype=np.float32) / 255.0
            alpha = img_array[:,:,3]

            # 多尺度边缘检测
            alpha_uint8 = (alpha * 255).astype(np.uint8)

            # 使用不同参数的边缘检测
            edges_1 = cv2.Canny(alpha_uint8, 30, 100)
            edges_2 = cv2.Canny(alpha_uint8, 50, 150)
            edges_3 = cv2.Canny(alpha_uint8, 70, 200)

            # 合并边缘
            combined_edges = np.maximum(np.maximum(edges_1, edges_2), edges_3) > 0

            if np.any(combined_edges):
                # 多层高斯模糊
                alpha_blur_1 = cv2.GaussianBlur(alpha, (3, 3), 0.5)
                alpha_blur_2 = cv2.GaussianBlur(alpha, (5, 5), 1.0)

                # 形态学操作
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                alpha_smooth = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel)

                # 混合处理结果
                alpha_enhanced = np.where(combined_edges, alpha_blur_1, alpha_smooth)
                img_array[:,:,3] = alpha_enhanced

            # 转换回图像
            result_array = (img_array * 255).clip(0, 255).astype(np.uint8)
            return Image.fromarray(result_array, 'RGBA')

        except Exception as e:
            safe_print(f"[Alpha合成器] 边缘增强失败: {e}")
            return image

    @staticmethod
    def _subpixel_composite(background: Image.Image, foreground: Image.Image,
                           opacity: float, blend_mode: str) -> Image.Image:
        """亚像素精度合成"""
        # 使用高精度浮点运算
        bg_array = np.array(background, dtype=np.float64) / 255.0
        fg_array = np.array(foreground, dtype=np.float64) / 255.0

        # 应用不透明度
        fg_array[:,:,3] *= opacity

        # 根据混合模式进行合成
        if blend_mode == 'normal':
            result = UnifiedAlphaCompositor._porter_duff_source_over(bg_array, fg_array)
        elif blend_mode == 'multiply':
            result = UnifiedAlphaCompositor._blend_multiply_precise(bg_array, fg_array)
        elif blend_mode == 'screen':
            result = UnifiedAlphaCompositor._blend_screen_precise(bg_array, fg_array)
        else:
            result = UnifiedAlphaCompositor._porter_duff_source_over(bg_array, fg_array)

        # 🔧 修复：使用抖动转换以消除色阶分层
        result_8bit = _float_to_uint8_with_dithering(result, use_dithering=True)
        return Image.fromarray(result_8bit, 'RGBA')

    @staticmethod
    def _standard_composite(background: Image.Image, foreground: Image.Image,
                           opacity: float, blend_mode: str) -> Image.Image:
        """标准合成方法"""
        # 使用PIL的标准合成
        if opacity < 1.0:
            # 创建带透明度的前景
            fg_with_opacity = Image.new('RGBA', foreground.size, (0, 0, 0, 0))
            fg_with_opacity = Image.blend(fg_with_opacity, foreground, opacity)
            foreground = fg_with_opacity

        # 使用PIL的paste方法
        result = background.copy()
        result.paste(foreground, (0, 0), foreground)
        return result


    # 添加精确混合方法（从perfect_alpha_blend.py合并）
    @staticmethod
    def _porter_duff_source_over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
        """Porter-Duff source over 合成算法"""
        # 分离颜色和alpha通道
        dst_rgb = dst[:,:,:3]
        dst_alpha = dst[:,:,3:4]
        src_rgb = src[:,:,:3]
        src_alpha = src[:,:,3:4]

        # 计算输出alpha
        out_alpha = src_alpha + dst_alpha * (1 - src_alpha)

        # 避免除零
        safe_out_alpha = np.where(out_alpha > 1e-10, out_alpha, 1e-10)

        # 计算输出颜色
        out_rgb = (src_rgb * src_alpha + dst_rgb * dst_alpha * (1 - src_alpha)) / safe_out_alpha

        # 组合结果
        result = np.concatenate([out_rgb, out_alpha], axis=2)
        return np.clip(result, 0, 1)

    @staticmethod
    def _blend_multiply_precise(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
        """精确的正片叠底混合"""
        # 分离通道
        bottom_rgb = bottom[:,:,:3]
        bottom_alpha = bottom[:,:,3:4]
        top_rgb = top[:,:,:3]
        top_alpha = top[:,:,3:4]

        blended_rgb = bottom_rgb * top_rgb
        result_alpha = top_alpha + bottom_alpha * (1.0 - top_alpha)
        safe_alpha = np.where(result_alpha > 1e-10, result_alpha, 1e-10)
        result_rgb_premul = (
            (1.0 - top_alpha) * bottom_alpha * bottom_rgb
            + (1.0 - bottom_alpha) * top_alpha * top_rgb
            + bottom_alpha * top_alpha * blended_rgb
        )
        result_rgb = result_rgb_premul / safe_alpha

        # 组合结果
        result = np.concatenate([result_rgb, result_alpha], axis=2)
        return np.clip(result, 0, 1)

    @staticmethod
    def _blend_screen_precise(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
        """精确的滤色混合"""
        # 分离通道
        bottom_rgb = bottom[:,:,:3]
        bottom_alpha = bottom[:,:,3:4]
        top_rgb = top[:,:,:3]
        top_alpha = top[:,:,3:4]

        blended_rgb = 1.0 - (1.0 - bottom_rgb) * (1.0 - top_rgb)
        result_alpha = top_alpha + bottom_alpha * (1.0 - top_alpha)
        safe_alpha = np.where(result_alpha > 1e-10, result_alpha, 1e-10)
        result_rgb_premul = (
            (1.0 - top_alpha) * bottom_alpha * bottom_rgb
            + (1.0 - bottom_alpha) * top_alpha * top_rgb
            + bottom_alpha * top_alpha * blended_rgb
        )
        result_rgb = result_rgb_premul / safe_alpha

        # 组合结果
        result = np.concatenate([result_rgb, result_alpha], axis=2)
        return np.clip(result, 0, 1)

    def optimize_png_rendering(self, image: Image.Image,
                              quality_level: str = 'high',
                              fix_black_edges: bool = True,
                              apply_antialiasing: bool = True,
                              enhance_edges: bool = True) -> Image.Image:
        """
        优化PNG图像渲染，解决黑边和锯齿问题

        Args:
            image: 输入的PNG图像
            quality_level: 质量级别 ('low', 'medium', 'high', 'ultra')
            fix_black_edges: 是否修复黑边问题
            apply_antialiasing: 是否应用抗锯齿
            enhance_edges: 是否增强边缘

        Returns:
            优化后的图像
        """
        if not PNG_OPTIMIZATION_AVAILABLE:
            # 如果PNG优化模块不可用，使用基础优化
            return self._basic_png_optimization(image)

        try:
            # 使用高级PNG优化
            return optimize_png_image(
                image, quality_level, fix_black_edges,
                apply_antialiasing, enhance_edges
            )
        except Exception as e:
            safe_print(f"[WARNING] PNG高级优化失败，使用基础优化: {e}")
            return self._basic_png_optimization(image)

    def fix_png_black_edges(self, image: Image.Image) -> Tuple[Image.Image, dict]:
        """
        修复PNG图像的黑边问题

        Args:
            image: 输入图像

        Returns:
            修复后的图像和检测信息
        """
        if not PNG_OPTIMIZATION_AVAILABLE:
            return self._basic_black_edge_fix(image), {'method': 'basic'}

        try:
            return fix_premultiplied_alpha(image)
        except Exception as e:
            safe_print(f"[WARNING] 预乘Alpha修复失败，使用基础修复: {e}")
            return self._basic_black_edge_fix(image), {'method': 'basic', 'error': str(e)}

    def apply_png_antialiasing(self, image: Image.Image,
                              quality: str = 'high',
                              strength: float = 1.0) -> Image.Image:
        """
        对PNG图像应用抗锯齿

        Args:
            image: 输入图像
            quality: 质量级别
            strength: 抗锯齿强度

        Returns:
            抗锯齿后的图像
        """
        if not PNG_OPTIMIZATION_AVAILABLE:
            return self._basic_antialiasing(image, strength)

        try:
            return apply_png_antialiasing(image, quality, strength)
        except Exception as e:
            safe_print(f"[WARNING] 高级抗锯齿失败，使用基础抗锯齿: {e}")
            return self._basic_antialiasing(image, strength)

    def _basic_png_optimization(self, image: Image.Image) -> Image.Image:
        """基础PNG优化（不依赖高级模块）"""
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # 基础黑边修复
        fixed_image, _ = self._basic_black_edge_fix(image)

        # 基础抗锯齿
        result = self._basic_antialiasing(fixed_image, 1.0)

        return result

    def _basic_black_edge_fix(self, image: Image.Image) -> Image.Image:
        """基础黑边修复"""
        # 简单的Alpha通道处理
        r, g, b, a = image.split()

        # 对Alpha通道进行轻微模糊以减少黑边
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=0.3))

        return Image.merge('RGBA', (r, g, b, a_smooth))

    def _basic_antialiasing(self, image: Image.Image, strength: float) -> Image.Image:
        """基础抗锯齿"""
        r, g, b, a = image.split()

        # 对Alpha通道应用高斯模糊
        blur_radius = max(0.3, min(2.0, strength * 0.8))
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        return Image.merge('RGBA', (r, g, b, a_smooth))

    def fix_png_dark_edges(self, image: Image.Image,
                          background_color: Optional[Tuple[int, int, int]] = None,
                          fix_strength: float = 1.0) -> Image.Image:
        """
        修复PNG图像的深色边缘问题

        Args:
            image: 输入PNG图像
            background_color: 背景颜色RGB (可选)
            fix_strength: 修复强度 (0.0-2.0)

        Returns:
            修复后的图像
        """
        if not PNG_OPTIMIZATION_AVAILABLE:
            return self._basic_dark_edge_fix(image, background_color)

        try:
            return fix_png_dark_edges_direct(image, background_color, fix_strength)
        except Exception as e:
            safe_print(f"[WARNING] PNG深色边缘修复失败，使用基础修复: {e}")
            return self._basic_dark_edge_fix(image, background_color)

    def auto_fix_png_for_background(self, image: Image.Image,
                                   background_color: Tuple[int, int, int]) -> Image.Image:
        """
        自动修复PNG图像以适配特定背景色

        Args:
            image: 输入PNG图像
            background_color: 目标背景颜色RGB

        Returns:
            优化后的图像
        """
        if not PNG_OPTIMIZATION_AVAILABLE:
            return self._basic_dark_edge_fix(image, background_color)

        try:
            return auto_fix_png_for_background_direct(image, background_color)
        except Exception as e:
            safe_print(f"[WARNING] PNG背景适配失败，使用基础修复: {e}")
            return self._basic_dark_edge_fix(image, background_color)

    def _basic_dark_edge_fix(self, image: Image.Image,
                           background_color: Optional[Tuple[int, int, int]] = None) -> Image.Image:
        """基础深色边缘修复"""
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        r, g, b, a = image.split()

        # 对Alpha通道进行更强的模糊以减少深色边缘
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=1.2))

        # 如果提供了背景色，进行简单的颜色校正
        if background_color:
            # 转换为numpy进行处理
            import numpy as np
            img_array = np.array(image, dtype=np.float64) / 255.0

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")

            rgb = img_array[:, :, :3]
            alpha = img_array[:, :, 3]
            bg_color = np.array(background_color) / 255.0

            # 对半透明区域进行颜色校正
            semi_transparent = (alpha > 0.1) & (alpha < 0.9)

            if np.any(semi_transparent):
                # 简单的背景色混合
                for i in range(3):
                    channel = rgb[:, :, i]
                    corrected = channel * 0.8 + bg_color[i] * 0.2
                    rgb[semi_transparent, i] = corrected[semi_transparent]

            # 转换回图像
            result_array = np.concatenate([rgb, alpha[:, :, np.newaxis]], axis=2)
            result_array = np.clip(result_array, 0, 1)
            result_8bit = (result_array * 255).astype(np.uint8)

            return Image.fromarray(result_8bit, 'RGBA')

        return Image.merge('RGBA', (r, g, b, a_smooth))


# 创建全局实例
unified_alpha_compositor = UnifiedAlphaCompositor()


# 向后兼容的函数接口
def blend_images(bottom: Image.Image, top: Image.Image, opacity: float = 1.0) -> Image.Image:
    """向后兼容的图像混合函数"""
    return unified_alpha_compositor.blend_normal(bottom, top, opacity)


# PNG渲染优化的便捷函数
def optimize_png_rendering(image: Image.Image,
                          quality_level: str = 'high',
                          fix_black_edges: bool = True,
                          apply_antialiasing: bool = True,
                          enhance_edges: bool = True) -> Image.Image:
    """
    PNG渲染优化便捷函数

    Args:
        image: 输入的PNG图像
        quality_level: 质量级别 ('low', 'medium', 'high', 'ultra')
        fix_black_edges: 是否修复黑边问题
        apply_antialiasing: 是否应用抗锯齿
        enhance_edges: 是否增强边缘

    Returns:
        优化后的图像
    """
    return unified_alpha_compositor.optimize_png_rendering(
        image, quality_level, fix_black_edges, apply_antialiasing, enhance_edges
    )


def fix_png_black_edges(image: Image.Image) -> Tuple[Image.Image, dict]:
    """
    修复PNG黑边便捷函数

    Args:
        image: 输入图像

    Returns:
        修复后的图像和检测信息
    """
    return unified_alpha_compositor.fix_png_black_edges(image)


def apply_png_antialiasing(image: Image.Image,
                          quality: str = 'high',
                          strength: float = 1.0) -> Image.Image:
    """
    PNG抗锯齿便捷函数

    Args:
        image: 输入图像
        quality: 质量级别
        strength: 抗锯齿强度

    Returns:
        抗锯齿后的图像
    """
    return unified_alpha_compositor.apply_png_antialiasing(image, quality, strength)


def fix_png_dark_edges(image: Image.Image,
                      background_color: Optional[Tuple[int, int, int]] = None,
                      fix_strength: float = 1.0) -> Image.Image:
    """
    修复PNG深色边缘便捷函数

    Args:
        image: 输入PNG图像
        background_color: 背景颜色RGB (可选)
        fix_strength: 修复强度 (0.0-2.0)

    Returns:
        修复后的图像
    """
    return unified_alpha_compositor.fix_png_dark_edges(image, background_color, fix_strength)


def auto_fix_png_for_background(image: Image.Image,
                               background_color: Tuple[int, int, int]) -> Image.Image:
    """
    自动修复PNG图像以适配特定背景色便捷函数

    Args:
        image: 输入PNG图像
        background_color: 目标背景颜色RGB

    Returns:
        优化后的图像
    """
    return unified_alpha_compositor.auto_fix_png_for_background(image, background_color)


def composite_layers(background: Image.Image, foreground: Image.Image,
                    position: Tuple[int, int], opacity: float = 1.0,
                    blend_mode: str = 'normal') -> Image.Image:
    """向后兼容的图层合成函数"""
    return unified_alpha_compositor.composite_layer(background, foreground, position, opacity, blend_mode)


# 导出的公共接口
__all__ = [
    'UnifiedAlphaCompositor',
    'BlendMode', 
    'unified_alpha_compositor',
    'blend_images',
    'composite_layers'
]
