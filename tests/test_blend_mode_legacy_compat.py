"""blend_mode 历史中文值的兼容性。

背景：早期版本把 blend_mode 存成中文名（'正常' / '正片叠底' …），
后来改为 0-15 的 int。读取侧若直接 int() 会抛 ValueError，属性回退默认值，
混合模式静默丢失——这类 bug 不会报错，只会让画面悄悄不对。

本文件锁定三件事：
1. 属性管理器能把中文/英文/int 全部归一为规范 int。
2. 未知值回退 normal 而不是抛异常。
3. 迁移工具能把存量数据洗干净，且不碰已合规的值。
"""

import pytest

from app.models.layer_new import Layer
from app.utils.blend_modes import BLEND_MODE_NAMES, blend_mode_to_int
from tools.migrate_blend_mode import migrate_payload


@pytest.mark.unit
@pytest.mark.parametrize(
    ["raw", "expected"],
    [
        ("正常", 0),
        ("正片叠底", 1),
        ("滤色", 2),
        ("叠加", 3),
        ("柔光", 4),
        ("强光", 5),
        ("normal", 0),
        ("multiply", 1),
        ("screen", 2),
        ("Normal", 0),          # 大小写不敏感
        ("  multiply  ", 1),    # 首尾空白
        (0, 0),
        (2, 2),
        (15, 15),
    ],
)
def test_legacy_blend_mode_values_normalize_to_int(qapp, raw, expected):
    """中文名、英文名、int 都必须落到同一个规范 int。"""
    layer = Layer(name="测试")
    layer._property_manager.set_property("blend_mode", raw, validate=True)
    assert layer.blend_mode == expected


@pytest.mark.unit
def test_unknown_blend_mode_falls_back_to_normal(qapp):
    """未知值不能抛异常，回退 normal（0）。"""
    layer = Layer(name="测试")
    layer._property_manager.set_property("blend_mode", "不存在的模式", validate=True)
    assert layer.blend_mode == 0


@pytest.mark.unit
def test_none_blend_mode_falls_back_to_normal(qapp):
    layer = Layer(name="测试")
    layer._property_manager.set_property("blend_mode", None, validate=True)
    assert layer.blend_mode == 0


@pytest.mark.unit
def test_all_chinese_names_map_to_their_int(qapp):
    """BLEND_MODE_NAMES 的每一项，用中文名写入后必须得到对应下标。"""
    zh_pairs = [
        ("正常", "normal"),
        ("正片叠底", "multiply"),
        ("滤色", "screen"),
        ("叠加", "overlay"),
        ("柔光", "soft_light"),
        ("强光", "hard_light"),
        ("颜色减淡", "color_dodge"),
        ("颜色加深", "color_burn"),
        ("变暗", "darken"),
        ("变亮", "lighten"),
        ("差值", "difference"),
        ("排除", "exclusion"),
        ("色相", "hue"),
        ("饱和度", "saturation"),
        ("颜色", "color"),
        ("明度", "luminosity"),
    ]
    layer = Layer(name="测试")
    for zh, en in zh_pairs:
        expected = BLEND_MODE_NAMES.index(en)
        layer._property_manager.set_property("blend_mode", zh, validate=True)
        assert layer.blend_mode == expected, f"{zh} 应映射到 {expected}"


@pytest.mark.unit
def test_migrate_payload_normalizes_legacy_and_keeps_valid():
    """迁移只改历史中文值，已合规的 int 原样保留。"""
    payload = {
        "documents": [
            {
                "layers": [
                    {"name": "中文层", "blend_mode": "正片叠底"},
                    {"name": "已合规", "blend_mode": 5},
                    {"name": "子组", "blend_mode": "正常", "children": [
                        {"name": "孙层", "blend_mode": "滤色"},
                    ]},
                    {"name": "无字段"},
                ]
            }
        ]
    }

    count, changes = migrate_payload(payload)

    assert count == 3, "只应改 3 个历史值（含嵌套 children）"
    layers = payload["documents"][0]["layers"]
    assert layers[0]["blend_mode"] == 1
    assert layers[1]["blend_mode"] == 5, "已合规的 int 不能被改动"
    assert layers[2]["blend_mode"] == 0
    assert layers[2]["children"][0]["blend_mode"] == 2
    assert "blend_mode" not in layers[3], "原本没有该字段的图层不应被塞入"


@pytest.mark.unit
def test_migrate_payload_is_idempotent():
    """跑第二遍不应再有任何改动（防止每次启动都改写文件）。"""
    payload = {"layers": [{"name": "a", "blend_mode": "正片叠底"}]}
    first, _ = migrate_payload(payload)
    second, _ = migrate_payload(payload)
    assert first == 1
    assert second == 0


@pytest.mark.unit
def test_blend_mode_to_int_handles_enum_like_prefix():
    """兼容 'BlendMode.NORMAL' 这种枚举字符串形式。"""
    assert blend_mode_to_int("BlendMode.SCREEN") == 2
