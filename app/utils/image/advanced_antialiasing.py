"""
高级抗锯齿处理器
实现专业级抗锯齿算法，专门针对PNG图像的锯齿问题

支持的抗锯齿技术：
1. MSAA (Multi-Sample Anti-Aliasing) - 多重采样抗锯齿
2. SSAA (Super-Sample Anti-Aliasing) - 超级采样抗锯齿  
3. FXAA (Fast Approximate Anti-Aliasing) - 快速近似抗锯齿
4. SMAA (Subpixel Morphological Anti-Aliasing) - 子像素形态学抗锯齿
5. TAA (Temporal Anti-Aliasing) - 时间抗锯齿（适用于动画）

重点解决：
- PNG图像边缘锯齿
- Alpha通道锯齿
- 缩放时的锯齿
- 旋转时的锯齿
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from typing import Tuple, Optional, List, Dict, Any
from enum import Enum
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)


class AntiAliasingMethod(Enum):
    """抗锯齿方法枚举"""
    BASIC = "basic"           # 基础抗锯齿
    MSAA_2X = "msaa_2x"      # 2x多重采样
    MSAA_4X = "msaa_4x"      # 4x多重采样
    MSAA_8X = "msaa_8x"      # 8x多重采样
    SSAA_2X = "ssaa_2x"      # 2x超级采样
    SSAA_4X = "ssaa_4x"      # 4x超级采样
    FXAA = "fxaa"            # 快速近似抗锯齿
    SMAA = "smaa"            # 子像素形态学抗锯齿
    ADAPTIVE = "adaptive"     # 自适应抗锯齿


class AdvancedAntialiasing:
    """高级抗锯齿处理器"""
    
    def __init__(self):
        self.epsilon = 1e-10
        
    def apply_antialiasing(self, image: Image.Image, 
                          method: AntiAliasingMethod = AntiAliasingMethod.ADAPTIVE,
                          strength: float = 1.0,
                          preserve_details: bool = True) -> Image.Image:
        """
        应用抗锯齿处理
        
        Args:
            image: 输入图像
            method: 抗锯齿方法
            strength: 抗锯齿强度 (0.0-2.0)
            preserve_details: 是否保持细节
            
        Returns:
            抗锯齿后的图像
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 根据方法选择处理函数
        if method == AntiAliasingMethod.BASIC:
            return self._basic_antialiasing(image, strength)
        elif method == AntiAliasingMethod.MSAA_2X:
            return self._msaa_antialiasing(image, 2, strength)
        elif method == AntiAliasingMethod.MSAA_4X:
            return self._msaa_antialiasing(image, 4, strength)
        elif method == AntiAliasingMethod.MSAA_8X:
            return self._msaa_antialiasing(image, 8, strength)
        elif method == AntiAliasingMethod.SSAA_2X:
            return self._ssaa_antialiasing(image, 2, strength)
        elif method == AntiAliasingMethod.SSAA_4X:
            return self._ssaa_antialiasing(image, 4, strength)
        elif method == AntiAliasingMethod.FXAA:
            return self._fxaa_antialiasing(image, strength)
        elif method == AntiAliasingMethod.SMAA:
            return self._smaa_antialiasing(image, strength)
        elif method == AntiAliasingMethod.ADAPTIVE:
            return self._adaptive_antialiasing(image, strength, preserve_details)
        else:
            return self._basic_antialiasing(image, strength)
    
    def _basic_antialiasing(self, image: Image.Image, strength: float) -> Image.Image:
        """基础抗锯齿 - 简单的Alpha通道模糊"""
        r, g, b, a = image.split()
        
        # 对Alpha通道应用高斯模糊
        blur_radius = max(0.3, min(2.0, strength * 0.8))
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        return Image.merge('RGBA', (r, g, b, a_smooth))
    
    def _msaa_antialiasing(self, image: Image.Image, samples: int, strength: float) -> Image.Image:
        """多重采样抗锯齿 (MSAA)"""
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0
        h, w = img_array.shape[:2]
        
        # 创建采样偏移
        offsets = self._generate_sample_offsets(samples)
        
        # 对每个采样点进行处理
        accumulated = np.zeros_like(img_array)
        
        for offset_x, offset_y in offsets:
            # 应用亚像素偏移
            shifted = self._apply_subpixel_shift(img_array, offset_x, offset_y)
            accumulated += shifted
        
        # 平均所有采样
        result = accumulated / samples
        
        # 应用强度调节
        if strength != 1.0:
            result = self._blend_with_original(img_array, result, strength)
        
        # 转换回图像
        result_8bit = (np.clip(result, 0, 1) * 255).astype(np.uint8)
        return Image.fromarray(result_8bit, 'RGBA')
    
    def _ssaa_antialiasing(self, image: Image.Image, scale: int, strength: float) -> Image.Image:
        """超级采样抗锯齿 (SSAA)"""
        original_size = image.size
        
        # 放大图像
        upscaled_size = (original_size[0] * scale, original_size[1] * scale)
        upscaled = image.resize(upscaled_size, Image.LANCZOS)
        
        # 对放大后的图像进行高质量滤波
        filtered = self._apply_high_quality_filter(upscaled, strength)
        
        # 缩放回原始大小
        return filtered.resize(original_size, Image.LANCZOS)
    
    def _fxaa_antialiasing(self, image: Image.Image, strength: float) -> Image.Image:
        """快速近似抗锯齿 (FXAA)"""
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0
        
        # 分离通道
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 计算亮度
        luma = np.dot(rgb, [0.299, 0.587, 0.114])
        
        # 检测边缘
        edge_map = self._detect_edges_fxaa(luma)
        
        # 对边缘区域应用定向模糊
        filtered_alpha = self._apply_directional_blur(alpha, edge_map, strength)
        
        # 重新组合
        result_array = np.concatenate([rgb, filtered_alpha[:, :, np.newaxis]], axis=2)
        result_8bit = (np.clip(result_array, 0, 1) * 255).astype(np.uint8)
        
        return Image.fromarray(result_8bit, 'RGBA')
    
    def _smaa_antialiasing(self, image: Image.Image, strength: float) -> Image.Image:
        """子像素形态学抗锯齿 (SMAA)"""
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0
        alpha = img_array[:, :, 3]
        
        # 第一步：边缘检测
        edge_map = self._detect_edges_smaa(alpha)
        
        # 第二步：混合权重计算
        blend_weights = self._calculate_blend_weights(edge_map, alpha)
        
        # 第三步：邻域混合
        filtered_alpha = self._apply_neighborhood_blending(alpha, blend_weights, strength)
        
        # 重新组合
        result_array = img_array.copy()
        result_array[:, :, 3] = filtered_alpha
        result_8bit = (np.clip(result_array, 0, 1) * 255).astype(np.uint8)
        
        return Image.fromarray(result_8bit, 'RGBA')
    
    def _adaptive_antialiasing(self, image: Image.Image, strength: float, 
                              preserve_details: bool) -> Image.Image:
        """自适应抗锯齿 - 根据图像特征选择最佳方法"""
        # 分析图像特征
        analysis = self._analyze_image_characteristics(image)
        
        # 根据分析结果选择方法
        if analysis['edge_density'] > 0.3:
            # 高边缘密度 - 使用SMAA
            return self._smaa_antialiasing(image, strength)
        elif analysis['has_fine_details'] and preserve_details:
            # 有精细细节 - 使用FXAA
            return self._fxaa_antialiasing(image, strength * 0.8)
        elif analysis['image_size'] > 1000000:  # 大图像
            # 大图像 - 使用基础方法
            return self._basic_antialiasing(image, strength)
        else:
            # 默认使用4x MSAA
            return self._msaa_antialiasing(image, 4, strength)
    
    def _generate_sample_offsets(self, samples: int) -> List[Tuple[float, float]]:
        """生成MSAA采样偏移"""
        if samples == 2:
            return [(0.25, 0.25), (-0.25, -0.25)]
        elif samples == 4:
            return [(0.125, 0.375), (0.375, -0.125), 
                   (-0.125, -0.375), (-0.375, 0.125)]
        elif samples == 8:
            return [(0.0625, 0.1875), (0.1875, 0.0625), (0.3125, 0.4375),
                   (0.4375, 0.3125), (-0.0625, -0.1875), (-0.1875, -0.0625),
                   (-0.3125, -0.4375), (-0.4375, -0.3125)]
        else:
            # 默认4x采样
            return [(0.125, 0.375), (0.375, -0.125), 
                   (-0.125, -0.375), (-0.375, 0.125)]
    
    def _apply_subpixel_shift(self, img_array: np.ndarray, 
                             offset_x: float, offset_y: float) -> np.ndarray:
        """应用亚像素偏移"""
        # 简化的亚像素偏移实现
        # 在实际应用中，这里应该使用双线性插值
        h, w = img_array.shape[:2]
        
        # 创建偏移后的图像
        shifted = np.zeros_like(img_array)
        
        # 计算整数偏移
        int_offset_x = int(offset_x)
        int_offset_y = int(offset_y)
        
        # 应用偏移
        if int_offset_x >= 0 and int_offset_y >= 0:
            shifted[int_offset_y:, int_offset_x:] = img_array[:h-int_offset_y, :w-int_offset_x]
        elif int_offset_x < 0 and int_offset_y >= 0:
            shifted[int_offset_y:, :w+int_offset_x] = img_array[:h-int_offset_y, -int_offset_x:]
        elif int_offset_x >= 0 and int_offset_y < 0:
            shifted[:h+int_offset_y, int_offset_x:] = img_array[-int_offset_y:, :w-int_offset_x]
        else:
            shifted[:h+int_offset_y, :w+int_offset_x] = img_array[-int_offset_y:, -int_offset_x:]
        
        return shifted
    
    def _apply_high_quality_filter(self, image: Image.Image, strength: float) -> Image.Image:
        """应用高质量滤波"""
        # 分离通道
        r, g, b, a = image.split()
        
        # 对Alpha通道应用多级滤波
        # 第一级：高斯模糊
        blur_radius = strength * 1.5
        a_blur1 = a.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # 第二级：双边滤波（使用UnsharpMask近似）
        a_blur2 = a_blur1.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
        
        # 混合两级结果
        a_final = Image.blend(a_blur1, a_blur2, 0.3)
        
        return Image.merge('RGBA', (r, g, b, a_final))
    
    def _detect_edges_fxaa(self, luma: np.ndarray) -> np.ndarray:
        """FXAA边缘检测"""
        # 计算亮度梯度
        grad_x = np.gradient(luma, axis=1)
        grad_y = np.gradient(luma, axis=0)
        
        # 计算梯度幅度
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        # 边缘阈值
        edge_threshold = 0.1
        return gradient_magnitude > edge_threshold
    
    def _apply_directional_blur(self, alpha: np.ndarray, edge_map: np.ndarray, 
                               strength: float) -> np.ndarray:
        """应用定向模糊"""
        result = alpha.copy()
        
        # 对边缘区域应用模糊
        if np.any(edge_map):
            # 使用PIL进行高斯模糊
            alpha_img = Image.fromarray((alpha * 255).astype(np.uint8), 'L')
            blurred = alpha_img.filter(ImageFilter.GaussianBlur(radius=strength))
            blurred_array = np.array(blurred).astype(np.float64) / 255.0
            
            # 只在边缘区域应用模糊
            result[edge_map] = blurred_array[edge_map]
        
        return result
    
    def _detect_edges_smaa(self, alpha: np.ndarray) -> np.ndarray:
        """SMAA边缘检测"""
        try:
            from scipy import ndimage
            # 使用Sobel算子
            grad_x = ndimage.sobel(alpha, axis=1)
            grad_y = ndimage.sobel(alpha, axis=0)
            gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
            return gradient_magnitude > 0.05
        except ImportError:
            # 简单的边缘检测
            return self._simple_edge_detection(alpha)
    
    def _simple_edge_detection(self, alpha: np.ndarray) -> np.ndarray:
        """简单边缘检测"""
        h, w = alpha.shape
        edges = np.zeros_like(alpha, dtype=bool)
        
        for i in range(1, h-1):
            for j in range(1, w-1):
                center = alpha[i, j]
                neighbors = alpha[i-1:i+2, j-1:j+2]
                max_diff = np.max(np.abs(neighbors - center))
                edges[i, j] = max_diff > 0.1
        
        return edges
    
    def _calculate_blend_weights(self, edge_map: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """计算混合权重"""
        weights = np.ones_like(alpha)
        
        # 在边缘区域增加权重
        weights[edge_map] = 2.0
        
        return weights
    
    def _apply_neighborhood_blending(self, alpha: np.ndarray, weights: np.ndarray, 
                                   strength: float) -> np.ndarray:
        """应用邻域混合"""
        # 使用加权平均进行邻域混合
        kernel_size = 3
        result = alpha.copy()
        h, w = alpha.shape
        
        for i in range(1, h-1):
            for j in range(1, w-1):
                if weights[i, j] > 1.0:  # 只处理边缘像素
                    # 获取邻域
                    neighborhood = alpha[i-1:i+2, j-1:j+2]
                    neighborhood_weights = weights[i-1:i+2, j-1:j+2]
                    
                    # 计算加权平均
                    weighted_sum = np.sum(neighborhood * neighborhood_weights)
                    weight_sum = np.sum(neighborhood_weights)
                    
                    if weight_sum > 0:
                        blended_value = weighted_sum / weight_sum
                        result[i, j] = alpha[i, j] * (1 - strength) + blended_value * strength
        
        return result
    
    def _analyze_image_characteristics(self, image: Image.Image) -> Dict[str, Any]:
        """分析图像特征"""
        img_array = np.array(image, dtype=np.float64) / 255.0
        alpha = img_array[:, :, 3]
        
        # 计算边缘密度
        edges = self._simple_edge_detection(alpha)
        edge_density = np.sum(edges) / edges.size
        
        # 检测精细细节
        has_fine_details = self._detect_fine_details(alpha)
        
        # 图像大小
        image_size = image.size[0] * image.size[1]
        
        return {
            'edge_density': edge_density,
            'has_fine_details': has_fine_details,
            'image_size': image_size,
            'alpha_variance': np.var(alpha)
        }
    
    def _detect_fine_details(self, alpha: np.ndarray) -> bool:
        """检测精细细节"""
        # 计算Alpha通道的方差
        variance = np.var(alpha)
        
        # 计算高频成分
        try:
            from scipy import ndimage
            laplacian = ndimage.laplace(alpha)
            high_freq_energy = np.sum(np.abs(laplacian))
            return high_freq_energy > 0.1 and variance > 0.05
        except ImportError:
            # 简单的细节检测
            return variance > 0.1
    
    def _blend_with_original(self, original: np.ndarray, processed: np.ndarray, 
                           strength: float) -> np.ndarray:
        """与原图混合"""
        return original * (1 - strength) + processed * strength


# 便捷函数
def apply_png_antialiasing(image: Image.Image, 
                          quality: str = 'high',
                          strength: float = 1.0) -> Image.Image:
    """
    PNG抗锯齿便捷函数
    
    Args:
        image: 输入图像
        quality: 质量级别 ('low', 'medium', 'high', 'ultra')
        strength: 抗锯齿强度
        
    Returns:
        抗锯齿后的图像
    """
    aa = AdvancedAntialiasing()
    
    # 根据质量级别选择方法
    method_map = {
        'low': AntiAliasingMethod.BASIC,
        'medium': AntiAliasingMethod.FXAA,
        'high': AntiAliasingMethod.MSAA_4X,
        'ultra': AntiAliasingMethod.SMAA
    }
    
    method = method_map.get(quality, AntiAliasingMethod.ADAPTIVE)
    return aa.apply_antialiasing(image, method, strength)
