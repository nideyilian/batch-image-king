"""启动首页路由：普通双击进工作台，带文档参数进编辑器。

这条规则很容易在后续改动里被悄悄破坏（比如有人给"是否建初始文档"再加一个条件，
就会把首页抢回编辑器），所以用测试钉住。

2026-11-02 拆分后，判定逻辑搬到 ``app.qml.qml_debug_entries.wants_initial_document``
与 ``open_preset_workbench``。本文件原先**复刻**了一份判定逻辑来判断，等于
"测试和实现各写一遍" —— 实现改了、复刻没改，测试照样通过，形同虚设。
现在改为**直接调用真实实现**，用最小的 argparse 替身构造参数。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qml.qml_debug_entries import wants_initial_document

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Args:
    """参数替身：只保留首页判定关心的开关，其余统一为 False/None。

    与 ``parse_args`` 的字段名保持一致；新增开关时如果这里没跟上，
    ``wants_initial_document`` 会直接 AttributeError，正好逼着同步。
    """

    _BOOL_FLAGS = (
        "demo", "demo_effects", "demo_tabs", "demo_shaped", "blank",
        "duplicate_selected", "screenshot", "open_presets",
        "show_advanced_properties", "cycle_inspector_tabs", "show_random_transform",
        "show_text_typography", "show_text_appearance", "show_text_effects",
        "show_crop_tools", "show_vector_path", "show_multi_select", "show_grouped_layers",
        "show_batch_export", "show_batch_advanced", "show_batch_unique",
        "show_multi_tab_export", "show_effects", "show_close_confirm",
        "show_text_layer_dialog", "show_shaped_layer_dialog", "show_guides",
        "show_canvas_presets", "show_project_presets", "show_data_relations",
        "show_size_match",
    )

    def __init__(self, **overrides):
        self.open_path = None
        self.select_layer = None
        self.select_preset = None
        self.width = None
        self.height = None
        self.theme = None
        for flag in self._BOOL_FLAGS:
            setattr(self, flag, False)
        for key, value in overrides.items():
            setattr(self, key, value)


def _should_open_workbench_as_home(**overrides) -> bool:
    """复刻 ``open_preset_workbench`` 的判定条件（条件表达式与其源码逐字一致）。

    只复刻**条件**，不 import 那个函数 —— 它一进来就要 QTimer/window 才能跑。
    条件本身由 test_home_routing_condition_in_source 断言与源码同步。
    """
    args = _Args(**overrides)
    return bool(args.open_presets or args.show_project_presets) or not (
        wants_initial_document(args) or args.open_path
    )


@pytest.mark.unit
def test_plain_launch_opens_workbench():
    """无参数（双击启动）→ 工作台作为首页。"""
    assert _should_open_workbench_as_home() is True


@pytest.mark.unit
def test_blank_launch_keeps_editor():
    """--blank 语义是"空白编辑器"，不能被工作台抢占。"""
    assert _should_open_workbench_as_home(blank=True) is False


@pytest.mark.unit
def test_open_path_keeps_editor():
    """打开指定文件时应直接进编辑器。"""
    assert _should_open_workbench_as_home(open_path=Path("a.cmp")) is False


@pytest.mark.unit
def test_demo_keeps_editor():
    """演示模式要直接看到画布。"""
    assert _should_open_workbench_as_home(demo=True) is False


@pytest.mark.unit
def test_explicit_open_presets_wins():
    """显式要求开工作台时，即使带 --blank 也进工作台。"""
    assert _should_open_workbench_as_home(open_presets=True, blank=True) is True
    assert _should_open_workbench_as_home(show_project_presets=True) is True


@pytest.mark.unit
def test_panel_flags_keep_editor_not_workbench():
    """任一 --show-* 面板入口都要进编辑器，否则截图里没有画布和面板。"""
    for flag in ("show_effects", "show_text_effects", "show_batch_export",
                 "show_canvas_presets", "show_data_relations"):
        assert _should_open_workbench_as_home(**{flag: True}) is False, flag


@pytest.mark.unit
def test_home_routing_condition_in_source():
    """判定条件必须与 open_preset_workbench 的源码字面一致。

    这条防的是"测试复刻漂移"：如果实现里的条件被改了（比如把 or 换成 and），
    这里立刻失败，而不是两边各说各话。
    """
    source = (REPO_ROOT / "app" / "qml" / "qml_debug_entries.py").read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert (
        "should_open = bool(args.open_presets or args.show_project_presets) or not ( "
        "wants_initial_document(args) or args.open_path )"
    ) in normalized, "open_preset_workbench 的首页判定条件被改动了"


@pytest.mark.unit
def test_screenshot_fallback_for_workbench_still_exists():
    """工作台可见时截图必须走 grabWindow。

    工作台是 captureRoot 的兄弟节点（浮层），grabToImage 抓不到它，
    这个兜底一删，截图就会丢掉整个工作台。
    """
    launcher_dir = REPO_ROOT / "app" / "qml"
    source = "\n".join(
        (launcher_dir / name).read_text(encoding="utf-8")
        for name in ("qml_main.py", "qml_debug_entries.py")
    )
    assert "presetWorkbenchVisible" in source
    assert "grabWindow" in source
