"""
混合模式管理器
提供多种图层混合模式处理，支持半透明像素正确处理
"""

from PIL import Image, ImageChops, ImageMath
import numpy as np

class BlendModeManager:
    """混合模式管理器，提供不同的图层混合模式"""

    # 混合模式常量
    MODE_NORMAL = 0        # 正常
    MODE_MULTIPLY = 1      # 正片叠底
    MODE_SCREEN = 2        # 滤色
    MODE_OVERLAY = 3       # 叠加
    MODE_SOFT_LIGHT = 4    # 柔光
    MODE_HARD_LIGHT = 5    # 强光
    MODE_COLOR_DODGE = 6   # 颜色减淡
    MODE_COLOR_BURN = 7    # 颜色加深
    MODE_DARKEN = 8        # 变暗
    MODE_LIGHTEN = 9       # 变亮
    MODE_DIFFERENCE = 10   # 差值
    MODE_EXCLUSION = 11    # 排除
    MODE_HUE = 12          # 色相
    MODE_SATURATION = 13   # 饱和度
    MODE_COLOR = 14        # 颜色
    MODE_LUMINOSITY = 15   # 明度

    @staticmethod
    def apply_blend(base, top, mode, preserve_alpha=False, use_premultiplied=True):
        """
        应用混合模式 - 改进版本，支持更精确的半透明处理

        Args:
            base: 底层图像 (PIL.Image)
            top: 顶层图像 (PIL.Image)
            mode: 混合模式 (常量)
            preserve_alpha: 是否保留原始alpha通道
            use_premultiplied: 是否使用预乘alpha算法（推荐）

        Returns:
            PIL.Image: 混合后的图像
        """
        # 确保图像是RGBA模式
        base = base.convert("RGBA")
        top = top.convert("RGBA")

        # 提取alpha通道以备后用
        base_alpha = base.getchannel('A')
        top_alpha = top.getchannel('A')

        # 基本检查
        if base.size != top.size:
            # 如果尺寸不同，将顶层调整为底层尺寸
            top = top.resize(base.size, Image.LANCZOS)

        # 普通模式使用改进的alpha合成
        if mode == BlendModeManager.MODE_NORMAL:
            if use_premultiplied:
                return BlendModeManager._premultiplied_alpha_composite(base, top)
            else:
                return Image.alpha_composite(base, top)

        # 将图像转换为numpy数组，便于处理
        base_array = np.array(base).astype(np.float32) / 255.0
        top_array = np.array(top).astype(np.float32) / 255.0

        # 分离通道
        base_r, base_g, base_b, base_a = base_array[:,:,0], base_array[:,:,1], base_array[:,:,2], base_array[:,:,3]
        top_r, top_g, top_b, top_a = top_array[:,:,0], top_array[:,:,1], top_array[:,:,2], top_array[:,:,3]

        # 混合RGB通道
        result_r, result_g, result_b = None, None, None

        # 根据混合模式应用不同的算法
        if mode == BlendModeManager.MODE_MULTIPLY:
            # 正片叠底
            result_r = base_r * top_r
            result_g = base_g * top_g
            result_b = base_b * top_b
        elif mode == BlendModeManager.MODE_SCREEN:
            # 滤色
            result_r = 1 - (1 - base_r) * (1 - top_r)
            result_g = 1 - (1 - base_g) * (1 - top_g)
            result_b = 1 - (1 - base_b) * (1 - top_b)
        elif mode == BlendModeManager.MODE_OVERLAY:
            # 叠加
            mask_r = base_r < 0.5
            result_r = np.where(mask_r, 2 * base_r * top_r, 1 - 2 * (1 - base_r) * (1 - top_r))
            mask_g = base_g < 0.5
            result_g = np.where(mask_g, 2 * base_g * top_g, 1 - 2 * (1 - base_g) * (1 - top_g))
            mask_b = base_b < 0.5
            result_b = np.where(mask_b, 2 * base_b * top_b, 1 - 2 * (1 - base_b) * (1 - top_b))
        elif mode == BlendModeManager.MODE_DARKEN:
            # 变暗
            result_r = np.minimum(base_r, top_r)
            result_g = np.minimum(base_g, top_g)
            result_b = np.minimum(base_b, top_b)
        elif mode == BlendModeManager.MODE_LIGHTEN:
            # 变亮
            result_r = np.maximum(base_r, top_r)
            result_g = np.maximum(base_g, top_g)
            result_b = np.maximum(base_b, top_b)
        elif mode == BlendModeManager.MODE_DIFFERENCE:
            # 差值
            result_r = np.abs(base_r - top_r)
            result_g = np.abs(base_g - top_g)
            result_b = np.abs(base_b - top_b)
        else:
            # 其他模式暂时使用默认混合
            return Image.alpha_composite(base, top)

        # 改进的alpha通道处理
        if preserve_alpha:
            # 使用更精确的Porter-Duff alpha混合算法
            result_a = base_a + top_a * (1 - base_a)

            # 避免除零错误
            mask = (result_a > 1e-6)

            # 正确的颜色混合公式：考虑预乘alpha
            result_array = np.zeros_like(base_array)

            # 对于有效alpha区域，使用正确的混合公式
            valid_pixels = mask
            if np.any(valid_pixels):
                # 计算混合权重
                base_weight = base_a[valid_pixels] / result_a[valid_pixels]
                top_weight = (top_a * (1 - base_a))[valid_pixels] / result_a[valid_pixels]

                # 混合颜色通道
                result_array[valid_pixels, 0] = (base_r[valid_pixels] * base_weight +
                                               result_r[valid_pixels] * top_weight)
                result_array[valid_pixels, 1] = (base_g[valid_pixels] * base_weight +
                                               result_g[valid_pixels] * top_weight)
                result_array[valid_pixels, 2] = (base_b[valid_pixels] * base_weight +
                                               result_b[valid_pixels] * top_weight)

            result_array[:,:,3] = result_a
        else:
            # 简化的alpha混合，但仍然正确处理透明度
            result_a = top_a + base_a * (1 - top_a)

            # 创建结果数组
            result_array = np.zeros_like(base_array)

            # 正确混合颜色
            mask = (result_a > 1e-6)
            if np.any(mask):
                alpha_ratio = np.where(mask, top_a / result_a, 0)
                result_array[:,:,0] = result_r * alpha_ratio + base_r * (1 - alpha_ratio)
                result_array[:,:,1] = result_g * alpha_ratio + base_g * (1 - alpha_ratio)
                result_array[:,:,2] = result_b * alpha_ratio + base_b * (1 - alpha_ratio)

            result_array[:,:,3] = result_a

        # 将数组转换回图像
        result_array = (result_array * 255).clip(0, 255).astype(np.uint8)
        result_image = Image.fromarray(result_array, mode='RGBA')

        return result_image

    @staticmethod
    def _premultiplied_alpha_composite(base, top):
        """
        使用预乘alpha算法进行更精确的图像合成
        这种方法在处理半透明像素时能提供更好的结果
        """
        import numpy as np

        # 转换为numpy数组
        base_array = np.array(base, dtype=np.float32) / 255.0
        top_array = np.array(top, dtype=np.float32) / 255.0

        # 分离通道
        base_rgb = base_array[:,:,:3]
        base_a = base_array[:,:,3:4]
        top_rgb = top_array[:,:,:3]
        top_a = top_array[:,:,3:4]

        # 预乘alpha
        base_premult = base_rgb * base_a
        top_premult = top_rgb * top_a

        # Porter-Duff "over" 操作
        result_a = top_a + base_a * (1 - top_a)
        result_premult = top_premult + base_premult * (1 - top_a)

        # 反预乘得到最终颜色
        mask = (result_a > 1e-6)
        result_rgb = np.where(mask, result_premult / result_a, 0)

        # 组合结果
        result_array = np.concatenate([result_rgb, result_a], axis=2)
        result_array = (result_array * 255).clip(0, 255).astype(np.uint8)

        return Image.fromarray(result_array, mode='RGBA')