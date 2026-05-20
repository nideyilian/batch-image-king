"""
图层图像加载模块

负责图层图像的加载和适配
"""

import os
import glob
import random
from typing import Optional, List, Tuple
from PIL import Image
from PIL.Image import Resampling
from app.utils.image.high_quality_resampler import HighQualityResampler


class LayerImageLoader:
    """
    图层图像加载器
    
    负责从文件或文件夹加载图像，并进行基本的适配处理。
    """
    
    # 支持的图像格式
    SUPPORTED_FORMATS = [
        '*.png', '*.jpg', '*.jpeg', '*.bmp', 
        '*.gif', '*.tiff', '*.webp'
    ]
    
    @staticmethod
    def load_image_from_path(image_path: str) -> Optional[Image.Image]:
        """
        从路径加载图像
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            PIL图像对象，失败返回None
        """
        try:
            if not os.path.exists(image_path):
                print(f"[LayerImageLoader] 文件不存在: {image_path}")
                return None
            
            # 加载图像（在 with 块内完成 decode + copy，避免文件句柄关闭后延迟读取失败）
            with Image.open(image_path) as img:
                rgba = img.convert('RGBA') if img.mode != 'RGBA' else img.copy()
                # 强制解码到内存，规避后续 copy/resize 时触发底层 seek(None)
                rgba.load()
                return rgba.copy()
            
        except Exception as e:
            print(f"[LayerImageLoader] 加载图像失败 {image_path}: {e}")
            return None
    
    @staticmethod
    def get_images_from_folder(folder_path: str, 
                                sort: bool = True,
                                recursive: bool = False) -> List[str]:
        """
        从文件夹获取图像列表
        
        Args:
            folder_path: 文件夹路径
            sort: 是否排序
            recursive: 是否递归子文件夹
            
        Returns:
            图像文件路径列表
        """
        if not os.path.exists(folder_path):
            print(f"[LayerImageLoader] 文件夹不存在: {folder_path}")
            return []
        
        images = []
        
        # 搜索模式
        pattern = '**' if recursive else '*'
        
        # 遍历所有支持的格式
        for fmt in LayerImageLoader.SUPPORTED_FORMATS:
            search_pattern = os.path.join(folder_path, pattern, fmt)
            found_files = glob.glob(search_pattern, recursive=recursive)
            images.extend(found_files)
        
        # 排序
        if sort:
            images.sort()
        
        return images
    
    @staticmethod
    def get_random_image_from_folder(folder_path: str) -> Optional[str]:
        """
        从文件夹随机获取一张图像
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            随机图像路径，如果文件夹为空返回None
        """
        images = LayerImageLoader.get_images_from_folder(folder_path, sort=False)
        
        if not images:
            return None
        
        return random.choice(images)
    
    @staticmethod
    def resize_image(image: Image.Image,
                    target_width: int,
                    target_height: int,
                    fit_mode: int = 0,
                    crop_direction: int = 0) -> Image.Image:
        """
        调整图像大小
        
        Args:
            image: 原始图像
            target_width: 目标宽度
            target_height: 目标高度
            fit_mode: 适配模式 (0=智能裁剪, 1=智能适配)
            crop_direction: 裁剪方向 (0=居中, 1=顶部, 2=底部, 3=左侧, 4=右侧)
            
        Returns:
            调整后的图像
        """
        if fit_mode == 0:  # 智能裁剪
            return LayerImageLoader._resize_with_crop(
                image, target_width, target_height, crop_direction
            )
        else:  # 智能适配（不裁剪）
            return LayerImageLoader._resize_with_fit(
                image, target_width, target_height
            )
    
    @staticmethod
    def _resize_with_crop(image: Image.Image,
                         target_width: int,
                         target_height: int,
                         crop_direction: int = 0) -> Image.Image:
        """
        等比缩放后裁剪
        
        Args:
            image: 原始图像
            target_width: 目标宽度
            target_height: 目标高度
            crop_direction: 裁剪方向
            
        Returns:
            调整后的图像
        """
        # 计算缩放比例（取较大的，确保覆盖目标区域）
        scale_w = target_width / image.width
        scale_h = target_height / image.height
        scale = max(scale_w, scale_h)
        
        # 缩放图像
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)
        resized = HighQualityResampler.resize(image, (new_width, new_height), method=Resampling.LANCZOS, enable_sharpening=True)
        
        # 裁剪
        if crop_direction == 0:  # 居中裁剪
            left = (new_width - target_width) // 2
            top = (new_height - target_height) // 2
        elif crop_direction == 1:  # 顶部对齐
            left = (new_width - target_width) // 2
            top = 0
        elif crop_direction == 2:  # 底部对齐
            left = (new_width - target_width) // 2
            top = new_height - target_height
        elif crop_direction == 3:  # 左侧对齐
            left = 0
            top = (new_height - target_height) // 2
        else:  # 右侧对齐
            left = new_width - target_width
            top = (new_height - target_height) // 2
        
        right = left + target_width
        bottom = top + target_height
        
        return resized.crop((left, top, right, bottom))
    
    @staticmethod
    def _resize_with_fit(image: Image.Image,
                        target_width: int,
                        target_height: int) -> Image.Image:
        """
        等比缩放适配（不裁剪，居中）
        
        Args:
            image: 原始图像
            target_width: 目标宽度
            target_height: 目标高度
            
        Returns:
            调整后的图像
        """
        # 计算缩放比例（取较小的，确保完全显示）
        scale_w = target_width / image.width
        scale_h = target_height / image.height
        scale = min(scale_w, scale_h)
        
        # 缩放图像
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)
        resized = HighQualityResampler.resize(image, (new_width, new_height), method=Resampling.LANCZOS, enable_sharpening=True)
        
        # 创建目标画布（透明背景）
        result = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
        
        # 居中粘贴
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        result.paste(resized, (paste_x, paste_y), resized)
        
        return result
    
    @staticmethod
    def load_and_adapt_image(source: str,
                            is_folder: bool,
                            target_width: int,
                            target_height: int,
                            fit_mode: int = 0,
                            crop_direction: int = 0,
                            specific_image: Optional[str] = None) -> Optional[Image.Image]:
        """
        加载并适配图像（一站式方法）
        
        Args:
            source: 图像源（文件或文件夹路径）
            is_folder: 是否为文件夹
            target_width: 目标宽度
            target_height: 目标高度
            fit_mode: 适配模式
            crop_direction: 裁剪方向
            specific_image: 指定图像路径（仅当is_folder为True时有效）
            
        Returns:
            适配后的图像，失败返回None
        """
        try:
            # 确定图像路径
            if is_folder:
                if specific_image:
                    image_path = specific_image
                else:
                    image_path = LayerImageLoader.get_random_image_from_folder(source)
                    if not image_path:
                        print(f"[LayerImageLoader] 文件夹为空: {source}")
                        return None
            else:
                image_path = source
            
            # 加载图像
            image = LayerImageLoader.load_image_from_path(image_path)
            if not image:
                return None
            
            # 调整大小
            adapted = LayerImageLoader.resize_image(
                image, target_width, target_height, fit_mode, crop_direction
            )
            
            return adapted
            
        except Exception as e:
            print(f"[LayerImageLoader] 加载并适配图像失败: {e}")
            return None


if __name__ == "__main__":
    # 测试代码
    loader = LayerImageLoader()
    
    # 测试获取文件夹图像
    images = loader.get_images_from_folder("./test_images")
    print(f"找到 {len(images)} 张图像")
    
    # 测试加载图像
    if images:
        image = loader.load_image_from_path(images[0])
        if image:
            print(f"图像尺寸: {image.size}")
            
            # 测试调整大小
            resized = loader.resize_image(image, 200, 200, fit_mode=0)
            print(f"调整后尺寸: {resized.size}")

