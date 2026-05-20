"""
高级混合模式处理器
提供更精确的图像混合算法，特别针对半透明图像优化
"""

import numpy as np
from PIL import Image

# OpenCV是可选依赖，如果不可用则禁用相关功能
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    # 只在调试模式下显示详细信息
    import os
    if os.getenv('DEBUG_MODE') == '1':
        safe_print("[INFO] OpenCV不可用，高级混合功能将使用基础实现")


class AdvancedBlending:
    """高级混合处理类"""
    
    # 混合模式常量
    MODE_NORMAL = "正常"
    MODE_MULTIPLY = "正片叠底"
    MODE_SCREEN = "滤色"
    MODE_OVERLAY = "叠加"
    MODE_SOFT_LIGHT = "柔光"
    MODE_HARD_LIGHT = "强光"
    MODE_COLOR_DODGE = "颜色减淡"
    MODE_COLOR_BURN = "颜色加深"
    MODE_DARKEN = "变暗"
    MODE_LIGHTEN = "变亮"
    MODE_DIFFERENCE = "差值"
    MODE_EXCLUSION = "排除"
    
    @staticmethod
    def advanced_blend(base, top, mode, opacity=1.0, use_premultiplied=True):
        """
        高级混合算法，支持精确的半透明处理
        
        Args:
            base: 底层图像 (PIL.Image)
            top: 顶层图像 (PIL.Image)
            mode: 混合模式
            opacity: 不透明度 (0.0-1.0)
            use_premultiplied: 是否使用预乘alpha
            
        Returns:
            PIL.Image: 混合后的图像
        """
        # 确保图像格式一致
        base = base.convert('RGBA')
        top = top.convert('RGBA')
        
        # 尺寸检查
        if base.size != top.size:
            top = top.resize(base.size, Image.LANCZOS)
        
        # 应用不透明度
        if opacity < 1.0:
            top = AdvancedBlending._apply_opacity(top, opacity)
        
        # 选择混合算法
        if use_premultiplied:
            return AdvancedBlending._premultiplied_blend(base, top, mode)
        else:
            return AdvancedBlending._standard_blend(base, top, mode)
    
    @staticmethod
    def _premultiplied_blend(base, top, mode):
        """
        使用预乘alpha的混合算法
        这种方法在处理半透明像素时更加精确
        """
        # 转换为浮点数组
        base_array = np.array(base, dtype=np.float32) / 255.0
        top_array = np.array(top, dtype=np.float32) / 255.0
        
        # 分离颜色和alpha通道
        base_rgb = base_array[:,:,:3]
        base_alpha = base_array[:,:,3:4]
        top_rgb = top_array[:,:,:3]
        top_alpha = top_array[:,:,3:4]
        
        # 预乘alpha
        base_premult = base_rgb * base_alpha
        top_premult = top_rgb * top_alpha
        
        # 应用混合模式到预乘颜色
        if mode == AdvancedBlending.MODE_NORMAL:
            blended_premult = top_premult + base_premult * (1 - top_alpha)
        elif mode == AdvancedBlending.MODE_MULTIPLY:
            # 正片叠底：预乘版本
            blended_rgb = AdvancedBlending._safe_divide(base_premult, base_alpha) * AdvancedBlending._safe_divide(top_premult, top_alpha)
            blended_premult = blended_rgb * (base_alpha + top_alpha - base_alpha * top_alpha)
        elif mode == AdvancedBlending.MODE_SCREEN:
            # 滤色：预乘版本
            base_unpremult = AdvancedBlending._safe_divide(base_premult, base_alpha)
            top_unpremult = AdvancedBlending._safe_divide(top_premult, top_alpha)
            blended_rgb = 1 - (1 - base_unpremult) * (1 - top_unpremult)
            blended_premult = blended_rgb * (base_alpha + top_alpha - base_alpha * top_alpha)
        elif mode == AdvancedBlending.MODE_OVERLAY:
            # 叠加：预乘版本
            base_unpremult = AdvancedBlending._safe_divide(base_premult, base_alpha)
            top_unpremult = AdvancedBlending._safe_divide(top_premult, top_alpha)
            
            mask = base_unpremult < 0.5
            blended_rgb = np.where(mask, 
                                 2 * base_unpremult * top_unpremult,
                                 1 - 2 * (1 - base_unpremult) * (1 - top_unpremult))
            blended_premult = blended_rgb * (base_alpha + top_alpha - base_alpha * top_alpha)
        else:
            # 默认使用正常混合
            blended_premult = top_premult + base_premult * (1 - top_alpha)
        
        # 计算结果alpha
        result_alpha = base_alpha + top_alpha * (1 - base_alpha)
        
        # 反预乘得到最终颜色
        result_rgb = AdvancedBlending._safe_divide(blended_premult, result_alpha)
        
        # 组合结果
        result_array = np.concatenate([result_rgb, result_alpha], axis=2)
        
        # 🔧 修复：使用抖动转换以消除色阶分层
        try:
            from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
            result_8bit = _float_to_uint8_with_dithering(np.clip(result_array, 0.0, 1.0), use_dithering=True)
        except ImportError:
            # 后备方案：使用四舍五入
            result_8bit = np.round(np.clip(result_array, 0.0, 1.0) * 255.0).astype(np.uint8)
        
        return Image.fromarray(result_8bit, mode='RGBA')
    
    @staticmethod
    def _standard_blend(base, top, mode):
        """
        标准混合算法（非预乘）
        """
        # 转换为浮点数组
        base_array = np.array(base, dtype=np.float32) / 255.0
        top_array = np.array(top, dtype=np.float32) / 255.0
        
        # 分离通道
        base_rgb = base_array[:,:,:3]
        base_alpha = base_array[:,:,3]
        top_rgb = top_array[:,:,:3]
        top_alpha = top_array[:,:,3]
        
        # 应用混合模式
        if mode == AdvancedBlending.MODE_MULTIPLY:
            blended_rgb = base_rgb * top_rgb
        elif mode == AdvancedBlending.MODE_SCREEN:
            blended_rgb = 1 - (1 - base_rgb) * (1 - top_rgb)
        elif mode == AdvancedBlending.MODE_OVERLAY:
            mask = base_rgb < 0.5
            blended_rgb = np.where(mask, 
                                 2 * base_rgb * top_rgb,
                                 1 - 2 * (1 - base_rgb) * (1 - top_rgb))
        elif mode == AdvancedBlending.MODE_SOFT_LIGHT:
            blended_rgb = AdvancedBlending._soft_light_blend(base_rgb, top_rgb)
        elif mode == AdvancedBlending.MODE_HARD_LIGHT:
            mask = top_rgb < 0.5
            blended_rgb = np.where(mask,
                                 2 * base_rgb * top_rgb,
                                 1 - 2 * (1 - base_rgb) * (1 - top_rgb))
        elif mode == AdvancedBlending.MODE_COLOR_DODGE:
            blended_rgb = AdvancedBlending._color_dodge_blend(base_rgb, top_rgb)
        elif mode == AdvancedBlending.MODE_COLOR_BURN:
            blended_rgb = AdvancedBlending._color_burn_blend(base_rgb, top_rgb)
        elif mode == AdvancedBlending.MODE_DARKEN:
            blended_rgb = np.minimum(base_rgb, top_rgb)
        elif mode == AdvancedBlending.MODE_LIGHTEN:
            blended_rgb = np.maximum(base_rgb, top_rgb)
        elif mode == AdvancedBlending.MODE_DIFFERENCE:
            blended_rgb = np.abs(base_rgb - top_rgb)
        elif mode == AdvancedBlending.MODE_EXCLUSION:
            blended_rgb = base_rgb + top_rgb - 2 * base_rgb * top_rgb
        else:  # MODE_NORMAL
            blended_rgb = top_rgb
        
        # Alpha混合
        result_alpha = top_alpha + base_alpha * (1 - top_alpha)
        
        # 颜色混合（考虑alpha）
        alpha_blend_factor = np.where(result_alpha > 0, top_alpha / result_alpha, 0)
        result_rgb = blended_rgb * alpha_blend_factor + base_rgb * (1 - alpha_blend_factor)
        
        # 组合结果
        result_array = np.zeros_like(base_array)
        result_array[:,:,:3] = result_rgb
        result_array[:,:,3] = result_alpha
        
        # 🔧 修复：使用抖动转换以消除色阶分层
        try:
            from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
            result_8bit = _float_to_uint8_with_dithering(np.clip(result_array, 0.0, 1.0), use_dithering=True)
        except ImportError:
            # 后备方案：使用四舍五入
            result_8bit = np.round(np.clip(result_array, 0.0, 1.0) * 255.0).astype(np.uint8)
        
        return Image.fromarray(result_8bit, mode='RGBA')
    
    @staticmethod
    def _soft_light_blend(base, top):
        """柔光混合算法"""
        mask = top <= 0.5
        result = np.where(mask,
                         base - (1 - 2 * top) * base * (1 - base),
                         base + (2 * top - 1) * (np.sqrt(base) - base))
        return np.clip(result, 0, 1)
    
    @staticmethod
    def _color_dodge_blend(base, top):
        """颜色减淡混合算法"""
        mask = top >= 1.0
        result = np.where(mask, 1.0, np.minimum(1.0, base / (1 - top + 1e-10)))
        return result
    
    @staticmethod
    def _color_burn_blend(base, top):
        """颜色加深混合算法"""
        mask = top <= 0.0
        result = np.where(mask, 0.0, np.maximum(0.0, 1 - (1 - base) / (top + 1e-10)))
        return result
    
    @staticmethod
    def _safe_divide(numerator, denominator):
        """安全除法，避免除零错误"""
        return np.where(denominator > 1e-10, numerator / denominator, 0)
    
    @staticmethod
    def _apply_opacity(image, opacity):
        """应用不透明度"""
        if opacity >= 1.0:
            return image
        
        # 转换为数组
        img_array = np.array(image, dtype=np.float32)
        
        # 调整alpha通道
        img_array[:,:,3] *= opacity
        
        # 转换回图像
        img_array = img_array.clip(0, 255).astype(np.uint8)
        return Image.fromarray(img_array, mode='RGBA')
    
    @staticmethod
    def optimize_transparency_edges(image, blur_radius=0.5):
        """
        优化半透明边缘，减少锯齿效果
        """
        if image.mode != 'RGBA':
            return image

        if not CV2_AVAILABLE:
            # 如果没有OpenCV，使用PIL的简单模糊作为替代
            from PIL import ImageFilter            # 分离alpha通道

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

            r, g, b, a = image.split()
            # 对alpha通道应用轻微模糊
            a_blurred = a.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            # 重新组合
            return Image.merge('RGBA', (r, g, b, a_blurred))

        # 使用OpenCV的高质量实现
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGBA2BGRA)

        # 分离alpha通道
        bgr = cv_image[:,:,:3]
        alpha = cv_image[:,:,3]

        # 对alpha通道应用轻微模糊
        alpha_blurred = cv2.GaussianBlur(alpha, (0, 0), blur_radius)

        # 重新组合
        cv_image[:,:,3] = alpha_blurred

        # 转换回PIL格式
        result = Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGRA2RGBA))

        return result
