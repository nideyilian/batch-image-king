"""
智能画质保持引擎
实现专业级的图像质量保持技术，包括：
1. 边缘保护缩放
2. 内容感知缩放
3. 智能锐化算法
4. 超分辨率技术
5. 噪声抑制
6. 细节增强
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import cv2
from typing import Tuple, Optional, Dict, Any
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


class ScalingMethod(Enum):
    """缩放方法枚举"""
    EDGE_PRESERVING = "edge_preserving"
    CONTENT_AWARE = "content_aware"
    SUPER_RESOLUTION = "super_resolution"
    LANCZOS_PLUS = "lanczos_plus"
    BICUBIC_SHARP = "bicubic_sharp"
    ADAPTIVE = "adaptive"


class ContentType(Enum):
    """内容类型枚举"""
    PHOTO = "photo"
    TEXT = "text"
    GRAPHICS = "graphics"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class QualityEngine:
    """智能画质保持引擎"""
    
    def __init__(self, enable_gpu: bool = False):
        """
        初始化质量引擎
        
        Args:
            enable_gpu: 是否启用GPU加速
        """
        self.enable_gpu = enable_gpu
        self.gpu_available = False
        
        if enable_gpu:
            self._check_gpu_support()
        
        # 初始化滤波器
        self._init_filters()
    
    def _check_gpu_support(self):
        """检查GPU支持"""
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                self.gpu_available = True
                safe_print(f"[INFO] GPU加速可用，检测到 {cv2.cuda.getCudaEnabledDeviceCount()} 个CUDA设备")
            else:
                self.gpu_available = False
                safe_print("[INFO] 未检测到CUDA设备")
        except Exception:
            self.gpu_available = False
            safe_print("[INFO] OpenCV未编译CUDA支持")
    
    def _init_filters(self):
        """初始化各种滤波器"""
        # 边缘检测滤波器
        self.sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
        self.sobel_y = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
        
        # 拉普拉斯滤波器
        self.laplacian = np.array([[0, -1, 0], [-1, 4, -1], [0, -1, 0]], dtype=np.float32)
        
        # 高斯核
        self.gaussian_3x3 = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=np.float32) / 16
        self.gaussian_5x5 = cv2.getGaussianKernel(5, 1.0) @ cv2.getGaussianKernel(5, 1.0).T
    
    def analyze_content(self, image: Image.Image) -> Dict[str, Any]:
        """
        分析图像内容特征
        
        Args:
            image: 输入图像
            
        Returns:
            包含内容分析结果的字典
        """
        # 转换为灰度图进行分析
        gray = np.array(image.convert('L'), dtype=np.float32) / 255.0
        
        # 计算边缘密度
        edges = cv2.Canny((gray * 255).astype(np.uint8), 50, 150)
        edge_density = np.count_nonzero(edges) / edges.size
        
        # 计算纹理复杂度
        texture_complexity = self._calculate_texture_complexity(gray)
        
        # 计算颜色复杂度
        color_complexity = self._calculate_color_complexity(image)
        
        # 检测文字特征
        has_text = self._detect_text_features(gray)
        
        # 检测照片特征
        is_photo = self._detect_photo_features(image)
        
        # 确定内容类型
        content_type = self._determine_content_type(edge_density, texture_complexity, 
                                                   color_complexity, has_text, is_photo)
        
        return {
            'edge_density': edge_density,
            'texture_complexity': texture_complexity,
            'color_complexity': color_complexity,
            'has_text': has_text,
            'is_photo': is_photo,
            'content_type': content_type,
            'recommended_method': self._recommend_scaling_method(content_type, edge_density)
        }
    
    def _calculate_texture_complexity(self, gray: np.ndarray) -> float:
        """计算纹理复杂度"""
        # 使用局部二值模式(LBP)的简化版本
        h, w = gray.shape
        complexity = 0.0
        
        # 计算局部方差
        kernel = np.ones((3, 3)) / 9
        local_mean = cv2.filter2D(gray, -1, kernel)
        local_variance = cv2.filter2D(gray**2, -1, kernel) - local_mean**2
        
        complexity = np.mean(local_variance)
        return min(complexity * 10, 1.0)  # 归一化到0-1
    
    def _calculate_color_complexity(self, image: Image.Image) -> float:
        """计算颜色复杂度"""
        # 计算颜色直方图的熵
        if image.mode == 'RGBA':
            rgb_image = image.convert('RGB')
        else:
            rgb_image = image
        
        # 降低分辨率以提高计算速度
        small_image = rgb_image.resize((64, 64), Image.LANCZOS)
        
        # 计算每个通道的直方图
        hist_r = np.histogram(np.array(small_image)[:,:,0], bins=32, range=(0, 255))[0]
        hist_g = np.histogram(np.array(small_image)[:,:,1], bins=32, range=(0, 255))[0]
        hist_b = np.histogram(np.array(small_image)[:,:,2], bins=32, range=(0, 255))[0]
        
        # 计算熵
        def calculate_entropy(hist):
            hist = hist + 1e-10  # 避免log(0)
            hist = hist / np.sum(hist)
            return -np.sum(hist * np.log2(hist))
        
        entropy = (calculate_entropy(hist_r) + calculate_entropy(hist_g) + calculate_entropy(hist_b)) / 3
        return min(entropy / 5.0, 1.0)  # 归一化
    
    def _detect_text_features(self, gray: np.ndarray) -> bool:
        """检测文字特征"""
        # 计算边缘方向性
        grad_x = cv2.filter2D(gray, -1, self.sobel_x)
        grad_y = cv2.filter2D(gray, -1, self.sobel_y)
        
        # 计算梯度幅值和方向
        magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        # 文字通常有较强的水平和垂直边缘
        horizontal_edges = np.sum(np.abs(grad_y) > 0.1)
        vertical_edges = np.sum(np.abs(grad_x) > 0.1)
        total_pixels = gray.size
        
        edge_ratio = (horizontal_edges + vertical_edges) / total_pixels
        return edge_ratio > 0.15
    
    def _detect_photo_features(self, image: Image.Image) -> bool:
        """检测照片特征"""
        # 转换为HSV进行分析
        hsv = np.array(image.convert('HSV'))
        
        # 计算饱和度分布
        saturation = hsv[:,:,1] / 255.0
        high_saturation_ratio = np.sum(saturation > 0.3) / saturation.size
        
        # 计算亮度分布
        value = hsv[:,:,2] / 255.0
        brightness_variance = np.var(value)
        
        # 照片通常有较高的饱和度变化和亮度变化
        return high_saturation_ratio > 0.2 and brightness_variance > 0.05
    
    def _determine_content_type(self, edge_density: float, texture_complexity: float,
                               color_complexity: float, has_text: bool, is_photo: bool) -> ContentType:
        """确定内容类型"""
        if has_text and edge_density > 0.2:
            return ContentType.TEXT
        elif is_photo and color_complexity > 0.5:
            return ContentType.PHOTO
        elif edge_density > 0.3 and texture_complexity < 0.3:
            return ContentType.GRAPHICS
        elif has_text and is_photo:
            return ContentType.MIXED
        else:
            return ContentType.UNKNOWN
    
    def _recommend_scaling_method(self, content_type: ContentType, edge_density: float) -> ScalingMethod:
        """推荐缩放方法"""
        if content_type == ContentType.TEXT:
            return ScalingMethod.BICUBIC_SHARP
        elif content_type == ContentType.PHOTO:
            return ScalingMethod.EDGE_PRESERVING if edge_density > 0.1 else ScalingMethod.LANCZOS_PLUS
        elif content_type == ContentType.GRAPHICS:
            return ScalingMethod.SUPER_RESOLUTION
        elif content_type == ContentType.MIXED:
            return ScalingMethod.ADAPTIVE
        else:
            return ScalingMethod.LANCZOS_PLUS
    
    def smart_resize(self, image: Image.Image, target_size: Tuple[int, int],
                    method: Optional[ScalingMethod] = None) -> Image.Image:
        """
        智能缩放图像
        
        Args:
            image: 输入图像
            target_size: 目标尺寸 (width, height)
            method: 缩放方法（None表示自动选择）
            
        Returns:
            缩放后的图像
        """
        # 分析内容特征
        analysis = self.analyze_content(image)
        
        # 选择缩放方法
        if method is None:
            method = analysis['recommended_method']
        
        safe_print(f"[INFO] 使用缩放方法: {method.value}, 内容类型: {analysis['content_type'].value}")
        
        # 执行缩放
        if method == ScalingMethod.EDGE_PRESERVING:
            return self._edge_preserving_resize(image, target_size)
        elif method == ScalingMethod.CONTENT_AWARE:
            return self._content_aware_resize(image, target_size, analysis)
        elif method == ScalingMethod.SUPER_RESOLUTION:
            return self._super_resolution_resize(image, target_size)
        elif method == ScalingMethod.LANCZOS_PLUS:
            return self._lanczos_plus_resize(image, target_size)
        elif method == ScalingMethod.BICUBIC_SHARP:
            return self._bicubic_sharp_resize(image, target_size)
        elif method == ScalingMethod.ADAPTIVE:
            return self._adaptive_resize(image, target_size, analysis)
        else:
            return image.resize(target_size, Image.LANCZOS)
    
    def _edge_preserving_resize(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """边缘保护缩放"""
        # 转换为OpenCV格式
        cv_image = cv2.cvtColor(np.array(image.convert('RGBA')), cv2.COLOR_RGBA2BGRA)
        
        # 使用边缘保护滤波
        filtered = cv2.edgePreservingFilter(cv_image, flags=cv2.RECURS_FILTER, 
                                          sigma_s=50, sigma_r=0.4)
        
        # 缩放
        resized = cv2.resize(filtered, target_size, interpolation=cv2.INTER_CUBIC)
        
        # 转换回PIL
        result_array = cv2.cvtColor(resized, cv2.COLOR_BGRA2RGBA)
        return Image.fromarray(result_array)
    
    def _content_aware_resize(self, image: Image.Image, target_size: Tuple[int, int],
                            analysis: Dict[str, Any]) -> Image.Image:
        """内容感知缩放"""
        # 根据内容特征调整缩放策略
        if analysis['has_text']:
            # 文字内容使用锐化缩放
            return self._bicubic_sharp_resize(image, target_size)
        elif analysis['is_photo']:
            # 照片内容使用边缘保护
            return self._edge_preserving_resize(image, target_size)
        else:
            # 其他内容使用标准方法
            return self._lanczos_plus_resize(image, target_size)
    
    def _super_resolution_resize(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """超分辨率缩放"""
        current_size = image.size
        scale_x = target_size[0] / current_size[0]
        scale_y = target_size[1] / current_size[1]
        
        # 如果是放大且倍数不大，使用超分辨率
        if scale_x > 1.0 and scale_y > 1.0 and max(scale_x, scale_y) <= 4.0:
            return self._multi_step_upscale(image, target_size)
        else:
            return self._lanczos_plus_resize(image, target_size)
    
    def _lanczos_plus_resize(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """增强Lanczos缩放"""
        # 基础Lanczos缩放
        resized = image.resize(target_size, Image.LANCZOS)
        
        # 计算缩放比例
        scale_ratio = min(target_size[0] / image.width, target_size[1] / image.height)
        
        # 根据缩放比例应用后处理
        if scale_ratio < 1.0:  # 缩小
            # 轻微锐化补偿模糊
            enhancer = ImageEnhance.Sharpness(resized)
            resized = enhancer.enhance(1.0 + (1.0 - scale_ratio) * 0.3)
        elif scale_ratio > 1.0:  # 放大
            # 应用USM锐化
            resized = self._apply_unsharp_mask(resized, radius=0.8, amount=0.3)
        
        return resized
    
    def _bicubic_sharp_resize(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """锐化双三次缩放"""
        # 双三次缩放
        resized = image.resize(target_size, Image.BICUBIC)
        
        # 应用锐化
        return self._apply_unsharp_mask(resized, radius=1.0, amount=0.5, threshold=3)
    
    def _adaptive_resize(self, image: Image.Image, target_size: Tuple[int, int],
                        analysis: Dict[str, Any]) -> Image.Image:
        """自适应缩放"""
        # 根据图像特征动态选择最佳方法
        edge_density = analysis['edge_density']
        
        if edge_density > 0.3:
            # 高边缘密度，使用边缘保护
            return self._edge_preserving_resize(image, target_size)
        elif edge_density > 0.1:
            # 中等边缘密度，使用锐化缩放
            return self._bicubic_sharp_resize(image, target_size)
        else:
            # 低边缘密度，使用平滑缩放
            return self._lanczos_plus_resize(image, target_size)
    
    def _multi_step_upscale(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """多步放大"""
        current_image = image
        current_size = image.size
        
        # 计算总放大倍数
        scale_factor = max(target_size[0] / current_size[0], target_size[1] / current_size[1])
        
        # 分步放大，每步最多2倍
        while scale_factor > 2.0:
            intermediate_size = (min(current_size[0] * 2, target_size[0]),
                               min(current_size[1] * 2, target_size[1]))
            
            # 双三次插值放大
            current_image = current_image.resize(intermediate_size, Image.BICUBIC)
            
            # 应用轻微锐化
            current_image = self._apply_unsharp_mask(current_image, radius=0.5, amount=0.25)
            
            current_size = intermediate_size
            scale_factor = max(target_size[0] / current_size[0], target_size[1] / current_size[1])
        
        # 最后一步
        if current_size != target_size:
            current_image = current_image.resize(target_size, Image.BICUBIC)
            current_image = self._apply_unsharp_mask(current_image, radius=0.8, amount=0.3)
        
        return current_image
    
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
