"""
预乘Alpha处理器
专门处理预乘Alpha图像，避免黑边和颜色失真问题

预乘Alpha (Premultiplied Alpha) 是一种图像存储格式，其中：
- RGB值已经与Alpha值相乘
- 公式：RGB_premult = RGB_straight * Alpha
- 优点：混合计算更快
- 缺点：需要特殊处理避免黑边

常见问题：
1. 将预乘Alpha当作直接Alpha处理会产生黑边
2. 在编辑时需要转换为直接Alpha
3. 保存时可能需要转换回预乘Alpha
"""

import numpy as np
from PIL import Image
from typing import Tuple, Optional, Dict, Any
import warnings

from app.utils.image import ndops

warnings.filterwarnings('ignore', category=RuntimeWarning)


class PremultipliedAlphaHandler:
    """预乘Alpha处理器"""
    
    def __init__(self):
        self.epsilon = 1e-10  # 防止除零的小值
        self.detection_threshold = 0.7  # 预乘Alpha检测阈值
        
    def detect_premultiplied_alpha(self, image: Image.Image) -> Dict[str, Any]:
        """
        检测图像是否使用预乘Alpha
        
        Args:
            image: 输入图像
            
        Returns:
            检测结果字典，包含是否为预乘Alpha和置信度
        """
        if image.mode != 'RGBA':
            return {'is_premultiplied': False, 'confidence': 0.0, 'reason': 'Not RGBA'}
        
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 分析像素特征
        analysis = self._analyze_alpha_characteristics(rgb, alpha)
        
        return analysis
    
    def _analyze_alpha_characteristics(self, rgb: np.ndarray, alpha: np.ndarray) -> Dict[str, Any]:
        """分析Alpha通道特征"""
        # 找到不同类型的像素
        fully_opaque = alpha >= (1.0 - self.epsilon)
        fully_transparent = alpha <= self.epsilon
        semi_transparent = ~fully_opaque & ~fully_transparent
        
        if not np.any(semi_transparent):
            return {
                'is_premultiplied': False, 
                'confidence': 0.0, 
                'reason': 'No semi-transparent pixels'
            }
        
        # 检查半透明像素的RGB值特征
        semi_rgb = rgb[semi_transparent]
        semi_alpha = alpha[semi_transparent]
        
        # 特征1：RGB值是否超过Alpha值
        max_rgb_per_pixel = np.max(semi_rgb, axis=1)
        exceeds_alpha = max_rgb_per_pixel > (semi_alpha + self.epsilon)
        exceeds_ratio = np.sum(exceeds_alpha) / len(exceeds_alpha)
        
        # 特征2：RGB值与Alpha值的相关性
        correlation = self._calculate_rgb_alpha_correlation(semi_rgb, semi_alpha)
        
        # 特征3：边缘像素的颜色分布
        edge_analysis = self._analyze_edge_colors(rgb, alpha)
        
        # 综合判断
        premult_indicators = 0
        confidence_factors = []
        
        # 指标1：RGB不超过Alpha（预乘特征）
        if exceeds_ratio < 0.3:  # 少于30%的像素RGB超过Alpha
            premult_indicators += 1
            confidence_factors.append(('low_exceeds_ratio', 1.0 - exceeds_ratio))
        
        # 指标2：RGB与Alpha高相关性（预乘特征）
        if correlation > 0.6:
            premult_indicators += 1
            confidence_factors.append(('high_correlation', correlation))
        
        # 指标3：边缘有黑色像素（预乘问题）
        if edge_analysis['has_black_edges']:
            premult_indicators += 1
            confidence_factors.append(('black_edges', edge_analysis['black_edge_ratio']))
        
        # 计算最终置信度
        is_premultiplied = premult_indicators >= 2
        confidence = np.mean([factor[1] for factor in confidence_factors]) if confidence_factors else 0.0
        
        return {
            'is_premultiplied': is_premultiplied,
            'confidence': confidence,
            'exceeds_ratio': exceeds_ratio,
            'correlation': correlation,
            'edge_analysis': edge_analysis,
            'indicators': premult_indicators,
            'reason': f'{premult_indicators}/3 indicators suggest premultiplied alpha'
        }
    
    def _calculate_rgb_alpha_correlation(self, rgb: np.ndarray, alpha: np.ndarray) -> float:
        """计算RGB与Alpha的相关性"""
        # 计算每个像素的RGB平均值与Alpha的相关性
        rgb_mean = np.mean(rgb, axis=1)
        
        # 计算皮尔逊相关系数
        if len(rgb_mean) < 2:
            return 0.0
        
        correlation = np.corrcoef(rgb_mean, alpha)[0, 1]
        return correlation if not np.isnan(correlation) else 0.0
    
    def _analyze_edge_colors(self, rgb: np.ndarray, alpha: np.ndarray) -> Dict[str, Any]:
        """分析边缘颜色特征"""
        # 检测Alpha边缘
        edge_mask = self._detect_alpha_edges(alpha)
        
        if not np.any(edge_mask):
            return {'has_black_edges': False, 'black_edge_ratio': 0.0}
        
        # 分析边缘像素的颜色
        edge_rgb = rgb[edge_mask]
        edge_alpha = alpha[edge_mask]
        
        # 检查是否有异常暗的边缘像素（可能是预乘Alpha问题）
        edge_brightness = np.mean(edge_rgb, axis=1)
        dark_edges = (edge_brightness < 0.1) & (edge_alpha > 0.1)  # 暗但不透明
        
        black_edge_ratio = np.sum(dark_edges) / len(dark_edges) if len(dark_edges) > 0 else 0.0
        
        return {
            'has_black_edges': black_edge_ratio > 0.1,
            'black_edge_ratio': black_edge_ratio,
            'edge_pixel_count': len(edge_rgb)
        }
    
    def _detect_alpha_edges(self, alpha: np.ndarray) -> np.ndarray:
        """检测Alpha通道边缘"""
        # 使用Sobel算子检测边缘（ndops.sobel 与 scipy.ndimage.sobel 逐位等价）
        grad_x = ndops.sobel(alpha, axis=1)
        grad_y = ndops.sobel(alpha, axis=0)
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        return gradient_magnitude > 0.1
    
    def unpremultiply_alpha(self, image: Image.Image) -> Image.Image:
        """
        将预乘Alpha图像转换为直接Alpha - 增强版本，修复PNG边缘问题
        
        Args:
            image: 预乘Alpha图像
            
        Returns:
            直接Alpha图像
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 首先检测是否为预乘alpha
        detection_result = self.detect_premultiplied_alpha(image)
        if not detection_result['is_premultiplied'] or detection_result['confidence'] < 0.5:
            # 如果不是预乘alpha或置信度低，直接返回原图
            return image
        
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 取消预乘，使用增强算法
        unpremult_rgb = self._enhanced_unpremultiply_rgb(rgb, alpha)
        
        # 重新组合
        result_array = np.concatenate([unpremult_rgb, alpha[:, :, np.newaxis]], axis=2)
        result_array = np.clip(result_array, 0, 1)
        
        # 转换回图像
        result_8bit = (result_array * 255.0).astype(np.uint8)
        return Image.fromarray(result_8bit)
    
    def premultiply_alpha(self, image: Image.Image) -> Image.Image:
        """
        将直接Alpha图像转换为预乘Alpha
        
        Args:
            image: 直接Alpha图像
            
        Returns:
            预乘Alpha图像
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 应用预乘
        premult_rgb = rgb * alpha[:, :, np.newaxis]
        
        # 重新组合
        result_array = np.concatenate([premult_rgb, alpha[:, :, np.newaxis]], axis=2)
        result_array = np.clip(result_array, 0, 1)
        
        # 转换回图像
        result_8bit = (result_array * 255.0).astype(np.uint8)
        return Image.fromarray(result_8bit)
    
    def _enhanced_unpremultiply_rgb(self, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """增强的取消预乘处理 - 修复PNG边缘问题"""
        # 使用智能算法检测和处理预乘alpha
        unpremult_rgb = rgb.copy()
        
        # 对于每个颜色通道分别处理
        for c in range(3):
            channel = rgb[:, :, c]
            
            # 避免除零
            safe_alpha = np.where(alpha > self.epsilon, alpha, self.epsilon)
            
            # 取消预乘：RGB_straight = RGB_premult / Alpha
            unpremult_channel = channel / safe_alpha
            
            # 修复异常值 - 处理由于预乘导致的颜色失真
            unpremult_channel = self._fix_channel_artifacts(unpremult_channel, channel, alpha, c)
            
            unpremult_rgb[:, :, c] = unpremult_channel
        
        # 对于完全透明的像素，保持原始RGB值
        transparent_mask = alpha <= self.epsilon
        unpremult_rgb[transparent_mask] = rgb[transparent_mask]
        
        return np.clip(unpremult_rgb, 0, 1)
    
    def _fix_channel_artifacts(self, unpremult_channel: np.ndarray, original_channel: np.ndarray, 
                              alpha: np.ndarray, channel_idx: int) -> np.ndarray:
        """修复取消预乘后的通道伪影"""
        fixed_channel = unpremult_channel.copy()
        
        # 检测异常高的值（可能是除法错误）
        high_values = unpremult_channel > 1.2
        
        if np.any(high_values):
            # 对于异常高的值，使用基于邻域的修复
            fixed_channel = self._neighborhood_fix(fixed_channel, original_channel, alpha, high_values)
        
        # 检测异常低的值（可能是预乘导致的暗化）
        low_values = (unpremult_channel < 0.1) & (alpha > 0.3)  # 暗但不透明
        
        if np.any(low_values):
            # 对于异常暗的值，适当提升亮度
            enhancement_factor = 1.2 + (0.3 - unpremult_channel[low_values]) * 0.5
            fixed_channel[low_values] = np.minimum(unpremult_channel[low_values] * enhancement_factor, 1.0)
        
        return fixed_channel
    
    def _neighborhood_fix(self, channel: np.ndarray, original_channel: np.ndarray, 
                         alpha: np.ndarray, problem_mask: np.ndarray) -> np.ndarray:
        """使用邻域信息修复问题像素"""
        fixed_channel = channel.copy()
        h, w = problem_mask.shape
        
        # 获取问题像素的坐标
        problem_coords = np.where(problem_mask)
        
        for y, x in zip(problem_coords[0], problem_coords[1]):
            # 获取5x5邻域
            y_start, y_end = max(0, y-2), min(h, y+3)
            x_start, x_end = max(0, x-2), min(w, x+3)
            
            neighborhood = original_channel[y_start:y_end, x_start:x_end]
            neighborhood_alpha = alpha[y_start:y_end, x_start:x_end]
            
            # 计算基于alpha的加权平均
            weights = neighborhood_alpha * (1 - neighborhood_alpha)  # 优先选择半透明像素
            weights = weights / (np.sum(weights) + self.epsilon)
            
            # 计算修复值
            if np.sum(weights) > 0:
                fixed_value = np.sum(neighborhood * weights)
                # 混合原始值和修复值
                fixed_channel[y, x] = 0.7 * fixed_value + 0.3 * channel[y, x]
        
        return fixed_channel
    
    def _unpremultiply_rgb(self, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """取消RGB的预乘处理"""
        # 避免除零
        safe_alpha = np.where(alpha > self.epsilon, alpha, self.epsilon)
        
        # 取消预乘：RGB_straight = RGB_premult / Alpha
        unpremult_rgb = rgb / safe_alpha[:, :, np.newaxis]
        
        # 对于完全透明的像素，保持原始RGB值
        transparent_mask = alpha <= self.epsilon
        unpremult_rgb[transparent_mask] = rgb[transparent_mask]
        
        # 对于异常值进行修复
        unpremult_rgb = self._fix_unpremult_artifacts(unpremult_rgb, alpha)
        
        return np.clip(unpremult_rgb, 0, 1)
    
    def _fix_unpremult_artifacts(self, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """修复取消预乘后的伪影"""
        fixed_rgb = rgb.copy()
        
        # 检测异常亮的像素（可能是除法错误）
        brightness = np.mean(rgb, axis=2)
        bright_mask = brightness > 1.5
        
        if np.any(bright_mask):
            # 对异常亮的像素使用邻近像素的颜色
            fixed_rgb = self._interpolate_bright_pixels(fixed_rgb, bright_mask, alpha)
        
        return fixed_rgb
    
    def _interpolate_bright_pixels(self, rgb: np.ndarray, bright_mask: np.ndarray, 
                                  alpha: np.ndarray) -> np.ndarray:
        """插值修复异常亮的像素"""
        result = rgb.copy()
        h, w = bright_mask.shape
        
        # 对每个异常像素使用邻近正常像素的加权平均
        bright_coords = np.where(bright_mask)
        
        for y, x in zip(bright_coords[0], bright_coords[1]):
            # 获取3x3邻域
            y_start, y_end = max(0, y-1), min(h, y+2)
            x_start, x_end = max(0, x-1), min(w, x+2)
            
            neighborhood_rgb = rgb[y_start:y_end, x_start:x_end]
            neighborhood_alpha = alpha[y_start:y_end, x_start:x_end]
            neighborhood_bright = bright_mask[y_start:y_end, x_start:x_end]
            
            # 只使用正常的邻近像素
            normal_mask = ~neighborhood_bright & (neighborhood_alpha > self.epsilon)
            
            if np.any(normal_mask):
                # 使用Alpha值作为权重
                weights = neighborhood_alpha[normal_mask]
                weights = weights / (np.sum(weights) + self.epsilon)
                
                # 计算加权平均颜色
                for c in range(3):
                    normal_colors = neighborhood_rgb[:, :, c][normal_mask]
                    result[y, x, c] = np.sum(normal_colors * weights)
        
        return result


# 便捷函数
def fix_premultiplied_alpha(image: Image.Image) -> Tuple[Image.Image, Dict[str, Any]]:
    """
    自动检测并修复预乘Alpha问题
    
    Args:
        image: 输入图像
        
    Returns:
        修复后的图像和检测信息
    """
    handler = PremultipliedAlphaHandler()
    
    # 检测是否为预乘Alpha
    detection_result = handler.detect_premultiplied_alpha(image)
    
    if detection_result['is_premultiplied']:
        # 转换为直接Alpha
        fixed_image = handler.unpremultiply_alpha(image)
        detection_result['action'] = 'unpremultiplied'
    else:
        # 不需要处理
        fixed_image = image.copy()
        detection_result['action'] = 'no_change'
    
    return fixed_image, detection_result
