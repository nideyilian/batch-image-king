"""
PNG边缘修复器
专门解决PNG图像与背景融合时出现的深色边缘问题

常见问题：
1. PNG图像边缘出现深色轮廓
2. 与背景融合不自然
3. 半透明区域颜色失真
4. 预乘Alpha导致的黑边

解决方案：
1. 智能检测问题类型
2. 预乘Alpha修复
3. 边缘颜色校正
4. Alpha通道优化
5. 背景融合优化
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from typing import Tuple, Optional, Dict, Any
import warnings

from app.utils.image import ndops

warnings.filterwarnings('ignore', category=RuntimeWarning)


class PNGEdgeFixer:
    """PNG边缘修复器"""
    
    def __init__(self):
        self.epsilon = 1e-10
        
    def fix_dark_edges(self, image: Image.Image, 
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
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 转换为numpy数组
        img_array = np.array(image, dtype=np.float64) / 255.0
        
        # 步骤1: 检测问题类型
        problem_analysis = self._analyze_edge_problems(img_array)
        
        # 步骤2: 根据问题类型应用相应的修复
        if problem_analysis['has_premult_alpha']:
            img_array = self._fix_premultiplied_alpha(img_array)
        
        if problem_analysis['has_dark_edges']:
            img_array = self._fix_dark_edge_colors(img_array, background_color)
        
        if problem_analysis['has_rough_edges']:
            img_array = self._smooth_alpha_edges(img_array, fix_strength)
        
        # 步骤3: 最终优化
        img_array = self._final_edge_optimization(img_array, fix_strength)
        
        # 转换回图像
        result_array = np.clip(img_array, 0, 1)
        result_8bit = (result_array * 255).astype(np.uint8)
        
        return Image.fromarray(result_8bit)
    
    def _analyze_edge_problems(self, img_array: np.ndarray) -> Dict[str, Any]:
        """分析边缘问题类型"""
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 检测半透明区域
        semi_transparent = (alpha > 0.1) & (alpha < 0.9)
        
        analysis = {
            'has_premult_alpha': False,
            'has_dark_edges': False,
            'has_rough_edges': False,
            'edge_pixel_count': 0
        }
        
        if not np.any(semi_transparent):
            return analysis
        
        analysis['edge_pixel_count'] = np.sum(semi_transparent)
        
        # 检测预乘Alpha
        semi_rgb = rgb[semi_transparent]
        semi_alpha = alpha[semi_transparent]
        
        # 预乘Alpha特征：RGB值通常不超过Alpha值
        max_rgb_per_pixel = np.max(semi_rgb, axis=1)
        exceeds_alpha = max_rgb_per_pixel > (semi_alpha + self.epsilon)
        exceeds_ratio = np.sum(exceeds_alpha) / len(exceeds_alpha)
        
        analysis['has_premult_alpha'] = exceeds_ratio < 0.3
        
        # 检测深色边缘
        edge_brightness = np.mean(semi_rgb, axis=1)
        dark_edges = (edge_brightness < 0.3) & (semi_alpha > 0.3)
        dark_edge_ratio = np.sum(dark_edges) / len(dark_edges) if len(dark_edges) > 0 else 0
        
        analysis['has_dark_edges'] = dark_edge_ratio > 0.2
        
        # 检测粗糙边缘
        alpha_variance = np.var(alpha[semi_transparent])
        analysis['has_rough_edges'] = alpha_variance > 0.1
        
        return analysis
    
    def _fix_premultiplied_alpha(self, img_array: np.ndarray) -> np.ndarray:
        """修复预乘Alpha问题"""
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 安全的Alpha除法
        safe_alpha = np.where(alpha > self.epsilon, alpha, self.epsilon)
        
        # 取消预乘：RGB_straight = RGB_premult / Alpha
        unpremult_rgb = rgb / safe_alpha[:, :, np.newaxis]
        
        # 对完全透明的像素保持原始RGB
        transparent_mask = alpha <= self.epsilon
        unpremult_rgb[transparent_mask] = rgb[transparent_mask]
        
        # 限制在合理范围内
        unpremult_rgb = np.clip(unpremult_rgb, 0, 1)
        
        # 重新组合
        result = img_array.copy()
        result[:, :, :3] = unpremult_rgb
        
        return result
    
    def _fix_dark_edge_colors(self, img_array: np.ndarray, 
                             background_color: Optional[Tuple[int, int, int]]) -> np.ndarray:
        """修复深色边缘颜色"""
        rgb = img_array[:, :, :3]
        alpha = img_array[:, :, 3]
        
        # 默认背景色为白色
        if background_color is None:
            bg_color = np.array([1.0, 1.0, 1.0])
        else:
            bg_color = np.array(background_color) / 255.0
        
        # 检测需要修复的边缘像素
        edge_mask = self._detect_problem_edges(alpha)
        
        if np.any(edge_mask):
            # 对问题边缘进行颜色校正
            fixed_rgb = self._correct_edge_colors(rgb, alpha, edge_mask, bg_color)
            
            result = img_array.copy()
            result[:, :, :3] = fixed_rgb
            return result
        
        return img_array
    
    def _detect_problem_edges(self, alpha: np.ndarray) -> np.ndarray:
        """检测有问题的边缘像素"""
        # 使用梯度检测边缘（ndops.sobel 与 scipy.ndimage.sobel 逐位等价）
        grad_x = ndops.sobel(alpha, axis=1)
        grad_y = ndops.sobel(alpha, axis=0)
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)

        # 边缘阈值
        edge_threshold = 0.1
        return gradient_magnitude > edge_threshold
    
    def _correct_edge_colors(self, rgb: np.ndarray, alpha: np.ndarray, 
                           edge_mask: np.ndarray, bg_color: np.ndarray) -> np.ndarray:
        """校正边缘颜色"""
        corrected_rgb = rgb.copy()
        h, w = rgb.shape[:2]
        
        # 对每个边缘像素进行颜色校正
        edge_coords = np.where(edge_mask)
        
        for y, x in zip(edge_coords[0], edge_coords[1]):
            current_alpha = alpha[y, x]
            current_rgb = rgb[y, x]
            
            if current_alpha > 0.1:
                # 方法1: 颜色传播 - 使用邻近高Alpha像素的颜色
                neighbor_color = self._get_neighbor_color(rgb, alpha, y, x, h, w)
                
                if neighbor_color is not None:
                    # 混合邻近颜色和背景色
                    blend_factor = min(0.5, 1.0 - current_alpha)
                    corrected_color = (neighbor_color * (1 - blend_factor) + 
                                     bg_color * blend_factor)
                    corrected_rgb[y, x] = corrected_color
                else:
                    # 方法2: 背景色混合
                    blend_factor = 0.3
                    corrected_rgb[y, x] = (current_rgb * (1 - blend_factor) + 
                                         bg_color * blend_factor)
        
        return corrected_rgb
    
    def _get_neighbor_color(self, rgb: np.ndarray, alpha: np.ndarray, 
                          y: int, x: int, h: int, w: int) -> Optional[np.ndarray]:
        """获取邻近像素的颜色"""
        # 搜索半径
        radius = 2
        
        # 获取邻域
        y_start = max(0, y - radius)
        y_end = min(h, y + radius + 1)
        x_start = max(0, x - radius)
        x_end = min(w, x + radius + 1)
        
        neighbor_rgb = rgb[y_start:y_end, x_start:x_end]
        neighbor_alpha = alpha[y_start:y_end, x_start:x_end]
        
        # 找到高Alpha值的邻近像素
        high_alpha_mask = neighbor_alpha > 0.8
        
        if np.any(high_alpha_mask):
            # 使用Alpha值作为权重计算加权平均
            weights = neighbor_alpha[high_alpha_mask]
            weights = weights / (np.sum(weights) + self.epsilon)
            
            weighted_color = np.zeros(3)
            for i in range(3):
                channel_values = neighbor_rgb[:, :, i][high_alpha_mask]
                weighted_color[i] = np.sum(channel_values * weights)
            
            return weighted_color
        
        return None
    
    def _smooth_alpha_edges(self, img_array: np.ndarray, strength: float) -> np.ndarray:
        """平滑Alpha边缘"""
        alpha = img_array[:, :, 3]
        
        # 转换为PIL图像进行滤波
        alpha_img = Image.fromarray((alpha * 255).astype(np.uint8), 'L')
        
        # 应用高斯模糊
        blur_radius = max(0.5, min(2.0, strength))
        alpha_smooth = alpha_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # 转换回numpy数组
        alpha_smooth_array = np.array(alpha_smooth).astype(np.float64) / 255.0
        
        # 更新结果
        result = img_array.copy()
        result[:, :, 3] = alpha_smooth_array
        
        return result
    
    def _final_edge_optimization(self, img_array: np.ndarray, strength: float) -> np.ndarray:
        """最终边缘优化"""
        # 对整个图像应用轻微的边缘增强
        alpha = img_array[:, :, 3]
        
        # 使用PIL进行边缘增强
        alpha_img = Image.fromarray((alpha * 255).astype(np.uint8), 'L')
        
        # 轻微的锐化以改善边缘质量
        enhancer = ImageEnhance.Sharpness(alpha_img)
        enhancement_factor = 1.0 + (strength - 1.0) * 0.2  # 轻微增强
        alpha_enhanced = enhancer.enhance(enhancement_factor)
        
        # 转换回numpy数组
        alpha_enhanced_array = np.array(alpha_enhanced).astype(np.float64) / 255.0
        
        # 更新结果
        result = img_array.copy()
        result[:, :, 3] = alpha_enhanced_array
        
        return result


# 便捷函数
def fix_png_dark_edges_direct(image: Image.Image,
                             background_color: Optional[Tuple[int, int, int]] = None,
                             fix_strength: float = 1.0) -> Image.Image:
    """
    修复PNG深色边缘的便捷函数（直接调用，避免循环导入）

    Args:
        image: 输入PNG图像
        background_color: 背景颜色RGB (可选)
        fix_strength: 修复强度 (0.0-2.0)

    Returns:
        修复后的图像
    """
    fixer = PNGEdgeFixer()
    return fixer.fix_dark_edges(image, background_color, fix_strength)


def auto_fix_png_for_background_direct(image: Image.Image,
                                      background_color: Tuple[int, int, int]) -> Image.Image:
    """
    自动修复PNG图像以适配特定背景色（直接调用，避免循环导入）

    Args:
        image: 输入PNG图像
        background_color: 目标背景颜色RGB

    Returns:
        优化后的图像
    """
    fixer = PNGEdgeFixer()

    # 根据背景色亮度调整修复强度
    bg_brightness = sum(background_color) / (3 * 255)

    if bg_brightness < 0.3:  # 深色背景
        fix_strength = 1.5
    elif bg_brightness > 0.7:  # 浅色背景
        fix_strength = 1.2
    else:  # 中等亮度背景
        fix_strength = 1.0

    return fixer.fix_dark_edges(image, background_color, fix_strength)
