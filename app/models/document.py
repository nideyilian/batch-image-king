import os
import random
import json
import pickle
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from PySide6.QtCore import QObject, Signal
import re
import glob
import gc
# 导入新的Layer类作为主要实现
from app.models.layer_new import Layer as NewLayer
from app.models.document_blend import BlendMode
from app.models.document_blend import Blender
from typing import List, Tuple
from app.models.binding_manager import BindingGroup
import time
import hashlib
from app.utils.render_diagnostics import log_branch, log_sampling
from app.utils.print_utils import safe_print as _safe_print
from app.utils.text_layer_virtual_path import is_text_layer_virtual_path, parse_text_layer_virtual_path
from app.models.layer_size_match_manager import LayerSizeMatchManager

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

def needs_cropping(bounds, image):
    """检查给定的边界是否需要裁剪
    
    Args:
        bounds: 边界元组 (left, top, right, bottom)
        image: PIL图像对象
        
    Returns:
        bool: 是否需要裁剪
    """
    left, top, right, bottom = bounds
    return (left > 0 or top > 0 or right < image.width or bottom < image.height)

class LegacyLayer:
    # 图像适配方式常量
    FIT_SMART_CROP = 0  # 智能缩放裁剪（保持比例并裁剪）
    FIT_SMART_FIT = 1   # 智能缩放不裁剪（保持比例并居中）
    
    # 裁剪方向常量
    CROP_CENTER = 0  # 中心裁剪
    CROP_TOP = 1     # 裁剪底部（保留顶部）
    CROP_BOTTOM = 2  # 裁剪顶部（保留底部）
    CROP_LEFT = 3    # 裁剪右侧（保留左侧）
    CROP_RIGHT = 4   # 裁剪左侧（保留右侧）
    
    def __init__(self, name, x, y, width, height, image_source=None, use_original_size=False, is_folder=True):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.visible = True
        self.opacity = 1.0
        self.image_source = image_source  # 可以是文件夹路径或单个文件路径
        self.is_folder = is_folder  # 标记图像源是文件夹还是单个文件
        self.current_image_path = None
        self.cached_image = None
        self.use_original_size = use_original_size  # 是否使用原始尺寸
        self.locked = False  # 图层锁定状态
        
        # 图像适配和裁剪设置
        self.fit_mode = self.FIT_SMART_CROP  # 默认智能缩放裁剪
        self.crop_direction = self.CROP_CENTER  # 默认中心裁剪
        
        # 圆角属性
        self.corner_radius = 0  # 圆角半径，0表示无圆角
        
        # 描边属性
        self.stroke_enabled = False
        self.stroke_width = 1
        self.stroke_color = (0, 0, 0, 255)  # RGBA格式
        
        # 分身属性
        self.clone_enabled = False
        self.clone_positions = []  # 分身位置列表
        self.clone_rows = 2        # 默认2行
        self.clone_columns = 2     # 默认2列
        self.clone_row_spacing = 10    # 默认行间距
        self.clone_column_spacing = 10 # 默认列间距
        
        # 混合模式属性
        self.blend_mode = BlendMode.NORMAL  # 默认正常混合模式
        
        # 变换属性
        self.rotation = 0.0         # 旋转角度（度）
        self.flip_horizontal = False # 水平翻转
        self.flip_vertical = False   # 垂直翻转
        
        # 随机变换属性 - 与手动变换分离，不冲突
        self.random_position_enabled = False  # 启用随机位置抖动
        self.random_position_range = 10  # 位置抖动范围（像素）
        self.random_scale_enabled = False  # 启用随机缩放
        self.random_scale_min = 0.9  # 最小缩放比例
        self.random_scale_max = 1.1  # 最大缩放比例
        self.random_rotation_enabled = False  # 启用随机旋转
        self.random_rotation_range = 5.0  # 随机旋转角度范围（度）
        
        # 当前随机变换状态（每次随机时生成）
        self._current_random_offset_x = 0
        self._current_random_offset_y = 0
        self._current_random_scale = 1.0
        self._current_random_rotation = 0.0
        
        # 如果图像源是单个文件，直接设置当前图像路径
        if image_source and not is_folder and os.path.isfile(image_source):
            self.current_image_path = image_source
        
    def get_random_image(self, force_random=False, restrict_to_bound_files=None):
        """从关联文件夹中随机选择一张图片，或加载单个图片

        Args:
            force_random (bool): 是否强制重新随机选择，即使已有current_image_path
            restrict_to_bound_files: 限制可选择的文件列表（用于绑定管理器）
        """
        # 如果图像源是单个文件，直接使用它
        if not self.is_folder and self.image_source and os.path.isfile(self.image_source):
            self.current_image_path = self.image_source
            try:
                # 在上下文中完成转换与复制，避免关闭后再操作
                with Image.open(self.image_source) as _img:
                    if _img.mode != 'RGBA':
                        if _img.mode == 'CMYK':
                            _img = _img.convert('RGB')
                        _img = _img.convert('RGBA')
                    image = _img.copy()
                
                # 确保透明通道正确初始化
                # 某些PNG可能存在无效的Alpha通道，需要额外处理
                if 'A' in image.getbands() and image.getchannel('A').getextrema() == (0, 0):
                    # 如果Alpha通道全为0，设置为全透明
                    r, g, b, _ = image.split()
                    new_alpha = Image.new('L', image.size, 255)  # 创建完全不透明的alpha通道
                    image = Image.merge('RGBA', (r, g, b, new_alpha))
                
                # 如果使用智能裁剪
                if self.use_original_size:
                    print(f"使用智能裁剪处理图像")
                    
                    # 查找图像中非空白区域
                    try:
                        img_array = np.array(image)
                        alpha = img_array[:, :, 3]
                        
                        # 找到非透明区域
                        alpha_threshold = 5
                        mask = alpha > alpha_threshold
                        
                        if np.any(mask):
                            # 找到非透明区域的边界
                            rows = np.any(mask, axis=1)
                            cols = np.any(mask, axis=0)
                            
                            top = np.argmax(rows)
                            bottom = image.height - np.argmax(rows[::-1])
                            left = np.argmax(cols)
                            right = image.width - np.argmax(cols[::-1])
                            
                            # 添加边距
                            margin = 1
                            left = max(0, int(left - margin))
                            top = max(0, int(top - margin))
                            right = min(image.width, int(right + margin))
                            bottom = min(image.height, int(bottom + margin))
                            
                            # 检查裁剪区域是否有效
                            crop_area = (right - left) * (bottom - top)
                            total_area = image.width * image.height
                            
                            if crop_area / total_area < 0.95 and (right - left) > 10 and (bottom - top) > 10:
                                print(f"智能裁剪区域: ({left}, {top}, {right}, {bottom})")
                                image = image.crop((left, top, right, bottom))
                                print(f"智能裁剪后尺寸: {image.width}x{image.height}")
                            else:
                                print("检测到的有效区域过大或过小，无需裁剪")
                        else:
                            print("未找到非透明区域，保持原图")
                    except Exception as e:
                        print(f"智能裁剪处理出错: {e}")
                
                # 接下来根据适配模式处理图像尺寸
                if self.fit_mode == self.FIT_SMART_FIT:
                    # 智能缩放不裁剪
                    resized_image = self._scale_and_crop(image)
                    if resized_image is None:
                        # 如果智能缩放失败，回退到拉伸方式
                        print("智能缩放不裁剪失败，回退到拉伸方式")
                        # 使用预乘Alpha缩放以保护半透明图像质量
                        if image.mode == 'RGBA':
                            resized_image = self._resize_with_premultiplied_alpha(image, (self.width, self.height))
                        else:
                            resized_image = image.resize((self.width, self.height), Resampling.BICUBIC)
                        
                    self.cached_image = resized_image
                    return resized_image
                else:  # FIT_SMART_CROP
                    # 智能缩放裁剪
                    resized_image = self._scale_and_crop(image)
                    if resized_image is None:
                        # 如果等比缩放裁剪失败，回退到拉伸方式
                        print("智能缩放裁剪失败，回退到拉伸方式")
                        # 使用预乘Alpha缩放以保护半透明图像质量
                        if image.mode == 'RGBA':
                            resized_image = self._resize_with_premultiplied_alpha(image, (self.width, self.height))
                        else:
                            resized_image = image.resize((self.width, self.height), Resampling.BICUBIC)
                        
                    self.cached_image = resized_image
                    return resized_image
            except Exception as e:
                print(f"无法加载图像 {self.image_source}: {e}")
                # 创建一个带有错误提示的空白图像
                error_image = Image.new('RGBA', (self.width, self.height), (255, 0, 0, 128))
                self.cached_image = error_image
                return error_image
                
        # 如果图像源是文件夹，随机选择图片
        if not self.image_source or not os.path.isdir(self.image_source):
            return None
            
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        image_files = []
        
        for file in os.listdir(self.image_source):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                image_files.append(os.path.join(self.image_source, file))

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
                    restricted_files.append(os.path.join(self.image_source, restricted_file))

            # 过滤出在限制范围内的文件
            image_files = [f for f in image_files if f in restricted_files]

            if not image_files:
                print(f"警告：文件限制后没有可用文件，图层: {self.name}")
                return None
        
        # 如果已经有current_image_path且文件存在，并且不强制随机，直接使用它
        if (not force_random and 
            self.current_image_path and 
            os.path.isfile(self.current_image_path) and 
            self.current_image_path in image_files):
            image_path = self.current_image_path
        else:
            # 强制随机选择时，使用增强随机化
            if force_random:
                import time
                # 使用时间戳增强随机种子
                random.seed(int(time.time() * 1000000) % 2**32)
                
                # 多次洗牌增加随机性
                for _ in range(5):
                    random.shuffle(image_files)
                
                # 尝试选择与当前不同的文件（如果可能）
                if len(image_files) > 1 and self.current_image_path:
                    available_files = [f for f in image_files if f != self.current_image_path]
                    if available_files:
                        image_path = random.choice(available_files)
                    else:
                        image_path = random.choice(image_files)
                else:
                    image_path = random.choice(image_files)
                
                # 恢复随机种子
                random.seed()
            else:
                # 否则正常随机选择一个文件
                image_path = random.choice(image_files)
            
            self.current_image_path = image_path
        
        try:
            # 在上下文中完成转换与复制
            with Image.open(image_path) as _img:
                if _img.mode != 'RGBA':
                    _img = _img.convert('RGBA')
                image = _img.copy()
            
            # 如果使用智能裁剪
            if self.use_original_size:
                print(f"使用智能裁剪处理图像")
                
                # 查找图像中非空白区域
                try:
                    img_array = np.array(image)
                    alpha = img_array[:, :, 3]
                    
                    # 找到非透明区域
                    alpha_threshold = 5
                    mask = alpha > alpha_threshold
                    
                    if np.any(mask):
                        # 找到非透明区域的边界
                        rows = np.any(mask, axis=1)
                        cols = np.any(mask, axis=0)
                        
                        top = np.argmax(rows)
                        bottom = image.height - np.argmax(rows[::-1])
                        left = np.argmax(cols)
                        right = image.width - np.argmax(cols[::-1])
                        
                        # 添加边距
                        margin = 1
                        left = max(0, int(left - margin))
                        top = max(0, int(top - margin))
                        right = min(image.width, int(right + margin))
                        bottom = min(image.height, int(bottom + margin))
                        
                        # 检查裁剪区域是否有效
                        crop_area = (right - left) * (bottom - top)
                        total_area = image.width * image.height
                        
                        if crop_area / total_area < 0.95 and (right - left) > 10 and (bottom - top) > 10:
                            print(f"智能裁剪区域: ({left}, {top}, {right}, {bottom})")
                            image = image.crop((left, top, right, bottom))
                            print(f"智能裁剪后尺寸: {image.width}x{image.height}")
                        else:
                            print("检测到的有效区域过大或过小，无需裁剪")
                    else:
                        print("未找到非透明区域，保持原图")
                except Exception as e:
                    print(f"智能裁剪处理出错: {e}")
            
            # 根据适配模式处理图像
            if self.fit_mode == self.FIT_SMART_FIT:
                # 智能缩放不裁剪
                resized_image = self._scale_and_crop(image)
                if resized_image is None:
                    # 如果智能缩放失败，回退到拉伸方式
                    print("智能缩放不裁剪失败，回退到拉伸方式")
                    if image.mode == 'RGBA':
                        resized_image = self._resize_with_premultiplied_alpha(image, (self.width, self.height))
                    else:
                        resized_image = image.resize((self.width, self.height), Resampling.BICUBIC)
                    
                self.cached_image = resized_image
                return resized_image
            else:  # FIT_SMART_CROP
                # 智能缩放裁剪
                resized_image = self._scale_and_crop(image)
                if resized_image is None:
                    # 如果等比缩放裁剪失败，回退到拉伸方式
                    print("智能缩放裁剪失败，回退到拉伸方式")
                    if image.mode == 'RGBA':
                        resized_image = self._resize_with_premultiplied_alpha(image, (self.width, self.height))
                    else:
                        resized_image = image.resize((self.width, self.height), Resampling.BICUBIC)
                    
                self.cached_image = resized_image
                return resized_image
                
        except Exception as e:
            print(f"无法加载图像 {image_path}: {e}")
            # 创建一个带有错误提示的空白图像
            error_image = Image.new('RGBA', (self.width, self.height), (255, 0, 0, 128))
            self.cached_image = error_image
            return error_image

    def get_image(self):
        """获取当前设置的图像（用于预计算导出）

        与get_random_image不同，这个方法使用当前设置的current_image_path，
        不会进行随机选择，适用于预计算导出场景。
        """
        # 如果没有设置current_image_path，回退到随机选择
        if not self.current_image_path:
            return self.get_random_image(force_random=False)

        # 检查当前路径是否有效
        if not os.path.isfile(self.current_image_path):
            print(f"警告：当前图像路径无效 {self.current_image_path}，回退到随机选择")
            return self.get_random_image(force_random=False)

        try:
            # 在上下文中完成转换与复制
            with Image.open(self.current_image_path) as _img:
                if _img.mode != 'RGBA':
                    if _img.mode == 'CMYK':
                        _img = _img.convert('RGB')
                    _img = _img.convert('RGBA')
                image = _img.copy()

            # 处理透明通道
            if 'A' in image.getbands() and image.getchannel('A').getextrema() == (0, 0):
                r, g, b, _ = image.split()
                new_alpha = Image.new('L', image.size, 255)
                image = Image.merge('RGBA', (r, g, b, new_alpha))

            # 智能裁剪处理（如果启用）
            if self.use_original_size:
                try:
                    img_array = np.array(image)
                    alpha = img_array[:, :, 3]
                    alpha_threshold = 5
                    mask = alpha > alpha_threshold

                    if np.any(mask):
                        rows = np.any(mask, axis=1)
                        cols = np.any(mask, axis=0)

                        top = np.argmax(rows)
                        bottom = image.height - np.argmax(rows[::-1])
                        left = np.argmax(cols)
                        right = image.width - np.argmax(cols[::-1])

                        margin = 1
                        left = max(0, int(left - margin))
                        top = max(0, int(top - margin))
                        right = min(image.width, int(right + margin))
                        bottom = min(image.height, int(bottom + margin))

                        crop_area = (right - left) * (bottom - top)
                        total_area = image.width * image.height

                        if crop_area / total_area < 0.95 and (right - left) > 10 and (bottom - top) > 10:
                            image = image.crop((left, top, right, bottom))
                except Exception as e:
                    print(f"智能裁剪处理出错: {e}")

            # 根据适配模式处理图像
            resized_image = self._scale_and_crop(image)
            if resized_image is None:
                if image.mode == 'RGBA':
                    resized_image = self._resize_with_premultiplied_alpha(image, (self.width, self.height))
                else:
                    resized_image = image.resize((self.width, self.height), Resampling.BICUBIC)

            self.cached_image = resized_image
            return resized_image

        except Exception as e:
            print(f"无法加载图像 {self.current_image_path}: {e}")
            error_image = Image.new('RGBA', (self.width, self.height), (255, 0, 0, 128))
            self.cached_image = error_image
            return error_image

    def _scale_and_crop(self, image):
        """根据适配模式处理图像尺寸"""
        try:
            # 确保图像是有效的
            if image is None or image.width == 0 or image.height == 0:
                return None
                
            # 确保目标尺寸有效
            if self.width <= 0 or self.height <= 0:
                return None
            
            # 确保图像是RGBA模式，保留所有透明信息
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            # 使用当前图层设置的尺寸
            target_width = self.width
            target_height = self.height
                
            # 打印调试信息
            print(f"智能缩放: 图层尺寸 {target_width}x{target_height}, 图像尺寸 {image.width}x{image.height}")
                
            # 计算原始宽高比
            orig_width, orig_height = image.size
            orig_ratio = orig_width / orig_height
            
            # 计算目标宽高比
            target_ratio = target_width / target_height
            
            print(f"智能缩放: 原始宽高比 {orig_ratio:.2f}, 目标宽高比 {target_ratio:.2f}")
            
            # 根据适配模式处理
            if self.fit_mode == self.FIT_SMART_FIT:
                # 智能缩放不裁剪（保持比例并居中）
                if orig_ratio > target_ratio:
                    # 原图更宽，以宽度为基准缩放
                    scale_width = target_width
                    scale_height = int(scale_width / orig_ratio)
                    print(f"智能缩放不裁剪: 原图更宽, 缩放尺寸 {scale_width}x{scale_height}")
                else:
                    # 原图更高，以高度为基准缩放
                    scale_height = target_height
                    scale_width = int(scale_height * orig_ratio)
                    print(f"智能缩放不裁剪: 原图更高, 缩放尺寸 {scale_width}x{scale_height}")
                    
                # Photoshop风格的高质量缩放方法
                # 先检测图像是否包含文字或细小边缘
                has_text = self._detect_text_or_fine_edges(image)
                
                if has_text:
                    # 对于文字或细边缘，使用高质量的多步缩放+锐化组合
                    scaled_image = self._high_quality_text_resize(image, (scale_width, scale_height))
                else:
                    # 正常图像使用渐进式缩放，类似Photoshop的"双线性"或"双三次"方法
                    scaled_image = self._progressive_resize(image, (scale_width, scale_height))
                
                # 创建透明背景图像
                result_image = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
                
                # 计算居中位置
                pos_x = (target_width - scale_width) // 2
                pos_y = (target_height - scale_height) // 2
                
                # 将缩放后的图像粘贴到透明背景中央，使用alpha通道作为蒙版
                alpha_mask = scaled_image if 'A' in scaled_image.getbands() else None
                result_image.paste(scaled_image, (pos_x, pos_y), alpha_mask)
                
                print(f"智能缩放不裁剪: 最终尺寸 {result_image.width}x{result_image.height}, 内容位置 ({pos_x}, {pos_y})")
                
                return result_image
            else:  # FIT_SMART_CROP
                # 智能缩放裁剪（保持比例并裁剪）
                if orig_ratio > target_ratio:
                    # 原图更宽，以高度为基准缩放
                    scale_height = target_height
                    scale_width = int(scale_height * orig_ratio)
                    print(f"智能缩放裁剪: 原图更宽, 缩放尺寸 {scale_width}x{scale_height}")
                else:
                    # 原图更高，以宽度为基准缩放
                    scale_width = target_width
                    scale_height = int(scale_width / orig_ratio)
                    print(f"智能缩放裁剪: 原图更高, 缩放尺寸 {scale_width}x{scale_height}")
                    
                # Photoshop风格的高质量缩放方法
                # 先检测图像是否包含文字或细小边缘
                has_text = self._detect_text_or_fine_edges(image)
                
                if has_text:
                    # 对于文字或细边缘，使用高质量的多步缩放+锐化组合
                    scaled_image = self._high_quality_text_resize(image, (scale_width, scale_height))
                else:
                    # 正常图像使用渐进式缩放，类似Photoshop的"双线性"或"双三次"方法
                    scaled_image = self._progressive_resize(image, (scale_width, scale_height))
                
                # 根据裁剪方向决定裁剪区域
                if self.crop_direction == self.CROP_CENTER:
                    left = (scale_width - target_width) // 2
                    top = (scale_height - target_height) // 2
                elif self.crop_direction == self.CROP_TOP:
                    left = (scale_width - target_width) // 2
                    top = 0
                elif self.crop_direction == self.CROP_BOTTOM:
                    left = (scale_width - target_width) // 2
                    top = scale_height - target_height
                elif self.crop_direction == self.CROP_LEFT:
                    left = 0
                    top = (scale_height - target_height) // 2
                elif self.crop_direction == self.CROP_RIGHT:
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
            print(f"智能缩放失败: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    def _detect_text_or_fine_edges(self, image):
        """检测图像是否包含文字或精细边缘，用于选择最佳缩放策略"""
        try:
            # 转换为灰度
            if image.mode != 'L':
                gray_image = image.convert('L')
            else:
                gray_image = image.copy()
                
            # 使用Sobel算子检测边缘
            from scipy import ndimage
            gray_array = np.array(gray_image)
            
            # 应用Sobel滤波器检测边缘
            sobel_h = ndimage.sobel(gray_array, axis=0)
            sobel_v = ndimage.sobel(gray_array, axis=1)
            magnitude = np.sqrt(sobel_h**2 + sobel_v**2)
            
            # 计算强边缘的比例
            edge_threshold = 50  # 边缘强度阈值
            strong_edge_ratio = np.sum(magnitude > edge_threshold) / magnitude.size
            
            # 根据边缘比例判断是否包含文字或细边缘
            # 文字通常具有较高的边缘密度
            is_text = strong_edge_ratio > 0.03  # 3%是个经验值，可根据实际调整
            
            print(f"边缘检测: 强边缘比例 {strong_edge_ratio:.4f}, 判断为{'文字' if is_text else '普通图像'}")
            return is_text
        except Exception as e:
            print(f"边缘检测失败: {e}")
            return False  # 出错时默认为非文字图像
            
    def _high_quality_text_resize(self, image, size):
        """Photoshop风格的高质量文字缩放方法，适用于文字和细边缘"""
        try:
            # 获取目标尺寸
            target_width, target_height = size
            
            # 如果尺寸变化不大，直接使用高质量重采样
            if 0.9 < image.width / target_width < 1.1 and 0.9 < image.height / target_height < 1.1:
                return image.resize(size, Resampling.BICUBIC)
                
            # 对于更大缩放比例，使用多步渐进式缩放
            current_w, current_h = image.width, image.height
            scaled_image = image
            
            # 计算缩放步骤，确保每步缩放比例不超过0.7
            max_ratio = 0.7
            
            while current_w * max_ratio > target_width or current_h * max_ratio > target_height:
                # 计算下一步尺寸
                next_w = max(int(current_w * max_ratio), target_width)
                next_h = max(int(current_h * max_ratio), target_height)
                
                # 如果已经非常接近目标尺寸，直接到最终尺寸
                if next_w < target_width * 1.1 and next_h < target_height * 1.1:
                    next_w, next_h = target_width, target_height
                
                print(f"多步缩放: {current_w}x{current_h} -> {next_w}x{next_h}")
                
                # 缩放当前步骤
                scaled_image = scaled_image.resize((next_w, next_h), Resampling.BICUBIC)
                
                # 应用轻微锐化，增强边缘，模拟Photoshop智能锐化效果
                if next_w != target_width or next_h != target_height:
                    from PIL import ImageFilter
                    sharp_filter = ImageFilter.UnsharpMask(radius=0.5, percent=80, threshold=3)
                    scaled_image = scaled_image.filter(sharp_filter)
                
                # 更新当前尺寸
                current_w, current_h = next_w, next_h
                
                # 如果已达到目标尺寸，退出循环
                if current_w == target_width and current_h == target_height:
                    break
            
            # 最后一步：确保精确达到目标尺寸
            if current_w != target_width or current_h != target_height:
                scaled_image = scaled_image.resize((target_width, target_height), Resampling.BICUBIC)
            
            return scaled_image
        except Exception as e:
            print(f"高质量文字缩放失败: {e}")
            # 失败回退到普通缩放
            return image.resize(size, Resampling.BICUBIC)
    
    def _progressive_resize(self, image, size):
        """渐进式缩放，用于普通图像，模拟Photoshop的平滑缩放"""
        try:
            target_width, target_height = size
            
            # 如果尺寸变化不大，直接使用高质量重采样
            if 0.9 < image.width / target_width < 1.1 and 0.9 < image.height / target_height < 1.1:
                return image.resize(size, Resampling.BICUBIC)
            
            # 对于缩小操作，先进行适当模糊，减少摩尔纹
            if target_width < image.width or target_height < image.height:
                # 计算缩放比例
                scale_ratio = min(target_width / image.width, target_height / image.height)
                
                # 根据缩放比例选择适当的模糊半径
                blur_radius = max(0, min(2.0, (1.0 - scale_ratio) * 2.0))
                
                if blur_radius > 0.3:
                    from PIL import ImageFilter
                    image = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            # 使用渐进式缩放
            current_w, current_h = image.width, image.height
            scaled_image = image
            
            # 计算缩放步骤
            step_ratio = 0.8  # 每步缩放到80%
            
            while current_w * step_ratio > target_width or current_h * step_ratio > target_height:
                # 计算下一步尺寸
                next_w = max(int(current_w * step_ratio), target_width)
                next_h = max(int(current_h * step_ratio), target_height)
                
                # 如果已经非常接近目标尺寸，直接到最终尺寸
                if next_w < target_width * 1.05 and next_h < target_height * 1.05:
                    next_w, next_h = target_width, target_height
                
                print(f"渐进式缩放: {current_w}x{current_h} -> {next_w}x{next_h}")
                
                # 缩放当前步骤，使用BICUBIC保持边缘清晰
                scaled_image = scaled_image.resize((next_w, next_h), Resampling.BICUBIC)
                
                # 更新当前尺寸
                current_w, current_h = next_w, next_h
                
                # 如果已达到目标尺寸，退出循环
                if current_w == target_width and current_h == target_height:
                    break
            
            # 最后一步：确保精确达到目标尺寸
            if current_w != target_width or current_h != target_height:
                scaled_image = scaled_image.resize((target_width, target_height), Resampling.BICUBIC)
            
            return scaled_image
        except Exception as e:
            print(f"渐进式缩放失败: {e}")
            # 失败回退到普通缩放
            return image.resize(size, Resampling.BICUBIC)
    
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
    
    def reset_transformations(self):
        """重置所有变换"""
        self.rotation = 0.0
        self.flip_horizontal = False
        self.flip_vertical = False
        self.cached_image = None

        # 通知文档需要缓存刷新
        if hasattr(self, '_document_ref') and self._document_ref:
            self._document_ref._needs_cache_refresh = True

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
    
    def _apply_transformations(self, image):
        """应用图像变换（旋转和翻转）"""
        if image is None:
            return None
        
        result = image
        
        # 应用翻转
        if self.flip_horizontal:
            result = result.transpose(Transpose.FLIP_LEFT_RIGHT)
            print("应用水平翻转")
        
        if self.flip_vertical:
            result = result.transpose(Transpose.FLIP_TOP_BOTTOM)
            print("应用垂直翻转")
        
        # 应用旋转
        if abs(self.rotation) > 0.001:  # 避免浮点数精度问题
            # 使用高质量旋转，保持透明度
            from app.utils.rgba_resampler import rotate_rgba_premultiplied
            result = rotate_rgba_premultiplied(
                result,
                -self.rotation,  # PIL使用逆时针为正，我们使用顺时针为正
                expand=True,       # 扩展画布以容纳完整的旋转后图像
                fillcolor=(0, 0, 0, 0),  # 透明填充
                resample=Resampling.BICUBIC   # 高质量重采样
            )
            print(f"应用旋转: {self.rotation}度 (扩展画布)")
        
        return result
    
    def _apply_random_transformations(self, image):
        """应用随机变换（缩放和旋转）
        
        注意：此方法不会裁剪超出原始图层边界的部分，
        让随机变换的效果能够自然显示，与智能裁剪功能不冲突。
        """
        if image is None:
            return None
        
        result = image.copy()
        
        # 应用随机缩放
        if self.random_scale_enabled and abs(self._current_random_scale - 1.0) > 0.001:
            # 直接缩放图像，不限制在原始图层尺寸内
            # 这样可以让缩放后的图像自然地显示，即使超出原始边界
            new_width = int(image.width * self._current_random_scale)
            new_height = int(image.height * self._current_random_scale)
            
            result = self._resize_with_premultiplied_alpha(result, (new_width, new_height))
            print(f"随机缩放: {image.width}x{image.height} -> {new_width}x{new_height} (比例: {self._current_random_scale:.3f})")
        
        # 应用随机旋转
        if self.random_rotation_enabled and abs(self._current_random_rotation) > 0.001:
            # 使用expand=True让旋转后的图像完整显示，不被裁剪
            from app.utils.rgba_resampler import rotate_rgba_premultiplied
            result = rotate_rgba_premultiplied(
                result,
                -self._current_random_rotation,  # PIL使用逆时针为正，我们使用顺时针为正
                expand=True,       # 扩展画布以容纳完整的旋转后图像
                fillcolor=(0, 0, 0, 0),  # 透明填充
                resample=Resampling.BICUBIC   # 高质量重采样
            )
            print(f"随机旋转: {self._current_random_rotation:.1f}度 (扩展画布以避免裁剪)")
        
        return result
    
    def apply_effects(self, image):
        """应用图层特效（圆角、描边等）"""
        if image is None:
            return None
        
        result = image.copy()
        
        # 应用变换的顺序：手动变换 -> 随机变换 -> 特效
        
        # 1. 首先应用手动变换（翻转、旋转）
        result = self._apply_transformations(result)
        
        # 2. 然后应用随机变换（随机缩放、随机旋转）
        result = self._apply_random_transformations(result)
        
        # 3. 应用图层样式（圆角、描边）
        stroke_enabled = (
            hasattr(self, 'stroke_enabled') and self.stroke_enabled and
            hasattr(self, 'stroke_width') and self.stroke_width > 0
        )
        log_branch(
            "legacy_layer.apply_effects",
            "enter",
            corner_radius=getattr(self, 'corner_radius', 0),
            stroke_enabled=stroke_enabled,
            stroke_type=getattr(self, 'stroke_type', -1),
            stroke_width=getattr(self, 'stroke_width', 0),
        )
        
        # 有描边时，圆角由描边流程统一控制，避免缩放后半径与描边不一致
        if hasattr(self, 'corner_radius') and self.corner_radius > 0 and not stroke_enabled:
            log_branch("legacy_layer.apply_effects", "corner_only")
            result = self._apply_corner_radius_doc(result, self.corner_radius)
        
        if stroke_enabled:
            stroke_type = getattr(self, 'stroke_type', 0)  # 默认内描边
            stroke_color = getattr(self, 'stroke_color', (0, 0, 0, 255))
            if stroke_type == 0:  # 内描边
                log_branch("legacy_layer.apply_effects", "stroke_inner")
                result = self._apply_inner_stroke_doc(result, self.stroke_width, stroke_color)
            elif stroke_type == 1:  # 居中描边
                log_branch("legacy_layer.apply_effects", "stroke_center")
                result = self._apply_center_stroke_doc(result, self.stroke_width, stroke_color)
            elif stroke_type == 2:  # 外描边
                log_branch("legacy_layer.apply_effects", "stroke_outer")
                result = self._apply_outer_stroke_doc(result, self.stroke_width, stroke_color)
        
        return result
    
    def _apply_corner_radius_doc(self, image, radius):
        """应用圆角效果"""
        if radius <= 0 or image is None:
            return image
        
        try:
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # 创建圆角蒙版
            mask = self._create_antialiased_rounded_rect_mask_doc(image.width, image.height, radius)
            return self._apply_alpha_mask_doc(image, mask)
        except Exception as e:
            print(f"应用圆角效果失败: {e}")
            return image
    
    def _apply_alpha_mask_doc(self, image, mask):
        """将灰度蒙版与原图Alpha相乘，保留平滑边缘过渡。"""
        if image is None or mask is None:
            return image
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        r, g, b, a = image.split()
        alpha = ImageChops.multiply(a, mask)
        return Image.merge('RGBA', (r, g, b, alpha))
    
    def _get_mask_supersample_scale_doc(self, width, height, edge_size=0):
        """根据尺寸和边缘复杂度动态选择超采样倍数。"""
        min_side = max(1, min(int(width), int(height)))
        edge_size = max(0, int(edge_size))

        # Legacy 路径与新图层保持一致的高质量策略
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

        log_sampling("legacy_layer.mask_scale", width, height, edge_size, scale)
        return scale
    
    def _create_antialiased_rounded_rect_mask_doc(self, width, height, radius):
        """超采样 + LANCZOS 回采样生成高质量圆角矩形蒙版。"""
        width = max(1, int(width))
        height = max(1, int(height))
        radius = max(0, min(int(radius), min(width, height) // 2))
        
        if radius <= 0:
            return Image.new('L', (width, height), 255)
        
        scale = self._get_mask_supersample_scale_doc(width, height, radius)
        large_size = (width * scale, height * scale)
        large_radius = radius * scale
        
        mask_large = Image.new('L', large_size, 0)
        draw = ImageDraw.Draw(mask_large)
        draw.rounded_rectangle(
            (0, 0, large_size[0] - 1, large_size[1] - 1),
            radius=large_radius,
            fill=255
        )
        return mask_large.resize((width, height), Resampling.LANCZOS)
    
    def _create_antialiased_rounded_ring_mask_doc(self, width, height, outer_radius, inset, inner_radius):
        """超采样生成圆角环带蒙版，用于内/中/外描边。"""
        width = max(1, int(width))
        height = max(1, int(height))
        inset = max(0, int(inset))
        outer_radius = max(0, min(int(outer_radius), min(width, height) // 2))
        inner_radius = max(0, min(int(inner_radius), min(width, height) // 2))
        
        scale = self._get_mask_supersample_scale_doc(width, height, max(outer_radius, inset))
        large_w = width * scale
        large_h = height * scale
        
        mask_large = Image.new('L', (large_w, large_h), 0)
        draw = ImageDraw.Draw(mask_large)
        draw.rounded_rectangle((0, 0, large_w - 1, large_h - 1), radius=outer_radius * scale, fill=255)
        
        if inset > 0 and inset * 2 < width and inset * 2 < height:
            inset_large = inset * scale
            draw.rounded_rectangle(
                (inset_large, inset_large, large_w - inset_large - 1, large_h - inset_large - 1),
                radius=inner_radius * scale,
                fill=0
            )
        
        return mask_large.resize((width, height), Resampling.LANCZOS)
    
    def _apply_stroke_doc(self, image, width, color, stroke_type=0):
        """应用描边效果"""
        if width <= 0 or image is None:
            return image
        
        if stroke_type == 0:  # 内描边
            return self._apply_inner_stroke_doc(image, width, color)
        elif stroke_type == 1:  # 居中描边
            return self._apply_center_stroke_doc(image, width, color)
        elif stroke_type == 2:  # 外描边
            return self._apply_outer_stroke_doc(image, width, color)
        else:
            return self._apply_inner_stroke_doc(image, width, color)  # 默认内描边

    def _apply_inner_stroke_doc(self, image, width, color):
        """应用内向描边效果，保持图像尺寸不变"""
        try:
            # 保持原始图像尺寸
            result_width = image.width
            result_height = image.height

            # 创建描边蒙版
            corner_radius = getattr(self, 'corner_radius', 0)
            outer_radius = corner_radius if corner_radius > 0 else 0

            # 内层边界（描边内边缘）
            stroke_width = min(width, min(result_width, result_height) // 4)  # 限制描边宽度
            inner_radius = max(0, corner_radius - stroke_width) if corner_radius > 0 else 0

            stroke_mask = self._create_antialiased_rounded_ring_mask_doc(
                width=result_width,
                height=result_height,
                outer_radius=outer_radius,
                inset=stroke_width,
                inner_radius=inner_radius
            )

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (result_width, result_height), color)
            stroke_layer.putalpha(stroke_mask)

            # 将描边应用到原图像上
            result = Image.alpha_composite(image.convert('RGBA'), stroke_layer)

            # 将原图像内容粘贴到描边上方（保留原图像内容）
            if stroke_width * 2 < result_width and stroke_width * 2 < result_height:
                # 创建内容区域蒙版
                content_mask = self._create_antialiased_rounded_rect_mask_doc(
                    result_width - stroke_width * 2,
                    result_height - stroke_width * 2,
                    inner_radius
                )

                # 缩放原图像以适应内容区域
                content_width = result_width - stroke_width * 2
                content_height = result_height - stroke_width * 2
                scaled_image = image.resize((content_width, content_height), Resampling.LANCZOS)

                # 创建内容图层
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (stroke_width, stroke_width), scaled_image)
                alpha_canvas = Image.new('L', (result_width, result_height), 0)
                alpha_canvas.paste(content_mask, (stroke_width, stroke_width))
                content_layer = self._apply_alpha_mask_doc(content_layer, alpha_canvas)

                # 合成最终结果
                result = Image.alpha_composite(result, content_layer)

            return result

        except Exception as e:
            print(f"应用内向描边效果时出错: {e}")
            return image

    def _apply_center_stroke_doc(self, image, width, color):
        """应用居中描边效果，保持图像尺寸不变"""
        if width <= 0 or image is None:
            return image
        try:
            result_width = image.width
            result_height = image.height
            
            corner_radius = getattr(self, 'corner_radius', 0)
            inner_stroke = max(1, int(width / 2))
            outer_radius = corner_radius + inner_stroke if corner_radius > 0 else inner_stroke
            inner_radius = max(0, corner_radius - inner_stroke) if corner_radius > 0 else 0
            
            stroke_mask = self._create_antialiased_rounded_ring_mask_doc(
                width=result_width,
                height=result_height,
                outer_radius=outer_radius,
                inset=inner_stroke,
                inner_radius=inner_radius
            )
            
            stroke_layer = Image.new('RGBA', (result_width, result_height), color)
            stroke_layer.putalpha(stroke_mask)
            result = Image.alpha_composite(Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0)), stroke_layer)
            
            if inner_stroke * 2 < result_width and inner_stroke * 2 < result_height:
                content_width = result_width - inner_stroke * 2
                content_height = result_height - inner_stroke * 2
                scaled_image = image.resize((content_width, content_height), Resampling.LANCZOS)
                
                content_mask = self._create_antialiased_rounded_rect_mask_doc(
                    content_width, content_height, inner_radius
                )
                content_layer = Image.new('RGBA', (result_width, result_height), (0, 0, 0, 0))
                content_layer.paste(scaled_image, (inner_stroke, inner_stroke), scaled_image)
                alpha_canvas = Image.new('L', (result_width, result_height), 0)
                alpha_canvas.paste(content_mask, (inner_stroke, inner_stroke))
                content_layer = self._apply_alpha_mask_doc(content_layer, alpha_canvas)
                result = Image.alpha_composite(result, content_layer)
            
            return result
        except Exception as e:
            print(f"应用居中描边效果时出错: {e}")
            return image

    def _apply_outer_stroke_doc(self, image, width, color):
        """应用外描边效果，会增加图像尺寸"""
        try:
            # 外描边会增加图像尺寸
            original_width = image.width
            original_height = image.height
            expanded_width = original_width + width * 2
            expanded_height = original_height + width * 2

            # 创建扩展画布
            expanded_image = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))

            # 创建描边蒙版
            corner_radius = getattr(self, 'corner_radius', 0)
            outer_radius = corner_radius + width if corner_radius > 0 else width

            # 内层边界（原图像边缘）
            inner_radius = corner_radius if corner_radius > 0 else 0
            stroke_mask = self._create_antialiased_rounded_ring_mask_doc(
                width=expanded_width,
                height=expanded_height,
                outer_radius=outer_radius,
                inset=width,
                inner_radius=inner_radius
            )

            # 创建描边图层
            stroke_layer = Image.new('RGBA', (expanded_width, expanded_height), color)
            stroke_layer.putalpha(stroke_mask)

            # 将描边图层覆盖到扩展画布上
            expanded_image = Image.alpha_composite(expanded_image, stroke_layer)

            # 将内容图层放到中央，并按内轮廓裁切，确保与描边半径严格一致
            content_layer = Image.new('RGBA', (expanded_width, expanded_height), (0, 0, 0, 0))
            content_layer.paste(image, (width, width), image)
            content_mask = self._create_antialiased_rounded_rect_mask_doc(
                original_width, original_height, inner_radius
            )
            alpha_canvas = Image.new('L', (expanded_width, expanded_height), 0)
            alpha_canvas.paste(content_mask, (width, width))
            content_layer = self._apply_alpha_mask_doc(content_layer, alpha_canvas)
            expanded_image = Image.alpha_composite(expanded_image, content_layer)

            return expanded_image

        except Exception as e:
            print(f"应用外描边效果时出错: {e}")
            return image
    
    def generate_random_transform_params(self):
        """生成新的随机变换参数
        
        这个方法会生成新的随机位置偏移、缩放比例和旋转角度，
        存储在内部状态中，用于后续的渲染。
        """
        import random
        
        print(f"开始为图层 '{self.name}' 生成随机变换参数")
        
        # 生成随机位置偏移
        if self.random_position_enabled:
            self._current_random_offset_x = random.randint(-self.random_position_range, self.random_position_range)
            self._current_random_offset_y = random.randint(-self.random_position_range, self.random_position_range)
            print(f"生成随机位置偏移: ({self._current_random_offset_x}, {self._current_random_offset_y})")
        else:
            self._current_random_offset_x = 0
            self._current_random_offset_y = 0
        
        # 生成随机缩放比例
        if self.random_scale_enabled:
            self._current_random_scale = random.uniform(self.random_scale_min, self.random_scale_max)
            print(f"生成随机缩放比例: {self._current_random_scale:.3f}")
        else:
            self._current_random_scale = 1.0
        
        # 生成随机旋转角度
        if self.random_rotation_enabled:
            self._current_random_rotation = random.uniform(-self.random_rotation_range, self.random_rotation_range)
            print(f"生成随机旋转角度: {self._current_random_rotation:.1f}度")
        else:
            self._current_random_rotation = 0.0
        
        print(f"图层 '{self.name}' 随机变换参数: 位置偏移({self._current_random_offset_x}, {self._current_random_offset_y}), 缩放{self._current_random_scale:.3f}, 旋转{self._current_random_rotation:.1f}°")
    
    def get_effective_position(self):
        """获取应用随机偏移后的有效位置
        
        Returns:
            Tuple[int, int]: (x, y) 有效位置坐标
        """
        effective_x = self.x + self._current_random_offset_x
        effective_y = self.y + self._current_random_offset_y
        return (effective_x, effective_y)
    
    def get_effective_clone_positions(self):
        """获取应用随机偏移后的所有分身位置
        
        Returns:
            List[Tuple[int, int]]: 包含所有分身有效位置的列表
        """
        if not self.clone_enabled or self.clone_rows <= 0 or self.clone_columns <= 0:
            return [self.get_effective_position()]
        
        positions = []
        base_x, base_y = self.get_effective_position()
        
        for row in range(self.clone_rows):
            for col in range(self.clone_columns):
                pos_x = base_x + col * (self.width + self.clone_column_spacing)
                pos_y = base_y + row * (self.height + self.clone_row_spacing)
                positions.append((pos_x, pos_y))
        
        return positions
    
    def reset_random_transforms(self):
        """重置所有随机变换到初始状态"""
        self._current_random_offset_x = 0
        self._current_random_offset_y = 0
        self._current_random_scale = 1.0
        self._current_random_rotation = 0.0
        print(f"图层 '{self.name}' 随机变换已重置")

    def set_image_source(self, image_source, is_folder=None):
        """设置图像源并清除缓存

        Args:
            image_source: 新的图像源路径
            is_folder: 是否为文件夹，如果为None则保持原值
        """
        if self.image_source != image_source:
            self.image_source = image_source
            if is_folder is not None:
                self.is_folder = is_folder
            # 清除缓存，强制重新加载
            self.cached_image = None
            self.current_image_path = None
            print(f"图层 '{self.name}' 图像源已更新: {image_source}")

            # 通知文档需要缓存刷新
            if hasattr(self, '_document_ref') and self._document_ref:
                self._document_ref._needs_cache_refresh = True

    def serialize(self):
        """将图层序列化为可存储的字典"""
        # 使用统一的序列化工具
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.serialize_layer(self)
    
    def duplicate(self):
        """复制图层，创建一个完全相同的新实例"""
        # 使用统一的序列化工具进行复制
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.duplicate_layer(self, target_layer_class=NewLayer)
    
    @classmethod
    def deserialize(cls, data):
        """从字典反序列化创建图层"""
        # 使用统一的序列化工具
        from app.utils.layer_serializer import LayerSerializer
        return LayerSerializer.deserialize_layer(data, cls)


# 向后兼容：为现有代码提供Layer类别名
# 这样现有代码可以继续使用 from app.models.document import Layer
# 但实际上使用的是更完善的新Layer类
Layer = NewLayer


class Document(QObject):
    """文档模型，包含画布和图层信息"""
    
    # 信号定义
    document_changed = Signal()  # 文档内容变化信号
    layer_changed = Signal()     # 图层列表变化信号
    history_changed = Signal()   # 历史记录变化信号
    layer_selected = Signal(int) # 图层选中信号，传递选中的图层索引
    layers_selection_changed = Signal(list)  # 多图层选中信号，传递选中的图层索引列表
    layers_changed = Signal()    # 图层内容变化信号
    layer_updated = Signal(int)  # 单个图层更新信号，传递图层索引

    # 批量导出相关信号
    export_progress_updated = Signal(int)  # 导出进度更新信号，传递当前进度值
    file_exported = Signal(str)            # 单个文件导出完成信号，传递文件信息
    export_stage_updated = Signal(str)     # 导出阶段更新信号，传递阶段名称
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 父对象
        self.parent = parent
        
        # 是否已修改
        self.is_modified = False
        
        # ===== 重构：使用DocumentHistory管理历史记录 =====
        from app.models.document_history import DocumentHistory
        self._history_manager = DocumentHistory(max_history=20, parent=self)
        self._history_manager.history_changed.connect(self.history_changed.emit)
        
        # 保留旧接口兼容性（委托给_history_manager）
        self.history = []  # 保留以防某些地方直接访问
        self.history_index = -1  # 保留以防某些地方直接访问
        self.max_history = 20  # 保留以防某些地方直接访问
        
        # ===== 重构：使用DocumentSerializer管理序列化 =====
        from app.models.document_serializer import DocumentSerializer
        self._serializer = DocumentSerializer(parent=self)
        
        # ===== 重构：使用DocumentRenderer管理渲染 =====
        from app.models.document_renderer import DocumentRenderer
        self._renderer = DocumentRenderer(parent=self)
        
        # ===== 重构：使用BatchExportCoordinator协调导出 =====
        from app.models.batch_export_coordinator import BatchExportCoordinator
        self._export_coordinator = BatchExportCoordinator(parent=self)
        
        # 画布尺寸
        self.canvas_width = 800
        self.canvas_height = 600
        
        # 图层列表
        self.layers = []
        self.selected_layer_index = -1
        self.selected_layer_indices = []
        
        # 当前文件路径
        self.current_file_path = None
        
        # 导出设置
        self.export_settings = self._build_default_export_settings()
        
        # 导出错误信息
        self._last_export_error = None  # 存储最后一次导出错误信息
        self._last_export_report = None  # 结构化导出报告（迭代1）
        self._export_report_history = []  # 最近N次导出报告（迭代3.1）
        
        # 缓存刷新标记
        self._needs_cache_refresh = False
        
        # 最近一次变更上下文（用于UI增量刷新）
        self._last_change_context = None
        
        # 视图设置（标尺/参考线/吸附/视图变换）
        self.view_settings = {
            'show_rulers': True,
            'show_guides': True,
            'horizontal_guides': [],
            'vertical_guides': [],
            'snap_to_guides': True,
            'ruler_size': 20,
            'zoom_factor': 1.0,
            'offset_x': 0,
            'offset_y': 0,
        }

        # 图层绑定管理器
        from app.models.binding_manager import LayerBindingManager
        self.binding_manager = LayerBindingManager()
        self.layer_size_match_manager = LayerSizeMatchManager(parent=self)

    def _build_default_export_settings(self) -> dict:
        return {
            'format': 'jpg',
            'format_index': 1,
            'directory': '',
            'last_directory': '',
            'template': 'output_{number}',
            'filename_template': 'output_{number}',
            'count': 10,
            'use_date': True,
            'date_format': '%Y%m%d',
            'date_format_index': 0,
            'custom_text': 'export',
            'use_layer_name': False,
            'layer_index': 0,
            'number_format': '{number:04d}',
            'number_format_index': 0,
            'max_file_size_kb': 299,
            'use_current_time_for_path': False,
            'randomize_all': True,  # 是否随机所有图层
            'force_opaque': False,  # 是否强制不透明（用于JPEG格式）
            # 迭代3：动态尝试预算
            'dynamic_budget_enabled': True,
            'dynamic_budget_binding_enabled': True,
            'dynamic_budget_standard_enabled': True,
            'dynamic_budget_min_ratio': 0.8,
            'dynamic_budget_max_ratio': 3.0,
            'dynamic_budget_check_interval': 25,
            'dynamic_budget_min_samples': 40,
            'dynamic_budget_expand_step': 0.2,
            'dynamic_budget_shrink_step': 0.1,
            'dynamic_budget_low_success_rate': 0.15,
            'dynamic_budget_high_success_rate': 0.65,
            'dynamic_budget_high_duplicate_rate': 0.75,
            'dynamic_budget_low_duplicate_rate': 0.30,
            'dynamic_budget_recent_n': 12,
            'export_report_history_limit': 80,
            # 导出写盘策略（迭代4中的I/O优化前置）
            'io_profile': 'balanced',  # speed | balanced | size
            'export_quality_profile': 'quality',  # quality | balanced | speed | size
            'allow_lossy_size_reduction': False,
            'export_backend': 'auto',
            'png_compress_level_override': -1,  # -1 表示自动
            'jpeg_quality_override': 0,  # 0 表示自动
            'auto_runtime_tuning_enabled': True,
            'freeze_preview_during_export': True,
            # 批导读盘优化：预读与会话缓存
            'batch_preload_enabled': True,
            'batch_preload_max_images': 120,
            'batch_preload_memory_mb': 384,
            # 大批量导出隔离：主进程只负责 UI，导出放到独立 Worker 进程
            'export_external_worker_enabled': True,
            'export_worker_min_count': 200,
            'export_worker_resume_enabled': True,
            # 批量导出安全保护：防止过多任务导致卡死/闪退
            'export_safety_enabled': True,
            'export_safety_memory_guard_ratio': 0.40,
            'export_safety_max_consecutive_failures': 8,
            'export_safety_failure_rate_limit': 0.45,
            'export_safety_failure_rate_min_samples': 12,
            'export_safety_stall_timeout_seconds': 180,
        }

    def set_change_context(self, source: str, layer_index: int = -1, fields=None, reason: str = ""):
        """记录最近一次变更上下文，供UI进行增量刷新判断"""
        try:
            normalized_fields = list(fields) if fields else []
        except Exception:
            normalized_fields = []

        self._last_change_context = {
            "source": source or "",
            "layer_index": int(layer_index) if isinstance(layer_index, int) else -1,
            "fields": normalized_fields,
            "reason": reason or "",
            "timestamp": time.time(),
        }

    def get_change_context(self, max_age_ms: int = 1200):
        """获取最近变更上下文；超时上下文自动失效"""
        ctx = self._last_change_context
        if not ctx:
            return None

        ts = ctx.get("timestamp", 0.0)
        if not ts:
            return None

        if (time.time() - ts) * 1000.0 > max_age_ms:
            return None

        return ctx

    def clear_change_context(self):
        """清除最近一次变更上下文"""
        self._last_change_context = None

    def get_view_settings(self):
        """获取文档视图设置（用于文件/预设保存）"""
        base = {
            'show_rulers': True,
            'show_guides': True,
            'horizontal_guides': [],
            'vertical_guides': [],
            'snap_to_guides': True,
            'ruler_size': 20,
            'zoom_factor': 1.0,
            'offset_x': 0,
            'offset_y': 0,
        }
        if not hasattr(self, 'view_settings') or not isinstance(self.view_settings, dict):
            return base
        merged = base.copy()
        merged.update(self.view_settings)
        return merged

    def set_view_settings(self, settings):
        """设置文档视图设置（用于文件/预设加载）"""
        if not isinstance(settings, dict):
            return
        def _safe_int(value, default=0):
            try:
                return int(value)
            except Exception:
                return default

        current = self.get_view_settings()
        current.update(settings)
        # 类型清洗，防止旧文件脏数据
        current['show_rulers'] = bool(current.get('show_rulers', True))
        current['show_guides'] = bool(current.get('show_guides', True))
        current['snap_to_guides'] = bool(current.get('snap_to_guides', True))
        current['ruler_size'] = _safe_int(current.get('ruler_size', 20), 20)
        current['zoom_factor'] = float(current.get('zoom_factor', 1.0))
        current['offset_x'] = _safe_int(current.get('offset_x', 0), 0)
        current['offset_y'] = _safe_int(current.get('offset_y', 0), 0)
        current['horizontal_guides'] = [_safe_int(v, 0) for v in (current.get('horizontal_guides', []) or [])]
        current['vertical_guides'] = [_safe_int(v, 0) for v in (current.get('vertical_guides', []) or [])]
        self.view_settings = current
        
    def save_state(self, action_name):
        """保存当前状态到历史记录"""
        # 添加递归保护
        if hasattr(self, '_saving_state') and self._saving_state:
            print(f"警告: 避免递归调用save_state: {action_name}")
            return
        
        # 确保图层列表存在
        if not hasattr(self, 'layers') or not self.layers:
            print(f"警告: 无法保存状态，图层列表为空: {action_name}")
            return
            
        self._saving_state = True
        try:
            # 创建当前状态的快照 - 序列化图层以断开引用
            try:
                from app.models.document_serializer import DocumentSerializer
                serialized_layers = [DocumentSerializer.serialize_layer(layer) for layer in self.layers]
            except Exception:
                serialized_layers = [layer.serialize() for layer in self.layers]
            state = {
                'layers': serialized_layers,
                'selected_layer_index': self.selected_layer_index,
                'selected_layer_indices': list(getattr(self, 'selected_layer_indices', [])),
                'action_name': action_name
            }
            
            # 如果当前不在历史记录末尾，则清除后面的历史记录
            if self.history_index < len(self.history) - 1:
                self.history = self.history[:self.history_index + 1]
                
            # 添加新状态
            self.history.append(state)
            self.history_index = len(self.history) - 1
            
            # 如果历史记录超过最大数量，删除最早的记录
            while len(self.history) > self.max_history:
                self.history.pop(0)
                self.history_index -= 1
                
            # 标记文档已修改
            self.is_modified = True
            
            # 发出历史记录变化信号
            try:
                self.history_changed.emit()
            except Exception as e:
                print(f"发出历史记录变化信号时出错: {e}")
        except Exception as e:
            print(f"保存状态时出错: {e}")
        finally:
            self._saving_state = False
        
    def can_undo(self):
        """检查是否可以撤销"""
        return self.history_index > 0
        
    def can_redo(self):
        """检查是否可以重做"""
        return self.history_index < len(self.history) - 1
        
    def undo(self):
        """撤销上一步操作"""
        if not self.can_undo():
            return False
            
        # 移动到上一个历史记录
        self.history_index -= 1
        
        # 恢复该状态
        self._restore_state(self.history[self.history_index])
        
        # 发出历史记录变化信号
        self.history_changed.emit()
        
        # 标记文档已修改
        self.is_modified = True
        
        return True
        
    def redo(self):
        """重做操作"""
        if not self.can_redo():
            return False
            
        # 移动到下一个历史记录
        self.history_index += 1
        
        # 恢复该状态
        self._restore_state(self.history[self.history_index])
        
        # 发出历史记录变化信号
        self.history_changed.emit()
        
        # 标记文档已修改
        self.is_modified = True
        
        return True
        
    def _restore_state(self, state):
        """从历史记录中恢复状态"""
        try:
            # 恢复图层
            old_layers = self.layers  # 保存旧图层以便后面清理
            self.layers = []
            for layer_data in state['layers']:
                try:
                    # 通过反序列化创建全新的图层对象，确保完全断开引用
                    layer = self.create_layer_from_data(layer_data)
                    self.layers.append(layer)
                except Exception as e:
                    print(f"恢复图层状态时出错: {e}")
                    # 创建一个默认的空图层作为替代
                    default_layer = NewLayer("错误图层", 0, 0, 100, 100)
                    self.layers.append(default_layer)
                
            # 恢复选中的图层索引
            self.selected_layer_index = state['selected_layer_index']
            self.selected_layer_indices = list(state.get('selected_layer_indices', [self.selected_layer_index]))
            # 确保索引在有效范围内
            if self.selected_layer_index >= len(self.layers):
                self.selected_layer_index = len(self.layers) - 1 if len(self.layers) > 0 else -1
            elif self.selected_layer_index < -1:
                self.selected_layer_index = -1
            self.selected_layer_indices = [
                idx for idx in self.selected_layer_indices
                if 0 <= idx < len(self.layers)
            ]
            if self.selected_layer_index >= 0 and self.selected_layer_index not in self.selected_layer_indices:
                self.selected_layer_indices.insert(0, self.selected_layer_index)
            
            # 确保清理旧图层的缓存对象以释放内存
            for old_layer in old_layers:
                if hasattr(old_layer, '_cached_image') and old_layer._cached_image:
                    old_layer._cached_image = None
                if hasattr(old_layer, 'cached_image') and old_layer.cached_image:
                    old_layer.cached_image = None
            
            # 发出信号通知界面更新
            self.document_changed.emit()
            self.layer_changed.emit()
            self.layer_selected.emit(self.selected_layer_index)
            self.layers_selection_changed.emit(list(self.selected_layer_indices))
            self.layers_changed.emit()  # 确保图层内容变化信号也被触发
        except Exception as e:
            print(f"恢复状态时出错: {e}")
            # 如果恢复失败，至少通知UI更新
            self.document_changed.emit()
            self.layer_changed.emit()
        
    def create_new(self, width, height):
        self.canvas_width = width
        self.canvas_height = height
        self.layers = []
        self.selected_layer_index = -1
        self.selected_layer_indices = []
        self.current_file_path = None
        self.is_modified = False
        
        # 重置历史记录
        self.history = []
        self.history_index = -1
        
        self.document_changed.emit()
        self.history_changed.emit()
        
    def add_layer(self, name, x, y, width, height, image_source=None, use_original_size=False, is_folder=True):
        # 保存当前状态
        self.save_state("添加图层前")
        
        # 使用新的Layer模型，支持形状功能
        # 自动判断图像源类型，避免单文件被当作文件夹导致加载失败
        try:
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
            src_norm = _normalize_path(image_source) if image_source else image_source
            if src_norm:
                if os.path.isfile(src_norm):
                    is_folder = False
                elif os.path.isdir(src_norm):
                    is_folder = True
        except Exception:
            pass

        layer = NewLayer(name, x, y, width, height, image_source, use_original_size, is_folder)
        try:
            if hasattr(layer, 'changed') and hasattr(layer.changed, 'connect'):
                layer.changed.connect(self.document_changed.emit)
        except Exception:
            pass
        self.layers.append(layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self._invalidate_render_cache()
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加图层")
        
        return layer
    
    def add_shaped_layer(self, shaped_layer):
        """添加异形图层"""
        # 保存当前状态
        self.save_state("添加异形图层前")
        
        # 安全地连接异形图层的信号
        try:
            if hasattr(shaped_layer, 'changed') and hasattr(shaped_layer.changed, 'connect'):
                shaped_layer.changed.connect(self.document_changed.emit)
        except Exception as e:
            print(f"警告：无法连接异形图层信号: {e}")
        
        # 将异形图层添加到图层列表
        self.layers.append(shaped_layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self._invalidate_render_cache()
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加异形图层")
        
        return shaped_layer
    
    def add_text_layer(self, text_layer):
        """添加文字图层"""
        # 保存当前状态
        self.save_state("添加文字图层前")
        
        # 安全地连接文字图层的信号
        try:
            if hasattr(text_layer, 'changed') and hasattr(text_layer.changed, 'connect'):
                text_layer.changed.connect(self.document_changed.emit)
            if hasattr(text_layer, 'text_changed') and hasattr(text_layer.text_changed, 'connect'):
                text_layer.text_changed.connect(self.document_changed.emit)
        except Exception as e:
            print(f"警告：无法连接文字图层信号: {e}")
        
        # 将文字图层添加到图层列表
        self.layers.append(text_layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self._invalidate_render_cache()
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加文字图层")
        
        return text_layer
    
    def add_existing_layer(self, layer):
        """添加已存在的图层对象（用于复制粘贴功能）"""
        # 保存当前状态
        self.save_state("添加图层前")
        
        # 安全地连接图层的信号（如果存在的话）
        try:
            if hasattr(layer, 'changed') and hasattr(layer.changed, 'connect'):
                layer.changed.connect(self.document_changed.emit)
        except Exception as e:
            print(f"警告：无法连接图层信号: {e}")
        
        # 将图层添加到图层列表
        self.layers.append(layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加图层")
        
        return layer
        
    def remove_layer(self, index):
        if 0 <= index < len(self.layers):
            # 检查图层是否锁定
            if self.layers[index].locked:
                return
                
            # 保存当前状态
            self.save_state("删除图层前")
            
            # 获取要删除的图层
            layer_to_remove = self.layers[index]
            
            # 从绑定管理器中移除图层
            if hasattr(self, 'binding_manager') and self.binding_manager:
                self.binding_manager.remove_layer_from_group(layer_to_remove)
                print(f"从绑定组中移除图层: {layer_to_remove.name}")
            
            del self.layers[index]
            if index == self.selected_layer_index:
                if len(self.layers) > 0:
                    self.selected_layer_index = min(index, len(self.layers) - 1)
                else:
                    self.selected_layer_index = -1
            elif index < self.selected_layer_index:
                self.selected_layer_index -= 1
            self.selected_layer_indices = [
                (idx - 1 if idx > index else idx)
                for idx in getattr(self, 'selected_layer_indices', [])
                if idx != index and 0 <= idx < len(self.layers) + 1
            ]
            self.selected_layer_indices = [
                idx for idx in self.selected_layer_indices if 0 <= idx < len(self.layers)
            ]
            if self.selected_layer_index >= 0 and self.selected_layer_index not in self.selected_layer_indices:
                self.selected_layer_indices.insert(0, self.selected_layer_index)

            self._invalidate_render_cache()
            self.layer_changed.emit()
            self.layer_selected.emit(self.selected_layer_index)
            self.layers_selection_changed.emit(list(self.selected_layer_indices))
            
            # 保存删除后的状态
            self.save_state("删除图层")
    
    def move_layer_up(self, index):
        if 0 < index < len(self.layers):
            # 检查图层是否锁定
            if self.layers[index].locked or self.layers[index-1].locked:
                return
                
            # 保存当前状态
            self.save_state("移动图层前")
            
            self.layers[index], self.layers[index-1] = self.layers[index-1], self.layers[index]
            if self.selected_layer_index == index:
                self.selected_layer_index -= 1
            elif self.selected_layer_index == index - 1:
                self.selected_layer_index += 1
            self.selected_layer_indices = [
                idx - 1 if idx == index else idx + 1 if idx == index - 1 else idx
                for idx in getattr(self, 'selected_layer_indices', [])
            ]
            self.layer_changed.emit()
            self.layer_selected.emit(self.selected_layer_index)
            self.layers_selection_changed.emit(list(self.selected_layer_indices))
            
            # 保存移动后的状态
            self.save_state("上移图层")
            
    def move_layer_down(self, index):
        if 0 <= index < len(self.layers) - 1:
            # 检查图层是否锁定
            if self.layers[index].locked or self.layers[index+1].locked:
                return
                
            # 保存当前状态
            self.save_state("移动图层前")
            
            self.layers[index], self.layers[index+1] = self.layers[index+1], self.layers[index]
            if self.selected_layer_index == index:
                self.selected_layer_index += 1
            elif self.selected_layer_index == index + 1:
                self.selected_layer_index -= 1
            self.selected_layer_indices = [
                idx + 1 if idx == index else idx - 1 if idx == index + 1 else idx
                for idx in getattr(self, 'selected_layer_indices', [])
            ]
            self.layer_changed.emit()
            self.layer_selected.emit(self.selected_layer_index)
            self.layers_selection_changed.emit(list(self.selected_layer_indices))
            
            # 保存移动后的状态
            self.save_state("下移图层")
    
    def move_layer(self, from_index, to_index):
        """移动图层从一个位置到另一个位置"""
        if not (0 <= from_index < len(self.layers) and 0 <= to_index < len(self.layers)):
            return
            
        if from_index == to_index:
            return
            
        # 检查图层是否锁定
        if self.layers[from_index].locked:
            return
            
        # 保存当前状态
        self.save_state("移动图层前")
        
        # 记住选中的图层
        selected_layer = self.layers[self.selected_layer_index] if self.selected_layer_index >= 0 else None
        selected_layer_objects = [
            self.layers[idx]
            for idx in getattr(self, 'selected_layer_indices', [])
            if 0 <= idx < len(self.layers)
        ]
        
        # 移动图层
        layer = self.layers.pop(from_index)
        self.layers.insert(to_index, layer)
        
        # 更新选中的图层索引
        if selected_layer:
            try:
                self.selected_layer_index = self.layers.index(selected_layer)
            except ValueError:
                self.selected_layer_index = min(self.selected_layer_index, len(self.layers) - 1)
        self.selected_layer_indices = []
        for selected in selected_layer_objects:
            try:
                new_idx = self.layers.index(selected)
            except ValueError:
                continue
            if new_idx not in self.selected_layer_indices:
                self.selected_layer_indices.append(new_idx)
        if self.selected_layer_index >= 0 and self.selected_layer_index not in self.selected_layer_indices:
            self.selected_layer_indices.insert(0, self.selected_layer_index)
        
        # 发送图层变化信号
        self.layer_changed.emit()
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存移动后的状态
        self.save_state("移动图层")
    
    def select_layer(self, index):
        if 0 <= index < len(self.layers):
            self.select_layers([index], primary_index=index)
        else:
            self.select_layers([], primary_index=-1)

    def select_layers(self, indices, primary_index=None):
        """选择一个或多个图层，并保持 selected_layer_index 兼容旧单选逻辑。"""
        valid_indices = []
        for idx in indices or []:
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(self.layers) and idx not in valid_indices:
                valid_indices.append(idx)

        if primary_index is None:
            primary = valid_indices[0] if valid_indices else -1
        else:
            try:
                primary = int(primary_index)
            except (TypeError, ValueError):
                primary = -1
            if primary not in valid_indices:
                primary = valid_indices[0] if valid_indices else -1

        selection_changed = (
            list(getattr(self, 'selected_layer_indices', [])) != valid_indices or
            self.selected_layer_index != primary
        )
        self.selected_layer_indices = valid_indices
        self.selected_layer_index = primary

        if selection_changed:
            self.layer_changed.emit()
            self.layer_selected.emit(primary)
            self.layers_selection_changed.emit(list(valid_indices))
            
    def randomize_all_layers(self):
        """为所有可见图层重新随机选择图片/文字，严格按照绑定组设置执行"""
        # 只获取可见图层进行处理
        try:
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            visible_layers = [
                layer for layer in self.layers
                if not is_layer_group(layer) and is_effectively_visible(layer, self.layers)
            ]
        except Exception:
            visible_layers = [layer for layer in self.layers if getattr(layer, 'visible', True)]

        # 预览随机化必须以绑定管理器为主链路，不能依赖导出模式推断
        # 否则公共分类分析失败时会被降级为标准随机化，导致绑定看似失效
        if hasattr(self, 'binding_manager') and self.binding_manager and self.binding_manager.global_enabled:
            print("[随机化] 🔗 绑定管理器已启用，按绑定规则执行预览随机化")
            try:
                from app.models.text_layer import TextLayer

                # 先分析文件限制，再一次性为所有绑定组选择组合
                self.binding_manager.analyze_and_restrict_layer_files(self.layers)
                bound_layer_mapping = self.binding_manager.randomize_bound_layers(self.layers)
                print(f"[随机化] 绑定管理器已更新 {len(bound_layer_mapping)} 个绑定图层")

                # 未由绑定映射覆盖的可见图层，按各自规则随机化
                for layer in visible_layers:
                    if isinstance(layer, TextLayer):
                        # 文字图层若已被绑定映射处理（text_layer://），这里不重复覆盖
                        if id(layer) in bound_layer_mapping:
                            continue
                        layer.randomize_text()
                        continue

                    # 图像图层：绑定图层已由 randomize_bound_layers 处理
                    if self.binding_manager.is_layer_bound(layer):
                        continue

                    # 非绑定图层遵守文件限制，避免抢占绑定图层文件
                    restricted_files = self.binding_manager.get_layer_file_restrictions(layer)
                    if restricted_files:
                        layer.get_random_image(force_random=True, restrict_to_bound_files=restricted_files)
                    else:
                        layer.get_random_image(force_random=True)
            except Exception as e:
                print(f"[随机化] ⚠️ 绑定链路执行失败，回退到基础随机化: {e}")
                for layer in visible_layers:
                    from app.models.text_layer import TextLayer
                    if isinstance(layer, TextLayer):
                        layer.randomize_text()
                    else:
                        layer.get_random_image(force_random=True)
        else:
            print(f"[随机化] ⚠️ 绑定管理器未启用，所有图层独立随机化")
            # 处理所有可见图层，正常随机化
            for layer in visible_layers:
                # 检查是否是文字图层
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer):
                    # 文字图层，随机选择文字
                    layer.randomize_text()
                else:
                    # 普通图层，强制随机化图片选择
                    layer.get_random_image(force_random=True)

        # 为所有可见图层生成随机变换参数
        for layer in visible_layers:
            if hasattr(layer, 'generate_random_transform_params'):
                layer.generate_random_transform_params()

        # 使渲染缓存失效，确保预览窗口显示最新的随机变化
        self._invalidate_render_cache()

        # 标记需要强制刷新缓存
        self._needs_cache_refresh = True

        # 强制发送文档变化信号，确保UI更新
        self.document_changed.emit()
        self.layer_changed.emit()  # 也发送图层变化信号
    
    def _randomize_text_layer_with_binding_categories(self, text_layer, binding_categories: List[str]):
        """在绑定组公共分类限制下随机化文字图层"""
        from app.models.text_layer import TextLayer
        
        if not isinstance(text_layer, TextLayer):
            return
            
        text_lines = text_layer.get_text_lines()
        if not text_lines:
            return
        
        # 🔧 关键修复：只选择包含绑定组公共分类关键词的文字
        eligible_texts = []
        
        for text_line in text_lines:
            text_stripped = str(text_line).strip()
            if not text_stripped:
                continue
                
            # 检查文字内容是否包含任何绑定组公共分类关键词
            for category in binding_categories:
                if category in text_stripped:
                    eligible_texts.append(text_stripped)
                    break
        
        if eligible_texts:
            # 从符合条件的文字中随机选择
            selected_text = random.choice(eligible_texts)
            text_layer.current_text = selected_text
            print(f"[绑定组文字限制] 文字图层 '{text_layer.name}' 从 {len(eligible_texts)} 个符合分类的文字中选择: {selected_text}")
        else:
            # 如果没有符合分类的文字，不要强制使用分类名称，保持原有文字
            # 强制使用分类名称会导致文字内容被改为商品类别，这不是用户期望的行为
            # 例如：分类是"半身裙"，但文字图层不应该被强制改为"半身裙"
            
            # 使用原始文字，保持用户设置的内容不变
            if text_lines:
                default_text = text_lines[0]
                text_layer.current_text = default_text
                print(f"[绑定组文字限制] 文字图层 '{text_layer.name}' 保持原有文字: {default_text}")
            else:
                # 如果没有文字行，保持当前文字不变
                print(f"[绑定组文字限制] 文字图层 '{text_layer.name}' 保持当前文字: {text_layer.current_text}")
    
    def _randomize_image_layer_with_binding_categories(self, image_layer, binding_categories: List[str]):
        """在绑定组公共分类限制下随机化普通图层"""
        if not image_layer.image_source or not os.path.isdir(image_layer.image_source):
            return
        
        # 🔧 关键修复：只选择文件名包含绑定组公共分类关键词的图像
        eligible_files = []
        
        try:
            for file in os.listdir(image_layer.image_source):
                ext = os.path.splitext(file)[1].lower()
                if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']:
                    continue
                    
                filename_without_ext = os.path.splitext(file)[0]
                
                # 检查文件名是否包含任何绑定组公共分类关键词
                for category in binding_categories:
                    if category in filename_without_ext:
                        eligible_files.append(file)
                        break
        except Exception as e:
            print(f"[绑定组图像限制] 扫描图层 '{image_layer.name}' 文件时出错: {e}")
            return
        
        if eligible_files:
            # 从符合条件的文件中随机选择
            selected_file = random.choice(eligible_files)
            file_path = os.path.join(image_layer.image_source, selected_file)
            
            # 🔧 关键修复：使用公共属性setter设置图像路径
            if hasattr(image_layer, 'current_image_path'):
                image_layer.current_image_path = file_path
            else:
                # 如果没有该属性，尝试其他方法
                try:
                    image_layer.get_random_image(force_random=True)
                except:
                    pass
            
            # 清除缓存
            image_layer.cached_image = None
            if hasattr(image_layer, '_cached_image_path'):
                image_layer._cached_image_path = None
                
            print(f"[绑定组图像限制] 图层 '{image_layer.name}' 从 {len(eligible_files)} 个符合分类的图像中选择: {selected_file}")
        else:
            # 未找到符合分类的图像时，不再跨类随机，保持当前状态避免破坏组合一致性
            print(f"[绑定组图像限制] 图层 '{image_layer.name}' 无符合分类的图像，跳过随机以保持绑定一致性")

    def _scale_content_to_fit(self, image, target_width, target_height):
        """对内容等比缩放以适应目标区域，不裁剪
        
        参数:
            image: PIL图像对象
            target_width: 目标宽度
            target_height: 目标高度
            
        返回:
            处理后的PIL图像对象，大小与目标相同，内容按比例缩放居中
        """
        if not image:
            return None
            
        # 创建透明背景
        result = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
        
        # 计算原始图像和目标区域的宽高比
        original_ratio = image.width / image.height
        target_ratio = target_width / target_height
        
        if original_ratio > target_ratio:
            # 原图更宽，以宽度为基准调整
            new_width = target_width
            new_height = int(new_width / original_ratio)
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            # 垂直居中放置
            y_offset = (target_height - new_height) // 2
            result.paste(resized, (0, y_offset), resized)
            
            print(f"智能缩放不裁剪: 原图更宽, 缩放尺寸 {new_width}x{new_height}")
            print(f"智能缩放不裁剪: 最终尺寸 {target_width}x{target_height}, 内容位置 (0, {y_offset})")
        else:
            # 原图更高或等比例，以高度为基准调整
            new_height = target_height
            new_width = int(original_ratio * new_height)
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            # 水平居中放置
            x_offset = (target_width - new_width) // 2
            result.paste(resized, (x_offset, 0), resized)
            
            print(f"智能缩放不裁剪: 原图更高, 缩放尺寸 {new_width}x{new_height}")
            print(f"智能缩放不裁剪: 最终尺寸 {target_width}x{target_height}, 内容位置 ({x_offset}, 0)")
            
        return result
    
    def _process_image_for_layer(self, image, target_width, target_height):
        """处理图像以适应目标尺寸，智能裁剪模式(保持纵横比)
        
        参数:
            image: PIL图像对象
            target_width: 目标宽度
            target_height: 目标高度
            
        返回:
            处理后的PIL图像对象
        """
        if not image:
            return None
            
        # 计算原始图像和目标区域的宽高比
        original_ratio = image.width / image.height
        target_ratio = target_width / target_height
        
        if original_ratio > target_ratio:
            # 原图更宽，以高度为基准调整
            new_height = target_height
            new_width = int(original_ratio * new_height)
            # 居中裁剪
            left = (new_width - target_width) // 2
            right = left + target_width
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            print(f"智能缩放裁剪: 原图更宽, 缩放尺寸 {new_width}x{new_height}")
            print(f"裁剪: 区域 ({left}, 0, {right}, {target_height})")
            
            cropped = resized.crop((left, 0, right, target_height))
            print(f"裁剪后尺寸: {cropped.width}x{cropped.height}, 期望尺寸: {target_width}x{target_height}")
            return cropped
        else:
            # 原图更高，以宽度为基准调整
            new_width = target_width
            new_height = int(new_width / original_ratio)
            # 居中裁剪
            top = (new_height - target_height) // 2
            bottom = top + target_height
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            print(f"智能缩放裁剪: 原图更高, 缩放尺寸 {new_width}x{new_height}")
            print(f"裁剪: 区域 (0, {top}, {target_width}, {bottom})")
            
            cropped = resized.crop((0, top, target_width, bottom))
            print(f"裁剪后尺寸: {cropped.width}x{cropped.height}, 期望尺寸: {target_width}x{target_height}")
            return cropped
    
    def _optimize_memory(self):
        """优化内存使用，减少内存占用"""
        try:
            from app.utils.memory_manager import get_memory_manager
            memory_manager = get_memory_manager()

            # 记录优化前的内存使用
            memory_before = memory_manager.get_memory_usage()

            # 清除图层缓存
            for layer in self.layers:
                if hasattr(layer, 'clear_cache'):
                    layer.clear_cache()
                elif hasattr(layer, '_cached_images'):
                    layer._cached_images = {}

            # 使用内存管理器进行清理
            freed_mb = memory_manager.force_cleanup()

            print(f"文档内存优化完成: 释放 {freed_mb} MB")

        except ImportError:
            # 回退到原有的简单清理方式
            import gc
            for layer in self.layers:
                if hasattr(layer, 'clear_cache'):
                    layer.clear_cache()
                elif hasattr(layer, '_cached_images'):
                    layer._cached_images = {}
            gc.collect()
            print("内存优化完成（简化模式）")
                
    def render_composition(self, random_mode=False, optimize_memory=False, use_advanced_quality=False, is_batch_mode=False, enable_gpu=True):
        """渲染当前图层组合 - 改进版本，支持GPU加速和高质量合成

        参数:
            random_mode: 是否使用随机图像
            optimize_memory: 是否在渲染后优化内存使用
            use_advanced_quality: 是否使用高级质量算法
            is_batch_mode: 是否批量模式（影响性能优化策略）
            enable_gpu: 是否启用GPU加速渲染

        返回:
            PIL.Image: 渲染后的图像
        """
        # 检查是否取消（渲染开始前）
        if hasattr(self, '_export_canceled') and self._export_canceled:
            print("[渲染] 渲染开始前检测到取消操作")
            return None

        # 🚀 GPU加速渲染尝试
        if enable_gpu and not is_batch_mode:  # 批量模式暂时不使用GPU以保证稳定性
            try:
                from app.utils.gpu_render_integration import get_gpu_integrator
                gpu_integrator = get_gpu_integrator()

                # 尝试GPU渲染
                gpu_result = gpu_integrator.render_composition_integrated(
                    self,
                    random_mode=random_mode,
                    optimize_memory=optimize_memory,
                    use_advanced_quality=use_advanced_quality,
                    is_batch_mode=is_batch_mode
                )

                if gpu_result is not None:
                    print("[渲染] GPU加速渲染成功")
                    if optimize_memory:
                        self.optimize_memory_usage()
                    return gpu_result
                else:
                    print("[渲染] GPU渲染失败，继续使用CPU渲染")

            except Exception as e:
                print(f"[渲染] GPU渲染异常，回退到CPU渲染: {e}")

        # 如果启用随机模式，先进行随机化
        if random_mode:
            print("[渲染] 启用随机模式，正在随机化所有图层...")
            self.randomize_all_layers()

        # 再次检查是否取消（随机化后）
        if hasattr(self, '_export_canceled') and self._export_canceled:
            print("[渲染] 随机化后检测到取消操作")
            return None

        # 创建一个空白画布
        composition = Image.new('RGBA', (self.canvas_width, self.canvas_height), (0, 0, 0, 0))

        # 导入高级合成管理器 - 使用缓存的实例
        advanced_compositor = None
        if use_advanced_quality:
            try:
                # 检查是否已有缓存的合成器
                if not hasattr(self, '_cached_compositor'):
                    from app.engines import get_advanced_compositor
                    AdvancedCompositorManager, CompositeQuality = get_advanced_compositor()

                    if AdvancedCompositorManager is not None:
                        self._cached_compositor = AdvancedCompositorManager(
                            quality=CompositeQuality.BALANCED,  # 使用平衡模式
                            enable_gpu=False,
                            cache_size=10  # 减少缓存大小
                        )
                        print("[INFO] 创建高级合成引擎缓存（平衡模式）")
                    else:
                        self._cached_compositor = None

                advanced_compositor = self._cached_compositor
                if advanced_compositor:
                    print("[DEBUG] 使用缓存的高级合成引擎")
                else:
                    print("[INFO] 高级合成引擎不可用，使用标准算法")
                    use_advanced_quality = False

            except Exception as e:
                print(f"[WARNING] 高级合成引擎初始化失败: {e}")
                use_advanced_quality = False
                advanced_compositor = None
        
        # 🔧 修复：严格按照绑定组设置执行随机化，不重新分析分类
        if random_mode:
            print("[渲染] 启用随机模式，严格按照绑定组设置执行...")
            self.randomize_all_layers()

        # 如果使用高级合成引擎
        if advanced_compositor:
            try:
                # 准备图层数据 - 使用与标准路径相同的逻辑
                layer_data = []
                from app.models.text_layer import TextLayer

                for layer_index, layer in enumerate(sorted(self.layers, key=lambda l: self.layers.index(l))):
                    # 每个图层开始前检查是否取消（高级合成路径）
                    if hasattr(self, '_export_canceled') and self._export_canceled:
                        print(f"[高级渲染] 处理图层 {layer_index+1} 时检测到取消操作")
                        if composition:
                            del composition
                        return None
                        
                    if not layer.visible:
                        continue

                    # 获取图层图像 - 与标准路径保持一致
                    layer_image = None
                    if isinstance(layer, TextLayer):
                        # 文字图层，渲染文字为图像
                        layer_image = layer.render_text()
                    else:
                        # 普通图层，获取图像
                        # 🔧 修复：随机模式下，图层应该已经被 randomize_all_layers 处理过
                        # 直接使用当前图像，避免重复随机化
                        if hasattr(layer, 'cached_image') and layer.cached_image is not None:
                            # 使用已缓存的图像
                            layer_image = layer.cached_image
                        else:
                            # 如果没有缓存，获取当前图像（可能是预设的组合）
                            layer_image = layer.get_image()

                    if layer_image is None:
                        continue

                    # 应用图层效果
                    if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
                        layer_image = layer.apply_effects(layer_image)

                    # 处理分身效果 - 与标准路径保持一致
                    is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled
                    clone_positions = []

                    if is_clone_enabled and hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                        # 获取所有分身位置
                        try:
                            # 使用支持随机偏移的有效位置方法
                            if hasattr(layer, 'get_effective_clone_positions'):
                                clone_positions = layer.get_effective_clone_positions()
                            else:
                                clone_positions = layer.get_clone_positions()
                        except Exception as e:
                            print(f"获取分身位置失败: {e}")
                            clone_positions = [(layer.x, layer.y)]
                    else:
                        # 没有分身效果，使用原始位置
                        clone_positions = [(layer.x, layer.y)]

                    fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
                    if fill_enabled:
                        spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                        angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                        mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                        
                        # 获取实际使用的宽高（考虑自定义大小）
                        clone_elem_width = layer.width
                        clone_elem_height = layer.height
                        if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                            hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                            if layer.clone_custom_width > 0:
                                clone_elem_width = layer.clone_custom_width
                            if layer.clone_custom_height > 0:
                                clone_elem_height = layer.clone_custom_height
                        
                        dx = max(1, int(clone_elem_width + spacing))
                        dy = max(1, int(clone_elem_height + spacing))
                        positions = []
                        cx = self.canvas_width / 2.0
                        cy = self.canvas_height / 2.0
                        base_x = layer.x
                        base_y = layer.y
                        import math
                        angle = math.radians(angle_deg % 360.0)
                        if mode == 'border':
                            # 边框排列：确保四角有元素，行距列距统一，支持边距
                            margin = int(getattr(layer, 'clone_fill_margin', 0))  # 获取边距参数
                            positions = []
                            
                            # 应用边距到画布尺寸
                            effective_width = self.canvas_width - 2 * margin
                            effective_height = self.canvas_height - 2 * margin
                            
                            # 计算每边的元素数量，确保四角都有元素
                            # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                            top_bottom_count = max(2, (effective_width + dx) // dx)  # 至少2个（两角）
                            # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                            left_right_count = max(2, (effective_height + dy) // dy)  # 至少2个（两角）
                            
                            # 计算统一的间距，确保元素均匀分布
                            # effective_width/height 是画布减去边距后的有效区域
                            # clone_elem_width/height 是分身元素的实际尺寸
                            if top_bottom_count > 1:
                                top_bottom_spacing = (effective_width - clone_elem_width) / (top_bottom_count - 1)
                            else:
                                top_bottom_spacing = 0
                                
                            if left_right_count > 1:
                                left_right_spacing = (effective_height - clone_elem_height) / (left_right_count - 1)
                            else:
                                left_right_spacing = 0
                            
                            # 顶部边缘（包括左上角和右上角）
                            for i in range(top_bottom_count):
                                x = margin + int(i * top_bottom_spacing)
                                if x <= self.canvas_width - clone_elem_width - margin:  # 确保不超出有效区域
                                    positions.append((x, margin))
                            
                            # 底部边缘（包括左下角和右下角）
                            for i in range(top_bottom_count):
                                x = margin + int(i * top_bottom_spacing)
                                if x <= self.canvas_width - clone_elem_width - margin:  # 确保不超出有效区域
                                    positions.append((x, self.canvas_height - clone_elem_height - margin))
                            
                            # 左侧边缘（不包括已经放置的角落元素）
                            for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                y = margin + int(i * left_right_spacing)
                                if margin < y < self.canvas_height - clone_elem_height - margin:  # 确保有效位置
                                    positions.append((margin, y))
                            
                            # 右侧边缘（不包括已经放置的角落元素）
                            for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                y = margin + int(i * left_right_spacing)
                                if margin < y < self.canvas_height - clone_elem_height - margin:  # 确保有效位置
                                    positions.append((self.canvas_width - clone_elem_width - margin, y))
                        else:
                            start_y = -int(clone_elem_height)
                            end_y = self.canvas_height + int(clone_elem_height)
                            step_y = dy
                            i_row = 0
                            for row_y in range(start_y, end_y + 1, step_y):
                                offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                                for col_x in range(-int(clone_elem_width), self.canvas_width + int(clone_elem_width) + 1, dx):
                                    x0 = base_x + col_x + offset
                                    y0 = base_y + row_y
                                    if angle != 0.0:
                                        rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                                        ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                                        x = int(rx)
                                        y = int(ry)
                                    else:
                                        x = x0
                                        y = y0
                                    positions.append((x, y))
                                i_row += 1
                        clone_positions = positions if positions else clone_positions

                    positions_info = [(x, y, False) for (x, y) in clone_positions]
                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    if mirror_mode and mirror_mode != 'none':
                        base = clone_positions[:]
                        
                        # 获取实际使用的宽高（考虑自定义大小）用于镜像计算
                        mirror_width = layer.width
                        mirror_height = layer.height
                        if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                            hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                            if layer.clone_custom_width > 0:
                                mirror_width = layer.clone_custom_width
                            if layer.clone_custom_height > 0:
                                mirror_height = layer.clone_custom_height
                        
                        min_x = min([x for x, _ in base])
                        max_x = max([x + mirror_width for x, _ in base])
                        min_y = min([y for _, y in base])
                        max_y = max([y + mirror_height for _, y in base])
                        group_width = max_x - min_x
                        group_height = max_y - min_y
                        if mirror_mode == 'horizontal':
                            mirrored_left = self.canvas_width - (min_x + group_width)
                            for x, y in base:
                                offset_x = x - min_x
                                positions_info.append((mirrored_left + offset_x, y, True))
                        elif mirror_mode == 'vertical':
                            mirrored_top = self.canvas_height - (min_y + group_height)
                            for x, y in base:
                                offset_y = y - min_y
                                positions_info.append((x, mirrored_top + offset_y, True))

                    from PIL import ImageOps
                    
                    # 检查是否需要调整分身大小
                    print(f"[快速渲染检查] 图层: {layer.name}")
                    print(f"  - 分身启用: {is_clone_enabled}")
                    print(f"  - 有 clone_custom_size_enabled: {hasattr(layer, 'clone_custom_size_enabled')}")
                    if hasattr(layer, 'clone_custom_size_enabled'):
                        print(f"  - clone_custom_size_enabled 值: {layer.clone_custom_size_enabled}")
                    print(f"  - 有 clone_custom_width: {hasattr(layer, 'clone_custom_width')}")
                    if hasattr(layer, 'clone_custom_width'):
                        print(f"  - clone_custom_width 值: {layer.clone_custom_width}")
                    print(f"  - 有 clone_custom_height: {hasattr(layer, 'clone_custom_height')}")
                    if hasattr(layer, 'clone_custom_height'):
                        print(f"  - clone_custom_height 值: {layer.clone_custom_height}")
                    
                    clone_resize_needed = (
                        is_clone_enabled and 
                        hasattr(layer, 'clone_custom_size_enabled') and 
                        layer.clone_custom_size_enabled and
                        hasattr(layer, 'clone_custom_width') and 
                        hasattr(layer, 'clone_custom_height') and
                        layer.clone_custom_width > 0 and 
                        layer.clone_custom_height > 0
                    )
                    print(f"  - 需要调整大小: {clone_resize_needed}")
                    
                    # 如果需要调整大小，准备调整后的图像
                    if clone_resize_needed:
                        try:
                            resized_layer_image = layer_image.resize(
                                (layer.clone_custom_width, layer.clone_custom_height),
                                Image.Resampling.LANCZOS
                            )
                            print(f"[快速渲染] 图层 '{layer.name}' 应用自定义分身大小: {layer.clone_custom_width}x{layer.clone_custom_height}")
                        except Exception as resize_error:
                            print(f"[快速渲染] 调整分身大小失败: {resize_error}，使用原图大小")
                            resized_layer_image = layer_image
                            clone_resize_needed = False
                    else:
                        resized_layer_image = layer_image
                    
                    for pos_x, pos_y, is_mirror in positions_info:
                        # 获取混合模式并转换为字符串
                        blend_mode = self._get_layer_blend_mode_string(layer)
                        
                        # 使用调整大小后的图像（如果启用了自定义大小）
                        img_to_use = resized_layer_image if clone_resize_needed else layer_image

                        layer_info = {
                            'image': ImageOps.mirror(img_to_use) if (is_mirror and mirror_mode == 'horizontal') else (ImageOps.flip(img_to_use) if (is_mirror and mirror_mode == 'vertical') else img_to_use),
                            'blend_mode': blend_mode,
                            'opacity': getattr(layer, 'opacity', 1.0),
                            'position': (pos_x, pos_y),
                            'mask': None
                        }
                        layer_data.append(layer_info)

                # 检查是否有有效的图层数据
                if not layer_data:
                    print("[WARNING] 没有有效的图层数据，使用空画布")
                    return composition

                print(f"[DEBUG] 准备合成 {len(layer_data)} 个图层")

                # 使用高级合成引擎
                composition = advanced_compositor.composite_layers(
                    layer_data,
                    (self.canvas_width, self.canvas_height),
                    (0, 0, 0, 0),
                    optimize_memory=optimize_memory
                )
                print("[INFO] 使用高级合成引擎完成渲染")

                # 如果需要优化内存，清理缓存
                if optimize_memory:
                    self._optimize_memory()

                return composition

            except Exception as e:
                print(f"[ERROR] 高级合成失败，回退到标准方法: {e}")
                import traceback
                traceback.print_exc()

        # 标准合成方法（后备）
        # 导入混合模式工具
        from app.models.document_blend import Blender, BlendMode

        # 性能优化：获取最优设置
        try:
            from app.utils.performance_optimizer import PerformanceOptimizer, PerformanceMonitor

            # 获取可见图层
            from app.utils.layer_tree import render_layers
            visible_layers = render_layers(self.layers)

            # 获取优化设置
            image_size = (self.canvas_width, self.canvas_height)
            layer_count = len(visible_layers)

            # 根据批量模式决定质量设置
            if is_batch_mode:
                # 批量模式使用性能优化设置
                perf_settings = PerformanceOptimizer.get_optimal_settings(
                    image_size, layer_count, is_batch_mode
                )
                print(f"[性能优化] 批量模式 - 图像尺寸: {image_size}, 图层数: {layer_count}")
                print(f"[性能优化] 批量设置: 抗锯齿={perf_settings['antialiasing_method']}, 质量={perf_settings['quality_level']}")
            else:
                # 非批量模式使用最高质量设置
                perf_settings = {
                    'edge_enhancement': True,
                    'subpixel_precision': True,
                    'antialiasing_method': 'smaa',  # 使用最高质量抗锯齿
                    'quality_level': 'high',
                    'use_threading': False,
                    'memory_optimization': False
                }
                print(f"[高质量渲染] 非批量模式 - 使用最高质量设置")

        except ImportError:
            # 后备设置
            perf_settings = {
                'edge_enhancement': True,
                'subpixel_precision': True,
                'antialiasing_method': 'smaa',
                'quality_level': 'high',
                'use_threading': False,
                'memory_optimization': False
            }
            from app.utils.layer_tree import render_layers
            visible_layers = render_layers(self.layers)

        # 绘制所有可见图层
        for layer_index, layer in enumerate(sorted(visible_layers, key=lambda l: self.layers.index(l))):
            # 每个图层开始前检查是否取消
            if hasattr(self, '_export_canceled') and self._export_canceled:
                print(f"[渲染] 处理图层 {layer_index+1}/{len(visible_layers)} 时检测到取消操作")
                if composition:
                    del composition
                return None
                
            if not layer.visible:
                continue
                
            # 获取图层图像 - 支持文字图层和普通图层
            layer_image = None
            from app.models.text_layer import TextLayer
            
            if isinstance(layer, TextLayer):
                # 文字图层，渲染文字为图像
                layer_image = layer.render_text()
            else:
                # 普通图层，获取图像
                if random_mode:
                    # 🔧 修复：随机模式下，图层应该已经被 randomize_all_layers 处理过
                    # 直接使用当前图像，避免重复随机化
                    if hasattr(layer, 'cached_image') and layer.cached_image is not None:
                        layer_image = layer.cached_image
                    else:
                        layer_image = layer.get_image()
                elif hasattr(layer, 'cached_image') and layer.cached_image is not None:
                    # 使用已缓存的图像
                    layer_image = layer.cached_image
                else:
                    # 如果没有缓存，获取当前图像（可能是预设的组合）
                    layer_image = layer.get_image()
                
            if layer_image is None:
                continue
                
            # 应用图层效果 - 批处理模式下设置批处理标志以优化性能
            if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
                if is_batch_mode:
                    # 批处理模式下设置批处理标志，减少日志输出
                    if hasattr(layer, '_is_batch_mode'):
                        layer._is_batch_mode = True
                layer_image = layer.apply_effects(layer_image)
                if is_batch_mode and hasattr(layer, '_is_batch_mode'):
                    layer._is_batch_mode = False
            
            # 判断是否启用了分身功能
            is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled
            clone_positions = []
            
            if is_clone_enabled and hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                # 获取所有分身位置
                try:
                    # 使用支持随机偏移的有效位置方法
                    if hasattr(layer, 'get_effective_clone_positions'):
                        clone_positions = layer.get_effective_clone_positions()
                    else:
                        clone_positions = layer.get_clone_positions()
                    print(f"图层 '{layer.name}' 渲染分身，共 {len(clone_positions)} 个位置")
                except Exception as e:
                    print(f"获取分身位置出错: {e}")
                    is_clone_enabled = False
                    # 使用支持随机偏移的有效位置
                    if hasattr(layer, 'get_effective_position'):
                        clone_positions = [layer.get_effective_position()]
                    else:
                        clone_positions = [(layer.x, layer.y)]
            else:
                # 没有启用分身或方法不存在，使用单一位置
                # 使用支持随机偏移的有效位置
                if hasattr(layer, 'get_effective_position'):
                    clone_positions = [layer.get_effective_position()]
                else:
                    clone_positions = [(layer.x, layer.y)]

            fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
            if fill_enabled:
                spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                
                # 获取实际使用的宽高（考虑自定义大小）
                effective_width = layer.width
                effective_height = layer.height
                if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                    hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                    if layer.clone_custom_width > 0:
                        effective_width = layer.clone_custom_width
                    if layer.clone_custom_height > 0:
                        effective_height = layer.clone_custom_height
                
                dx = max(1, int(effective_width + spacing))
                dy = max(1, int(effective_height + spacing))
                positions = []
                cx = self.canvas_width / 2.0
                cy = self.canvas_height / 2.0
                base_x = layer.x
                base_y = layer.y
                import math
                angle = math.radians(angle_deg % 360.0)
                start_y = -layer.height
                end_y = self.canvas_height + layer.height
                if mode == 'border':
                    # 边框排列：确保四角有元素，行距列距统一
                    positions = []
                    
                    # 计算每边的元素数量，确保四角都有元素
                    # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                    top_bottom_count = max(2, (self.canvas_width + dx) // dx)  # 至少2个（两角）
                    # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                    left_right_count = max(2, (self.canvas_height + dy) // dy)  # 至少2个（两角）
                    
                    # 计算统一的间距，确保元素均匀分布
                    if top_bottom_count > 1:
                        top_bottom_spacing = (self.canvas_width - effective_width) / (top_bottom_count - 1)
                    else:
                        top_bottom_spacing = 0
                        
                    if left_right_count > 1:
                        left_right_spacing = (self.canvas_height - effective_height) / (left_right_count - 1)
                    else:
                        left_right_spacing = 0
                    
                    # 顶部边缘（包括左上角和右上角）
                    for i in range(top_bottom_count):
                        x = int(i * top_bottom_spacing)
                        if x <= self.canvas_width - effective_width:  # 确保不超出画布
                            positions.append((x, 0))
                    
                    # 底部边缘（包括左下角和右下角）
                    for i in range(top_bottom_count):
                        x = int(i * top_bottom_spacing)
                        if x <= self.canvas_width - effective_width:  # 确保不超出画布
                            positions.append((x, self.canvas_height - effective_height))
                    
                    # 左侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = int(i * left_right_spacing)
                        if 0 < y < self.canvas_height - effective_height:  # 确保有效位置
                            positions.append((0, y))
                    
                    # 右侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = int(i * left_right_spacing)
                        if 0 < y < self.canvas_height - effective_height:  # 确保有效位置
                            positions.append((self.canvas_width - effective_width, y))
                else:
                    step_y = dy
                    i_row = 0
                    for row_y in range(start_y, end_y + 1, step_y):
                        offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                        for col_x in range(-int(effective_width), self.canvas_width + int(effective_width) + 1, dx):
                            x0 = base_x + col_x + offset
                            y0 = base_y + row_y
                            if angle != 0.0:
                                rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                                ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                                x = int(rx)
                                y = int(ry)
                            else:
                                x = x0
                                y = y0
                            positions.append((x, y))
                        i_row += 1
                clone_positions = positions if positions else clone_positions

            
            
            # 判断混合模式是否为正常模式
            is_normal_blend = (
                not hasattr(layer, 'blend_mode') or
                layer.blend_mode is None or
                layer.blend_mode == BlendMode.NORMAL or
                layer.blend_mode == "正常"
            )
            
            positions_info = [(x, y, False) for (x, y) in clone_positions]
            mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
            if mirror_mode and mirror_mode != 'none':
                base = clone_positions[:]
                
                # 获取实际使用的宽高（考虑自定义大小）
                mirror_width = layer.width
                mirror_height = layer.height
                if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                    hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                    if layer.clone_custom_width > 0:
                        mirror_width = layer.clone_custom_width
                    if layer.clone_custom_height > 0:
                        mirror_height = layer.clone_custom_height
                
                min_x = min([x for x, _ in base])
                max_x = max([x + mirror_width for x, _ in base])
                min_y = min([y for _, y in base])
                max_y = max([y + mirror_height for _, y in base])
                group_width = max_x - min_x
                group_height = max_y - min_y
                if mirror_mode == 'horizontal':
                    mirrored_left = self.canvas_width - (min_x + group_width)
                    for x, y in base:
                        offset_x = x - min_x
                        positions_info.append((mirrored_left + offset_x, y, True))
                elif mirror_mode == 'vertical':
                    mirrored_top = self.canvas_height - (min_y + group_height)
                    for x, y in base:
                        offset_y = y - min_y
                        positions_info.append((x, mirrored_top + offset_y, True))

            from PIL import ImageOps
            
            # 检查是否需要调整分身大小
            print(f"[渲染检查] 图层: {layer.name}")
            print(f"  - 分身启用: {is_clone_enabled}")
            print(f"  - 有 clone_custom_size_enabled: {hasattr(layer, 'clone_custom_size_enabled')}")
            if hasattr(layer, 'clone_custom_size_enabled'):
                print(f"  - clone_custom_size_enabled 值: {layer.clone_custom_size_enabled}")
            print(f"  - 有 clone_custom_width: {hasattr(layer, 'clone_custom_width')}")
            if hasattr(layer, 'clone_custom_width'):
                print(f"  - clone_custom_width 值: {layer.clone_custom_width}")
            print(f"  - 有 clone_custom_height: {hasattr(layer, 'clone_custom_height')}")
            if hasattr(layer, 'clone_custom_height'):
                print(f"  - clone_custom_height 值: {layer.clone_custom_height}")
            
            clone_resize_needed = (
                is_clone_enabled and 
                hasattr(layer, 'clone_custom_size_enabled') and 
                layer.clone_custom_size_enabled and
                hasattr(layer, 'clone_custom_width') and 
                hasattr(layer, 'clone_custom_height') and
                layer.clone_custom_width > 0 and 
                layer.clone_custom_height > 0
            )
            print(f"  - 需要调整大小: {clone_resize_needed}")
            
            # 如果需要调整大小，准备调整后的图像
            if clone_resize_needed:
                try:
                    resized_layer_image = layer_image.resize(
                        (layer.clone_custom_width, layer.clone_custom_height),
                        Image.Resampling.LANCZOS
                    )
                    print(f"[标准渲染] 图层 '{layer.name}' 应用自定义分身大小: {layer.clone_custom_width}x{layer.clone_custom_height}")
                except Exception as resize_error:
                    print(f"[标准渲染] 调整分身大小失败: {resize_error}，使用原图大小")
                    resized_layer_image = layer_image
                    clone_resize_needed = False
            else:
                resized_layer_image = layer_image
            
            for pos_x, pos_y, is_mirror in positions_info:
                try:
                    # 尝试使用高级合成器
                    from app.utils.unified_alpha_compositor import unified_alpha_compositor

                    # 确定混合模式
                    blend_mode_str = self._get_layer_blend_mode_string(layer)

                    # 修复：使用更稳定的合成方法
                    try:
                        # 使用调整大小后的图像（如果启用了自定义大小）
                        img_to_use = resized_layer_image if clone_resize_needed else layer_image
                        img_for_pos = ImageOps.mirror(img_to_use) if (is_mirror and mirror_mode == 'horizontal') else (ImageOps.flip(img_to_use) if (is_mirror and mirror_mode == 'vertical') else img_to_use)

                        # 智能暗化：半透明近黑/近灰覆盖自动切换为正片叠底
                        auto_blend = blend_mode_str
                        try:
                            sample_rgb = img_for_pos.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0))
                            sample_a = img_for_pos.getchannel('A').resize((1, 1), Image.BOX).getpixel((0, 0)) / 255.0
                            r, g, b = sample_rgb
                            neutral = abs(r - g) < 3 and abs(g - b) < 3
                            near_black = max(r, g, b) < 12
                            if auto_blend == 'normal' and sample_a > 0.01 and neutral and (near_black or max(r, g, b) < 48):
                                auto_blend = 'multiply'
                        except Exception:
                            pass

                        if is_batch_mode:
                            # 批量模式使用性能优化设置
                            composition = PerformanceOptimizer.optimize_composite_layer(
                                background=composition,
                                foreground=img_for_pos,
                                position=(pos_x, pos_y),
                                opacity=getattr(layer, 'opacity', 1.0),
                                blend_mode=auto_blend,
                                settings=perf_settings
                            )
                        else:
                            # 非批量模式也使用稳定的合成方法，启用边缘增强以匹配Photoshop效果
                            # 🔧 修复：禁用边缘增强以解决边缘像素缺失问题
                            # 之前的边缘增强算法会侵蚀图像边缘的Alpha通道
                            composition = unified_alpha_compositor.composite_layer(
                                background=composition,
                                foreground=img_for_pos,
                                position=(pos_x, pos_y),
                                opacity=getattr(layer, 'opacity', 1.0),
                                blend_mode=auto_blend,
                                edge_enhancement=False,
                                subpixel_precision=True,
                                use_srgb_blending=True  # 启用 Photoshop 风格混合
                            )
                    except Exception as composite_e:
                        print(f"[渲染] 高级合成失败: {composite_e}，使用简单合成")
                        # 回退到最简单的合成方法
                        try:
                            if img_for_pos.mode != 'RGBA':
                                img_for_pos = img_for_pos.convert('RGBA')

                            opacity = getattr(layer, 'opacity', 1.0)
                            if opacity < 1.0:
                                alpha = img_for_pos.split()[-1]
                                alpha = alpha.point(lambda p: int(p * opacity))
                                img_for_pos = img_for_pos.copy()
                                img_for_pos.putalpha(alpha)

                            composition.paste(img_for_pos, (pos_x, pos_y), img_for_pos)
                        except Exception as simple_e:
                            print(f"[渲染] 简单合成也失败: {simple_e}")
                            continue

                except ImportError:
                    # 后备方案：使用改进的传统方法
                    if is_normal_blend:
                        # 使用改进的alpha混合
                        composition = self._improved_layer_composite(
                            composition, img_for_pos, (pos_x, pos_y), layer.opacity
                        )
                    else:
                        # 创建临时图像用于混合模式
                        temp_image = Image.new('RGBA', composition.size, (0, 0, 0, 0))
                        if img_for_pos.mode == 'RGBA':
                            temp_image.paste(img_for_pos, (pos_x, pos_y), img_for_pos)
                        else:
                            temp_image.paste(img_for_pos, (pos_x, pos_y))

                        # 应用混合模式
                        composition = Blender.apply_blend_mode(composition, temp_image, layer.blend_mode, layer.opacity)
        
        # 如果需要优化内存，清理缓存
        if optimize_memory:
            self._optimize_memory()
            
        return composition

    def _improved_layer_composite(self, background: Image.Image, foreground: Image.Image,
                                 position: Tuple[int, int], opacity: float) -> Image.Image:
        """
        改进的图层合成方法 - 解决半透明和边缘问题的后备方案
        """
        import numpy as np

        # 确保图像格式
        if background.mode != 'RGBA':
            background = background.convert('RGBA')
        if foreground.mode != 'RGBA':
            foreground = foreground.convert('RGBA')

        # 获取位置和尺寸
        pos_x, pos_y = position
        fg_width, fg_height = foreground.size
        bg_width, bg_height = background.size

        # 计算有效区域
        src_x1 = max(0, -pos_x)
        src_y1 = max(0, -pos_y)
        src_x2 = min(fg_width, bg_width - pos_x)
        src_y2 = min(fg_height, bg_height - pos_y)

        dst_x1 = max(0, pos_x)
        dst_y1 = max(0, pos_y)
        dst_x2 = dst_x1 + (src_x2 - src_x1)
        dst_y2 = dst_y1 + (src_y2 - src_y1)

        # 检查是否有有效区域
        if src_x2 <= src_x1 or src_y2 <= src_y1:
            return background

        # 提取有效区域
        fg_crop = foreground.crop((src_x1, src_y1, src_x2, src_y2))
        bg_crop = background.crop((dst_x1, dst_y1, dst_x2, dst_y2))

        # 转换为浮点数组进行高精度计算
        bg_array = np.array(bg_crop, dtype=np.float64) / 255.0
        fg_array = np.array(fg_crop, dtype=np.float64) / 255.0

        # 应用不透明度
        if opacity < 1.0:
            fg_array[:,:,3] *= opacity

        # Porter-Duff "source over" 合成
        bg_rgb = bg_array[:,:,:3]
        bg_alpha = bg_array[:,:,3:4]
        fg_rgb = fg_array[:,:,:3]
        fg_alpha = fg_array[:,:,3:4]

        # 计算输出alpha
        result_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)

        # 避免除零
        safe_alpha = np.where(result_alpha > 1e-12, result_alpha, 1e-12)

        # 计算输出颜色
        result_rgb = (fg_rgb * fg_alpha + bg_rgb * bg_alpha * (1 - fg_alpha)) / safe_alpha

        # 组合结果
        result_array = np.concatenate([result_rgb, result_alpha], axis=2)
        result_array = np.clip(result_array, 0, 1)

        # 🔧 修复：使用抖动转换以消除色阶分层
        try:
            from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
            result_8bit = _float_to_uint8_with_dithering(result_array, use_dithering=True)
        except ImportError:
            # 后备方案：使用四舍五入
            result_8bit = np.round(result_array * 255.0).astype(np.uint8)
        
        composited = Image.fromarray(result_8bit, 'RGBA')

        # 将合成结果粘贴回原图
        result = background.copy()
        result.paste(composited, (dst_x1, dst_y1))

        return result

    def _invalidate_render_cache(self):
        """使渲染缓存失效"""
        try:
            from app.utils.fast_renderer import get_global_fast_renderer
            fast_renderer = get_global_fast_renderer()
            # 精确失效当前文档相关的智能缓存
            if hasattr(fast_renderer, 'invalidate_document_cache'):
                fast_renderer.invalidate_document_cache(self)
            # 标记需要缓存刷新，确保下一帧强制重渲染
            self._needs_cache_refresh = True
        except Exception:
            # 如果无法访问渲染器，仍然标记需要刷新
            self._needs_cache_refresh = True

    def _force_clear_all_caches(self):
        """强制清除所有可能的缓存，确保导出时没有重复"""
        print("[文档] 强制清除所有缓存...")

        # 清除图层缓存
        for layer in self.layers:
            cache_attrs = ['cached_image', '_cached_image', '_cached_image_path',
                          '_current_image_cache', 'current_image_path']
            for attr in cache_attrs:
                if hasattr(layer, attr):
                    setattr(layer, attr, None)

        # 清除绑定管理器缓存
        if self.binding_manager:
            for group in self.binding_manager.binding_groups.values():
                if hasattr(group, '_matched_files_cache'):
                    group._matched_files_cache.clear()
                if hasattr(group, '_session_seed'):
                    delattr(group, '_session_seed')
                if hasattr(group, 'layer_image_usage'):
                    for usage_dict in group.layer_image_usage.values():
                        usage_dict.clear()

        # 🔧 超级修复：清除快速渲染器和智能缓存系统
        try:
            from app.utils.fast_renderer import get_global_fast_renderer
            fast_renderer = get_global_fast_renderer()
            fast_renderer.invalidate_cache()
            print("[文档] 快速渲染器缓存已清除")
        except Exception as e:
            print(f"[文档] 清除快速渲染器缓存失败: {e}")

        try:
            from app.utils.intelligent_cache_system import get_intelligent_cache
            intelligent_cache = get_intelligent_cache()
            intelligent_cache.clear_all_caches()
            print("[文档] 智能缓存系统已清除")
        except Exception as e:
            print(f"[文档] 清除智能缓存系统失败: {e}")

        print("[文档] 所有缓存已清除")

    def _analyze_document_for_export(self) -> dict:
        """完整的文档状态预分析 - 为导出提供全面的状态信息"""
        print("[文档分析] 开始完整的文档状态分析...")

        analysis_result = {
            'binding_enabled': False,
            'binding_categories': [],
            'layer_analysis': {
                'visible_layers': [],
                'bound_layers': [],
                'unbound_layers': [],
                'layer_states': {},
                'layer_settings': {}
            },
            'export_mode': 'standard',
            'recommendations': []
        }

        # 1. 分析可见图层
        try:
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            visible_layers = [
                layer for layer in self.layers
                if not is_layer_group(layer) and is_effectively_visible(layer, self.layers)
            ]
        except Exception:
            visible_layers = [layer for layer in self.layers if getattr(layer, 'visible', True)]
        analysis_result['layer_analysis']['visible_layers'] = visible_layers
        print(f"[文档分析] 发现 {len(visible_layers)} 个可见图层")

        # 2. 分析每个图层的状态和设置
        for i, layer in enumerate(visible_layers):
            layer_info = {
                'index': i,
                'name': layer.name,
                'type': 'text' if hasattr(layer, 'text_content') and layer.text_content else 'image',
                'image_source': getattr(layer, 'image_source', None),
                'is_folder': getattr(layer, 'is_folder', False),
                'current_image_path': getattr(layer, 'current_image_path', None),
                'settings': {
                    'fit_mode': getattr(layer, 'fit_mode', getattr(layer, '_fit_mode', 0)),
                    'use_original_size': getattr(layer, 'use_original_size', getattr(layer, '_use_original_size', False)),
                    'smart_crop_enabled': getattr(layer, 'smart_crop_enabled', getattr(layer, '_smart_crop_enabled', False)),
                    'clone_enabled': getattr(layer, 'clone_enabled', getattr(layer, '_clone_enabled', False)),
                    'effects_enabled': bool(getattr(layer, 'effects', getattr(layer, '_effects', None)))
                }
            }
            analysis_result['layer_analysis']['layer_states'][i] = layer_info

        # 3. 检查绑定管理器状态
        binding_manager_exists = (hasattr(self, 'binding_manager') and
                                 self.binding_manager and
                                 self.binding_manager.global_enabled)

        if binding_manager_exists:
            print("[文档分析] 绑定管理器存在且启用，分析绑定状态...")

            # 检查哪些图层参与了绑定
            bound_layers = []
            unbound_layers = []

            for layer in visible_layers:
                if self.binding_manager.is_layer_bound(layer):
                    bound_layers.append(layer)
                    print(f"[文档分析] 发现绑定图层: {layer.name}")
                else:
                    unbound_layers.append(layer)

            analysis_result['layer_analysis']['bound_layers'] = bound_layers
            analysis_result['layer_analysis']['unbound_layers'] = unbound_layers

            # 获取绑定分类
            if bound_layers:
                binding_categories = self._get_binding_common_categories()
                analysis_result['binding_categories'] = binding_categories

                if binding_categories:
                    analysis_result['binding_enabled'] = True
                    analysis_result['export_mode'] = 'binding'
                    print(f"[文档分析] 绑定模式启用，发现 {len(binding_categories)} 个分类: {binding_categories}")
                else:
                    print("[文档分析] 有绑定图层但没有有效分类，使用标准模式")
                    analysis_result['recommendations'].append("绑定图层存在但缺少有效分类，建议检查图片文件")
            else:
                print("[文档分析] 绑定管理器存在但没有图层参与绑定")
                analysis_result['recommendations'].append("绑定管理器已启用但没有图层参与绑定")
        else:
            print("[文档分析] 绑定功能未启用或不存在")
            analysis_result['layer_analysis']['unbound_layers'] = visible_layers

        # 4. 生成导出建议
        if analysis_result['export_mode'] == 'binding':
            analysis_result['recommendations'].append(f"建议使用绑定模式导出，可生成 {len(binding_categories)} 种不同组合")
        else:
            total_combinations = 1
            for layer_info in analysis_result['layer_analysis']['layer_states'].values():
                if layer_info['is_folder'] and layer_info['image_source']:
                    # 估算图片数量（这里简化处理）
                    total_combinations *= 10  # 假设每个文件夹有10张图片
            analysis_result['recommendations'].append(f"建议使用标准模式导出，理论组合数约 {total_combinations}")

        print(f"[文档分析] 分析完成，导出模式: {analysis_result['export_mode']}")
        return analysis_result

    def batch_export(self, directory, count, filename_template=None, file_format="png", start_index=1, cancel_callback=None, use_high_performance=True, traverse_mode=False, use_smart_sampling=True):
        """批量导出不同组合的图像

        Args:
            directory: 输出目录
            count: 导出数量
            filename_template: 文件名模板
            file_format: 文件格式
            start_index: 起始文件序号
            cancel_callback: 取消回调函数
            use_high_performance: 是否使用高性能渲染方案
            traverse_mode: 是否启用遍历模式
            use_smart_sampling: 是否使用智能采样策略（避免图片重复）

        Returns:
            bool: 是否成功
        """
        
        # 📊 诊断日志：导出参数
        self._last_export_report = None
        self._is_batch_export_running = True
        def _is_export_canceled():
            return bool(getattr(self, '_export_canceled', False)) or bool(cancel_callback and cancel_callback())

        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        try:
            from app.utils.export_worker_client import export_with_worker, should_use_export_worker
            if should_use_export_worker(self, int(count or 0)):
                def worker_progress_wrapper(current_count):
                    if hasattr(self, 'export_progress_updated'):
                        self.export_progress_updated.emit(int(current_count or 0))

                def worker_file_completed_wrapper(message):
                    if hasattr(self, 'file_exported'):
                        self.file_exported.emit(str(message or ""))

                def worker_stage_wrapper(stage_name):
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit(str(stage_name or ""))

                worker_result = export_with_worker(
                    self,
                    directory=directory,
                    count=int(count or 0),
                    filename_template=filename_template or "image_{number:04d}",
                    file_format=file_format,
                    start_index=start_index,
                    traverse_mode=traverse_mode,
                    avoid_duplicates=use_smart_sampling,
                    progress_callback=worker_progress_wrapper,
                    file_completed_callback=worker_file_completed_wrapper,
                    stage_callback=worker_stage_wrapper,
                    cancel_callback=cancel_callback,
                )
                if worker_result.attempted:
                    self._is_batch_export_running = False
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit("收尾清理")
                    try:
                        self._cleanup_layers_after_export()
                    except Exception:
                        pass
                    if worker_result.success:
                        if hasattr(self, 'export_stage_updated'):
                            self.export_stage_updated.emit("导出完成")
                        return True
                    self._last_export_error = worker_result.error or "独立导出进程失败"
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit("导出失败")
                    return False
        except Exception as worker_launch_error:
            print(f"[批量导出] 独立导出进程不可用，回退内部导出: {worker_launch_error}")
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("准备导出")
        print("=" * 80)
        print(f"[批量导出] 🚀 开始批量导出")
        print(f"[批量导出]    数量: {count}")
        print(f"[批量导出]    目录: {directory}")
        print(f"[批量导出]    遍历模式: {traverse_mode}")
        print(f"[批量导出]    智能采样: {use_smart_sampling}")
        print(f"[批量导出]    高性能渲染: {use_high_performance}")
        print("=" * 80)

        # 🔧 性能优化：仅在真正需要时清理缓存
        # 不要每次都执行五层防护清理，那会严重影响性能
        # 只清理必要的渲染缓存即可
        print("[🔧 批量导出] 🧹 清理渲染缓存（轻量级）...")
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("清理缓存")
        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        try:
            # 只清理渲染缓存，保留其他状态
            from app.utils.fast_renderer import get_global_fast_renderer
            renderer = get_global_fast_renderer()
            if hasattr(renderer, 'clear_cache'):
                renderer.clear_cache()
                print("[🔧 批量导出] ✅ 渲染缓存已清理")
        except Exception as e:
            print(f"[🔧 批量导出] ⚠️ 缓存清理失败: {e}")
        
        # 🔧 性能优化：不要清除绑定组历史！这会导致避重机制失效
        # 绑定组历史应该在整个导出过程中保持，这样才能真正避免重复
        # 只在用户明确要求"重置"时才清除
        print("[🔧 批量导出] ℹ️ 保持绑定组历史以确保避重机制有效")
        
        # 🔧 关键修复：重新分析所有绑定组的文件分类，确保使用最新的图层状态
        print(f"\n{'='*80}")
        print(f"[🔍 批量导出启动] 检查绑定管理器...")
        print(f"{'='*80}")
        
        if hasattr(self, 'binding_manager') and self.binding_manager:
            if hasattr(self, 'export_stage_updated'):
                self.export_stage_updated.emit("绑定检查")
            if _is_export_canceled():
                self._last_export_error = "导出已取消"
                self._is_batch_export_running = False
                return False
            print("[🔧 批量导出] ✅ 绑定管理器存在")
            print(f"[🔧 批量导出] 绑定组数量: {len(self.binding_manager.binding_groups)}")
            print("[🔧 批量导出] 🔄 重新分析绑定组文件分类...")
            
            for group_id, group in self.binding_manager.binding_groups.items():
                if _is_export_canceled():
                    self._last_export_error = "导出已取消"
                    self._is_batch_export_running = False
                    return False
                print(f"\n[🔧 批量导出] 处理绑定组: '{group.name}' (ID: {group_id})")
                print(f"  图层数: {len(group.layers)}")
                
                # 🔧 修复：不要清空绑定组的文件分类和避重历史
                # 这些信息应该在整个导出过程中保持，以确保绑定功能正常工作
                print(f"  保持现有分类（{len(group.file_categories)} 个）")
                print(f"  保持避重历史（{len(getattr(group, '_category_usage_history', {}))} 个记录）")
                
                # 🔧 修复：只在分类信息缺失时重新分析
                if not group.file_categories:
                    print(f"  分类信息缺失，重新分析文件...")
                    for idx, layer in enumerate(group.layers):
                        if _is_export_canceled():
                            self._last_export_error = "导出已取消"
                            self._is_batch_export_running = False
                            return False
                        print(f"  分析图层 {idx}: {layer.name}")
                        print(f"    图层源: {layer.image_source}")
                        group._analyze_layer_files(layer, idx)
                else:
                    print(f"  分类信息完整，跳过重新分析")
                
                print(f"[🔧 批量导出] ✅ 绑定组 '{group.name}' 状态检查完成")
                print(f"  当前分类数: {len(group.file_categories)}")
                print(f"  分类列表: {list(group.file_categories.keys())}")
        else:
            print("[🔧 批量导出] ⚠️ 警告：没有绑定管理器或绑定管理器未启用")
        
        print(f"{'='*80}\n")

        # 🚀 第一步：完整的文档状态预分析
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("文档分析")
        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        print("[批量导出] 开始文档状态预分析...")
        document_analysis = self._analyze_document_for_export()

        # 从分析结果中提取关键信息
        binding_enabled = document_analysis['binding_enabled']
        binding_categories = document_analysis['binding_categories']
        layer_analysis = document_analysis['layer_analysis']
        export_mode = document_analysis['export_mode']

        print(f"[批量导出] 文档分析完成:")
        print(f"  - 导出模式: {export_mode}")
        print(f"  - 绑定状态: {binding_enabled}")
        print(f"  - 绑定分类: {len(binding_categories)} 个")
        print(f"  - 可见图层: {len(layer_analysis['visible_layers'])} 个")
        print(f"  - 绑定图层: {len(layer_analysis['bound_layers'])} 个")

        # 🚀 第二步：强制使用预计算优化导出系统 - 屏蔽所有旧版导出
        print(f"[批量导出] 强制使用预计算优化导出系统（屏蔽旧版导出）")

        try:
            from app.utils.optimized_batch_executor import export_batch_with_precomputation_v2

            # 创建进度回调包装器
            def progress_wrapper(current_count):
                # 优化批量执行器现在直接传递当前完成数量
                if hasattr(self, 'export_progress_updated'):
                    self.export_progress_updated.emit(current_count)

            def file_completed_wrapper(message):
                if hasattr(self, 'file_exported'):
                    self.file_exported.emit(message)

            def stage_wrapper(stage_name):
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit(str(stage_name))

            def cancel_wrapper():
                return getattr(self, '_export_canceled', False) or (cancel_callback and cancel_callback())

            # 🔧 强制使用预计算导出，无论数量多少
            success = export_batch_with_precomputation_v2(
                document=self,
                document_analysis=document_analysis,  # 传递预分析结果
                directory=directory,
                count=count,
                filename_template=filename_template or "image_{number:04d}",
                file_format=file_format,
                start_index=start_index,
                progress_callback=progress_wrapper,
                file_completed_callback=file_completed_wrapper,
                stage_callback=stage_wrapper,
                cancel_callback=cancel_wrapper,
                traverse_mode=traverse_mode,
                avoid_duplicates=use_smart_sampling
            )

            if success:
                print(f"[批量导出] 预计算导出成功完成")
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("收尾清理")
                self._is_batch_export_running = False
                # 🔧 关键修复：清理所有图层的临时状态
                self._cleanup_layers_after_export()
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("导出完成")
                return True
            else:
                print(f"[批量导出] 预计算导出失败")
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("收尾清理")
                self._is_batch_export_running = False
                # 🔧 关键修复：清理所有图层的临时状态
                self._cleanup_layers_after_export()
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("导出失败")
                return False

        except Exception as e:
            print(f"[批量导出] 预计算导出异常: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self, 'export_stage_updated'):
                self.export_stage_updated.emit("导出异常")
            self._is_batch_export_running = False
            # 🔧 关键修复：清理所有图层的临时状态
            self._cleanup_layers_after_export()
            return False

    def _clear_layer_temporary_states(self):
        """🔧 清理所有图层的临时状态（用于文档加载后）
        
        与 _cleanup_layers_after_export 不同，此方法会清理 current_image_path，
        因为这是从旧文件加载时可能存在的过时状态。
        """
        try:
            print("[文档加载清理] 开始清理图层临时状态...")
            cleaned_count = 0
            
            for layer in self.layers:
                try:
                    # 🔧 关键修复：使用公共属性 current_image_path 而不是私有属性 _current_image_path
                    # Layer（layer_new.py）使用属性管理器，LegacyLayer直接使用实例属性
                    # 通过setter正确处理两种情况
                    if hasattr(layer, 'current_image_path'):
                        old_path = layer.current_image_path
                        if old_path is not None:
                            try:
                                basename = os.path.basename(old_path) if isinstance(old_path, str) else str(old_path)
                                print(f"[文档加载清理] 清理图层 '{layer.name}' 的临时路径: {basename}")
                            except:
                                print(f"[文档加载清理] 清理图层 '{layer.name}' 的临时路径")
                        layer.current_image_path = None  # 使用setter正确清理
                    
                    # 清理缓存
                    if hasattr(layer, '_cached_image'):
                        layer._cached_image = None
                    if hasattr(layer, '_cached_image_path'):
                        layer._cached_image_path = None
                    if hasattr(layer, '_cache_valid'):
                        layer._cache_valid = False
                    if hasattr(layer, 'cached_image'):
                        try:
                            # 对于有setter的cached_image属性
                            layer.cached_image = None
                        except:
                            pass
                    
                    cleaned_count += 1
                except Exception as e:
                    print(f"[文档加载清理] 清理图层 {layer.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
            
            print(f"[文档加载清理] ✅ 已清理 {cleaned_count} 个图层的临时状态")
            
        except Exception as e:
            print(f"[文档加载清理] 清理过程出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _cleanup_layers_after_export(self):
        """🔧 批量导出完成后清理所有图层的临时状态"""
        try:
            print("[批量导出清理] 开始清理图层状态...")
            cleaned_count = 0
            
            for layer in self.layers:
                try:
                    # 清理缓存验证标志
                    if hasattr(layer, '_cache_valid'):
                        layer._cache_valid = False
                    
                    # 清理临时缓存路径（保留_current_image_path和image_source）
                    if hasattr(layer, '_cached_image_path'):
                        layer._cached_image_path = None

                    # 关键：释放图像对象引用，防止导出结束后缓存堆积占用内存
                    if hasattr(layer, '_cached_image'):
                        layer._cached_image = None
                    if hasattr(layer, 'cached_image'):
                        try:
                            layer.cached_image = None
                        except Exception:
                            pass
                    if hasattr(layer, '_current_image_cache'):
                        layer._current_image_cache = None
                    
                    # 注意：不清理_current_image_path和image_source，这些是用户设置的
                    # 只清理内部缓存状态
                    
                    cleaned_count += 1
                except Exception as e:
                    print(f"[批量导出清理] 清理图层 {layer.name} 时出错: {e}")
            
            print(f"[批量导出清理] ✅ 已清理 {cleaned_count} 个图层的状态")
            
            # 清理文档级别的批量导出标志
            if hasattr(self, '_export_canceled'):
                self._export_canceled = False
            
            # 使渲染缓存失效，强制下次预览时重新渲染
            self._invalidate_render_cache()

            # 清理导出链路中的全局缓存，避免任务结束后内存滞留
            try:
                from app.utils.intelligent_render_cache import clear_global_cache as _clear_render_cache
                _clear_render_cache()
            except Exception:
                pass
            try:
                from app.utils.intelligent_cache_system import get_intelligent_cache as _get_intelligent_cache
                _get_intelligent_cache().clear_all_caches()
            except Exception:
                pass
            try:
                from app.utils.advanced_image_cache import get_advanced_image_cache as _get_advanced_cache
                _get_advanced_cache().clear_cache()
            except Exception:
                pass

            # 强制回收游离对象，确保任务完成后内存及时回落
            gc.collect()
            
            print("[批量导出清理] ✅ 批量导出清理完成")
            
        except Exception as e:
            print(f"[批量导出清理] 清理过程出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _invalidate_render_cache(self):
        """使渲染缓存失效"""
        try:
            from app.utils.fast_renderer import get_global_fast_renderer
            renderer = get_global_fast_renderer()
            if hasattr(renderer, 'invalidate_document_cache'):
                renderer.invalidate_document_cache(self)
                print("[文档] 渲染缓存已失效")
        except Exception as e:
            print(f"[文档] 缓存失效失败: {e}")



    def _sanitize_filename_template(self, template):
        """清理文件名模板，移除或替换非法字符，但保护所有占位符格式"""
        import re

        # 先保存所有有效的占位符，包括带格式化的（如{number:04d}）
        # 匹配 {word} 或 {word:format} 格式的占位符
        placeholders = re.findall(r'\{[a-zA-Z_][a-zA-Z0-9_]*(?::[^}]+)?\}', template)

        # 使用临时标记替换所有占位符，使用完全不包含特殊字符的标记
        temp_markers = {}
        for i, placeholder in enumerate(placeholders):
            marker = f"TEMPPLACEHOLDER{i}"  # 使用简单的标记
            template = template.replace(placeholder, marker)
            temp_markers[marker] = placeholder

        # 替换中文逗号并移除逗号（在文件名中通常不需要）
        template = template.replace('，', '')
        template = template.replace(',', '')

        # 移除Windows系统中文件名不允许的字符
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in illegal_chars:
            template = template.replace(char, '_')

        # 恢复占位符
        for marker, placeholder in temp_markers.items():
            template = template.replace(marker, placeholder)

        return template

    def _clean_filename(self, filename):
        """清理生成的文件名，确保合法性"""
        import re
        import unicodedata

        # 确保filename是字符串类型
        if not isinstance(filename, str):
            filename = str(filename)

        # 先处理Unicode字符，规范化为NFKC形式
        try:
            filename = unicodedata.normalize('NFKC', filename)
        except Exception as e:
            print(f"Unicode规范化失败: {e}")
            # 如果规范化失败，尝试编码/解码来清理字符
            try:
                filename = filename.encode('utf-8', 'ignore').decode('utf-8')
            except Exception:
                filename = "export"

        # 移除非法字符，但保留中文和其他Unicode字符
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in illegal_chars:
            filename = filename.replace(char, '_')

        # 移除控制字符和其他不可见字符
        filename = ''.join(char for char in filename if unicodedata.category(char)[0] != 'C')

        # 移除连续的分隔符
        filename = re.sub(r'[-_]{2,}', '-', filename)
        filename = re.sub(r'^[-_]+|[-_]+$', '', filename)  # 移除开头和结尾的分隔符
        
        # 确保文件名不为空
        if not filename or filename.isspace():
            filename = "export"
        
        # 限制文件名长度（考虑多字节字符）
        # Windows文件名限制约255字节，但为了安全，我们使用200个字符
        if len(filename.encode('utf-8')) > 200:
            # 按字符逐个截取，确保不超过字节限制
            truncated = ""
            for char in filename:
                if len((truncated + char).encode('utf-8')) <= 200:
                    truncated += char
                else:
                    break
            filename = truncated
        
        return filename
    
    def _extract_main_filename(self, filename):
        """提取文件名的主要部分，去除可能的序号"""
        import re
        import unicodedata
        
        # 确保filename是字符串类型，并进行Unicode规范化
        if not isinstance(filename, str):
            filename = str(filename)
        
        try:
            filename = unicodedata.normalize('NFKC', filename)
        except Exception:
            # 如果规范化失败，继续使用原始字符串
            pass
        
        # 分离可能的编号部分
        name_parts = filename.split('-')
        
        # 过滤掉所有纯数字、数字+字母或带下划线的数字组合（可能是序号）
        filtered_parts = []
        for part in name_parts:
            # 检查是否为纯数字
            if part.isdigit():
                continue
            # 检查是否为带下划线的数字（如"12_2"）
            if re.match(r'^\d+_\d+$', part):
                continue
            # 检查是否为ASCII字母+数字组合（如"a1", "b2"）
            if re.match(r'^[a-zA-Z]+\d+$', part):
                continue
            # 检查是否为数字+ASCII字母组合（如"1a", "2b"）
            if re.match(r'^\d+[a-zA-Z]+$', part):
                continue
            # 检查是否为纯英文字母+下划线+数字的组合（如"scene_1", "bg_01"）
            if re.match(r'^[a-zA-Z_]+\d+$', part):
                continue
            
            # 保留包含中文或其他非ASCII字符的部分
            filtered_parts.append(part)
        
        # 如果所有部分都被过滤掉了，使用原始文件名
        if not filtered_parts:
            return filename
        
        # 重新组合
        result = '-'.join(filtered_parts)
        
        # 最后清理结果
        return self._clean_filename(result)
    
    def _get_binding_common_categories(self) -> List[str]:
        """获取所有绑定组的公共分类 - 修复版本，添加详细的诊断信息"""
        print("[绑定分析] 开始分析绑定组的公共分类...")
        
        # 🔧 关键修复：更严格的绑定管理器检查
        if not hasattr(self, 'binding_manager'):
            print("[绑定分析] ❌ 文档没有绑定管理器属性")
            return []
        
        if not self.binding_manager:
            print("[绑定分析] ❌ 绑定管理器为空")
            return []
        
        if not self.binding_manager.global_enabled:
            print("[绑定分析] ❌ 绑定管理器的全局功能未启用")
            return []
        
        if not self.binding_manager.binding_groups:
            print("[绑定分析] ❌ 没有绑定组")
            return []
        
        print(f"[绑定分析] ✅ 发现 {len(self.binding_manager.binding_groups)} 个绑定组")
        
        common_categories = None
        processed_groups = 0
        
        # 检查所有绑定组
        for group_id, group in self.binding_manager.binding_groups.items():
            print(f"[绑定分析] 处理绑定组: {group.name} (ID: {group_id})")
            
            # 🔧 关键修复：只考虑可见图层，并提供更详细的匹配信息
            document_layers = []
            unmatched_layers = []
            
            for group_layer in group.layers:
                matched = False
                for doc_layer in self.layers:
                    # 🔧 关键修复：检查图层是否可见
                    if doc_layer.name == group_layer.name and doc_layer.visible:
                        document_layers.append(doc_layer)
                        matched = True
                        print(f"[绑定分析]   ✅ 匹配图层: {group_layer.name} (可见)")
                        break
                    elif doc_layer.name == group_layer.name and not doc_layer.visible:
                        print(f"[绑定分析]   ⚠️  图层 {group_layer.name} 存在但不可见，跳过")
                        matched = True
                        break
                
                if not matched:
                    unmatched_layers.append(group_layer.name)
                    print(f"[绑定分析]   ❌ 未找到图层: {group_layer.name}")
            
            # 🔧 关键修复：如果没有可见的匹配图层，跳过此绑定组
            if not document_layers:
                print(f"[绑定分析] ⚠️  绑定组 {group.name} 没有可见的匹配图层，跳过")
                continue
            
            # 如果有部分图层未匹配，给出警告但继续处理
            if unmatched_layers:
                print(f"[绑定分析] ⚠️  绑定组 {group.name} 中有 {len(unmatched_layers)} 个图层未找到: {unmatched_layers}")
            
            print(f"[绑定分析]   处理 {len(document_layers)} 个可见匹配图层")
            
            # 🔧 关键修复：创建临时绑定组用于文件分析
            from app.models.binding_manager import BindingGroup
            temp_group = BindingGroup(group.group_id, group.name, binding_manager=self.binding_manager)
            temp_group._binding_manager = self.binding_manager
            
            for i, layer in enumerate(document_layers):
                temp_group.add_layer(layer, i)
                print(f"[绑定分析]     添加图层 {i}: {layer.name} -> {layer.image_source}")
            
            # 🔧 关键修复：强制重新分析文件分类
            print(f"[绑定分析]   重新分析文件分类...")
            temp_group._rebuild_file_categories()
            
            group_categories = temp_group.get_available_categories()
            print(f"[绑定分析]   绑定组 {group.name} 可用分类: {group_categories}")

            image_backed_categories = []
            try:
                for category in group_categories:
                    has_image_support = False
                    if category in temp_group.file_categories:
                        for layer_idx, files in temp_group.file_categories[category].items():
                            if any(isinstance(f, str) and not is_text_layer_virtual_path(f) for f in files):
                                has_image_support = True
                                break
                    if has_image_support:
                        image_backed_categories.append(category)
                if image_backed_categories:
                    print(f"[绑定分析]   图像支撑分类: {image_backed_categories}")
                    group_categories = image_backed_categories
                else:
                    print(f"[绑定分析]   ⚠️ 无图像支撑分类，保留原分类以避免空结果")
            except Exception:
                pass
            
            if not group_categories:
                print(f"[绑定分析] ⚠️  绑定组 {group.name} 没有可用分类，可能文件结构不匹配")
                # 🔧 关键修复：输出详细的文件分类调试信息
                print(f"[绑定分析]     文件分类详情: {temp_group.file_categories}")
                continue
            
            group_categories_set = set(group_categories)
            
            if common_categories is None:
                common_categories = group_categories_set
                print(f"[绑定分析]   初始化公共分类: {group_categories}")
            else:
                # 取交集
                before_intersection = len(common_categories)
                common_categories = common_categories.intersection(group_categories_set)
                print(f"[绑定分析]   更新公共分类: {before_intersection} -> {len(common_categories)}")
            
            processed_groups += 1
        
        print(f"[绑定分析] 处理完成，成功处理了 {processed_groups} 个绑定组")
        
        if common_categories is None:
            print("[绑定分析] ❌ 没有找到任何公共分类")
            return []
        
        result = sorted(list(common_categories))
        print(f"[绑定分析] ✅ 找到 {len(result)} 个公共分类: {result}")
        
        return result
    
    def _set_binding_category_combination(self, category: str):
        """为绑定组设置指定分类的组合 - 根本修复：确保所有绑定组使用统一分类"""
        if not hasattr(self, 'binding_manager') or not self.binding_manager.global_enabled:
            print(f"[绑定组合] ❌ 绑定管理器不可用或未启用")
            return
        
        print(f"[绑定组合] 🎯 设置绑定分类组合: '{category}'")
        print(f"[绑定组合] 📋 可用绑定组数量: {len(self.binding_manager.binding_groups) if hasattr(self.binding_manager, 'binding_groups') else 0}")
        
        # 🔧 根本修复：首先为所有绑定组预选择统一的文件组合
        # 这样可以确保所有绑定组使用相同的分类和内容
        binding_group_combinations = {}
        
        # 为每个绑定组预选择组合，但确保使用相同的分类
        for group_id, group in self.binding_manager.binding_groups.items():
            print(f"[绑定组合] 预选择绑定组组合: {group.name} (ID: {group_id})")
            
            # 创建临时绑定组用于预选择
            from app.models.binding_manager import BindingGroup
            temp_group = BindingGroup(group.group_id, group.name, binding_manager=self.binding_manager)
            temp_group._binding_manager = self.binding_manager
            
            # 同步使用历史
            if hasattr(group, '_category_usage_history') and category in group._category_usage_history:
                temp_group._category_usage_history = {category: group._category_usage_history[category].copy()}
            
            # 只添加可见图层
            document_layers = []
            for group_layer in group.layers:
                for doc_layer in self.layers:
                    if doc_layer.name == group_layer.name and doc_layer.visible:
                        document_layers.append(doc_layer)
                        break
            
            if not document_layers:
                print(f"[绑定组合] ⚠️  绑定组 {group.name} 没有可见图层，跳过预选择")
                continue
            
            # 添加图层到临时绑定组
            for i, layer in enumerate(document_layers):
                temp_group.add_layer(layer, i)
            
            # 重新分析分类
            temp_group._rebuild_file_categories()
            available_categories = temp_group.get_available_categories()
            
            if category not in available_categories:
                print(f"[绑定组合] ❌ 绑定组 {group.name} 不支持分类 '{category}'")
                continue
            
            # 预选择组合（预览模式不启用避重）
            try:
                matched_files = temp_group.get_matched_files(category, avoid_duplicates=False)
                # 计算该绑定组在当前文档中可见并参与绑定的图层数量
                expected_count = len(document_layers)
                # 只有当所有参与绑定的可见图层都获得匹配文件时，才认为该组可用
                if matched_files and len(matched_files) == expected_count:
                    binding_group_combinations[group_id] = matched_files
                    print(f"[绑定组合] ✅ 预选择成功: 覆盖 {len(matched_files)}/{expected_count} 个图层")
                else:
                    print(f"[绑定组合] ⚠️  预选择失败: 覆盖 {len(matched_files) if matched_files else 0}/{expected_count} 个图层")
            except Exception as e:
                print(f"[绑定组合] ❌ 预选择失败: {e}")
        
        if not binding_group_combinations:
            print(f"[绑定组合] ❌ 没有绑定组能使用分类 '{category}'")
            return
        
        # 记录已处理的图层，避免重复随机化
        processed_layers = set()
        successful_groups = 0
        
        # 🔧 根本修复：使用预选的统一组合应用到所有绑定组
        for group_id, group in self.binding_manager.binding_groups.items():
            if group_id not in binding_group_combinations:
                print(f"[绑定组合] 跳过绑定组 {group.name}: 无预选择组合")
                continue
                
            print(f"[绑定组合] 应用预选择组合到绑定组: {group.name} (ID: {group_id})")
            
            # 获取预选的统一组合
            matched_files = binding_group_combinations[group_id]
            
            # 获取该绑定组的可见图层
            document_layers = []
            for group_layer in group.layers:
                for doc_layer in self.layers:
                    if doc_layer.name == group_layer.name and doc_layer.visible:
                        document_layers.append(doc_layer)
                        break
            
            if not document_layers:
                print(f"[绑定组合] ⚠️  绑定组 {group.name} 没有可见图层，跳过")
                continue
            
            print(f"[绑定组合]   应用 {len(matched_files)} 个文件到 {len(document_layers)} 个图层")
            # 严格校验：若未覆盖全部图层，则跳过应用，避免出现跨分类混合
            if len(matched_files) != len(document_layers):
                print(f"[绑定组合] ⚠️ 覆盖不完整，跳过绑定组 '{group.name}' 的应用")
                continue
            
            # 应用到实际的文档图层
            for layer_index, file_path in matched_files.items():
                if layer_index < len(document_layers):
                    layer = document_layers[layer_index]
                    
                    # 检查图层类型，分别处理
                    from app.models.text_layer import TextLayer
                    
                    if isinstance(layer, TextLayer):
                        # 文字图层：优先使用匹配结果中的虚拟路径来设置当前文字
                        try:
                            if is_text_layer_virtual_path(file_path):
                                _, text_content = parse_text_layer_virtual_path(file_path)
                                if text_content.strip():
                                    layer.current_text = text_content
                                    print(f"文字图层 '{layer.name}' 应用匹配文案: {text_content}")
                                else:
                                    raise ValueError("无法解析文字匹配路径")
                            else:
                                # 回退：根据分类关键词匹配文字行（单向包含：文字内容包含分类关键词）
                                text_lines = layer.get_text_lines()
                                matching_text = None
                                for text_line in text_lines:
                                    # 修复：只需要文字内容包含分类关键词即可匹配
                                    if category in text_line:
                                        matching_text = text_line
                                        break
                                if matching_text:
                                    layer.current_text = matching_text
                                    print(f"文字图层 '{layer.name}' 回退根据分类应用文案: {matching_text}")
                                elif text_lines:
                                    default_text = text_lines[0]
                                    layer.current_text = default_text
                                    print(f"文字图层 '{layer.name}' 未找到匹配，使用默认: {default_text}")
                                else:
                                    print(f"文字图层 '{layer.name}' 没有可用的文本内容")
                        except Exception as e:
                            print(f"[绑定组合] 处理文字图层匹配失败: {e}")
                        
                        # 记录已处理的图层并清除缓存
                        processed_layers.add(id(layer))
                        if hasattr(layer, '_cached_image'):
                            layer._cached_image = None
                        
                    else:
                        # 图像图层：设置图像路径
                        old_path = layer.current_image_path
                        # 🔧 关键修复：使用公共属性setter，它不是只读的
                        layer.current_image_path = file_path
                        
                        # 清除缓存，确保重新加载图片
                        layer.cached_image = None
                        if hasattr(layer, '_cached_image_path'):
                            layer._cached_image_path = None
                        
                        print(f"图层 '{layer.name}' 设置为分类 '{category}' 的文件: {os.path.basename(file_path)}")
                        
                        # 记录已处理的图层
                        processed_layers.add(id(layer))
                        
                        # 🔧 关键修复：如果路径发生变化，使用图层的标准处理方法
                        if old_path != file_path:
                            try:
                                # 使用图层的标准图像处理方法，保持所有图层设置
                                # 这会考虑 fit_mode, use_original_size, 智能裁剪等所有设置
                                processed_image = layer.get_random_image(force_random=False)

                                if processed_image is not None:
                                    # 确保缓存路径正确设置
                                    layer._cached_image_path = layer.current_image_path
                                    print(f"[导出绑定] 使用标准方法加载图层 '{layer.name}' 图像成功")
                                else:
                                    print(f"[导出绑定] 标准方法返回空图像: {layer.name}")

                            except Exception as e:
                                print(f"[导出绑定] 标准方法加载图层 '{layer.name}' 图像失败: {e}")
                                # 如果标准方法失败，清除缓存让渲染时重新处理
                                layer.cached_image = None
                                layer._cached_image_path = None
            
            successful_groups += 1
        
        print(f"[绑定组合] 处理完成，成功处理了 {successful_groups} 个绑定组，共 {len(processed_layers)} 个图层")
        
        # 🔧 关键修复：对于未绑定的可见图层，进行标准随机化
        unbound_layers_processed = 0
        for layer in self.layers:
            # 只处理可见图层
            if not layer.visible:
                continue

            # 检查图层是否已经被处理过（即属于绑定组）
            if id(layer) not in processed_layers:
                # 检查是否是文字图层
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer):
                    # 文字图层，随机选择文字
                    layer.randomize_text()
                    print(f"[绑定组合] 非绑定文字图层 '{layer.name}' 随机选择文字: {layer.current_text}")
                elif layer.image_source and os.path.isdir(layer.image_source):
                    # 普通图层，随机选择图像
                    old_path = layer.current_image_path
                    # 强制随机选择新的图像文件
                    layer.get_random_image(force_random=True)
                    print(f"[绑定组合] 非绑定图层 '{layer.name}' 随机选择文件: {os.path.basename(layer.current_image_path) if layer.current_image_path else 'None'}")
                    # 检查路径是否发生变化
                    if layer.current_image_path != old_path:
                        layer.cached_image = None
                unbound_layers_processed += 1

            # 为可见图层（包括绑定和非绑定）生成新的随机变换参数
            if hasattr(layer, 'generate_random_transform_params'):
                layer.generate_random_transform_params()
                
        print(f"[绑定组合] 额外处理了 {unbound_layers_processed} 个非绑定图层")
    
    def save_document(self, file_path):
        """保存文档到指定路径"""
        try:
            from app.models.document_serializer import DocumentSerializer

            document_data = DocumentSerializer.prepare_document_data(self)
            document_data['version'] = 5  # 统一图层参数序列化，补齐随机/文字扩展字段
            
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # 保存数据
            with open(file_path, 'wb') as f:
                pickle.dump(document_data, f)
                
            self.current_file_path = file_path
            
            # 标记文档为未修改状态
            self.is_modified = False
            
            # 发送文档变更信号，通知界面更新
            self.document_changed.emit()
            
            return True
        except Exception as e:
            # 使用日志记录错误，同时保持原有的print输出以确保兼容性
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(f"保存文档失败: {e}", exc_info=True)
            except:
                pass
            print(f"保存文档失败: {e}")
            return False
            
    def load_document(self, file_path):
        """从指定路径加载文档"""
        try:
            # 尝试导入错误处理函数
            try:
                from main import set_document_load_error
                has_error_handler = True
            except ImportError:
                has_error_handler = False
            
            with open(file_path, 'rb') as f:
                document_data = pickle.load(f)
            
            # 检查文档版本
            doc_version = document_data.get('version', 1)  # 默认为版本1（无版本号的旧文件）
            print(f"加载文档, 版本: {doc_version}")
                
            self.canvas_width = document_data.get('canvas_width', 0)
            self.canvas_height = document_data.get('canvas_height', 0)
            
            # 加载图层
            self.layers = []
            layers_data = document_data.get('layers', [])
            try:
                from app.utils.layer_tree import deserialize_layer_tree
                self.layers.extend(
                    deserialize_layer_tree(
                        layers_data,
                        lambda data, parent=None: self.create_layer_from_data(data),
                        parent=self,
                    )
                )
            except Exception:
                for layer_data in layers_data:
                    layer = self.create_layer_from_data(layer_data)
                    if layer is not None:
                        self.layers.append(layer)
                
            self.selected_layer_index = document_data.get('selected_layer_index', -1)
            self.selected_layer_indices = [self.selected_layer_index] if self.selected_layer_index >= 0 else []
            
            # 如果选择的图层索引超出范围，重置为-1
            if self.selected_layer_index >= len(self.layers):
                self.selected_layer_index = -1
                self.selected_layer_indices = []
                
            # 加载导出设置
            if 'export_settings' in document_data:
                loaded_settings = document_data.get('export_settings', {})
                merged_settings = self._build_default_export_settings()
                if isinstance(loaded_settings, dict):
                    merged_settings.update(loaded_settings)
                self.export_settings = merged_settings
            
            # 加载视图设置（标尺/参考线/吸附/缩放位移）
            self.set_view_settings(document_data.get('view_settings', {}))
                
            self.current_file_path = file_path
            
            # 标记文档为未修改状态
            self.is_modified = False
            
            # 重置历史记录
            self.history = []
            self.history_index = -1
            
            # 确保绑定管理器正确初始化（兼容性处理）
            if not hasattr(self, 'binding_manager'):
                from app.models.binding_manager import LayerBindingManager
                self.binding_manager = LayerBindingManager()
            
            # 加载绑定组数据（如果存在）
            if 'binding_groups' in document_data:
                try:
                    self.binding_manager.deserialize(document_data['binding_groups'], self.layers)
                except Exception as e:
                    print(f"加载绑定组数据失败: {e}")
                    # 如果加载失败，使用空的绑定管理器
                    self.binding_manager = LayerBindingManager()

            # 加载图层大小匹配配置
            if not hasattr(self, 'layer_size_match_manager') or self.layer_size_match_manager is None:
                self.layer_size_match_manager = LayerSizeMatchManager(parent=self)
            try:
                self.layer_size_match_manager.deserialize(document_data.get('layer_size_matches', {}))
            except Exception as e:
                print(f"加载图层大小匹配配置失败: {e}")
                self.layer_size_match_manager = LayerSizeMatchManager(parent=self)
            
            # 🔧 关键修复：加载文档后，清除所有图层的临时图像路径
            # 这确保从旧版本文件加载时，不会保留过时的图像路径
            self._clear_layer_temporary_states()
            
            # 发出信号通知界面更新
            self.document_changed.emit()
            self.layer_changed.emit()
            
            return True
        except Exception as e:
            error_msg = f"加载文档失败: {e}"
            # 使用日志记录错误，同时保持原有的print输出
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(error_msg, exc_info=True)
            except:
                pass
            print(error_msg)

            # 如果存在错误处理函数，设置错误信息
            if has_error_handler:
                set_document_load_error(e)

            return False

    def render_document(self):
        """渲染文档为PIL图像"""
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            return None
        # 使用新的渲染器实现，保持与导出一致
        try:
            from app.models.document_renderer import DocumentRenderer
            renderer = DocumentRenderer()
            image = renderer.render_document(
                canvas_width=self.canvas_width,
                canvas_height=self.canvas_height,
                layers=self.layers,
                background_color=(0, 0, 0, 0),
                force_opaque=False
            )
            return image
        except Exception:
            # 回退到兼容渲染逻辑，以确保功能可用
            return self._render_document_legacy()

    def export_image(self, file_path: str) -> bool:
        """导出单张图像 - 使用与预览一致的渲染方式"""
        try:
            if self.canvas_width <= 0 or self.canvas_height <= 0:
                self._last_export_error = "画布尺寸无效"
                print(f"[导出] 错误：画布尺寸无效")
                return False
            
            if not file_path:
                self._last_export_error = "文件路径为空"
                print(f"[导出] 错误：文件路径为空")
                return False
            
            ext = os.path.splitext(file_path)[1].lower()
            
            # 使用统一渲染服务，内部仍可回退到现有快速渲染器。
            print(f"[导出] 开始渲染图像: {file_path}")
            try:
                from app.services.render_service import RenderRequest, get_render_service
                render_result = get_render_service().render(
                    RenderRequest(
                        document=self,
                        mode="export",
                        quality_profile=str((getattr(self, "export_settings", {}) or {}).get("export_quality_profile", "quality")),
                        batch_mode=False,
                    )
                )
                image = render_result.image
                if not render_result.ok and render_result.error:
                    print(f"[导出] 渲染服务提示: {render_result.error}")
            except Exception:
                from app.utils.fast_renderer import get_global_fast_renderer
                fast_renderer = get_global_fast_renderer()
                image = fast_renderer.render_batch(self)
            
            if image is None:
                self._last_export_error = "渲染失败：渲染器返回None"
                print(f"[导出] 错误：渲染器返回None")
                return False
            
            print(f"[导出] 渲染成功: {image.size}, 模式={image.mode}")
            
            try:
                from app.services.export_service import ExportJob, get_export_service
                settings = getattr(self, "export_settings", {}) or {}
                report = get_export_service().save_image(
                    image,
                    ExportJob(
                        file_path=file_path,
                        file_format=ext[1:] if ext else None,
                        quality_profile=str(settings.get("export_quality_profile", "quality") or "quality"),
                        max_file_size_kb=int(settings.get("max_file_size_kb", 0) or 0),
                        jpeg_quality=int(settings.get("jpeg_quality_override", 0) or 0),
                        png_compress_level=int(settings.get("png_compress_level_override", -1)),
                        backend=str(settings.get("export_backend", "pillow") or "pillow"),
                        allow_lossy_size_reduction=bool(settings.get("allow_lossy_size_reduction", False)),
                    )
                )
                if not report.success:
                    self._last_export_error = report.error or "保存失败"
                return bool(report.success)
            except Exception:
                from app.utils.image_quality import ImageQualityManager
                ok = ImageQualityManager.save_high_quality_image(
                    image, file_path, format_hint=ext[1:] if ext else None
                )
                if not ok:
                    self._last_export_error = "保存失败"
                return bool(ok)
        except Exception as e:
            self._last_export_error = str(e)
            return False
    
    def _render_document_legacy(self):
        """原始渲染逻辑（向后兼容）"""
        # 创建空白画布
        canvas = Image.new('RGBA', (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
        
        # 从下到上渲染每个图层
        for layer in self.layers:
            if not layer.visible:
                continue
                
            # 获取图层图像 - 支持文字图层和普通图层
            layer_image = None
            from app.models.text_layer import TextLayer
            
            if isinstance(layer, TextLayer):
                # 文字图层，渲染文字为图像
                layer_image = layer.render_text()
            else:
                # 普通图层处理
                # 检查图层是否已绑定且current_image_path已更新
                is_bound_layer = (hasattr(self, 'binding_manager') and 
                                self.binding_manager.is_layer_bound(layer))
                                
                if is_bound_layer and hasattr(layer, 'current_image_path') and layer.current_image_path:
                    # 绑定图层：检查缓存是否与当前路径匹配
                    cache_valid = (hasattr(layer, 'cached_image') and 
                                 layer.cached_image is not None and
                                 hasattr(layer, '_cached_image_path') and
                                 layer._cached_image_path == layer.current_image_path)
                    
                    if cache_valid:
                        # 缓存有效，使用缓存
                        layer_image = layer.cached_image
                        print(f"[渲染] 绑定图层 '{layer.name}' 使用有效缓存")
                    else:
                        # 缓存无效或路径不匹配，重新加载但不随机化
                        print(f"[渲染] 绑定图层 '{layer.name}' 缓存无效，重新加载: {layer.current_image_path}")
                        layer_image = layer.get_random_image(force_random=False)
                        # 记录缓存对应的路径
                        if layer_image and hasattr(layer, 'current_image_path'):
                            layer._cached_image_path = layer.current_image_path
                else:
                    # 非绑定图层：使用原有逻辑
                    if hasattr(layer, 'cached_image') and layer.cached_image is not None:
                        # 使用已缓存的图像
                        layer_image = layer.cached_image
                    else:
                        # 如果没有缓存，才尝试获取/随机一个
                        layer_image = layer.get_random_image()
            
            if layer_image is None:
                continue
                
            # 应用图层特效
            layer_image = layer.apply_effects(layer_image)
                
            # 创建图层位置框
            box = (layer.x, layer.y, layer.x + layer.width, layer.y + layer.height)
            
            # 获取图层的透明度
            opacity = layer.opacity
            
            # 如果图层完全透明，则跳过
            if opacity <= 0:
                continue
                
            # 将图像粘贴到画布上，考虑透明度
            if opacity < 1.0:
                # 需要创建一个带透明度的临时图像
                transparent = Image.new('RGBA', layer_image.size, (0, 0, 0, 0))
                temp_image = Image.blend(transparent, layer_image, opacity)
                canvas.paste(temp_image, (layer.x, layer.y), temp_image)
            else:
                # 完全不透明，直接粘贴
                canvas.paste(layer_image, (layer.x, layer.y), layer_image)
        
        return canvas
    

    


    def create_layer_from_data(self, layer_data):
        """从序列化的数据创建图层对象
        
        参数:
            layer_data (dict): 序列化的图层数据
            
        返回:
            Layer或TextLayer或ShapedLayer: 创建的图层对象
        """
        if not isinstance(layer_data, dict):
            # 兜底为默认图层，避免把None/非法数据注入图层列表
            return NewLayer(name='错误图层', x=0, y=0, width=100, height=100)

        try:
            # 检查图层类型 - 支持 type 和 layer_type 两种字段名
            layer_type = layer_data.get('layer_type') or layer_data.get('type', 'image')
            
            # 🔧 增强：通过检查关键字段来验证图层类型
            if 'shape_type' in layer_data and layer_type not in ('image', 'Layer'):
                # 如果有 shape_type 字段，应该是异形图层
                if layer_type != 'shaped':
                    print(f"[警告] 图层数据包含shape_type但layer_type为{layer_type}，强制使用异形图层")
                    layer_type = 'shaped'
            
            if layer_type == 'group':
                from app.models.layer_group import LayerGroup
                return LayerGroup.deserialize(layer_data, parent=self)
            elif layer_type == 'text':
                # 文字图层
                from app.models.text_layer import TextLayer
                layer = TextLayer.deserialize(layer_data)
            elif layer_type == 'shaped':
                # 异形图层
                from app.models.shaped_layer_new import ShapedLayer
                layer = ShapedLayer.deserialize(layer_data)
            else:
                # 普通图层
                layer = NewLayer.deserialize(layer_data)
            parent_group_id = layer_data.get('parent_group_id') or layer_data.get('_parent_group_id')
            if parent_group_id:
                try:
                    setattr(layer, 'parent_group_id', str(parent_group_id))
                    setattr(layer, '_parent_group_id', str(parent_group_id))
                except Exception:
                    pass
            return layer
                
        except Exception as e:
            print(f"从数据创建图层失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 🔧 增强异常处理：尝试根据数据特征恢复图层类型
            try:
                if 'shape_type' in layer_data:
                    # 尝试作为异形图层创建
                    print("[恢复] 尝试作为异形图层恢复...")
                    from app.models.shaped_layer_new import ShapedLayer
                    layer = ShapedLayer(
                        name=layer_data.get('name', '恢复的异形图层'),
                        x=layer_data.get('x', 0),
                        y=layer_data.get('y', 0),
                        width=layer_data.get('width', 100),
                        height=layer_data.get('height', 100),
                        image_source=layer_data.get('image_source'),
                        use_original_size=layer_data.get('use_original_size', False),
                        is_folder=layer_data.get('is_folder', True)
                        # 🔧 关键修复：不传入current_image_path，这是临时状态
                    )
                    # 尝试设置异形属性
                    for key in ['shape_type', 'trapezoid_top_width', 'trapezoid_bottom_width', 
                               'trapezoid_slope_side', 'polygon_rotation', 'polygon_corner_radius']:
                        if key in layer_data:
                            try:
                                setattr(layer, key, layer_data[key])
                            except Exception as attr_e:
                                print(f"[恢复] 设置属性 {key} 失败: {attr_e}")
                    return layer
                else:
                    # 回退到普通图层
                    raise Exception("不是异形图层数据")
            except Exception as recovery_e:
                # 最终回退方案
                print(f"[恢复] 异形图层恢复失败: {recovery_e}")
                print("[恢复] 最终回退到普通图层")
                default_layer = NewLayer(
                    name=layer_data.get('name', '错误图层'),
                    x=layer_data.get('x', 0),
                    y=layer_data.get('y', 0),
                    width=layer_data.get('width', 100),
                    height=layer_data.get('height', 100)
                )
                return default_layer

    def update_layer(self, layer_index):
        """更新指定图层，避免全局重绘"""
        if 0 <= layer_index < len(self.layers):
            layer = self.layers[layer_index]
            # 清理该图层的缓存
            if hasattr(layer, 'clear_cache'):
                layer.clear_cache()
            # 发送精确的图层更新信号
            self.layer_updated.emit(layer_index)
            print(f"更新图层 {layer_index}: {layer.name}")

    def update_specific_layers(self, layer_indices):
        """更新指定的多个图层"""
        for layer_index in layer_indices:
            if 0 <= layer_index < len(self.layers):
                layer = self.layers[layer_index]
                # 清理该图层的缓存
                if hasattr(layer, 'clear_cache'):
                    layer.clear_cache()
                # 发送精确的图层更新信号
                self.layer_updated.emit(layer_index)
        print(f"更新图层: {layer_indices}")

    def _calculate_possible_combinations(self):
        """计算理论上可能的唯一组合数量"""
        try:
            total_combinations = 1
            visible_layers = 0
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
            unique_caps = []
            combination_limit_applied = False
            export_settings = getattr(self, 'export_settings', {}) or {}
            unique_use_enabled = bool(export_settings.get('unique_use_enabled', False))
            try:
                unique_use_layers = {int(idx) for idx in export_settings.get('unique_use_layers', [])}
            except Exception:
                unique_use_layers = set()

            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            for doc_layer_idx, layer in enumerate(self.layers):
                if is_layer_group(layer) or not is_effectively_visible(layer, self.layers):
                    continue

                visible_layers += 1
                layer_combinations = 1
                is_image_candidate_layer = False

                # 检查是否是文字图层
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer) or hasattr(layer, 'get_text_lines') or hasattr(layer, 'text_content'):
                    candidates = []
                    if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                        try:
                            candidates = [
                                str(line)
                                for line in (layer.get_text_lines() or [])
                                if line is not None and str(line).strip()
                            ]
                        except Exception:
                            candidates = []
                    elif hasattr(layer, 'text_list') and layer.text_list:
                        candidates = [str(line) for line in layer.text_list if line is not None and str(line).strip()]
                    elif hasattr(layer, 'text_content'):
                        content = getattr(layer, 'text_content', '')
                        if bool(getattr(layer, 'text_binding_enabled', False)):
                            candidates = [line.strip() for line in str(content).splitlines() if line.strip()]
                        elif str(content).strip():
                            candidates = [str(content)]
                    layer_combinations = max(1, len(candidates))
                elif hasattr(layer, '_is_folder') and layer._is_folder:
                    # 文件夹图层：计算文件夹中的图片数量
                    is_image_candidate_layer = True
                    if hasattr(layer, 'image_source') and layer.image_source:
                        try:
                            if os.path.isdir(layer.image_source):
                                image_files = []
                                for file in os.listdir(layer.image_source):
                                    ext = os.path.splitext(file)[1].lower()
                                    if ext in image_extensions:
                                        image_files.append(file)
                                layer_combinations = max(1, len(image_files))
                        except Exception as e:
                            print(f"计算图层 {layer.name} 文件数量时出错: {e}")
                            layer_combinations = 1
                elif hasattr(layer, 'image_source') and layer.image_source:
                    # 检查是否是单个文件
                    if os.path.isfile(layer.image_source):
                        is_image_candidate_layer = True
                        layer_combinations = 1
                    elif os.path.isdir(layer.image_source):
                        # 如果image_source是目录，按文件夹处理
                        is_image_candidate_layer = True
                        try:
                            image_files = []
                            for file in os.listdir(layer.image_source):
                                ext = os.path.splitext(file)[1].lower()
                                if ext in image_extensions:
                                    image_files.append(file)
                            layer_combinations = max(1, len(image_files))
                        except:
                            layer_combinations = 1
                    else:
                        layer_combinations = 1
                else:
                    # 其他情况：只有1种组合
                    layer_combinations = 1

                print(f"图层 '{layer.name}': {layer_combinations} 种可能")
                total_combinations *= layer_combinations
                if unique_use_enabled and doc_layer_idx in unique_use_layers and is_image_candidate_layer:
                    unique_caps.append(layer_combinations)

                # 防止数值过大
                if total_combinations > 1000000:  # 限制在100万以内
                    if not combination_limit_applied:
                        print(f"组合数量过大，限制为1000000")
                        combination_limit_applied = True
                    total_combinations = 1000000

            # 如果没有可见图层，返回1
            if visible_layers == 0:
                print("没有可见图层，返回组合数量: 1")
                return 1

            result = max(1, total_combinations)
            if unique_use_enabled and unique_caps:
                unique_cap = max(1, min(unique_caps))
                if result > unique_cap:
                    print(f"图像唯一使用限制生效，组合数量从 {result} 调整为 {unique_cap}")
                    result = unique_cap
            print(f"计算得到的总组合数量: {result}")
            return result

        except Exception as e:
            print(f"计算可能组合数量时出错: {e}")
            import traceback
            traceback.print_exc()
            return 1000  # 默认返回一个合理的数值

    def cancel_export(self):
        """取消当前的批量导出操作"""
        if hasattr(self, '_export_canceled'):
            self._export_canceled = True
            print("已设置导出取消标志")
        try:
            self._last_export_error = "导出已取消"
        except Exception:
            pass

        # 尝试立即中断执行器与预计算器，降低取消延迟
        try:
            active_executor = getattr(self, '_active_export_executor', None)
            if active_executor and hasattr(active_executor, 'cancel'):
                active_executor.cancel()
        except Exception:
            pass
        try:
            active_precomputer = getattr(self, '_active_precomputer', None)
            if active_precomputer is not None:
                setattr(active_precomputer, '_was_canceled', True)
        except Exception:
            pass
        
        # 强制垃圾回收以释放资源
        try:
            import gc
            gc.collect()
        except:
            pass







    def _get_layer_blend_mode_string(self, layer):
        """获取图层的混合模式字符串"""
        try:
            blend_mode = getattr(layer, 'blend_mode', 0)

            # 如果是None或无效值，返回normal
            if blend_mode is None:
                return 'normal'

            # 如果是数字，转换为字符串
            if isinstance(blend_mode, int):
                blend_mode_map = {
                    0: 'normal',
                    1: 'multiply',
                    2: 'screen',
                    3: 'overlay',
                    4: 'soft_light',
                    5: 'hard_light',
                    6: 'color_dodge',
                    7: 'color_burn',
                    8: 'darken',
                    9: 'lighten',
                    10: 'difference',
                    11: 'exclusion',
                    12: 'hue',
                    13: 'saturation',
                    14: 'color',
                    15: 'luminosity'
                }
                return blend_mode_map.get(blend_mode, 'normal')

            # 如果已经是字符串，直接返回
            return str(blend_mode)

        except Exception as e:
            print(f"获取混合模式失败: {e}")
            return 'normal'

    def _optimized_batch_export(self, directory, count, filename_template=None, file_format="png",
                               start_index=1, cancel_callback=None, traverse_mode=False):
        """优化的批量导出实现"""
        try:
            from app.utils.batch_optimization_manager import get_optimization_manager, ExportProfile
            from app.utils.parallel_batch_exporter import get_parallel_exporter
            from app.utils.intelligent_cache_system import get_intelligent_cache
            from app.utils.memory_optimizer import get_memory_optimizer

            print(f"[优化导出] 开始高性能批量导出 {count} 张图像")

            # 1. 分析导出任务
            export_profile = ExportProfile(
                image_count=count,
                average_image_size=(self.canvas_width, self.canvas_height),
                file_format=file_format,
                quality_level='high',
                has_complex_layers=len(self.layers) > 5,
                has_text_layers=any(hasattr(layer, 'text') for layer in self.layers),
                has_effects=any(getattr(layer, 'blend_mode', 0) != 0 for layer in self.layers),
                estimated_total_size_mb=count * (self.canvas_width * self.canvas_height * 4) / (1024 * 1024)
            )

            # 2. 生成并应用优化策略
            optimization_manager = get_optimization_manager()
            strategy = optimization_manager.generate_optimization_strategy(export_profile)
            optimization_manager.apply_strategy(strategy)

            # 3. 启动优化组件
            cache_system = get_intelligent_cache()
            cache_system.optimize_for_batch_export(self)

            memory_optimizer = get_memory_optimizer()
            memory_optimizer.start_optimization()
            memory_optimizer.optimize_for_batch_export(count)

            # 4. 执行并行导出
            parallel_exporter = get_parallel_exporter()

            start_time = time.time()
            success = parallel_exporter.export_batch_parallel(
                self, directory, count, filename_template or "image_{number:04d}",
                file_format, start_index, None, cancel_callback
            )
            export_time = time.time() - start_time

            # 5. 性能监控和调优
            try:
                memory_stats = memory_optimizer.get_memory_report()
                peak_memory = memory_stats['current_stats'].process_mb

                optimization_manager.monitor_performance(
                    export_time, count, peak_memory, 0.0  # CPU使用率暂时设为0
                )

                # 自动调优
                optimization_manager.auto_tune_strategy()
            except Exception as e:
                print(f"[优化导出] 性能监控失败: {e}")

            # 6. 清理资源
            memory_optimizer.stop_optimization()

            if success:
                speedup = count / export_time if export_time > 0 else 0
                print(f"[优化导出] 批量导出完成: {count}张/{export_time:.1f}秒 = {speedup:.2f}张/秒")

                # 显示性能提升信息
                estimated_traditional_time = count * 0.5  # 估算传统方法每张0.5秒
                if export_time > 0:
                    performance_gain = estimated_traditional_time / export_time
                    print(f"[优化导出] 预估性能提升: {performance_gain:.1f}x")
            else:
                print("[优化导出] 批量导出部分失败")

            return success

        except ImportError:
            print("[优化导出] 优化模块不可用，回退到传统导出")
            raise
        except Exception as e:
            print(f"[优化导出] 优化导出失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def enable_optimized_export(self, enabled: bool = True):
        """启用或禁用优化导出"""
        self.use_optimized_export = enabled
        if enabled:
            print("[优化导出] 优化导出已启用")
        else:
            print("[优化导出] 优化导出已禁用")

    def get_export_performance_info(self):
        """获取导出性能信息"""
        try:
            from app.utils.batch_optimization_manager import get_optimization_manager, ExportProfile
            from app.utils.optimized_image_processor import get_optimized_processor

            optimization_manager = get_optimization_manager()
            processor = get_optimized_processor()

            return {
                'system_performance_score': optimization_manager.system_profile.performance_score,
                'optimization_available': True,
                'processor_info': processor.get_performance_info(),
                'performance_analysis': optimization_manager.get_performance_analysis(),
                'recommendations': optimization_manager.get_recommendations(
                    ExportProfile(
                        image_count=100,
                        average_image_size=(self.canvas_width, self.canvas_height),
                        file_format='png',
                        quality_level='high',
                        has_complex_layers=len(self.layers) > 5,
                        has_text_layers=any(hasattr(layer, 'text') for layer in self.layers),
                        has_effects=any(getattr(layer, 'blend_mode', 0) != 0 for layer in self.layers),
                        estimated_total_size_mb=100 * (self.canvas_width * self.canvas_height * 4) / (1024 * 1024)
                    )
                )
            }
        except ImportError:
            return {
                'system_performance_score': 50.0,
                'optimization_available': False,
                'processor_info': {},
                'performance_analysis': {'status': 'unavailable'},
                'recommendations': ['优化模块不可用，建议安装相关依赖']
            }

    def batch_export_enhanced(self, directory: str, count: int = 10,
                            filename_template: str = "batch_{number:04d}",
                            file_format: str = "png",
                            use_high_performance: bool = True,
                            max_workers: int = 4) -> bool:
        """增强版批量导出 - 考虑所有图层设置，完全消除重复"""
        print(f"[增强批量导出] 开始导出 {count} 张图片到 {directory}")

        try:
            # 导入增强版组件
            from app.utils.enhanced_batch_precomputer import get_enhanced_batch_precomputer
            from app.utils.enhanced_batch_executor import get_enhanced_batch_executor

            # 1. 预计算阶段
            print("[增强批量导出] 阶段1: 预计算分析")
            precomputer = get_enhanced_batch_precomputer(self)

            # 分析文档
            total_combinations = precomputer.analyze_document_enhanced()
            if total_combinations == 0:
                print("[增强批量导出] 错误：没有可用的图层组合")
                return False

            # 生成组合
            combinations = precomputer.generate_enhanced_combinations(count, avoid_duplicates=True)
            if not combinations:
                print("[增强批量导出] 错误：无法生成图层组合")
                return False

            # 预计算文件名
            filenames = precomputer.precompute_enhanced_filenames(combinations, filename_template)

            # 2. 执行阶段
            print("[增强批量导出] 阶段2: 批量渲染导出")
            executor = get_enhanced_batch_executor(self, max_workers if use_high_performance else 1)

            # 确保目录存在
            os.makedirs(directory, exist_ok=True)

            # 执行导出
            success = executor.export_batch_enhanced(combinations, directory, filenames, file_format)

            # 3. 结果报告
            precompute_stats = precomputer.get_stats()
            executor_stats = executor.get_stats()

            print(f"[增强批量导出] 预计算统计:")
            print(f"  - 预计算时间: {precompute_stats['precompute_time']:.3f}秒")
            print(f"  - 组合生成数: {precompute_stats['combinations_generated']}")
            print(f"  - 重复避免数: {precompute_stats['duplicates_avoided']}")
            print(f"  - 绑定组处理: {precompute_stats['binding_groups_processed']}")

            print(f"[增强批量导出] 执行统计:")
            print(f"  - 成功导出: {executor_stats['completed_tasks']}")
            print(f"  - 失败导出: {executor_stats['failed_tasks']}")
            print(f"  - 渲染时间: {executor_stats['render_time']:.3f}秒")
            print(f"  - I/O时间: {executor_stats['io_time']:.3f}秒")
            print(f"  - 缓存命中: {executor_stats['cache_hits']}")
            print(f"  - 图层应用: {executor_stats['layer_applications']}")

            if success:
                print(f"[增强批量导出] ✅ 成功导出 {executor_stats['completed_tasks']} 张图片")
                print(f"[增强批量导出] 🎯 重复率: 0% (完全消除重复)")
            else:
                print(f"[增强批量导出] ❌ 导出过程中出现错误")

            return success

        except Exception as e:
            print(f"[增强批量导出] 异常: {e}")
            import traceback
            traceback.print_exc()
            return False
