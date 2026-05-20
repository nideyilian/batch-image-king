
import numpy as np
from PIL import Image, ImageFilter
from typing import Tuple, Optional

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
        # Convert to float32 for precision
        arr = np.array(image, dtype=np.float32) / 255.0
        
        # Separate channels
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3:4]
        
        # Premultiply Alpha
        # RGB = RGB * Alpha
        premul_rgb = rgb * alpha
        
        # Stack back to RGBA
        premul_img_arr = np.concatenate([premul_rgb, alpha], axis=2)
        
        # Convert back to PIL for resizing (PIL's Lanczos is very good)
        premul_img = Image.fromarray((np.clip(premul_img_arr, 0.0, 1.0) * 255.0).astype(np.uint8), 'RGBA')
        
        # Resize
        resized_premul = premul_img.resize(target_size, method)
        
        # Un-premultiply
        resized_arr = np.array(resized_premul, dtype=np.float32) / 255.0
        r_rgb = resized_arr[:, :, :3]
        r_alpha = resized_arr[:, :, 3:4]
        
        # Avoid division by zero
        mask = r_alpha > 1e-6
        
        # Restore original RGB where alpha > 0
        unpremul_rgb = np.zeros_like(r_rgb)
        
        # Vectorized un-premultiply
        # RGB = RGB_premul / Alpha
        # Note: We need to be careful with broadcasting
        # r_rgb[mask] is flattened, so we need to handle it carefully or just use boolean indexing
        # The mask is (H, W, 1), r_rgb is (H, W, 3).
        
        # Simplified loop-free implementation
        # Expand mask to 3 channels
        mask_3ch = np.repeat(mask, 3, axis=2)
        
        np.divide(r_rgb, r_alpha, out=unpremul_rgb, where=mask_3ch)
        
        # Recombine
        result_arr = np.concatenate([unpremul_rgb, r_alpha], axis=2)
        
        # Convert to uint8
        result_image = Image.fromarray((np.clip(result_arr, 0.0, 1.0) * 255.0).astype(np.uint8), 'RGBA')
        
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
        # Convert to float32
        arr = np.array(image, dtype=np.float32) / 255.0
        
        # Premultiply
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3:4]
        premul_rgb = rgb * alpha
        premul_arr = np.concatenate([premul_rgb, alpha], axis=2)
        
        # Back to PIL
        premul_img = Image.fromarray((np.clip(premul_arr, 0.0, 1.0) * 255.0).astype(np.uint8), 'RGBA')
        
        # Rotate
        rotated = premul_img.rotate(angle, resample=resample, expand=expand, fillcolor=(0,0,0,0))
        
        # Un-premultiply
        rot_arr = np.array(rotated, dtype=np.float32) / 255.0
        r_rgb = rot_arr[:, :, :3]
        r_alpha = rot_arr[:, :, 3:4]
        
        mask = r_alpha > 1e-6
        unpremul_rgb = np.zeros_like(r_rgb)
        
        mask_3ch = np.repeat(mask, 3, axis=2)
        np.divide(r_rgb, r_alpha, out=unpremul_rgb, where=mask_3ch)
        
        result_arr = np.concatenate([unpremul_rgb, r_alpha], axis=2)
        
        return Image.fromarray((np.clip(result_arr, 0.0, 1.0) * 255.0).astype(np.uint8), 'RGBA')
