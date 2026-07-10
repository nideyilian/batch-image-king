"""
Photoshop级图像合成引擎
实现专业级的图像合成功能，包括：
1. 高精度半透明处理
2. 专业级混合模式
3. 边缘保护和抗锯齿
4. 颜色空间管理
5. 内存优化

职责边界（R6 收敛说明）：
本模块**仅**经 ``AdvancedCompositorManager`` 在 quality 模式被调用
（``_advanced_composite`` 路径），不对外直接暴露。默认渲染/导出主链路
已统一收敛到 ``app.utils.unified_alpha_compositor``，二者形成「平衡/默认
走 unified、quality 走本引擎」的双链路，禁止在预览/导出默认路径直接调用。
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import cv2
from typing import Tuple, Optional, Union, List
from enum import Enum
import warnings

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        safe_print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            safe_print(f"[DEBUG] {ascii_message}")
        except Exception:
            # 最后的备选方案
            safe_print("[DEBUG] Message encoding failed")


# 抑制NumPy警告
warnings.filterwarnings('ignore', category=RuntimeWarning)


class BlendMode(Enum):
    """专业级混合模式枚举"""
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
    HUE = "hue"
    SATURATION = "saturation"
    COLOR = "color"
    LUMINOSITY = "luminosity"
    LINEAR_BURN = "linear_burn"
    LINEAR_DODGE = "linear_dodge"
    VIVID_LIGHT = "vivid_light"
    LINEAR_LIGHT = "linear_light"
    PIN_LIGHT = "pin_light"
    HARD_MIX = "hard_mix"


class ColorSpace(Enum):
    """颜色空间枚举"""
    SRGB = "srgb"
    LINEAR_RGB = "linear_rgb"
    LAB = "lab"
    HSV = "hsv"


class PhotoshopCompositor:
    """Photoshop级图像合成器"""
    
    def __init__(self, color_space: ColorSpace = ColorSpace.SRGB, 
                 use_16bit: bool = False, enable_gpu: bool = False):
        """
        初始化合成器
        
        Args:
            color_space: 工作颜色空间
            use_16bit: 是否使用16位精度
            enable_gpu: 是否启用GPU加速（需要OpenCV GPU支持）
        """
        self.color_space = color_space
        self.use_16bit = use_16bit
        self.enable_gpu = enable_gpu
        self.dtype = np.float64 if use_16bit else np.float32
        
        # 初始化颜色空间转换矩阵
        self._init_color_matrices()
        
        # GPU检查
        if enable_gpu:
            self._check_gpu_support()
    
    def _init_color_matrices(self):
        """初始化颜色空间转换矩阵"""
        # sRGB到线性RGB的转换参数
        self.srgb_gamma = 2.4
        self.srgb_alpha = 0.055
        self.srgb_threshold = 0.04045
        
        # XYZ色彩空间转换矩阵（D65白点）
        self.rgb_to_xyz = np.array([
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041]
        ], dtype=self.dtype)
        
        self.xyz_to_rgb = np.linalg.inv(self.rgb_to_xyz)
    
    def _check_gpu_support(self):
        """检查GPU支持"""
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                safe_print(f"[INFO] 检测到 {cv2.cuda.getCudaEnabledDeviceCount()} 个CUDA设备")
                self.gpu_available = True
            else:
                safe_print("[INFO] 未检测到CUDA设备，使用CPU处理")
                self.gpu_available = False
                self.enable_gpu = False
        except Exception:
            safe_print("[INFO] OpenCV未编译CUDA支持，使用CPU处理")
            self.gpu_available = False
            self.enable_gpu = False
    
    def composite_layers(self, layers: List[dict], canvas_size: Tuple[int, int],
                        background_color: Tuple[int, int, int, int] = (0, 0, 0, 0)) -> Image.Image:
        """
        合成多个图层
        
        Args:
            layers: 图层列表，每个图层包含 {'image': PIL.Image, 'blend_mode': BlendMode, 
                   'opacity': float, 'position': (x, y), 'mask': PIL.Image}
            canvas_size: 画布尺寸 (width, height)
            background_color: 背景颜色 (r, g, b, a)
            
        Returns:
            PIL.Image: 合成后的图像
        """
        width, height = canvas_size
        
        # 创建背景画布
        canvas = self._create_canvas(width, height, background_color)
        
        # 按顺序合成每个图层
        for layer in layers:
            canvas = self._composite_single_layer(canvas, layer)
        
        # 转换回PIL图像
        return self._array_to_pil(canvas)
    
    def _create_canvas(self, width: int, height: int, 
                      color: Tuple[int, int, int, int]) -> np.ndarray:
        """创建画布"""
        canvas = np.full((height, width, 4), color, dtype=self.dtype)
        if self.dtype == np.float32 or self.dtype == np.float64:
            canvas /= 255.0
        return canvas
    
    def _composite_single_layer(self, canvas: np.ndarray, layer: dict) -> np.ndarray:
        """合成单个图层"""
        image = layer['image']
        blend_mode = layer.get('blend_mode', BlendMode.NORMAL)
        opacity = layer.get('opacity', 1.0)
        position = layer.get('position', (0, 0))
        mask = layer.get('mask', None)
        
        # 转换图像为数组
        layer_array = self._pil_to_array(image)
        
        # 应用蒙版
        if mask:
            mask_array = self._pil_to_array(mask.convert('L'))
            layer_array[:,:,3] *= mask_array[:,:,0]
        
        # 应用不透明度
        if opacity < 1.0:
            layer_array[:,:,3] *= opacity
        
        # 定位图层
        positioned_layer = self._position_layer(layer_array, canvas.shape[:2], position)
        
        # 执行混合
        return self._blend_layers(canvas, positioned_layer, blend_mode)
    
    def _pil_to_array(self, image: Image.Image) -> np.ndarray:
        """PIL图像转换为数组"""
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        array = np.array(image, dtype=self.dtype)
        if self.dtype == np.float32 or self.dtype == np.float64:
            array /= 255.0
        
        # 颜色空间转换
        if self.color_space == ColorSpace.LINEAR_RGB:
            array[:,:,:3] = self._srgb_to_linear(array[:,:,:3])
        
        return array
    
    def _array_to_pil(self, array: np.ndarray) -> Image.Image:
        """数组转换为PIL图像"""
        # 颜色空间转换
        if self.color_space == ColorSpace.LINEAR_RGB:
            array[:,:,:3] = self._linear_to_srgb(array[:,:,:3])
        
        # 🔧 修复：使用抖动转换以消除色阶分层
        if self.dtype == np.float32 or self.dtype == np.float64:
            # 确保在0-1范围内
            array = np.clip(array, 0.0, 1.0)
            
            # 导入抖动函数
            try:
                from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
                array = _float_to_uint8_with_dithering(array, use_dithering=True)
            except ImportError:
                # 后备方案：使用四舍五入
                array = np.round(array * 255.0).astype(np.uint8)
        else:
            array = array.astype(np.uint8)
        
        return Image.fromarray(array, 'RGBA')
    
    def _srgb_to_linear(self, rgb: np.ndarray) -> np.ndarray:
        """sRGB到线性RGB转换"""
        linear = np.where(rgb <= self.srgb_threshold / 255.0,
                         rgb / 12.92,
                         np.power((rgb + self.srgb_alpha) / (1 + self.srgb_alpha), self.srgb_gamma))
        return linear
    
    def _linear_to_srgb(self, rgb: np.ndarray) -> np.ndarray:
        """线性RGB到sRGB转换"""
        srgb = np.where(rgb <= 0.0031308,
                       rgb * 12.92,
                       (1 + self.srgb_alpha) * np.power(rgb, 1/self.srgb_gamma) - self.srgb_alpha)
        return srgb
    
    def _position_layer(self, layer: np.ndarray, canvas_shape: Tuple[int, int], 
                       position: Tuple[int, int]) -> np.ndarray:
        """定位图层到画布上"""
        canvas_h, canvas_w = canvas_shape
        layer_h, layer_w = layer.shape[:2]
        x, y = position
        
        # 创建与画布同尺寸的透明图层
        positioned = np.zeros((canvas_h, canvas_w, 4), dtype=self.dtype)
        
        # 计算有效区域
        src_x1 = max(0, -x)
        src_y1 = max(0, -y)
        src_x2 = min(layer_w, canvas_w - x)
        src_y2 = min(layer_h, canvas_h - y)
        
        dst_x1 = max(0, x)
        dst_y1 = max(0, y)
        dst_x2 = dst_x1 + (src_x2 - src_x1)
        dst_y2 = dst_y1 + (src_y2 - src_y1)
        
        # 复制有效区域
        if src_x2 > src_x1 and src_y2 > src_y1:
            positioned[dst_y1:dst_y2, dst_x1:dst_x2] = layer[src_y1:src_y2, src_x1:src_x2]
        
        return positioned
    
    def _blend_layers(self, base: np.ndarray, top: np.ndarray, 
                     blend_mode: BlendMode) -> np.ndarray:
        """执行图层混合"""
        # 使用预乘alpha进行混合
        base_premult = self._premultiply_alpha(base)
        top_premult = self._premultiply_alpha(top)
        
        # 分离颜色和alpha通道
        base_rgb = base_premult[:,:,:3]
        base_alpha = base[:,:,3:4]
        top_rgb = top_premult[:,:,:3]
        top_alpha = top[:,:,3:4]
        
        # 应用混合模式
        blended_rgb = self._apply_blend_mode(base_rgb, top_rgb, base_alpha, top_alpha, blend_mode)
        
        # 计算结果alpha
        result_alpha = self._composite_alpha(base_alpha, top_alpha)
        
        # 反预乘
        result_rgb = self._unpremultiply_alpha(blended_rgb, result_alpha)
        
        # 组合结果
        result = np.concatenate([result_rgb, result_alpha], axis=2)
        return result
    
    def _premultiply_alpha(self, rgba: np.ndarray) -> np.ndarray:
        """预乘alpha"""
        result = rgba.copy()
        alpha = rgba[:,:,3:4]
        result[:,:,:3] *= alpha
        return result
    
    def _unpremultiply_alpha(self, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """反预乘alpha"""
        # 避免除零
        safe_alpha = np.where(alpha > 1e-10, alpha, 1e-10)
        return np.clip(rgb / safe_alpha, 0, 1 if self.dtype == np.float32 else 255)
    
    def _composite_alpha(self, base_alpha: np.ndarray, top_alpha: np.ndarray) -> np.ndarray:
        """Porter-Duff alpha合成"""
        return top_alpha + base_alpha * (1 - top_alpha)
    
    def _apply_blend_mode(self, base_rgb: np.ndarray, top_rgb: np.ndarray,
                         base_alpha: np.ndarray, top_alpha: np.ndarray,
                         blend_mode: BlendMode) -> np.ndarray:
        """应用混合模式"""
        # 反预乘以获得原始颜色
        base_color = self._unpremultiply_alpha(base_rgb, base_alpha)
        top_color = self._unpremultiply_alpha(top_rgb, top_alpha)
        
        # 应用具体的混合算法
        if blend_mode == BlendMode.NORMAL:
            blended = top_color
        elif blend_mode == BlendMode.MULTIPLY:
            blended = base_color * top_color
        elif blend_mode == BlendMode.SCREEN:
            blended = 1 - (1 - base_color) * (1 - top_color)
        elif blend_mode == BlendMode.OVERLAY:
            blended = self._overlay_blend(base_color, top_color)
        elif blend_mode == BlendMode.SOFT_LIGHT:
            blended = self._soft_light_blend(base_color, top_color)
        elif blend_mode == BlendMode.HARD_LIGHT:
            blended = self._hard_light_blend(base_color, top_color)
        elif blend_mode == BlendMode.COLOR_DODGE:
            blended = self._color_dodge_blend(base_color, top_color)
        elif blend_mode == BlendMode.COLOR_BURN:
            blended = self._color_burn_blend(base_color, top_color)
        elif blend_mode == BlendMode.DARKEN:
            blended = np.minimum(base_color, top_color)
        elif blend_mode == BlendMode.LIGHTEN:
            blended = np.maximum(base_color, top_color)
        elif blend_mode == BlendMode.DIFFERENCE:
            blended = np.abs(base_color - top_color)
        elif blend_mode == BlendMode.EXCLUSION:
            blended = base_color + top_color - 2 * base_color * top_color
        else:
            blended = top_color  # 默认为正常模式
        
        # 计算最终alpha并重新预乘
        final_alpha = self._composite_alpha(base_alpha, top_alpha)
        return blended * final_alpha

    def _overlay_blend(self, base: np.ndarray, top: np.ndarray) -> np.ndarray:
        """叠加混合模式"""
        mask = base < 0.5
        return np.where(mask, 2 * base * top, 1 - 2 * (1 - base) * (1 - top))

    def _soft_light_blend(self, base: np.ndarray, top: np.ndarray) -> np.ndarray:
        """柔光混合模式（Photoshop算法）"""
        mask = top <= 0.5
        # 当top <= 0.5时
        result1 = base - (1 - 2 * top) * base * (1 - base)
        # 当top > 0.5时
        d = np.where(base <= 0.25, ((16 * base - 12) * base + 4) * base, np.sqrt(base))
        result2 = base + (2 * top - 1) * (d - base)
        return np.where(mask, result1, result2)

    def _hard_light_blend(self, base: np.ndarray, top: np.ndarray) -> np.ndarray:
        """强光混合模式"""
        mask = top < 0.5
        return np.where(mask, 2 * base * top, 1 - 2 * (1 - base) * (1 - top))

    def _color_dodge_blend(self, base: np.ndarray, top: np.ndarray) -> np.ndarray:
        """颜色减淡混合模式"""
        # 避免除零
        denominator = np.where(top >= 1.0, 1e-10, 1 - top)
        result = np.where(top >= 1.0, 1.0, np.minimum(1.0, base / denominator))
        return result

    def _color_burn_blend(self, base: np.ndarray, top: np.ndarray) -> np.ndarray:
        """颜色加深混合模式"""
        # 避免除零
        denominator = np.where(top <= 0.0, 1e-10, top)
        result = np.where(top <= 0.0, 0.0, np.maximum(0.0, 1 - (1 - base) / denominator))
        return result

    def enhance_transparency_edges(self, image: Image.Image,
                                 method: str = 'gaussian', strength: float = 0.5) -> Image.Image:
        """
        增强半透明边缘，减少锯齿效果

        Args:
            image: 输入图像
            method: 增强方法 ('gaussian', 'bilateral', 'edge_preserving')
            strength: 增强强度 (0.0-1.0)

        Returns:
            增强后的图像
        """
        if image.mode != 'RGBA':
            return image

        array = self._pil_to_array(image)
        alpha = array[:,:,3]

        # 检测半透明边缘
        semi_transparent = (alpha > 0.1) & (alpha < 0.9)

        if not np.any(semi_transparent):
            return image

        if method == 'gaussian':
            # 高斯模糊平滑
            kernel_size = max(3, int(strength * 10) | 1)  # 确保为奇数
            alpha_smooth = cv2.GaussianBlur(alpha.astype(np.float32),
                                          (kernel_size, kernel_size),
                                          strength * 2.0)
        elif method == 'bilateral':
            # 双边滤波保边平滑
            alpha_smooth = cv2.bilateralFilter(
                (alpha * 255).astype(np.uint8),
                int(strength * 20) + 5,
                strength * 50,
                strength * 50
            ).astype(np.float32) / 255.0
        else:  # edge_preserving
            # 边缘保护平滑
            alpha_smooth = cv2.edgePreservingFilter(
                (alpha * 255).astype(np.uint8),
                flags=cv2.RECURS_FILTER,
                sigma_s=strength * 100,
                sigma_r=strength * 0.4
            ).astype(np.float32) / 255.0

        # 只在半透明区域应用平滑
        array[:,:,3] = np.where(semi_transparent,
                               alpha * (1 - strength) + alpha_smooth * strength,
                               alpha)

        return self._array_to_pil(array)

    def super_resolution_upscale(self, image: Image.Image,
                               scale_factor: float, method: str = 'bicubic_plus') -> Image.Image:
        """
        超分辨率放大

        Args:
            image: 输入图像
            scale_factor: 放大倍数
            method: 放大方法 ('bicubic_plus', 'lanczos_plus', 'edge_preserving')

        Returns:
            放大后的图像
        """
        if scale_factor <= 1.0:
            return image

        original_size = image.size
        target_size = (int(original_size[0] * scale_factor),
                      int(original_size[1] * scale_factor))

        if method == 'bicubic_plus':
            return self._bicubic_plus_upscale(image, target_size)
        elif method == 'lanczos_plus':
            return self._lanczos_plus_upscale(image, target_size)
        else:  # edge_preserving
            return self._edge_preserving_upscale(image, target_size)

    def _bicubic_plus_upscale(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """增强双三次插值放大"""
        # 多步放大，每步最多2倍
        current_image = image
        current_size = image.size

        while max(target_size[0] / current_size[0], target_size[1] / current_size[1]) > 2.0:
            intermediate_size = (min(current_size[0] * 2, target_size[0]),
                               min(current_size[1] * 2, target_size[1]))

            # 双三次插值
            current_image = current_image.resize(intermediate_size, Image.BICUBIC)

            # 轻微锐化
            current_image = self._apply_unsharp_mask(current_image, radius=0.5, amount=0.3)

            current_size = intermediate_size

        # 最终步骤
        if current_size != target_size:
            current_image = current_image.resize(target_size, Image.BICUBIC)
            current_image = self._apply_unsharp_mask(current_image, radius=0.8, amount=0.4)

        return current_image

    def _lanczos_plus_upscale(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """增强Lanczos放大"""
        # 直接使用Lanczos放大
        upscaled = image.resize(target_size, Image.LANCZOS)

        # 应用边缘增强
        return self._enhance_edges(upscaled, strength=0.3)

    def _edge_preserving_upscale(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """边缘保护放大"""
        # 转换为OpenCV格式
        cv_image = cv2.cvtColor(np.array(image.convert('RGBA')), cv2.COLOR_RGBA2BGRA)

        # 使用OpenCV的边缘保护缩放
        upscaled_cv = cv2.resize(cv_image, target_size, interpolation=cv2.INTER_CUBIC)

        # 应用边缘保护滤波
        enhanced_cv = cv2.edgePreservingFilter(upscaled_cv, flags=cv2.RECURS_FILTER,
                                             sigma_s=50, sigma_r=0.4)

        # 转换回PIL
        result_array = cv2.cvtColor(enhanced_cv, cv2.COLOR_BGRA2RGBA)
        return Image.fromarray(result_array, 'RGBA')

    def _apply_unsharp_mask(self, image: Image.Image, radius: float = 1.0,
                           amount: float = 0.5, threshold: int = 3) -> Image.Image:
        """应用USM锐化"""
        # 创建模糊版本
        blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))

        # 转换为数组
        original = np.array(image, dtype=np.float32)
        blurred_array = np.array(blurred, dtype=np.float32)

        # 计算差值
        diff = original - blurred_array

        # 应用阈值
        mask = np.abs(diff) >= threshold

        # 应用锐化
        sharpened = original + diff * amount * mask

        # 限制范围
        sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

        return Image.fromarray(sharpened, image.mode)

    def _enhance_edges(self, image: Image.Image, strength: float = 0.3) -> Image.Image:
        """边缘增强"""
        enhancer = ImageEnhance.Sharpness(image)
        return enhancer.enhance(1.0 + strength)
