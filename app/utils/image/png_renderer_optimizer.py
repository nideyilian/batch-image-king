"""
PNG渲染优化器
专门解决PNG图像渲染中的黑边和锯齿问题

主要功能：
1. 正确处理预乘Alpha，避免黑边
2. 高质量抗锯齿算法
3. 专业级Alpha混合
4. 边缘优化和平滑处理
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from typing import Tuple, Optional, Union, List
import warnings

# 抑制NumPy警告
warnings.filterwarnings('ignore', category=RuntimeWarning)


class PNGRenderOptimizer:
    """PNG渲染优化器"""
    
    def __init__(self):
        self.gamma = 2.2  # 标准sRGB Gamma值
        self.epsilon = 1e-10  # 防止除零的小值
        
    def optimize_png_rendering(self, image: Image.Image, 
                             fix_black_edges: bool = True,
                             apply_antialiasing: bool = True,
                             enhance_edges: bool = True,
                             quality_level: str = 'high') -> Image.Image:
        """
        优化PNG图像渲染
        
        Args:
            image: 输入的PNG图像
            fix_black_edges: 是否修复黑边问题
            apply_antialiasing: 是否应用抗锯齿
            enhance_edges: 是否增强边缘
            quality_level: 质量级别 ('low', 'medium', 'high', 'ultra')
            
        Returns:
            优化后的图像
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        result = image.copy()
        
        # 1. 修复黑边问题
        if fix_black_edges:
            result = self._fix_black_edges(result)
        
        # 2. 应用抗锯齿
        if apply_antialiasing:
            result = self._apply_antialiasing(result, quality_level)
        
        # 3. 边缘增强
        if enhance_edges:
            result = self._enhance_edges(result, quality_level)
        
        return result
    
    def _fix_black_edges(self, image: Image.Image) -> Image.Image:
        """修复黑边问题"""
        # 转换为numpy数组进行处理
        img_array = np.array(image, dtype=np.float64) / 255.0
        
        # 分离通道
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 检测是否为预乘Alpha
        is_premultiplied = self._detect_premultiplied_alpha(rgb, alpha)
        
        if is_premultiplied:
            # 处理预乘Alpha
            rgb = self._unpremultiply_alpha(rgb, alpha)
        
        # 修复边缘黑色像素
        rgb = self._fix_edge_artifacts(rgb, alpha)
        
        # 重新组合
        result_array = np.concatenate([rgb, alpha[:, :, np.newaxis]], axis=2)
        result_array = np.clip(result_array, 0, 1)
        
        # 转换回图像
        result_8bit = (result_array * 255.0).astype(np.uint8)
        return Image.fromarray(result_8bit, 'RGBA')
    
    def _detect_premultiplied_alpha(self, rgb: np.ndarray, alpha: np.ndarray) -> bool:
        """检测是否为预乘Alpha"""
        # 找到半透明像素（0 < alpha < 1）
        semi_transparent = (alpha > self.epsilon) & (alpha < 1 - self.epsilon)
        
        if not np.any(semi_transparent):
            return False
        
        # 检查RGB值是否超过Alpha值（预乘Alpha的特征）
        max_rgb = np.max(rgb, axis=2)
        exceeds_alpha = max_rgb > alpha + self.epsilon
        
        # 如果大部分半透明像素的RGB值都不超过Alpha值，可能是预乘Alpha
        premult_ratio = np.sum(semi_transparent & ~exceeds_alpha) / np.sum(semi_transparent)
        
        return premult_ratio > 0.7  # 70%的阈值
    
    def _unpremultiply_alpha(self, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """取消预乘Alpha"""
        # 避免除零
        safe_alpha = np.where(alpha > self.epsilon, alpha, self.epsilon)
        
        # 取消预乘
        unpremult_rgb = rgb / safe_alpha[:, :, np.newaxis]
        
        # 对于完全透明的像素，保持原始RGB值
        transparent_mask = alpha <= self.epsilon
        unpremult_rgb[transparent_mask] = rgb[transparent_mask]
        
        return np.clip(unpremult_rgb, 0, 1)
    
    def _fix_edge_artifacts(self, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """修复边缘伪影"""
        # 创建边缘掩码
        edge_mask = self._detect_edges(alpha)
        
        # 对边缘像素进行颜色修复
        fixed_rgb = rgb.copy()
        
        # 使用形态学操作扩展有效颜色到边缘
        for channel in range(3):
            fixed_rgb[:, :, channel] = self._propagate_colors(
                rgb[:, :, channel], alpha, edge_mask
            )
        
        return fixed_rgb
    
    def _detect_edges(self, alpha: np.ndarray) -> np.ndarray:
        """检测Alpha通道的边缘"""
        # 使用Sobel算子检测边缘
        from scipy import ndimage
        
        try:
            # 计算梯度
            grad_x = ndimage.sobel(alpha, axis=1)
            grad_y = ndimage.sobel(alpha, axis=0)
            gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
            
            # 边缘阈值
            edge_threshold = 0.1
            return gradient_magnitude > edge_threshold
        except ImportError:
            # 如果没有scipy，使用简单的边缘检测
            return self._simple_edge_detection(alpha)
    
    def _simple_edge_detection(self, alpha: np.ndarray) -> np.ndarray:
        """简单的边缘检测（不依赖scipy）"""
        # 使用PIL的边缘检测滤镜
        alpha_img = Image.fromarray((alpha * 255).astype(np.uint8), 'L')
        edges = alpha_img.filter(ImageFilter.FIND_EDGES)
        edge_array = np.array(edges) / 255.0
        
        return edge_array > 0.1
    
    def _propagate_colors(self, channel: np.ndarray, alpha: np.ndarray, 
                         edge_mask: np.ndarray) -> np.ndarray:
        """将有效颜色传播到边缘区域"""
        result = channel.copy()
        
        # 找到需要修复的像素（边缘且Alpha值较低）
        fix_mask = edge_mask & (alpha < 0.5)
        
        if not np.any(fix_mask):
            return result
        
        # 使用邻近像素的加权平均来修复
        kernel_size = 3
        pad_width = kernel_size // 2
        
        # 填充数组
        padded_channel = np.pad(channel, pad_width, mode='edge')
        padded_alpha = np.pad(alpha, pad_width, mode='edge')
        
        # 对每个需要修复的像素
        fix_coords = np.where(fix_mask)
        for y, x in zip(fix_coords[0], fix_coords[1]):
            # 获取邻域
            py, px = y + pad_width, x + pad_width
            neighborhood_color = padded_channel[py-pad_width:py+pad_width+1, 
                                             px-pad_width:px+pad_width+1]
            neighborhood_alpha = padded_alpha[py-pad_width:py+pad_width+1, 
                                            px-pad_width:px+pad_width+1]
            
            # 使用Alpha值作为权重
            weights = neighborhood_alpha
            weights = weights / (np.sum(weights) + self.epsilon)
            
            # 计算加权平均
            result[y, x] = np.sum(neighborhood_color * weights)
        
        return result

    def _apply_antialiasing(self, image: Image.Image, quality_level: str) -> Image.Image:
        """应用抗锯齿处理"""
        if quality_level == 'low':
            return self._basic_antialiasing(image)
        elif quality_level == 'medium':
            return self._medium_antialiasing(image)
        elif quality_level == 'high':
            return self._high_antialiasing(image)
        else:  # ultra
            return self._ultra_antialiasing(image)

    def _basic_antialiasing(self, image: Image.Image) -> Image.Image:
        """基础抗锯齿"""
        # 对Alpha通道进行轻微模糊
        r, g, b, a = image.split()
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=0.5))
        return Image.merge('RGBA', (r, g, b, a_smooth))

    def _medium_antialiasing(self, image: Image.Image) -> Image.Image:
        """中等质量抗锯齿"""
        # 使用双线性插值进行2x超采样
        original_size = image.size
        upscaled = image.resize((original_size[0] * 2, original_size[1] * 2),
                               Image.LANCZOS)

        # 对Alpha通道进行高斯模糊
        r, g, b, a = upscaled.split()
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=1.0))
        upscaled_smooth = Image.merge('RGBA', (r, g, b, a_smooth))

        # 缩放回原始大小
        return upscaled_smooth.resize(original_size, Image.LANCZOS)

    def _high_antialiasing(self, image: Image.Image) -> Image.Image:
        """高质量抗锯齿"""
        # 4x超采样 + 高质量滤波
        original_size = image.size
        scale_factor = 4

        # 超采样
        upscaled = image.resize((original_size[0] * scale_factor,
                               original_size[1] * scale_factor),
                               Image.LANCZOS)

        # 转换为numpy进行高精度处理
        img_array = np.array(upscaled, dtype=np.float64) / 255.0

        # 对Alpha通道应用高质量滤波
        alpha = img_array[:, :, 3]
        alpha_filtered = self._apply_gaussian_filter(alpha, sigma=1.5)
        img_array[:, :, 3] = alpha_filtered

        # 转换回图像
        filtered_img = Image.fromarray((img_array * 255).astype(np.uint8), 'RGBA')

        # 缩放回原始大小
        return filtered_img.resize(original_size, Image.LANCZOS)

    def _ultra_antialiasing(self, image: Image.Image) -> Image.Image:
        """超高质量抗锯齿"""
        # 8x超采样 + 多级滤波
        original_size = image.size
        scale_factor = 8

        # 超采样
        upscaled = image.resize((original_size[0] * scale_factor,
                               original_size[1] * scale_factor),
                               Image.LANCZOS)

        # 多级滤波处理
        result = self._multi_level_filtering(upscaled)

        # 缩放回原始大小
        return result.resize(original_size, Image.LANCZOS)

    def _apply_gaussian_filter(self, data: np.ndarray, sigma: float) -> np.ndarray:
        """应用高斯滤波"""
        try:
            from scipy import ndimage
            return ndimage.gaussian_filter(data, sigma=sigma)
        except ImportError:
            # 如果没有scipy，使用PIL的高斯模糊
            data_img = Image.fromarray((data * 255).astype(np.uint8), 'L')
            blurred = data_img.filter(ImageFilter.GaussianBlur(radius=sigma))
            return np.array(blurred).astype(np.float64) / 255.0

    def _multi_level_filtering(self, image: Image.Image) -> Image.Image:
        """多级滤波处理"""
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0

        # 分离通道
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]

        # 对Alpha通道应用多级滤波
        # 第一级：边缘保持滤波
        alpha_level1 = self._edge_preserving_filter(alpha)

        # 第二级：高斯滤波
        alpha_level2 = self._apply_gaussian_filter(alpha_level1, sigma=1.0)

        # 第三级：双边滤波（如果可用）
        alpha_final = self._bilateral_filter(alpha_level2)

        # 重新组合
        result_array = np.concatenate([rgb, alpha_final[:, :, np.newaxis]], axis=2)
        result_array = np.clip(result_array, 0, 1)

        return Image.fromarray((result_array * 255).astype(np.uint8), 'RGBA')

    def _edge_preserving_filter(self, data: np.ndarray) -> np.ndarray:
        """边缘保持滤波"""
        try:
            from scipy import ndimage
            return ndimage.median_filter(data, size=3)
        except ImportError:
            # 简单的边缘保持实现
            return data  # 如果没有scipy，跳过此步骤

    def _bilateral_filter(self, data: np.ndarray) -> np.ndarray:
        """双边滤波"""
        try:
            import cv2
            # 转换为8位进行OpenCV处理
            data_8bit = (data * 255).astype(np.uint8)
            filtered = cv2.bilateralFilter(data_8bit, 9, 75, 75)
            return filtered.astype(np.float64) / 255.0
        except ImportError:
            # 如果没有OpenCV，使用高斯滤波作为替代
            return self._apply_gaussian_filter(data, sigma=1.0)

    def _enhance_edges(self, image: Image.Image, quality_level: str) -> Image.Image:
        """边缘增强处理"""
        if quality_level in ['low', 'medium']:
            return self._basic_edge_enhancement(image)
        else:
            return self._advanced_edge_enhancement(image)

    def _basic_edge_enhancement(self, image: Image.Image) -> Image.Image:
        """基础边缘增强"""
        # 分离通道
        r, g, b, a = image.split()

        # 对Alpha通道进行轻微的锐化
        enhancer = ImageEnhance.Sharpness(a)
        a_enhanced = enhancer.enhance(1.2)  # 轻微锐化

        return Image.merge('RGBA', (r, g, b, a_enhanced))

    def _advanced_edge_enhancement(self, image: Image.Image) -> Image.Image:
        """高级边缘增强"""
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0

        # 分离通道
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]

        # 检测边缘
        edge_mask = self._detect_edges(alpha)

        # 对边缘区域进行特殊处理
        enhanced_alpha = self._enhance_edge_alpha(alpha, edge_mask)

        # 重新组合
        result_array = np.concatenate([rgb, enhanced_alpha[:, :, np.newaxis]], axis=2)
        result_array = np.clip(result_array, 0, 1)

        return Image.fromarray((result_array * 255).astype(np.uint8), 'RGBA')

    def _enhance_edge_alpha(self, alpha: np.ndarray, edge_mask: np.ndarray) -> np.ndarray:
        """增强边缘Alpha值"""
        enhanced = alpha.copy()

        # 对边缘像素应用S曲线增强
        edge_pixels = alpha[edge_mask]

        if len(edge_pixels) > 0:
            # S曲线函数：增强对比度
            def s_curve(x):
                return 3 * x**2 - 2 * x**3

            enhanced[edge_mask] = s_curve(edge_pixels)

        return enhanced


# 便捷函数
def optimize_png_image(image: Image.Image,
                      quality_level: str = 'high',
                      fix_black_edges: bool = True,
                      apply_antialiasing: bool = True,
                      enhance_edges: bool = True) -> Image.Image:
    """
    优化PNG图像渲染的便捷函数

    Args:
        image: 输入图像
        quality_level: 质量级别 ('low', 'medium', 'high', 'ultra')
        fix_black_edges: 是否修复黑边
        apply_antialiasing: 是否应用抗锯齿
        enhance_edges: 是否增强边缘

    Returns:
        优化后的图像
    """
    optimizer = PNGRenderOptimizer()
    return optimizer.optimize_png_rendering(
        image, fix_black_edges, apply_antialiasing, enhance_edges, quality_level
    )
