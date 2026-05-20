"""
现代样式渲染器 - 高质量圆角和描边实现
基于现代图像处理技术，提供更好的圆角和描边效果
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from typing import Optional, Tuple
import cv2
import math
from app.utils.print_utils import safe_print
from app.utils.render_diagnostics import log_branch, log_sampling


class ModernStyleRenderer:
    """现代样式渲染器 - 提供高质量的圆角和描边效果"""
    
    def __init__(self):
        """初始化现代样式渲染器"""
        safe_print("[现代样式] 现代样式渲染器初始化完成")
        self.enable_gpu_acceleration = self._check_gpu_support()
    
    def _check_gpu_support(self) -> bool:
        """检查GPU加速支持"""
        try:
            # 检查OpenCV是否支持GPU
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                safe_print("[现代样式] GPU加速可用")
                return True
            else:
                safe_print("[现代样式] GPU加速不可用，使用CPU处理")
                return False
        except:
            safe_print("[现代样式] GPU检查失败，使用CPU处理")
            return False
    
    def apply_modern_corner_radius(self, image: Image.Image, radius: int, 
                                 quality: str = "high") -> Image.Image:
        """
        应用现代高质量圆角效果
        
        Args:
            image: 输入图像
            radius: 圆角半径
            quality: 质量等级 ("fast", "medium", "high", "ultra")
            
        Returns:
            处理后的圆角图像
        """
        if image is None or radius <= 0:
            return image
        
        try:
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            width, height = image.size
            safe_print(f"[现代圆角] 处理图像 {width}x{height}, 半径: {radius}, 质量: {quality}")
            log_branch(
                "modern_style.apply_modern_corner_radius",
                "enter",
                width=width,
                height=height,
                radius=radius,
                quality=quality,
            )
            
            # 根据质量等级选择处理方法
            if quality == "ultra":
                log_branch("modern_style.apply_modern_corner_radius", "ultra")
                return self._apply_ultra_quality_corners(image, radius)
            elif quality == "high":
                log_branch("modern_style.apply_modern_corner_radius", "high")
                return self._apply_high_quality_corners(image, radius)
            elif quality == "medium":
                log_branch("modern_style.apply_modern_corner_radius", "medium")
                return self._apply_medium_quality_corners(image, radius)
            else:  # fast
                log_branch("modern_style.apply_modern_corner_radius", "fast")
                return self._apply_fast_corners(image, radius)
            
        except Exception as e:
            safe_print(f"[现代圆角] 处理失败: {e}")
            return image
    
    def _apply_ultra_quality_corners(self, image: Image.Image, radius: int) -> Image.Image:
        """超高质量圆角处理 - 基于距离场技术"""
        try:
            width, height = image.size
            
            # 转换为numpy数组
            img_array = np.array(image, dtype=np.float32) / 255.0
            
            # 创建距离场
            distance_field = self._create_distance_field(width, height, radius)
            
            # 使用距离场生成平滑的alpha蒙版
            smooth_mask = self._distance_field_to_mask(distance_field, radius)
            
            # 应用蒙版
            result_array = img_array.copy()
            result_array[:, :, 3] *= smooth_mask
            
            # 抗锯齿处理
            result_array = self._apply_advanced_antialiasing(result_array)
            
            # 转换回PIL图像
            result = Image.fromarray((result_array * 255).astype(np.uint8), 'RGBA')
            
            safe_print(f"[现代圆角] 超高质量处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[现代圆角] 超高质量处理失败: {e}")
            return self._apply_high_quality_corners(image, radius)
    
    def _apply_high_quality_corners(self, image: Image.Image, radius: int) -> Image.Image:
        """高质量圆角处理 - 修复黑边问题"""
        try:
            width, height = image.size
            
            # 🔧 修复：防止黑边的高质量圆角处理
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # 创建高质量蒙版
            mask = self._create_bezier_corner_mask(width, height, radius)
            
            # 🔧 关键修复：使用正确的Alpha合成避免黑边
            # 分离RGBA通道
            r, g, b, a = image.split()
            
            # 将蒙版应用到Alpha通道
            mask_array = np.array(mask, dtype=np.float32) / 255.0
            alpha_array = np.array(a, dtype=np.float32) / 255.0
            
            # 精确的Alpha混合
            new_alpha_array = alpha_array * mask_array
            
            # 转换回PIL格式
            new_alpha_array = np.clip(new_alpha_array * 255, 0, 255).astype(np.uint8)
            new_alpha = Image.fromarray(new_alpha_array, mode='L')
            
            # 重新组合图像，避免黑边
            result = Image.merge('RGBA', (r, g, b, new_alpha))
            
            # 边缘优化（可选，但要小心不引入黑边）
            try:
                result = self._optimize_edges(result, radius)
            except Exception as opt_e:
                safe_print(f"[现代圆角] 边缘优化跳过: {opt_e}")
            
            safe_print(f"[现代圆角] 高质量处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[现代圆角] 高质量处理失败: {e}")
            return self._apply_medium_quality_corners(image, radius)
    
    def _apply_medium_quality_corners(self, image: Image.Image, radius: int) -> Image.Image:
        """中等质量圆角处理 - 修复黑边问题"""
        try:
            width, height = image.size
            
            # 🔧 修复：防止黑边的中等质量圆角处理
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # 使用4x超采样
            scale = 4
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
            
            # 应用适度的高斯模糊
            large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=1.5))
            
            # 缩放回原始尺寸
            mask = large_mask.resize((width, height), Image.LANCZOS)
            
            # 🔧 关键修复：使用正确的Alpha合成避免黑边
            # 分离RGBA通道
            r, g, b, a = image.split()
            
            # 将蒙版应用到Alpha通道
            mask_array = np.array(mask, dtype=np.float32) / 255.0
            alpha_array = np.array(a, dtype=np.float32) / 255.0
            
            # 精确的Alpha混合
            new_alpha_array = alpha_array * mask_array
            
            # 转换回PIL格式
            new_alpha_array = np.clip(new_alpha_array * 255, 0, 255).astype(np.uint8)
            new_alpha = Image.fromarray(new_alpha_array, mode='L')
            
            # 重新组合图像，避免黑边
            result = Image.merge('RGBA', (r, g, b, new_alpha))
            
            safe_print(f"[现代圆角] 中等质量处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[现代圆角] 中等质量处理失败: {e}")
            return self._apply_fast_corners(image, radius)
    
    def _apply_fast_corners(self, image: Image.Image, radius: int) -> Image.Image:
        """快速圆角处理 - 修复黑边问题"""
        try:
            width, height = image.size
            
            # 🔧 修复：防止黑边的圆角处理
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # 创建基础蒙版，使用适度的超采样
            scale = 2  # 使用2倍超采样，平衡质量和性能
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
            
            # 轻微的高斯模糊以减少锯齿
            large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=0.8))
            
            # 高质量缩放回原始尺寸
            mask = large_mask.resize((width, height), Image.LANCZOS)
            
            # 🔧 关键修复：使用正确的Alpha合成避免黑边
            # 分离RGBA通道
            r, g, b, a = image.split()
            
            # 将蒙版应用到Alpha通道
            mask_array = np.array(mask, dtype=np.float32) / 255.0
            alpha_array = np.array(a, dtype=np.float32) / 255.0
            
            # 精确的Alpha混合
            new_alpha_array = alpha_array * mask_array
            
            # 转换回PIL格式
            new_alpha_array = np.clip(new_alpha_array * 255, 0, 255).astype(np.uint8)
            new_alpha = Image.fromarray(new_alpha_array, mode='L')
            
            # 重新组合图像，避免黑边
            result = Image.merge('RGBA', (r, g, b, new_alpha))
            
            safe_print(f"[现代圆角] 快速处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[现代圆角] 快速处理失败: {e}")
            return image
    
    def apply_modern_stroke(self, image: Image.Image, width: int, color: Tuple[int, int, int, int],
                           stroke_type: str = "outer", quality: str = "high", corner_radius: int = 0) -> Image.Image:
        """
        应用现代高质量描边效果
        
        Args:
            image: 输入图像
            width: 描边宽度
            color: 描边颜色 (R, G, B, A)
            stroke_type: 描边类型 ("inner", "center", "outer")
            quality: 质量等级 ("fast", "medium", "high", "ultra")
            
        Returns:
            处理后的描边图像
        """
        if image is None or width <= 0:
            return image
        
        try:
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            safe_print(f"[现代描边] 处理图像，宽度: {width}, 颜色: {color}, 类型: {stroke_type}, 质量: {quality}")
            log_branch(
                "modern_style.apply_modern_stroke",
                "enter",
                stroke_type=stroke_type,
                width=width,
                corner_radius=corner_radius,
                quality=quality,
            )
            
            # 根据描边类型选择处理方法
            if stroke_type == "inner":
                log_branch("modern_style.apply_modern_stroke", "inner")
                return self._apply_modern_inner_stroke(image, width, color, quality, corner_radius)
            elif stroke_type == "center":
                log_branch("modern_style.apply_modern_stroke", "center")
                return self._apply_modern_center_stroke(image, width, color, quality, corner_radius)
            else:  # outer
                log_branch("modern_style.apply_modern_stroke", "outer")
                return self._apply_modern_outer_stroke(image, width, color, quality, corner_radius)
            
        except Exception as e:
            safe_print(f"[现代描边] 处理失败: {e}")
            return image

    def _get_mask_supersample_scale(self, width: int, height: int, edge_size: int = 0) -> int:
        """根据尺寸和边缘复杂度选择超采样倍数。"""
        min_side = max(1, min(int(width), int(height)))
        edge_size = max(0, int(edge_size))

        # 现代渲染器优先边缘质量，避免低倍采样出现明显台阶
        if min_side <= 256:
            scale = 8
        elif min_side <= 1024:
            scale = 7
        elif min_side <= 2048:
            scale = 6
        else:
            scale = 5

        if edge_size <= 4:
            scale = max(scale, 8 if min_side <= 1024 else 6)
        elif edge_size <= 10:
            scale = max(scale, 7 if min_side <= 1024 else 6)
        log_sampling("modern_style.mask_scale", width, height, edge_size, scale)
        return scale

    def _create_antialiased_rounded_rect_mask(self, width: int, height: int, radius: int) -> Image.Image:
        """使用超采样生成高质量圆角矩形蒙版。"""
        width = max(1, int(width))
        height = max(1, int(height))
        radius = max(0, min(int(radius), min(width, height) // 2))

        if radius <= 0:
            return Image.new('L', (width, height), 255)

        scale = self._get_mask_supersample_scale(width, height, radius)
        large_w, large_h = width * scale, height * scale
        large_mask = Image.new('L', (large_w, large_h), 0)
        draw = ImageDraw.Draw(large_mask)
        draw.rounded_rectangle((0, 0, large_w - 1, large_h - 1), radius=radius * scale, fill=255)
        return large_mask.resize((width, height), Image.Resampling.LANCZOS)

    def _create_antialiased_rounded_ring_mask(
        self,
        width: int,
        height: int,
        outer_radius: int,
        inset: int,
        inner_radius: int
    ) -> Image.Image:
        """使用超采样生成高质量圆角环带蒙版。"""
        width = max(1, int(width))
        height = max(1, int(height))
        inset = max(0, int(inset))
        outer_radius = max(0, min(int(outer_radius), min(width, height) // 2))
        inner_radius = max(0, min(int(inner_radius), min(width, height) // 2))

        scale = self._get_mask_supersample_scale(width, height, max(outer_radius, inset))
        large_w, large_h = width * scale, height * scale
        large_mask = Image.new('L', (large_w, large_h), 0)
        draw = ImageDraw.Draw(large_mask)
        draw.rounded_rectangle((0, 0, large_w - 1, large_h - 1), radius=outer_radius * scale, fill=255)

        if inset > 0 and inset * 2 < width and inset * 2 < height:
            inset_large = inset * scale
            draw.rounded_rectangle(
                (inset_large, inset_large, large_w - inset_large - 1, large_h - inset_large - 1),
                radius=inner_radius * scale,
                fill=0
            )

        return large_mask.resize((width, height), Image.Resampling.LANCZOS)

    def _apply_alpha_mask(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        """将蒙版与图像Alpha相乘，保持边缘平滑。"""
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        r, g, b, a = image.split()
        a_arr = np.array(a, dtype=np.float32) / 255.0
        m_arr = np.array(mask, dtype=np.float32) / 255.0
        out_a = np.clip(a_arr * m_arr * 255.0, 0, 255).astype(np.uint8)
        return Image.merge('RGBA', (r, g, b, Image.fromarray(out_a, mode='L')))
    
    def _apply_modern_inner_stroke(self, image: Image.Image, width: int, 
                                 color: Tuple[int, int, int, int], quality: str, corner_radius: int) -> Image.Image:
        """现代内描边实现（高质量超采样版）"""
        try:
            img_width, img_height = image.size

            stroke_width = max(1, min(int(width), min(img_width, img_height) // 4))
            outer_radius = max(0, int(corner_radius))
            inner_radius = max(0, outer_radius - stroke_width)

            stroke_mask = self._create_antialiased_rounded_ring_mask(
                img_width, img_height, outer_radius, stroke_width, inner_radius
            )
            stroke_layer = Image.new('RGBA', (img_width, img_height), color)
            stroke_layer.putalpha(stroke_mask)
            result = Image.alpha_composite(Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0)), stroke_layer)

            if stroke_width * 2 < img_width and stroke_width * 2 < img_height:
                content_width = img_width - stroke_width * 2
                content_height = img_height - stroke_width * 2
                scaled_content = image.resize((content_width, content_height), Image.Resampling.LANCZOS)
                content_layer = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
                content_layer.paste(scaled_content, (stroke_width, stroke_width), scaled_content)
                content_mask = self._create_antialiased_rounded_rect_mask(content_width, content_height, inner_radius)
                alpha_canvas = Image.new('L', (img_width, img_height), 0)
                alpha_canvas.paste(content_mask, (stroke_width, stroke_width))
                content_layer = self._apply_alpha_mask(content_layer, alpha_canvas)
                result = Image.alpha_composite(result, content_layer)

            safe_print(f"[现代描边] 内描边处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[现代描边] 内描边处理失败: {e}")
            return image
    
    def _apply_modern_center_stroke(self, image: Image.Image, width: int, 
                                  color: Tuple[int, int, int, int], quality: str, corner_radius: int) -> Image.Image:
        """现代居中描边实现（高质量超采样版）"""
        try:
            img_width, img_height = image.size

            inner_margin = max(1, int(width / 2))
            outer_radius = max(0, int(corner_radius)) + inner_margin
            inner_radius = max(0, int(corner_radius) - inner_margin)

            stroke_mask = self._create_antialiased_rounded_ring_mask(
                img_width, img_height, outer_radius, inner_margin, inner_radius
            )
            stroke_layer = Image.new('RGBA', (img_width, img_height), color)
            stroke_layer.putalpha(stroke_mask)
            result = Image.alpha_composite(Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0)), stroke_layer)

            if inner_margin * 2 < img_width and inner_margin * 2 < img_height:
                content_width = img_width - inner_margin * 2
                content_height = img_height - inner_margin * 2
                scaled_content = image.resize((content_width, content_height), Image.Resampling.LANCZOS)
                content_layer = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
                content_layer.paste(scaled_content, (inner_margin, inner_margin), scaled_content)
                content_mask = self._create_antialiased_rounded_rect_mask(content_width, content_height, inner_radius)
                alpha_canvas = Image.new('L', (img_width, img_height), 0)
                alpha_canvas.paste(content_mask, (inner_margin, inner_margin))
                content_layer = self._apply_alpha_mask(content_layer, alpha_canvas)
                result = Image.alpha_composite(result, content_layer)

            safe_print(f"[现代描边] 居中描边处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[现代描边] 居中描边处理失败: {e}")
            return image
    
    def _apply_modern_outer_stroke(self, image: Image.Image, width: int, 
                                 color: Tuple[int, int, int, int], quality: str, corner_radius: int) -> Image.Image:
        """现代外描边实现（保持尺寸，内容内缩）。"""
        try:
            img_width, img_height = image.size

            stroke_width = max(1, min(int(width), min(img_width, img_height) // 4))
            outer_radius = max(0, int(corner_radius))
            inner_radius = max(0, outer_radius - stroke_width)

            stroke_mask = self._create_antialiased_rounded_ring_mask(
                img_width, img_height, outer_radius, stroke_width, inner_radius
            )
            stroke_layer = Image.new('RGBA', (img_width, img_height), color)
            stroke_layer.putalpha(stroke_mask)
            result = Image.alpha_composite(Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0)), stroke_layer)

            if stroke_width * 2 < img_width and stroke_width * 2 < img_height:
                inner_width = img_width - stroke_width * 2
                inner_height = img_height - stroke_width * 2
                scaled_image = image.resize((inner_width, inner_height), Image.Resampling.LANCZOS)
                content_layer = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (stroke_width, stroke_width), scaled_image)
                content_mask = self._create_antialiased_rounded_rect_mask(inner_width, inner_height, inner_radius)
                alpha_canvas = Image.new('L', (img_width, img_height), 0)
                alpha_canvas.paste(content_mask, (stroke_width, stroke_width))
                content_layer = self._apply_alpha_mask(content_layer, alpha_canvas)
                result = Image.alpha_composite(result, content_layer)
            else:
                result = Image.alpha_composite(result, image.convert('RGBA'))

            safe_print(f"[现代描边] 外描边处理完成")
            return result
            
        except Exception as e:
            safe_print(f"[现代描边] 外描边处理失败: {e}")
            return image
    
    # === 辅助方法 ===
    
    def _create_distance_field(self, width: int, height: int, radius: int) -> np.ndarray:
        """创建距离场用于超高质量圆角"""
        try:
            # 创建坐标网格
            y, x = np.ogrid[:height, :width]
            
            # 计算到各个角落的距离
            corners = [
                (radius, radius),                    # 左上
                (width - radius, radius),            # 右上
                (radius, height - radius),           # 左下
                (width - radius, height - radius)    # 右下
            ]
            
            # 初始化距离场
            distance_field = np.full((height, width), radius + 1, dtype=np.float32)
            
            # 计算每个像素到最近圆角中心的距离
            for corner_x, corner_y in corners:
                dist = np.sqrt((x - corner_x)**2 + (y - corner_y)**2)
                
                # 只在相应的象限更新距离
                if corner_x < width // 2 and corner_y < height // 2:  # 左上
                    mask = (x <= corner_x) & (y <= corner_y)
                elif corner_x >= width // 2 and corner_y < height // 2:  # 右上
                    mask = (x >= corner_x) & (y <= corner_y)
                elif corner_x < width // 2 and corner_y >= height // 2:  # 左下
                    mask = (x <= corner_x) & (y >= corner_y)
                else:  # 右下
                    mask = (x >= corner_x) & (y >= corner_y)
                
                distance_field[mask] = np.minimum(distance_field[mask], dist[mask])
            
            return distance_field
            
        except Exception as e:
            safe_print(f"[现代圆角] 距离场创建失败: {e}")
            return np.ones((height, width), dtype=np.float32) * radius
    
    def _distance_field_to_mask(self, distance_field: np.ndarray, radius: int) -> np.ndarray:
        """将距离场转换为平滑蒙版"""
        try:
            # 使用平滑步函数创建抗锯齿边缘
            edge_width = 1.0  # 边缘平滑宽度
            
            # 平滑步函数
            t = np.clip((radius - distance_field) / edge_width, 0.0, 1.0)
            smooth_mask = t * t * (3.0 - 2.0 * t)  # 平滑步函数
            
            return smooth_mask.astype(np.float32)
            
        except Exception as e:
            safe_print(f"[现代圆角] 距离场转换失败: {e}")
            return np.ones_like(distance_field, dtype=np.float32)
    
    def _create_bezier_corner_mask(self, width: int, height: int, radius: int) -> Image.Image:
        """创建基于贝塞尔曲线的高质量圆角蒙版"""
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
            
            # 🐛 修复极小半径问题：使用更高的超采样和不同的阈值
            if radius <= 4:  # 扩大阈值范围
                # 🔧 批量导出优化：降低超采样倍数以提高性能
                if is_batch_mode:
                    # 批量模式下使用较低的超采样
                    scale = 8 if radius <= 2 else 4  # 1-2px用8倍，3-4px用4倍
                    safe_print(f"[现代圆角] 🔧 批量模式：小半径 {radius}px，使用 {scale}倍超采样")
                else:
                    # 正常模式下使用高质量超采样
                    scale = 32 if radius <= 2 else 16  # 1-2px用32倍，3-4px用16倍
                    safe_print(f"[现代圆角] 小半径 {radius}px，使用 {scale}倍超采样")
                
                large_width = width * scale
                large_height = height * scale
                large_radius = max(radius * scale, 2)  # 确保最小半径为2
                
                large_mask = Image.new('L', (large_width, large_height), 0)
                draw = ImageDraw.Draw(large_mask)
                
                if is_batch_mode:
                    # 批量模式下简化处理
                    draw.rounded_rectangle(
                        (0, 0, large_width-1, large_height-1),
                        radius=large_radius,
                        fill=255
                    )
                    # 轻微模糊
                    large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=0.5))
                else:
                    # 正常模式下使用高质量处理
                    # 使用多次绘制提高边缘质量
                    for offset in [0, 0.25, 0.5, 0.75]:
                        draw.rounded_rectangle(
                            (offset, offset, large_width-1-offset, large_height-1-offset),
                            radius=large_radius,
                            fill=64  # 使用部分透明度叠加
                        )
                    
                    # 应用强度高斯模糊提升边缘质量
                    large_mask = large_mask.filter(ImageFilter.GaussianBlur(radius=1.0))
                
                # 高质量缩放回原始尺寸
                mask = large_mask.resize((width, height), Image.LANCZOS)
                
                if not is_batch_mode:
                    # 再次轻微模糊（仅正常模式）
                    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.2))
                
                return mask
            else:
                # 🔧 批量导出优化：大半径也降低超采样
                if is_batch_mode:
                    scale = 4  # 批量模式下使用4倍超采样
                    safe_print(f"[现代圆角] 🔧 批量模式：大半径 {radius}px，使用 {scale}倍超采样")
                else:
                    scale = 8  # 正常模式下使用8倍超采样
                    safe_print(f"[现代圆角] 大半径 {radius}px，使用 {scale}倍超采样")
                
                large_width = width * scale
                large_height = height * scale
                large_radius = radius * scale
                
                large_mask = Image.new('L', (large_width, large_height), 0)
                draw = ImageDraw.Draw(large_mask)
                
                # 直接使用PIL的rounded_rectangle
                draw.rounded_rectangle(
                    (0, 0, large_width-1, large_height-1),
                    radius=large_radius,
                    fill=255
                )
                
                mask = large_mask.resize((width, height), Image.LANCZOS)
                return mask
            
        except Exception as e:
            safe_print(f"[现代圆角] 贝塞尔蒙版创建失败: {e}")
            # 降级到标准实现
            mask = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
            return mask
    
    def _draw_improved_rounded_rect(self, draw: ImageDraw.ImageDraw, width: int, height: int, radius: int):
        """绘制改进的圆角矩形"""
        try:
            # 🐛 修复：直接使用PIL的高质量rounded_rectangle
            # PIL的rounded_rectangle在高分辨率下效果很好
            draw.rounded_rectangle(
                (0, 0, width-1, height-1),
                radius=radius,
                fill=255
            )
            
        except Exception as e:
            safe_print(f"[现代圆角] 改进圆角绘制失败: {e}")
            # 最基础的矩形
            draw.rectangle((0, 0, width-1, height-1), fill=255)
    
    def _apply_advanced_antialiasing(self, img_array: np.ndarray) -> np.ndarray:
        """应用高级抗锯齿处理"""
        try:
            # 使用双边滤波进行边缘平滑
            if self.enable_gpu_acceleration:
                return self._gpu_antialiasing(img_array)
            else:
                return self._cpu_antialiasing(img_array)
                
        except Exception as e:
            safe_print(f"[现代圆角] 高级抗锯齿失败: {e}")
            return img_array
    
    def _gpu_antialiasing(self, img_array: np.ndarray) -> np.ndarray:
        """GPU加速的抗锯齿处理"""
        try:
            # 转换为OpenCV格式
            cv_img = (img_array * 255).astype(np.uint8)
            
            # GPU双边滤波
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(cv_img)
            
            # 应用双边滤波
            gpu_filtered = cv2.cuda.bilateralFilter(gpu_img, -1, 50, 50)
            
            # 下载结果
            filtered_img = gpu_filtered.download()
            
            return filtered_img.astype(np.float32) / 255.0
            
        except Exception as e:
            safe_print(f"[现代圆角] GPU抗锯齿失败: {e}")
            return self._cpu_antialiasing(img_array)
    
    def _cpu_antialiasing(self, img_array: np.ndarray) -> np.ndarray:
        """CPU抗锯齿处理"""
        try:
            # 转换为OpenCV格式
            cv_img = (img_array * 255).astype(np.uint8)
            
            # 应用双边滤波
            filtered_img = cv2.bilateralFilter(cv_img, 9, 75, 75)
            
            return filtered_img.astype(np.float32) / 255.0
            
        except Exception as e:
            safe_print(f"[现代圆角] CPU抗锯齿失败: {e}")
            return img_array
    
    def _optimize_edges(self, image: Image.Image, radius: int) -> Image.Image:
        """优化边缘质量"""
        try:
            # 转换为numpy数组
            img_array = np.array(image, dtype=np.float32) / 255.0
            
            # 检测边缘
            alpha = img_array[:, :, 3]
            
            # 使用形态学操作优化边缘
            try:
                kernel = np.ones((3, 3), np.uint8)
                optimized_alpha = cv2.morphologyEx(
                    (alpha * 255).astype(np.uint8), 
                    cv2.MORPH_CLOSE, 
                    kernel
                ).astype(np.float32) / 255.0
            except (AttributeError, ImportError):
                # OpenCV函数不可用，使用PIL替代方案
                from PIL import ImageFilter
                alpha_pil = Image.fromarray((alpha * 255).astype(np.uint8), 'L')
                alpha_pil = alpha_pil.filter(ImageFilter.SMOOTH)
                optimized_alpha = np.array(alpha_pil, dtype=np.float32) / 255.0
            
            # 应用优化的alpha通道
            img_array[:, :, 3] = optimized_alpha
            
            # 转换回PIL图像
            result = Image.fromarray((img_array * 255).astype(np.uint8), 'RGBA')
            
            return result
            
        except Exception as e:
            safe_print(f"[现代圆角] 边缘优化失败: {e}")
            return image
    
    def _create_inner_distance_mask(self, img_array: np.ndarray, width: int, quality: str) -> np.ndarray:
        """创建内描边距离蒙版 - 已移除，不再使用"""
        # 🔧 注意：此方法已被新的内描边实现替代，保留以防兼容性问题
        try:
            alpha = img_array[:, :, 3]
            return np.zeros_like(alpha, dtype=np.float32)
        except Exception as e:
            safe_print(f"[现代描边] 内距离蒙版创建失败: {e}")
            return np.zeros_like(img_array[:, :, 3], dtype=np.float32)
    
    def _create_dilated_mask(self, image: Image.Image, width: int, quality: str) -> Image.Image:
        """创建膨胀蒙版用于外描边"""
        try:
            # 获取alpha通道
            alpha = image.getchannel('A')
            img_width, img_height = image.size
            
            # 🐛 修复：创建更准确的描边蒙版
            # 创建扩展画布来容纳描边
            expanded_width = img_width + width * 2
            expanded_height = img_height + width * 2
            
            # 创建扩展的alpha蒙版
            expanded_alpha = Image.new('L', (expanded_width, expanded_height), 0)
            expanded_alpha.paste(alpha, (width, width))
            
            # 创建描边蒙版（整个扩展区域）
            stroke_mask = Image.new('L', (expanded_width, expanded_height), 255)
            
            # 挖空内容区域
            inner_mask = Image.new('L', (expanded_width, expanded_height), 0)
            inner_mask.paste(alpha, (width, width))
            
            # 描边 = 扩展区域 - 内容区域
            stroke_array = np.array(stroke_mask) - np.array(inner_mask)
            stroke_array = np.clip(stroke_array, 0, 255)
            
            # 裁剪回原始尺寸（保持描边在原始边界内）
            final_stroke = Image.fromarray(stroke_array.astype(np.uint8), 'L')
            final_stroke = final_stroke.crop((width, width, width + img_width, width + img_height))
            
            # 如果不是快速模式，应用平滑
            if quality != "fast":
                final_stroke = final_stroke.filter(ImageFilter.GaussianBlur(radius=0.5))
            
            return final_stroke
            
        except Exception as e:
            safe_print(f"[现代描边] 膨胀蒙版创建失败: {e}")
            # 降级到简单矩形描边
            mask = Image.new('L', image.size, 0)
            draw = ImageDraw.Draw(mask)
            w, h = image.size
            # 绘制外框
            draw.rectangle((0, 0, w-1, h-1), outline=255, width=width)
            return mask


# 全局实例
_modern_style_renderer = None

def get_modern_style_renderer() -> ModernStyleRenderer:
    """获取现代样式渲染器"""
    global _modern_style_renderer
    if _modern_style_renderer is None:
        _modern_style_renderer = ModernStyleRenderer()
    return _modern_style_renderer
