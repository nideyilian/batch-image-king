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
