"""
优化图像处理器
使用高效算法和向量化操作大幅提升图像处理性能
专门针对批量导出场景优化
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from typing import Tuple, Optional, List, Dict, Any
import time
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

# 尝试导入加速库
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from numba import jit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

try:
    import scipy.ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class OptimizedImageProcessor:
    """优化图像处理器"""
    
    def __init__(self):
        self.use_cv2 = CV2_AVAILABLE
        self.use_numba = NUMBA_AVAILABLE
        self.use_scipy = SCIPY_AVAILABLE
        
        safe_print(f"[图像处理] 优化库状态:")
        safe_print(f"  - OpenCV: {'✓' if self.use_cv2 else '✗'}")
        safe_print(f"  - Numba: {'✓' if self.use_numba else '✗'}")
        safe_print(f"  - SciPy: {'✓' if self.use_scipy else '✗'}")
    
    def fast_resize(self, image: Image.Image, size: Tuple[int, int], 
                   quality: str = 'high') -> Image.Image:
        """
        快速图像缩放
        
        Args:
            image: 输入图像
            size: 目标尺寸
            quality: 质量级别 ('fast', 'medium', 'high')
            
        Returns:
            缩放后的图像
        """
        if image.size == size:
            return image
        
        if self.use_cv2 and quality == 'fast':
            # 使用OpenCV进行快速缩放
            return self._cv2_resize(image, size)
        else:
            # 使用PIL进行高质量缩放
            if quality == 'fast':
                resample = Image.NEAREST
            elif quality == 'medium':
                resample = Image.BILINEAR
            else:
                resample = Image.LANCZOS
            
            return image.resize(size, resample)
    
    def _cv2_resize(self, image: Image.Image, size: Tuple[int, int]) -> Image.Image:
        """使用OpenCV进行快速缩放"""
        try:
            # 转换为numpy数组
            img_array = np.array(image)
            
            # 使用OpenCV缩放
            if len(img_array.shape) == 3:
                if img_array.shape[2] == 4:  # RGBA
                    resized = cv2.resize(img_array, size, interpolation=cv2.INTER_LINEAR)
                else:  # RGB
                    resized = cv2.resize(img_array, size, interpolation=cv2.INTER_LINEAR)
            else:  # 灰度
                resized = cv2.resize(img_array, size, interpolation=cv2.INTER_LINEAR)
            
            # 转换回PIL图像
            return Image.fromarray(resized, image.mode)
            
        except Exception as e:
            safe_print(f"[图像处理] OpenCV缩放失败，回退到PIL: {e}")
            return image.resize(size, Image.BILINEAR)
    
    def fast_rotate(self, image: Image.Image, angle: float, 
                   expand: bool = True) -> Image.Image:
        """
        快速图像旋转
        
        Args:
            image: 输入图像
            angle: 旋转角度
            expand: 是否扩展画布
            
        Returns:
            旋转后的图像
        """
        if abs(angle) < 0.1:  # 角度太小，不需要旋转
            return image
        
        if self.use_cv2:
            return self._cv2_rotate(image, angle, expand)
        else:
            return image.rotate(angle, expand=expand, fillcolor=(0, 0, 0, 0))
    
    def _cv2_rotate(self, image: Image.Image, angle: float, expand: bool) -> Image.Image:
        """使用OpenCV进行快速旋转"""
        try:
            img_array = np.array(image)
            h, w = img_array.shape[:2]
            
            # 计算旋转矩阵
            center = (w // 2, h // 2)
            rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            
            if expand:
                # 计算新的边界框
                cos_val = abs(rotation_matrix[0, 0])
                sin_val = abs(rotation_matrix[0, 1])
                new_w = int((h * sin_val) + (w * cos_val))
                new_h = int((h * cos_val) + (w * sin_val))
                
                # 调整旋转矩阵
                rotation_matrix[0, 2] += (new_w / 2) - center[0]
                rotation_matrix[1, 2] += (new_h / 2) - center[1]
                
                output_size = (new_w, new_h)
            else:
                output_size = (w, h)
            
            # 执行旋转
            rotated = cv2.warpAffine(img_array, rotation_matrix, output_size,
                                   flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT,
                                   borderValue=(0, 0, 0, 0))
            
            return Image.fromarray(rotated, image.mode)
            
        except Exception as e:
            safe_print(f"[图像处理] OpenCV旋转失败，回退到PIL: {e}")
            return image.rotate(angle, expand=expand, fillcolor=(0, 0, 0, 0))
    
    def fast_alpha_composite(self, background: Image.Image, 
                           foreground: Image.Image, 
                           position: Tuple[int, int] = (0, 0),
                           opacity: float = 1.0) -> Image.Image:
        """
        快速Alpha合成
        
        Args:
            background: 背景图像
            foreground: 前景图像
            position: 前景图像位置
            opacity: 前景图像不透明度
            
        Returns:
            合成后的图像
        """
        if self.use_numba:
            return self._numba_alpha_composite(background, foreground, position, opacity)
        else:
            return self._numpy_alpha_composite(background, foreground, position, opacity)
    
    def _numpy_alpha_composite(self, background: Image.Image, 
                              foreground: Image.Image,
                              position: Tuple[int, int],
                              opacity: float) -> Image.Image:
        """使用NumPy进行Alpha合成"""
        try:
            # 确保图像为RGBA模式
            if background.mode != 'RGBA':
                background = background.convert('RGBA')
            if foreground.mode != 'RGBA':
                foreground = foreground.convert('RGBA')
            
            # 转换为numpy数组
            bg_array = np.array(background, dtype=np.float32) / 255.0
            fg_array = np.array(foreground, dtype=np.float32) / 255.0
            
            # 应用不透明度
            if opacity < 1.0:
                fg_array[:, :, 3] *= opacity
            
            # 计算合成区域
            x, y = position
            fg_h, fg_w = fg_array.shape[:2]
            bg_h, bg_w = bg_array.shape[:2]
            
            # 计算有效区域
            x_start = max(0, x)
            y_start = max(0, y)
            x_end = min(bg_w, x + fg_w)
            y_end = min(bg_h, y + fg_h)
            
            if x_start >= x_end or y_start >= y_end:
                return background  # 没有重叠区域
            
            # 计算前景图像的有效区域
            fg_x_start = x_start - x
            fg_y_start = y_start - y
            fg_x_end = fg_x_start + (x_end - x_start)
            fg_y_end = fg_y_start + (y_end - y_start)
            
            # 提取重叠区域
            bg_region = bg_array[y_start:y_end, x_start:x_end]
            fg_region = fg_array[fg_y_start:fg_y_end, fg_x_start:fg_x_end]
            
            # Alpha合成
            fg_alpha = fg_region[:, :, 3:4]
            bg_alpha = bg_region[:, :, 3:4]
            
            # 计算输出Alpha
            out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)
            
            # 避免除零
            out_alpha_safe = np.where(out_alpha > 0, out_alpha, 1)
            
            # 计算输出RGB
            out_rgb = (fg_region[:, :, :3] * fg_alpha + 
                      bg_region[:, :, :3] * bg_alpha * (1 - fg_alpha)) / out_alpha_safe
            
            # 组合结果
            result_region = np.concatenate([out_rgb, out_alpha], axis=2)
            
            # 更新背景数组
            result_array = bg_array.copy()
            result_array[y_start:y_end, x_start:x_end] = result_region
            
            # 🔧 修复：使用抖动转换以消除色阶分层
            try:
                from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
                result_8bit = _float_to_uint8_with_dithering(np.clip(result_array, 0.0, 1.0), use_dithering=True)
            except ImportError:
                # 后备方案：使用四舍五入
                result_8bit = np.round(np.clip(result_array, 0.0, 1.0) * 255.0).astype(np.uint8)
            return Image.fromarray(result_8bit, 'RGBA')
            
        except Exception as e:
            safe_print(f"[图像处理] NumPy合成失败，回退到PIL: {e}")
            # 回退到PIL的paste方法
            result = background.copy()
            if opacity < 1.0:
                fg_with_opacity = foreground.copy()
                alpha = fg_with_opacity.split()[-1]
                alpha = alpha.point(lambda p: int(p * opacity))
                fg_with_opacity.putalpha(alpha)
                result.paste(fg_with_opacity, position, fg_with_opacity)
            else:
                result.paste(foreground, position, foreground)
            return result
    
    def _numba_alpha_composite(self, background: Image.Image, 
                              foreground: Image.Image,
                              position: Tuple[int, int],
                              opacity: float) -> Image.Image:
        """使用Numba加速的Alpha合成"""
        try:
            # 转换为numpy数组
            bg_array = np.array(background, dtype=np.float32) / 255.0
            fg_array = np.array(foreground, dtype=np.float32) / 255.0
            
            # 使用Numba加速的合成函数
            result_array = self._numba_composite_core(bg_array, fg_array, position, opacity)
            
            # 🔧 修复：使用抖动转换以消除色阶分层
            try:
                from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
                result_8bit = _float_to_uint8_with_dithering(np.clip(result_array, 0.0, 1.0), use_dithering=True)
            except ImportError:
                # 后备方案：使用四舍五入
                result_8bit = np.round(np.clip(result_array, 0.0, 1.0) * 255.0).astype(np.uint8)
            return Image.fromarray(result_8bit, 'RGBA')
            
        except Exception as e:
            safe_print(f"[图像处理] Numba合成失败，回退到NumPy: {e}")
            return self._numpy_alpha_composite(background, foreground, position, opacity)
    
    def fast_gaussian_blur(self, image: Image.Image, radius: float) -> Image.Image:
        """
        快速高斯模糊
        
        Args:
            image: 输入图像
            radius: 模糊半径
            
        Returns:
            模糊后的图像
        """
        if radius <= 0:
            return image
        
        if self.use_cv2:
            return self._cv2_gaussian_blur(image, radius)
        elif self.use_scipy:
            return self._scipy_gaussian_blur(image, radius)
        else:
            return image.filter(ImageFilter.GaussianBlur(radius=radius))
    
    def _cv2_gaussian_blur(self, image: Image.Image, radius: float) -> Image.Image:
        """使用OpenCV进行高斯模糊"""
        try:
            img_array = np.array(image)
            
            # OpenCV的高斯模糊
            kernel_size = int(radius * 6) | 1  # 确保是奇数
            blurred = cv2.GaussianBlur(img_array, (kernel_size, kernel_size), radius)
            
            return Image.fromarray(blurred, image.mode)
            
        except Exception as e:
            safe_print(f"[图像处理] OpenCV模糊失败，回退到PIL: {e}")
            return image.filter(ImageFilter.GaussianBlur(radius=radius))
    
    def _scipy_gaussian_blur(self, image: Image.Image, radius: float) -> Image.Image:
        """使用SciPy进行高斯模糊"""
        try:
            img_array = np.array(image, dtype=np.float32)
            
            # 对每个通道分别进行模糊
            if len(img_array.shape) == 3:
                for i in range(img_array.shape[2]):
                    img_array[:, :, i] = scipy.ndimage.gaussian_filter(
                        img_array[:, :, i], sigma=radius
                    )
            else:
                img_array = scipy.ndimage.gaussian_filter(img_array, sigma=radius)
            
            # 转换回图像
            img_array = np.clip(img_array, 0, 255).astype(np.uint8)
            return Image.fromarray(img_array, image.mode)
            
        except Exception as e:
            safe_print(f"[图像处理] SciPy模糊失败，回退到PIL: {e}")
            return image.filter(ImageFilter.GaussianBlur(radius=radius))
    
    def batch_process_images(self, images: List[Image.Image], 
                           operations: List[Dict[str, Any]]) -> List[Image.Image]:
        """
        批量处理图像
        
        Args:
            images: 图像列表
            operations: 操作列表，每个操作是一个字典
            
        Returns:
            处理后的图像列表
        """
        results = []
        
        for image in images:
            processed = image
            
            for op in operations:
                op_type = op.get('type')
                
                if op_type == 'resize':
                    processed = self.fast_resize(
                        processed, 
                        op.get('size', processed.size),
                        op.get('quality', 'high')
                    )
                elif op_type == 'rotate':
                    processed = self.fast_rotate(
                        processed,
                        op.get('angle', 0),
                        op.get('expand', True)
                    )
                elif op_type == 'blur':
                    processed = self.fast_gaussian_blur(
                        processed,
                        op.get('radius', 1.0)
                    )
                elif op_type == 'opacity':
                    opacity = op.get('opacity', 1.0)
                    if opacity < 1.0:
                        alpha = processed.split()[-1]
                        alpha = alpha.point(lambda p: int(p * opacity))
                        processed.putalpha(alpha)
            
            results.append(processed)
        
        return results
    
    def get_performance_info(self) -> Dict[str, Any]:
        """获取性能信息"""
        return {
            'cv2_available': self.use_cv2,
            'numba_available': self.use_numba,
            'scipy_available': self.use_scipy,
            'recommended_batch_size': 50 if self.use_cv2 else 20,
            'supports_fast_resize': self.use_cv2,
            'supports_fast_rotate': self.use_cv2,
            'supports_fast_blur': self.use_cv2 or self.use_scipy,
            'supports_fast_composite': self.use_numba
        }


# 如果Numba可用，编译加速函数
if NUMBA_AVAILABLE:
    @jit(nopython=True, parallel=True)
    def _numba_composite_core(bg_array, fg_array, position, opacity):
        """Numba加速的Alpha合成核心函数"""
        x, y = position
        fg_h, fg_w = fg_array.shape[:2]
        bg_h, bg_w = bg_array.shape[:2]
        
        result = bg_array.copy()
        
        for i in prange(fg_h):
            for j in prange(fg_w):
                bg_y = y + i
                bg_x = x + j
                
                if 0 <= bg_y < bg_h and 0 <= bg_x < bg_w:
                    fg_alpha = fg_array[i, j, 3] * opacity
                    bg_alpha = bg_array[bg_y, bg_x, 3]
                    
                    out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)
                    
                    if out_alpha > 0:
                        for c in range(3):  # RGB通道
                            result[bg_y, bg_x, c] = (
                                fg_array[i, j, c] * fg_alpha +
                                bg_array[bg_y, bg_x, c] * bg_alpha * (1 - fg_alpha)
                            ) / out_alpha
                        
                        result[bg_y, bg_x, 3] = out_alpha
        
        return result
    
    # 将函数绑定到类
    OptimizedImageProcessor._numba_composite_core = staticmethod(_numba_composite_core)


# 全局优化图像处理器实例
_global_image_processor = None

def get_optimized_processor() -> OptimizedImageProcessor:
    """获取全局优化图像处理器"""
    global _global_image_processor
    if _global_image_processor is None:
        _global_image_processor = OptimizedImageProcessor()
    return _global_image_processor


def test_optimized_processor():
    """测试优化图像处理器"""
    safe_print("=== 测试优化图像处理器 ===")
    
    try:
        processor = get_optimized_processor()
        
        # 创建测试图像
        test_image = Image.new('RGBA', (200, 200), (255, 0, 0, 128))
        
        # 测试快速缩放
        start_time = time.time()
        resized = processor.fast_resize(test_image, (100, 100), 'fast')
        resize_time = time.time() - start_time
        safe_print(f"✓ 快速缩放测试通过 ({resize_time:.3f}s)")
        
        # 测试快速旋转
        start_time = time.time()
        rotated = processor.fast_rotate(test_image, 45, True)
        rotate_time = time.time() - start_time
        safe_print(f"✓ 快速旋转测试通过 ({rotate_time:.3f}s)")
        
        # 测试快速模糊
        start_time = time.time()
        blurred = processor.fast_gaussian_blur(test_image, 2.0)
        blur_time = time.time() - start_time
        safe_print(f"✓ 快速模糊测试通过 ({blur_time:.3f}s)")
        
        # 测试Alpha合成
        background = Image.new('RGBA', (300, 300), (0, 255, 0, 255))
        start_time = time.time()
        composited = processor.fast_alpha_composite(background, test_image, (50, 50), 0.8)
        composite_time = time.time() - start_time
        safe_print(f"✓ 快速合成测试通过 ({composite_time:.3f}s)")
        
        # 获取性能信息
        perf_info = processor.get_performance_info()
        safe_print(f"性能信息: {perf_info}")
        
        safe_print("✓ 优化图像处理器测试完成")
        return True
        
    except Exception as e:
        safe_print(f"✗ 优化图像处理器测试失败: {e}")
        import traceback
        traceback.print_exc()

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

        return False


if __name__ == "__main__":
    test_optimized_processor()
