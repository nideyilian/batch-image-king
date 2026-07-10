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
    cancel_token: object = None


@dataclass
class PreviewRenderResult:
    image: Optional[Image.Image]
    elapsed: float = 0.0
    error: str = ""
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return self.image is not None and not self.error and not self.cancelled


class PreviewRenderService:
    """Facade for canvas and thumbnail preview rendering."""

    def render(self, request: PreviewRenderRequest) -> PreviewRenderResult:
        from app.utils.preview_perf import PreviewPerfMonitor, is_perf_enabled
        perf = PreviewPerfMonitor.instance() if is_perf_enabled() else None
        start = time.time()
        primary_error = None
        token = getattr(request, "cancel_token", None)
        try:
            from app.utils.fast_renderer import get_global_fast_renderer

            renderer = get_global_fast_renderer()
            if request.interactive_low_quality and request.active_layer_index >= 0:
                image = renderer.render_preview_incremental(
                    request.document,
                    active_layer_index=request.active_layer_index,
                    force_refresh=request.force_refresh,
                    interactive_low_quality=True,
                    cancel_token=token,
                )
            elif request.interactive_low_quality:
                image = renderer.render_preview_live(
                    request.document,
                    interactive_low_quality=True,
                    cancel_token=token,
                )
            else:
                image = renderer.render_preview(
                    request.document,
                    force_refresh=request.force_refresh,
                    interactive_low_quality=request.interactive_low_quality,
                    cancel_token=token,
                )
            if token is not None and getattr(token, "cancelled", False):
                if perf is not None:
                    perf.record_cancelled_render()
                if perf is not None:
                    perf.background_render.record((time.time() - start) * 1000.0)
                return PreviewRenderResult(None, time.time() - start, cancelled=True)
            if image is not None:
                if perf is not None:
                    perf.background_render.record((time.time() - start) * 1000.0)
                return PreviewRenderResult(image, time.time() - start)
        except Exception as exc:
            primary_error = exc
            logger.warning("Preview FastRenderer failed; falling back to legacy render", exc_info=True)

        try:
            if token is not None and getattr(token, "cancelled", False):
                return PreviewRenderResult(None, time.time() - start, cancelled=True)
            image = render_document_legacy_fallback(request.document)
            if perf is not None:
                perf.background_render.record((time.time() - start) * 1000.0)
            return PreviewRenderResult(
                image,
                time.time() - start,
                "" if image is not None else str(primary_error or "preview renderer returned no image"),
            )
        except Exception as exc:
            logger.warning("Preview legacy fallback failed", exc_info=True)
            if perf is not None:
                perf.background_render.record((time.time() - start) * 1000.0)
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
    cancel_token=None,
) -> PreviewRenderResult:
    return get_preview_render_service().render(
        PreviewRenderRequest(
            document=document,
            force_refresh=force_refresh,
            interactive_low_quality=interactive_low_quality,
            active_layer_index=active_layer_index,
            cancel_token=cancel_token,
        )
    )


def clear_preview_render_cache() -> None:
    get_preview_render_service().clear_cache()


def get_layer_surface_for_overlay(document, layer) -> Optional[Image.Image]:
    """Return a cached PIL surface for the given layer, if available.

    Used by the canvas overlay path which must not import ``FastRenderer``
    directly.  Returns ``None`` when the renderer is unavailable or the
    layer has no surface cache.
    """
    try:
        from app.utils.fast_renderer import get_global_fast_renderer

        renderer = get_global_fast_renderer()
        surface = renderer._get_layer_surface_cached(layer, document, was_just_loaded=False)
        if surface is not None:
            return surface
    except Exception:
        return None
    return None

