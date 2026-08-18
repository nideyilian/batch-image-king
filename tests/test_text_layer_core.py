"""TextLayer 核心行为测试。

覆盖：

- 文字行增删与绑定模式
- 序列化往返：TextLayer -> dict -> TextLayer 后类型不退化为 Layer
- duplicate() 创建新实例，修改副本不影响原图层
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.text_layer import TextLayer  # noqa: E402


pytestmark = pytest.mark.unit


class TestTextLayerLines:
    def test_default_font_uses_cross_platform_sans_serif_alias(self, tmp_path, monkeypatch):
        regular = tmp_path / "msyh.ttc"
        regular.write_bytes(b"font")
        layer = TextLayer()
        layer._cached_font_paths = {"Microsoft YaHei": str(regular)}
        monkeypatch.setattr("app.models.text_layer_font.platform.system", lambda: "Windows")

        assert layer.font_family == "sans-serif"
        assert layer._find_font_path("sans-serif") == str(regular)

    def test_set_text_lines_replaces_lines(self):
        layer = TextLayer()
        # 显式把 current_text 清空，触发 set_text_lines 中的自动设置
        layer._current_text = ""
        layer.set_text_lines(["hello", "world"])
        assert layer.get_text_lines() == ["hello", "world"]
        # 清空 current_text 后，set_text_lines 会把第一行作为 current_text
        assert layer._current_text == "hello"

    def test_set_text_lines_to_empty_clears(self):
        layer = TextLayer()
        layer.set_text_lines(["a", "b"])
        layer.set_text_lines([])
        assert layer.get_text_lines() == []

    def test_parse_text_input_splits_lines_when_binding_enabled(self):
        layer = TextLayer()
        # parse_text_input_to_lines 是纯解析函数，不修改内部状态
        layer._text_binding_enabled = True
        result = layer.parse_text_input_to_lines("A\nB\nC")
        assert result == ["A", "B", "C"]

    def test_parse_text_input_treats_newline_as_layout_when_binding_disabled(self):
        layer = TextLayer()
        layer._text_binding_enabled = False
        result = layer.parse_text_input_to_lines("A\nB\nC")
        # 非绑定模式：整段文本作为单条候选
        assert result == ["A\nB\nC"]


class TestTextLayerSerialize:
    def test_binding_mode_clears_color_and_font_size_ranges(self):
        layer = TextLayer()
        layer._text_binding_enabled = False
        layer.set_text_lines(["ABCD"])
        layer.set_current_text("ABCD", force=True)
        layer.set_text_color_range(1, 2, (255, 0, 0, 255))
        layer.set_font_size_range(1, 2, 60)

        layer.text_binding_enabled = True

        assert layer.get_text_color_ranges() == []
        assert layer.get_font_size_ranges() == []

    def test_serialize_round_trip_keeps_textlayer_type(self):
        layer = TextLayer(name="banner", x=5, y=5, width=300, height=80)
        layer.set_text_lines(["promo-1", "promo-2", "promo-3"])
        data = layer.serialize()
        # type 标记是 'text'（见 text_layer_serialize.py serialize()）
        assert data.get("type") == "text"

        restored = TextLayer.deserialize(data)
        # 仍然能拿到 TextLayer
        assert isinstance(restored, TextLayer)
        assert restored.get_text_lines() == ["promo-1", "promo-2", "promo-3"]
        assert restored.serialize()["name"] == "banner"

    def test_duplicate_creates_independent_instance(self):
        layer = TextLayer(name="t1", width=200, height=60)
        layer.set_text_lines(["A", "B"])
        copy = layer.duplicate()
        assert copy is not layer
        copy.set_text_lines(["X", "Y", "Z"])
        # 原图层未被影响
        assert layer.get_text_lines() == ["A", "B"]
        assert copy.get_text_lines() == ["X", "Y", "Z"]

    def test_font_face_round_trip_duplicate_and_legacy_default(self):
        layer = TextLayer(name="weighted")
        layer.font_family = "Demo Sans SC"
        layer.font_face = "SemiBold"

        data = layer.serialize()
        assert data["font_face"] == "SemiBold"

        restored = TextLayer.deserialize(data)
        assert restored.font_family == "Demo Sans SC"
        assert restored.font_face == "SemiBold"

        duplicate = layer.duplicate()
        assert duplicate.font_face == "SemiBold"
        duplicate.font_face = "Light"
        assert layer.font_face == "SemiBold"

        legacy_data = dict(data)
        legacy_data.pop("font_face")
        legacy = TextLayer.deserialize(legacy_data)
        assert legacy.font_face == ""

    def test_font_face_invalidates_render_cache_and_selects_exact_path(self, tmp_path):
        regular = tmp_path / "Demo-Regular.ttf"
        bold = tmp_path / "Demo-Bold.ttf"
        regular.write_bytes(b"regular")
        bold.write_bytes(b"bold")
        layer = TextLayer()
        layer.font_family = "Demo Sans SC"
        layer._cached_image = object()
        layer._cached_font_paths = {"Demo Sans SC": str(regular)}
        layer._cached_font_faces = {
            "Demo Sans SC": [
                {"style": "Regular", "path": str(regular), "weight": 400, "italic": False},
                {"style": "Bold", "path": str(bold), "weight": 700, "italic": False},
            ]
        }

        layer.font_face = "Bold"

        assert layer._cached_image is None
        assert layer._find_font_path("Demo Sans SC", "Bold") == str(bold)
        assert layer._find_font_path("Demo Sans SC", "Missing") == str(regular)
