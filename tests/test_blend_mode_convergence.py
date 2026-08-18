"""混合模式收敛契约测试（P1-8）。

锁定：
1. 0-15 int -> 规范英文名 -> int 往返一致（.cmp 磁盘格式）。
2. 历史分散映射（document_blend._normalize_mode、fast_renderer_composite、
   document_render._get_layer_blend_mode_string）与规范来源一致。
3. Enum / 中文 / "BlendMode.X" 前缀 / 扩展名 / None 的归一行为。
"""

from __future__ import annotations

import pytest

from app.utils.blend_modes import (
    BLEND_MODE_NAMES,
    BlendMode,
    blend_mode_to_int,
    blend_mode_to_name,
)

pytestmark = pytest.mark.unit


def test_int_name_roundtrip():
    for i, name in enumerate(BLEND_MODE_NAMES):
        assert blend_mode_to_name(i) == name, f"int {i} 应映射为 {name}"
        assert blend_mode_to_int(name) == i, f"{name} 应映射回 int {i}"
    # 完整往返
    for i in range(len(BLEND_MODE_NAMES)):
        assert blend_mode_to_int(blend_mode_to_name(i)) == i


def test_unknown_int_falls_back_to_normal():
    assert blend_mode_to_name(99) == "normal"
    assert blend_mode_to_int(99) == 0


def test_enum_and_string_inputs():
    assert blend_mode_to_name(BlendMode.MULTIPLY) == "multiply"
    assert blend_mode_to_int(BlendMode.MULTIPLY) == 1
    # 中文名
    assert blend_mode_to_name("正片叠底") == "multiply"
    assert blend_mode_to_int("正片叠底") == 1
    # "BlendMode.X" 前缀
    assert blend_mode_to_name("BlendMode.SCREEN") == "screen"
    # 大小写与空白
    assert blend_mode_to_name("  Overlay  ") == "overlay"
    # None
    assert blend_mode_to_name(None) == "normal"
    assert blend_mode_to_int(None) == 0
    # 扩展名原样返回（不落入 normal）
    assert blend_mode_to_name("linear_burn") == "linear_burn"
    # 未知字符串原样返回（与历史行为一致）
    assert blend_mode_to_name("bogus_mode") == "bogus_mode"
    # 未知字符串无法映射回 int -> 0
    assert blend_mode_to_int("bogus_mode") == 0


def test_document_blend_legacy_int_map_matches_canonical():
    """document_blend._normalize_mode 的 0-15 中文映射必须与规范顺序一致。"""
    from app.models.document_blend import BlendMode as ZhBlendMode, Blender

    zh = {
        0: ZhBlendMode.NORMAL,
        1: ZhBlendMode.MULTIPLY,
        2: ZhBlendMode.SCREEN,
        3: ZhBlendMode.OVERLAY,
        4: ZhBlendMode.SOFT_LIGHT,
        5: ZhBlendMode.HARD_LIGHT,
        6: ZhBlendMode.COLOR_DODGE,
        7: ZhBlendMode.COLOR_BURN,
        8: ZhBlendMode.DARKEN,
        9: ZhBlendMode.LIGHTEN,
        10: ZhBlendMode.DIFFERENCE,
        11: ZhBlendMode.EXCLUSION,
        12: ZhBlendMode.HUE,
        13: ZhBlendMode.SATURATION,
        14: ZhBlendMode.COLOR,
        15: ZhBlendMode.LUMINOSITY,
    }
    for i in range(len(BLEND_MODE_NAMES)):
        normalized = Blender._normalize_mode(i)
        assert blend_mode_to_name(normalized) == BLEND_MODE_NAMES[i], (
            f"document_blend int {i} -> {normalized!r} 与规范 {BLEND_MODE_NAMES[i]} 不一致"
        )


def test_render_getters_match_canonical():
    """两条渲染 getter 的 int 归一结果与规范一致。"""
    from app.models.document_render import DocumentRender
    from app.utils.fast_renderer_composite import FastRendererComposite

    class FakeLayer:
        pass

    layer = FakeLayer()
    fr_getter = FastRendererComposite()._get_layer_blend_mode
    dr_getter = DocumentRender()._get_layer_blend_mode_string

    for i in range(len(BLEND_MODE_NAMES)):
        layer.blend_mode = i
        assert fr_getter(layer) == BLEND_MODE_NAMES[i]
        assert dr_getter(layer) == BLEND_MODE_NAMES[i]

    # None / 字符串 / 枚举
    layer.blend_mode = None
    assert fr_getter(layer) == "normal"
    assert dr_getter(layer) == "normal"
    layer.blend_mode = "正片叠底"
    assert fr_getter(layer) == "multiply"
    layer.blend_mode = BlendMode.SCREEN
    assert fr_getter(layer) == "screen"
    assert dr_getter(layer) == "screen"
