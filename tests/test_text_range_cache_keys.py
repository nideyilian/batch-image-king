from __future__ import annotations

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.utils.fast_renderer import FastRenderer, SmartCache


pytestmark = pytest.mark.unit


def _document_with_text() -> tuple[Document, TextLayer]:
    document = Document()
    document.create_new(360, 220)
    layer = TextLayer(name="缓存文字", x=20, y=30, width=280, height=100)
    layer.text_binding_enabled = False
    layer.auto_fit_text_box = False
    layer.set_text_lines(["ABCD"])
    layer.set_current_text("ABCD", force=True)
    document.add_text_layer(layer)
    return document, layer


def test_document_cache_key_changes_with_local_font_size_range():
    document, layer = _document_with_text()
    cache = SmartCache()
    before = cache._generate_key(document)

    layer.set_font_size_range(1, 3, 60)

    assert cache._generate_key(document) != before


def test_layer_surface_cache_key_changes_with_local_font_size_range():
    document, layer = _document_with_text()
    renderer = FastRenderer()
    before = renderer._build_layer_surface_key(layer, document)

    layer.set_font_size_range(1, 3, 60)

    assert renderer._build_layer_surface_key(layer, document) != before
