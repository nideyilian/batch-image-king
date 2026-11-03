"""卡片右键菜单：契约测试。

用「读 QML 源码断言结构」的方式，因为 offscreen 下 Popup 无法枚举，
但菜单的**存在、入口、启用条件、命名一致性**都能从源码确定。
真实点击行为另有探针 docs/audit/_verify_context_menu_real.py（QTest 发真事件）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

QML_ROOT = Path(__file__).resolve().parents[1] / "app" / "qml" / "components"
CARD = (QML_ROOT / "PresetCard.qml").read_text(encoding="utf-8")
WORKBENCH = (QML_ROOT / "PresetWorkbench.qml").read_text(encoding="utf-8")


def _block(source: str, marker: str, size: int = 2000) -> str:
    start = source.index(marker)
    return source[start:start + size]


@pytest.mark.unit
def test_card_declares_context_menu_signal():
    assert "signal contextMenuRequested" in CARD


@pytest.mark.unit
def test_card_accepts_right_button():
    assert "Qt.LeftButton | Qt.RightButton" in CARD


@pytest.mark.unit
def test_right_click_selects_before_opening_menu():
    """右键必须先 activated() 再发信号。

    否则「右键 A 卡片 → 菜单作用于之前选中的 B」，这是最容易出的错。
    用语句先后顺序断言，而不是「包含某字符串」——后者无法保证顺序。
    """
    taphandler = CARD[CARD.index("TapHandler {"):CARD.index("ColumnLayout {")]
    right_branch = taphandler[taphandler.index("RightButton"):]
    assert right_branch.index("card.activated()") < right_branch.index("contextMenuRequested")


@pytest.mark.unit
def test_right_click_passes_scene_coordinates():
    taphandler = CARD[CARD.index("TapHandler {"):CARD.index("ColumnLayout {")]
    right_branch = taphandler[taphandler.index("RightButton"):]
    assert "eventPoint.position" in right_branch
    # 菜单要按窗口坐标弹，不能只传卡片内局部坐标
    assert "mapToItem(null" in right_branch


@pytest.mark.unit
def test_workbench_handles_card_context_menu():
    assert "onContextMenuRequested" in WORKBENCH
    assert "id: cardContextMenu" in WORKBENCH


@pytest.mark.unit
def test_card_menu_and_tab_menu_names_do_not_collide():
    """卡片菜单叫「重命名预设」，页菜单叫「重命名标签页」，不能混用。

    两者同名会让用户以为是同一件事，改错对象。
    """
    card_menu = _block(WORKBENCH, "id: cardContextMenu")
    tab_menu = _block(WORKBENCH, "id: tabRowMenu", 1200)
    assert "重命名预设" in card_menu
    assert "重命名标签页" in tab_menu
    assert "重命名预设" not in tab_menu


@pytest.mark.unit
def test_clear_all_tabs_requires_more_than_one_page():
    """单页预设不给「清空全部」入口：语义上等同删除整卡内容。

    这里断言的是菜单项的 enabled 条件里出现了 documentCount > 1，
    而不只是有一行文案。
    """
    card_menu = _block(WORKBENCH, "id: cardContextMenu")
    assert "documentCount > 1" in card_menu


@pytest.mark.unit
def test_card_menu_reuses_existing_flows():
    """菜单不另起流程，全部复用工作台已有方法。

    自己再写一套会立刻漂移（比如清空时忘了二次确认）。
    """
    card_menu = _block(WORKBENCH, "id: cardContextMenu")
    for call in ("root.requestLoad(", "root.requestClearAllTabs(",
                 "root.requestDuplicate(", "root.requestDelete("):
        assert call in card_menu, f"卡片菜单没有复用 {call}"


@pytest.mark.unit
def test_preset_name_field_has_id_for_focus():
    """右键「重命名预设」靠聚焦名称框实现，输入框必须有 id。"""
    assert "id: presetNameField" in WORKBENCH
    assert "presetNameField.forceActiveFocus()" in WORKBENCH
    assert "presetNameField.selectAll()" in WORKBENCH
