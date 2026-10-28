"""设计令牌契约测试：颜色对比度 + 字号下限 + 间距栅格。

意义：设计规范如果只写在文档里，改代码时一定会漂。这里把「可量化的部分」
变成断言，任何人调色值/字号都会被 CI 拦住。

标准来源：
  - WCAG 2.1 AA：正文 4.5:1，大字号(>=18.66px bold / 24px)与图形 3:1
  - TDesign：桌面正文字号下限 12px
  - Material Design 3：11px 仅用于 label/annotation
  - Arco / Ant / Bootstrap：4px 间距栅格
"""

from __future__ import annotations

import pytest

from app.ui.tokens_v2 import (
    Color,
    Motion,
    Palette,
    Radius,
    Size,
    Space,
    Typography,
    ZIndex,
)


def _srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# --- 正文对比度：所有可能承载正文的表面都要 >= 4.5 -------------------------

BODY_SURFACES = [
    ("canvas", Color.canvas),
    ("surface_base", Color.surface_base),
    ("surface_1", Color.surface_1),
    ("surface_2", Color.surface_2),
    ("surface_3", Color.surface_3),
    ("surface_4", Color.surface_4),
    ("surface_selected", Color.surface_selected),
]


@pytest.mark.unit
@pytest.mark.parametrize("surface_name,surface", BODY_SURFACES)
def test_primary_text_meets_wcag_aa(surface_name, surface):
    ratio = contrast_ratio(Color.text_primary, surface)
    assert ratio >= 4.5, f"正文在 {surface_name} 上仅 {ratio:.2f}:1，低于 AA 要求 4.5:1"


@pytest.mark.unit
@pytest.mark.parametrize("surface_name,surface", BODY_SURFACES)
def test_secondary_text_meets_wcag_aa(surface_name, surface):
    ratio = contrast_ratio(Color.text_secondary, surface)
    assert ratio >= 4.5, f"次级文字在 {surface_name} 上仅 {ratio:.2f}:1"


@pytest.mark.unit
@pytest.mark.parametrize("surface_name,surface", BODY_SURFACES)
def test_muted_text_meets_wcag_aa(surface_name, surface):
    """提示文字最容易踩线 —— 它常被放在最亮的浮层上。"""
    ratio = contrast_ratio(Color.text_muted, surface)
    assert ratio >= 4.5, f"提示文字在 {surface_name} 上仅 {ratio:.2f}:1"


# --- 按钮白字：hover/active 全状态都要达标 --------------------------------

BUTTON_STATES = [
    ("accent", Color.accent),
    ("accent_hover", Color.accent_hover),
    ("accent_active", Color.accent_active),
    ("danger", Color.danger),
    ("danger_hover", Color.danger_hover),
]


@pytest.mark.unit
@pytest.mark.parametrize("state_name,bg", BUTTON_STATES)
def test_white_text_on_filled_button(state_name, bg):
    ratio = contrast_ratio(Color.text_on_accent, bg)
    assert ratio >= 4.5, f"按钮白字在 {state_name} 上仅 {ratio:.2f}:1"


# --- 图形/边框类：3:1 即可 ------------------------------------------------


@pytest.mark.unit
def test_accent_visible_on_base_surface():
    ratio = contrast_ratio(Color.accent, Color.surface_base)
    assert ratio >= 3.0, f"主色在基面上仅 {ratio:.2f}:1，作为可交互元素标识不足 3:1"


@pytest.mark.unit
@pytest.mark.parametrize(
    "name,color",
    [
        ("success", Color.success),
        ("warning", Color.warning),
        # 注意：这里用 danger_emphasis 而不是 danger。
        # danger 是「填充色」，职责是承载白字；在暗底上当颜色用会不够亮，
        # 所以图形/文字场景有专门的高亮变体。见 tokens_v2 里的说明。
        ("danger_emphasis", Color.danger_emphasis),
    ],
)
def test_semantic_colors_visible(name, color):
    ratio = contrast_ratio(color, Color.surface_1)
    assert ratio >= 3.0, f"语义色 {name} 在面板上仅 {ratio:.2f}:1"


@pytest.mark.unit
@pytest.mark.parametrize(
    "surface_name,surface", BODY_SURFACES
)
def test_danger_emphasis_visible_on_all_surfaces(surface_name, surface):
    """danger_emphasis 要能在任何层级上作为图标/文字使用（含最高层浮层）。"""
    ratio = contrast_ratio(Color.danger_emphasis, surface)
    assert ratio >= 3.0, (
        f"danger_emphasis 在 {surface_name} 上仅 {ratio:.2f}:1，"
        f"作为错误图标/文字不可见"
    )


# --- 暗色层级：elevation 越高必须越亮 ------------------------------------
# 依据：Radix / Mantlr 明确规则 —— 暗色下 elevation 靠「更亮」表达，不是更暗。


@pytest.mark.unit
def test_dark_elevation_monotonically_increases():
    ladder = [
        ("canvas", Color.canvas),
        ("surface_base", Color.surface_base),
        ("surface_1", Color.surface_1),
        ("surface_2", Color.surface_2),
        ("surface_3", Color.surface_3),
        ("surface_4", Color.surface_4),
    ]
    prev_name, prev = ladder[0]
    prev_lum = relative_luminance(prev)
    for name, value in ladder[1:]:
        lum = relative_luminance(value)
        assert lum > prev_lum, (
            f"暗色层级断裂：{name}({value}) 不比 {prev_name}({prev}) 更亮，"
            f"违反『elevation 越高越亮』规则"
        )
        prev_name, prev, prev_lum = name, value, lum


@pytest.mark.unit
def test_hover_is_lighter_than_default_surface():
    assert relative_luminance(Color.surface_hover) > relative_luminance(Color.surface_3)


# --- 字号：桌面下限 12px，11px 仅 label -----------------------------------


@pytest.mark.unit
def test_body_font_size_not_below_12px():
    assert Typography.size_base >= 12
    assert Typography.size_md >= 12
    assert Typography.size_sm >= 12


@pytest.mark.unit
def test_caption_size_is_allowed_exception():
    """11px 是 TDesign/M3 认可的 label 档，但不能小到 10px。"""
    assert Typography.size_caption == 11


@pytest.mark.unit
def test_no_font_size_below_11px():
    sizes = [
        v for k, v in vars(Typography).items()
        if k.startswith("size_") and isinstance(v, int)
    ]
    assert min(sizes) >= 11, f"存在低于 11px 的字号: {min(sizes)}"


@pytest.mark.unit
def test_line_height_follows_tdesign_rule():
    """TDesign 规则：line-height = font-size + 8。"""
    pairs = [
        (Typography.size_caption, Typography.line_caption),
        (Typography.size_sm, Typography.line_sm),
        (Typography.size_base, Typography.line_base),
        (Typography.size_md, Typography.line_md),
        (Typography.size_lg, Typography.line_lg),
        (Typography.size_xl, Typography.line_xl),
        (Typography.size_2xl, Typography.line_2xl),
    ]
    for size, line in pairs:
        assert line == size + 8, f"字号 {size}px 的行高应为 {size + 8}px，实际 {line}px"


@pytest.mark.unit
def test_font_stack_prefers_chinese_family():
    """中文字体必须排在 Segoe UI 前面。

    Windows 的 Segoe UI 不含汉字，若排在前面会触发逐字回退，
    中英混排时字重与基线不一致 —— 这是旧界面「字看着不精致」的主因。
    """
    stack = Typography.family
    assert "YaHei" in stack or "PingFang" in stack
    yahei_pos = stack.find("YaHei")
    segoe_pos = stack.find("Segoe UI")
    if segoe_pos != -1:
        assert yahei_pos < segoe_pos, "Segoe UI 不应排在中文族之前"


# --- 间距：4px 栅格，只允许 2/6 作为补充档 -------------------------------


@pytest.mark.unit
def test_spacing_follows_4px_grid():
    """间距必须落在 4px 栅格或其公认的补充档内。

    补充档依据（不是自造）：
      2px  = Tailwind space-0.5 / Chakra 0.5
      6px  = Tailwind space-1.5 / Chakra 1.5
      10px = Tailwind space-2.5 / Chakra 2.5
      14px = Tailwind space-3.5 / Chakra 3.5
    后两档是本项目 01 方案的核心节奏（gap / pad），属正式档位而非例外。
    无论如何，奇数 5/7/9/11/13 一律不允许 —— 无任何主流系统支持。
    """
    ALLOWED_NON_GRID = (2, 6, 10, 14)
    values = [
        v for k, v in vars(Space).items()
        if not k.startswith("_") and isinstance(v, int)
    ]
    for v in values:
        assert v % 4 == 0 or v in ALLOWED_NON_GRID, (
            f"间距 {v}px 不在 4px 栅格内，也不是 Tailwind/Chakra 的公认补充档 "
            f"{ALLOWED_NON_GRID}"
        )


@pytest.mark.unit
def test_spacing_has_no_odd_values():
    values = [
        v for k, v in vars(Space).items()
        if not k.startswith("_") and isinstance(v, int)
    ]
    odd = [v for v in values if v % 2 != 0]
    assert not odd, f"存在奇数间距（主流系统均不支持）: {odd}"


# --- 圆角：4 档，不出现 2/3/5/7 碎值 --------------------------------------


@pytest.mark.unit
def test_radius_scale_is_compact():
    values = {
        k: v for k, v in vars(Radius).items()
        if not k.startswith("_") and isinstance(v, int)
    }
    for name, v in values.items():
        assert v in (4, 6, 8, 12, 9999), f"圆角 {name}={v}px 不在四档体系内"


# --- 层级：单一具名阶梯，不允许散值 --------------------------------------


@pytest.mark.unit
def test_zindex_is_named_ladder():
    values = [
        v for k, v in vars(ZIndex).items()
        if not k.startswith("_") and isinstance(v, int)
    ]
    # 只允许 0/1/10 这类低位与 >=1000 的浮层档，中间不留散点
    for v in values:
        assert v <= 10 or v >= 1000, f"z-index {v} 属于散点值，应归入具名阶梯"
    assert ZIndex.toast > ZIndex.modal > ZIndex.dropdown
    assert ZIndex.tooltip > ZIndex.toast


# --- 基础完备性 -----------------------------------------------------------


@pytest.mark.unit
def test_tokens_are_hex_or_rgba():
    for name, value in vars(Color).items():
        if name.startswith("_") or not isinstance(value, str):
            continue
        assert value.startswith("#") or value.startswith("rgba("), (
            f"Color.{name}={value} 不是合法色值"
        )


@pytest.mark.unit
def test_primitive_palette_is_sorted_by_luminance():
    """灰阶必须按亮度单调，否则取档时会选错层级。"""
    scale = [
        Palette.NEUTRAL_950,
        Palette.NEUTRAL_900,
        Palette.NEUTRAL_850,
        Palette.NEUTRAL_800,
        Palette.NEUTRAL_750,
        Palette.NEUTRAL_700,
        Palette.NEUTRAL_650,
        Palette.NEUTRAL_600,
        Palette.NEUTRAL_500,
        Palette.NEUTRAL_400,
        Palette.NEUTRAL_300,
        Palette.NEUTRAL_200,
        Palette.NEUTRAL_100,
        Palette.NEUTRAL_50,
    ]
    lums = [relative_luminance(c) for c in scale]
    assert lums == sorted(lums), "中性灰阶未按亮度递增排列"


@pytest.mark.unit
def test_control_heights_meet_target_size():
    """WCAG 2.5.8：可点击目标最小 24x24。"""
    assert Size.control_h_sm >= Size.hit_target_min
    assert Size.control_h >= Size.hit_target_min
    assert Size.icon >= 14


@pytest.mark.unit
def test_motion_durations_are_short():
    """桌面工具动效宜短，超过 240ms 会显得拖沓。"""
    for name in ("instant", "fast", "base", "slow"):
        assert getattr(Motion, name) <= 240
