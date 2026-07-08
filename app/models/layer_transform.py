import logging

logger = logging.getLogger(__name__)
from PySide6.QtCore import QObject, Signal, Property
import os
import builtins
import sys
import random
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from enum import Enum, auto
import copy  # 导入copy模块实现深拷贝
from collections import OrderedDict
import hashlib
import threading
from typing import List, Tuple
import math
from app.utils.image.high_quality_resampler import HighQualityResampler
from app.utils.render_diagnostics import log_branch


_LAYER_DEBUG = os.environ.get("BTPW_LAYER_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")


def print(*args, **kwargs):
    """Keep noisy layer diagnostics off the interactive preview path by default."""
    if _LAYER_DEBUG:
        builtins.print(*args, **kwargs)


def _is_batch_render_context() -> bool:
    """Cheap call-stack check used by legacy layer code.

    The previous inspect.stack() call allocates FrameInfo objects for the whole
    stack on every image load. Walking frames directly is much lighter and keeps
    the same behavior for batch/export detection.
    """
    frame = sys._getframe(1)
    checked = 0
    while frame is not None and checked < 32:
        name = frame.f_code.co_name
        if (
            "batch_export" in name
            or "render_batch" in name
            or "export_batch" in name
            or "generate_combinations" in name
        ):
            return True
        frame = frame.f_back
        checked += 1
    return False


class LayerTransform(object):
    """Mixin for layer_transform (split from Layer)."""

    def _apply_transformations(self, image):
        """应用图像变换（旋转和翻转）"""
        if image is None:
            return None
        
        result = image
        
        # 第一步：应用手动翻转
        if self._flip_horizontal:
            result = result.transpose(Transpose.FLIP_LEFT_RIGHT)
            print("应用水平翻转")
        
        if self._flip_vertical:
            result = result.transpose(Transpose.FLIP_TOP_BOTTOM)
            print("应用垂直翻转")
        
        # 第二步：应用手动旋转
        if abs(self._rotation) > 0.001:  # 避免浮点数精度问题
            # 检查是否是90度的倍数旋转
            rotation_angle = self._rotation % 360
            is_90_degree_rotation = (abs(rotation_angle % 90) < 0.1)
            
            if is_90_degree_rotation:
                # 对于90度的倍数旋转，使用expand=True以保持图像完整性
                result = HighQualityResampler.rotate_high_quality(
                    result,
                    -self._rotation,
                    expand=True,
                    resample=Resampling.BICUBIC,
                    enable_premultiplied=True
                )
                print(f"应用90度倍数旋转: {self._rotation}度 (扩展画布)")
                
                # 如果旋转后尺寸与图层尺寸不匹配，需要调整
                if result.width != self._width or result.height != self._height:
                    # 对于智能缩放模式，保持宽高比
                    if self._fit_mode == 1:  # 智能缩放不裁剪
                        # 计算等比缩放以适应图层尺寸
                        scale_ratio = min(self._width / result.width, self._height / result.height)
                        new_width = int(result.width * scale_ratio)
                        new_height = int(result.height * scale_ratio)
                        
                        # 缩放图像
                        scaled_result = self._resize_with_premultiplied_alpha(result, (new_width, new_height))
                        
                        # 创建图层尺寸的画布并居中放置
                        centered_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                        paste_x = (self._width - new_width) // 2
                        paste_y = (self._height - new_height) // 2
                        centered_result.paste(scaled_result, (paste_x, paste_y), scaled_result)
                        result = centered_result
                        
                        print(f"旋转后智能缩放: {result.width}x{result.height} -> {new_width}x{new_height}, 居中于 ({paste_x}, {paste_y})")
                    else:
                        # 对于其他模式，直接调整尺寸
                        result = self._resize_with_premultiplied_alpha(result, (self._width, self._height))
                        print(f"旋转后调整尺寸: {self._width}x{self._height}")
            else:
                # 对于非90度倍数的旋转，也扩展画布以避免裁剪
                result = HighQualityResampler.rotate_high_quality(
                    result,
                    -self._rotation,  # PIL使用逆时针为正，我们使用顺时针为正
                    expand=True,       # 扩展画布以容纳完整的旋转后图像
                    resample=Resampling.BICUBIC,   # 高质量重采样
                    enable_premultiplied=True
                )
                print(f"应用任意角度旋转: {self._rotation}度 (扩展画布)")
        
        # 第三步：应用随机变换（在手动变换之后）
        result = self._apply_random_transformations(result)
        
        return result
    
    def _apply_random_transformations(self, image):
        """应用随机变换（随机缩放和随机旋转）
        
        注意：随机位置偏移在渲染时处理，不在此处理
        """
        if image is None:
            return None
        
        result = image
        
        # 应用随机缩放
        if self._random_scale_enabled and abs(self._current_random_scale - 1.0) > 0.001:
            # 计算新尺寸
            new_width = int(result.width * self._current_random_scale)
            new_height = int(result.height * self._current_random_scale)
            
            # 缩放图像
            scaled_image = HighQualityResampler.resize(result, (new_width, new_height), method=Resampling.LANCZOS, enable_sharpening=False)
            
            # 创建一个与原图层尺寸相同的透明画布
            canvas = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
            
            # 计算居中位置
            paste_x = (self._width - new_width) // 2
            paste_y = (self._height - new_height) // 2
            
            # 将缩放后的图像粘贴到画布中央
            canvas.paste(scaled_image, (paste_x, paste_y), scaled_image if scaled_image.mode == 'RGBA' else None)
            
            result = canvas
            print(f"应用随机缩放: {self._current_random_scale:.3f}")
        
        # 应用随机旋转
        if self._random_rotation_enabled and abs(self._current_random_rotation) > 0.001:
            result = HighQualityResampler.rotate_high_quality(
                result,
                -self._current_random_rotation,  # PIL使用逆时针为正，我们使用顺时针为正
                expand=False,      # 不扩展画布尺寸
                resample=Resampling.BICUBIC,   # 高质量重采样
                enable_premultiplied=True
            )
            print(f"应用随机旋转: {self._current_random_rotation:.1f}度")
        
        return result
    
    def reset_transformations(self):
        """重置所有变换"""
        self._rotation = 0.0
        self._flip_horizontal = False
        self._flip_vertical = False
        self._cached_image = None
        self.changed.emit()
        print("重置所有变换")
    
    def apply_rotation_preset(self, preset):
        """应用旋转预设"""
        presets = {
            'rotate_90': 90.0,
            'rotate_180': 180.0,
            'rotate_270': 270.0,
            'rotate_45': 45.0,
            'rotate_-45': -45.0
        }
        
        if preset in presets:
            self.rotation = presets[preset]
            print(f"应用旋转预设: {preset} ({presets[preset]}度)")
    
    def _create_error_image(self):
        """创建错误图像（红色底色）"""
        error_image = Image.new('RGBA', (self._width, self._height), (255, 0, 0, 128))
        return error_image
    
    def _resize_with_premultiplied_alpha(self, image, size):
        """使用预乘Alpha方法缩放图像，避免半透明边缘暗晕"""
        try:
            if image.mode != 'RGBA':
                return image.resize(size, Resampling.BICUBIC)

            from app.utils.rgba_resampler import resize_rgba_premultiplied

            return resize_rgba_premultiplied(image, size, Resampling.BICUBIC)
            
        except Exception as e:
            print(f"预乘Alpha缩放失败: {e}")
            return image.resize(size, Resampling.BICUBIC)

    def _mark_dirty(self):
        """标记图层状态为脏，需要更新"""
        self._state_dirty = True
        self._cache_valid = False
        # 🔧 修复：清除所有图像缓存
        self._cached_image = None
        if hasattr(self, 'cached_image'):
            self.cached_image = None
        # 清理缓存路径，确保重新验证
        self._cached_image_path = None

    def _is_cache_valid(self):
        """检查缓存是否有效"""
        if not self._cache_valid:
            return False
        if not hasattr(self, '_cached_image') or self._cached_image is None:
            return False
        if hasattr(self, '_current_image_path') and self._current_image_path:
            # 检查缓存路径是否匹配当前路径
            return (hasattr(self, '_cached_image_path') and
                   self._cached_image_path == self._current_image_path)
        return True

    def _validate_cache(self):
        """验证并更新缓存状态"""
        if self._is_cache_valid():
            return True
        # 缓存无效，清理
        self.clear_cache()
        return False

    def clear_cache(self):
        """清理图像缓存，释放内存"""
        try:
            if hasattr(self, '_cached_image') and self._cached_image:
                # 关闭PIL图像对象
                if hasattr(self._cached_image, 'close'):
                    self._cached_image.close()
                self._cached_image = None

            if hasattr(self, '_cached_images') and self._cached_images:
                # 清理多个缓存图像
                for img in self._cached_images.values():
                    if img and hasattr(img, 'close'):
                        img.close()
                self._cached_images.clear()

            # 清理其他可能的图像缓存
            if hasattr(self, 'cached_image') and self.cached_image:
                if hasattr(self.cached_image, 'close'):
                    self.cached_image.close()
                self.cached_image = None

            # 重置缓存状态
            self._cache_valid = False
            self._cached_image_path = None

        except Exception as e:
            logger.debug("静默异常已忽略: except in models/layer_transform.py")
            pass

    def serialize(self):
        """将图层序列化为字典"""
        # 使用统一的序列化工具
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.serialize_layer(self)
    
    def duplicate(self, parent=None):
        """复制图层，创建一个完全相同的新实例"""
        # 使用统一的序列化工具进行复制
        from app.utils.layer_serializer import LayerSerializer
        
        # 传递parent参数
        kwargs = {}
        if parent is not None:
            kwargs['parent'] = parent
        else:
            kwargs['parent'] = self.parent()
            
        return LayerSerializer.duplicate_layer(self, target_layer_class=Layer, **kwargs)
    
    @classmethod
    def deserialize(cls, data, parent=None):
        """从字典反序列化图层"""
        # 使用统一的序列化工具
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.deserialize_layer(data, cls, parent=parent)
