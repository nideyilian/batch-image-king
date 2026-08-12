from __future__ import annotations

import threading
import time

from PIL import Image
from PySide6.QtCore import QSize, QThreadPool
from PySide6.QtGui import QColor, QImage
import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels import workspace_view_model as workspace_module
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.services.preview_render_service import PreviewRenderRequest, PreviewRenderService
from app.utils.fast_renderer_preview import FastRendererPreview
from app.utils.preview_render_token import PreviewRenderToken


def _text_workspace(*, auto_render: bool = False) -> WorkspaceViewModel:
    document = Document()
    document.create_new(640, 480)
    document.add_text_layer(
        TextLayer(
            name="标题",
            x=40,
            y=50,
            width=320,
            height=100,
        )
    )
    document.select_layers([0], primary_index=0)
    document._history_manager.clear()
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=auto_render,
    )


@pytest.mark.unit
def test_font_catalog_property_never_scans_fonts_on_gui_thread(monkeypatch):
    workspace = _text_workspace()
    preload_calls = []

    def fail_sync_scan(*_args, **_kwargs):
        raise AssertionError("字体目录不能在 QML Property getter 中同步扫描")

    monkeypatch.setattr(workspace, "_load_text_font_options", fail_sync_scan)
    monkeypatch.setattr(
        workspace,
        "startFontCatalogPreload",
        lambda: preload_calls.append(True),
        raising=False,
    )

    options = workspace.textFontOptions

    assert preload_calls == [True]
    assert options
    assert options[0]["value"] == workspace.selectedTextFontFamily


@pytest.mark.unit
def test_deferred_font_catalog_waits_until_idle_callback(monkeypatch):
    workspace = _text_workspace()
    workspace._defer_font_catalog_preload = True
    preload_calls = []
    monkeypatch.setattr(
        workspace,
        "startFontCatalogPreload",
        lambda: preload_calls.append(True),
        raising=False,
    )

    options = workspace.textFontOptions

    assert options
    assert preload_calls == []
    workspace.enableDeferredFontCatalogPreload()
    assert preload_calls == [True]


@pytest.mark.unit
def test_initial_preview_is_submitted_only_after_auto_render_is_enabled():
    workspace = _text_workspace(auto_render=False)

    assert workspace._preview_generation == 0
    workspace.setAutoRender(True)
    assert workspace._preview_generation == 0

    workspace.renderInitialPreview()

    assert workspace._preview_generation == 1
    workspace._preview_timer.stop()


@pytest.mark.unit
def test_preview_provider_uses_qimage_implicit_sharing():
    provider = PreviewImageProvider()
    source = QImage(3840, 2160, QImage.Format_RGBA8888)
    source.fill(QColor("#2A7F68"))

    provider.set_image(source)
    published = provider.requestImage("current", None, QSize())

    assert provider._image.cacheKey() == source.cacheKey()
    assert published.cacheKey() == provider._image.cacheKey()


@pytest.mark.unit
def test_preview_task_avoids_ui_lock_and_receives_cancel_token(monkeypatch):
    workspace = _text_workspace()
    captured = {}

    class _Pool:
        def start(self, task):
            captured["task"] = task

    class _ThreadPoolFacade:
        @staticmethod
        def globalInstance():
            return _Pool()

    monkeypatch.setattr(workspace_module, "QThreadPool", _ThreadPoolFacade)
    workspace._auto_render = True
    workspace.requestPreview(force=True)
    workspace._preview_timer.stop()
    workspace._start_preview_render()

    task = captured["task"]
    assert task.document is workspace.document
    assert task.snapshot_data is None
    assert not hasattr(task, "document_lock")
    assert task.cancel_token is not None
    assert task.interactive_low_quality is True
    assert workspace.busy is False


@pytest.mark.unit
def test_text_edit_preview_task_omits_active_text_layer(monkeypatch):
    workspace = _text_workspace()
    captured = {}

    class _Pool:
        def start(self, task):
            captured["task"] = task

    class _ThreadPoolFacade:
        @staticmethod
        def globalInstance():
            return _Pool()

    monkeypatch.setattr(workspace_module, "QThreadPool", _ThreadPoolFacade)
    workspace._auto_render = True
    assert workspace.startTextEditOverlay() is True
    workspace._preview_timer.stop()
    workspace._start_preview_render()

    task = captured["task"]
    assert task.active_layer_index == 0
    assert task.omit_active_layer is True


@pytest.mark.unit
def test_new_preview_request_cancels_inflight_generation():
    workspace = _text_workspace()
    workspace._auto_render = True
    old_token = workspace._preview_token_source.peek()

    workspace.requestPreview(force=True)

    assert old_token.cancelled is True


@pytest.mark.unit
def test_layer_edit_does_not_wait_for_background_preview(monkeypatch):
    workspace = _text_workspace()
    workspace._auto_render = True
    render_started = threading.Event()

    def slow_preview(*_args, **_kwargs):
        from app.services.preview_render_service import PreviewRenderResult

        render_started.set()
        time.sleep(0.25)
        return PreviewRenderResult(image=None, elapsed=0.25)

    monkeypatch.setattr(
        "app.services.preview_render_service.render_preview_to_image",
        slow_preview,
    )
    workspace.requestPreview(force=True)
    workspace._preview_timer.stop()
    workspace._start_preview_render()
    assert render_started.wait(1.0)

    started = time.perf_counter()
    assert workspace.setSelectedOpacity(55) is True
    elapsed = time.perf_counter() - started

    assert elapsed < 0.12
    assert QThreadPool.globalInstance().waitForDone(1000) is True


@pytest.mark.unit
def test_opacity_change_avoids_full_selection_notification_fanout():
    workspace = _text_workspace()
    selection_notifications = []
    appearance_notifications = []
    workspace.selectionChanged.connect(lambda: selection_notifications.append(True))
    workspace.layerAppearanceChanged.connect(lambda: appearance_notifications.append(True))

    assert workspace.setSelectedOpacity(55) is True

    assert selection_notifications == []
    assert appearance_notifications == [True]


class _PreviewCacheProbe:
    def __init__(self):
        self.put_calls = []

    def get(self, *_args, **_kwargs):
        return None

    def put(self, *args, **kwargs):
        self.put_calls.append((args, kwargs))


class _PreviewRendererProbe(FastRendererPreview):
    def __init__(self):
        self._preview_render_lock = threading.RLock()
        self.intelligent_cache = _PreviewCacheProbe()
        self._last_render_time = {}
        self._last_preview_snapshot = None
        self._verbose_logging = False
        self.cancel_during_render = False
        self.fast_render_tokens = []

    def _is_export_preview_frozen(self, _document):
        return False

    def _get_cached_memory_status(self):
        return {"pressure_level": "normal"}

    def _fast_render(self, _document, **kwargs):
        token = kwargs.get("cancel_token")
        self.fast_render_tokens.append(token)
        if self.cancel_during_render and token is not None:
            token.cancel()
        return Image.new("RGBA", (8, 8), (50, 100, 150, 255))


class _PreviewDocument:
    canvas_width = 8
    canvas_height = 8
    _needs_cache_refresh = False


@pytest.mark.unit
def test_full_quality_preview_cancellation_reaches_renderer_and_skips_cache():
    renderer = _PreviewRendererProbe()
    token = PreviewRenderToken()
    renderer.cancel_during_render = True

    image = renderer.render_preview(_PreviewDocument(), force_refresh=True, cancel_token=token)

    assert renderer.fast_render_tokens == [token]
    assert image is None
    assert renderer.intelligent_cache.put_calls == []
    assert renderer._last_preview_snapshot is None


@pytest.mark.unit
def test_incremental_preview_fallback_keeps_cancellation_token():
    token = PreviewRenderToken()
    captured = {}

    class _IncrementalProbe(FastRendererPreview):
        def __init__(self):
            self._preview_render_lock = threading.RLock()

        def render_preview(self, **kwargs):
            captured.update(kwargs)
            return None

    document = type("Document", (), {"layers": []})()
    _IncrementalProbe().render_preview_incremental(
        document,
        active_layer_index=-1,
        cancel_token=token,
    )

    assert captured["cancel_token"] is token


@pytest.mark.unit
def test_preview_service_uses_without_layer_renderer_for_text_edit(monkeypatch):
    calls = []

    class _Renderer:
        def render_preview_without_layer(self, document, **kwargs):
            calls.append(("without", document, kwargs))
            return Image.new("RGBA", (4, 4), (0, 0, 0, 0))

        def render_preview_incremental(self, document, **kwargs):
            calls.append(("incremental", document, kwargs))
            return None

        def render_preview(self, document, **kwargs):
            calls.append(("full", document, kwargs))
            return None

    monkeypatch.setattr(
        "app.utils.fast_renderer.get_global_fast_renderer",
        lambda: _Renderer(),
    )

    request = PreviewRenderRequest(
        document=object(),
        active_layer_index=2,
        omit_active_layer=True,
        interactive_low_quality=True,
    )
    result = PreviewRenderService().render(request)

    assert result.ok is True
    assert calls[0][0] == "without"
    assert calls[0][2]["active_layer_index"] == 2
    assert calls[0][2]["interactive_low_quality"] is True
