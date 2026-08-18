"""
专业级混合模式引擎
实现完整的Photoshop混合模式集合，包括：
1. 所有标准混合模式
2. 颜色空间转换
3. 高精度计算
4. HSV/HSL混合模式
5. 特殊效果混合

职责边界（R6 收敛说明）：
本模块**仅**经 ``AdvancedCompositorManager._standard_composite`` 在 quality
模式被调用（``ProfessionalBlender.blend``），不对外直接暴露。普通混合模式
入口 ``document_blend.Blender`` 现已委托 ``unified_alpha_compositor.blend_with_mode``，
请勿在默认渲染/导出路径直接调用本模块。
"""

import numpy as np
from PIL import Image
import cv2
from typing import Tuple, Optional, Union
from enum import Enum
import colorsys


class BlendMode(Enum):
    """完整的混合模式枚举"""
    # 基础混合模式
    NORMAL = "normal"
    DISSOLVE = "dissolve"
    
    # 变暗混合模式
    DARKEN = "darken"
    MULTIPLY = "multiply"
    COLOR_BURN = "color_burn"
    LINEAR_BURN = "linear_burn"
    DARKER_COLOR = "darker_color"
    
    # 变亮混合模式
    LIGHTEN = "lighten"
    SCREEN = "screen"
    COLOR_DODGE = "color_dodge"
    LINEAR_DODGE = "linear_dodge"
    LIGHTER_COLOR = "lighter_color"
    
    # 对比度混合模式
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"
    VIVID_LIGHT = "vivid_light"
    LINEAR_LIGHT = "linear_light"
    PIN_LIGHT = "pin_light"
    HARD_MIX = "hard_mix"
    
    # 比较混合模式
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"
    SUBTRACT = "subtract"
    DIVIDE = "divide"
    
    # 颜色混合模式
    HUE = "hue"
    SATURATION = "saturation"
    COLOR = "color"
    LUMINOSITY = "luminosity"


class ProfessionalBlender:
    """专业级混合器"""
    
    def __init__(self, use_16bit: bool = False, color_space: str = 'srgb'):
        """
        初始化专业混合器
        
        Args:
            use_16bit: 是否使用16位精度
            color_space: 颜色空间 ('srgb', 'linear', 'lab')
        """
        self.use_16bit = use_16bit
        self.color_space = color_space
        self.dtype = np.float64 if use_16bit else np.float32
        
        # 初始化颜色空间转换参数
        self._init_color_space_params()
    
    def _init_color_space_params(self):
        """初始化颜色空间转换参数"""
        # sRGB gamma参数
        self.srgb_gamma = 2.4
        self.srgb_alpha = 0.055
        self.srgb_threshold = 0.04045
        
        # XYZ转换矩阵
        self.rgb_to_xyz = np.array([
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041]
        ], dtype=self.dtype)
        
        self.xyz_to_rgb = np.linalg.inv(self.rgb_to_xyz)
    
    def blend(self, base: Image.Image, overlay: Image.Image, 
             mode: BlendMode, opacity: float = 1.0) -> Image.Image:
        """
        执行专业级混合
        
        Args:
            base: 底层图像
            overlay: 覆盖层图像
            mode: 混合模式
            opacity: 不透明度 (0.0-1.0)
            
        Returns:
            混合后的图像
        """
        # 确保图像格式一致
        base = base.convert('RGBA')
        overlay = overlay.convert('RGBA')
        
        # 尺寸检查
        if base.size != overlay.size:
            overlay = overlay.resize(base.size, Image.LANCZOS)
        
        # 转换为数组
        base_array = self._image_to_array(base)
        overlay_array = self._image_to_array(overlay)
        
        # 应用不透明度
        if opacity < 1.0:
            overlay_array[:,:,3] *= opacity
        
        # 执行混合
        result_array = self._apply_blend_mode(base_array, overlay_array, mode)
        
        # 转换回图像
        return self._array_to_image(result_array)
    
    def _image_to_array(self, image: Image.Image) -> np.ndarray:
        """图像转数组，包含颜色空间转换"""
        array = np.array(image, dtype=self.dtype) / 255.0
        
        # 颜色空间转换
        if self.color_space == 'linear':
            array[:,:,:3] = self._srgb_to_linear(array[:,:,:3])
        elif self.color_space == 'lab':
            array[:,:,:3] = self._rgb_to_lab(array[:,:,:3])
        
        return array
    
    def _array_to_image(self, array: np.ndarray) -> Image.Image:
        """数组转图像，包含颜色空间转换"""
        # 颜色空间转换
        if self.color_space == 'linear':
            array[:,:,:3] = self._linear_to_srgb(array[:,:,:3])
        elif self.color_space == 'lab':
            array[:,:,:3] = self._lab_to_rgb(array[:,:,:3])
        
        # 转换为8位
        array = (array * 255.0).clip(0, 255).astype(np.uint8)
        return Image.fromarray(array)
    
    def _srgb_to_linear(self, rgb: np.ndarray) -> np.ndarray:
        """sRGB到线性RGB转换"""
        return np.where(rgb <= self.srgb_threshold,
                       rgb / 12.92,
                       np.power((rgb + self.srgb_alpha) / (1 + self.srgb_alpha), self.srgb_gamma))
    
    def _linear_to_srgb(self, rgb: np.ndarray) -> np.ndarray:
        """线性RGB到sRGB转换"""
        return np.where(rgb <= 0.0031308,
                       rgb * 12.92,
                       (1 + self.srgb_alpha) * np.power(rgb, 1/self.srgb_gamma) - self.srgb_alpha)
    
    def _rgb_to_lab(self, rgb: np.ndarray) -> np.ndarray:
        """RGB到LAB转换"""
        # 先转换到XYZ
        xyz = np.dot(rgb, self.rgb_to_xyz.T)
        
        # XYZ到LAB
        xyz = xyz / np.array([0.95047, 1.0, 1.08883])  # D65白点
        
        def f(t):
            return np.where(t > 0.008856, np.power(t, 1/3), (7.787 * t + 16/116))
        
        fx, fy, fz = f(xyz[:,:,0]), f(xyz[:,:,1]), f(xyz[:,:,2])
        
        L = 116 * fy - 16
        a = 500 * (fx - fy)
        b = 200 * (fy - fz)
        
        # 归一化到0-1范围
        L = L / 100.0
        a = (a + 128) / 255.0
        b = (b + 128) / 255.0
        
        return np.stack([L, a, b], axis=2)
    
    def _lab_to_rgb(self, lab: np.ndarray) -> np.ndarray:
        """LAB到RGB转换"""
        # 反归一化
        L = lab[:,:,0] * 100.0
        a = lab[:,:,1] * 255.0 - 128
        b = lab[:,:,2] * 255.0 - 128
        
        # LAB到XYZ
        fy = (L + 16) / 116
        fx = a / 500 + fy
        fz = fy - b / 200
        
        def f_inv(t):
            return np.where(t > 0.206893, np.power(t, 3), (t - 16/116) / 7.787)
        
        xyz = np.stack([f_inv(fx), f_inv(fy), f_inv(fz)], axis=2)
        xyz = xyz * np.array([0.95047, 1.0, 1.08883])  # D65白点
        
        # XYZ到RGB
        rgb = np.dot(xyz, self.xyz_to_rgb.T)
        return np.clip(rgb, 0, 1)
    
    def _apply_blend_mode(self, base: np.ndarray, overlay: np.ndarray, mode: BlendMode) -> np.ndarray:
        """应用混合模式"""
        # 分离颜色和alpha通道
        base_rgb = base[:,:,:3]
        base_alpha = base[:,:,3:4]
        overlay_rgb = overlay[:,:,:3]
        overlay_alpha = overlay[:,:,3:4]
        
        # 应用混合算法
        if mode == BlendMode.NORMAL:
            blended_rgb = overlay_rgb
        elif mode == BlendMode.DISSOLVE:
            blended_rgb = self._dissolve_blend(base_rgb, overlay_rgb, overlay_alpha)
        elif mode == BlendMode.DARKEN:
            blended_rgb = np.minimum(base_rgb, overlay_rgb)
        elif mode == BlendMode.MULTIPLY:
            blended_rgb = base_rgb * overlay_rgb
        elif mode == BlendMode.COLOR_BURN:
            blended_rgb = self._color_burn_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.LINEAR_BURN:
            blended_rgb = np.maximum(base_rgb + overlay_rgb - 1, 0)
        elif mode == BlendMode.DARKER_COLOR:
            blended_rgb = self._darker_color_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.LIGHTEN:
            blended_rgb = np.maximum(base_rgb, overlay_rgb)
        elif mode == BlendMode.SCREEN:
            blended_rgb = 1 - (1 - base_rgb) * (1 - overlay_rgb)
        elif mode == BlendMode.COLOR_DODGE:
            blended_rgb = self._color_dodge_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.LINEAR_DODGE:
            blended_rgb = np.minimum(base_rgb + overlay_rgb, 1)
        elif mode == BlendMode.LIGHTER_COLOR:
            blended_rgb = self._lighter_color_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.OVERLAY:
            blended_rgb = self._overlay_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.SOFT_LIGHT:
            blended_rgb = self._soft_light_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.HARD_LIGHT:
            blended_rgb = self._hard_light_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.VIVID_LIGHT:
            blended_rgb = self._vivid_light_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.LINEAR_LIGHT:
            blended_rgb = self._linear_light_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.PIN_LIGHT:
            blended_rgb = self._pin_light_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.HARD_MIX:
            blended_rgb = self._hard_mix_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.DIFFERENCE:
            blended_rgb = np.abs(base_rgb - overlay_rgb)
        elif mode == BlendMode.EXCLUSION:
            blended_rgb = base_rgb + overlay_rgb - 2 * base_rgb * overlay_rgb
        elif mode == BlendMode.SUBTRACT:
            blended_rgb = np.maximum(base_rgb - overlay_rgb, 0)
        elif mode == BlendMode.DIVIDE:
            blended_rgb = self._divide_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.HUE:
            blended_rgb = self._hue_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.SATURATION:
            blended_rgb = self._saturation_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.COLOR:
            blended_rgb = self._color_blend(base_rgb, overlay_rgb)
        elif mode == BlendMode.LUMINOSITY:
            blended_rgb = self._luminosity_blend(base_rgb, overlay_rgb)
        else:
            blended_rgb = overlay_rgb  # 默认为正常模式
        
        # Alpha合成
        result_alpha = overlay_alpha + base_alpha * (1 - overlay_alpha)
        
        # 颜色混合（考虑alpha）
        alpha_blend_factor = np.where(result_alpha > 1e-10, overlay_alpha / result_alpha, 0)
        result_rgb = blended_rgb * alpha_blend_factor + base_rgb * (1 - alpha_blend_factor)
        
        return np.concatenate([result_rgb, result_alpha], axis=2)
    
    def _dissolve_blend(self, base: np.ndarray, overlay: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """溶解混合模式"""
        # 基于alpha值的随机溶解效果
        noise = np.random.random(base.shape)
        mask = noise < alpha
        return np.where(mask, overlay, base)
    
    def _color_burn_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """颜色加深混合模式"""
        return np.where(overlay <= 1e-10, 0, np.maximum(0, 1 - (1 - base) / overlay))
    
    def _color_dodge_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """颜色减淡混合模式"""
        return np.where(overlay >= 1 - 1e-10, 1, np.minimum(1, base / (1 - overlay)))
    
    def _darker_color_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """较暗颜色混合模式"""
        base_lum = np.sum(base * [0.299, 0.587, 0.114], axis=2, keepdims=True)
        overlay_lum = np.sum(overlay * [0.299, 0.587, 0.114], axis=2, keepdims=True)
        return np.where(base_lum < overlay_lum, base, overlay)
    
    def _lighter_color_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """较亮颜色混合模式"""
        base_lum = np.sum(base * [0.299, 0.587, 0.114], axis=2, keepdims=True)
        overlay_lum = np.sum(overlay * [0.299, 0.587, 0.114], axis=2, keepdims=True)
        return np.where(base_lum > overlay_lum, base, overlay)
    
    def _overlay_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """叠加混合模式"""
        mask = base < 0.5
        return np.where(mask, 2 * base * overlay, 1 - 2 * (1 - base) * (1 - overlay))
    
    def _soft_light_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """柔光混合模式（Photoshop算法）"""
        mask = overlay <= 0.5
        result1 = base - (1 - 2 * overlay) * base * (1 - base)
        d = np.where(base <= 0.25, ((16 * base - 12) * base + 4) * base, np.sqrt(base))
        result2 = base + (2 * overlay - 1) * (d - base)
        return np.where(mask, result1, result2)
    
    def _hard_light_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """强光混合模式"""
        mask = overlay < 0.5
        return np.where(mask, 2 * base * overlay, 1 - 2 * (1 - base) * (1 - overlay))
    
    def _vivid_light_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """亮光混合模式"""
        mask = overlay < 0.5
        burn = np.where(overlay <= 1e-10, 0, np.maximum(0, 1 - (1 - base) / (2 * overlay)))
        dodge = np.where(overlay >= 1 - 1e-10, 1, np.minimum(1, base / (2 * (1 - overlay))))
        return np.where(mask, burn, dodge)
    
    def _linear_light_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """线性光混合模式"""
        return np.clip(base + 2 * overlay - 1, 0, 1)
    
    def _pin_light_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """点光混合模式"""
        mask = overlay < 0.5
        return np.where(mask, np.minimum(base, 2 * overlay), np.maximum(base, 2 * overlay - 1))
    
    def _hard_mix_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """实色混合模式"""
        return np.where(base + overlay < 1, 0, 1)
    
    def _divide_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """除法混合模式"""
        return np.where(overlay <= 1e-10, 1, np.minimum(1, base / overlay))
    
    def _hue_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """色相混合模式"""
        return self._hsv_blend(base, overlay, blend_h=True, blend_s=False, blend_v=False)
    
    def _saturation_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """饱和度混合模式"""
        return self._hsv_blend(base, overlay, blend_h=False, blend_s=True, blend_v=False)
    
    def _color_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """颜色混合模式"""
        return self._hsv_blend(base, overlay, blend_h=True, blend_s=True, blend_v=False)
    
    def _luminosity_blend(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """明度混合模式"""
        return self._hsv_blend(base, overlay, blend_h=False, blend_s=False, blend_v=True)
    
    def _hsv_blend(self, base: np.ndarray, overlay: np.ndarray, 
                   blend_h: bool, blend_s: bool, blend_v: bool) -> np.ndarray:
        """HSV空间混合"""
        # 转换到HSV空间
        base_hsv = self._rgb_to_hsv(base)
        overlay_hsv = self._rgb_to_hsv(overlay)
        
        # 选择性混合通道
        result_hsv = base_hsv.copy()
        if blend_h:
            result_hsv[:,:,0] = overlay_hsv[:,:,0]
        if blend_s:
            result_hsv[:,:,1] = overlay_hsv[:,:,1]
        if blend_v:
            result_hsv[:,:,2] = overlay_hsv[:,:,2]
        
        # 转换回RGB
        return self._hsv_to_rgb(result_hsv)
    
    def _rgb_to_hsv(self, rgb: np.ndarray) -> np.ndarray:
        """RGB到HSV转换"""
        # 使用向量化的colorsys转换
        h, w, c = rgb.shape
        rgb_flat = rgb.reshape(-1, 3)
        hsv_flat = np.array([colorsys.rgb_to_hsv(r, g, b) for r, g, b in rgb_flat])
        return hsv_flat.reshape(h, w, c)
    
    def _hsv_to_rgb(self, hsv: np.ndarray) -> np.ndarray:
        """HSV到RGB转换"""
        # 使用向量化的colorsys转换
        h, w, c = hsv.shape
        hsv_flat = hsv.reshape(-1, 3)
        rgb_flat = np.array([colorsys.hsv_to_rgb(h, s, v) for h, s, v in hsv_flat])
        return rgb_flat.reshape(h, w, c)
