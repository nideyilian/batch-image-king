"""
图像质量修复器 - 修复渲染噪点和质量问题
"""

import numpy as np
from PIL import Image, ImageFilter
from typing import Tuple, Optional
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


# 抑制numpy警告
warnings.filterwarnings('ignore', category=RuntimeWarning)


class ImageQualityFixer:
    """图像质量修复器"""
    
    def __init__(self):
        self.debug_mode = False
    
    def composite_with_quality(self, background: Image.Image, foreground: Image.Image,
                              position: Tuple[int, int], opacity: float = 1.0,
                              fix_edges: bool = True, enhance_aa: bool = True) -> Image.Image:
        """
        高质量合成方法
        
        Args:
            background: 背景图像
            foreground: 前景图像
            position: 位置
            opacity: 不透明度
            fix_edges: 是否修复边缘
            enhance_aa: 是否增强抗锯齿
            
        Returns:
            合成后的图像
        """
        try:
            # 确保图像格式
            if background.mode != 'RGBA':
                background = background.convert('RGBA')
            if foreground.mode != 'RGBA':
                foreground = foreground.convert('RGBA')
            
            # 预处理前景图像
            if enhance_aa:
                foreground = self._enhance_antialiasing(foreground)
            
            if fix_edges:
                foreground = self._fix_edges(foreground)
            
            # 执行高质量合成
            result = self._safe_composite(background, foreground, position, opacity)
            
            if self.debug_mode:
                safe_print(f"[质量修复器] 高质量合成完成")
            
            return result
            
        except Exception as e:
            safe_print(f"[质量修复器] 合成失败: {e}")
            # 回退到简单合成
            return self._fallback_composite(background, foreground, position, opacity)
    
    def _enhance_antialiasing(self, image: Image.Image) -> Image.Image:
        """增强抗锯齿效果"""
        try:
            # 轻微的高斯模糊来平滑边缘
            return image.filter(ImageFilter.GaussianBlur(radius=0.3))
        except Exception:
            return image
    
    def _fix_edges(self, image: Image.Image) -> Image.Image:
        """修复边缘问题"""
        try:
            # 使用轻微的边缘平滑
            return image.filter(ImageFilter.SMOOTH_MORE)
        except Exception:
            return image
    
    def _safe_composite(self, background: Image.Image, foreground: Image.Image,
                       position: Tuple[int, int], opacity: float) -> Image.Image:
        """安全的合成方法"""
        try:
            # 使用numpy进行高精度计算
            bg_array = np.array(background, dtype=np.float64) / 255.0
            fg_array = np.array(foreground, dtype=np.float64) / 255.0
            
            # 创建结果数组
            result_array = bg_array.copy()
            
            # 计算合成区域
            x, y = position
            bg_h, bg_w = bg_array.shape[:2]
            fg_h, fg_w = fg_array.shape[:2]
            
            # 计算有效区域
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(bg_w, x + fg_w)
            y2 = min(bg_h, y + fg_h)
            
            if x2 <= x1 or y2 <= y1:
                return background
            
            # 计算前景的对应区域
            fx1 = max(0, -x)
            fy1 = max(0, -y)
            fx2 = fx1 + (x2 - x1)
            fy2 = fy1 + (y2 - y1)
            
            # 提取区域
            bg_region = bg_array[y1:y2, x1:x2]
            fg_region = fg_array[fy1:fy2, fx1:fx2]
            
            # 应用不透明度
            if opacity < 1.0:
                fg_region = fg_region.copy()
                fg_region[:, :, 3] *= opacity
            
            # Alpha混合
            fg_alpha = fg_region[:, :, 3:4]
            bg_alpha = bg_region[:, :, 3:4]
            
            # 计算输出alpha
            out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)
            
            # 避免除零
            safe_alpha = np.maximum(out_alpha, 1e-12)
            
            # 计算输出颜色
            fg_rgb = fg_region[:, :, :3]
            bg_rgb = bg_region[:, :, :3]
            out_rgb = (fg_rgb * fg_alpha + bg_rgb * bg_alpha * (1 - fg_alpha)) / safe_alpha
            
            # 组合结果
            result_region = np.concatenate([out_rgb, out_alpha], axis=2)
            result_array[y1:y2, x1:x2] = result_region
            
            # 🔧 修复：使用抖动转换以消除色阶分层
            result_array = np.clip(result_array, 0.0, 1.0)
            try:
                from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
                result_8bit = _float_to_uint8_with_dithering(result_array, use_dithering=True)
            except ImportError:
                # 后备方案：使用四舍五入
                result_8bit = np.round(result_array * 255.0).astype(np.uint8)
            return Image.fromarray(result_8bit, 'RGBA')
            
        except Exception as e:
            safe_print(f"[质量修复器] 安全合成失败: {e}")
            return self._fallback_composite(background, foreground, position, opacity)
    
    def _fallback_composite(self, background: Image.Image, foreground: Image.Image,
                           position: Tuple[int, int], opacity: float) -> Image.Image:
        """后备合成方法"""
        try:
            result = background.copy()
            
            if opacity < 1.0:
                alpha = foreground.split()[-1]
                alpha = alpha.point(lambda p: int(p * opacity))
                foreground = foreground.copy()
                foreground.putalpha(alpha)
            
            x, y = position
            result.paste(foreground, (x, y), foreground)
            return result
            
        except Exception as e:
            safe_print(f"[质量修复器] 后备合成也失败: {e}")
            return background


# 全局实例
_global_quality_fixer = None

def get_image_quality_fixer() -> ImageQualityFixer:
    """获取全局图像质量修复器实例"""
    global _global_quality_fixer
    if _global_quality_fixer is None:
        _global_quality_fixer = ImageQualityFixer()
    return _global_quality_fixer


def test_quality_fixer():
    """测试质量修复器"""
    safe_print("=== 测试图像质量修复器 ===")
    
    try:
        fixer = get_image_quality_fixer()
        
        # 创建测试图像
        bg = Image.new('RGBA', (200, 200), (255, 255, 255, 255))
        fg = Image.new('RGBA', (100, 100), (255, 0, 0, 128))
        
        # 测试合成
        result = fixer.composite_with_quality(bg, fg, (50, 50), 0.8)
        
        safe_print(f"✓ 质量修复器测试完成，结果尺寸: {result.size}")
        return True
        
    except Exception as e:
        safe_print(f"✗ 质量修复器测试失败: {e}")
        return False


if __name__ == "__main__":
    test_quality_fixer()
