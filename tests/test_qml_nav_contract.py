"""顶部导航栏与命令入口的契约（2026-11-04）。

背景与取舍：
- 顶栏曾有 01 画布 / 02 预设 / 03 导出 / 04 命令 四个带编号的项，编号没有 active 联动，
  会被误读成「必须依次完成的步骤」→ 编号默认关闭（`showIndex: false`）。
- 曾把 4 项折叠成「更多操作」单一菜单，被否：常用动作多一次点击，不符合操作习惯。
  → 并列入口必须保持一点直达，**去重只能删重复项，不能加折叠层**。
- 曾同时存在 6 个 AppMenu（fileMenu / editMenu / layerMenu / canvasMenu / viewMenu /
  helpMenu），全项目 0 处 .popup()，是死代码 → 已删除，其中 3 个别处到不了的命令已迁出。

本文件锁住的规则：
1. 顶栏 3 个一点直达入口（画布 / 预设 / 命令），不折叠、不带编号。
2. 同一功能在同屏只留 1 个可见主按钮（导出、项目预设各锁一条）。
3. 命令菜单只收录「能标注真实快捷键」或「没有按钮入口」的命令。
4. 死菜单不得复活；孤儿命令必须始终有落点。
5. 标注出来的快捷键必须是 Main.qml 里真实注册过的 Shortcut。
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = REPO_ROOT / "app" / "qml"
DOCS_ROOT = REPO_ROOT / "docs"

# 顶栏必须直达的入口：(标签, 动作)
# 文案用「动词 + 对象」，不用「画布/预设/命令」这类名词缩写——缩写要靠 tooltip 才看得懂。
TOP_LEVEL_ACTIONS = (
    ("新建画布", "window.openNewCanvasDialog"),
    ("预设中心", "window.openProjectPresetDrawer"),
    ("更多命令", "commandMenu.popup"),
)

# 曾只在死菜单里可达的 3 个命令，删除死菜单前已迁出，必须始终有落点。
ORPHANED_COMMANDS = (
    ("导入素材文件夹", "imageFolderDialog.open()"),
    ("适合窗口", "canvasWorkspace.fitScale"),
    ("高级图层属性", "window.revealAdvancedProperties()"),
)

DEAD_MENU_IDS = ("fileMenu", "editMenu", "layerMenu", "canvasMenu", "viewMenu", "helpMenu")


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
_MENU_ITEM = re.compile(r'ShapeMenuItem \{ text: "([^"]*)"[^}]*?onTriggered:[ \t]*([A-Za-z0-9_.]+)')


def _actions(section: str) -> list[str]:
    return [a or b for a, b in _ACTION.findall(section)]


@pytest.mark.unit
def test_title_bar_keeps_three_direct_entries_without_index():
    title = _command_sections(_main_source())["titleBar"]

    assert title.count("HermesNavItem {") == len(TOP_LEVEL_ACTIONS)
    assert "HermesNavItem { index:" not in title
    assert 'text: "更多操作"' not in title

    for label, action in TOP_LEVEL_ACTIONS:
        assert f'text: "{label}"' in title, label
        assert f"onClicked: {action}()" in title, action

    # 每个顶栏项都要有写清后果的 tooltip，不能只是复读标签。
    assert title.count("description:") == len(TOP_LEVEL_ACTIONS)


@pytest.mark.unit
def test_export_has_exactly_one_visible_button():
    """导出同屏只留工具栏强调色主按钮，顶栏和命令菜单都不再放第二个。"""

    sections = _command_sections(_main_source())

    assert "window.openBatchExportDrawer" not in sections["titleBar"]
    assert _actions(sections["commandBar"]).count("window.openBatchExportDrawer") == 1
    assert "window.openBatchExportDrawer" not in sections["commandMenu"]


@pytest.mark.unit
def test_project_preset_has_exactly_one_visible_button():
    """项目预设：顶栏是主入口，工具栏与命令菜单不再重复。"""

    sections = _command_sections(_main_source())

    assert "window.openProjectPresetDrawer" in sections["titleBar"]
    assert "window.openProjectPresetDrawer" not in sections["commandBar"]
    assert "window.openProjectPresetDrawer" not in sections["commandMenu"]


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
def test_dead_menus_stay_deleted():
    """6 个 0 引用菜单删掉后不许复活（它们会再抄一整套命令清单）。"""

    source = _main_source()
    for menu_id in DEAD_MENU_IDS:
        assert f"id: {menu_id}" not in source, f"{menu_id} 已删除，不要重新加回来"


@pytest.mark.unit
def test_orphaned_commands_still_reachable_after_menu_cleanup():
    """死菜单里那 3 个别处到不了的命令，删除前必须已迁到别处。"""

    source = _main_source()
    for label, action in ORPHANED_COMMANDS:
        assert f'text: "{label}' in source, f"{label} 没有可见落点"
        assert action in source, f"{label} 的动作 {action} 丢了"


@pytest.mark.unit
def test_command_menu_only_lists_shortcut_aliases_or_buttonless_entries():
    """命令菜单的收录规则：要么带真实快捷键，要么该动作别处没有可见按钮。

    这样菜单保持了「查命令 / 学快捷键」的作用，又不会变成第二个工具栏。
    同时不允许用嵌套菜单做二次折叠（那会把点击次数从 1 抬到 2）。
    """

    sections = _command_sections(_main_source())
    menu = sections["commandMenu"]
    button_surface = sections["titleBar"] + sections["commandBar"]

    items = _MENU_ITEM.findall(menu)
    assert len(items) >= 8, f"命令菜单解析异常，只找到 {len(items)} 项"

    for text, action in items:
        has_shortcut = "\\t" in text
        buttonless = f"onClicked: {action}" not in button_surface
        assert has_shortcut or buttonless, (
            f"「{text}」既没有快捷键可标注，{action} 又已有按钮入口，属于重复项"
        )

    # 不允许「更多操作」式的二次折叠。
    assert "AppMenu {" not in menu
    assert "Menu {" not in menu


@pytest.mark.unit
def test_command_bar_buttons_are_unique_within_itself():
    bar = _command_sections(_main_source())["commandBar"]
    counts = Counter(_actions(bar))

    for action in (
        "window.openBatchExportDrawer",
        "exportDialog.open",
        "window.openMultiTabExportDrawer",
    ):
        assert counts[action] == 1, (action, counts[action])

    # 新建画布的按钮归空工作区首页所有，工具栏不放第二个。
    assert counts["window.openNewCanvasDialog"] == 0
    assert "iconName: AppIcons.fileNew" not in _main_source()


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
    sections = _command_sections(source)

    advertised: set[str] = set()
    for key in ("commandBar", "commandMenu"):
        section = sections[key]
        advertised |= set(re.findall(r"tooltip: \"[^\"]*?((?:Ctrl|Shift|Alt|F\d)[^\"]*?)\"", section))
        advertised |= set(re.findall(r"ToolTip\.text: \"[^\"]*?((?:Ctrl|Shift|Alt|F\d)[^\"]*?)\"", section))
        advertised |= set(re.findall(r"ShapeMenuItem \{ text: \"[^\"]*\\t([^\"]+)\"", section))

    keys = {token for chunk in advertised for token in chunk.split() if token}
    assert keys, "工具栏与命令菜单应当标注快捷键"
    for key in keys:
        assert key in registered, f"{key} 没有对应的 Shortcut 注册"


@pytest.mark.unit
def test_design_system_documents_the_rules():
    doc = (DOCS_ROOT / "hermes-desktop-design-system.md").read_text(encoding="utf-8")

    assert "并列导航与动作按钮不显示编号" in doc
    assert "`showIndex: true`" in doc
    assert "默认不显示编号" in doc
    assert "并列入口保持一点直达" in doc
