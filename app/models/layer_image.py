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
import logging
logger = logging.getLogger(__name__)


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


class LayerImage(object):
    """Mixin for layer_image (split from Layer)."""

    @property
    def cached_image(self):
        return self._cached_image
    
    @cached_image.setter
    def cached_image(self, value):
        self._cached_image = value
    
    def extract_filename_core(self, filename):
        """
        提取文件名的核心部分用于绑定匹配
        
        Args:
            filename: 文件名（不含扩展名）
            
        Returns:
            str: 核心文件名，例如：
                avatar_001 -> avatar
                bg-002 -> bg
                char_hero_03 -> char_hero
        """
        import re
        
        # 移除常见的数字后缀模式
        patterns = [
            r'[-_]\d+$',        # 匹配 _001, -02 等
            r'[-_]\d+[-_]\d+$', # 匹配 _01_02 等
            r'\d+$',            # 匹配末尾的纯数字
        ]
        
        core_name = filename
        for pattern in patterns:
            core_name = re.sub(pattern, '', core_name)
        
        return core_name.strip('_-') if core_name else filename
    
    def get_bound_images(self, target_core_name):
        """
        获取当前图层文件夹中与目标核心名称匹配的所有图像文件
        
        Args:
            target_core_name: 目标核心名称
            
        Returns:
            list: 匹配的图像文件路径列表
        """
        if not self._image_source or not os.path.isdir(self._image_source):
            return []
            
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        matching_files = []
        
        for file in os.listdir(self._image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                filename_without_ext = os.path.splitext(file)[0]
                core_name = self.extract_filename_core(filename_without_ext)
                
                if core_name == target_core_name:
                    matching_files.append(os.path.join(self._image_source, file))
        
        return matching_files
    
    def get_random_image(self, force_random=False, restrict_to_bound_files=None):
        """从关联文件夹中随机选择一张图片，或加载单个图片

        Args:
            force_random: 是否强制重新随机选择，忽略缓存
            restrict_to_bound_files: 限制可选择的文件列表（用于绑定管理器）
        """
        # 🔧 智能修复：检测是否为批量模式，预览启用缓存，批量禁用缓存
        is_batch_mode = _is_batch_render_context()

        # 检查调用栈，判断是否为批量导出模式
        if is_batch_mode:
            # 批量模式：禁用缓存验证，避免重复图片问题
            print(f"[图层] 🔧 批量模式：强制重新加载图像: {self.name}")
        else:
            # 预览模式：启用缓存验证，提高预览性能
            if not force_random and self._validate_cache() and self._cached_image is not None:
                print(f"[图层] ✅ 预览模式：使用缓存图像: {self.name}")
                return self._cached_image
            
        # 🔧 预计算导出修复：优先使用已指定的当前图像路径
        if self._current_image_path and os.path.isfile(self._current_image_path):
            try:
                print(f"[图层] 使用预设图像路径: {self._current_image_path}")
                # 保存当前尺寸，以便检测是否被意外更改
                old_width, old_height = self._width, self._height

                # 加载并处理图像
                image = self._load_and_process_image(self._current_image_path)

                # 如果尺寸被意外更改，恢复原有尺寸并打印警告
                if old_width != self._width or old_height != self._height:
                    print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                    self._width = old_width
                    self._height = old_height

                    # 如果尺寸发生变化，可能需要重新处理图像以匹配正确尺寸
                    if image.width != old_width or image.height != old_height:
                        print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                        # 使用预乘Alpha缩放保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_with_premultiplied_alpha(image, (old_width, old_height))
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)
                        # 🔧 关键修复：在批量模式下禁用缓存存储
                        if not is_batch_mode:
                            self._cached_image = image

                # 确保启用分身时图像正确处理
                if self._clone_enabled:
                    print(f"分身已启用，使用预设路径: {self._current_image_path}")
                return image
            except Exception as e:
                print(f"无法加载预设图像 {self._current_image_path}: {e}")
                # 在预计算模式下，如果指定图像加载失败，不应该继续随机选择
                if not force_random:
                    print(f"[图层] 预计算模式下指定图像加载失败，返回错误图像")
                    return self._create_error_image()
                # 清除无效的当前路径，继续执行随机选择
                self._current_image_path = None
            
        # 如果图像源是单个文件，直接使用（除非强制随机且实际是文件夹）
        # 规范化路径以正确识别UNC上的单文件
        def _normalize_path(p):
            if not p:
                return p
            p = p.replace('/', os.sep)
            if p.startswith('\\\\'):
                return p
            if p.startswith('//'):
                server_share = p.lstrip('/').replace('/', '\\')
                return f"\\\\{server_share}"
            return os.path.normpath(p)

        image_source_norm = _normalize_path(self._image_source) if self._image_source else self._image_source

        if not self._is_folder and image_source_norm and os.path.isfile(image_source_norm) and not force_random:
            try:
                print(f"加载单个图像: {image_source_norm}, 智能裁剪={self._use_original_size}")
                # 保存当前尺寸，以便检测是否被意外更改
                old_width, old_height = self._width, self._height

                # 加载并处理图像
                image = self._load_and_process_image(image_source_norm)
                
                # 如果尺寸被意外更改，恢复原有尺寸并打印警告
                if old_width != self._width or old_height != self._height:
                    print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                    self._width = old_width
                    self._height = old_height
                    
                    # 如果尺寸发生变化，可能需要重新处理图像以匹配正确尺寸
                    if image.width != old_width or image.height != old_height:
                        print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                        # 使用预乘Alpha缩放保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_with_premultiplied_alpha(image, (old_width, old_height))
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)
                        self._cached_image = image
                
                # 确保启用分身时图像正确处理
                if self._clone_enabled:
                    print(f"分身已启用，加载图像: {self._image_source}")
                return image
            except Exception as e:
                print(f"无法加载图像 {self._image_source}: {e}")
                return self._create_error_image()
                
        # 如果图像源是文件夹，随机选择图片
        if not self._image_source or not os.path.isdir(self._image_source):
            return None
            
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        image_files = []
        
        for file in os.listdir(self._image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                image_files.append(os.path.join(self._image_source, file))

        if not image_files:
            return None

        # 如果有文件限制，只使用限制范围内的文件
        if restrict_to_bound_files:
            # 将限制文件列表转换为绝对路径进行比较
            restricted_files = []
            for restricted_file in restrict_to_bound_files:
                if os.path.isabs(restricted_file):
                    restricted_files.append(restricted_file)
                else:
                    restricted_files.append(os.path.join(self._image_source, restricted_file))

            # 过滤出在限制范围内的文件
            image_files = [f for f in image_files if f in restricted_files]

            if not image_files:
                print(f"警告：文件限制后没有可用文件，图层: {self.name}")
                return None

        # 如果强制随机且有多个文件，尝试选择与当前不同的文件
        if force_random and len(image_files) > 1 and self._current_image_path:
            # 过滤掉当前图片，从剩余的图片中随机选择
            available_files = [f for f in image_files if f != self._current_image_path]
            if available_files:
                # 使用更好的随机选择算法
                import time
                import hashlib

                # 创建基于时间和文件路径的随机种子
                seed_string = f"{time.time_ns()}_{self._image_source}_{len(available_files)}"
                seed_hash = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
                random.seed(seed_hash)

                image_path = random.choice(available_files)
                print(f"强制随机选择新图片: {os.path.basename(image_path)} (避免重复: {os.path.basename(self._current_image_path)}) [种子:{seed_hash}]")

                # 恢复随机状态
                random.seed()
            else:
                image_path = random.choice(image_files)
                print(f"强制随机选择图片: {os.path.basename(image_path)} (无其他选择)")
        else:
            # 即使不是强制随机，也使用更好的随机算法
            if force_random or len(image_files) > 1:
                import time
                import hashlib

                seed_string = f"{time.time_ns()}_{self._image_source}_{random.random()}"
                seed_hash = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
                random.seed(seed_hash)

                image_path = random.choice(image_files)
                if force_random:
                    print(f"强制随机选择图片: {os.path.basename(image_path)} [种子:{seed_hash}]")

                # 恢复随机状态
                random.seed()
            else:
                image_path = random.choice(image_files)

        self._current_image_path = image_path

        # 如果是强制随机，清除缓存确保重新加载
        if force_random:
            self._cached_image = None

        try:
            # 保存当前尺寸，以便检测是否被意外更改
            old_width, old_height = self._width, self._height

            # 加载并处理图像
            image = self._load_and_process_image(image_path)
            
            # 如果尺寸被意外更改，恢复原有尺寸并打印警告
            if old_width != self._width or old_height != self._height:
                print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                self._width = old_width
                self._height = old_height
                
                # 如果尺寸发生变化，可能需要重新处理图像以匹配正确尺寸
                if image.width != old_width or image.height != old_height:
                    print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                    image = image.resize((old_width, old_height), Resampling.BICUBIC)
                    self._cached_image = image
            
            return image
        except Exception as e:
            # 使用日志记录错误，同时保持原有的print输出
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(f"无法加载图像 {image_path}: {e}", exc_info=True)
            except:
                logger.debug("静默异常已忽略: except: in layer_image.py")
                pass
            print(f"无法加载图像 {image_path}: {e}")
            return self._create_error_image()

    def get_image(self):
        """获取图层的当前图像

        这是一个兼容性方法，用于支持旧的代码调用

        Returns:
            PIL.Image: 图层的当前图像
        """
        # 如果有当前指定的图像路径，使用它
        if hasattr(self, '_current_image_path') and self._current_image_path:
            try:
                # 保存当前尺寸，以便检测是否被意外更改
                old_width, old_height = self._width, self._height

                # 加载并处理图像
                image = self._load_and_process_image(self._current_image_path)

                # 如果尺寸被意外更改，恢复原有尺寸
                if old_width != self._width or old_height != self._height:
                    print(f"警告：图层尺寸被意外更改: {old_width}x{old_height} => {self._width}x{self._height}，正在恢复")
                    self._width = old_width
                    self._height = old_height

                    # 如果尺寸发生变化，重新调整图像尺寸
                    if image.width != old_width or image.height != old_height:
                        print(f"重新调整图像尺寸以匹配图层尺寸: {old_width}x{old_height}")
                        # 使用预乘Alpha缩放保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_with_premultiplied_alpha(image, (old_width, old_height))
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)
                        self._cached_image = image

                # 确保启用分身时图像正确处理
                if self._clone_enabled:
                    print(f"分身已启用，使用路径: {self._current_image_path}")
                return image
            except Exception as e:
                print(f"无法加载指定图像 {self._current_image_path}: {e}")
                # 清除无效的当前路径，继续执行随机选择
                self._current_image_path = None
                # 通知文档状态已更改，需要UI更新
                if hasattr(self, 'changed') and hasattr(self.changed, 'emit'):
                    self.changed.emit()

        # 🔧 关键修复：完全禁用图层缓存使用，避免重复图片问题
        # 注释掉缓存使用，确保每次都重新加载图像
        # if hasattr(self, '_cached_image') and self._cached_image is not None:
        #     # 使用已缓存的图像
        #     image = self._cached_image
        #     # ... 缓存处理逻辑 ...
        #     return image
        print(f"[图层] 🔧 跳过缓存图像使用: {self.name} (强制重新加载)")

        # 否则获取随机图像
        return self.get_random_image(force_random=False)

    def _find_non_transparent_bounds(self, image):
        """查找图像中非空白区域的边界，使用更高效的检测方法
        
        Args:
            image: PIL图像对象，必须是RGBA模式
            
        Returns:
            元组 (left, top, right, bottom)，表示非空白区域的边界
        """
        if image.mode != 'RGBA':
            print("警告: 图像不是RGBA模式，无法检测透明度")
            return (0, 0, image.width, image.height)
        
        try:
            # 获取图像尺寸
            width, height = image.size
            print(f"检测非空白区域，图像尺寸: {width}x{height}")
            
            # 转换为numpy数组进行更高效的处理
            img_array = np.array(image)
            
            # 提取alpha通道
            alpha = img_array[:, :, 3]
            
            # 使用更低的透明度阈值，只要不是完全透明就算作内容
            alpha_threshold = 5
            
            # 找到alpha通道大于阈值的像素位置
            mask = alpha > alpha_threshold
            
            # 如果没有找到任何非透明像素，返回整个图像
            if not np.any(mask):
                print("未找到任何非透明像素，返回完整图像")
                return (0, 0, width, height)
            
            # 找到非透明区域的边界
            rows = np.any(mask, axis=1)
            cols = np.any(mask, axis=0)
            
            # 确定边界
            top = np.argmax(rows)
            bottom = height - np.argmax(rows[::-1])
            left = np.argmax(cols)
            right = width - np.argmax(cols[::-1])
            
            # 添加边距，避免太紧贴内容
            margin = 1
            left = max(0, int(left - margin))
            top = max(0, int(top - margin))
            right = min(width, right + margin)
            bottom = min(height, bottom + margin)
            
            print(f"找到非空白区域: ({left}, {top}, {right}, {bottom})")
            
            # 检查裁剪区域是否太小或太接近原图
            crop_width = right - left
            crop_height = bottom - top
            
            # 如果裁剪区域太小，返回完整图像
            if crop_width < 10 or crop_height < 10:
                print(f"裁剪区域过小 {crop_width}x{crop_height}，返回完整图像")
                return (0, 0, width, height)
                
            # 如果裁剪区域占比超过95%，返回完整图像
            crop_area = crop_width * crop_height
            original_area = width * height
            crop_ratio = crop_area / original_area
            
            if crop_ratio > 0.95:
                print(f"裁剪区域占比 {crop_ratio:.2%} 过大，几乎是整图，返回完整图像")
                return (0, 0, width, height)
                
            return (left, top, right, bottom)
            
        except Exception as e:
            print(f"计算非空白区域边界时出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时返回完整图像
            return (0, 0, image.width, image.height)
    
    def _load_and_process_image(self, image_path):
        """加载并处理图像，支持去除空白像素模式（优化版本）"""
        try:
            # 🔧 检测是否为批量模式
            is_batch_mode = _is_batch_render_context()

            # 尝试使用图像优化器进行快速加载
            try:
                from app.utils.image_optimizer import get_image_optimizer
                optimizer = get_image_optimizer()

                # 对于简单的适配模式，直接使用优化器
                if not self._smart_crop_enabled:
                    optimized_image = optimizer.load_image_optimized(
                        image_path,
                        (self._width, self._height),
                        fit_mode=self._fit_mode
                    )

                    if optimized_image:
                        # 🔧 智能修复：预览模式启用缓存存储，批量模式禁用缓存存储
                        if not is_batch_mode:
                            # 预览模式：启用缓存存储，提高预览性能
                            self._cached_image = optimized_image
                            self._cached_image_path = image_path
                            self._cache_valid = True
                        # 批量模式：不存储缓存，避免重复图片问题
                        return optimized_image

            except ImportError:
                # 图像优化器不可用，使用原有逻辑
                pass
            # 使用PIL打开图像（规范化路径，兼容UNC与正斜杠）
            def _normalize_path(p):
                if not p:
                    return p
                p = p.replace('/', os.sep)
                if p.startswith('\\\\'):
                    return p
                if p.startswith('//'):
                    server_share = p.lstrip('/').replace('/', '\\')
                    return f"\\\\{server_share}"
                return os.path.normpath(p)

            image_path_norm = _normalize_path(image_path)

            with Image.open(image_path_norm) as _img:
                original_image = _img if _img.mode == 'RGBA' else _img.convert('RGBA')
            # 复制为内存图，避免持有底层文件句柄
            original_image = original_image.copy()
            
            # 保存用户设置的目标尺寸（这个不能改变！）
            target_width = self._width
            target_height = self._height
            
            # 批处理模式下减少日志输出
            is_batch_mode = getattr(self, '_is_batch_mode', False)
            if not is_batch_mode:
                print(f"加载图像: {image_path}")
                print(f"用户设置的图层尺寸: {target_width}x{target_height}（此尺寸严格不变）")
                print(f"原始图像尺寸: {original_image.width}x{original_image.height}")
                print(f"处理模式: 智能裁剪={self._use_original_size}, 适配模式={self._fit_mode}")
                print(f"旋转角度: {self._rotation}度")
            
            # 使用中间变量来保存处理结果
            processed_image = original_image
            
            # 如果启用智能裁剪，先裁剪非空白区域
            if self._use_original_size:
                if not is_batch_mode:
                    print(f"========== 开始智能裁剪 ==========")
                
                # 查找非空白区域
                bounds = self._find_non_transparent_bounds(original_image)
                left, top, right, bottom = bounds
                
                # 检查是否需要裁剪
                needs_cropping = (left > 0 or top > 0 or right < original_image.width or bottom < original_image.height)
                
                if needs_cropping:
                    if not is_batch_mode:
                        print(f"执行智能裁剪: ({left}, {top}, {right}, {bottom})")
                    cropped_image = original_image.crop((left, top, right, bottom))
                    if not is_batch_mode:
                        print(f"裁剪结果: {cropped_image.width}x{cropped_image.height}")
                    processed_image = cropped_image
                else:
                    if not is_batch_mode:
                        print("不需要裁剪，保持原图")
                    processed_image = original_image
                
                if not is_batch_mode:
                    print(f"智能裁剪后图像尺寸: {processed_image.width}x{processed_image.height}")
                    print(f"========== 智能裁剪结束 ==========")
            
            # 创建一个透明背景图像，尺寸为图层尺寸
            final_image = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            
            # 根据适配模式调整图像大小并放置在图层中
            if self._fit_mode == 0:  # 智能裁剪(等比缩放后裁剪)
                print(f"使用智能裁剪(等比缩放后裁剪)模式")
                
                # 计算等比缩放尺寸
                src_ratio = processed_image.width / processed_image.height
                target_ratio = target_width / target_height
                
                if src_ratio > target_ratio:
                    # 源图更宽，以高度为基准缩放
                    scale_height = target_height
                    scale_width = int(scale_height * src_ratio)
                    print(f"等比缩放: 源图更宽，以高度为基准，缩放尺寸 {scale_width}x{scale_height}")
                else:
                    # 源图更高，以宽度为基准缩放
                    scale_width = target_width
                    scale_height = int(scale_width / src_ratio)
                    print(f"等比缩放: 源图更高，以宽度为基准，缩放尺寸 {scale_width}x{scale_height}")
                
                # 等比缩放
                scaled_image = self._resize_with_premultiplied_alpha(processed_image, (scale_width, scale_height))
                
                # 根据裁剪方向决定裁剪区域
                if self._crop_direction == 0:  # 居中
                    left = (scale_width - target_width) // 2
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：居中")
                elif self._crop_direction == 1:  # 顶部
                    left = (scale_width - target_width) // 2
                    top = 0
                    print(f"裁剪方向：顶部")
                elif self._crop_direction == 2:  # 底部
                    left = (scale_width - target_width) // 2
                    top = scale_height - target_height
                    print(f"裁剪方向：底部")
                elif self._crop_direction == 3:  # 左侧
                    left = 0
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：左侧")
                elif self._crop_direction == 4:  # 右侧
                    left = scale_width - target_width
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：右侧")
                else:  # 默认居中
                    left = (scale_width - target_width) // 2
                    top = (scale_height - target_height) // 2
                    print(f"裁剪方向：默认居中")
                
                # 确保裁剪区域不超出图像范围
                left = max(0, min(left, scale_width - target_width))
                top = max(0, min(top, scale_height - target_height))
                
                print(f"裁剪区域: ({left}, {top}, {left+target_width}, {top+target_height})")
                cropped_image = scaled_image.crop((left, top, left + target_width, top + target_height))
                print(f"返回裁剪图像: {cropped_image.width}x{cropped_image.height}")
                final_image = cropped_image
            elif self._fit_mode == 1:  # 智能缩放不裁剪
                print(f"使用智能缩放不裁剪模式")
                # 计算等比缩放尺寸
                src_ratio = processed_image.width / processed_image.height
                target_ratio = target_width / target_height
                
                if src_ratio > target_ratio:
                    # 源图更宽，以宽度为基准缩放
                    scale_width = target_width
                    scale_height = int(scale_width / src_ratio)
                else:
                    # 源图更高或相等，以高度为基准缩放
                    scale_height = target_height
                    scale_width = int(scale_height * src_ratio)
                
                # 等比缩放确保不会为0
                scale_width = max(1, scale_width)
                scale_height = max(1, scale_height)
                
                # 等比缩放
                scaled_image = self._resize_with_premultiplied_alpha(processed_image, (scale_width, scale_height))
                
                # 计算居中位置
                x = (target_width - scale_width) // 2
                y = (target_height - scale_height) // 2
                
                # 将缩放后的图像粘贴到透明背景的中心
                final_image.paste(scaled_image, (x, y), scaled_image)
                
                if not is_batch_mode:
                    print(f"智能缩放不裁剪: 原图宽高比 {src_ratio:.2f}, 目标宽高比 {target_ratio:.2f}")
                    print(f"智能缩放不裁剪: {'原图更宽' if src_ratio > target_ratio else '原图更高'}, 缩放尺寸 {scale_width}x{scale_height}")
                    print(f"智能缩放不裁剪: 最终尺寸 {target_width}x{target_height}, 内容位置 ({x}, {y})")
            else:  # 拉伸适配
                if not is_batch_mode:
                    print(f"使用拉伸适配调整到图层尺寸: {target_width}x{target_height}")
                resized_image = self._resize_with_premultiplied_alpha(processed_image, (target_width, target_height))
                final_image = resized_image
            
            # 🔧 智能修复：预览模式启用缓存存储，批量模式禁用缓存存储
            if not is_batch_mode:
                # 预览模式：启用缓存存储，提高预览性能
                self._cached_image = final_image
                self._cached_image_path = image_path
                self._cache_valid = True
            # 批量模式：不存储缓存，避免重复图片问题

            return final_image
            
        except Exception as e:
            # 批处理模式下减少错误日志输出
            is_batch_mode = getattr(self, '_is_batch_mode', False)
            if not is_batch_mode:
                print(f"图像处理失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 🔧 关键修复：清理无效的current_image_path
            if hasattr(self, '_current_image_path') and self._current_image_path:
                print(f"清理无效的current_image_path: {self._current_image_path}")
                self._current_image_path = None
                # 通知UI状态已改变
                if hasattr(self, 'changed') and hasattr(self.changed, 'emit'):
                    self.changed.emit()
            
            # 创建错误提示图像
            error_image = self._create_error_image()
            # 🔧 关键修复：禁用错误图像缓存存储
            # self._cached_image = error_image
            return error_image
    
    def _scale_and_crop(self, image):
        """等比缩放图像并按指定方向裁剪"""
        try:
            # 确保图像是有效的
            if image is None or image.width == 0 or image.height == 0:
                return None
                
            # 确保目标尺寸有效
            if self._width <= 0 or self._height <= 0:
                return None
                
            # 使用当前图层设置的尺寸
            target_width = self._width
            target_height = self._height
                
            # 打印调试信息 - 批处理模式下减少日志
            is_batch_mode = getattr(self, '_is_batch_mode', False)
            if not is_batch_mode:
                print(f"等比缩放: 图层尺寸 {target_width}x{target_height}, 图像尺寸 {image.width}x{image.height}")
                
            # 计算原始宽高比
            orig_width, orig_height = image.size
            orig_ratio = orig_width / orig_height
            
            # 计算目标宽高比
            target_ratio = target_width / target_height
            
            print(f"等比缩放: 原始宽高比 {orig_ratio:.2f}, 目标宽高比 {target_ratio:.2f}")
            
            # 确定缩放后的尺寸
            if orig_ratio > target_ratio:
                # 原图更宽，以高度为基准缩放
                scale_height = target_height
                scale_width = int(scale_height * orig_ratio)
                print(f"等比缩放: 原图更宽, 缩放尺寸 {scale_width}x{scale_height}")
            else:
                # 原图更高，以宽度为基准缩放
                scale_width = target_width
                scale_height = int(scale_width / orig_ratio)
                print(f"等比缩放: 原图更高, 缩放尺寸 {scale_width}x{scale_height}")
                
            # 等比缩放图像
            scaled_image = self._resize_with_premultiplied_alpha(image, (scale_width, scale_height))
            
            # 根据裁剪方向决定裁剪区域
            if self._crop_direction == 0:
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
            elif self._crop_direction == 1:
                left = (scale_width - target_width) // 2
                top = 0
            elif self._crop_direction == 2:
                left = (scale_width - target_width) // 2
                top = scale_height - target_height
            elif self._crop_direction == 3:
                left = 0
                top = (scale_height - target_height) // 2
            elif self._crop_direction == 4:
                left = scale_width - target_width
                top = (scale_height - target_height) // 2
            else:
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
            
            print(f"裁剪: 区域 ({left}, {top}, {left+target_width}, {top+target_height})")
            
            # 确保裁剪区域不超出图像范围
            left = max(0, min(left, scale_width - target_width))
            top = max(0, min(top, scale_height - target_height))
            
            # 裁剪图像
            cropped_image = scaled_image.crop((left, top, left + target_width, top + target_height))
            print(f"裁剪后尺寸: {cropped_image.width}x{cropped_image.height}, 期望尺寸: {target_width}x{target_height}")
            
            return cropped_image
        except Exception as e:
            print(f"等比缩放裁剪失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _scale_content_and_crop(self, image, target_width, target_height):
        """等比缩放裁剪后的内容图像，保持内容比例"""
        try:
            # 检查参数有效性
            if image is None or image.width == 0 or image.height == 0:
                print("警告：输入图像无效或尺寸为零")
                return None
            if target_width <= 0 or target_height <= 0:
                print(f"警告：目标尺寸无效：{target_width}x{target_height}")
                return None
            
            print(f"内容等比缩放：原始尺寸={image.width}x{image.height}, 目标尺寸={target_width}x{target_height}")
            
            # 计算比例
            src_ratio = image.width / image.height
            target_ratio = target_width / target_height
            
            print(f"内容等比缩放：原始宽高比={src_ratio:.2f}, 目标宽高比={target_ratio:.2f}")
            
            # 确定缩放方式
            if src_ratio > target_ratio:
                # 源图更宽，以高度为基准缩放
                scale_height = target_height
                scale_width = int(scale_height * src_ratio)
                print(f"源图更宽：以高度为基准缩放，缩放尺寸={scale_width}x{scale_height}")
            else:
                # 源图更高，以宽度为基准缩放
                scale_width = target_width
                scale_height = int(scale_width / src_ratio)
                print(f"源图更高：以宽度为基准缩放，缩放尺寸={scale_width}x{scale_height}")
            
            # 安全检查：确保缩放尺寸不为零
            if scale_width <= 0 or scale_height <= 0:
                print(f"警告：计算的缩放尺寸无效：{scale_width}x{scale_height}，回退到目标尺寸")
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            
            # 等比缩放
            try:
                scaled_image = HighQualityResampler.resize(image, (scale_width, scale_height), method=Resampling.LANCZOS, enable_sharpening=True)
                print(f"等比缩放后尺寸：{scaled_image.width}x{scaled_image.height}")
            except Exception as e:
                print(f"等比缩放失败：{e}，回退到直接缩放")
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            
            # 根据裁剪方向确定裁剪区域
            if self._crop_direction == 0:  # 居中
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：居中")
            elif self._crop_direction == 1:  # 顶部
                left = (scale_width - target_width) // 2
                top = 0
                print(f"裁剪方向：顶部")
            elif self._crop_direction == 2:  # 底部
                left = (scale_width - target_width) // 2
                top = scale_height - target_height
                print(f"裁剪方向：底部")
            elif self._crop_direction == 3:  # 左侧
                left = 0
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：左侧")
            elif self._crop_direction == 4:  # 右侧
                left = scale_width - target_width
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：右侧")
            else:  # 默认居中
                left = (scale_width - target_width) // 2
                top = (scale_height - target_height) // 2
                print(f"裁剪方向：默认居中")
            
            # 确保裁剪区域不超出图像范围
            left = max(0, min(left, scale_width - target_width))
            top = max(0, min(top, scale_height - target_height))
            right = left + target_width
            bottom = top + target_height
            
            # 确保裁剪区域的正确性
            if right > scale_width:
                right = scale_width
                left = max(0, right - target_width)
            if bottom > scale_height:
                bottom = scale_height
                top = max(0, bottom - target_height)
            
            print(f"裁剪区域：({left}, {top}, {right}, {bottom})")
            
            # 检查最终裁剪区域
            final_width = right - left
            final_height = bottom - top
            if final_width != target_width or final_height != target_height:
                print(f"警告：计算的裁剪区域尺寸 {final_width}x{final_height} 与目标尺寸 {target_width}x{target_height} 不符")
                # 如果裁剪区域尺寸不正确，可能需要调整策略
                if final_width <= 0 or final_height <= 0:
                    print("裁剪区域无效，回退到直接缩放")
                    return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            
            # 裁剪并返回
            try:
                cropped_image = scaled_image.crop((left, top, right, bottom))
                print(f"裁剪后最终尺寸：{cropped_image.width}x{cropped_image.height}")
                
                # 最终检查
                if cropped_image.width != target_width or cropped_image.height != target_height:
                    print(f"警告：最终图像尺寸 {cropped_image.width}x{cropped_image.height} 与目标尺寸 {target_width}x{target_height} 不符，调整大小")
                    cropped_image = HighQualityResampler.resize(cropped_image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
                
                return cropped_image
            except Exception as e:
                print(f"裁剪失败：{e}，回退到直接缩放")
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
        except Exception as e:
            print(f"等比缩放裁剪内容失败: {e}")
            import traceback
            traceback.print_exc()
            # 发生任何错误，尝试直接缩放原图
            try:
                return HighQualityResampler.resize(image, (target_width, target_height), method=Resampling.LANCZOS, enable_sharpening=True)
            except:
                logger.debug("静默异常已忽略: except: in layer_image.py")
                return None
    
    def _scale_to_fit(self, image):
        """等比缩放图像以适应目标区域，不进行裁剪，保持图像完整并最大化利用空间"""
        try:
            # 确保图像是有效的
            if image is None or image.width == 0 or image.height == 0:
                print("警告: 输入图像无效")
                return None
                
            # 确保目标尺寸有效
            if self._width <= 0 or self._height <= 0:
                print("警告: 目标尺寸无效")
                return None
                
            # 使用当前图层设置的尺寸
            target_width = self._width
            target_height = self._height
                
            # 打印调试信息
            print(f"等比缩放适配: 目标尺寸 {target_width}x{target_height}, 源图尺寸 {image.width}x{image.height}")
                
            # 计算原始宽高比
            orig_width, orig_height = image.size
            orig_ratio = orig_width / orig_height if orig_height > 0 else 1.0
            
            # 计算目标宽高比
            target_ratio = target_width / target_height if target_height > 0 else 1.0
            
            print(f"等比缩放适配: 源图比例 {orig_ratio:.3f}, 目标比例 {target_ratio:.3f}")
            
            # 计算缩放尺寸，确保内容完全可见且最大化填充空间
            if orig_ratio > target_ratio:
                # 原图更宽，以宽度为基准缩放（让宽度正好适合目标宽度）
                scale_width = target_width
                scale_height = int(scale_width / orig_ratio)
                print(f"等比缩放适配: 源图更宽，以宽度为基准，缩放尺寸 {scale_width}x{scale_height}")
            else:
                # 原图更高或比例相同，以高度为基准缩放（让高度正好适合目标高度）
                scale_height = target_height
                scale_width = int(scale_height * orig_ratio)
                print(f"等比缩放适配: 源图更高或等比，以高度为基准，缩放尺寸 {scale_width}x{scale_height}")
                
            # 确保计算结果不为零
            scale_width = max(1, scale_width)
            scale_height = max(1, scale_height)
            
            # 等比缩放图像
            scaled_image = HighQualityResampler.resize(image, (scale_width, scale_height), method=Resampling.LANCZOS, enable_sharpening=True)
            print(f"缩放后图像尺寸: {scaled_image.width}x{scaled_image.height}")
            
            # 创建透明背景图像
            result_image = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            
            # 计算居中位置
            pos_x = (target_width - scale_width) // 2
            pos_y = (target_height - scale_height) // 2
            
            # 将缩放后的图像粘贴到透明背景中央
            result_image.paste(scaled_image, (pos_x, pos_y))
            
            print(f"等比缩放适配: 最终尺寸 {result_image.width}x{result_image.height}, 内容位置 ({pos_x}, {pos_y})")
            
            return result_image
        except Exception as e:
            print(f"等比缩放适配失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _scale_content_to_fit(self, content_image, target_width, target_height):
        """对智能裁剪后的内容等比缩放以适应目标区域，不裁剪"""
        # 直接使用_scale_to_fit方法，保持代码一致性
        return self._scale_to_fit(content_image)
    
    def _apply_color_overlay(self, image):
        """应用颜色叠加"""
        if image is None:
            return None
            
        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            # 1. 创建纯色图层
            color = self._color_overlay_color
            if len(color) == 3:
                color = (*color, 255)
            
            # 使用原图大小
            overlay = Image.new('RGBA', image.size, color)
            
            # 2. 提取原图Alpha通道作为蒙版
            alpha = image.split()[3]
            
            # 将蒙版应用到纯色层
            # 注意：如果原图有半透明像素，alpha会保留这种半透明
            # 如果纯色层本身也是半透明的（color alpha < 255），那么需要组合
            # 这里我们假设color alpha只控制颜色本身的透明度，
            # 但最终的alpha必须受限于原图的形状(alpha)
            
            # 组合Alpha: min(original_alpha, color_alpha) ?
            # 通常Color Overlay是替换颜色，保留原图Alpha。
            # 但如果Overlay Color是半透明的，那么结果也应该是半透明的？
            # Photoshop: Color Overlay (Red, 50% Opacity) on Black Square -> Dark Red?
            # No, Photoshop "Opacity" in Layer Style is the blend opacity.
            # The Color Picker alpha is usually 100%.
            
            # Let's assume overlay.putalpha(alpha) sets the alpha channel to exactly 'alpha'.
            # This ignores the alpha of the color itself if it had any.
            # But our color is (R,G,B,A).
            
            # Correct logic:
            # Result Alpha = Original Alpha * (Color Alpha / 255)
            # But usually Color Overlay color is opaque.
            
            # Let's stick to simple:
            overlay.putalpha(alpha)
            
            # 3. 混合
            if self._color_overlay_opacity >= 1.0:
                return overlay
            
            return Image.blend(image, overlay, self._color_overlay_opacity)
            
        except Exception as e:
            print(f"[颜色叠加] 失败: {e}")
            return image

    def _apply_gradient_overlay(self, image):
        """应用渐变叠加"""
        if image is None:
            return None
            
        try:
            # 确保是RGBA
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            width, height = image.size
            
            # 1. 生成渐变图像
            # 计算对角线长度，确保旋转后覆盖全图
            diag = int(math.ceil(math.sqrt(width**2 + height**2)))
            if diag == 0: diag = 1
            
            # 创建渐变数据 (numpy)
            # 确保颜色列表有效
            if not self._gradient_overlay_colors or len(self._gradient_overlay_colors) < 2:
                # 默认黑白
                colors = [(0, 0, 0, 255), (255, 255, 255, 255)]
            else:
                colors = self._gradient_overlay_colors
                
            start_color = np.array(colors[0], dtype=float)
            end_color = np.array(colors[1], dtype=float)
            
            # 确保颜色是RGBA
            if len(start_color) == 3: start_color = np.append(start_color, 255.0)
            if len(end_color) == 3: end_color = np.append(end_color, 255.0)
            
            # 生成垂直渐变 (1 x diag)
            # 0.0 -> 1.0
            y = np.linspace(0, 1, diag).reshape(diag, 1)
            
            # 线性插值
            gradient_col = start_color * (1.0 - y) + end_color * y
            
            # 转换为uint8
            gradient_col = np.clip(gradient_col, 0, 255).astype(np.uint8)
            
            # 扩展为 (diag, diag)
            # 先转为Image strip (1, diag)
            # 注意: numpy array is (height, width, channels) -> (diag, 1, 4)
            gradient_strip = Image.fromarray(gradient_col.reshape(diag, 1, 4), 'RGBA')
            
            # Resize to (diag, diag) -> Stretch horizontally
            gradient_square = gradient_strip.resize((diag, diag), Resampling.NEAREST)
            
            # 2. 旋转
            # Photoshop默认90度是下到上？
            # 我们生成的是上到下。
            # 旋转 self._gradient_overlay_angle
            rotated_gradient = gradient_square.rotate(self._gradient_overlay_angle, expand=False, resample=Resampling.BILINEAR)
            
            # 3. 裁剪中心
            left = (diag - width) // 2
            top = (diag - height) // 2
            gradient_layer = rotated_gradient.crop((left, top, left + width, top + height))
            
            # 4. 应用蒙版
            alpha = image.split()[3]
            gradient_layer.putalpha(alpha)
            
            # 5. 混合
            if self._gradient_overlay_opacity >= 1.0:
                return gradient_layer
            
            return Image.blend(image, gradient_layer, self._gradient_overlay_opacity)
            
        except Exception as e:
            print(f"[渐变叠加] 失败: {e}")
            import traceback
            traceback.print_exc()
            return image

