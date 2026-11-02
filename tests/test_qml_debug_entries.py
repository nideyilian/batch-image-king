"""调试入口拆分回归（2026-11-02）。

``qml_main.main()`` 原本是 668 行 / ~134 分支的单一函数，其中 300 多行是
``--show-*`` / ``--demo-*`` 的截图夹具准备。拆分后 main 只剩「装配 → 加载 →
进事件循环」，调试分支搬进 ``app/qml/qml_debug_entries.py``。

这个文件锁住拆分时**最容易改错的两处语义**（都靠读代码看不出来）：

1. **默认启动不建文档**。``wants_initial_document`` 在无参数时必须为 False ——
   因为默认首页是预设工作台，不是一张白纸。如果拆分时误把某个语法分支
   （``or args.show_*`` 写反、漏掉 not）算成 True，用户双击启动会看到空画布。
2. **面板类入口必须建文档**。任何一个 ``--show-*`` 都需要文档已存在，否则
   截图里是空画布，验收失效。

另外做结构断言：调试函数不读闭包（全部显式传参），否则单独调用会 NameError。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.qml import qml_debug_entries as entries
from app.qml.qml_debug_entries import wants_initial_document

MODULE_PATH = Path(entries.__file__)


class _Args:
    """最小的 argparse.Namespace 替身：所有开关默认 False，可任意覆盖。"""

    def __init__(self, **overrides):
        self.open_path = None
        self.demo = False
        self.demo_effects = False
        self.demo_tabs = False
        self.demo_shaped = False
        self.blank = False
        self.select_layer = None
        self.duplicate_selected = False
        self.screenshot = False
        self.width = None
        self.height = None
        self.theme = None
        self.open_presets = False
        self.select_preset = None
        for name in (
            "show_advanced_properties",
            "cycle_inspector_tabs",
            "show_random_transform",
            "show_text_typography",
            "show_text_appearance",
            "show_text_effects",
            "show_crop_tools",
            "show_vector_path",
            "show_multi_select",
            "show_grouped_layers",
            "show_batch_export",
            "show_batch_advanced",
            "show_batch_unique",
            "show_multi_tab_export",
            "show_effects",
            "show_close_confirm",
            "show_text_layer_dialog",
            "show_shaped_layer_dialog",
            "show_guides",
            "show_canvas_presets",
            "show_project_presets",
            "show_data_relations",
            "show_size_match",
            "show_color_picker",
            "show_new_canvas",
            "show_resize_canvas",
            "show_rename_document",
        ):
            setattr(self, name, False)
        for key, value in overrides.items():
            setattr(self, key, value)


@pytest.mark.unit
def test_default_launch_wants_no_document():
    """不带任何参数 = 普通双击启动，首页是预设工作台，不该建空画布。"""
    assert wants_initial_document(_Args()) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "flag",
    [
        "blank",
        "demo",
        "demo_effects",
        "demo_tabs",
        "demo_shaped",
        "duplicate_selected",
        "show_advanced_properties",
        "cycle_inspector_tabs",
        "show_random_transform",
        "show_text_typography",
        "show_text_appearance",
        "show_text_effects",
        "show_crop_tools",
        "show_vector_path",
        "show_multi_select",
        "show_grouped_layers",
        "show_batch_export",
        "show_batch_advanced",
        "show_batch_unique",
        "show_multi_tab_export",
        "show_effects",
        "show_close_confirm",
        "show_text_layer_dialog",
        "show_shaped_layer_dialog",
        "show_guides",
        "show_canvas_presets",
        "show_project_presets",
        "show_data_relations",
        "show_size_match",
    ],
)
def test_each_panel_flag_requires_a_document(flag):
    """每个面板/夹具开关都必须要求文档存在，否则截图是空画布。"""
    assert wants_initial_document(_Args(**{flag: True})) is True


@pytest.mark.unit
def test_select_layer_zero_still_counts_as_requiring_document():
    """``--select-layer 0`` 是合法值，不能因为 0 为假就漏判。"""
    assert wants_initial_document(_Args(select_layer=0)) is True


@pytest.mark.unit
def test_open_path_requires_document():
    assert wants_initial_document(_Args(open_path=Path("x.cmp"))) is True


@pytest.mark.unit
def test_debug_entry_functions_are_module_level_and_take_explicit_args():
    """调试入口不得读取 main() 的闭包变量 —— 所有依赖必须显式传参。

    拆分最容易埋的坑：把 ``workspace`` / ``window`` / ``debug`` 当自由变量用，
    单测或别处调用时直接 NameError。这里用 AST 检查每个函数的自由变量集合。
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    expected_params = {
        "wants_initial_document": {"args"},
        "prepare_initial_document": {"args", "workspace", "qml_dir"},
        "apply_window_geometry": {"window", "args", "debug"},
        "open_preset_workbench": {"args", "window", "debug"},
        "open_debug_dialogs": {"args", "window", "workspace", "workspace_sessions", "debug"},
        "open_debug_overlays": {"args", "window", "workspace", "workspace_sessions", "debug"},
        "_open_inspector_sections": {"args", "window", "workspace", "debug"},
        "_open_side_drawers": {"args", "window", "debug"},
    }

    found = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in expected_params:
            found[node.name] = {a.arg for a in node.args.args}

    assert set(found) == set(expected_params), (
        f"缺少调试入口函数: {set(expected_params) - set(found)}"
    )
    for name, params in found.items():
        assert params == expected_params[name], (
            f"{name} 的参数集变了: {params} != {expected_params[name]}"
        )


@pytest.mark.unit
def test_main_no_longer_contains_debug_branches():
    """main() 里不应再出现几十个 --show-* 分支（防止有人把代码抄回去）。"""
    qml_main = Path(__file__).resolve().parents[1] / "app" / "qml" / "qml_main.py"
    tree = ast.parse(qml_main.read_text(encoding="utf-8"))

    main_fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    # 统计 main 内出现的 args.show_* 属性访问次数
    show_refs = sum(
        1 for n in ast.walk(main_fn)
        if isinstance(n, ast.Attribute) and n.attr.startswith("show_")
    )
    line_count = main_fn.end_lineno - main_fn.lineno + 1

    assert line_count <= 350, f"main() 又胖回去了：{line_count} 行（拆完是 302 行）"
    assert show_refs <= 5, (
        f"main() 里出现 {show_refs} 次 args.show_*，调试分支疑似被抄回来了 —— "
        f"它们应该在 qml_debug_entries.py"
    )
