"""文字图层不得用整块矩形抢占下层图层的点击命中。

背景：``_layer_contains_point`` 曾对 ``TextLayer`` 直接 ``return True``，
只判矩形、不看像素。文字框（尤其关掉自动适配的大框）覆盖到哪里，
下面真正有内容的图层就在那一片点不中了——用户表现为「选中一个图层后，
点另一个图层选不中」。
"""

from __future__ import annotations

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(document: Document) -> WorkspaceViewModel:
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


def _document() -> tuple[Document, TextLayer, int, int]:
    """形状层压在文字框内部（文字框该处透明）。返回 (文档, 文字层, 文字索引, 形状索引)。"""
    document = Document()
    document.create_new(600, 400)
    document.add_layer("形状层", 200, 200, 200, 120, is_folder=False)

    text = TextLayer(name="文字图层")
    text.set_current_text("标题", force=True)
    text.font_size = 40
    text.auto_fit_text_box = False
    text.width = 400
    text.height = 260
    document.add_text_layer(text)
    text.x = 100
    text.y = 100

    text_index = next(i for i, layer in enumerate(document.layers) if isinstance(layer, TextLayer))
    shape_index = next(i for i, layer in enumerate(document.layers) if layer.name == "形状层")
    return document, text, text_index, shape_index


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_text_box_transparent_area_passes_through_to_lower_layer():
    """文字框内透明处应命中下层图层，而不是文字层。"""
    document, _text, text_index, shape_index = _document()
    workspace = _workspace(document)

    x, y = 300, 260  # 文字框内，但位于形状层上、文字层该处透明
    assert workspace.hitTestLayerAt(x, y) == shape_index
    assert workspace.hitTestLayersAt(x, y) == [shape_index]

    workspace.selectLayer(text_index)
    assert workspace.selectLayerAtWithModifiers(x, y, False, False) == shape_index
    assert workspace.selectedLayerIndex == shape_index


def test_text_glyph_still_selects_text_layer():
    """点字形本身仍然选中文字层。"""
    document, text, text_index, _shape_index = _document()
    workspace = _workspace(document)

    image = text.get_image().convert("RGBA")
    width, height = image.size
    alpha = image.getchannel("A")
    found = None
    for py in range(0, height, 2):
        for px in range(0, width, 2):
            if alpha.getpixel((px, py)) > 100:
                found = (text.x + px, text.y + py)
                break
        if found:
            break
    assert found is not None, "文字层应当渲染出可见字形"

    workspace.selectLayer(_shape_index)
    assert workspace.selectLayerAtWithModifiers(found[0], found[1], False, False) == text_index
    assert workspace.selectedLayerIndex == text_index


def test_text_box_blank_area_still_selects_text_layer():
    """文字框空白处、下方无其他图层时，仍兜底选中文字层。"""
    document, _text, text_index, _shape_index = _document()
    workspace = _workspace(document)

    workspace.selectLayer(0)
    # 文字框 x=100..500 y=100..360，右下角 (480,340) 无字形、下方也无图层
    assert workspace.hitTestLayerAt(480, 340) == text_index
    assert workspace.selectLayerAtWithModifiers(480, 340, False, False) == text_index


def test_empty_text_layer_does_not_block_lower_layer():
    """空文字层不应挡住下层图层的点击。"""
    document = Document()
    document.create_new(600, 400)
    document.add_layer("形状层", 200, 200, 200, 120, is_folder=False)

    text = TextLayer(name="空文字")
    text.auto_fit_text_box = False
    text.width = 400
    text.height = 260
    document.add_text_layer(text)
    text.x = 100
    text.y = 100

    workspace = _workspace(document)
    shape_index = next(i for i, layer in enumerate(document.layers) if layer.name == "形状层")
    assert workspace.hitTestLayerAt(300, 260) == shape_index
