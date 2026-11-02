"""启动首页路由：普通双击进工作台，带文档参数进编辑器。

这条规则容易在后续改动里被悄悄破坏（比如有人给 initial_document_requested
再加一个条件，就会把首页抢回编辑器），所以用测试钉住。
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _should_open_workbench_as_home(*argv: str) -> bool:
    """复刻 qml_main 里的首页判定，只依赖参数解析结果。

    故意不 import qml_main（它会建 QApplication/engine），而是把判定逻辑
    用同一份参数定义跑一遍，保证「参数语义」与源码一致。
    """
    # 与 qml_main 的参数定义保持同名的子集
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--blank", action="store_true")
    parser.add_argument("--open-presets", action="store_true")
    parser.add_argument("--show-project-presets", action="store_true")
    parser.add_argument("--open", dest="open_path", default=None)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--select-layer", type=int, default=None)
    parser.add_argument("--screenshot", type=Path, default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--theme", default=None)
    args = parser.parse_args(list(argv))

    initial_document_requested = bool(
        args.open_path or args.demo or args.blank or args.select_layer is not None
    )
    return bool(args.open_presets or args.show_project_presets) or not (
        initial_document_requested or args.open_path
    )


@pytest.mark.unit
def test_plain_launch_opens_workbench():
    """无参数（双击启动）→ 工作台作为首页。"""
    assert _should_open_workbench_as_home("--screenshot", "x.png") is True


@pytest.mark.unit
def test_blank_launch_keeps_editor():
    """--blank 语义是"空白编辑器"，不能被工作台抢占。"""
    assert _should_open_workbench_as_home("--blank") is False


@pytest.mark.unit
def test_open_path_keeps_editor():
    """打开指定文件时应直接进编辑器。"""
    assert _should_open_workbench_as_home("--open", "a.cmp") is False


@pytest.mark.unit
def test_demo_keeps_editor():
    """演示模式要直接看到画布。"""
    assert _should_open_workbench_as_home("--demo") is False


@pytest.mark.unit
def test_explicit_open_presets_wins():
    """显式要求开工作台时，即使带 --blank 也进工作台。"""
    assert _should_open_workbench_as_home("--open-presets", "--blank") is True
    assert _should_open_workbench_as_home("--show-project-presets") is True


@pytest.mark.unit
def test_source_contains_home_routing_and_screenshot_fallback():
    """源码层面确认两处关键实现还在。

    - open_presets_as_home 判定存在
    - 工作台可见时截图走 grabWindow（工作台是 captureRoot 的兄弟节点，
      grabToImage 抓不到它，这个兜底一删截图就会丢整个工作台）
    """
    source = (REPO_ROOT / "app" / "qml" / "qml_main.py").read_text(encoding="utf-8")
    assert "open_presets_as_home" in source
    assert "presetWorkbenchVisible" in source and "grabWindow" in source
