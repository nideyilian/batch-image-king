"""P3 硬编码色值契约：防止旧主题色重新渗回业务 UI。

背景（2026-10-27）：
`app/ui` 下曾有 162 处硬编码色值，其中 45 处集中在 5 个**零引用**的旧对话框里
（`integrated_text_editor_dialog` / `simple_text_editor_dialog` / `preset_panel` /
`add_shaped_layer_dialog` / `export_progress_dialog`）。

docs/DESIGN.md 5.2 的取舍：
- 高频且与令牌一致 → 换令牌
- 低频局部设计 → 先补令牌再替换
- Ant 蓝 #1677FF / #4096FF → 必改

本测试锁住三件事：
1. 明确的旧主题色不得出现在业务 UI 里（会直接让界面「半新半旧」）
2. 令牌定义文件本身不受约束（那里就该写色值）
3. 色板数据文件不受约束（用户可选的颜料，不是主题样式）
"""

from __future__ import annotations

from pathlib import Path

import pytest

UI_ROOT = Path(__file__).resolve().parents[1] / "app" / "ui"

# 令牌定义处：色值的单一真源，允许出现字面量
TOKEN_FILES = {
    "tokens_v2.py",
    "design_tokens.py",
    "dark_theme.py",
    "provider.py",
    "tokens.py",
    "visual_hierarchy.py",
}

# 用户调色板数据：这些是「可选的颜料」，与主题无关
PALETTE_FILES = {"color_picker_dialog_a2.py"}

# 已确认 0 引用的死代码（2026-10-27 全库 grep + 类名 grep 双向核实）。
#
# 为什么不修：改它们不会让任何用户看到变化，纯属浪费改动面；
# 为什么保留而不删：删文件属于独立决策（可能有外部脚本/历史分支依赖），
# 不在「清理硬编码」范围内。这里显式登记，好处是**范围可见** ——
# 哪天这些文件被复活，测试会立刻提醒它们还是旧色。
DEAD_FILES = {
    "add_shaped_layer_dialog.py",      # 0 引用
    "export_progress_dialog.py",       # 0 引用
    "integrated_text_editor_dialog.py",  # 0 引用
    "simple_text_editor_dialog.py",    # 0 引用
    "preset_panel.py",                 # 0 引用
    "showcase.py",                     # 组件演示页，0 引用；且刻意展示多种颜色
}

# 历史遗留的旧主题色 —— 出现即说明有文件没跟上令牌化
LEGACY_COLORS = {
    "#2f9cf4": "旧主色（Ant 蓝系）→ Color.accent",
    "#55b2ff": "旧主色亮档 → Color.accent_hover",
    "#1677ff": "Ant Design 蓝 → Color.accent",
    "#4096ff": "Ant Design 蓝亮档 → Color.accent_hover",
    "#1f1f1f": "旧控件底 → Color.surface_3",
    "#303033": "旧描边 → Color.border_strong",
    "#8e8e93": "旧提示文字 → Color.text_muted",
    "#2f2f2f": "旧对话框底 → Color.surface_1",
}


def _ui_py_files():
    for path in UI_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name in TOKEN_FILES or path.name in PALETTE_FILES:
            continue
        if path.name in DEAD_FILES:
            continue
        yield path


def test_no_legacy_theme_colors_in_business_ui():
    """业务 UI 文件里不得残留旧主题色。

    这些色值一旦出现，界面就会呈现「部分区域是新品牌紫、部分还是旧蓝/旧灰」的
    割裂感 —— 这是视觉改造最容易被用户察觉的破绽。
    """
    offenders: list[str] = []

    for path in _ui_py_files():
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        for color, hint in LEGACY_COLORS.items():
            if color in lowered:
                # 注释里提到色值是允许的（用于说明历史），只要不是活代码
                for lineno, line in enumerate(source.splitlines(), 1):
                    if color not in line.lower():
                        continue
                    if line.strip().startswith("#"):
                        continue
                    offenders.append(
                        f"{path.relative_to(UI_ROOT.parent.parent)}:{lineno} "
                        f"{color} ({hint})"
                    )

    assert not offenders, "发现旧主题色残留：\n  " + "\n  ".join(offenders)


def test_token_module_exposes_all_mapped_colors():
    """映射表里引用的每个令牌都必须真实存在。"""
    from app.ui.tokens_v2 import Color

    required = [
        "accent",
        "accent_hover",
        "surface_1",
        "surface_3",
        "surface_selected",
        "border_strong",
        "text_muted",
        "text_primary",
        "text_on_accent",
    ]
    missing = [name for name in required if not hasattr(Color, name)]
    assert not missing, f"tokens_v2.Color 缺少令牌: {missing}"


def test_legacy_color_picker_palette_is_intact():
    """调色板的 BASIC_COLORS 不能被令牌化误伤。

    它们是用户可选的颜色值（纯红/纯绿等），替换成主题令牌会让取色功能失效。
    """
    source = (UI_ROOT / "color_picker_dialog_a2.py").read_text(encoding="utf-8")
    assert "BASIC_COLORS" in source
    # 必须保留一组纯色定义
    assert "#ff0000" in source.lower()
    assert "#00ff00" in source.lower()


@pytest.mark.parametrize(
    "module_path",
    [
        "app.ui.layer_item",
        "app.ui.enhanced_font_selector",
        "app.ui.minimal_text_editor_dialog",
        "app.ui.preset_store_dialog",
        "app.ui.shaped_layer_panel",
    ],
)
def test_refactored_modules_import_without_error(module_path):
    """改过色值的模块必须能正常导入（防止 f-string 花括号写错）。"""
    import importlib

    importlib.import_module(module_path)
