#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layer 子 mixin 1: 图像源管理 + 图像加载/缩放/裁剪 + 图像缓存

从原 layer_new.py 拆分。涵盖：
- current_image_path / cached_image 属性
- _normalize_image_path / _paths_equal 路径处理
- extract_filename_core / get_bound_images 文件名核心名 + 绑定匹配
- get_image / get_random_image / _get_random_image_impl 图像获取
- _load_and_process_image / _process_image 图像加载与基础处理
- _find_non_transparent_bounds / _scale_and_crop / _scale_to_fit 缩放裁剪
"""

import os
import logging

from PIL import Image, ImageFile
from PIL.Image import Resampling

logger = logging.getLogger(__name__)


class LayerImageSourceMixin:
    """图像源管理 + 图像加载/缩放/裁剪 + 图像缓存（拆分自 Layer）。"""

    @property
    def current_image_path(self):
        return self._property_manager.get_property('current_image_path')

    @current_image_path.setter
    def current_image_path(self, value):
        self._property_manager.set_property('current_image_path', value, validate=False)

    @property
    def cached_image(self):
        return self._cached_image

    @cached_image.setter
    def cached_image(self, value):
        self._cached_image = value

    @staticmethod
    def _normalize_image_path(path_value):
        """规范化图片路径，统一本地与UNC表示。"""
        if not path_value:
            return path_value
        p = str(path_value).replace('/', os.sep)
        if p.startswith('\\\\'):
            return p
        if p.startswith('//'):
            server_share = p.lstrip('/').replace('/', '\\')
            return f"\\\\{server_share}"
        return os.path.normpath(p)

    @staticmethod
    def _paths_equal(left, right):
        """跨平台稳健路径比较（区分大小写策略跟随系统）。"""
        if not left or not right:
            return False
        return os.path.normcase(str(left)) == os.path.normcase(str(right))

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
        image_source = self.image_source
        if not image_source or not os.path.isdir(image_source):
            return []

        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        matching_files = []

        for file in os.listdir(image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                filename_without_ext = os.path.splitext(file)[0]
                core_name = self.extract_filename_core(filename_without_ext)

                if core_name == target_core_name:
                    matching_files.append(os.path.join(image_source, file))

        return matching_files

    def get_random_image(self, force_random=False, restrict_to_bound_files=None):
        """从关联文件夹中随机选择一张图片，或加载单个图片"""
        current_image_path = self.current_image_path
        image_source = self.image_source
        is_folder = self.is_folder
        image_source_norm = self._normalize_image_path(image_source) if image_source else image_source

        # 如果图像源是单个文件：优先命中缓存，避免每帧触发网络路径isfile开销
        if not is_folder and image_source_norm and not force_random:
            try:
                if self._cached_image is not None and self._paths_equal(self._cached_image_path, image_source_norm):
                    return self._cached_image
                if not os.path.isfile(image_source_norm):
                    return None

                old_width, old_height = self.width, self.height
                image = self._load_and_process_image(image_source_norm)

                if old_width != self.width or old_height != self.height:
                    self._property_manager.set_property('width', old_width, validate=False)
                    self._property_manager.set_property('height', old_height, validate=False)
                    if image.width != old_width or image.height != old_height:
                        # 使用预乘Alpha缩放以保护半透明图像质量
                        if image.mode == 'RGBA':
                            image = self._resize_rgba_premultiplied(image, (old_width, old_height), Resampling.BICUBIC)
                        else:
                            image = image.resize((old_width, old_height), Resampling.BICUBIC)

                self._cached_image = image
                self._cached_image_path = image_source_norm
                self._property_manager.set_property('current_image_path', image_source_norm, validate=False)
                return image
            except Exception as e:
                print(f"无法加载图像 {image_source}: {e}")
                err = self._create_error_image()
                self._cached_image = err
                self._cached_image_path = image_source_norm
                return err

        # 其他逻辑保持不变...
        return self._get_random_image_impl(force_random, restrict_to_bound_files)

    def get_image(self):
        """获取图层的当前图像"""
        current_path = self._normalize_image_path(self.current_image_path) if self.current_image_path else None

        # 热路径优化：缓存命中时直接返回，避免预览时频繁isfile/exists（网络盘尤其昂贵）
        if current_path and self._cached_image is not None and self._paths_equal(self._cached_image_path, current_path):
            return self._cached_image

        if current_path and os.path.isfile(current_path):
            try:
                img = self._load_and_process_image(current_path)
                self._cached_image = img
                self._cached_image_path = current_path
                return img
            except Exception as e:
                print(f"无法加载指定图像 {current_path}: {e}")
                self._property_manager.set_property('current_image_path', None, validate=False)
        elif current_path and not os.path.isfile(current_path):
            self._property_manager.set_property('current_image_path', None, validate=False)
            try:
                if hasattr(self, 'changed') and hasattr(self.changed, 'emit'):
                    self.changed.emit()
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in layer_new.py")
                pass

        try:
            src = self._normalize_image_path(self.image_source) if getattr(self, 'image_source', None) else None
            if src and os.path.isfile(src):
                self._property_manager.set_property('current_image_path', src, validate=False)
                try:
                    if self._cached_image is not None and self._paths_equal(self._cached_image_path, src):
                        return self._cached_image
                    img = self._load_and_process_image(src)
                    self._cached_image = img
                    self._cached_image_path = src
                    return img
                except Exception as e:
                    print(f"无法加载图像 {src}: {e}")
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in layer_new.py")
            pass

        return self.get_random_image(force_random=False)

    def _get_random_image_impl(self, force_random=False, restrict_to_bound_files=None):
        """随机图像选择的内部实现"""
        image_source = self.image_source
        is_folder = self.is_folder

        if not image_source or not os.path.isdir(image_source) or not is_folder:
            return None

        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        image_files = []

        for file in os.listdir(image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                image_files.append(os.path.join(image_source, file))

        if not image_files:
            return None

        # 使用缓存（仅当缓存路径与当前目标路径一致时）
        if not force_random and self._cached_image is not None and self._cached_image_path:
            try:
                current_path = self.current_image_path
                if current_path:
                    # 已指定当前路径时，缓存必须与当前路径一致，避免显示旧图
                    if self._paths_equal(self._cached_image_path, current_path):
                        return self._cached_image
                    else:
                        # 路径不一致，主动清缓存，确保后续按新路径加载
                        self._cached_image = None
                        self._cached_image_path = None
                else:
                    # 未指定当前路径时，允许沿用缓存
                    return self._cached_image
            except Exception:
                # 发生路径规范化异常时，保守处理：不使用缓存
                self._cached_image = None
                self._cached_image_path = None

        import random
        if not force_random and self.current_image_path and self.current_image_path in image_files:
            selected_path = self.current_image_path
        else:
            selected_path = random.choice(image_files)
        self._property_manager.set_property('current_image_path', selected_path, validate=False)

        try:
            img = self._load_and_process_image(selected_path)
            self._cached_image = img
            self._cached_image_path = selected_path
            return img
        except Exception as e:
            print(f"无法加载图像 {selected_path}: {e}")
            err = self._create_error_image()
            self._cached_image = err
            self._cached_image_path = selected_path
            return err

    def _load_and_process_image(self, image_path):
        """加载并处理图像"""
        try:
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            image_path_norm = self._normalize_image_path(image_path)
            if not image_path_norm or not os.path.exists(image_path_norm):
                raise FileNotFoundError(image_path_norm)
            # 先用源图缓存，避免连续交互（拖拽/缩放）反复从磁盘或网络读取同一路径
            if self._cached_source_image is None or not self._paths_equal(self._cached_source_path, image_path_norm):
                img = Image.open(image_path_norm)
                try:
                    img.load()
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in layer_new.py")
                    pass
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                self._cached_source_image = img.copy()
                self._cached_source_path = image_path_norm
                try:
                    img.close()
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in layer_new.py")
                    pass

            return self._process_image(self._cached_source_image.copy())

        except Exception as e:
            print(f"图像处理失败: {e}")
            return self._create_error_image()

    def _process_image(self, original_image):
        """处理图像的核心逻辑"""
        target_width = self.width
        target_height = self.height
        use_original_size = self.use_original_size
        fit_mode = self.fit_mode

        if use_original_size:
            # 智能裁剪逻辑
            bounds = self._find_non_transparent_bounds(original_image)
            if bounds != (0, 0, original_image.width, original_image.height):
                original_image = original_image.crop(bounds)

        # 根据适配模式调整大小
        if fit_mode == 0:  # 智能裁剪
            return self._scale_and_crop(original_image)
        elif fit_mode == 1:  # 智能缩放不裁剪
            return self._scale_to_fit(original_image)
        else:  # 拉伸适配
            # 使用预乘Alpha缩放以保护半透明图像质量
            if original_image.mode == 'RGBA':
                return self._resize_rgba_premultiplied(original_image, (target_width, target_height), Resampling.BICUBIC)
            else:
                return original_image.resize((target_width, target_height), Resampling.BICUBIC)

    def _find_non_transparent_bounds(self, image):
        """查找图像中非空白区域的边界"""
        import numpy as np
        if image.mode != 'RGBA':
            return (0, 0, image.width, image.height)

        try:
            img_array = np.array(image)
            alpha = img_array[:, :, 3]
            alpha_threshold = 5

            mask = alpha > alpha_threshold
            if not np.any(mask):
                return (0, 0, image.width, image.height)

            rows = np.any(mask, axis=1)
            cols = np.any(mask, axis=0)

            top = int(np.argmax(rows))
            bottom = image.height - int(np.argmax(rows[::-1]))
            left = int(np.argmax(cols))
            right = image.width - int(np.argmax(cols[::-1]))

            # 添加边距
            margin = 1
            left = max(0, int(left - margin))
            top = max(0, int(top - margin))
            right = min(image.width, right + margin)
            bottom = min(image.height, bottom + margin)

            return (left, top, right, bottom)

        except Exception as e:
            print(f"计算非空白区域边界时出错: {e}")
            return (0, 0, image.width, image.height)

    def _scale_and_crop(self, image):
        """等比缩放图像并按指定方向裁剪"""
        if image is None or image.width == 0 or image.height == 0:
            return None

        target_width = self.width
        target_height = self.height

        if target_width <= 0 or target_height <= 0:
            return None

        # 计算缩放尺寸
        orig_ratio = image.width / image.height
        target_ratio = target_width / target_height

        if orig_ratio > target_ratio:
            scale_height = target_height
            scale_width = int(scale_height * orig_ratio)
        else:
            scale_width = target_width
            scale_height = int(scale_width / orig_ratio)

        # 缩放 - 使用预乘Alpha保护半透明图像质量
        if image.mode == 'RGBA':
            scaled_image = self._resize_rgba_premultiplied(image, (scale_width, scale_height), Resampling.BICUBIC)
        else:
            scaled_image = image.resize((scale_width, scale_height), Resampling.BICUBIC)

        # 裁剪
        crop_direction = self.crop_direction
        if crop_direction == 0:  # 居中
            left = (scale_width - target_width) // 2
            top = (scale_height - target_height) // 2
        elif crop_direction == 1:  # 顶部
            left = (scale_width - target_width) // 2
            top = 0
        elif crop_direction == 2:  # 底部
            left = (scale_width - target_width) // 2
            top = scale_height - target_height
        elif crop_direction == 3:  # 左侧
            left = 0
            top = (scale_height - target_height) // 2
        elif crop_direction == 4:  # 右侧
            left = scale_width - target_width
            top = (scale_height - target_height) // 2
        else:
            left = (scale_width - target_width) // 2
            top = (scale_height - target_height) // 2

        # 确保裁剪区域有效
        left = max(0, min(left, scale_width - target_width))
        top = max(0, min(top, scale_height - target_height))

        return scaled_image.crop((left, top, left + target_width, top + target_height))

    def _scale_to_fit(self, image):
        """等比缩放图像以适应目标区域，不进行裁剪"""
        if image is None or image.width == 0 or image.height == 0:
            return None

        target_width = self.width
        target_height = self.height

        if target_width <= 0 or target_height <= 0:
            return None

        # 计算缩放尺寸
        orig_ratio = image.width / image.height
        target_ratio = target_width / target_height

        if orig_ratio > target_ratio:
            scale_width = target_width
            scale_height = int(scale_width / orig_ratio)
        else:
            scale_height = target_height
            scale_width = int(scale_height * orig_ratio)

        # 缩放
        if image.mode == 'RGBA':
            return self._resize_rgba_premultiplied(image, (scale_width, scale_height), Resampling.BICUBIC)
        else:
            return image.resize((scale_width, scale_height), Resampling.BICUBIC)
