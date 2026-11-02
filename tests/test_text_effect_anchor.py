# -*- coding: utf-8 -*-
"""文字图层加描边/阴影/发光不应挪动字形位置。

历史 bug：textbbox 带 stroke_width 会把包围盒向四周各扩 w，而绘制原点直接用
-bbox 计算，于是字形被整体推 +w；盒子尺寸变化后图层坐标又不回补，画布上的字
就跟着跑。这里锁住「字形绝对位置不变」这一行为。
"""
import numpy as np
import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer


def _fill_origin(document):
    """返回字身（蓝色填充）在画布上的左上角坐标。"""
    arr = np.asarray(document.render_composition().convert("RGBA"), dtype=np.int16)
    mask = (arr[:, :, 2] > 180) & (arr[:, :, 0] < 90) & (arr[:, :, 3] > 200)
    ys, xs = np.nonzero(mask)
    assert len(xs), "没有渲染出字身像素"
    return int(xs.min()), int(ys.min())


def _make_document():
    document = Document()
    document.create_new(700, 400)
    layer = TextLayer()
    layer.set_current_text("测试Abc", force=True)
    layer.font_size = 36
    layer.text_color = (0, 0, 255, 255)
    document.add_text_layer(layer)
    layer.x = 150
    layer.y = 90
    return document, layer


@pytest.mark.integration
@pytest.mark.parametrize("stroke", [4, 10, 20])
def test_stroke_does_not_move_glyphs(qapp, stroke):
    document, layer = _make_document()
    before = _fill_origin(document)

    layer.stroke_width = stroke
    layer.stroke_enabled = True

    assert _fill_origin(document) == before
    # 盒子向右扩张多少，图层坐标就向左补多少（水平方向外扩是对称的）
    assert layer.x == 150 - stroke


@pytest.mark.integration
def test_stroke_toggle_is_reversible(qapp):
    document, layer = _make_document()
    before = _fill_origin(document)

    layer.stroke_width = 12
    layer.stroke_enabled = True
    layer.stroke_enabled = False

    assert _fill_origin(document) == before
    assert (layer.x, layer.y) == (150, 90)


@pytest.mark.integration
def test_padding_change_keeps_glyphs(qapp):
    document, layer = _make_document()
    before = _fill_origin(document)

    layer.text_box_padding = 25
    assert _fill_origin(document) == before

    layer.text_box_padding = 5
    assert _fill_origin(document) == before


@pytest.mark.integration
def test_shadow_and_glow_keep_glyphs(qapp):
    document, layer = _make_document()
    before = _fill_origin(document)

    layer.shadow_enabled = True
    assert abs(_fill_origin(document)[0] - before[0]) <= 1
    assert abs(_fill_origin(document)[1] - before[1]) <= 1

    layer.glow_enabled = True
    assert abs(_fill_origin(document)[0] - before[0]) <= 1
    assert abs(_fill_origin(document)[1] - before[1]) <= 1


@pytest.mark.integration
def test_text_edit_does_not_shift_anchor(qapp):
    document, layer = _make_document()
    before = _fill_origin(document)

    for text in ("文案一", "第二段文案", "A", "测试Abc"):
        layer.set_current_text(text, force=True)
        origin = _fill_origin(document)
        assert abs(origin[0] - before[0]) <= 1, f"{text} 横向跑位 {origin[0] - before[0]}px"
        assert abs(origin[1] - before[1]) <= 1, f"{text} 纵向跑位 {origin[1] - before[1]}px"
        assert (layer.x, layer.y) == (150, 90)
