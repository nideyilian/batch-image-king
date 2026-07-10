#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
"""
图像质量管理器
提供高质量的图像保存和处理功能
"""

import logging

logger = logging.getLogger(__name__)
import os
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np


class ImageQualityManager:
    """图像质量管理器"""

    @staticmethod
    def save_high_quality_image(image, file_path, format_hint=None):
        """
        保存高质量图像

        Args:
            image: PIL Image对象
            file_path: 保存路径
            format_hint: 格式提示

        Returns:
            bool: 保存是否成功
        """
        try:
            from app.services.export_service import ExportJob, get_export_service

            report = get_export_service().save_image(
                image,
                ExportJob(
                    file_path=file_path,
                    file_format=format_hint or "",
                    quality_profile="quality",
                    backend="auto",
                    max_file_size_kb=0,
                    allow_lossy_size_reduction=False,
                )
            )
            if not report.success:
                print(f"保存图像失败: {report.error}")
            return bool(report.success)
        except Exception:
            logger.warning("静默异常已忽略: except in utils/image_quality.py", exc_info=True)
            pass

        try:
            # 检查图像对象
            if image is None:
                print(f"[图像质量] 错误：图像对象为None")
                return False
            
            # 检查文件路径
            if not file_path:
                print(f"[图像质量] 错误：文件路径为空")
                return False
            
            # 确保目录存在
            dir_path = os.path.dirname(file_path)
            if dir_path:  # 只有当目录路径不为空时才创建
                os.makedirs(dir_path, exist_ok=True)

            # 根据文件扩展名确定格式
            if format_hint:
                format_name = format_hint.upper()
            else:
                _, ext = os.path.splitext(file_path)
                format_name = ext[1:].upper() if ext else 'PNG'

            try:
                from app.services.render_quality import get_quality_policy, prepare_image_for_export

                image = prepare_image_for_export(image, format_name, get_quality_policy("quality"))
            except Exception:
                logger.warning("静默异常已忽略: except in utils/image_quality.py", exc_info=True)
                pass

            # 处理不同格式
            if format_name in ['JPG', 'JPEG']:
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                # 高质量JPEG保存
                image.save(file_path, format='JPEG', quality=95, optimize=True)

            elif format_name == 'PNG':
                # PNG格式保持alpha通道
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')

                # 高质量PNG保存
                image.save(file_path, format='PNG', optimize=True)

            elif format_name in ['GIF', 'BMP', 'TIFF']:
                # 其他格式的标准保存
                image.save(file_path, format=format_name)

            else:
                # 默认PNG格式
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
                image.save(file_path, format='PNG', optimize=True)

            return True

        except Exception as e:
            print(f"保存图像失败: {e}")
            return False

    @staticmethod
    def enhance_image_quality(image, enhance_level='medium'):
        """
        增强图像质量

        Args:
            image: PIL Image对象
            enhance_level: 增强级别 ('low', 'medium', 'high')

        Returns:
            PIL Image: 增强后的图像
        """
        try:
            if enhance_level == 'low':
                # 轻微增强
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(1.1)

            elif enhance_level == 'medium':
                # 中等增强
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(1.2)
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.05)

            elif enhance_level == 'high':
                # 高级增强
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(1.3)
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.1)
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(1.05)

            return image

        except Exception as e:
            print(f"图像增强失败: {e}")
            return image

    @staticmethod
    def apply_unsharp_mask(image, radius=1.0, percent=50, threshold=3):
        """
        应用USM锐化

        Args:
            image: PIL Image对象
            radius: 锐化半径
            percent: 锐化强度百分比
            threshold: 锐化阈值

        Returns:
            PIL Image: 锐化后的图像
        """
        try:
            # 创建模糊版本
            blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))

            # 转换为numpy数组进行计算
            original = np.array(image, dtype=np.float32)
            blurred_array = np.array(blurred, dtype=np.float32)

            # 计算锐化
            mask = original - blurred_array
            sharpened = original + (mask * percent / 100.0)

            # 应用阈值
            mask_magnitude = np.abs(mask)
            sharpened = np.where(mask_magnitude > threshold, sharpened, original)

            # 限制值范围并转换回PIL图像
            sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
            return Image.fromarray(sharpened, mode=image.mode)

        except Exception as e:
            print(f"USM锐化失败: {e}")
            return image

    @staticmethod
    def optimize_for_web(image, max_size=(1920, 1080), quality=85):
        """
        为网络优化图像

        Args:
            image: PIL Image对象
            max_size: 最大尺寸 (width, height)
            quality: JPEG质量

        Returns:
            PIL Image: 优化后的图像
        """
        try:
            # 调整尺寸
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 转换为RGB（适合网络）
            if image.mode == 'RGBA':
                # 在白色背景上合成
                bg = Image.new('RGB', image.size, (255, 255, 255))
                bg.paste(image, (0, 0), image)
                image = bg
            elif image.mode != 'RGB':
                image = image.convert('RGB')

            return image

        except Exception as e:
            print(f"网络优化失败: {e}")
            return image

    @staticmethod
    def get_optimal_format(image, file_path):
        """
        获取最优的保存格式

        Args:
            image: PIL Image对象
            file_path: 文件路径

        Returns:
            str: 推荐的格式
        """
        try:
            # 根据图像特征推荐格式
            has_transparency = image.mode in ('RGBA', 'LA') or 'transparency' in image.info

            if has_transparency:
                return 'PNG'  # 有透明度用PNG
            else:
                # 检查是否是照片类型（颜色丰富）
                colors = image.getcolors(maxcolors=256*256*256)
                if colors and len(colors) > 1000:
                    return 'JPEG'  # 颜色丰富用JPEG
                else:
                    return 'PNG'   # 颜色简单用PNG

        except Exception:
            return 'PNG'  # 默认PNG

    @staticmethod
    def detect_text_content(image):
        """
        检测图像中是否包含文字内容

        Args:
            image: PIL Image对象

        Returns:
            bool: 是否检测到文字
        """
        try:
            # 简单的文字检测实现
            # 这里可以集成OCR库如pytesseract，但为了避免依赖问题，使用简单的启发式方法

            # 转换为灰度图像
            if image.mode != 'L':
                gray_image = image.convert('L')
            else:
                gray_image = image

            # 转换为numpy数组进行分析
            img_array = np.array(gray_image)

            # 计算图像的边缘密度（文字通常有较多边缘）
            # 使用简单的梯度计算
            if img_array.size > 0:
                # 计算水平和垂直梯度
                grad_x = np.abs(np.diff(img_array, axis=1))
                grad_y = np.abs(np.diff(img_array, axis=0))

                # 计算边缘密度
                edge_density = (np.sum(grad_x > 30) + np.sum(grad_y > 30)) / img_array.size

                # 如果边缘密度超过阈值，认为可能包含文字
                return edge_density > 0.01

            return False

        except Exception as e:
            print(f"文字检测失败: {e}")
            return False



    @staticmethod
    def get_recommended_quality_settings():
        """
        获取推荐的图像质量设置

        Returns:
            dict: 包含推荐质量设置的字典
        """
        # 这里可以根据系统资源、图像内容等动态调整
        # 目前返回一组高质量的默认值
        return {
            'jpeg_high_quality': 95,
            'jpeg_medium_quality': 85,
            'png_compress_level': 6,  # 0-9, quality-first default; speed mode uses lower levels
            'webp_quality': 90
        }