"""
超级抗锯齿系统
解决边缘锯齿问题的终极解决方案
实现多种高级抗锯齿技术
"""

import numpy as np
from PIL import Image, ImageFilter, ImageDraw
from typing import Tuple, Optional, Union
import os

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

# OpenCV是可选依赖
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    # 只在调试模式下显示详细信息
    import os
    if os.getenv('DEBUG_MODE') == '1':
        safe_print("[INFO] OpenCV不可用，超级抗锯齿将使用基础实现")

# SciPy是可选依赖
try:
    import scipy.ndimage as ndimage
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    # 只在调试模式下显示详细信息
    import os
    if os.getenv('DEBUG_MODE') == '1':
        safe_print("[INFO] SciPy不可用，部分高级抗锯齿功能将被禁用")


class SuperAntialiasing:
    """超级抗锯齿系统"""
    
    @staticmethod
    def apply_super_antialiasing(image: Image.Image, method: str = 'msaa_4x',
                                strength: float = 1.0) -> Image.Image:
        """
        应用超级抗锯齿

        Args:
            image: 输入图像
            method: 抗锯齿方法 ('msaa_4x', 'msaa_8x', 'fxaa', 'smaa', 'distance_field')
            strength: 抗锯齿强度 (0.0-2.0)

        Returns:
            抗锯齿后的图像
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # 如果没有必要的依赖，使用基础抗锯齿
        if not CV2_AVAILABLE:
            return SuperAntialiasing._basic_antialiasing(image, strength)

        if method == 'msaa_4x':
            return SuperAntialiasing._msaa_4x(image, strength)
        elif method == 'msaa_8x':
            return SuperAntialiasing._msaa_8x(image, strength)
        elif method == 'fxaa':
            return SuperAntialiasing._fxaa(image, strength)
        elif method == 'smaa':
            return SuperAntialiasing._smaa(image, strength)
        elif method == 'distance_field':
            return SuperAntialiasing._distance_field_aa(image, strength)
        else:
            return SuperAntialiasing._msaa_4x(image, strength)

    @staticmethod
    def _basic_antialiasing(image: Image.Image, strength: float = 1.0) -> Image.Image:
        """
        基础抗锯齿实现（不依赖OpenCV）
        使用PIL的内置滤镜
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # 分离通道
        r, g, b, a = image.split()

        # 对alpha通道应用轻微模糊来减少锯齿
        blur_radius = max(0.5, min(2.0, strength))
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # 重新组合
        result = Image.merge('RGBA', (r, g, b, a_smooth))

        return result

    @staticmethod
    def _basic_edge_enhancement(image: Image.Image, strength: float = 1.0) -> Image.Image:
        """
        基础边缘增强实现（不依赖OpenCV）
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # 分离通道
        r, g, b, a = image.split()

        # 对alpha通道应用边缘增强滤镜
        from PIL import ImageFilter        # 使用EDGE_ENHANCE滤镜
        
        a_enhanced = a.filter(ImageFilter.EDGE_ENHANCE)

        # 混合原始和增强的alpha
        blend_factor = min(1.0, strength * 0.3)
        a_final = Image.blend(a, a_enhanced, blend_factor)

        # 重新组合
        result = Image.merge('RGBA', (r, g, b, a_final))

        return result
    
    @staticmethod
    def _msaa_4x(image: Image.Image, strength: float) -> Image.Image:
        """
        4x多重采样抗锯齿 (MSAA)
        """
        # 放大4倍进行超采样
        upscale_factor = 4
        original_size = image.size
        upscaled_size = (original_size[0] * upscale_factor, original_size[1] * upscale_factor)
        
        # 使用高质量插值放大
        upscaled = image.resize(upscaled_size, Image.LANCZOS)
        
        # 应用边缘检测和增强
        upscaled = SuperAntialiasing._enhance_alpha_edges(upscaled, strength)
        
        # 使用高质量滤波缩回原尺寸
        result = upscaled.resize(original_size, Image.LANCZOS)
        
        return result
    
    @staticmethod
    def _msaa_8x(image: Image.Image, strength: float) -> Image.Image:
        """
        8x多重采样抗锯齿 (MSAA)
        """
        # 放大8倍进行超采样
        upscale_factor = 8
        original_size = image.size
        upscaled_size = (original_size[0] * upscale_factor, original_size[1] * upscale_factor)
        
        # 使用高质量插值放大
        upscaled = image.resize(upscaled_size, Image.LANCZOS)
        
        # 应用边缘检测和增强
        upscaled = SuperAntialiasing._enhance_alpha_edges(upscaled, strength)
        
        # 使用高质量滤波缩回原尺寸
        result = upscaled.resize(original_size, Image.LANCZOS)
        
        return result

    @staticmethod
    def _fxaa(image: Image.Image, strength: float) -> Image.Image:
        """
        快速近似抗锯齿 (FXAA)
        """
        # 转换为数组
        img_array = np.array(image, dtype=np.float32) / 255.0
        
        # 计算亮度
        rgb = img_array[:,:,:3]
        alpha = img_array[:,:,3]
        luma = 0.299 * rgb[:,:,0] + 0.587 * rgb[:,:,1] + 0.114 * rgb[:,:,2]
        
        # 检测边缘
        luma_padded = np.pad(luma, 1, mode='edge')
        
        # 计算局部对比度
        luma_n = luma_padded[0:-2, 1:-1]  # 北
        luma_s = luma_padded[2:, 1:-1]    # 南
        luma_e = luma_padded[1:-1, 2:]    # 东
        luma_w = luma_padded[1:-1, 0:-2]  # 西
        luma_ne = luma_padded[0:-2, 2:]   # 东北
        luma_nw = luma_padded[0:-2, 0:-2] # 西北
        luma_se = luma_padded[2:, 2:]     # 东南
        luma_sw = luma_padded[2:, 0:-2]   # 西南
        
        # 计算梯度
        grad_h = np.abs(luma_e - luma_w)
        grad_v = np.abs(luma_n - luma_s)
        
        # 检测边缘方向
        is_horizontal = grad_h >= grad_v
        
        # 应用FXAA滤波
        edge_threshold = 0.0625 * strength
        edge_mask = np.maximum(grad_h, grad_v) > edge_threshold
        
        if np.any(edge_mask):
            # 水平边缘处理
            h_blend = np.where(is_horizontal & edge_mask,
                             (luma_n + luma_s) * 0.5,
                             luma)
            
            # 垂直边缘处理
            v_blend = np.where(~is_horizontal & edge_mask,
                             (luma_e + luma_w) * 0.5,
                             h_blend)
            
            # 应用到RGB通道
            for c in range(3):
                rgb[:,:,c] = np.where(edge_mask, v_blend, rgb[:,:,c])
        
        # 重新组合
        result_array = np.concatenate([rgb, alpha[:,:,np.newaxis]], axis=2)
        result_array = np.clip(result_array, 0, 1)
        
        result_8bit = (result_array * 255).astype(np.uint8)
        return Image.fromarray(result_8bit, 'RGBA')
    
    @staticmethod
    def _smaa(image: Image.Image, strength: float) -> Image.Image:
        """
        子像素形态学抗锯齿 (SMAA)
        """
        if not CV2_AVAILABLE:
            # 如果没有OpenCV，使用基础抗锯齿
            return SuperAntialiasing._basic_antialiasing(image, strength)

        # 转换为数组
        img_array = np.array(image, dtype=np.float32) / 255.0
        alpha = img_array[:,:,3]

        # 边缘检测
        alpha_uint8 = (alpha * 255).astype(np.uint8)

        # 使用多尺度边缘检测
        edges_1 = cv2.Canny(alpha_uint8, 30, 100)
        edges_2 = cv2.Canny(alpha_uint8, 50, 150)
        edges_3 = cv2.Canny(alpha_uint8, 70, 200)
        
        # 合并边缘
        combined_edges = np.maximum(np.maximum(edges_1, edges_2), edges_3) > 0
        
        if np.any(combined_edges):
            # 形态学操作
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            
            # 膨胀边缘区域
            edge_dilated = cv2.dilate(combined_edges.astype(np.uint8), kernel, iterations=1) > 0
            
            # 多层高斯模糊
            alpha_blur_1 = cv2.GaussianBlur(alpha, (3, 3), 0.5 * strength)
            alpha_blur_2 = cv2.GaussianBlur(alpha, (5, 5), 1.0 * strength)
            alpha_blur_3 = cv2.GaussianBlur(alpha, (7, 7), 1.5 * strength)
            
            # 根据边缘强度选择模糊级别
            edge_strength = cv2.GaussianBlur(combined_edges.astype(np.float32), (3, 3), 1.0)
            
            # 混合不同级别的模糊
            alpha_blended = np.where(edge_strength > 0.7, alpha_blur_3,
                                   np.where(edge_strength > 0.4, alpha_blur_2, alpha_blur_1))
            
            # 只在边缘区域应用
            img_array[:,:,3] = np.where(edge_dilated, alpha_blended, alpha)
        
        # 转换回图像
        result_8bit = (img_array * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_8bit, 'RGBA')
    
    @staticmethod
    def _distance_field_aa(image: Image.Image, strength: float) -> Image.Image:
        """
        距离场抗锯齿
        """
        if not CV2_AVAILABLE:
            # 如果没有OpenCV，使用基础抗锯齿
            return SuperAntialiasing._basic_antialiasing(image, strength)

        # 转换为数组
        img_array = np.array(image, dtype=np.float32) / 255.0
        alpha = img_array[:,:,3]

        # 创建距离场
        alpha_binary = (alpha > 0.5).astype(np.uint8)

        # 计算距离变换
        dist_inside = cv2.distanceTransform(alpha_binary, cv2.DIST_L2, 3)
        dist_outside = cv2.distanceTransform(1 - alpha_binary, cv2.DIST_L2, 3)
        
        # 组合距离场
        distance_field = dist_inside - dist_outside
        
        # 使用距离场生成平滑的alpha
        smooth_alpha = np.clip(0.5 + distance_field * strength * 0.1, 0, 1)
        
        # 应用平滑的alpha
        img_array[:,:,3] = smooth_alpha
        
        # 转换回图像
        result_8bit = (img_array * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_8bit, 'RGBA')
    
    @staticmethod
    def _enhance_alpha_edges(image: Image.Image, strength: float) -> Image.Image:
        """
        增强alpha边缘
        """
        if not CV2_AVAILABLE:
            # 如果没有OpenCV，使用基础边缘增强
            return SuperAntialiasing._basic_edge_enhancement(image, strength)

        # 转换为数组
        img_array = np.array(image, dtype=np.float32) / 255.0
        alpha = img_array[:,:,3]

        # 多尺度边缘检测
        alpha_uint8 = (alpha * 255).astype(np.uint8)

        # 使用不同参数的Canny检测
        edges_fine = cv2.Canny(alpha_uint8, 20, 60)
        edges_medium = cv2.Canny(alpha_uint8, 50, 150)
        edges_coarse = cv2.Canny(alpha_uint8, 100, 200)
        
        # 合并边缘
        all_edges = np.maximum(np.maximum(edges_fine, edges_medium), edges_coarse) > 0
        
        if np.any(all_edges):
            # 创建多层模糊
            kernels = [(3, 3), (5, 5), (7, 7)]
            sigmas = [0.5, 1.0, 1.5]
            
            blurred_alphas = []
            for kernel, sigma in zip(kernels, sigmas):
                blurred = cv2.GaussianBlur(alpha, kernel, sigma * strength)
                blurred_alphas.append(blurred)
            
            # 根据边缘强度混合
            kernel = np.ones((3, 3), np.uint8)
            edge_dilated = cv2.dilate(all_edges.astype(np.uint8), kernel, iterations=2) > 0
            
            # 计算边缘距离
            edge_distance = cv2.distanceTransform((~edge_dilated).astype(np.uint8), cv2.DIST_L2, 3)
            edge_weight = np.exp(-edge_distance * 0.5)
            
            # 混合原始和模糊的alpha
            alpha_enhanced = alpha.copy()
            for i, blurred in enumerate(blurred_alphas):
                weight = edge_weight * (0.3 - i * 0.1) * strength
                alpha_enhanced = alpha_enhanced * (1 - weight) + blurred * weight
            
            img_array[:,:,3] = np.clip(alpha_enhanced, 0, 1)
        
        # 转换回图像
        result_8bit = (img_array * 255).astype(np.uint8)
        return Image.fromarray(result_8bit, 'RGBA')
    
    @staticmethod
    def _multi_layer_edge_enhancement(image: Image.Image, strength: float) -> Image.Image:
        """
        多层边缘增强
        """
        # 应用多种边缘增强技术
        result = image.copy()
        
        # 1. 基础边缘平滑
        result = SuperAntialiasing._enhance_alpha_edges(result, strength * 0.5)
        
        # 2. 形态学平滑
        img_array = np.array(result, dtype=np.float32) / 255.0
        alpha = img_array[:,:,3]
        
        # 使用椭圆形结构元素
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        alpha_opened = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel)
        alpha_closed = cv2.morphologyEx(alpha_opened, cv2.MORPH_CLOSE, kernel)
        
        # 混合形态学结果
        img_array[:,:,3] = alpha * 0.7 + alpha_closed * 0.3 * strength
        
        result = Image.fromarray((img_array * 255).astype(np.uint8), 'RGBA')
        
        # 3. 双边滤波
        result = SuperAntialiasing._bilateral_filter_alpha(result, strength)
        
        return result
    
    @staticmethod
    def _bilateral_filter_alpha(image: Image.Image, strength: float) -> Image.Image:
        """
        对alpha通道应用双边滤波
        """
        img_array = np.array(image, dtype=np.float32) / 255.0
        alpha = img_array[:,:,3]
        
        # 双边滤波参数
        d = int(5 + strength * 5)  # 邻域直径
        sigma_color = 50 * strength  # 颜色空间标准差
        sigma_space = 50 * strength  # 坐标空间标准差
        
        # 应用双边滤波
        alpha_uint8 = (alpha * 255).astype(np.uint8)
        alpha_filtered = cv2.bilateralFilter(alpha_uint8, d, sigma_color, sigma_space)
        
        # 更新alpha通道
        img_array[:,:,3] = alpha_filtered.astype(np.float32) / 255.0
        
        # 转换回图像
        result_8bit = (img_array * 255).astype(np.uint8)
        return Image.fromarray(result_8bit, 'RGBA')
    
    @staticmethod
    def _high_quality_downscale(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """
        高质量缩小
        """
        # 使用多步缩小以保持质量
        current_image = image
        current_size = image.size
        
        while max(current_size[0] / target_size[0], current_size[1] / target_size[1]) > 2:
            # 每次最多缩小2倍
            intermediate_size = (
                max(current_size[0] // 2, target_size[0]),
                max(current_size[1] // 2, target_size[1])
            )
            
            # 应用轻微模糊防止混叠
            current_image = current_image.filter(ImageFilter.GaussianBlur(radius=0.5))
            
            # 缩小
            current_image = current_image.resize(intermediate_size, Image.LANCZOS)
            current_size = intermediate_size
        
        # 最后一步缩放到目标尺寸
        if current_size != target_size:
            current_image = current_image.filter(ImageFilter.GaussianBlur(radius=0.3))
            current_image = current_image.resize(target_size, Image.LANCZOS)
        
        return current_image


def test_super_antialiasing():
    """测试超级抗锯齿系统"""
    safe_print("=== 测试超级抗锯齿系统 ===")
    
    # 创建测试图像 - 包含各种锯齿情况
    test_image = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(test_image)
    
    # 绘制各种形状来测试锯齿
    # 1. 斜线
    draw.line([(10, 10), (190, 50)], fill=(255, 0, 0, 255), width=3)
    
    # 2. 圆形
    draw.ellipse([50, 50, 150, 150], outline=(0, 255, 0, 255), width=2)
    
    # 3. 多边形
    points = [(100, 20), (180, 80), (150, 180), (50, 180), (20, 80)]
    draw.polygon(points, outline=(0, 0, 255, 255), width=2)
    
    # 4. 小细节
    for i in range(5):
        draw.rectangle([160 + i*5, 160 + i*5, 165 + i*5, 165 + i*5], 
                      fill=(255, 255, 0, 200))
    
    # 保存原始图像
    test_image.save('test_original_jagged.png')
    
    # 测试不同的抗锯齿方法
    methods = ['msaa_4x', 'msaa_8x', 'fxaa', 'smaa', 'distance_field']
    
    for method in methods:
        try:
            result = SuperAntialiasing.apply_super_antialiasing(test_image, method, strength=1.0)
            result.save(f'test_antialiased_{method}.png')
            safe_print(f"✓ {method} 抗锯齿完成")
        except Exception as e:
            safe_print(f"✗ {method} 抗锯齿失败: {e}")
    
    # 测试不同强度
    for strength in [0.5, 1.0, 1.5, 2.0]:
        try:
            result = SuperAntialiasing.apply_super_antialiasing(test_image, 'msaa_8x', strength=strength)
            result.save(f'test_antialiased_strength_{strength}.png')
            safe_print(f"✓ 强度 {strength} 测试完成")
        except Exception as e:
            safe_print(f"✗ 强度 {strength} 测试失败: {e}")
    
    safe_print("✓ 超级抗锯齿测试完成")
    return True


if __name__ == "__main__":
    test_super_antialiasing()
