"""
统一图像优化器
提供高效的图像加载、处理和缓存功能

合并了以下模块的功能：
- image_optimizer.py - 图像处理性能优化器
- image_process_optimizer.py - 图像处理优化器
"""
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print

import os
import time
import hashlib
import threading
import weakref
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image, ImageOps, ImageFilter
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from .memory_manager import get_image_cache_manager
from .performance_optimizer import time_it

# 尝试导入高性能库
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import scipy.ndimage as ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class ImageOptimizer:
    """图像处理优化器"""
    
    def __init__(self):
        self._cache_manager = get_image_cache_manager()
        self._lock = threading.Lock()
        self._thumbnail_cache: Dict[str, Image.Image] = {}
        
    def _get_cache_key(self, image_path: str, width: int, height: int, 
                      fit_mode: int = 0, **kwargs) -> str:
        """生成缓存键"""
        # 包含文件修改时间以确保缓存有效性
        try:
            mtime = os.path.getmtime(image_path)
        except OSError:
            mtime = 0
        
        key_data = f"{image_path}_{width}_{height}_{fit_mode}_{mtime}"
        for k, v in sorted(kwargs.items()):
            key_data += f"_{k}_{v}"
        
        return hashlib.md5(key_data.encode()).hexdigest()
    
    @time_it
    def load_image_optimized(self, image_path: str, target_size: Tuple[int, int],
                           fit_mode: int = 0, use_cache: bool = True) -> Optional[Image.Image]:
        """优化的图像加载方法"""
        if not os.path.exists(image_path):
            return None
        
        width, height = target_size
        cache_key = self._get_cache_key(image_path, width, height, fit_mode)
        
        # 🔧 关键修复：禁用图像优化器缓存获取，避免重复图片问题
        # 注释掉缓存获取，确保每次都重新处理
        # if use_cache:
        #     cached_image = self._cache_manager.get(cache_key)
        #     if cached_image:
        #         return cached_image.copy()  # 返回副本以避免修改缓存
        
        try:
            # 使用优化的加载策略
            image = self._load_image_smart(image_path, target_size)
            if image is None:
                return None
            
            # 应用适配模式
            processed_image = self._apply_fit_mode(image, target_size, fit_mode)
            
            # 🔧 关键修复：禁用图像优化器缓存存储，避免重复图片问题
            # 注释掉缓存存储，确保每次都重新处理
            # if use_cache and processed_image:
            #     # 估算图像大小（MB）
            #     size_mb = (processed_image.width * processed_image.height * 4) / (1024 * 1024)
            #     self._cache_manager.put(cache_key, processed_image.copy(), size_mb)
            
            return processed_image
            
        except Exception as e:
            print(f"图像加载失败 {image_path}: {e}")
            return None
    
    def _load_image_smart(self, image_path: str, target_size: Tuple[int, int]) -> Optional[Image.Image]:
        """智能图像加载，根据目标尺寸优化加载策略"""
        try:
            # 首先获取图像信息而不加载完整图像
            with Image.open(image_path) as img:
                original_size = img.size
                
            # 如果原图比目标尺寸大很多，使用缩略图加载
            width_ratio = original_size[0] / target_size[0]
            height_ratio = original_size[1] / target_size[1]
            max_ratio = max(width_ratio, height_ratio)
            
            if max_ratio > 4:  # 原图比目标大4倍以上
                # 使用PIL的draft模式进行快速缩放
                with Image.open(image_path) as img:
                    # 计算合适的draft尺寸
                    draft_size = (
                        int(original_size[0] / (max_ratio / 2)),
                        int(original_size[1] / (max_ratio / 2))
                    )
                    img.draft('RGB', draft_size)
                    image = img.convert('RGBA')
            else:
                # 正常加载
                with Image.open(image_path) as img:
                    image = img.convert('RGBA')
            
            return image
            
        except Exception as e:
            print(f"智能图像加载失败 {image_path}: {e}")
            return None
    
    def _apply_fit_mode(self, image: Image.Image, target_size: Tuple[int, int],
                       fit_mode: int) -> Image.Image:
        """应用适配模式"""
        target_width, target_height = target_size

        if fit_mode == 0:  # 智能裁剪
            return self._smart_crop(image, target_size)
        elif fit_mode == 1:  # 智能缩放不裁剪
            return self._smart_fit(image, target_size)
        elif fit_mode == 2:  # 智能适配不缩放
            # 🔧 关键修复：保持原图尺寸返回，避免拉伸变形。
            # 渲染管线会按图层尺寸创建画布并将原图居中放置。
            return image.copy() if hasattr(image, 'copy') else image
        else:  # 拉伸
            return image.resize(target_size, Image.LANCZOS)
    
    def _smart_crop(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """智能裁剪（等比缩放后裁剪）"""
        target_width, target_height = target_size
        image_width, image_height = image.size

        # 计算缩放比例（统一比例保证等比）
        scale_x = target_width / image_width
        scale_y = target_height / image_height
        # 关键：主方向边长直接钉到目标尺寸，另一条边用源图比例反推，
        # 保证 new_width/new_height == image_width/image_height，
        # 避免 int() 对宽高分别取整造成的细微各向异性拉伸。
        if scale_x >= scale_y:
            new_width = target_width
            new_height = max(1, int(round(new_width * image_height / image_width)))
        else:
            new_height = target_height
            new_width = max(1, int(round(new_height * image_width / image_height)))

        scaled_image = image.resize((new_width, new_height), Image.LANCZOS)

        # 居中裁剪
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        return scaled_image.crop((left, top, right, bottom))
    
    def _smart_fit(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """智能缩放不裁剪"""
        target_width, target_height = target_size
        image_width, image_height = image.size

        # 计算缩放比例（统一比例保证等比）
        scale_x = target_width / image_width
        scale_y = target_height / image_height
        # 关键：限制方向边长直接钉到目标尺寸，另一条边用源图比例反推，
        # 保证 new_width/new_height == image_width/image_height，
        # 避免 int() 对宽高分别取整造成的细微各向异性拉伸。
        if scale_x <= scale_y:
            new_width = target_width
            new_height = max(1, int(round(new_width * image_height / image_width)))
        else:
            new_height = target_height
            new_width = max(1, int(round(new_height * image_width / image_height)))

        scaled_image = image.resize((new_width, new_height), Image.LANCZOS)

        # 创建目标尺寸的透明背景
        result = Image.new('RGBA', target_size, (0, 0, 0, 0))

        # 居中粘贴
        x = (target_width - new_width) // 2
        y = (target_height - new_height) // 2
        result.paste(scaled_image, (x, y), scaled_image)

        return result
    
    def get_thumbnail(self, image_path: str, size: Tuple[int, int] = (128, 128)) -> Optional[Image.Image]:
        """获取缩略图"""
        cache_key = f"thumb_{self._get_cache_key(image_path, size[0], size[1])}"
        
        with self._lock:
            if cache_key in self._thumbnail_cache:
                return self._thumbnail_cache[cache_key].copy()
        
        try:
            with Image.open(image_path) as img:
                img.thumbnail(size, Image.LANCZOS)
                thumbnail = img.convert('RGBA')
            
            with self._lock:
                self._thumbnail_cache[cache_key] = thumbnail.copy()
            
            return thumbnail
            
        except Exception as e:
            print(f"缩略图生成失败 {image_path}: {e}")
            return None
    
    def preload_images(self, image_paths: list, target_size: Tuple[int, int]):
        """预加载图像（异步）"""
        def preload_worker():
            for path in image_paths:
                if os.path.exists(path):
                    self.load_image_optimized(path, target_size, use_cache=True)
        
        # 🔧 关键修夏：不再使用daemon=True，避免程序退出时的锁竞争问题
        thread = threading.Thread(target=preload_worker)
        # thread.daemon = True  # 已移除daemon=True
        thread.start()
    
    def clear_cache(self):
        """清理所有缓存"""
        self._cache_manager.clear()
        with self._lock:
            for img in self._thumbnail_cache.values():
                if hasattr(img, 'close'):
                    img.close()
            self._thumbnail_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        cache_stats = self._cache_manager.get_stats()
        with self._lock:
            thumbnail_count = len(self._thumbnail_cache)
        
        return {
            'image_cache': cache_stats,
            'thumbnail_count': thumbnail_count
        }


class ProcessCache:
    """图像处理结果缓存（从image_process_optimizer.py合并）"""

    def __init__(self, max_size: int = 50):
        self._cache = {}
        self._access_times = {}
        self._max_size = max_size
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _generate_process_key(self, operation: str, image_id: str, params: Dict) -> str:
        """生成处理操作的缓存键"""
        try:
            param_str = "|".join(f"{k}:{v}" for k, v in sorted(params.items()))
            key_string = f"{operation}:{image_id}:{param_str}"
            return hashlib.md5(key_string.encode()).hexdigest()[:16]
        except Exception:
            return f"{operation}_{time.time()}"

    def get(self, operation: str, image_id: str, params: Dict) -> Optional[Any]:
        """获取缓存的处理结果"""
        with self._lock:
            key = self._generate_process_key(operation, image_id, params)
            if key in self._cache:
                self._access_times[key] = time.time()
                self._hits += 1
                return self._cache[key]

            self._misses += 1
            return None

    def put(self, operation: str, image_id: str, params: Dict, result: Any):
        """存储处理结果到缓存"""
        with self._lock:
            key = self._generate_process_key(operation, image_id, params)

            # 清理旧缓存
            while len(self._cache) >= self._max_size:
                oldest_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
                del self._cache[oldest_key]
                del self._access_times[oldest_key]

            self._cache[key] = result
            self._access_times[key] = time.time()

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0

            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate
            }


class ImageProcessOptimizer:
    """图像处理优化器（从image_process_optimizer.py合并）"""

    def __init__(self, cache_size: int = 50, max_workers: int = None):
        self._process_cache = ProcessCache(cache_size)
        
        # 使用智能线程池管理器
        try:
            from .intelligent_thread_pool_manager import get_thread_pool_manager
            self._thread_pool_manager = get_thread_pool_manager()
            
            # 如果指定了max_workers，临时覆盖配置
            if max_workers is not None:
                from .intelligent_thread_pool_manager import PoolConfig, TaskType
                from .thread_pool_config import get_config_manager
                
                config_manager = get_config_manager()
                custom_config = PoolConfig(
                    max_workers=max_workers,
                    min_workers=1,
                    idle_timeout=60.0,
                    queue_size=100,
                    auto_scale=True
                )
                config_manager.set_pool_config(TaskType.IO_INTENSIVE, custom_config)
            
            # 针对图像处理优化
            self._thread_pool_manager.optimize_for_workload('image_processing')
            
            # 获取实际配置
            pool_status = self._thread_pool_manager.get_pool_status()
            actual_workers = pool_status['pools'].get('io_intensive', {}).get('max_workers', 4)
            
            print(f"[ImageOptimizer] 智能线程池初始化，工作线程: {actual_workers}")
            
        except ImportError:
            # 回退到传统 ThreadPoolExecutor
            actual_workers = max_workers or 4
            self._thread_pool = ThreadPoolExecutor(max_workers=actual_workers)
            self._thread_pool_manager = None
            print(f"[ImageOptimizer] 使用传统线程池，工作线程: {actual_workers}")
        
        self._lock = threading.RLock()

    def _get_image_id(self, image: Image.Image) -> str:
        """生成图像的唯一标识"""
        try:
            # 使用图像的基本属性生成ID
            img_array = np.array(image)
            img_hash = hashlib.md5(img_array.tobytes()).hexdigest()[:16]
            return f"{image.size[0]}x{image.size[1]}_{img_hash}"
        except Exception:
            return f"{id(image)}_{time.time()}"

    @time_it
    def optimized_resize(self, image: Image.Image, target_size: Tuple[int, int],
                        method: str = 'lanczos', use_cache: bool = True) -> Image.Image:
        """优化的图像缩放"""
        if not use_cache:
            return self._resize_image(image, target_size, method)

        image_id = self._get_image_id(image)
        params = {'target_size': target_size, 'method': method}

        # 尝试从缓存获取
        cached_result = self._process_cache.get('resize', image_id, params)
        if cached_result is not None:
            return cached_result.copy()

        # 执行缩放
        result = self._resize_image(image, target_size, method)

        # 存储到缓存
        self._process_cache.put('resize', image_id, params, result.copy())

        return result

    def _resize_image(self, image: Image.Image, target_size: Tuple[int, int], method: str) -> Image.Image:
        """执行图像缩放"""
        if method == 'lanczos':
            return image.resize(target_size, Image.LANCZOS)
        elif method == 'bicubic':
            return image.resize(target_size, Image.BICUBIC)
        elif method == 'bilinear':
            return image.resize(target_size, Image.BILINEAR)
        elif method == 'nearest':
            return image.resize(target_size, Image.NEAREST)
        else:
            return image.resize(target_size, Image.LANCZOS)

    @time_it
    def optimized_filter(self, image: Image.Image, filter_type: str,
                        params: Dict[str, Any] = None, use_cache: bool = True) -> Image.Image:
        """优化的图像滤镜处理"""
        if params is None:
            params = {}

        if not use_cache:
            return self._apply_filter(image, filter_type, params)

        image_id = self._get_image_id(image)
        cache_params = {'filter_type': filter_type, **params}

        # 尝试从缓存获取
        cached_result = self._process_cache.get('filter', image_id, cache_params)
        if cached_result is not None:
            return cached_result.copy()

        # 执行滤镜
        result = self._apply_filter(image, filter_type, params)

        # 存储到缓存
        self._process_cache.put('filter', image_id, cache_params, result.copy())

        return result

    def _apply_filter(self, image: Image.Image, filter_type: str, params: Dict[str, Any]) -> Image.Image:
        """执行滤镜处理"""
        try:
            if filter_type == 'blur':
                radius = params.get('radius', 1.0)
                return image.filter(ImageFilter.GaussianBlur(radius=radius))
            elif filter_type == 'sharpen':
                return image.filter(ImageFilter.SHARPEN)
            elif filter_type == 'edge_enhance':
                return image.filter(ImageFilter.EDGE_ENHANCE)
            elif filter_type == 'smooth':
                return image.filter(ImageFilter.SMOOTH)
            else:
                return image
        except Exception as e:
            print(f"[图像处理优化] 滤镜处理失败: {e}")
            return image

    def clear_cache(self):
        """清空处理缓存"""
        self._process_cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return self._process_cache.get_stats()


# 全局实例
_image_optimizer = None
_process_optimizer = None

def get_image_optimizer() -> ImageOptimizer:
    """获取全局图像优化器实例"""
    global _image_optimizer
    if _image_optimizer is None:
        _image_optimizer = ImageOptimizer()
    return _image_optimizer

def get_process_optimizer() -> ImageProcessOptimizer:
    """获取全局图像处理优化器实例"""
    global _process_optimizer
    if _process_optimizer is None:
        _process_optimizer = ImageProcessOptimizer()
    return _process_optimizer
