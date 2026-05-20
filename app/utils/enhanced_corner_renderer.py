"""
增强圆角渲染器
专门解决UI显示和特定场景下的黑边问题
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from typing import Optional
import math

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        safe_print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            safe_print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            safe_print("[DEBUG] Message encoding failed")



class EnhancedCornerRenderer:
    """增强圆角渲染器 - 解决所有已知的黑边问题"""
    
    def __init__(self):
        safe_print("[增强圆角] 增强圆角渲染器初始化完成")
    
    def apply_enhanced_corner_radius(self, image: Image.Image, radius: int) -> Image.Image:
        """
        应用增强的圆角效果
        
        Args:
            image: 输入图像
            radius: 圆角半径
            
        Returns:
            增强处理的圆角图像
        """
        if image is None or radius <= 0:
            return image
        
        try:
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            width, height = image.size
            safe_print(f"[增强圆角] 处理图像 {width}x{height}, 半径: {radius}")
            
            # 使用增强方法
            result = self._apply_enhanced_method(image, radius)
            
            safe_print(f"[增强圆角] 处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[增强圆角] 处理失败: {e}")
            return image
    
    def _apply_enhanced_method(self, image: Image.Image, radius: int) -> Image.Image:
        """应用增强方法"""
        try:
            width, height = image.size
            
            # 步骤1：创建超高质量蒙版
            mask = self._create_ultra_high_quality_mask(width, height, radius)
            
            # 步骤2：预处理图像以避免黑边
            processed_image = self._preprocess_image_for_corners(image)
            
            # 步骤3：应用蒙版
            result = self._apply_enhanced_mask(processed_image, mask)
            
            # 步骤4：后处理以确保完美边缘
            result = self._postprocess_corners(result, radius)
            
            return result
            
        except Exception as e:
            safe_print(f"[增强圆角] 增强方法失败: {e}")
            return image
    
    def _create_ultra_high_quality_mask(self, width: int, height: int, radius: int) -> Image.Image:
        """创建超高质量蒙版"""
        try:
            # 🔧 批量导出优化：检测是否处于批量模式
            import inspect
            is_batch_mode = False
            for frame_info in inspect.stack():
                if ('batch_export' in frame_info.function or
                    'render_batch' in frame_info.function or
                    'export_batch' in frame_info.function or
                    'generate_combinations' in frame_info.function):
                    is_batch_mode = True
                    break
            
            # 🔧 批量导出优化：降低超采样倍数以提高性能
            if is_batch_mode:
                # 批量模式下使用较低的超采样
                scale = 8  # 批量模式下使用8倍超采样
                safe_print(f"[增强圆角] 🔧 批量模式：创建超高质量蒙版，使用 {scale}倍超采样")
            else:
                # 正常模式下使用高质量超采样
                scale = 32  # 正常模式下使用32倍超采样
                safe_print(f"[增强圆角] 创建超高质量蒙版，使用 {scale}倍超采样")
            
            large_width = width * scale
            large_height = height * scale
            large_radius = radius * scale
            
            # 创建大尺寸蒙版
            large_mask = Image.new('L', (large_width, large_height), 0)
            draw = ImageDraw.Draw(large_mask)
            
            # 绘制圆角矩形
            draw.rounded_rectangle(
                (0, 0, large_width-1, large_height-1),
                radius=large_radius,
                fill=255
            )
            
            if is_batch_mode:
                # 批量模式下简化模糊处理
                large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=1.0))
            else:
                # 正常模式下使用多级高斯模糊
                blur_levels = [6.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5]
                for blur_radius in blur_levels:
                    large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            # 高质量重采样到原始尺寸
            final_mask = large_mask.resize((width, height), Image.LANCZOS)
            
            return final_mask
            
        except Exception as e:
            safe_print(f"[增强圆角] 超高质量蒙版创建失败: {e}")
            # 降级实现
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            return mask
    
    def _preprocess_image_for_corners(self, image: Image.Image) -> Image.Image:
        """预处理图像以避免角落黑边"""
        try:
            # 转换为numpy数组
            img_array = np.array(image, dtype=np.float64)
            
            # 检查是否有暗色像素可能导致黑边
            # 对于边缘区域的暗色像素，稍微提亮以避免黑边效果
            height, width = img_array.shape[:2]
            edge_width = min(50, width // 4, height // 4)
            
            # 定义边缘区域
            edge_regions = [
                (slice(0, edge_width), slice(0, width)),  # 上边
                (slice(height-edge_width, height), slice(0, width)),  # 下边
                (slice(0, height), slice(0, edge_width)),  # 左边
                (slice(0, height), slice(width-edge_width, width))  # 右边
            ]
            
            for region_y, region_x in edge_regions:
                region = img_array[region_y, region_x]
                
                # 对于Alpha不为0的像素，检查亮度
                alpha_mask = region[:, :, 3] > 0
                if np.any(alpha_mask):
                    rgb = region[:, :, :3]
                    brightness = np.mean(rgb, axis=2)
                    
                    # 对于亮度很低的像素，稍微提亮
                    dark_mask = (brightness < 80) & alpha_mask
                    if np.any(dark_mask):
                        # 提亮暗色像素
                        boost_factor = 1.2
                        rgb[dark_mask] = np.clip(rgb[dark_mask] * boost_factor, 0, 255)
                        region[:, :, :3] = rgb
            
            # 转换回PIL图像
            result = Image.fromarray(img_array.astype(np.uint8), mode='RGBA')
            
            return result
            
        except Exception as e:
            safe_print(f"[增强圆角] 图像预处理失败: {e}")
            return image
    
    def _apply_enhanced_mask(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        """应用增强蒙版 - 修复黑边问题"""
        try:
            # 🔧 关键修复：使用最安全的Alpha合成方法避免黑边
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # 分离RGBA通道
            r, g, b, a = image.split()
            
            # 将蒙版应用到Alpha通道
            mask_array = np.array(mask, dtype=np.float32) / 255.0
            alpha_array = np.array(a, dtype=np.float32) / 255.0
            
            # 精确的Alpha混合，避免黑边
            new_alpha_array = alpha_array * mask_array
            
            # 转换回PIL格式
            new_alpha_array = np.clip(new_alpha_array * 255, 0, 255).astype(np.uint8)
            new_alpha = Image.fromarray(new_alpha_array, mode='L')
            
            # 重新组合图像，完全避免黑边
            result = Image.merge('RGBA', (r, g, b, new_alpha))
            
            return result
            
        except Exception as e:
            safe_print(f"[增强圆角] 增强蒙版应用失败: {e}")
            # 降级到最安全的方法
            try:
                r, g, b, a = image.split()
                result = Image.merge('RGBA', (r, g, b, mask))
                return result
            except:
                return image
    
    def _postprocess_corners(self, image: Image.Image, radius: int) -> Image.Image:
        """后处理角落以确保完美边缘"""
        try:
            width, height = image.size
            
            # 转换为numpy数组
            img_array = np.array(image, dtype=np.uint8)
            
            # 对四个角落进行精确处理
            corner_size = radius + 10
            corners = [
                (0, 0, corner_size, corner_size),  # 左上
                (width-corner_size, 0, width, corner_size),  # 右上
                (0, height-corner_size, corner_size, height),  # 左下
                (width-corner_size, height-corner_size, width, height)  # 右下
            ]
            
            for x1, y1, x2, y2 in corners:
                # 确保不超出边界
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(width, x2)
                y2 = min(height, y2)
                
                if x2 <= x1 or y2 <= y1:
                    continue
                
                # 获取角落区域
                corner_region = img_array[y1:y2, x1:x2]
                
                # 清理可能的黑边像素
                self._clean_corner_region(corner_region)
                
                # 更新图像
                img_array[y1:y2, x1:x2] = corner_region
            
            # 转换回PIL图像
            result = Image.fromarray(img_array, mode='RGBA')
            
            return result
            
        except Exception as e:
            safe_print(f"[增强圆角] 角落后处理失败: {e}")
            return image
    
    def _clean_corner_region(self, region: np.ndarray):
        """清理角落区域的黑边像素"""
        try:
            # 对于Alpha值很低但不为0的像素，直接设为透明
            low_alpha_mask = (region[:, :, 3] > 0) & (region[:, :, 3] < 50)
            region[low_alpha_mask, 3] = 0
            
            # 对于半透明的暗色像素，检查是否应该设为透明
            semi_transparent_mask = (region[:, :, 3] > 50) & (region[:, :, 3] < 200)
            if np.any(semi_transparent_mask):
                rgb = region[semi_transparent_mask, :3]
                brightness = np.mean(rgb, axis=1)
                
                # 如果半透明像素很暗，可能是黑边，设为透明
                dark_semi_mask = brightness < 60
                if np.any(dark_semi_mask):
                    # 找到对应的位置
                    indices = np.where(semi_transparent_mask)
                    dark_indices = (indices[0][dark_semi_mask], indices[1][dark_semi_mask])
                    region[dark_indices, 3] = 0
            
        except Exception as e:
            safe_print(f"[增强圆角] 角落区域清理失败: {e}")


class UltimateCornerRenderer:
    """终极圆角渲染器 - 最后的解决方案"""
    
    def __init__(self):
        safe_print("[终极圆角] 终极圆角渲染器初始化完成")
    
    def apply_ultimate_corner_radius(self, image: Image.Image, radius: int) -> Image.Image:
        """
        应用终极圆角效果
        
        Args:
            image: 输入图像
            radius: 圆角半径
            
        Returns:
            终极处理的圆角图像
        """
        if image is None or radius <= 0:
            return image
        
        try:
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            width, height = image.size
            safe_print(f"[终极圆角] 处理图像 {width}x{height}, 半径: {radius}")
            
            # 使用终极方法：完全重新绘制
            result = self._redraw_with_perfect_corners(image, radius)
            
            safe_print(f"[终极圆角] 处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[终极圆角] 处理失败: {e}")
            return image
    
    def _redraw_with_perfect_corners(self, image: Image.Image, radius: int) -> Image.Image:
        """完全重新绘制以获得完美圆角"""
        try:
            width, height = image.size
            
            # 创建新的透明画布
            result = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(result)
            
            # 获取图像的主要颜色
            img_array = np.array(image)
            
            # 绘制圆角矩形，使用图像的平均颜色
            avg_color = self._get_average_color(img_array)
            
            # 绘制基础圆角矩形
            draw.rounded_rectangle(
                (0, 0, width-1, height-1),
                radius=radius,
                fill=avg_color
            )
            
            # 然后将原图像的内容复制到非角落区域
            self._copy_non_corner_content(result, image, radius)
            
            return result
            
        except Exception as e:
            safe_print(f"[终极圆角] 重新绘制失败: {e}")
            return image
    
    def _get_average_color(self, img_array: np.ndarray) -> tuple:
        """获取图像的平均颜色"""
        try:
            # 只考虑不透明的像素
            opaque_mask = img_array[:, :, 3] > 200
            
            if np.any(opaque_mask):
                opaque_pixels = img_array[opaque_mask]
                avg_r = int(np.mean(opaque_pixels[:, 0]))
                avg_g = int(np.mean(opaque_pixels[:, 1]))
                avg_b = int(np.mean(opaque_pixels[:, 2]))
                return (avg_r, avg_g, avg_b, 255)
            else:
                return (128, 128, 128, 255)
                
        except Exception as e:
            safe_print(f"[终极圆角] 平均颜色计算失败: {e}")
            return (128, 128, 128, 255)
    
    def _copy_non_corner_content(self, target: Image.Image, source: Image.Image, radius: int):
        """复制非角落区域的内容"""
        try:
            width, height = source.size
            
            # 定义安全区域（远离角落的区域）
            safe_margin = radius + 5
            
            if width > safe_margin * 2 and height > safe_margin * 2:
                # 提取中心区域
                center_region = source.crop((safe_margin, safe_margin, 
                                           width - safe_margin, height - safe_margin))
                
                # 粘贴到目标图像
                target.paste(center_region, (safe_margin, safe_margin), center_region)
            
        except Exception as e:
            safe_print(f"[终极圆角] 内容复制失败: {e}")


# 全局实例
_enhanced_corner_renderer = None
_ultimate_corner_renderer = None

def get_enhanced_corner_renderer() -> EnhancedCornerRenderer:
    """获取增强圆角渲染器"""
    global _enhanced_corner_renderer
    if _enhanced_corner_renderer is None:
        _enhanced_corner_renderer = EnhancedCornerRenderer()
    return _enhanced_corner_renderer

def get_ultimate_corner_renderer() -> UltimateCornerRenderer:
    """获取终极圆角渲染器"""
    global _ultimate_corner_renderer
    if _ultimate_corner_renderer is None:
        _ultimate_corner_renderer = UltimateCornerRenderer()
    return _ultimate_corner_renderer
