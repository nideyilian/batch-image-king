"""Unified rendering service facade.

The project still has several historical rendering entry points. This service
gives new code a single request/result API while delegating to the existing
renderer implementations underneath.
"""

from __future__ import annotations

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
