"""Layer / LayerSerializer 序列化测试。

覆盖：

- Layer.serialize() 输出包含关键字段（name/坐标/尺寸/可见性/不透明度）
- serialize() -> deserialize() 往返后关键字段一致
- LayerSerializer 工具类对缺失属性给出默认值、类型转换生效
- Layer.duplicate() 产生独立副本（修改副本不污染原图层）
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.layer_new import Layer  # noqa: E402
from app.utils.layer_serializer import LayerSerializer  # noqa: E402


pytestmark = pytest.mark.unit


def _make_layer(tmp_dir, name: str = "L", w: int = 100, h: int = 80) -> Layer:
    """构造一个最小可用的图片图层。

    image_source 指向真实存在的目录（即使是空的），避免 layer 内部图片加载路径报错。
    """
    layer = Layer(
        name=name,
        x=10,
        y=20,
        width=w,
        height=h,
        image_source=tmp_dir,
        use_original_size=False,
        is_folder=True,
    )
    layer.visible = True
    layer.opacity = 0.5
    return layer


class TestLayerSerialize:
    def test_serialize_contains_core_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer = _make_layer(tmp, "alpha", 120, 90)
            data = layer.serialize()
        for key in ("name", "x", "y", "width", "height", "visible", "opacity"):
            assert key in data, f"missing key: {key}"
        assert data["name"] == "alpha"
        assert data["width"] == 120
        assert data["height"] == 90
        assert data["visible"] is True
        assert abs(data["opacity"] - 0.5) < 1e-6

    def test_round_trip_preserves_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer = _make_layer(tmp, "beta", 64, 64)
            data = layer.serialize()
        # 反序列化时不再传 image_source，data 里有原值
        restored = Layer.deserialize(data)
        assert restored.serialize()["name"] == "beta"
        assert restored.serialize()["width"] == 64
        assert restored.serialize()["height"] == 64
        assert abs(restored.serialize()["opacity"] - 0.5) < 1e-6

    def test_duplicate_is_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer = _make_layer(tmp, "origin", 50, 50)
            copy = layer.duplicate()
        # 副本基础字段一致
        assert copy.serialize()["name"] == "origin"
        # 修改副本不影响原图层（用公共属性 setter 而不是直接写私有属性）
        copy.name = "copy-1"
        copy.x = 999
        assert layer.name == "origin"
        assert layer.x == 10  # 原图层初始 x=10，未被副本影响


class TestLayerSerializerHelper:
    def test_serialize_layer_on_minimal_object(self):
        """LayerSerializer 不应要求 layer 是 Layer 类型，对 duck-typed 对象也能工作。"""

        class _Dummy:
            _name = "duck"
            _x = 1
            _y = 2
            _width = 30
            _height = 40
            _visible = True
            _opacity = 1.0
            _locked = False
            _image_source = None
            _is_folder = True
            _use_original_size = False
            _current_image_path = None
            _fit_mode = 0
            _crop_direction = 0
            _blend_mode = "normal"

        data = LayerSerializer.serialize_layer(_Dummy())
        assert data["name"] == "duck"
        assert data["x"] == 1
        assert data["width"] == 30
        assert data["blend_mode"] == "normal"

    def test_missing_attribute_returns_default(self):
        """对属性不存在的对象，仍能用默认值填充。"""

        class _Empty:
            pass

        data = LayerSerializer.serialize_layer(_Empty())
        # 默认值在 BASIC_ATTRIBUTES 里
        assert data["name"] == "新图层"
        assert data["visible"] is True
        assert data["opacity"] == 1.0
