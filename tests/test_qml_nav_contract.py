"""顶部导航栏的命令入口契约（2026-11-04）。

背景：顶栏曾有 01 画布 / 02 预设 / 03 导出 / 04 命令 四个带编号的项，
它们与第二行 commandBar、commandMenu 里指向同一函数，且编号没有 active 联动，
会被误读成「必须依次完成的步骤」。本文件锁住收敛后的结构：

1. 顶栏不再展示编号，也不再重复 commandBar 里的动作。
2. 一个函数只有一个可见主入口；菜单里只允许保留带快捷键的文本别名。
3. 三个导出入口按作用域命名、图标互不相同。
4. tooltip 里出现的快捷键必须是 Main.qml 里真实注册过的 Shortcut。
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = REPO_ROOT / "app" / "qml"
DOCS_ROOT = REPO_ROOT / "docs"


def _main_source() -> str:
    return (QML_ROOT / "Main.qml").read_text(encoding="utf-8")


def _section(source: str, start_marker: str, end_marker: str) -> str:
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if start_marker in line)
    end = next(i for i, line in enumerate(lines) if i > start and end_marker in line)
    return "\n".join(lines[start:end])


def _command_sections(source: str) -> dict[str, str]:
    return {
        "titleBar": _section(source, "id: titleBar", "id: commandMenu"),
        "commandMenu": _section(source, "id: commandMenu", "id: commandBar"),
        "commandBar": _section(source, "id: commandBar", "id: documentTabs"),
    }


_ACTION = re.compile(
    r"onClicked:[ \t]*([A-Za-z0-9_.]+)|onTriggered:[ \t]*([A-Za-z0-9_.]+)"
)


def _actions(section: str) -> list[str]:
    return [a or b for a, b in _ACTION.findall(section)]


@pytest.mark.unit
def test_title_bar_has_no_numbered_items_and_no_duplicate_actions():
    source = _main_source()
    sections = _command_sections(source)
    title = sections["titleBar"]

    assert title.count("HermesNavItem {") == 1
    assert "HermesNavItem { index:" not in title
    assert 'text: "更多操作"' in title

    for action in (
        "window.openNewCanvasDialog",
        "window.openProjectPresetDrawer",
        "window.openBatchExportDrawer",
    ):
        assert action not in title, f"{action} 是 commandBar 的动作，不该出现在顶栏"


@pytest.mark.unit
def test_nav_item_index_is_opt_in_and_tooltip_is_descriptive():
    nav = (QML_ROOT / "components" / "HermesNavItem.qml").read_text(encoding="utf-8")

    assert "property bool showIndex: false" in nav
    assert "visible: root.showIndex && root.index.length > 0" in nav
    assert "property string description:" in nav
    assert "ToolTip.text: root.description.length > 0 ? root.description : root.text" in nav
    # 编号与 badge 收敛到 11px（M3 labelSmall 下限），不再出现 9/10px。
    assert not re.search(r"font\.pixelSize:[ \t]*(9|10)\b", nav)


@pytest.mark.unit
def test_each_command_has_one_visible_home():
    source = _main_source()
    sections = _command_sections(source)
    places_by_action: dict[str, set[str]] = {}
    for region, section in sections.items():
        for action in _actions(section):
            places_by_action.setdefault(action, set()).add(region)

    duplicated = {
        action: sorted(places)
        for action, places in places_by_action.items()
        if len(places) > 1
    }
    # 唯一允许的是「检查更新」：commandBar 图标是主入口，菜单里是带快捷键的文本别名。
    assert set(duplicated) <= {"window.openUpdateDialog"}, duplicated
    if duplicated:
        assert 'text: "检查更新\\tCtrl+Shift+U"' in sections["commandMenu"]
        assert "commandBar" in duplicated["window.openUpdateDialog"]

    # 四个高频动作在 commandBar 里各只有一个入口。
    bar_counts = Counter(_actions(sections["commandBar"]))
    for action in (
        "window.openProjectPresetDrawer",
        "window.openBatchExportDrawer",
        "exportDialog.open",
        "window.openMultiTabExportDrawer",
    ):
        assert bar_counts[action] == 1, (action, bar_counts[action])

    # 新建画布的按钮归空工作区首页所有，工具栏不放第二个；
    # 有文档时通过「更多操作」菜单里带快捷键的文本别名 + Ctrl+N 到达。
    assert bar_counts["window.openNewCanvasDialog"] == 0
    assert "iconName: AppIcons.fileNew" not in source
    assert 'text: "新建画布\\tCtrl+N"' in sections["commandMenu"]


@pytest.mark.unit
def test_export_entries_are_named_by_scope_and_use_distinct_icons():
    bar = _command_sections(_main_source())["commandBar"]

    assert 'tooltip: "导出当前画面（单张）Ctrl+Shift+X"' in bar
    assert 'tooltip: "多标签批量导出（跨标签页）Ctrl+Alt+Shift+X"' in bar
    assert 'ToolTip.text: "批量导出当前文档 F12"' in bar

    assert 'iconName: AppIcons.folderOutput' in bar          # 单张
    assert 'iconName: AppIcons.listChecks' in bar            # 跨标签页
    assert bar.count("iconName: AppIcons.exportAction") == 1  # 仅当前文档批量导出


@pytest.mark.unit
def test_tooltips_only_advertise_registered_shortcuts():
    source = _main_source()
    registered = set(re.findall(r'Shortcut \{ sequence: "([^"]+)"', source))
    bar = _command_sections(source)["commandBar"]

    advertised = set(re.findall(r"tooltip: \"[^\"]*?((?:Ctrl|Shift|Alt|F\d)[^\"]*?)\"", bar))
    advertised |= set(re.findall(r"ToolTip\.text: \"[^\"]*?((?:Ctrl|Shift|Alt|F\d)[^\"]*?)\"", bar))
    # 正则会带上尾随文字，逐个按空白拆出键位。
    keys = {token for chunk in advertised for token in chunk.split() if token}
    assert keys, "工具栏应当标注快捷键"
    for key in keys:
        assert key in registered, f"{key} 没有对应的 Shortcut 注册"


@pytest.mark.unit
def test_design_system_documents_the_index_rule():
    doc = (DOCS_ROOT / "hermes-desktop-design-system.md").read_text(encoding="utf-8")

    assert "并列导航与动作按钮不显示编号" in doc
    assert "`showIndex: true`" in doc
    assert "默认不显示编号" in doc
