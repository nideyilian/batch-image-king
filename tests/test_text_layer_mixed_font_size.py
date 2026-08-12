"""TextLayer 混合字号（局部字号区间）与画布就地编辑测试。

覆盖：

- 局部字号区间：设置/清除/合并/裁剪/序列化往返/duplicate
- 混合字号渲染：横排/竖排/超采样不崩溃且尺寸合理
- 画布就地编辑器：打开、Ctrl+滚轮调整选中字号、提交/取消
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.text_layer import TextLayer  # noqa: E402

pytestmark = pytest.mark.unit


class TestFontSizeRanges:
    def test_set_and_query_font_size_range(self):
        layer = TextLayer()
        layer.font_size = 24
        layer.set_current_text("你好世界")
        assert layer.set_font_size_range(0, 2, 60) is True
        assert layer.font_size_for_text_index(0) == 60
        assert layer.font_size_for_text_index(1) == 60
        assert layer.font_size_for_text_index(2) == 24
        assert layer.get_font_size_ranges() == [{"start": 0, "end": 2, "size": 60}]
        assert layer.has_font_size_ranges() is True

    def test_set_same_as_global_size_clears_range(self):
        layer = TextLayer()
        layer.font_size = 24
        layer.set_current_text("测试")
        layer.set_font_size_range(0, 1, 40)
        assert layer.has_font_size_ranges()
        # 设置与全局字号相同时自动清除区间
        assert layer.set_font_size_range(0, 1, 24) is True
        assert layer.get_font_size_ranges() == []

    def test_clear_font_size_range(self):
        layer = TextLayer()
        layer.font_size = 24
        layer.set_current_text("测试文字")
        layer.set_font_size_range(1, 3, 50)
        assert layer.clear_font_size_range(1, 3) is True
        assert layer.get_font_size_ranges() == []
        assert layer.font_size_for_text_index(1) == 24

    def test_overlapping_ranges_merge(self):
        layer = TextLayer()
        layer.font_size = 20
        layer.set_current_text("abcdef")
        layer.set_font_size_range(0, 3, 40)
        layer.set_font_size_range(2, 5, 40)
        # 相邻且同字号的区间合并
        assert layer.get_font_size_ranges() == [{"start": 0, "end": 5, "size": 40}]

    def test_ranges_clip_when_text_shortens(self):
        layer = TextLayer()
        layer.set_current_text("这是一个很长的文字")
        layer.set_font_size_range(0, 6, 48)
        layer.set_current_text("短文")
        # 区间被裁剪到当前文本长度
        assert layer.get_font_size_ranges() == [{"start": 0, "end": 2, "size": 48}]

    def test_serialize_round_trip_font_size_ranges(self):
        layer = TextLayer(name="mixed", width=400, height=120)
        layer.font_size = 30
        layer.set_current_text("混合字号演示")
        layer.set_font_size_range(0, 2, 64)
        layer.set_font_size_range(4, 6, 20)

        data = layer.serialize()
        assert data["font_size_ranges"] == [
            {"start": 0, "end": 2, "size": 64},
            {"start": 4, "end": 6, "size": 20},
        ]

        restored = TextLayer.deserialize(data)
        assert isinstance(restored, TextLayer)
        assert restored.get_font_size_ranges() == data["font_size_ranges"]
        assert restored.font_size_for_text_index(1) == 64
        assert restored.font_size_for_text_index(4) == 20

    def test_duplicate_copies_font_size_ranges_independently(self):
        layer = TextLayer()
        layer.set_current_text("复制测试")
        layer.set_font_size_range(0, 2, 56)
        copy = layer.duplicate()
        assert copy.get_font_size_ranges() == layer.get_font_size_ranges()
        copy.clear_font_size_range(0, 2)
        assert layer.has_font_size_ranges() is True
        assert copy.has_font_size_ranges() is False

    def test_legacy_deserialize_without_ranges(self):
        data = {
            "type": "text",
            "name": "legacy",
            "x": 0, "y": 0, "width": 200, "height": 60,
            "visible": True, "opacity": 1.0, "locked": False,
            "use_original_size": False,
            "text_lines": ["旧文件"],
            "current_text": "旧文件",
            "random_mode": False,
            "text_binding_enabled": True,
            "font_family": "Microsoft YaHei",
            "font_face": "",
            "font_size": 24,
            "font_style": "NORMAL",
            "text_color": (0, 0, 0, 255),
            "text_color_ranges": [],
        }
        restored = TextLayer.deserialize(data)
        assert restored.get_font_size_ranges() == []


class TestFontSizeRangesRender:
    def test_mixed_size_render_horizontal(self):
        layer = TextLayer(width=400, height=160)
        layer.font_size = 30
        layer.set_current_text("混合字号渲染")
        layer.set_font_size_range(0, 2, 70)
        image = layer.render_text()
        assert image.size[0] > 100 and image.size[1] > 30
        assert image.getbbox() is not None

    def test_mixed_size_render_vertical(self):
        layer = TextLayer(width=200, height=320)
        layer.font_size = 28
        layer.set_current_text("竖排混字号")
        layer.vertical_layout = True
        layer.set_font_size_range(0, 2, 56)
        image = layer.render_text()
        assert image.getbbox() is not None

    def test_mixed_size_render_with_stroke_and_gradient(self):
        layer = TextLayer(width=500, height=180)
        layer.font_size = 32
        layer.set_current_text("描边渐变混合字号")
        layer.set_font_size_range(0, 2, 64)
        layer.stroke_enabled = True
        layer.stroke_width = 3
        layer.stroke_color = (255, 255, 255, 255)
        layer.gradient_enabled = True
        image = layer.render_text()
        assert image.getbbox() is not None

    def test_mixed_size_render_with_letter_spacing(self):
        layer = TextLayer(width=500, height=180)
        layer.font_size = 30
        layer.set_current_text("字距混合字号")
        layer.set_font_size_range(0, 2, 58)
        layer.letter_spacing = 3
        image = layer.render_text()
        assert image.getbbox() is not None

    def test_mixed_size_supersampled_render(self):
        layer = TextLayer(width=500, height=180)
        layer.font_size = 30
        layer.set_current_text("超采样混合字号渲染")
        layer.set_font_size_range(0, 3, 66)
        layer.supersample_enabled = True
        layer.supersample_scale = 2
        image = layer.render_text()
        assert image.getbbox() is not None
        # 超采样临时参数已还原
        assert layer.font_size == 30
        assert layer.get_font_size_ranges() == [{"start": 0, "end": 3, "size": 66}]

    def test_mixed_size_auto_fit_text_box(self):
        layer = TextLayer(width=100, height=60)
        layer.font_size = 24
        layer.auto_fit_text_box = True
        layer.set_current_text("自动适配")
        layer.set_font_size_range(0, 2, 64)
        layer._update_text_box_size_if_needed()
        assert layer.width > 60 and layer.height > 40


@pytest.mark.integration
class TestCanvasTextEditor:
    def _make_editor(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QWidget

        app = QApplication.instance() or QApplication([])

        class DummyCanvas(QWidget):
            def __init__(self, doc):
                super().__init__()
                self.document = doc
                self.zoom_factor = 1.0
                self._text_editor = None

            def get_layer_rect(self, idx):
                return None

        from app.models.document import Document
        from app.ui.canvas_text_editor import CanvasTextEditor

        doc = Document()
        doc.canvas_width = 800
        doc.canvas_height = 600
        layer = TextLayer(name="t", x=100, y=100, width=220, height=80, parent=doc)
        doc.layers.append(layer)
        layer.font_size = 30
        layer.set_current_text("就地编辑测试")

        class _Rect:
            x = y = 100
            width = 220
            height = 80

        canvas = DummyCanvas(doc)
        editor = CanvasTextEditor(canvas, layer, _Rect(), 1.0)
        return app, canvas, doc, layer, editor

    def test_editor_loads_current_text(self):
        _app, _canvas, _doc, layer, editor = self._make_editor()
        assert editor.toPlainText() == "就地编辑测试"

    def test_editor_commit_writes_text_and_restores_auto_fit(self):
        _app, _canvas, _doc, layer, editor = self._make_editor()
        layer.auto_fit_text_box = True
        editor.setPlainText("修改后的文案")
        editor._commit()
        assert layer.current_text == "修改后的文案"
        assert layer.get_text_lines() == ["修改后的文案"]
        # 自动适配已恢复
        assert layer.auto_fit_text_box is True

    def test_editor_cancel_keeps_text(self):
        _app, _canvas, _doc, layer, editor = self._make_editor()
        editor.setPlainText("不应保存的修改")
        editor._cancel()
        assert layer.current_text == "就地编辑测试"

    def test_editor_cancel_restores_inline_styles_and_auto_fit(self):
        _app, _canvas, _doc, layer, _editor = self._make_editor()
        layer.text_binding_enabled = False
        layer.set_text_lines(["就地编辑测试"])
        layer.set_current_text("就地编辑测试", force=True)
        layer.set_text_color_range(1, 3, (255, 0, 0, 255))
        layer.set_font_size_range(2, 4, 60)
        original_colors = layer.get_text_color_ranges()
        original_sizes = layer.get_font_size_ranges()
        original_auto_fit = layer.auto_fit_text_box

        from app.ui.canvas_text_editor import CanvasTextEditor
        class _Rect:
            x = y = 100
            width = 220
            height = 80
        editor = CanvasTextEditor(_canvas, layer, _Rect(), 1.0)
        editor.setPlainText("不应保存的修改")
        editor._cancel()

        assert layer.current_text == "就地编辑测试"
        assert layer.get_text_color_ranges() == original_colors
        assert layer.get_font_size_ranges() == original_sizes
        assert layer.auto_fit_text_box is original_auto_fit

    def test_editor_ctrl_wheel_adjusts_selected_size(self):
        _app, _canvas, _doc, layer, editor = self._make_editor()
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(2, cursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor._adjust_selected_font_size(1)
        assert layer.get_font_size_ranges() == [{"start": 0, "end": 2, "size": 31}]
        editor._adjust_selected_font_size(-5)
        assert layer.get_font_size_ranges() == [{"start": 0, "end": 2, "size": 26}]
