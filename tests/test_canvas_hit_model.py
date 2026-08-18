# -*- coding: utf-8 -*-
"""预览点击层级模型的集成测试（hit-test contract）。

覆盖：
- 从顶到底命中顺序与 z 序一致；
- 普通图片图层透明像素命中（点到上层透明区应穿透到下层）；
- 图层上下移动后命中顺序随之更新（hit_test_version 驱动缓存失效）；
- 组选中规则：点子图层选子图层，点组空白区选组。
"""
import os
import tempfile
import shutil

import pytest
from PySide6.QtCore import QPoint

from app.models.document import Document
from app.models.layer_group import LayerGroup
from app.utils.layer_tree import set_parent_group_id
from app.ui.canvas import CanvasWidget
from PIL import Image


def _make_png(path, color, size=100, hole_center=None, hole_size=30):
    img = Image.new("RGBA", (size, size), color)
    if hole_center is not None:
        hx0 = hole_center[0] - hole_size // 2
        hy0 = hole_center[1] - hole_size // 2
        for y in range(hy0, hy0 + hole_size):
            for x in range(hx0, hx0 + hole_size):
                if 0 <= x < size and 0 <= y < size:
                    img.putpixel((x, y), (0, 0, 0, 0))
    img.save(path, "PNG")


@pytest.mark.integration
def test_hit_top_layer_and_transparent_fallthrough(qapp):
    tmp = tempfile.mkdtemp(prefix="hittest_")
    try:
        doc = Document()
        doc.canvas_width = 400
        doc.canvas_height = 400

        bottom_path = os.path.join(tmp, "bottom.png")
        top_path = os.path.join(tmp, "top.png")
        # 上层在中心留一个透明洞，四角不透明
        _make_png(bottom_path, (0, 0, 255, 255))
        _make_png(top_path, (255, 0, 0, 255), hole_center=(50, 50))

        doc.add_layer("bottom", 0, 0, 100, 100, image_source=bottom_path, is_folder=False)
        doc.add_layer("top", 0, 0, 100, 100, image_source=top_path, is_folder=False)

        canvas = CanvasWidget(doc)
        canvas.resize(600, 600)
        canvas.zoom_factor = 1.0
        canvas.offset = QPoint(0, 0)
        canvas.show_rulers = False  # 不让标尺影响居中计算
        canvas.update()  # 触发一次布局，使 width()/height() 生效

        # 画布居中：ruler=0, 600 内容, 400 画布 -> center = (600-400)//2 = 100
        crect = canvas.get_canvas_rect()
        assert crect is not None
        # 文档坐标 (dx,dy) -> 屏幕坐标 (crect.x+dx, crect.y+dy)
        ox, oy = crect.x(), crect.y()

        # 点四角（两层都不透明）应命中上层（index 1）
        corner = QPoint(ox + 10, oy + 10)
        stack = canvas.get_layers_at_position(corner)
        assert stack[0] == 1, f"corner 应命中上层, got {stack}"

        # 点透明洞（doc 50,50）应穿透，命中下层 index 0
        hole = QPoint(ox + 50, oy + 50)
        stack_hole = canvas.get_layers_at_position(hole)
        assert 1 not in stack_hole, f"透明洞不应命中上层, got {stack_hole}"
        assert stack_hole[0] == 0, f"透明洞应命中下层, got {stack_hole}"

        canvas.deleteLater()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.integration
def test_hit_zorder_after_move(qapp):
    tmp = tempfile.mkdtemp(prefix="hittest_")
    try:
        doc = Document()
        doc.canvas_width = 400
        doc.canvas_height = 400

        bottom_path = os.path.join(tmp, "bottom.png")
        top_path = os.path.join(tmp, "top.png")
        _make_png(bottom_path, (0, 0, 255, 255))
        _make_png(top_path, (255, 0, 0, 255))

        doc.add_layer("bottom", 0, 0, 100, 100, image_source=bottom_path, is_folder=False)
        doc.add_layer("top", 0, 0, 100, 100, image_source=top_path, is_folder=False)

        canvas = CanvasWidget(doc)
        canvas.resize(600, 600)
        canvas.zoom_factor = 1.0
        canvas.offset = QPoint(0, 0)
        canvas.show_rulers = False
        canvas.update()

        crect = canvas.get_canvas_rect()
        ox, oy = crect.x(), crect.y()
        corner = QPoint(ox + 10, oy + 10)
        assert canvas.get_layer_at_position(corner) == 1

        # 把上层移到最底（index 0）
        doc.move_layer(1, 0)
        # 现在最上层是原来的 bottom（index 1）
        stack = canvas.get_layers_at_position(corner)
        assert stack[0] == 1, f"移动后最上层应为原 bottom, got {stack}"

        canvas.deleteLater()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.integration
def test_hit_group_rules(qapp):
    tmp = tempfile.mkdtemp(prefix="hittest_")
    try:
        doc = Document()
        doc.canvas_width = 400
        doc.canvas_height = 400

        a_path = os.path.join(tmp, "a.png")
        b_path = os.path.join(tmp, "b.png")
        _make_png(a_path, (0, 0, 255, 255))
        _make_png(b_path, (0, 255, 0, 255))

        doc.add_layer("A", 0, 0, 100, 100, image_source=a_path, is_folder=False)
        doc.add_layer("B", 200, 200, 100, 100, image_source=b_path, is_folder=False)

        # 手动组建组（绕开 UI 面板）
        g = LayerGroup(name="G")
        doc.layers.insert(0, g)
        for idx in (1, 2):
            set_parent_group_id(doc.layers[idx], g.group_id)
        doc.select_layers([0], primary_index=0)
        doc.bump_hit_test_version()

        canvas = CanvasWidget(doc)
        canvas.resize(600, 600)
        canvas.zoom_factor = 1.0
        canvas.offset = QPoint(0, 0)
        canvas.show_rulers = False
        canvas.update()

        crect = canvas.get_canvas_rect()
        ox, oy = crect.x(), crect.y()

        # 点子图层 A（doc 10,10）-> 选中子图层 A（index 1）
        hit_a = QPoint(ox + 10, oy + 10)
        assert canvas.get_layers_at_position(hit_a) == [1], "点子图层应选中子图层"

        # 点组空白区（doc 150,150，介于 A/B 之间，落在组 bounds 内）-> 选中组（index 0）
        hit_empty = QPoint(ox + 150, oy + 150)
        assert canvas.get_layers_at_position(hit_empty) == [0], "点组空白区应选中组"

        canvas.deleteLater()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

