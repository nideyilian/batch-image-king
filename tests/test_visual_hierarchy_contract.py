"""VisualHierarchy 兼容层契约测试。

背景（2026-10-27）：经典界面（``python main.py --classic``）被发现**图层面板
显示 0 个图层**——数据里明明有图层，界面上一个都不渲染，且只在 stderr 里留一行
``KeyError: 'body'``。根因是 design token 改造（commit b5a98eb）把
``VisualHierarchy`` 的三样东西改坏了，而 624 项既有测试**没有一项覆盖这里**：

1. ``FONTS`` 从「角色 → {size, weight}」退化成了仅含 ``UI``/``MONO`` 的字体族表，
   于是 ``vh.FONTS['body']['size']`` 抛 KeyError；
2. ``get_font(role)`` 退化成「所有 role 都返回 13pt」，字号梯级全部丢失；
3. ``get_color()`` 由返回 **str** 改成返回 **QColor 对象**，而全部 108 处调用都是
   把它 f-string 拼进 QSS。``str(QColor)`` 会产出
   ``PySide6.QtGui.QColor.fromRgbF(...)``，整条声明被 Qt 静默丢弃——
   按钮/文字/边框全部退回默认样式，不报任何错。

这组测试守的是**契约**，不是字面量：
- get_color 的返回必须能直接拼进 QSS（是合法的颜色字符串）；
- role 必须有真实的字号梯级差异（不能全是一个值）；
- 代码里用到的每个 COLORS 组名都必须在 COLORS 里存在（不允许静默 fallback）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ui.visual_hierarchy import VisualHierarchy as VH

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = REPO_ROOT / "app" / "ui"


# --------------------------------------------------------------------------
# get_color 契约
# --------------------------------------------------------------------------

QSS_COLOR_RE = re.compile(
    r"^(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}"
    r"|rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*(,\s*[\d.]+%?\s*)?\))$"
)


def test_get_color_returns_qss_ready_string():
    """get_color 必须返回 QSS 可直接消费的颜色字符串。

    这是本组最关键的断言：返回 QColor 会让 108 处样式表声明集体失效，
    且 Qt 不报错、不抛异常，属于最难发现的静默降级。
    """
    for group, variants in VH.COLORS.items():
        for key in variants:
            value = VH.get_color(group, key)
            assert isinstance(value, str), (
                f"get_color({group!r}, {key!r}) 返回 {type(value).__name__}，"
                "必须返回 str 才能拼进 QSS"
            )
            assert "QColor" not in value, (
                f"get_color({group!r}, {key!r}) 泄漏了 QColor 的 repr：{value!r}"
            )
            assert QSS_COLOR_RE.match(value), (
                f"get_color({group!r}, {key!r}) = {value!r} 不是 QSS 合法颜色"
            )


def test_get_color_unknown_group_falls_back_to_string():
    """未知组名不能抛异常，也不能返回 QColor。"""
    assert VH.get_color("no_such_group", "no_such_key") == "#888888"
    assert VH.get_color("text", "no_such_variant") == "#888888"


def test_all_referenced_color_groups_exist():
    """源码里出现的每个 (group, key) 都必须能在 COLORS 查到底。

    历史上 layer_item 用了 'primary' / 'interactive' 两组，token 改造时被删掉，
    于是 20 处调用集体 fallback 成灰色 #888888 —— 界面不崩，但选中态/悬停态
    全部失灵。用静态扫描提前拦住这类「组名拼错或被删」。
    """
    pattern = re.compile(r"get_color\(\s*['\"]([a-z_]+)['\"]\s*,\s*['\"]([a-z_]+)['\"]")
    missing = []
    for path in UI_DIR.rglob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            group, key = match.group(1), match.group(2)
            if key not in VH.COLORS.get(group, {}):
                missing.append(f"{path.relative_to(REPO_ROOT)}: {group}.{key}")
    assert not missing, "存在 COLORS 未定义的引用（会静默 fallback 成灰色）：\n" + "\n".join(
        sorted(set(missing))
    )


# --------------------------------------------------------------------------
# get_font 契约
# --------------------------------------------------------------------------

def test_get_font_roles_have_real_size_steps():
    """role 必须映射到不同字号，而不是全部一个值。"""
    sizes = {role: VH.get_font(role).pixelSize() for role in VH.FONTS}
    assert len(set(sizes.values())) >= 3, f"字号梯级丢失，全部塌成同一档：{sizes}"
    assert sizes["body"] == 13, f"body 应为 13px（docs/UI设计规范.md §3.2），实际 {sizes['body']}"
    assert sizes["small"] == 11, f"small 应为 11px，实际 {sizes['small']}"
    assert sizes["body"] > sizes["small"]
    assert sizes["title"] > sizes["body"]


def test_get_font_never_returns_point_size():
    """统一用 pixelSize，pointSize 必须为 -1（避免 DPI 换算漂移）。"""
    for role in VH.FONTS:
        font = VH.get_font(role)
        assert font.pixelSize() > 0, f"{role} 未设置 pixelSize"
        assert font.pointSize() == -1, f"{role} 意外设置了 pointSize，规范要求统一 px"


def test_get_font_unknown_role_is_safe():
    """未知 role 回落到正文，不能抛异常。"""
    font = VH.get_font("no_such_role")
    assert font.pixelSize() == 13


def test_fonts_table_entries_are_size_dicts():
    """FONTS 的每个角色都必须是 {size, weight} 结构。

    这条直接对应历史 bug：FONTS 被改成族名字符串表后，
    ``FONTS['body']['size']`` 在字符串上取下标会抛 TypeError，
    ``FONTS['body']`` 则直接 KeyError。
    """
    for role, spec in VH.FONTS.items():
        assert isinstance(spec, dict), f"FONTS[{role!r}] 应为 dict，实际 {type(spec).__name__}"
        assert "size" in spec and "weight" in spec, f"FONTS[{role!r}] 缺少 size/weight"
        assert isinstance(spec["size"], int) and spec["size"] > 0


def test_font_families_are_strings():
    """字体族表单独维护，且必须是非空字符串。"""
    for name, family in VH.FONT_FAMILIES.items():
        assert isinstance(family, str) and family.strip(), f"FONT_FAMILIES[{name!r}] 非法"


# --------------------------------------------------------------------------
# 越界访问静态扫描
# --------------------------------------------------------------------------

def test_no_direct_fonts_subscript_beyond_defined_roles():
    """只允许访问 FONTS 中真实存在的角色。

    历史上 layer_item.py 有个 ``FONTS['body']['size']`` 直接写在 f-string 里，
    一构造 LayerItem 就炸，而图层面板把异常 catch 掉只打日志，
    表现为「面板空白」而非「程序崩溃」，极难发现。
    """
    pattern = re.compile(r"FONTS\[\s*['\"]([A-Za-z_]+)['\"]\s*\]")
    bad = []
    for path in UI_DIR.rglob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            role = match.group(1)
            # 'UI' / 'MONO' 属于 FONT_FAMILIES 的键，允许出现在别处但不在 FONTS
            if role not in VH.FONTS and role not in VH.FONT_FAMILIES:
                bad.append(f"{path.relative_to(REPO_ROOT)}: FONTS[{role!r}]")
    assert not bad, "存在越界访问 FONTS 的角色名：\n" + "\n".join(sorted(set(bad)))


# --------------------------------------------------------------------------
# 面板可渲染性（不依赖真实 GUI 的降级版）
# --------------------------------------------------------------------------

def test_get_spacing_and_radius_are_ints():
    for key in ("xs", "sm", "md", "lg", "xl"):
        assert isinstance(VH.get_spacing(key), int)
    for key in ("sm", "md", "lg"):
        assert isinstance(VH.get_radius(key), int)
    # 未知键走默认值而非抛异常
    assert VH.get_spacing("nope") == 8
    assert VH.get_radius("nope") == 6
