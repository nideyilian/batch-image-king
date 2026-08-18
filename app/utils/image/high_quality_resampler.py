
from PIL import Image, ImageFilter
from typing import Tuple

from app.utils.rgba_resampler import resize_rgba_premultiplied, rotate_rgba_premultiplied

class HighQualityResampler:
    """
    High Quality Image Resampler
    
    Provides industry-standard image resizing algorithms with a focus on:
    1. Edge integrity (via Premultiplied Alpha)
    2. Detail preservation (via Lanczos/Bicubic)
    3. Anti-aliasing (via Super-sampling for small images)
    """

    @staticmethod
    def resize(image: Image.Image, 
               target_size: Tuple[int, int], 
               method: int = Image.LANCZOS,
               enable_premultiplied: bool = True,
               enable_sharpening: bool = False) -> Image.Image:
        """
        Resize image with high quality settings.
        
        Args:
            image: Source PIL Image
            target_size: (width, height)
            method: PIL Resampling method (default: LANCZOS)
            enable_premultiplied: Use premultiplied alpha to prevent dark edges (default: True)
            enable_sharpening: Apply subtle sharpening after resizing (default: False)
            
        Returns:
            Resized PIL Image
        """
        if image is None:
            return None
            
        if image.size == target_size:
            return image

        # Handle Transparent Images (RGBA)
        if enable_premultiplied and image.mode == 'RGBA':
            return HighQualityResampler._resize_rgba_premultiplied(image, target_size, method, enable_sharpening)
        else:
            resized = image.resize(target_size, method)
            if enable_sharpening:
                resized = HighQualityResampler._apply_smart_sharpen(resized)
            return resized

    @staticmethod
    def _resize_rgba_premultiplied(image: Image.Image, 
                                 target_size: Tuple[int, int], 
                                 method: int = Image.LANCZOS,
                                 enable_sharpening: bool = False) -> Image.Image:
        """
        Resize RGBA image using Premultiplied Alpha to avoid dark borders.
        """
        result_image = resize_rgba_premultiplied(image, target_size, method)
        
        if enable_sharpening:
            result_image = HighQualityResampler._apply_smart_sharpen(result_image)
            
        return result_image

    @staticmethod
    def _apply_smart_sharpen(image: Image.Image) -> Image.Image:
        """Apply subtle Unsharp Mask to restore details lost during resampling."""
        # Radius 0.5-0.8 is usually good for digital content
        # Percent 50-80% is subtle enough
        return image.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=2))

    @staticmethod
    def rotate_high_quality(image: Image.Image, 
                           angle: float, 
                           expand: bool = False,
                           resample: int = Image.BICUBIC,
                           enable_premultiplied: bool = True) -> Image.Image:
        """
        Rotate image with high quality.
        """
        if abs(angle) < 0.01:
            return image
            
        if enable_premultiplied and image.mode == 'RGBA':
            return HighQualityResampler._rotate_rgba_premultiplied(image, angle, expand, resample)
        else:
            return image.rotate(angle, resample=resample, expand=expand, fillcolor=(0,0,0,0))

    @staticmethod
    def _rotate_rgba_premultiplied(image: Image.Image, 
                                 angle: float,
                                 expand: bool = False,
                                 resample: int = Image.BICUBIC) -> Image.Image:
        """Rotate RGBA image using Premultiplied Alpha."""
        return rotate_rgba_premultiplied(
            image,
            angle,
            resample=resample,
            expand=expand,
            fillcolor=(0, 0, 0, 0),
        )
