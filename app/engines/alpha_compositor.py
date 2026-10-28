"""
高精度半透明处理模块
实现专业级的alpha合成算法，包括：
1. 预乘alpha处理
2. Porter-Duff合成操作
3. 边缘抗锯齿
4. 子像素精度处理
5. 颜色出血控制

职责边界（R6 收敛说明）：
本模块**仅**经 ``AdvancedCompositorManager`` 在 quality 模式被调用，
实际活跃入口只有 ``AlphaCompositor.enhance_alpha_edges``
（见 ``advanced_compositor_manager.py``）。其余 Porter-Duff / 预乘相关方法
为历史残留，默认渲染/导出主链路已统一收敛到
``app.utils.unified_alpha_compositor``，请勿在预览/导出默认路径直接调用本模块。
"""

import numpy as np
from PIL import Image, ImageFilter
import cv2
from typing import Tuple, Optional, Union
from enum import Enum


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")


class CompositeOperation(Enum):
    """Porter-Duff合成操作"""
    CLEAR = "clear"
    COPY = "copy"
    DESTINATION = "destination"
    SOURCE_OVER = "source_over"
    DESTINATION_OVER = "destination_over"
    SOURCE_IN = "source_in"
    DESTINATION_IN = "destination_in"
    SOURCE_OUT = "source_out"
    DESTINATION_OUT = "destination_out"
    SOURCE_ATOP = "source_atop"
    DESTINATION_ATOP = "destination_atop"
    XOR = "xor"
    PLUS = "plus"


class AlphaCompositor:
    """高精度Alpha合成器"""
    
    def __init__(self, use_subpixel: bool = True, anti_alias: bool = True):
        """
        初始化Alpha合成器
        
        Args:
            use_subpixel: 是否使用子像素精度
            anti_alias: 是否启用抗锯齿
        """
        self.use_subpixel = use_subpixel
        self.anti_alias = anti_alias
        self.epsilon = 1e-10  # 避免除零的小值
    
    def composite_premultiplied(self, source: np.ndarray, destination: np.ndarray,
                              operation: CompositeOperation = CompositeOperation.SOURCE_OVER) -> np.ndarray:
        """
        使用预乘alpha进行Porter-Duff合成
        
        Args:
            source: 源图像数组 (H, W, 4) 预乘alpha格式
            destination: 目标图像数组 (H, W, 4) 预乘alpha格式
            operation: 合成操作
            
        Returns:
            合成后的图像数组 (预乘alpha格式)
        """
        src_rgb = source[:,:,:3]
        src_alpha = source[:,:,3:4]
        dst_rgb = destination[:,:,:3]
        dst_alpha = destination[:,:,3:4]
        
        if operation == CompositeOperation.CLEAR:
            return np.zeros_like(source)
        
        elif operation == CompositeOperation.COPY:
            return source.copy()
        
        elif operation == CompositeOperation.DESTINATION:
            return destination.copy()
        
        elif operation == CompositeOperation.SOURCE_OVER:
            # Fa = 1, Fb = (1 - αs)
            result_rgb = src_rgb + dst_rgb * (1 - src_alpha)
            result_alpha = src_alpha + dst_alpha * (1 - src_alpha)
        
        elif operation == CompositeOperation.DESTINATION_OVER:
            # Fa = (1 - αd), Fb = 1
            result_rgb = src_rgb * (1 - dst_alpha) + dst_rgb
            result_alpha = src_alpha * (1 - dst_alpha) + dst_alpha
        
        elif operation == CompositeOperation.SOURCE_IN:
            # Fa = αd, Fb = 0
            result_rgb = src_rgb * dst_alpha
            result_alpha = src_alpha * dst_alpha
        
        elif operation == CompositeOperation.DESTINATION_IN:
            # Fa = 0, Fb = αs
            result_rgb = dst_rgb * src_alpha
            result_alpha = dst_alpha * src_alpha
        
        elif operation == CompositeOperation.SOURCE_OUT:
            # Fa = (1 - αd), Fb = 0
            result_rgb = src_rgb * (1 - dst_alpha)
            result_alpha = src_alpha * (1 - dst_alpha)
        
        elif operation == CompositeOperation.DESTINATION_OUT:
            # Fa = 0, Fb = (1 - αs)
            result_rgb = dst_rgb * (1 - src_alpha)
            result_alpha = dst_alpha * (1 - src_alpha)
        
        elif operation == CompositeOperation.SOURCE_ATOP:
            # Fa = αd, Fb = (1 - αs)
            result_rgb = src_rgb * dst_alpha + dst_rgb * (1 - src_alpha)
            result_alpha = dst_alpha
        
        elif operation == CompositeOperation.DESTINATION_ATOP:
            # Fa = (1 - αd), Fb = αs
            result_rgb = src_rgb * (1 - dst_alpha) + dst_rgb * src_alpha
            result_alpha = src_alpha
        
        elif operation == CompositeOperation.XOR:
            # Fa = (1 - αd), Fb = (1 - αs)
            result_rgb = src_rgb * (1 - dst_alpha) + dst_rgb * (1 - src_alpha)
            result_alpha = src_alpha * (1 - dst_alpha) + dst_alpha * (1 - src_alpha)
        
        elif operation == CompositeOperation.PLUS:
            # Fa = 1, Fb = 1
            result_rgb = np.minimum(src_rgb + dst_rgb, 1.0)
            result_alpha = np.minimum(src_alpha + dst_alpha, 1.0)
        
        else:
            # 默认使用SOURCE_OVER
            result_rgb = src_rgb + dst_rgb * (1 - src_alpha)
            result_alpha = src_alpha + dst_alpha * (1 - src_alpha)
        
        return np.concatenate([result_rgb, result_alpha], axis=2)
    
    def premultiply_alpha(self, rgba: np.ndarray) -> np.ndarray:
        """
        将直接alpha转换为预乘alpha
        
        Args:
            rgba: 直接alpha格式的RGBA数组
            
        Returns:
            预乘alpha格式的数组
        """
        result = rgba.copy()
        alpha = rgba[:,:,3:4]
        result[:,:,:3] *= alpha
        return result
    
    def unpremultiply_alpha(self, premult_rgba: np.ndarray) -> np.ndarray:
        """
        将预乘alpha转换为直接alpha
        
        Args:
            premult_rgba: 预乘alpha格式的RGBA数组
            
        Returns:
            直接alpha格式的数组
        """
        result = premult_rgba.copy()
        alpha = premult_rgba[:,:,3:4]
        
        # 避免除零
        safe_alpha = np.where(alpha > self.epsilon, alpha, self.epsilon)
        result[:,:,:3] = np.clip(premult_rgba[:,:,:3] / safe_alpha, 0, 1)
        
        return result
    
    def enhance_alpha_edges(self, image: Image.Image, method: str = 'subpixel') -> Image.Image:
        """
        增强alpha通道边缘，实现更好的抗锯齿效果
        
        Args:
            image: 输入RGBA图像
            method: 增强方法 ('subpixel', 'supersampling', 'morphological')
            
        Returns:
            边缘增强后的图像
        """
        if image.mode != 'RGBA':
            return image
        
        array = np.array(image, dtype=np.float32) / 255.0
        
        if method == 'subpixel':
            return self._subpixel_alpha_enhancement(array)
        elif method == 'supersampling':
            return self._supersampling_alpha_enhancement(image)
        else:  # morphological
            return self._morphological_alpha_enhancement(array)
    
    def _subpixel_alpha_enhancement(self, rgba: np.ndarray) -> Image.Image:
        """子像素级alpha边缘增强"""
        alpha = rgba[:,:,3]
        
        # 计算alpha梯度
        grad_x = cv2.Sobel(alpha, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(alpha, cv2.CV_32F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        # 检测边缘区域
        edge_threshold = 0.1
        edge_mask = gradient_magnitude > edge_threshold
        
        if np.any(edge_mask):
            # 对边缘区域应用子像素平滑
            kernel = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=np.float32) / 16
            alpha_smooth = cv2.filter2D(alpha, -1, kernel)
            
            # 根据梯度强度混合原始和平滑的alpha
            blend_factor = np.clip(gradient_magnitude / 0.5, 0, 1)
            rgba[:,:,3] = np.where(edge_mask, 
                                  alpha * (1 - blend_factor) + alpha_smooth * blend_factor,
                                  alpha)
        
        result_array = (rgba * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_array)
    
    def _supersampling_alpha_enhancement(self, image: Image.Image) -> Image.Image:
        """超采样抗锯齿"""
        # 放大2倍
        upscaled = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
        
        # 应用轻微模糊
        blurred = upscaled.filter(ImageFilter.GaussianBlur(radius=0.5))
        
        # 缩回原尺寸
        return blurred.resize(image.size, Image.LANCZOS)
    
    def _morphological_alpha_enhancement(self, rgba: np.ndarray) -> Image.Image:
        """形态学alpha边缘增强"""
        alpha = rgba[:,:,3]
        
        # 创建结构元素
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        
        # 形态学梯度
        gradient = cv2.morphologyEx(alpha, cv2.MORPH_GRADIENT, kernel)
        
        # 检测需要平滑的区域
        smooth_mask = gradient > 0.05
        
        if np.any(smooth_mask):
            # 应用高斯模糊到需要平滑的区域
            alpha_smooth = cv2.GaussianBlur(alpha, (3, 3), 0.8)
            rgba[:,:,3] = np.where(smooth_mask, alpha_smooth, alpha)
        
        result_array = (rgba * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_array)
    
    def control_color_bleeding(self, image: Image.Image, strength: float = 0.5) -> Image.Image:
        """
        控制颜色出血效果，改善半透明边缘的颜色质量
        
        Args:
            image: 输入RGBA图像
            strength: 控制强度 (0.0-1.0)
            
        Returns:
            处理后的图像
        """
        if image.mode != 'RGBA':
            return image
        
        array = np.array(image, dtype=np.float32) / 255.0
        rgb = array[:,:,:3]
        alpha = array[:,:,3]
        
        # 检测半透明区域
        semi_transparent = (alpha > 0.1) & (alpha < 0.9)
        
        if not np.any(semi_transparent):
            return image
        
        # 计算每个像素的"有效颜色"
        # 对于半透明像素，减少低alpha区域对颜色的贡献
        alpha_weight = np.power(alpha, 1.0 + strength)[:,:,np.newaxis]
        weighted_rgb = rgb * alpha_weight
        
        # 在半透明区域应用加权颜色
        array[:,:,:3] = np.where(semi_transparent[:,:,np.newaxis], weighted_rgb, rgb)
        
        result_array = (array * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_array)
    
    def optimize_alpha_channel(self, image: Image.Image, 
                             remove_fringe: bool = True,
                             smooth_edges: bool = True) -> Image.Image:
        """
        优化alpha通道，移除边缘伪影和改善质量
        
        Args:
            image: 输入RGBA图像
            remove_fringe: 是否移除边缘光晕
            smooth_edges: 是否平滑边缘
            
        Returns:
            优化后的图像
        """
        if image.mode != 'RGBA':
            return image
        
        result = image.copy()
        
        if remove_fringe:
            result = self._remove_alpha_fringe(result)
        
        if smooth_edges:
            result = self.enhance_alpha_edges(result, method='subpixel')
        
        return result
    
    def _remove_alpha_fringe(self, image: Image.Image) -> Image.Image:
        """移除alpha边缘光晕"""
        array = np.array(image, dtype=np.float32) / 255.0
        rgb = array[:,:,:3]
        alpha = array[:,:,3]
        
        # 检测边缘区域
        kernel = np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]], dtype=np.float32)
        edges = cv2.filter2D(alpha, -1, kernel)
        edge_mask = np.abs(edges) > 0.1
        
        if np.any(edge_mask):
            # 对边缘区域的颜色进行去光晕处理
            # 使用中值滤波减少颜色异常
            for channel in range(3):
                rgb_channel = rgb[:,:,channel]
                # Pillow MedianFilter 已实测与 scipy.ndimage.median_filter(size=3) 逐像素等价
                filtered_channel = np.asarray(
                    Image.fromarray((rgb_channel * 255).astype(np.uint8), "L").filter(
                        ImageFilter.MedianFilter(3)
                    ),
                    dtype=np.float32,
                ) / 255.0
                rgb[:,:,channel] = np.where(edge_mask, filtered_channel, rgb_channel)
        
        array[:,:,:3] = rgb
        result_array = (array * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_array)
    
    def create_soft_mask(self, image: Image.Image, feather_radius: float = 2.0) -> Image.Image:
        """
        创建柔化蒙版，用于更自然的合成效果
        
        Args:
            image: 输入图像（将基于其alpha通道创建蒙版）
            feather_radius: 羽化半径
            
        Returns:
            柔化后的图像
        """
        if image.mode != 'RGBA':
            return image
        
        array = np.array(image, dtype=np.float32) / 255.0
        alpha = array[:,:,3]
        
        # 应用高斯模糊进行羽化
        if feather_radius > 0:
            alpha_feathered = cv2.GaussianBlur(alpha, (0, 0), feather_radius)
            array[:,:,3] = alpha_feathered
        
        result_array = (array * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_array)
