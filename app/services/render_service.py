"""唯一渲染出口（Single Render Exit Point）。

架构约定（P1 收敛）：
- 全项目**所有**文档渲染（预览 / 导出 / 缩略图）都必须经由本模块的
  ``RenderService``（底层引擎为 ``FastRenderer``），禁止再散用
  ``document.render_composition`` 等历史实现，避免"预览≠导出"的不一致。
- 新代码统一调用便捷函数 :func:`render_document_to_image`；需要更细控制时直接构造
  ``RenderRequest`` 交给 :meth:`RenderService.render`。
- ``RenderService.render`` 内部已自带兜底：FastRenderer 失败时回退到
  ``document.render_composition``，保证功能不中断。

历史实现现状：
- 旧的 ``app.models.document_renderer.DocumentRenderer`` 已于 R5 删除（P2 收敛），
  所有渲染统一收敛到本 ``RenderService`` 单一路出口。
- ``Document.render_composition`` 仅作为 ``RenderService`` 的兜底路径存在。
"""

from __future__ import annotations

# Architecture note:
# RenderService is the standard render boundary. Interactive canvas preview uses
# app.services.preview_render_service as a separate latency-oriented boundary.
# Direct FastRenderer imports outside these services should be treated as
# explicit exceptions and covered by contract tests.

from dataclasses import dataclass
import time
from typing import Callable, Optional

from PIL import Image

from app.services.render_quality import normalize_quality_profile
from app.utils.error_handling import ErrorCategory, handle_core_exception

import logging

logger = logging.getLogger(__name__)


CancelCallback = Optional[Callable[[], bool]]


@dataclass(frozen=True)
class RenderRequest:
    document: object
    mode: str = "preview"  # preview | export
    quality_profile: str = "quality"  # quality | balanced | speed | size
    batch_mode: bool = False
    renderer: Optional[object] = None
    force_refresh: bool = False
    interactive_low_quality: bool = False
    cancel_callback: CancelCallback = None


@dataclass
class RenderResult:
    image: Optional[Image.Image]
    elapsed: float = 0.0
    cache_hit: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.image is not None and not self.error


class RenderService:
    """Facade for preview/export rendering."""

    def render(self, request: RenderRequest) -> RenderResult:
        start = time.time()
        quality_profile = normalize_quality_profile(request.quality_profile)
        if request.cancel_callback and request.cancel_callback():
            return RenderResult(None, 0.0, False, "渲染已取消")

        try:
            renderer = request.renderer
            if renderer is None:
                from app.utils.fast_renderer import get_global_fast_renderer

                renderer = get_global_fast_renderer()
            if request.mode == "preview":
                image = renderer.render_preview(
                    request.document,
                    force_refresh=request.force_refresh,
                    interactive_low_quality=request.interactive_low_quality,
                )
            else:
                image = renderer.render_batch(request.document)

            if request.cancel_callback and request.cancel_callback():
                return RenderResult(None, time.time() - start, False, "渲染已取消")
            return RenderResult(image, time.time() - start)
        except Exception as primary_error:
            handle_core_exception(
                primary_error,
                context=f"RenderService primary renderer ({request.mode})",
                category=ErrorCategory.INTERNAL_FALLBACK,
                logger=logger,
            )
            try:
                image = render_document_legacy_fallback(
                    request.document,
                    batch_mode=bool(request.batch_mode),
                    use_advanced_quality=quality_profile == "quality",
                )
                return RenderResult(image, time.time() - start, error="" if image is not None else str(primary_error))
            except Exception as fallback_error:
                handle_core_exception(
                    fallback_error,
                    context=f"RenderService legacy fallback ({request.mode})",
                    category=ErrorCategory.USER_VISIBLE,
                    logger=logger,
                )
                return RenderResult(None, time.time() - start, False, str(fallback_error or primary_error))


_render_service: Optional[RenderService] = None


def render_document_legacy_fallback(
    document: object,
    batch_mode: bool = False,
    use_advanced_quality: bool = True,
) -> Optional[Image.Image]:
    """The only sanctioned legacy ``render_composition`` fallback."""
    return document.render_composition(
        random_mode=False,
        optimize_memory=bool(batch_mode),
        use_advanced_quality=bool(use_advanced_quality),
        is_batch_mode=bool(batch_mode),
        enable_gpu=False,
    )


def get_render_service() -> RenderService:
    global _render_service
    if _render_service is None:
        _render_service = RenderService()
    return _render_service


def render_layer_with_auto_mask(document: object, layer: object, relation: object):
    """通过统一渲染边界生成应用自动遮罩后的单图层 surface。"""
    renderer = (
        getattr(document, "fast_renderer", None)
        or getattr(document, "renderer", None)
        or getattr(document, "_renderer", None)
    )
    if renderer is None:
        from app.utils.fast_renderer import get_global_fast_renderer

        renderer = get_global_fast_renderer()
    if renderer is None:
        return None
    surface = renderer._get_layer_surface_cached(layer, document, False)
    if surface is None:
        return None
    return renderer._apply_auto_mask(surface, relation)


def render_document_to_image(
    document: object,
    mode: str = "preview",
    quality_profile: str = "quality",
    batch_mode: bool = False,
    force_refresh: bool = False,
    cancel_callback: CancelCallback = None,
) -> "RenderResult":
    """唯一渲染出口的便捷函数：把文档渲染成 PIL 图像。

    所有预览 / 导出 / 缩略图渲染都应调用本函数，而不是自行 new 一个渲染器。
    返回的 ``RenderResult.image`` 为渲染结果（失败/取消时为 ``None``）。

    Args:
        document: 实现了渲染所需属性的文档对象（``canvas_width/height``、``layers`` 等）。
        mode: ``"preview"`` 或 ``"export"``。
        quality_profile: ``quality`` / ``balanced`` / ``speed`` / ``size``。
        batch_mode: 是否批量模式（影响缓存与内存策略）。
        force_refresh: 是否强制重渲染（跳过预览缓存）。
        cancel_callback: 可调用对象，返回 ``True`` 时中止渲染。
    """
    return get_render_service().render(
        RenderRequest(
            document=document,
            mode=mode,
            quality_profile=quality_profile,
            batch_mode=batch_mode,
            force_refresh=force_refresh,
            cancel_callback=cancel_callback,
        )
    )
