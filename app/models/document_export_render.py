"""``DocumentExportRender`` mixin：渲染相关 + 单图导出。

本 mixin 负责：

- ``render_document``: 渲染文档为 PIL 图像。
- ``export_image``: 单图导出（用 RenderService / ExportService，回退 fast_renderer）。
- ``_render_document_legacy``: render_document 的兼容渲染回退路径。

注意：``export_image`` 用到 ``os`` 用于文件扩展名处理，所以模块顶层需 import。
"""
from __future__ import annotations
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print

import logging
import os

from PIL import Image

logger = logging.getLogger(__name__)


class DocumentExportRender:
    """Document 导出相关：渲染 + 单图导出子 mixin。"""

    def render_document(self):
        """渲染文档为PIL图像。

        统一经由 ``RenderService``（FastRenderer）这一唯一渲染出口，
        保证预览与导出一致的所见即所得效果。仅在渲染服务失败时才回退到
        兼容路径，确保功能可用。
        """
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            return None
        try:
            from app.services.render_service import render_document_to_image

            result = render_document_to_image(self, mode="preview")
            if result.image is not None:
                return result.image
            logger.warning(
                "静默异常已忽略: render_document_to_image 返回空图像，回退兼容渲染",
                exc_info=True,
            )
        except Exception:
            logger.warning(
                "静默异常已忽略: except Exception: in document_export_render.render_document",
                exc_info=True,
            )
        # 渲染服务失败时回退到兼容渲染逻辑，确保功能可用
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
                from app.services.render_service import render_document_legacy_fallback
                image = render_document_legacy_fallback(self, batch_mode=True)

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
