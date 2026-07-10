"""Preview rendering boundary.

Interactive canvas rendering is allowed to use FastRenderer's preview-only
entry points for latency. UI code should call this service instead of importing
FastRenderer directly.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Optional

from PIL import Image

from app.services.render_service import render_document_legacy_fallback

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewRenderRequest:
    document: object
    force_refresh: bool = False
    interactive_low_quality: bool = False
    active_layer_index: int = -1


@dataclass
class PreviewRenderResult:
    image: Optional[Image.Image]
    elapsed: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.image is not None and not self.error


class PreviewRenderService:
    """Facade for canvas and thumbnail preview rendering."""

    def render(self, request: PreviewRenderRequest) -> PreviewRenderResult:
        start = time.time()
        primary_error = None
        try:
            from app.utils.fast_renderer import get_global_fast_renderer

            renderer = get_global_fast_renderer()
            if request.interactive_low_quality and request.active_layer_index >= 0:
                image = renderer.render_preview_incremental(
                    request.document,
                    active_layer_index=request.active_layer_index,
                    force_refresh=request.force_refresh,
                    interactive_low_quality=True,
                )
            elif request.interactive_low_quality:
                image = renderer.render_preview_live(
                    request.document,
                    interactive_low_quality=True,
                )
            else:
                image = renderer.render_preview(
                    request.document,
                    force_refresh=request.force_refresh,
                    interactive_low_quality=request.interactive_low_quality,
                )
            if image is not None:
                return PreviewRenderResult(image, time.time() - start)
        except Exception as exc:
            primary_error = exc
            logger.warning("Preview FastRenderer failed; falling back to legacy render", exc_info=True)

        try:
            image = render_document_legacy_fallback(request.document)
            return PreviewRenderResult(
                image,
                time.time() - start,
                "" if image is not None else str(primary_error or "preview renderer returned no image"),
            )
        except Exception as exc:
            logger.warning("Preview legacy fallback failed", exc_info=True)
            return PreviewRenderResult(None, time.time() - start, str(exc or primary_error))

    def clear_cache(self) -> None:
        from app.utils.fast_renderer import get_global_fast_renderer

        renderer = get_global_fast_renderer()
        if hasattr(renderer, "clear_cache"):
            renderer.clear_cache()


_preview_render_service: Optional[PreviewRenderService] = None


def get_preview_render_service() -> PreviewRenderService:
    global _preview_render_service
    if _preview_render_service is None:
        _preview_render_service = PreviewRenderService()
    return _preview_render_service


def render_preview_to_image(
    document: object,
    *,
    force_refresh: bool = False,
    interactive_low_quality: bool = False,
    active_layer_index: int = -1,
) -> PreviewRenderResult:
    return get_preview_render_service().render(
        PreviewRenderRequest(
            document=document,
            force_refresh=force_refresh,
            interactive_low_quality=interactive_low_quality,
            active_layer_index=active_layer_index,
        )
    )


def clear_preview_render_cache() -> None:
    get_preview_render_service().clear_cache()

